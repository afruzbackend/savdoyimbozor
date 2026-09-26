"""Hisobdan chiqarish me'yori — savdoni "chirib ketdi" deb yashirishning oldini olish.

Me'yor mahsulot TURIGA bog'liq (ProductCategory.waste_norm_percent): pomidor 5%, go'sht 2%,
gul 10%, kiyim 0,5%. Bir xil me'yor qo'yilsa yo kiyim do'koni istagancha "chiqarib" yuborardi,
yo meva sotuvchi har kuni signal olardi.

Ulush = 30 kunda hisobdan chiqarilgan / shu davrda qo'lda bo'lgan (davr boshidagi qoldiq + kirim).
Manba — o'zgarmas tovar jurnali (StockMove): tez sotuv mahsulotga bog'lanmasa ham hisob to'g'ri.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum

from apps.core.dates import day_start, days_between

WINDOW_DAYS = 30
DEFAULT_NORM = Decimal("2")  # toifasiz mahsulot (tez kirimda yangi nom bilan yaratilgan)


@dataclass
class Excess:
    product: object
    pct: Decimal  # chiqarilgan ulush, %
    norm: Decimal  # me'yor, %
    written: Decimal  # chiqarilgan miqdor
    value: int  # taxminiy qiymati (so'm)

    @property
    def level(self) -> str:
        return "red" if self.pct >= self.norm * 2 else "yellow"

    def text(self) -> str:
        return (f"{self.product.name} {self.pct:.0f}% (me'yor {self.norm:g}%) — "
                f"{self.written:g} {self.product.get_unit_display()}")


def norm_for(product) -> Decimal:
    cat = product.category
    return Decimal(cat.waste_norm_percent) if cat is not None else DEFAULT_NORM


def share(product, day, days=WINDOW_DAYS):
    """(chiqarilgan, qo'lda bo'lgan) — [day-days+1, day] oralig'ida, jurnal asosida."""
    from apps.sales.models import StockMove

    start = day - timedelta(days=days - 1)
    moves = StockMove.objects.filter(product=product)
    opening = (moves.filter(created_at__lt=day_start(start)).order_by("-created_at", "-id")
               .values_list("balance", flat=True).first()) or Decimal("0")
    window = moves.filter(**days_between("created_at", start, day))
    received = window.filter(kind__in=[StockMove.Kind.IN, StockMove.Kind.OPENING], qty__gt=0) \
        .aggregate(s=Sum("qty"))["s"] or Decimal("0")
    written = -(window.filter(kind=StockMove.Kind.WRITEOFF).aggregate(s=Sum("qty"))["s"] or 0)
    return Decimal(written), max(Decimal(opening), Decimal("0")) + Decimal(received)


def excess(product, day, min_value=0, days=WINDOW_DAYS) -> Excess | None:
    """Me'yordan oshgan bo'lsa — Excess, aks holda None."""
    written, available = share(product, day, days)
    if written <= 0 or available <= 0:
        return None
    pct = written / available * 100
    norm = norm_for(product)
    value = int(written * (product.buy_price or product.sell_price or 0))
    if pct <= norm or value < min_value:
        return None
    return Excess(product, pct, norm, written, value)


def shop_excesses(shop, day, min_value=0) -> list[Excess]:
    """Shu KUNI hisobdan chiqarilgan mahsulotlar ichida me'yordan oshganlari.

    Faqat shu kungi chiqarishlar tekshiriladi — bitta katta chiqarish 30 kun davomida har kuni
    qayta signal bermasin.
    """
    from apps.catalog.models import Product
    from apps.sales.models import StockMove

    pids = set(StockMove.objects.filter(
        shop=shop, kind=StockMove.Kind.WRITEOFF, created_at__gte=day_start(day),
        created_at__lt=day_start(day + timedelta(days=1)),
    ).values_list("product_id", flat=True))
    out = []
    for p in Product.objects.filter(pk__in=pids).select_related("category"):
        e = excess(p, day, min_value)
        if e is not None:
            out.append(e)
    return sorted(out, key=lambda e: -e.value)
