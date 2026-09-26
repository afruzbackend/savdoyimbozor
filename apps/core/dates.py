"""Kun bo'yicha filtr — INDEKSDAN foydalanadigan shaklda.

`created_at__date=day` SQL'da `(created_at AT TIME ZONE 'Asia/Tashkent')::date = ...` bo'ladi:
PostgreSQL `created_at` indeksini ishlata olmaydi va butun jadvalni o'qiydi (sotuvlar eng katta
jadval — millionlab qator). Buning o'rniga vaqt ORALIG'I: `created_at >= kun boshi AND < keyingi
kun boshi` — (shop, created_at) indeksi ishlaydi. Natija bir xil (mahalliy kun chegaralari).

    Sale.objects.filter(shop=shop, **on_day("created_at", day))
    Sale.objects.filter(**since_day("created_at", today - timedelta(days=29)))
    Sale.objects.filter(**days_between("created_at", start, end))   # ikkala chet ham kiradi
"""

from __future__ import annotations

import datetime

from django.utils import timezone


def day_start(day: datetime.date) -> datetime.datetime:
    """Mahalliy (TIME_ZONE) kun boshlanishi — aware datetime."""
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))


def on_day(field: str, day: datetime.date) -> dict:
    return {f"{field}__gte": day_start(day),
            f"{field}__lt": day_start(day + datetime.timedelta(days=1))}


def since_day(field: str, day: datetime.date) -> dict:
    return {f"{field}__gte": day_start(day)}


def days_between(field: str, start: datetime.date, end: datetime.date) -> dict:
    return {f"{field}__gte": day_start(start),
            f"{field}__lt": day_start(end + datetime.timedelta(days=1))}
