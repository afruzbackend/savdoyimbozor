"""Mahsulot turiga qarab qoidalar (hammaga bir xil emas):

- bozor narxi qadoq/turi bo'yicha solishtiriladi (250 g choy 1 kg ga keltiriladi, AA — AA bilan);
- dona/quti/bog'lam — butun son (1,5 kurtka yo'q), kg/litr/metr — kasr (2,5 kg pomidor bor);
- hisobdan chiqarish me'yori turga qarab (pomidor 5%, kiyim 0,5%) va oshsa — signal;
- kiyimga kg/litr birligi yo'q; inspektor qidiruvi "250g" = "250 g".
"""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.analytics.models import Alert, MarketPrice
from apps.analytics.scoring.services import (
    _shop_price_score,
    compute_market_prices,
    recompute_for_date,
)
from apps.catalog import variants
from apps.catalog.models import Product, ProductCategory, ShopCategory
from apps.sales.models import StockMove, WriteOff
from apps.sales.services.stock import record_move
from apps.sales.services.writeoffs import excess
from conftest import INSPECTOR_HOST, SELLER_HOST, photo_file

# ---------- Bozor narxi: qadoq va turi aralashmaydi ----------

@pytest.mark.django_db
def test_market_price_normalizes_packs_and_separates_types(shop, market):
    from apps.shops.models import Shop

    other = Shop.objects.create(market=market, row=shop.row, category=shop.category, number="2",
                                stir="987654321", owner_name="Vali")
    choy = ProductCategory.objects.create(name="Choy")
    bat = ProductCategory.objects.create(name="Batareyka")
    # 1-do'kon: kichik qadoq; 2-do'kon: katta qadoq — 1 kg narxi deyarli bir xil
    Product.objects.create(shop=shop, name="Choy — 250 g", base_name="Choy", size="250 g",
                           category=choy, sell_price=25_000)
    Product.objects.create(shop=other, name="Choy — 1 kg", base_name="Choy", size="1 kg",
                           category=choy, sell_price=90_000)
    Product.objects.create(shop=shop, name="Batareyka — AA", base_name="Batareyka", size="AA",
                           category=bat, sell_price=3_000)
    Product.objects.create(shop=other, name="Batareyka — 9V", base_name="Batareyka", size="9V",
                           category=bat, sell_price=25_000)
    day = timezone.localdate()
    med = compute_market_prices(market, day)
    assert med[(choy.pk, "kg")] == 95_000  # 100 000 va 90 000 — bitta 1 kg asosida
    assert med[(bat.pk, "dona:AA")] == 3_000 and med[(bat.pk, "dona:9V")] == 25_000
    assert MarketPrice.objects.filter(product_category=choy, basis="kg").count() == 1
    # 250 g sotuvchi "arzon sotyapti" deb jazolanmaydi (eski mantiqda 25 000 / 57 500 → past ball)
    assert _shop_price_score(shop, med) == 100.0


def test_price_basis_rules():
    assert variants.price_basis("dona", "250 g", 25_000) == ("kg", 100_000)
    assert variants.price_basis("dona", "0,5 L", 9_000) == ("litr", 18_000)
    assert variants.price_basis("kg", "", 90_000) == ("kg", 90_000)
    assert variants.price_basis("dona", "M", 120_000, "clothing") == ("dona", 120_000)
    assert variants.price_basis("dona", "AA", 3_000, "type") == ("dona:AA", 3_000)


# ---------- Butun son: dona/quti ----------

@pytest.fixture
def jacket(shop):
    cat = ProductCategory.objects.create(name="Kurtka")
    p = Product.objects.create(shop=shop, name="Kurtka — M", base_name="Kurtka", size="M",
                               category=cat, unit="dona", buy_price=300_000, sell_price=450_000)
    record_move(p, StockMove.Kind.IN, delta=Decimal("10"), ref="test")
    return p


@pytest.fixture
def tomato(shop):
    cat = ProductCategory.objects.create(name="Pomidor ", default_unit="kg")
    p = Product.objects.create(shop=shop, name="Pomidor kg", category=cat, unit="kg",
                               buy_price=8_000, sell_price=12_000)
    record_move(p, StockMove.Kind.IN, delta=Decimal("100"), ref="test")
    return p


def _sale(client, pid, qty, price):
    body = {"items": [{"product_id": pid, "name": "x", "qty": qty, "unit_price": price}],
            "discount": 0, "rounding": 0, "payment_type": "cash", "mode": "scan"}
    return client.post("/api/sales/", json.dumps(body), content_type="application/json",
                       HTTP_HOST=SELLER_HOST)


