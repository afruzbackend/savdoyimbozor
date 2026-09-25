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


# ============================================================================
# O'ZGARMAS OMBOR JURNALI — qoldiq FAQAT shu funksiya orqali o'zgaradi
# ============================================================================


class NegativeStock(Exception):
    """Qoldiqdan ko'p chiqarishga urinish (qulf ostida tekshiriladi)."""


def record_move(product, kind, *, delta=None, set_to=None, ref="", user=None,
                allow_negative=True):
    """Qoldiqni o'zgartiradi VA jurnalga yozadi (xesh zanjiri bilan). Qaytadi: StockMove.

    delta — o'zgarish (+kirim / −sotuv); set_to — sanoq (qoldiq shu songa tenglashadi).
    Do'kon qatori qulflanadi: bir do'kon zanjiri parallel yozuvlarda buzilmaydi.
    """
    from django.db import transaction
    from django.utils import timezone

    from apps.catalog.models import Product
    from apps.shops.models import Shop

    from ..models import StockMove

    with transaction.atomic():
        Shop.objects.select_for_update().filter(pk=product.shop_id).first()
        p = Product.objects.select_for_update().get(pk=product.pk)
        before = p.stock
        after = Decimal(set_to) if set_to is not None else before + Decimal(delta)
        if not allow_negative and after < 0:
            raise NegativeStock(
                f"«{p.name}» qoldig'i {before:g}, so'ralgan {abs(Decimal(delta)):g}."
            )
        Product.objects.filter(pk=p.pk).update(stock=after)
        prev = (
            StockMove.objects.filter(shop_id=p.shop_id)
            .order_by("-created_at", "-id")
            .values_list("hash", flat=True)
            .first()
            or ""
        )
        m = StockMove(
            shop_id=p.shop_id, product_id=p.pk, kind=kind,
            qty=after if kind == StockMove.Kind.OPENING else after - before, balance=after,
            unit_price=p.sell_price, ref=str(ref)[:60], user=user, created_at=timezone.now(),
            prev_hash=prev,
        )
        m.hash = m.compute_hash()
        m.save()
        product.stock = after
        return m


def verify_chain(shop) -> tuple[bool, int | None, int]:
    """Do'kon jurnali butunmi. Qaytadi: (butun, birinchi buzilgan yozuv id, yozuvlar soni)."""
    from ..models import StockMove

    prev = ""
    n = 0
    for m in StockMove.objects.filter(shop=shop).order_by("created_at", "id").iterator():
        n += 1
        if m.prev_hash != prev or m.hash != m.compute_hash():
            return False, m.pk, n
        prev = m.hash
    return True, None, n


def stock_at(shops, at) -> dict:
    """Berilgan VAQTdagi qoldiq: {product_id: (qoldiq, narx, oxirgi harakat vaqti)}.

    Har mahsulot bo'yicha `at` gacha bo'lgan OXIRGI jurnal yozuvi (PostgreSQL DISTINCT ON).
    """
    from ..models import StockMove

    rows = (
        StockMove.objects.filter(shop__in=shops, created_at__lte=at)
        .order_by("product_id", "-created_at", "-id")
        .distinct("product_id")
        .values_list("product_id", "balance", "unit_price", "created_at")
    )
    return {pid: (bal, price, t) for pid, bal, price, t in rows}


def last_count_at(shops, at) -> dict:
    """Har do'kon uchun `at` gacha oxirgi JISMONIY sanoq vaqti (kun yakuni)."""
    from ..models import StockMove

    rows = (
        StockMove.objects.filter(shop__in=shops, created_at__lte=at, kind=StockMove.Kind.COUNT)
        .order_by("shop_id", "-created_at")
        .distinct("shop_id")
        .values_list("shop_id", "created_at")
    )
    return dict(rows)
