"""To'liq audit topgan baglar uchun regressiya testlari (qaytib buzilmasin)."""

import json

import pytest

from apps.sales.models import RegisterClose, Sale, StockIn
from conftest import SELLER_HOST


def _post_sale(client, body):
    return client.post(
        "/api/sales/", json.dumps(body), content_type="application/json", HTTP_HOST=SELLER_HOST
    )


# ---------- 500 xato (crash) bo'lmasin ----------

@pytest.mark.django_db
@pytest.mark.parametrize("bad", ["abc", "12.5.3", "1e999"])
def test_product_bad_price_no_crash(sclient, shop, bad):
    r = sclient.post(
        "/mahsulotlar/",
        {"name": "Test", "buy_price": bad, "sell_price": "5000"},
        HTTP_HOST=SELLER_HOST,
    )
    assert r.status_code == 302  # xato xabari bilan qaytadi, 500 emas


@pytest.mark.django_db
def test_price_with_spaces_accepted(sclient, shop):
    """Sotuvchi "25 000" deb yozsa ham qabul qilinadi."""
    sclient.post(
        "/mahsulotlar/",
        {"name": "Probelli", "buy_price": "20 000", "sell_price": "25 000"},
        HTTP_HOST=SELLER_HOST,
    )
    from apps.catalog.models import Product

    p = Product.objects.get(shop=shop, name="Probelli")
    assert p.buy_price == 20000 and p.sell_price == 25000


# ---------- Firibgarlik yo'llari yopiq ----------

@pytest.mark.django_db
def test_negative_stock_in_rejected(sclient, shop, product):
    before = product.stock
    sclient.post(
        "/kirim/", {"product": product.pk, "quantity": "-5", "unit_price": "1000"},
        HTTP_HOST=SELLER_HOST,
    )
    product.refresh_from_db()
    assert product.stock == before
    assert not StockIn.objects.filter(shop=shop).exists()


@pytest.mark.django_db
def test_correction_of_old_sale_rejected(sclient, shop):
    from datetime import timedelta

    from django.utils import timezone

    old = Sale.objects.create(shop=shop, subtotal=50000, total=50000)
    Sale.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=5))
    r = sclient.post(
        "/tuzatish/", {"sale": old.pk, "new_total": "1000", "reason": "x"}, HTTP_HOST=SELLER_HOST
    )
    assert r.status_code == 404
    old.refresh_from_db()
    assert old.total == 50000


# ---------- Noto'g'ri ayblov bo'lmasin ----------

@pytest.mark.django_db
def test_register_close_requires_counted(sclient, shop):
    sclient.post("/kassa/", {"counted_cash": ""}, HTTP_HOST=SELLER_HOST)
    assert not RegisterClose.objects.filter(shop=shop).exists()
    sclient.post("/kassa/", {"counted_cash": "0"}, HTTP_HOST=SELLER_HOST)
    assert RegisterClose.objects.filter(shop=shop, counted_cash=0).exists()


@pytest.mark.django_db
def test_daily_close_requires_counted(sclient, shop):
    sclient.post("/kun-yakuni/", {"counted_cash": ""}, HTTP_HOST=SELLER_HOST)
    assert not RegisterClose.objects.filter(shop=shop).exists()


# ---------- API validatsiyasi ----------

@pytest.mark.django_db
def test_api_rejects_negative_qty(sclient, shop):
    r = _post_sale(sclient, {"items": [{"name": "x", "qty": -1, "unit_price": 5000}]})
    assert r.status_code == 400
    assert not Sale.objects.filter(shop=shop).exists()


@pytest.mark.django_db
def test_api_rejects_unknown_payment_type(sclient, shop):
    r = _post_sale(sclient, {"items": [{"name": "x", "qty": 1, "unit_price": 5000}],
                             "payment_type": "bitcoin"})
    assert r.status_code == 400


@pytest.mark.django_db
def test_api_bad_number_is_400_not_500(sclient, shop):
    r = _post_sale(sclient, {"items": [{"name": "x", "qty": "abc", "unit_price": 5000}]})
    assert r.status_code == 400


@pytest.mark.django_db
def test_api_zero_total_not_saved(sclient, shop):
    r = _post_sale(sclient, {"items": [{"name": "x", "qty": 1, "unit_price": 0}]})
    assert r.status_code == 400
    assert not Sale.objects.filter(shop=shop).exists()


@pytest.mark.django_db
def test_api_client_uid_is_idempotent(sclient, shop):
    """Offline navbatdan qayta yuborilgan sotuv dublikat yaratmaydi."""
    body = {"items": [{"name": "x", "qty": 1, "unit_price": 7000}], "client_uid": "abc-123"}
    r1 = _post_sale(sclient, body)
    r2 = _post_sale(sclient, body)
    assert r1.status_code == 201 and r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    assert Sale.objects.filter(shop=shop).count() == 1
