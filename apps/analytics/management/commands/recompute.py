"""Kunlik rostlik ballarini va signallarni qayta hisoblaydi.

    python manage.py recompute                 # bugun
    python manage.py recompute --date 2026-09-01
    python manage.py recompute --days 7        # oxirgi 7 kun

Production'da Celery beat buni har 5 daqiqa (bugun) va har kecha (kecha) chaqiradi.
"""

from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.analytics.scoring.services import recompute_for_date


class Command(BaseCommand):
    help = "Rostlik ballari va signallarni qayta hisoblaydi."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default=None, help="YYYY-MM-DD")
        parser.add_argument("--days", type=int, default=1, help="Oxirgi N kun")

    def handle(self, *args, **opts):
        if opts["date"]:
            day = datetime.strptime(opts["date"], "%Y-%m-%d").date()
            days = [day]
        else:
            today = timezone.localdate()
            days = [today - timedelta(days=d) for d in range(opts["days"])]

        total = 0
        for day in days:
            n = recompute_for_date(day)
            total += n
            self.stdout.write(f"  {day}: {n} do'kon hisoblandi")
        self.stdout.write(self.style.SUCCESS(f"Tayyor. {total} yozuv, {len(days)} kun."))
