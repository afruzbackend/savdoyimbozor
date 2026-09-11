"""Sotuvchi oqimi: mahsulot qo'shish, kirim, sotuv, tuzatish, sahifalar."""

import pytest

from apps.catalog.models import Product
from apps.sales.models import Correction, RegisterClose, Sale, StockIn
from apps.sales.services import sales as sale_svc
from conftest import SELLER_HOST


@pytest.mark.django_db
def test_add_product(sclient, shop):
    r = sclient.post(
        "/mahsulotlar/",
        {"name": "Kartoshka", "unit": "kg", "buy_price": "5000", "sell_price": "7000"},
        HTTP_HOST=SELLER_HOST,
    )
    assert r.status_code == 302
    assert Product.objects.filter(shop=shop, name="Kartoshka").exists()


@pytest.mark.django_db
def test_stock_in_increases_stock(sclient, shop, product):
    start = product.stock
    r = sclient.post(
        "/kirim/",
        {"product": product.pk, "quantity": "20", "unit_price": "8000"},
        HTTP_HOST=SELLER_HOST,
    )
    assert r.status_code == 302
    product.refresh_from_db()
    assert product.stock == start + 20
    assert StockIn.objects.filter(product=product).count() == 1


@pytest.mark.django_db
def test_sale_reduces_stock(shop, seller, product):
    start = product.stock
    sale_svc.create_sale(
        shop=shop,
        seller=seller,
        items=[{"product_id": product.pk, "name": product.name, "qty": 3, "unit_price": 12000}],
    )
    product.refresh_from_db()
    assert product.stock == start - 3


@pytest.mark.django_db
def test_correction_keeps_old_value(sclient, shop, seller):
    sale = Sale.objects.create(shop=shop, seller=seller, total=50000, subtotal=50000)
    r = sclient.post(
        "/tuzatish/",
        {"sale": sale.pk, "new_total": "40000", "reason": "xato summa"},
        HTTP_HOST=SELLER_HOST,
    )
    assert r.status_code == 302
    sale.refresh_from_db()
    assert sale.total == 40000
    corr = Correction.objects.get(shop=shop, target_id=sale.id)
    assert corr.old_value == "50000" and corr.new_value == "40000"


@pytest.mark.django_db
def test_correction_requires_reason(sclient, shop, seller):
    sale = Sale.objects.create(shop=shop, seller=seller, total=50000, subtotal=50000)
    sclient.post(
        "/tuzatish/",
        {"sale": sale.pk, "new_total": "40000", "reason": ""},
        HTTP_HOST=SELLER_HOST,
    )
    sale.refresh_from_db()
    assert sale.total == 50000  # sababsiz tuzatilmaydi
    assert not Correction.objects.filter(target_id=sale.id).exists()


@pytest.mark.django_db
def test_register_totals_split_by_payment(sclient, shop, seller):
    Sale.objects.create(shop=shop, seller=seller, total=30000, payment_type="cash")
    Sale.objects.create(shop=shop, seller=seller, total=20000, payment_type="card")
    r = sclient.get("/kassa/", HTTP_HOST=SELLER_HOST)
    assert r.status_code == 200
    html = r.content.decode()
    assert "30\xa0000" in html or "30 000" in html  # naqd


@pytest.mark.django_db
def test_register_close_records_z_report(sclient, shop, seller):
    Sale.objects.create(shop=shop, seller=seller, total=30000, payment_type="cash")
    r = sclient.post(
        "/kassa/", {"counted_cash": "25000", "note": "kamomad"}, HTTP_HOST=SELLER_HOST
    )
    assert r.status_code == 302
    z = RegisterClose.objects.get(shop=shop)
    assert z.expected_cash == 30000
    assert z.counted_cash == 25000
    assert z.difference == -5000  # kamomad


@pytest.mark.django_db
def test_register_close_does_not_create_cashrecord(sclient, shop, seller):
    """Z-hisobot mustaqil deklaratsiyani (CashRecord) o'zgartirmasligi kerak."""
    from apps.cash.models import CashRecord

    Sale.objects.create(shop=shop, seller=seller, total=30000, payment_type="cash")
    sclient.post("/kassa/", {"counted_cash": "30000"}, HTTP_HOST=SELLER_HOST)
    assert not CashRecord.objects.filter(shop=shop).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path", ["/", "/hisobot/", "/reyting/", "/tuzatish/", "/mahsulotlar/", "/kassa/"]
)
def test_seller_pages_render(sclient, shop, product, path):
    r = sclient.get(path, HTTP_HOST=SELLER_HOST)
    assert r.status_code == 200
