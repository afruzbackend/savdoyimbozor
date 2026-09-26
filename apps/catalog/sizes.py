"""Razmer (variant) tartibi — BITTA manba: sotuvchi ro'yxatlari, kirim jadvali, inspektor
ma'lumotnomasi va favqulodda holat muhri bir xil tartibda ko'rsatadi."""

import re

_LETTER_ORDER = {s: i for i, s in enumerate(["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL"])}
_LETTER_ORDER["2XL"] = _LETTER_ORDER["XXL"]
_LETTER_ORDER["XXXL"] = _LETTER_ORDER["3XL"]


def size_key(s):
    """XS < S < M ... ; raqamlar son bo'yicha (36 < 37 < 110); qadoq o'lchovi bo'yicha
    (250 g < 500 g < 1 kg; 0,5 L < 1 L); qolgani matn bo'yicha."""
    from .variants import measure

    s = str(s or "")
    if s.upper() in _LETTER_ORDER:
        return (0, _LETTER_ORDER[s.upper()], "")
    m = measure(s)
    if m:
        return (1, float(m[1]), m[0])
    try:
        return (1, float(s.replace(",", ".")), "")
    except ValueError:
        pass
    lead = re.match(r"(\d+(?:[.,]\d+)?)", s)  # "35-37" < "38-40"
    if lead:
        return (1, float(lead.group(1).replace(",", ".")), s)
    return (2, 0, s.lower())


def product_order(p):
    """Model nomi → razmer → rang. Nom bo'yicha alifbo "Futbolka — L, M, S, XL, XS" berardi."""
    base = (p.base_name or p.name.split(" — ")[0]).lower()
    return (base, size_key(p.size) if p.size else (-1, 0, ""), (p.color or "").lower(), p.name.lower())


def sorted_products(items):
    return sorted(items, key=product_order)
