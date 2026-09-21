"""Umumiy formatlash yordamchilari."""

from __future__ import annotations


def som(value) -> str:
    """Pul summasini o'zbekcha — probel ajratgichi bilan: 6 600 000.

    Python `{:,}` vergul beradi (6,600,000), bu esa ilova bo'ylab ishlatiladigan
    probel formatidan farq qiladi. Server matnlarida (signal, xabar, akt) shu
    funksiya ishlatilsin.
    """
    try:
        return f"{int(value or 0):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)
