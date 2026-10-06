"""Fiskal chek qatorlari tashqi manbaning aynan o'zini saqlaydi."""

from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.cash.models import FiscalReceipt, FiscalReceiptLine


@pytest.mark.django_db
def test_receipt_keeps_multiple_lines_and_return_link(shop):
    receipt = FiscalReceipt.objects.create(
        shop=shop, source="tax_api", source_receipt_id="EXT-100", issued_at=timezone.now(), total=25_000
    )
    FiscalReceiptLine.objects.create(receipt=receipt, line_number=1, product_name="Olma", product_code="123", quantity=Decimal("2"), unit_price=10_000, line_total=20_000)
    FiscalReceiptLine.objects.create(receipt=receipt, line_number=2, product_name="Paket", quantity=Decimal("1"), unit_price=5_000, line_total=5_000)
    returned = FiscalReceipt.objects.create(
        shop=shop, source="tax_api", source_receipt_id="EXT-101", issued_at=timezone.now(),
        status=FiscalReceipt.Status.RETURNED, original_receipt=receipt, total=20_000,
    )

    assert receipt.lines.count() == 2
    assert returned.original_receipt == receipt


@pytest.mark.django_db
def test_external_receipt_id_is_idempotent_per_source(shop):
    FiscalReceipt.objects.create(shop=shop, source="tax_api", source_receipt_id="EXT-100", issued_at=timezone.now())
    with pytest.raises(IntegrityError):
        FiscalReceipt.objects.create(shop=shop, source="tax_api", source_receipt_id="EXT-100", issued_at=timezone.now())
