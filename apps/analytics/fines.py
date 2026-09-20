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
    range_text = (
        f"{lo:,} so'mdan yuqori" if hi is None else f"{lo:,}–{hi:,} so'm"
    ) if lo else f"{hi:,} so'mgacha"
    return {
        "code": code,
        "label": label + (" (takroriy)" if repeat else ""),
        "is_criminal": is_crime,
        "warning_only": code == "warning" and not repeat,
        "repeat": repeat,
        "range_text": range_text,
    }
