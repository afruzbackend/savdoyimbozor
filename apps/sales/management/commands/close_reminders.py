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

REMIND_HOUR = 20  # 20:00 dan keyin


def remind_if_due(user) -> bool:
    """Bitta sotuvchi uchun eslatma (Celery beat bo'lmasa ham — sahifa ochilganda).

    20:00 dan keyin, kassa yopilmagan, do'kon dam olish kuni bo'lmasa. Kuniga bir marta.
    """
    now = timezone.localtime()
    shop = getattr(user, "shop", None)
    if now.hour < REMIND_HOUR or shop is None or not shop.is_active:
        return False
    today = now.date()
    if today.weekday() in shop.closed_weekday_list():
        return False
    if RegisterClose.objects.filter(shop=shop, date=today).exists():
        return False
    notify(
        user,
        Notification.Kind.INFO,
        "Kun yakunini yoping",
        body="Mahsulotlarni sanang va kassani yoping — bugungi hisobni yakunlang.",
        url="/kun-yakuni/",
        key=f"close-reminder-{today}",
    )
    return True


class Command(BaseCommand):
    help = "Sotuvchilarga kun yakuni/kassa yopishni eslatuvchi bildirishnoma yuboradi."

    def handle(self, *args, **opts):
        today = timezone.localdate()
        closed_shop_ids = set(
            RegisterClose.objects.filter(date=today).values_list("shop_id", flat=True)
        )
        sellers = User.objects.filter(role=Role.SELLER, is_active=True, shop__isnull=False)
        sent = 0
        for u in sellers.select_related("shop"):
            if u.shop_id in closed_shop_ids:
                continue  # bugun allaqachon yopgan
            if not u.shop.is_active or today.weekday() in u.shop.closed_weekday_list():
                continue  # dam olish kuni / nofaol do'kon
            notify(
                u,
                Notification.Kind.INFO,
                "Kun yakunini yoping",
                body="Mahsulotlarni sanang va kassani yoping — bugungi hisobni yakunlang.",
                url="/kun-yakuni/",
                key=f"close-reminder-{today}",  # kuniga bir marta
            )
            sent += 1
        # Nasiya eslatmalari (1 kun oldin / o'sha kuni / o'tgan) — hamma sotuvchiga
        from apps.sales.services.debts import debt_reminders

        debts = sum(debt_reminders(u, u.shop) for u in sellers.select_related("shop"))
        self.stdout.write(
            self.style.SUCCESS(f"{sent} ta kun yakuni, {debts} ta nasiya eslatmasi ({today})")
        )