@pytest.mark.django_db
def test_piece_goods_sold_only_in_whole_numbers(sclient, jacket, tomato):
    r = _sale(sclient, jacket.pk, 1.5, 450_000)
    assert r.status_code == 400 and "butun son" in r.json()["detail"]
    assert _sale(sclient, jacket.pk, 2, 450_000).status_code == 201
    assert _sale(sclient, tomato.pk, 2.5, 12_000).status_code == 201  # kg — kasr bo'ladi
    jacket.refresh_from_db()
    tomato.refresh_from_db()
    assert jacket.stock == 8 and tomato.stock == Decimal("97.5")


@pytest.mark.django_db
def test_whole_numbers_in_stock_in_writeoff_return(sclient, shop, jacket, tomato):
    sclient.post("/kirim/", {"product": jacket.pk, "quantity": "2.5", "unit_price": "300000",
                             "invoice_photo": photo_file()}, HTTP_HOST=SELLER_HOST)
    sclient.post("/hisobdan-chiqarish/", {"product": jacket.pk, "quantity": "0.5", "reason": "brak",
                                          "photo": photo_file()}, HTTP_HOST=SELLER_HOST)
    sclient.post("/qaytarish/", {"product": jacket.pk, "quantity": "1.5", "reason": "x"},
                 HTTP_HOST=SELLER_HOST)
    jacket.refresh_from_db()
    assert jacket.stock == 10  # hech biri o'tmadi
    # kg — 2,5 kg chirigan pomidorni chiqarsa bo'ladi (forma ham endi "dona" deb qotirmaydi)
    sclient.post("/hisobdan-chiqarish/", {"product": tomato.pk, "quantity": "2.5", "reason": "chirigan",
                                          "photo": photo_file()}, HTTP_HOST=SELLER_HOST)
    tomato.refresh_from_db()
    assert tomato.stock == Decimal("97.5")


@pytest.mark.django_db
def test_quick_stock_in_rejects_fractional_pieces(sclient, jacket):
    rows = [{"product_id": jacket.pk, "qty": "1.5", "price": 300_000}]
    sclient.post("/kirim/tez/saqlash/", {"rows": json.dumps(rows), "invoice_photo": photo_file()},
                 HTTP_HOST=SELLER_HOST)
    jacket.refresh_from_db()
    assert jacket.stock == 10


@pytest.mark.django_db
def test_forms_follow_unit(sclient, jacket, tomato):
    html = sclient.get("/hisobdan-chiqarish/", HTTP_HOST=SELLER_HOST).content.decode()
    assert 'step="1" min="1" name="quantity"' not in html  # endi birlikka qarab (JS)
    assert f'value="{tomato.pk}" data-unit="kg"' in html
    html = sclient.get("/kun-yakuni/", HTTP_HOST=SELLER_HOST).content.decode()
    assert f'step="1" inputmode="numeric" min="0" name="evening_{jacket.pk}"' in html
    assert f'step="any" inputmode="decimal" min="0" name="evening_{tomato.pk}"' in html


# ---------- Hisobdan chiqarish me'yori (turga qarab) va signal ----------

def test_default_waste_by_type():
    assert variants.default_waste("clothing") == Decimal("0.5")
    assert variants.default_waste("none", "Meva-sabzavot") == 5
    assert variants.default_waste("none", "Go'sht-baliq") == 2
    assert variants.default_waste("color", "Gullar") == 10


@pytest.mark.django_db
def test_new_category_gets_type_waste_norm():
    kiyim = ShopCategory.objects.create(name="Kiyim-kechak")
    assert ProductCategory.objects.create(name="Kurtka", shop_category=kiyim).waste_norm_percent == Decimal("0.5")


def _writeoff(sclient, p, qty):
    return sclient.post("/hisobdan-chiqarish/", {"product": p.pk, "quantity": str(qty), "reason": "brak",
                                                 "photo": photo_file()}, HTTP_HOST=SELLER_HOST, follow=True)


@pytest.mark.django_db
def test_writeoff_over_type_norm_warns_and_alerts(sclient, shop, jacket, tomato):
    from conftest import set_settings

    set_settings(writeoff_alert_min=100_000)
    # Pomidor: 100 kg dan 4 kg (4%) — me'yor 5% ichida, signal yo'q
    _writeoff(sclient, tomato, 4)
    assert excess(tomato, timezone.localdate(), 0) is None
    # Kurtka: 10 tadan 1 tasi (10%) — kiyim me'yori 0,5% — sotuvchiga ogohlantirish
    r = _writeoff(sclient, jacket, 1)
    assert "Nazoratchiga signal boradi" in r.content.decode()
    e = excess(jacket, timezone.localdate(), 100_000)
    assert e is not None and e.pct == 10 and e.norm == Decimal("0.5") and e.level == "red"
    # Kun yakunida — nazoratchiga signal (bir marta)
    recompute_for_date(timezone.localdate(), final=True)
    recompute_for_date(timezone.localdate(), final=True)
    alerts = Alert.objects.filter(shop=shop, kind=Alert.Kind.WRITEOFF)
    assert alerts.count() == 1 and "Kurtka" in alerts[0].reason and "Pomidor" not in alerts[0].reason


