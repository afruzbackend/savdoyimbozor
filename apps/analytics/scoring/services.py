"""
Rostlik darajasi — sof funksiyalar (spec 5-bo'lim formulalari).

Bu yerda faqat hisoblash mantig'i; ma'lumot yig'ish P3'da `recompute_for_date` ichida.
Funksiyalar sof (I/O yo'q) — test qilish oson va sudda tushuntirish mumkin.
"""
from __future__ import annotations

from typing import Optional


def match(a: float, b: float) -> Optional[float]:
    """Ikki qiymat mosligi (%). Kam ham, ko'p ham yozsa tushadi.

    Biror qiymat 0 yoki noma'lum bo'lsa None (ma'lumot yetarli emas).
    """
    if not a or not b or a <= 0 or b <= 0:
        return None
    return min(a, b) / max(a, b) * 100.0


def price_score(avg_price: float, market_median: float,
                high: float = 0.8, low: float = 0.4) -> Optional[float]:
    """Narx balli: o'rtacha narx / bozor medianasi. ≥high→100, ≤low→0, orada chiziqli."""
    if not avg_price or not market_median or market_median <= 0:
        return None
    ratio = avg_price / market_median
    if ratio >= high:
        return 100.0
    if ratio <= low:
        return 0.0
    return (ratio - low) / (high - low) * 100.0


def weighted_truth(parts: dict[str, Optional[float]], weights: dict[str, float],
                   weakest_cap_bonus: float = 15.0, yellow_threshold: float = 50.0) -> dict:
    """Og'irlikli o'rtacha rostlik.

    - Ma'lumoti yo'q (None) qismlar chiqarib tashlanadi, og'irliklar qayta taqsimlanadi.
    - Eng zaif qism sariq chegaradan past bo'lsa: umumiy ball ≤ (o'sha qism + bonus).
      Sababi: bitta kuchli signal o'rtachada yo'qolib ketmasligi kerak.

    Qaytadi: {"truth": int, "weakest": str|"", "parts": {...}}
    """
    active = {k: v for k, v in parts.items() if v is not None}
    if not active:
        return {"truth": 0, "weakest": "", "parts": parts}

    total_w = sum(weights.get(k, 0) for k in active) or 1.0
    avg = sum(v * weights.get(k, 0) for k, v in active.items()) / total_w

    weakest_key = min(active, key=lambda k: active[k])
    weakest_val = active[weakest_key]

    truth = avg
    if weakest_val < yellow_threshold:
        truth = min(truth, weakest_val + weakest_cap_bonus)

    return {
        "truth": int(round(max(0.0, min(100.0, truth)))),
        "weakest": weakest_key if weakest_val < yellow_threshold else "",
        "parts": {k: (int(round(v)) if v is not None else None) for k, v in parts.items()},
    }


def level_for(truth: int, green: int, yellow: int) -> str:
    """Rang darajasi: ≥green yashil, ≥yellow sariq, aks holda qizil."""
    if truth >= green:
        return "green"
    if truth >= yellow:
        return "yellow"
    return "red"


def recompute_for_date(day) -> int:
    """Berilgan kun uchun barcha do'kon ballarini qayta hisoblaydi (P3'da to'ldiriladi).

    Hozircha skelet — 0 qaytaradi. P3'da: har do'kon uchun kassa/kamera/qoldiq/narx
    qismlarini yig'ib, `weighted_truth` bilan DailyScore yaratadi va signal chiqaradi.
    """
    return 0
