"""Jarima darajalari (huquqiy tasnif) — yashirilgan savdo miqdoriga qarab.

Chegaralar taxminiy (so'mda), demo/pilot uchun. Yakuniy tasnif va jarima
amaldagi qonunchilik asosida vakolatli organ tomonidan belgilanadi.
Takroriy huquqbuzarlik — jarima 2 baravar.
"""

from __future__ import annotations

# (quyi_chegara, yuqori_chegara_yoki_None, kod, yorliq, jinoiy_mi)
TIERS = [
    (0, 6_600_000, "warning", "Ogohlantirish darajasi (kichik)", False),
    (6_600_000, 13_200_000, "small", "Kam miqdordagi", False),
    (13_200_000, 44_000_000, "medium", "Ancha miqdordagi", False),
    (44_000_000, 132_000_000, "crime", "Jinoyat darajasidagi", True),
    (132_000_000, None, "grave", "Juda katta (og'ir jinoyat)", True),
]


# Jarima darajalari: (kod, yorliq, qachon qo'llanadi). Summalar — SystemSettings.fine_<kod>.
FINE_LEVELS = [
    ("small", "Kichik", "Birinchi marta: savdo kassasiz / cheksiz, yashirilgan summa kichik"),
    ("medium", "O'rta", "Bir yil ichida takroran"),
    ("high", "Yuqori", "Ko'p marta takroriy yoki jinoyat miqyosidagi yashirish"),
]


def level_amounts(cfg) -> dict:
    return {"small": cfg.fine_small, "medium": cfg.fine_medium, "high": cfg.fine_high}


def suggest_level(hidden: int, prior_confirmed: int) -> str:
    """Tavsiya etilgan daraja. prior_confirmed — oxirgi 365 kunda tasdiqlangan tekshiruvlar soni
    (Soliq kodeksi: "bir yil davomida takroran"). Tekshiruvchi boshqasini tanlashi mumkin — tanlov
    auditda qoladi."""
    if prior_confirmed >= 2 or classify_hidden(hidden)["is_criminal"]:
        return "high"
    if prior_confirmed == 1:
        return "medium"
    return "small"


def shop_fine_hints(shops, today) -> dict:
    """Har do'kon uchun: 30 kunlik yashirilgan savdo, yil ichidagi tasdiqlangan tekshiruvlar va
    tavsiya etilgan daraja. Ikki agregat so'rov (do'konlar ko'p bo'lsa ham N+1 yo'q)."""
    from datetime import timedelta

    from django.db.models import Count, Sum

    from .models import DailyScore, Inspection

    hidden = dict(
        DailyScore.objects.filter(shop__in=shops, date__gte=today - timedelta(days=29))
        .values_list("shop_id").annotate(h=Sum("hidden_sales")).values_list("shop_id", "h")
    )
    prior = dict(
        Inspection.objects.filter(shop__in=shops, result=Inspection.Result.CONFIRMED,
                                  created_at__date__gte=today - timedelta(days=365))
        .values_list("shop_id").annotate(n=Count("id")).values_list("shop_id", "n")
    )
    ids = set(hidden) | set(prior)
    return {
        sid: {"hidden": int(hidden.get(sid) or 0), "prior": prior.get(sid, 0),
              "level": suggest_level(int(hidden.get(sid) or 0), prior.get(sid, 0))}
        for sid in ids
    }


def classify_hidden(amount: int, repeat: bool = False) -> dict:
    """Yashirilgan savdo (so'm) bo'yicha huquqiy tasnif.

    repeat=True bo'lsa (takroriy) daraja bir pog'ona yuqoriga ko'tariladi (2 baravar).
    Qaytadi: {code, label, is_criminal, warning_only, repeat, range_text}.
    """
    amount = max(0, int(amount or 0))
    idx = 0
    for i, (lo, hi, *_rest) in enumerate(TIERS):
        if amount >= lo and (hi is None or amount < hi):
            idx = i
            break
    if repeat and idx < len(TIERS) - 1:
        idx += 1  # takroriy — bir pog'ona yuqori
    lo, hi, code, label, is_crime = TIERS[idx]
    from apps.core.format import som

    range_text = (
        f"{som(lo)} so'mdan yuqori" if hi is None else f"{som(lo)}–{som(hi)} so'm"
    ) if lo else f"{som(hi)} so'mgacha"
    return {
        "code": code,
        "label": label + (" (takroriy)" if repeat else ""),
        "is_criminal": is_crime,
        "warning_only": code == "warning" and not repeat,
        "repeat": repeat,
        "range_text": range_text,
    }
