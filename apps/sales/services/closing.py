"""Kun yakuni majburiyati: kechagi savdo kuni sanalmaguncha yangi savdo yo'q.

Tez sotuv (faqat summa) va nasiya mahsulotga bog'lanmaydi — qoldiqdan ayrilmaydi. Ular faqat kun
yakunidagi jismoniy sanoq orqali qoldiq bilan solishtiriladi (qoldiq qismi rostlik hisobida). Sanoq
qilinmasa, sotilgan mahsulot "yo'qolib" ketadi va qoldiq nazorati ishlamaydi. Shuning uchun: savdo
bo'lgan kun yakunlanmagan bo'lsa, ertasi kuni avval o'sha kun sanaladi, keyin sotuv ochiladi.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

LOOKBACK_DAYS = 7  # juda eski ochiq kun (pilotdan oldingi ma'lumot) yangi do'konni to'smasin


def pending_close_day(shop, today=None):
    """Bugundan oldingi oxirgi SAVDO kuni (7 kun ichida) yakunlanmagan bo'lsa — o'sha sana, aks holda None."""
    from apps.core.dates import days_between
    from apps.core.models import SystemSettings

    from ..models import DailyClose, Sale

    if shop is None or not SystemSettings.get_solo().require_daily_close:
        return None
    today = today or timezone.localdate()
    last = (
        Sale.objects.filter(
            shop=shop,
            **days_between(
                "created_at", today - timedelta(days=LOOKBACK_DAYS), today - timedelta(days=1)
            ),
        )
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    if last is None:
        return None
    day = timezone.localtime(last).date()
    return None if DailyClose.objects.filter(shop=shop, date=day).exists() else day


def pending_message(day) -> str:
    return (
        f"{day:%d.%m} kun yakuni qilinmagan: tez sotuv va nasiyadagi mahsulotlar qoldiqdan "
        "ayrilmagan. Avval rastadagi qoldiqni sanab kunni yakunlang — keyin sotuv ochiladi."
    )
