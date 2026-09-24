"""Qoldiq (kun yakuni) hisobi — BITTA MANBA: sotuvchi sahifasi ham, rostlik dvigateli ham.

Jismoniy sotilgan = ertalab + kirim − hisobdan chiqarish − qaytarish − kechqurun (sanoq).

Ilgari: sotilgan = ertalab − kechqurun, ustiga kunning BUTUN kirimi kelish narxida
"sotilgan" deb qo'shilardi. Natijada tovar olgan har halol sotuvchi "yashirilgan savdo"
bo'lib chiqar, akt/jarimaga ham kirardi. Chiqarish/qaytarish esa umuman hisobga olinmasdi.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Sum

ZERO = Decimal("0")


def day_movements(shop, day, until=None) -> dict:
    """Kun ichidagi harakatlar, mahsulot bo'yicha REAL miqdor (qop → dona/kg).

    until: shu vaqtgacha (kun yakuni sanalgan payt) — keyingi harakat sanoqqa kirmaydi.
    Qaytadi: {"in": {pid: qty}, "out": {pid: qty}, "sold": {pid: qty}}
    """
    from ..models import SaleItem, SaleReturn, StockIn, WriteOff

    def upto(qs, field="created_at"):
        return qs.filter(**{f"{field}__lte": until}) if until else qs

    ins = defaultdict(lambda: ZERO)
    for s in upto(StockIn.objects.filter(shop=shop, created_at__date=day)).select_related(
        "product"
    ):
        coeff = (s.product.pack_coeff or 1) if s.in_packs else 1
        ins[s.product_id] += s.quantity * coeff

    out = defaultdict(lambda: ZERO)
    for model in (WriteOff, SaleReturn):
        for r in (
            upto(model.objects.filter(shop=shop, created_at__date=day, product__isnull=False))
            .values("product")
            .annotate(q=Sum("quantity"))
        ):
            out[r["product"]] += r["q"] or ZERO

    sold = defaultdict(lambda: ZERO)
    for r in (
        upto(
            SaleItem.objects.filter(
                sale__shop=shop, sale__created_at__date=day, product__isnull=False
            ),
            "sale__created_at",
        )
        .values("product")
        .annotate(q=Sum("quantity"))
    ):
        sold[r["product"]] = r["q"] or ZERO
    return {"in": ins, "out": out, "sold": sold}


def system_morning(product, mv) -> Decimal:
    """Tizim bo'yicha kun boshidagi qoldiq: joriy + bugun sotilgan − kirim + chiqarilgan."""
    pid = product.pk
    val = product.stock + mv["sold"][pid] - mv["in"][pid] + mv["out"][pid]
    return max(ZERO, val)


def sold_qty(morning, evening, pid, mv) -> Decimal:
    return max(ZERO, morning + mv["in"][pid] - mv["out"][pid] - evening)


def close_sold_value(close) -> int | None:
    """Kun yakuni bo'yicha jismoniy sotilgan qiymat (so'm). Sanoq bo'lmasa None."""
    lines = list(close.lines.all())
    if not lines:
        return None
    mv = day_movements(close.shop, close.date, until=close.updated_at)
    value = 0
    for ln in lines:
        if ln.product_id is None:
            continue
        value += int(sold_qty(ln.morning_qty, ln.evening_qty, ln.product_id, mv) * ln.unit_price)
    return value
