"""Sotuvni yaratish xizmati — narxlash bitta manbadan (pricing.py)."""

from __future__ import annotations

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.models import SystemSettings

from ..models import Sale, SaleItem
from . import pricing


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
    settings_obj = SystemSettings.get_solo()
    subtotal = sum(int(round(float(i["qty"]) * int(i["unit_price"]))) for i in items)

    # Tannarxni yig'amiz (agar product_id bo'lsa) — tannarxdan past sotishni bloklash uchun
    items_cost = 0
    have_cost = False
    from apps.catalog.models import Product

    for i in items:
        pid = i.get("product_id")
        if pid:
            p = Product.objects.filter(pk=pid).first()
            if p and p.buy_price:
                items_cost += int(round(float(i["qty"]) * p.buy_price))
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
    for i in items:
        qty = float(i["qty"])
        up = int(i["unit_price"])
        SaleItem.objects.create(
            sale=sale,
            product_id=i.get("product_id"),
            product_name=i.get("name", "")[:200],
            quantity=qty,
            unit_price=up,
            line_total=int(round(qty * up)),
        )
        # Qoldiqni kamaytiramiz
        if i.get("product_id"):
            Product.objects.filter(pk=i["product_id"]).update(stock=F("stock") - qty)
    return sale
