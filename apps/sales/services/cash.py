"""Kassa va nasiya xizmati — kutilgan naqd BITTA MANBADA hisoblanadi.

Kutilgan naqd = ertalabki maydalik + naqd sotuv + shu kuni nasiyadan qaytgan naqd.
Ilgari faqat naqd sotuv olinardi: sandiqdagi maydalik va qaytgan nasiya puli
"ortiqcha" bo'lib, sotuvchiga noto'g'ri "yozilmagan savdo" signali chiqardi.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.core.format import som

from ..models import CashOpen, Debt, DebtPayment, PaymentType, RegisterClose, Sale


class CashError(Exception):
    """Foydalanuvchiga ko'rsatiladigan kassa/nasiya xatosi."""


def register_totals(shop, day) -> dict:
    agg = {
        r["payment_type"]: r
        for r in Sale.objects.filter(shop=shop, created_at__date=day)
        .values("payment_type")
        .annotate(s=Sum("total"), n=Count("id"))
    }

    def part(k):
        return agg.get(k, {}).get("s") or 0

    cash, card, transfer, debt = part("cash"), part("card"), part("transfer"), part("debt")
    count = sum((r.get("n") or 0) for r in agg.values())
    total = cash + card + transfer + debt
    opening = (
        CashOpen.objects.filter(shop=shop, date=day).values_list("amount", flat=True).first() or 0
    )
    debt_in = (
        DebtPayment.objects.filter(
            shop=shop, created_at__date=day, method=PaymentType.CASH
        ).aggregate(s=Sum("amount"))["s"]
        or 0
    )
    return {
        "cash": cash,
        "card": card,
        "transfer": transfer,
        "debt": debt,
        "total": total,
        "count": count,
        "avg": int(total / count) if count else 0,
        "opening": opening,
        "debt_in_cash": debt_in,
        "expected_cash": opening + cash + debt_in,
    }


def can_set_opening(shop, day) -> bool:
    """Maydalik faqat kunning birinchi sotuvidan OLDIN kiritiladi."""
    return not Sale.objects.filter(shop=shop, created_at__date=day).exists()


def set_opening(shop, day, amount, seller) -> CashOpen:
    if amount is None or amount < 0:
        raise CashError("Maydalik summasini kiriting (bo'lmasa 0).")
    if not can_set_opening(shop, day):
        raise CashError(
            "Bugun sotuv boshlangan — maydalikni endi o'zgartirib bo'lmaydi. "
            "Kerak bo'lsa kassa yopishda izohga yozing."
        )
    obj, _ = CashOpen.objects.update_or_create(
        shop=shop, date=day, defaults={"amount": amount, "seller": seller}
    )
    return obj


def close_register(shop, day, counted, seller, note="") -> tuple[RegisterClose, int]:
    """Kassani yopadi (Z-hisobot). Qaytadi: (yozuv, farq = sanalgan − kutilgan)."""
    if counted is None or counted < 0:
        raise CashError("Sandiqdagi sanalgan naqdni kiriting (0 bo'lsa 0 yozing).")

    t = register_totals(shop, day)
    note = (note or "").strip()[:200]
    prev = RegisterClose.objects.filter(shop=shop, date=day).first()
    if prev and prev.counted_cash != counted:
        # Qayta yopish — oldingi sanoq izsiz yo'qolmasin (inspektor ko'radi)
        note = (f"Qayta yopildi (avval {som(prev.counted_cash)}). " + note)[:200]
    elif prev and not note:
        note = prev.note
    obj, _ = RegisterClose.objects.update_or_create(
        shop=shop,
        date=day,
        defaults={
            "seller": seller,
            "expected_cash": t["expected_cash"],
            "opening_cash": t["opening"],
            "debt_cash_in": t["debt_in_cash"],
            "counted_cash": counted,
            "card_total": t["card"],
            "transfer_total": t["transfer"],
            "checks_count": t["count"],
            "note": note,
        },
    )
    return obj, counted - t["expected_cash"]


@transaction.atomic
def pay_debt(debt: Debt, amount, method, seller) -> DebtPayment:
    """Nasiya to'lovi (qisman ham). Qoldiqdan ko'p to'lab bo'lmaydi."""
    debt = Debt.objects.select_for_update().get(pk=debt.pk)
    if debt.is_paid:
        raise CashError("Bu nasiya allaqachon to'langan.")
    if method not in (PaymentType.CASH, PaymentType.CARD, PaymentType.TRANSFER):
        raise CashError("To'lov turini tanlang.")
    remaining = debt.remaining
    if amount is None or amount <= 0:
        raise CashError("To'lov summasi 0 dan katta bo'lsin.")
    if amount > remaining:
        raise CashError(f"Qoldiq {som(remaining)} so'm — undan ko'p to'lab bo'lmaydi.")
    pay = DebtPayment.objects.create(
        debt=debt, shop=debt.shop, seller=seller, amount=amount, method=method
    )
    Debt.objects.filter(pk=debt.pk).update(paid_amount=F("paid_amount") + amount)
    debt.refresh_from_db()
    if debt.remaining == 0:
        debt.is_paid = True
        debt.paid_at = timezone.now()
        debt.save(update_fields=["is_paid", "paid_at"])
    return pay
