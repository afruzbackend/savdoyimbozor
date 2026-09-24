"""
Narx / chegirma / yaxlitlash mantig'i — BITTA MANBA.

Server bu qoidani tekshiradi; frontend `frontend_config()` orqali xuddi shu qoidani
ko'rsatadi. Ikki joyda ikki xil bo'lmasligi kerak (spec 5-bo'lim).

Pul = butun son (so'm). Float ishlatilmaydi.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PricedSale:
    subtotal: int
    discount: int
    rounding: int
    total: int


def discount_buttons(subtotal: int, percents: list, cap: int) -> list[int]:
    """O'zbekcha savdolashish tugmalari: chek summasining foizi, yaxlitlangan, cheklangan.

    Har tugma = subtotal × foiz, pastga yaxlitlanadi (katta chekda 1000, kichikda 500 gacha),
    va `cap` (ruxsat etilgan maks chegirma)дан oshmaydi. Shu bois "20 000 chekka 20 000
    chegirma" kabi bema'nilik bo'lmaydi — tugma qancha ko'rsatsa, shuncha qo'llanadi.
    """
    if subtotal <= 0:
        return []
    step = 1000 if subtotal >= 100_000 else 500
    out = []
    for p in percents or [5, 10, 15]:
        amt = (subtotal * int(p) // 100 // step) * step
        amt = min(amt, cap)
        if amt > 0 and amt not in out:
            out.append(amt)
    return out


def max_discount(subtotal: int, items_cost: int | None, no_cost_pct: int) -> int:
    """Ruxsat etilgan eng katta chegirma (so'm).

    - Tannarx ma'lum bo'lsa: chekni tannarxdan past tushirmaydi → maks = subtotal - cost.
    - Tannarx noma'lum bo'lsa: subtotal ning `no_cost_pct` % gacha.
    """
    if items_cost is not None and items_cost > 0:
        return max(0, subtotal - items_cost)
    return subtotal * no_cost_pct // 100


def clamp_discount(subtotal: int, discount: int, items_cost: int | None, no_cost_pct: int) -> int:
    """Chegirmani ruxsat chegarasiga cheklaydi (0 dan past emas, maksdan yuqori emas)."""
    if discount < 0:
        return 0
    cap = max_discount(subtotal, items_cost, no_cost_pct)
    return min(discount, cap)


def apply_rounding(amount: int, rounding: int, rounding_max: int) -> int:
    """Yaxlitlash — FAQAT pastga, `rounding_max` (odatda 1000) gacha.

    Chegirma statistikasiga kirmaydi (alohida maydon). Qaytaradi: qo'llangan yaxlitlash.
    """
    if rounding <= 0:
        return 0
    rounding = min(rounding, rounding_max)
    return min(rounding, amount)  # summani manfiyga tushirmaydi


def price_sale(
    subtotal: int, discount: int, rounding: int, *, items_cost: int | None, settings
) -> PricedSale:
    """To'liq narxlash: chegirma cheklanadi, yaxlitlash qo'llanadi, jami hisoblanadi."""
    subtotal = max(0, int(subtotal))
    d = clamp_discount(subtotal, int(discount), items_cost, settings.max_discount_no_cost_pct)
    after_discount = subtotal - d
    r = apply_rounding(after_discount, int(rounding), settings.rounding_max)
    total = after_discount - r
    return PricedSale(subtotal=subtotal, discount=d, rounding=r, total=total)


def frontend_config(settings) -> dict:
    """Frontend uchun qoidalar (Alpine shu bilan tugma va cheklovlarni ko'rsatadi)."""
    return {
        "discount_percents": settings.discount_percents or [5, 10, 15],
        "max_discount_no_cost_pct": settings.max_discount_no_cost_pct,
        "rounding_max": settings.rounding_max,
    }
