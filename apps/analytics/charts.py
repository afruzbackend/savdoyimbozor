"""Grafik ma'lumoti — barcha diagrammalar uchun bitta qoida."""

from __future__ import annotations

from datetime import date, timedelta


def day_series(rows: dict, start: date, end: date, keys=("entered", "cash", "truth")) -> dict:
    """{sana: {entered, cash, truth}} → grafik uchun KUNMA-KUN qator.

    Hisoblanmagan kun o'qdan tushib qolmaydi (ilgari 21.09 dan keyin to'g'ridan 23.09 kelardi —
    sanalar "tartibsiz" ko'rinardi): u kun bo'sh (null) turadi, grafikda uzilish bo'ladi.
    """
    out = {"labels": [], **{k: [] for k in keys}}
    if end < start:
        return out
    d = start
    while d <= end:
        r = rows.get(d)
        out["labels"].append(d.strftime("%d.%m"))
        for k in keys:
            out[k].append(r.get(k) if r else None)
        d += timedelta(days=1)
    return out
