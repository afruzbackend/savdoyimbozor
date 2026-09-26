"""Tez kirim: o'zbekcha erkin matn (ovozdan) → kirim qatorlari; tasdiqlab saqlash."""

import json
from decimal import Decimal

import pytest

from apps.catalog.models import Product
from apps.sales.models import StockIn, StockMove
from apps.sales.services.quick_entry import parse, parse_segment
from conftest import SELLER_HOST, photo_file, set_settings


@pytest.mark.parametrize("text,qty,unit,price,name", [
    ("pomidor o'n besh kilo sakkiz mingdan", Decimal(15), "kg", 8000, "pomidor"),
    ("15 kg olma narxi 12 000", Decimal(15), "kg", 12000, "olma"),
    ("banan 20 kilo 18 ming", Decimal(20), "kg", 18000, "banan"),
    ("kartoshka 2 qop", Decimal(2), "qop", None, "kartoshka"),
    ("bir yarim kilo zira ellik ming so'm", Decimal("1.5"), "kg", 50000, "zira"),
    ("shakar ikki yuz ellik kilo 9 500dan", Decimal(250), "kg", 9500, "shakar"),
    ("tuxum 30ta 1500", Decimal(30), "dona", 1500, "tuxum"),
    ("yog' 5 litr narxi o'ttiz ming", Decimal(5), "litr", 30000, "yog'"),
    ("500 gramm murch", Decimal("0.5"), "kg", None, "murch"),
    ("olma 2 yarim kilo", Decimal("2.5"), "kg", None, "olma"),
    ("Oʻn ikki dona non 4 mingdan", Decimal(12), "dona", 4000, "non"),  # ʻ apostrof ham
])
def test_parse_segment(text, qty, unit, price, name):
    d = parse_segment(text)
    assert d["qty"] == qty and d["unit"] == unit and d["price"] == price and d["name"] == name


@pytest.mark.django_db
def test_parse_matches_catalog_and_splits(shop, product):
    Product.objects.create(shop=shop, name="Kartoshka", unit="kg", buy_price=3000,
                           pack_coeff=Decimal("50"))
    rows = parse("pomidorr 15 kilo 8 mingdan, kartoshka 2 qop; anor 10 kilo 20000\nfoo",
                 Product.objects.filter(shop=shop))
    assert len(rows) == 4
    pom, kar, anor, foo = rows
    assert pom["product_id"] == product.pk and pom["qty"] == "15" and pom["price"] == 8000  # imlo xatosi
    assert kar["product_name"] == "Kartoshka" and kar["in_packs"] is True and kar["unit"] == "kg"
    assert kar["price"] == 3000  # narx aytilmadi — oxirgi kelish narxi
    assert anor["is_new"] and anor["product_name"] == "Anor" and anor["price"] == 20000
    assert foo["error"] == "miqdor topilmadi"


@pytest.mark.django_db
def test_parse_endpoint(sclient, product):
    r = sclient.post("/kirim/tez/tahlil/", json.dumps({"text": "pomidor 5 kilo 9000"}),
                     content_type="application/json", HTTP_HOST=SELLER_HOST)
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert rows[0]["product_id"] == product.pk and rows[0]["qty"] == "5"
    assert StockIn.objects.count() == 0  # tahlil bazaga yozmaydi


@pytest.mark.django_db
def test_save_creates_stockins_moves_and_new_product(sclient, shop, product):
    set_settings(stockin_photo_min=0)
    stock0 = product.stock
    rows = [
        {"product_id": product.pk, "product_name": "Pomidor", "qty": "10", "unit": "kg", "price": 8000},
        {"product_id": None, "product_name": "Anor", "qty": "4.5", "unit": "kg", "price": 20000,
         "is_new": True},
    ]
    r = sclient.post("/kirim/tez/saqlash/", {"rows": json.dumps(rows), "supplier_name": "Ali aka"},
                     HTTP_HOST=SELLER_HOST)
    assert r.status_code == 302
    assert StockIn.objects.filter(shop=shop, source="quick").count() == 2
    product.refresh_from_db()
    assert product.stock == stock0 + 10
    anor = Product.objects.get(shop=shop, name="Anor")
    assert anor.stock == Decimal("4.5") and anor.barcode
    assert StockMove.objects.filter(kind="in").count() == 2
    assert set(StockIn.objects.values_list("supplier_name", flat=True)) == {"Ali aka"}


@pytest.mark.django_db
def test_save_requires_photo_for_big_batch_and_shares_one_file(sclient, shop, product):
    set_settings(stockin_photo_min=1_000_000)
    rows = [{"product_id": product.pk, "qty": "100", "price": 8000},
            {"product_id": product.pk, "qty": "50", "price": 8000}]  # 1.2 mln
    sclient.post("/kirim/tez/saqlash/", {"rows": json.dumps(rows)}, HTTP_HOST=SELLER_HOST)
    assert not StockIn.objects.exists()
    sclient.post("/kirim/tez/saqlash/", {"rows": json.dumps(rows), "invoice_photo": photo_file()},
                 HTTP_HOST=SELLER_HOST)
    names = set(StockIn.objects.values_list("invoice_photo", flat=True))
    assert StockIn.objects.count() == 2 and len(names) == 1 and names != {""}


@pytest.mark.django_db
def test_save_rejects_foreign_product_and_bad_rows(sclient, market, product):
    from apps.shops.models import Shop

    other = Shop.objects.create(market=market, number="88", stir="88")
    foreign = Product.objects.create(shop=other, name="Begona", unit="kg")
    for rows in ([{"product_id": foreign.pk, "qty": "1", "price": 1}],
                 [{"product_id": product.pk, "qty": "-3", "price": 1}],
                 [{"product_id": product.pk, "qty": "abc", "price": 1}],
                 [{"product_name": "", "qty": "1", "price": 1}]):
        sclient.post("/kirim/tez/saqlash/", {"rows": json.dumps(rows)}, HTTP_HOST=SELLER_HOST)
    sclient.post("/kirim/tez/saqlash/", {"rows": "buzuq json"}, HTTP_HOST=SELLER_HOST)
    assert not StockIn.objects.exists()
