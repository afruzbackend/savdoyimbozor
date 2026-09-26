"""Favqulodda holat: bozor omborini ma'lum VAQTga muhrlash (snapshot + xesh)."""

from __future__ import annotations

import hashlib
import json

from django.db import transaction
from django.utils import timezone


def _hash(snapshot: dict) -> str:
    raw = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def build_snapshot(market, at) -> dict:
    """Bozordagi har do'konning `at` paytidagi ombori (o'zgarmas jurnaldan)."""
    from apps.catalog.models import Product
    from apps.catalog.sizes import product_order
    from apps.sales.models import DailyClose, StockMove
    from apps.sales.services.stock import last_count_at, stock_at, verify_chain

    shops = list(market.shops.filter(is_active=True).order_by("number"))
    snap = stock_at(shops, at)
    prods = {p.pk: p for p in Product.objects.filter(pk__in=snap)}
    counts = last_count_at(shops, at)
    photos = {}
    for c in DailyClose.objects.filter(shop__in=shops, date__lte=timezone.localtime(at).date()) \
            .exclude(photo="").order_by("shop_id", "-date"):
        photos.setdefault(c.shop_id, (c.photo.name, c.date.isoformat()))
    out_shops = []
    total_value = total_items = 0
    for shop in shops:
        lines = []
        for pid, (bal, price, _t) in snap.items():
            p = prods.get(pid)
            if p is None or p.shop_id != shop.pk or bal <= 0:
                continue
            value = int(bal * price)
            lines.append((product_order(p), {
                "product": p.name, "size": p.size, "color": p.color, "unit": p.get_unit_display(),
                "barcode": p.barcode, "qty": f"{bal:.3f}", "price": int(price), "value": value,
            }))
        # Model → razmer tartibida: "Krossovka — 36, 37, 38" yonma-yon (kompensatsiyada tushunarli)
        lines = [ln for _k, ln in sorted(lines, key=lambda x: x[0])]
        value = sum(ln["value"] for ln in lines)
        ok, _bad, n = verify_chain(shop)
        last = (StockMove.objects.filter(shop=shop, created_at__lte=at)
                .order_by("-created_at", "-id").values_list("hash", flat=True).first())
        lc = counts.get(shop.pk)
        photo = photos.get(shop.pk)
        out_shops.append({
            "id": shop.pk, "number": shop.number, "owner": shop.owner_name, "stir": shop.stir,
            "phone": shop.owner_phone, "value": value, "items": len(lines),
            "last_count": lc.isoformat() if lc else None,
            "chain_ok": ok, "moves": n, "fingerprint": (last or "")[:16],
            "photo": photo[0] if photo else "", "photo_date": photo[1] if photo else "",
            "lines": lines,
        })
        total_value += value
        total_items += len(lines)
    return {
        "at": at.isoformat(), "market": market.name, "market_id": market.pk,
        "total_value": total_value, "total_items": total_items, "shops": out_shops,
    }


@transaction.atomic
def declare_incident(market, kind, at, description, user):
    from .models import Incident

    snap = build_snapshot(market, at)
    inc = Incident(
        market=market, kind=kind, occurred_at=at, description=description[:2000],
        created_by=user, snapshot=snap, snapshot_hash=_hash(snap),
        total_value=snap["total_value"], shops_count=len(snap["shops"]),
    )
    inc.save()
    inc.number = f"FH-{timezone.localtime(at):%Y}-{inc.pk:04d}"
    Incident.objects.filter(pk=inc.pk).update(number=inc.number)
    return inc


def snapshot_intact(incident) -> bool:
    """Muhrlangan ma'lumot o'zgartirilmaganmi (bazada qo'lda tahrir qilinsa — False)."""
    return _hash(incident.snapshot) == incident.snapshot_hash
