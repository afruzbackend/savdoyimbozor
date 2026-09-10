"""Kunlik statistikani hisoblab, signallarni yaratadi.

Foydalanish:
    python manage.py recompute            # bugun uchun
    python manage.py recompute --date 2026-09-10

Production'da buni har kuni kechqurun cron yoki Celery beat orqali chaqiramiz.
"""
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.services import compute_all_daily_stats, generate_alerts


class Command(BaseCommand):
    help = "Kunlik statistika va signallarni qayta hisoblaydi."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD")

    def handle(self, *args, **opts):
        if opts["date"]:
            day = datetime.strptime(opts["date"], "%Y-%m-%d").date()
        else:
            day = timezone.localdate()
        self.stdout.write(f"Hisoblanmoqda: {day}")
        compute_all_daily_stats(day)
        alerts = generate_alerts(day)
        self.stdout.write(self.style.SUCCESS(
            f"Tayyor. {len(alerts)} ta yangi signal yaratildi."))
