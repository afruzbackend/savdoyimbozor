"""Sotuvni yaratish xizmati — narxlash bitta manbadan (pricing.py)."""

from __future__ import annotations

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.models import SystemSettings

from ..models import Sale, SaleItem
from . import pricing


class InsufficientStock(Exception):
    """Qoldiqdan ko'p sotishga urinilganda."""


@transaction.atomic
def create_sale(
    *,
    shop,
    seller,
    items,
    discount=0,
    rounding=0,
    payment_type="cash",
    is_wholesale=False,
    mode="quick",
    client_ts=None,
    note="",
):
    """Sotuv yaratadi.

    items: [{"product_id"?, "name", "qty", "unit_price"}] — quick rejimda bitta qator ham bo'ladi.
    Vaqt serverdan olinadi; client_ts kelsa va farq katta bo'lsa is_late belgilanadi.
    """
    from decimal import Decimal

    from apps.catalog.models import Product

    settings_obj = SystemSettings.get_solo()
    # Miqdor — hamma joyda Decimal (float yaxlitlash xatosi bo'lmasin). Pul = butun so'm.
    # lines: [(qty, unit_price, product_id, name), ...]
    lines = [
        (Decimal(str(i["qty"])), int(i["unit_price"]), i.get("product_id"), i.get("name", ""))
        for i in items
    ]
    subtotal = sum(int((q * up).quantize(Decimal("1"))) for q, up, _pid, _n in lines)

    # Bir mahsulot bir chekda bir necha marta bo'lishi mumkin — jami miqdorni yig'amiz
    need = {}
    for q, _up, pid, _n in lines:
        if pid:
            need[pid] = need.get(pid, Decimal("0")) + q

    # RACE himoyasi: qoldiq qatorlarini select_for_update bilan QULFLAB o'qiymiz —
    # ikki sotuv bir vaqtda kelsa, ikkinchisi birinchisining commit'ini kutadi va
    # yangilangan qoldiqni ko'radi (manfiy qoldiq bo'lmaydi).
    prods = {p.pk: p for p in Product.objects.select_for_update().filter(pk__in=need)}
    for pid, qty in need.items():
        p = prods.get(pid)
        if p and qty > p.stock:
            raise InsufficientStock(
                f"«{p.name}» qoldig'i yetarli emas: bor {p.stock:g} {p.get_unit_display()}, "
                f"so'ralgan {qty:g}."
            )

    # Tannarxni yig'amiz — tannarxdan past sotishni bloklash uchun
    items_cost = 0
    have_cost = False
    for q, _up, pid, _n in lines:
        if pid and prods.get(pid) and prods[pid].buy_price:
            items_cost += int((q * prods[pid].buy_price).quantize(Decimal("1")))
            have_cost = True
    cost = items_cost if have_cost else None

    priced = pricing.price_sale(
        subtotal, discount, rounding, items_cost=cost, settings=settings_obj
    )

    now = timezone.now()
    is_late = False
    if client_ts:
        try:
            delta = abs((now - client_ts).total_seconds())
            is_late = delta > 300  # 5 daqiqadan ko'p farq — kech kiritilgan
        except TypeError:
            is_late = False

    sale = Sale.objects.create(
        shop=shop,
        seller=seller,
        mode=mode,
        subtotal=priced.subtotal,
        discount=priced.discount,
        rounding=priced.rounding,
        total=priced.total,
        payment_type=payment_type,
        is_wholesale=is_wholesale,
        client_ts=client_ts,
        is_late=is_late,
        note=note[:200],
    )
    for q, up, pid, name in lines:
        SaleItem.objects.create(
            sale=sale,
            product_id=pid,
            product_name=name[:200],
            quantity=q,
            unit_price=up,
            line_total=int((q * up).quantize(Decimal("1"))),
        )
        # Qoldiqni kamaytiramiz (qatorlar allaqachon qulflangan)
        if pid:
            Product.objects.filter(pk=pid).update(stock=F("stock") - q)
    return sale
