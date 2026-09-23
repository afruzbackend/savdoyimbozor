"""Kunlik eslatma: sotuvchilarga kun yakuni + kassa yopishni eslatadi.

Kechqurun (masalan 20:00–21:00) ishga tushiriladi:
  python manage.py close_reminders
Windows Task Scheduler / cron / Celery beat orqali rejalashtiriladi.
Bir kunda bir marta (idempotent `key`). Bugun kassani yopgan sotuvchiga yuborilmaydi.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.core.models import Notification, notify
from apps.sales.models import RegisterClose


class Command(BaseCommand):
    help = "Sotuvchilarga kun yakuni/kassa yopishni eslatuvchi bildirishnoma yuboradi."

    def handle(self, *args, **opts):
        today = timezone.localdate()
        closed_shop_ids = set(
            RegisterClose.objects.filter(date=today).values_list("shop_id", flat=True)
        )
        sellers = User.objects.filter(role=Role.SELLER, is_active=True, shop__isnull=False)
        sent = 0
        for u in sellers:
            if u.shop_id in closed_shop_ids:
                continue  # bugun allaqachon yopgan
            notify(
                u,
                Notification.Kind.INFO,
                "Kun yakunini yoping",
                body="Mahsulotlarni sanang va kassani yoping — bugungi hisobni yakunlang.",
                url="/kun-yakuni/",
                key=f"close-reminder-{today}",  # kuniga bir marta
            )
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"{sent} ta eslatma yuborildi ({today})"))
