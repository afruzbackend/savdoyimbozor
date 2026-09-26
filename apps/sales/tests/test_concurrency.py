"""Bir vaqtda sotuv (race) va kasr miqdor (Decimal) — pul/qoldiq to'g'riligi.

Bu testlar RACE va DECIMAL bug'larini ushlaydi. Avval yozildi (bug bor paytda
yiqiladi), keyin `create_sale` select_for_update + Decimal bilan tuzatildi.
"""

import threading
from decimal import Decimal

import pytest
from django.db import connection

from apps.sales.services.sales import InsufficientStock, create_sale


@pytest.mark.django_db(transaction=True)
def test_no_oversell_under_concurrency(shop, seller, product):
    """Ikki sotuv bir vaqtda kelsa — qoldiqdan ko'p sotilmaydi (manfiy bo'lmaydi)."""
    product.stock = Decimal("10.000")
    product.save(update_fields=["stock"])

    results = []

    def worker():
        try:
            create_sale(
                shop=shop,
                seller=seller,
                items=[
                    {"product_id": product.pk, "name": product.name, "qty": 7, "unit_price": 1000}
                ],
            )
            results.append("ok")
        except InsufficientStock:
            results.append("rejected")
        except Exception as e:  # noqa: BLE001
            results.append(f"err:{e}")
        finally:
            connection.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    product.refresh_from_db()
    assert product.stock >= 0, f"manfiy qoldiq: {product.stock}"
    assert results.count("ok") == 1, f"faqat bittasi o'tishi kerak: {results}"
    assert results.count("rejected") == 1, f"biri rad etilishi kerak: {results}"


@pytest.mark.django_db
def test_fractional_qty_exact_stock(shop, seller, product):
    """Kasr miqdor (kg) — qoldiq aniq hisoblanadi, xato bermaydi."""
    product.stock, product.unit = Decimal("1.000"), "kg"  # pomidor tortib sotiladi (dona — butun son)
    product.save(update_fields=["stock", "unit"])
    for _ in range(3):
        create_sale(
            shop=shop,
            seller=seller,
            items=[
                {"product_id": product.pk, "name": product.name, "qty": "0.250", "unit_price": 40000}
            ],
        )
    product.refresh_from_db()
    assert product.stock == Decimal("0.250")  # 1.000 - 3×0.250


@pytest.mark.django_db
def test_fractional_qty_line_total_exact(shop, seller, product):
    """Kasr miqdor × narx — qator jami aniq (float yaxlitlash xatosi yo'q)."""
    from apps.sales.models import SaleItem

    product.unit = "kg"  # 2,5 — faqat tortib sotiladigan tovarda (dona — butun son)
    product.save(update_fields=["unit"])

    sale = create_sale(
        shop=shop,
        seller=seller,
        items=[
            {"product_id": product.pk, "name": product.name, "qty": "2.5", "unit_price": 12000}
        ],
    )
    item = SaleItem.objects.get(sale=sale)
    assert item.line_total == 30000  # 2.5 × 12000
    assert sale.total == 30000
