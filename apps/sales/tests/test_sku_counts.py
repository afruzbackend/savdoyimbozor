"""Sanoq ishonchi do'kon bo'yicha emas, mahsulot bo'yicha ko'rsatiladi."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.catalog.models import Product
from apps.sales.models import StockMove
from apps.sales.services.stock import last_count_by_product, record_move
from conftest import INSPECTOR_HOST


@pytest.mark.django_db
def test_last_count_is_tracked_per_sku(shop, product):
    other = Product.objects.create(shop=shop, name="Sanalmagan mahsulot", stock=Decimal("8"))
    record_move(product, StockMove.Kind.COUNT, set_to=Decimal("95"), ref="test count")

    counts = last_count_by_product([shop], timezone.now())

    assert product.pk in counts
    assert other.pk not in counts


@pytest.mark.django_db
def test_inventory_marks_uncounted_sku(iclient, shop, product):
    other = Product.objects.create(shop=shop, name="Sanalmagan mahsulot", stock=Decimal("8"))
    record_move(product, StockMove.Kind.COUNT, set_to=Decimal("95"), ref="test count")

    response = iclient.get(f"/ombor/dokon/{shop.pk}/", HTTP_HOST=INSPECTOR_HOST)

    by_product = {line["p"].pk: line for line in response.context["lines"]}
    assert by_product[product.pk]["last_count"] is not None
    assert by_product[other.pk]["last_count"] is None
