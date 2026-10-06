"""Admin qoldiqni jurnalni chetlab o'zgartirmasligi uchun regressiya testlari."""

import pytest
from django.urls import reverse

from apps.catalog.admin import ProductAdmin
from apps.catalog.models import Product
from apps.sales.models import StockAdjustment, StockMove


@pytest.mark.django_db
def test_product_admin_makes_stock_readonly(admin_user):
    assert "stock" in ProductAdmin(Product, None).get_readonly_fields(None)


@pytest.mark.django_db
def test_admin_adjustment_records_count_move(aclient, admin_user, product):
    response = aclient.post(
        reverse("admin:sales_stockadjustment_add"),
        {"product": product.pk, "counted_qty": "87", "reason": "Jismoniy sanoq farqi"},
    )

    assert response.status_code == 302
    adjustment = StockAdjustment.objects.get(product=product)
    assert adjustment.user == admin_user
    move = StockMove.objects.get(product=product, ref=f"StockAdjustment#{adjustment.pk}")
    assert move.kind == StockMove.Kind.COUNT and move.balance == 87
    product.refresh_from_db()
    assert product.stock == 87


@pytest.mark.django_db
def test_adjustment_cannot_be_edited(product):
    adjustment = StockAdjustment.objects.create(
        product=product, counted_qty=90, reason="Sinov uchun"
    )
    adjustment.reason = "Boshqa sabab"
    with pytest.raises(ValueError, match="o'zgartirilmaydi"):
        adjustment.save()
