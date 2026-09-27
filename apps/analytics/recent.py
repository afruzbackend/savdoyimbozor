"""Oxirgi kunlar bo'yicha rostlik — xarita, dashboard, do'kon sahifasi va sotuvchi hisoboti UCHUN BITTA manba.

Bitta umumiy sana olinmaydi: o'sha kuni o'lchanmagan do'kon (bugun hali hisoblanmagan, 1-2 kunlik
yangi do'kon, kechagi kassa yuklanmagan) "—" bo'lib qolardi. Har do'kon o'zining oxirgi kunlaridan
hisoblanadi — bitta o'lchangan kun ham yetadi. Baza darajasida bitta agregat so'rov (respublika
bo'yicha minglab do'konda ham qatorlar Python'ga yuklanmaydi).
"""

from __future__ import annotations

from datetime import timedelta

RECENT_DAYS = 7


def recent_scores(shops, today, days: int = RECENT_DAYS) -> dict:
    """{shop_id: {truth, days, last, entered, cash}} — faqat O'LCHANGAN kunlar (kassa/kamera/qoldiq)."""
    from django.db.models import Avg, Count, Max, Sum

    from .models import DailyScore

    rows = (
        DailyScore.objects.filter(
            shop__in=shops, date__range=(today - timedelta(days=days - 1), today), measured=True
        )
        .values("shop_id")
        .annotate(
            t=Avg("truth_pct"),
            n=Count("id"),
            last=Max("date"),
            e=Sum("entered_sales"),
            c=Sum("cash_amount"),
        )
    )
    return {
        r["shop_id"]: {
            "truth": round(r["t"]),
            "days": r["n"],
            "last": r["last"],
            "entered": r["e"] or 0,
            "cash": r["c"] or 0,
        }
        for r in rows
    }


def level(truth, cfg) -> str:
    """Rang darajasi — chegaralar SystemSettings'dan (kodda 80/50 qotirilmaydi)."""
    if truth is None:
        return "none"
    if truth >= cfg.green_threshold:
        return "green"
    if truth >= cfg.yellow_threshold:
        return "yellow"
    return "red"