@pytest.mark.django_db
def test_small_writeoff_value_does_not_alert(sclient, shop, tomato):
    from conftest import set_settings

    set_settings(writeoff_alert_min=1_000_000)
    _writeoff(sclient, tomato, 20)  # 20% — me'yordan oshdi, lekin 160 000 so'm < 1 mln
    recompute_for_date(timezone.localdate(), final=True)
    assert not Alert.objects.filter(shop=shop, kind=Alert.Kind.WRITEOFF).exists()


@pytest.mark.django_db
def test_old_writeoff_does_not_realert_every_day(sclient, shop, jacket):
    from conftest import set_settings

    set_settings(writeoff_alert_min=0)
    _writeoff(sclient, jacket, 1)
    tomorrow = timezone.localdate() + timedelta(days=1)
    recompute_for_date(tomorrow, final=True)  # ertaga yangi chiqarish yo'q — signal ham yo'q
    assert not Alert.objects.filter(shop=shop, kind=Alert.Kind.WRITEOFF, date=tomorrow).exists()
    assert WriteOff.objects.count() == 1


# ---------- Birlik turga mos ----------

@pytest.mark.django_db
def test_clothing_cannot_be_created_in_kg(sclient, shop):
    cat = ProductCategory.objects.create(name="Futbolka")
    sclient.post("/mahsulotlar/", {"category": cat.pk, "unit": "kg", "sell_price": "1"}, HTTP_HOST=SELLER_HOST)
    assert not Product.objects.filter(shop=shop).exists()
    sclient.post("/mahsulotlar/", {"category": cat.pk, "unit": "dona", "sell_price": "1"}, HTTP_HOST=SELLER_HOST)
    assert Product.objects.filter(shop=shop, name="Futbolka").exists()


@pytest.mark.django_db
def test_products_page_offers_only_matching_units(sclient, shop):
    ProductCategory.objects.create(name="Futbolka", shop_category=shop.category)
    ProductCategory.objects.create(name="Olma", shop_category=shop.category, default_unit="kg")
    html = sclient.get("/mahsulotlar/", HTTP_HOST=SELLER_HOST).content.decode()
    import re

    data = {c["name"]: c for c in json.loads(re.search(r'id="catalog-data"[^>]*>(.*?)</script>', html, re.S).group(1))}
    assert data["Futbolka"]["units"] == ["dona", "quti"]
    assert "metr" not in data["Olma"]["units"] and "kg" in data["Olma"]["units"]  # olma metrlab emas
    assert 'id="unit-choices"' in html


# ---------- Inspektor qidiruvi ----------

@pytest.mark.django_db
def test_inspector_search_normalizes_pack_size(iclient, shop):
    cat = ProductCategory.objects.create(name="Choy")
    Product.objects.create(shop=shop, name="Choy — 250 g", base_name="Choy", size="250 g", category=cat,
                           stock=5, sell_price=25_000)
    Product.objects.create(shop=shop, name="Olma", unit="kg", stock=7, sell_price=10_000)
    r = iclient.get("/qidiruv/?p=choy&size=250g", HTTP_HOST=INSPECTOR_HOST)
    assert [p.size for p in r.context["items"]] == ["250 g"]
    r = iclient.get("/qidiruv/?p=o", HTTP_HOST=INSPECTOR_HOST)  # choy (dona) + olma (kg)
    assert r.context["total_qty"] is None  # har xil birlik — "jami" qo'shilmaydi


@pytest.mark.django_db
def test_returns_count_toward_norm_no_loophole(sclient, shop, jacket):
    """"Chirib ketdi" o'rniga "qaytarildi" deb yozish me'yor nazoratidan qochish yo'li emas."""
    from conftest import set_settings

    set_settings(writeoff_alert_min=0)
    r = sclient.post("/qaytarish/", {"product": jacket.pk, "quantity": "2", "reason": "qaytdi"},
                     HTTP_HOST=SELLER_HOST, follow=True)
    assert "Nazoratchiga signal boradi" in r.content.decode()  # 20% > kiyim me'yori 0,5%
    recompute_for_date(timezone.localdate(), final=True)
    a = Alert.objects.get(shop=shop, kind=Alert.Kind.WRITEOFF)
    assert "qaytarish" in a.reason and "Kurtka" in a.reason
