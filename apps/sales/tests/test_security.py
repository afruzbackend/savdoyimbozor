"""Xavfsizlik testlari: cross-shop IDOR (boshqa do'kon mahsuloti/qoldig'iga tegib bo'lmasin)."""

from decimal import Decimal

import pytest

from apps.catalog.models import Product
from apps.sales.models import SaleItem
from apps.sales.services.sales import create_sale
from apps.shops.models import Shop


@pytest.mark.django_db
def test_sale_cannot_touch_other_shop_product(shop, seller, market):
    """Sotuvchi boshqa do'kon product_id sini yuborsa — o'sha do'kon qoldig'i o'zgarmaydi."""
    other_shop = Shop.objects.create(market=market, number="999", stir="111111111")
    victim = Product.objects.create(
        shop=other_shop, name="Begona olma", unit="kg", sell_price=5000, stock=Decimal("100")
    )
    # Sotuvchi (shop) begona do'kon mahsulotini yuboradi
    sale = create_sale(
        shop=shop,
        seller=seller,
        items=[{"product_id": victim.pk, "name": "Begona olma", "qty": "10", "unit_price": 5000}],
    )
    victim.refresh_from_db()
    assert victim.stock == Decimal("100")  # begona qoldiq TEGILMAGAN
    # Qator nomli sifatida yozilgan, begona mahsulotga bog'lanmagan
    item = SaleItem.objects.get(sale=sale)
    assert item.product_id is None
    assert sale.shop == shop  # sotuv o'z do'koniga yozilgan


@pytest.mark.django_db
def test_sale_uses_own_shop_product(shop, seller, product):
    """O'z do'koni mahsuloti bo'lsa — qoldiq to'g'ri kamayadi."""
    product.stock = Decimal("50")
    product.save()
    create_sale(
        shop=shop,
        seller=seller,
        items=[{"product_id": product.pk, "name": product.name, "qty": "8", "unit_price": 3000}],
    )
    product.refresh_from_db()
    assert product.stock == Decimal("42")
