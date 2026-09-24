"""Sotuvchi qolgan endpointlari: sotuv ekranlari, qaytarish, hisobdan chiqarish, nasiya, API."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.sales.models import Debt, SaleReturn, WriteOff
from conftest import SELLER_HOST


# Haqiqiy (Pillow bilan yaratilgan) PNG — foto tekshiruvidan (validate_image_upload) o'tadi
def _make_png():
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (2, 2), (10, 120, 40)).save(buf, format="PNG")
    return buf.getvalue()


_PNG = _make_png()


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/sotuv/", "/skaner/", "/kun-yakuni/", "/qaytarish/", "/nasiya/", "/e-tiroz/"])
def test_seller_get_pages(sclient, shop, path):
    assert sclient.get(path, HTTP_HOST=SELLER_HOST).status_code == 200


@pytest.mark.django_db
def test_return_recorded(sclient, shop, product):
    # Mahsulotsiz / sababsiz / qoldiqdan ko'p — yozilmaydi (dalilsiz chiqarish yo'li yopiq)
    sclient.post("/qaytarish/", {"amount": "20000", "reason": "yaroqsiz"}, HTTP_HOST=SELLER_HOST)
    sclient.post("/qaytarish/", {"product": product.pk, "quantity": "1"}, HTTP_HOST=SELLER_HOST)
    sclient.post("/qaytarish/", {"product": product.pk, "quantity": "99999", "reason": "x"},
                 HTTP_HOST=SELLER_HOST)
    assert not SaleReturn.objects.filter(shop=shop).exists()
    # To'g'ri — yoziladi, qoldiq kamayadi
    before = product.stock
    r = sclient.post(
        "/qaytarish/",
        {"product": product.pk, "quantity": "2", "amount": "20000", "reason": "yaroqsiz"},
        HTTP_HOST=SELLER_HOST,
    )
    assert r.status_code == 302
    assert SaleReturn.objects.filter(shop=shop, amount=20000).exists()
    product.refresh_from_db()
    assert product.stock == before - 2


@pytest.mark.django_db
def test_return_reduces_stock(sclient, shop, product):
    # 285 kg anordan 200 kg achib qaytarildi → 85 kg qoladi
    from decimal import Decimal

    product.stock = Decimal("285")
    product.sell_price = 15000
    product.save()
    r = sclient.post(
        "/qaytarish/",
        {"product": str(product.pk), "quantity": "200", "reason": "achigan"},
        HTTP_HOST=SELLER_HOST,
    )
    assert r.status_code == 302
    product.refresh_from_db()
    assert product.stock == Decimal("85")
    ret = SaleReturn.objects.get(shop=shop, product=product)
    assert ret.quantity == Decimal("200")
    # Summa bo'sh berildi → narx × miqdor = 15000 × 200
    assert ret.amount == 200 * 15000


@pytest.mark.django_db
def test_stock_in_manual_creates_product(sclient, shop):
    from decimal import Decimal

    from apps.catalog.models import Product

    r = sclient.post(
        "/kirim/",
        {"new_name": "Yangi Anor", "unit": "kg", "sell_price": "18000",
         "quantity": "50", "unit_price": "12000"},
        HTTP_HOST=SELLER_HOST,
    )
    assert r.status_code == 302
    p = Product.objects.get(shop=shop, name="Yangi Anor")
    assert p.stock == Decimal("50")
    assert p.sell_price == 18000


@pytest.mark.django_db
def test_writeoff_requires_photo(sclient, shop, product):
    # Fotosiz — yozilmaydi
    sclient.post(
        "/hisobdan-chiqarish/",
        {"product": product.pk, "quantity": "2", "reason": "chirigan"},
        HTTP_HOST=SELLER_HOST,
    )
    assert not WriteOff.objects.filter(shop=shop).exists()
    # Sababsiz — yozilmaydi
    photo = SimpleUploadedFile("w.png", _PNG, content_type="image/png")
    sclient.post(
        "/hisobdan-chiqarish/",
        {"product": product.pk, "quantity": "2", "photo": photo},
        HTTP_HOST=SELLER_HOST,
    )
    assert not WriteOff.objects.filter(shop=shop).exists()
    # Qoldiqdan ko'p — yozilmaydi
    photo = SimpleUploadedFile("w.png", _PNG, content_type="image/png")
    sclient.post(
        "/hisobdan-chiqarish/",
        {"product": product.pk, "quantity": "99999", "reason": "chirigan", "photo": photo},
        HTTP_HOST=SELLER_HOST,
    )
    assert not WriteOff.objects.filter(shop=shop).exists()
    # To'g'ri: mahsulot + sabab + foto — yoziladi va qoldiq kamayadi
    before = product.stock
    photo = SimpleUploadedFile("w.png", _PNG, content_type="image/png")
    sclient.post(
        "/hisobdan-chiqarish/",
        {"product": product.pk, "quantity": "2", "reason": "chirigan", "photo": photo},
        HTTP_HOST=SELLER_HOST,
    )
    assert WriteOff.objects.filter(shop=shop, product=product).exists()
    product.refresh_from_db()
    assert product.stock == before - 2


@pytest.mark.django_db
def test_debt_added(sclient, shop):
    r = sclient.post(
        "/nasiya/", {"customer_name": "Vali", "amount": "50000"}, HTTP_HOST=SELLER_HOST
    )
    assert r.status_code == 302
    assert Debt.objects.filter(shop=shop, customer_name="Vali").exists()


@pytest.mark.django_db
def test_api_product_lookup(sclient, shop, product):
    r = sclient.get(f"/api/products/lookup/?q={product.name}", HTTP_HOST=SELLER_HOST)
    assert r.status_code == 200
    assert any(p["name"] == product.name for p in r.json())


@pytest.mark.django_db
def test_api_sales_requires_auth():
    from django.test import Client

    r = Client().post(
        "/api/sales/", {"items": []}, content_type="application/json", HTTP_HOST=SELLER_HOST
    )
    assert r.status_code in (401, 403)
