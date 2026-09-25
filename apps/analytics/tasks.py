"""Celery fon vazifalari (P3'da scoring bilan to'ldiriladi)."""

from celery import shared_task


@shared_task
def recompute_today():
    """Bugungi rostlik ballarini yangilaydi (har 5 daqiqada)."""
    from django.utils import timezone

    from .scoring.services import recompute_for_date

    return recompute_for_date(timezone.localdate())


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
