"""Xaridor xabari → signal. Sotuvchi chekka kamroq yozgan bo'lsa, bu yashirilgan savdoning
bevosita dalili (xaridor pulni qo'lida to'lagan)."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.sales.models import ReceiptReport


def _som(n) -> str:
    return f"{int(n):,}".replace(",", " ")


@transaction.atomic
def file_buyer_report(sale, paid_amount: int, comment: str = "") -> ReceiptReport:
    from apps.analytics.models import Alert

    report, created = ReceiptReport.objects.get_or_create(
        sale=sale, defaults={"paid_amount": paid_amount, "comment": (comment or "").strip()[:300]}
    )
    if not created:
        return report
    gap = paid_amount - sale.total
    # Xaridor KO'P to'lagan (sotuvchi kam yozgan) — yashirish belgisi. Arzimas farq (yaxlitlash,
    # 1000 so'mgacha yoki 3%) signal emas. Kam to'lagan bo'lsa — faqat qayd (soliqqa zarar yo'q).
    if gap > max(1000, sale.total * 0.03):
        level = "red" if gap >= max(10_000, sale.total * 0.2) else "yellow"
        inspector = sale.shop.market.duty_inspector()
        alert = Alert.objects.create(
            shop=sale.shop,
            date=timezone.localtime(sale.created_at).date(),
            kind=Alert.Kind.BUYER_REPORT,
            level=level,
            reason=(f"Xaridor chekdan ko'p to'laganini bildirdi: chekda {_som(sale.total)} so'm, "
                    f"to'langan {_som(paid_amount)} so'm (+{_som(gap)})")[:300],
            assigned_to=inspector,
        )
        report.alert = alert
        report.save(update_fields=["alert"])
        if level == "red":
            try:
                from apps.analytics.notifications import notify_alert

                notify_alert(alert)
            except Exception:  # noqa: BLE001 — xabar asosiy oqimni buzmasin
                pass
    return report
