"""Sotuvchi qolgan endpointlari: sotuv ekranlari, qaytarish, hisobdan chiqarish, nasiya, API."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.sales.models import Debt, SaleReturn, WriteOff
from conftest import SELLER_HOST

# 1x1 shaffof PNG (ImageField validatsiyasidan o'tadi)
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000154a24f5f0000000049454e44ae426082"
)


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/sotuv/", "/skaner/", "/kun-yakuni/", "/qaytarish/", "/nasiya/", "/e-tiroz/"])
def test_seller_get_pages(sclient, shop, path):
    assert sclient.get(path, HTTP_HOST=SELLER_HOST).status_code == 200


@pytest.mark.django_db
def test_return_recorded(sclient, shop):
    r = sclient.post(
        "/qaytarish/", {"amount": "20000", "reason": "yaroqsiz"}, HTTP_HOST=SELLER_HOST
    )
    assert r.status_code == 302
    assert SaleReturn.objects.filter(shop=shop, amount=20000).exists()


@pytest.mark.django_db
def test_writeoff_requires_photo(sclient, shop):
    # Fotosiz — yozilmaydi
    sclient.post(
        "/hisobdan-chiqarish/", {"product_name": "Olma", "quantity": "2"}, HTTP_HOST=SELLER_HOST
    )
    assert not WriteOff.objects.filter(shop=shop).exists()
    # Foto bilan — yoziladi
    photo = SimpleUploadedFile("w.png", _PNG, content_type="image/png")
    sclient.post(
        "/hisobdan-chiqarish/",
        {"product_name": "Olma", "quantity": "2", "reason": "chirigan", "photo": photo},
        HTTP_HOST=SELLER_HOST,
    )
    assert WriteOff.objects.filter(shop=shop, product_name="Olma").exists()


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
