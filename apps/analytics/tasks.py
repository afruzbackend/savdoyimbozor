"""Celery fon vazifalari (P3'da scoring bilan to'ldiriladi)."""

from celery import shared_task


@shared_task
def recompute_today():
    """Bugungi rostlik ballarini yangilaydi (har RECOMPUTE_EVERY_MIN daqiqada, standart 5).

    Qulf: oldingi hisob tugamagan bo'lsa yangisi o'tkazib yuboriladi — minglab do'konda hisob
    oraliqdan uzoq cho'zilsa, navbatda ustma-ust vazifalar yig'ilib protsessorni to'ldirmasin.
    """
    from django.core.cache import cache
    from django.utils import timezone

    from .scoring.services import recompute_for_date

    if not cache.add("lock:recompute_today", 1, timeout=30 * 60):
        return "skip: oldingi hisob davom etmoqda"
    try:
        return recompute_for_date(timezone.localdate())
    finally:
        cache.delete("lock:recompute_today")


@shared_task
def recompute_yesterday():
    """Kechagi kunni yakuniy hisoblaydi + bozor narxi (har kecha)."""
    from datetime import timedelta

    from django.utils import timezone

    from .scoring.services import recompute_for_date

    return recompute_for_date(timezone.localdate() - timedelta(days=1))


@shared_task
def check_gate_yesterday():
    """Darvoza kamerasi ko'rgan tushirishlar kirim bilan solishtiriladi (har kuni 14:10)."""
    from datetime import timedelta

    from django.utils import timezone

    from .gate import check_day

    return check_day(timezone.localdate() - timedelta(days=1))
