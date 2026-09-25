"""Nasiya eslatmalari va qaytarish sanasi — BITTA MANBA (sahifa, API, kechki buyruq)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.utils import timezone

from apps.core.format import som
from apps.core.models import Notification, notify

from ..models import Debt


def parse_due(raw) -> date | None:
    """"2026-10-01" / "01.10.2026" → date. Noto'g'ri yoki bo'sh → None."""
    raw = str(raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def debt_reminders(user, shop) -> int:
    """Sotuvchiga nasiya eslatmalari. Qaytadi: yangi yaratilgan eslatmalar soni.

    - qaytarish sanasidan 1 KUN OLDIN: "Ertaga qaytarish kuni"
    - o'sha KUNI: "Bugun qaytarish kuni"
    - muddati o'tgan: "Muddati o'tdi" (bir marta)
    Har bosqich idempotent (key) — takrorlanmaydi.
    """
    if shop is None or user is None:
        return 0
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    created = 0
    qs = Debt.objects.filter(shop=shop, is_paid=False, due_date__isnull=False,
                             due_date__lte=tomorrow)
    for d in qs:
        who = d.customer_name or "xaridor"
        left = f"{som(d.remaining)} so'm"
        if d.due_date == tomorrow:
            stage, title, body = "before", f"Ertaga nasiya qaytarish kuni: {who}", \
                f"{left} — {d.due_date:%d.%m.%Y}"
        elif d.due_date == today:
            stage, title, body = "today", f"Bugun nasiya qaytarish kuni: {who}", \
                f"{left} — bugun olinishi kerak"
        else:
            stage, title, body = "overdue", f"Nasiya muddati o'tdi: {who}", \
                f"{left} — {d.due_date:%d.%m.%Y} edi"
        before = Notification.objects.filter(user=user).count()
        notify(
            user,
            Notification.Kind.DEBT_DUE,
            title,
            body=body + (f" · {d.customer_phone}" if d.customer_phone else ""),
            url="/nasiya/",
            key=f"debt:{d.id}:{d.due_date}:{stage}",
        )
        created += Notification.objects.filter(user=user).count() - before
    return created


OVERDUE_SMS_AFTER = 3  # muddat o'tgach necha kundan keyin bitta eslatma


def _sms_text(d, stage) -> str:
    """Lotin, ~160 belgi (bitta SMS). Faqat kerakli: kimdan, qancha, qachon."""
    who = (d.customer_name or "").split()[0][:20] if d.customer_name else ""
    shop = f"{d.shop.market.name} {d.shop.number}-do'kon"[:40]
    left = som(d.remaining)
    when = {
        "before": f"qaytarish kuni ertaga, {d.due_date:%d.%m}",
        "today": "qaytarish kuni bugun",
        "overdue": f"muddati {d.due_date:%d.%m} da o'tgan",
    }[stage]
    hello = f"Hurmatli {who}! " if who else ""
    return f"{hello}{shop}: nasiya {left} so'm, {when}. Bozor Nazorat"


def buyer_sms_reminders(today=None) -> dict:
    """Xaridorlarga nasiya SMS eslatmasi (har kuni 10:00, Celery). Idempotent (SmsMessage.key).

    Bosqichlar: 1 kun oldin · o'sha kuni · muddat o'tgach 3-kuni (bir marta).
    """
    from apps.core import sms

    stats = {"sent": 0, "failed": 0, "invalid": 0}
    if not sms.enabled():
        return stats
    today = today or timezone.localdate()
    stages = {
        today + timedelta(days=1): "before",
        today: "today",
        today - timedelta(days=OVERDUE_SMS_AFTER): "overdue",
    }
    qs = (Debt.objects.filter(is_paid=False, sms_remind=True, due_date__in=list(stages))
          .exclude(customer_phone="").select_related("shop", "shop__market"))
    for d in qs:
        if d.remaining <= 0:
            continue
        stage = stages[d.due_date]
        msg = sms.send(f"debt:{d.id}:{d.due_date}:{stage}", d.customer_phone, _sms_text(d, stage),
                       shop=d.shop)
        if msg is not None:
            stats[msg.status] = stats.get(msg.status, 0) + 1
    return stats
