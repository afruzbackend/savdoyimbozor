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
