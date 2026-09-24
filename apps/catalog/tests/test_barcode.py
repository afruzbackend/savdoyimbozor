"""Barkod (EAN-13) generatsiyasi testlari."""

import pytest

from apps.catalog.barcodes import ean13_check_digit, ensure_barcode, make_ean13
from apps.catalog.models import Product


def _valid_ean13(code: str) -> bool:
    return len(code) == 13 and code.isdigit() and ean13_check_digit(code[:12]) == code[12]


def test_make_ean13_is_valid():
    code = make_ean13(42)
    assert _valid_ean13(code)
    assert code.startswith("200")


@pytest.mark.django_db
def test_ensure_barcode_assigns_valid_unique(shop):
    p1 = Product.objects.create(shop=shop, name="Olma", sell_price=15000)
    p2 = Product.objects.create(shop=shop, name="Anor", sell_price=17000)
    b1 = ensure_barcode(p1)
    b2 = ensure_barcode(p2)
    assert _valid_ean13(b1) and _valid_ean13(b2)
    assert b1 != b2
    # Ikkinchi marta chaqirilsa o'zgarmaydi (barqaror)
    assert ensure_barcode(p1) == b1


@pytest.mark.django_db
def test_existing_barcode_kept(shop):
    p = Product.objects.create(shop=shop, name="Uzum", sell_price=20000, barcode="4780000000001")
    assert ensure_barcode(p) == "4780000000001"
