"""Razmer (variant) tartibi — BITTA manba: sotuvchi ro'yxatlari, kirim jadvali, inspektor
ma'lumotnomasi va favqulodda holat muhri bir xil tartibda ko'rsatadi."""

_LETTER_ORDER = {s: i for i, s in enumerate(["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL", "5XL"])}
_LETTER_ORDER["2XL"] = _LETTER_ORDER["XXL"]
_LETTER_ORDER["XXXL"] = _LETTER_ORDER["3XL"]


def size_key(s):
    """XS < S < M ... ; raqamlar son bo'yicha (36 < 37 < 110); qolgani matn bo'yicha."""
    s = str(s or "")
    if s.upper() in _LETTER_ORDER:
        return (0, _LETTER_ORDER[s.upper()], "")
    try:
        return (1, float(s.replace(",", ".")), "")
    except ValueError:
        return (2, 0, s)


def product_order(p):
    """Model nomi → razmer → rang. Nom bo'yicha alifbo "Futbolka — L, M, S, XL, XS" berardi."""
    base = (p.base_name or p.name.split(" — ")[0]).lower()
    return (base, size_key(p.size) if p.size else (-1, 0, ""), (p.color or "").lower(), p.name.lower())


def sorted_products(items):
    return sorted(items, key=product_order)
