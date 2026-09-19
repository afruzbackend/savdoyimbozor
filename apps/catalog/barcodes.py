"""Ichki barkod (EAN-13) generatsiyasi — meva/kiyim/oziq-ovqat, hammasi uchun.

Barcha mahsulotga betakror 13 xonali EAN-13 barkod beriladi (200-prefiks — ichki
foydalanish diapazoni). Barkod maydoni bo'sh bo'lsa avtomatik to'ldiriladi;
sotuvchi barkodni chop etib, mahsulotга yopishtiradi va skanerда o'qiydi.
"""

from __future__ import annotations


def ean13_check_digit(d12: str) -> str:
    """EAN-13 nazorat raqami (12 xonali asosga)."""
    s = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(d12))
    return str((10 - (s % 10)) % 10)


def make_ean13(seed: int) -> str:
    """Ichki EAN-13: '200' + 9 xonali id + nazorat raqami (jami 13)."""
    base = f"200{int(seed):09d}"[:12]
    return base + ean13_check_digit(base)


def ensure_barcode(product) -> str:
    """Mahsulotда barkod bo'lmasa — betakror EAN-13 beradi va saqlaydi."""
    if product.barcode:
        return product.barcode
    from .models import Product

    code = make_ean13(product.pk)
    # Nazariy to'qnashuvda (kam) keyingi bo'sh kodni qidiramiz
    n = product.pk
    while Product.objects.filter(barcode=code).exclude(pk=product.pk).exists():
        n += 1
        code = make_ean13(n)
    product.barcode = code
    product.save(update_fields=["barcode"])
    return code


def ensure_barcodes_for_shop(shop) -> int:
    """Do'konning barkodsiz faol mahsulotlariga barkod beradi. Qaytadi: nechta berildi."""
    from .models import Product

    count = 0
    for p in Product.objects.filter(shop=shop, is_active=True, barcode=""):
        ensure_barcode(p)
        count += 1
    return count
