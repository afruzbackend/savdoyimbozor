"""Mahsulot turi bo'yicha variantlar — BITTA manba.

Har mahsulot toifasi (ProductCategory.variant_kind) o'ziga mos variantga ega: choyga kiyim
razmeri (3XL) taklif qilinmaydi — qadoq og'irligi (100 g, 250 g); guruchga variant yo'q (kg bilan
sotiladi); poyabzalga 35–46; batareykaga AA/AAA. Yangi mahsulot formasi, server tekshiruvi, tez
kirim tahlilchisi va kirim jadvali shu yerdan o'qiydi.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_LETTERS = ["XS", "S", "M", "L", "XL", "XXL", "3XL"]

# noun — o'lcham bo'limi sarlavhasi ("" — o'lcham yo'q); colors — rang so'raladimi;
# field/hint — "nav" maydoni yorlig'i va misoli (har tur uchun o'ziga mos)
KINDS: dict[str, dict] = {
    "none": {"noun": "", "colors": False, "presets": {},
             "field": "Navi (ixtiyoriy)", "hint": "masalan: mahalliy, 1-nav, katta"},
    "clothing": {"noun": "O'lchamlar", "colors": True,
                 "presets": {"Harfli": _LETTERS, "Raqamli": [str(n) for n in range(42, 62, 2)]},
                 "field": "Model / brend (ixtiyoriy)", "hint": "masalan: klassik, Nike"},
    "shoes": {"noun": "O'lchamlar", "colors": True,
              "presets": {"Kattalar": [str(n) for n in range(35, 47)],
                          "Bolalar": [str(n) for n in range(20, 35)]},
              "field": "Model / brend (ixtiyoriy)", "hint": "masalan: krossovka, charm tufli"},
    "kids": {"noun": "Bo'yi (sm)", "colors": True,
             "presets": {"Bo'y, sm": [str(n) for n in range(80, 170, 6)]},
             "field": "Model (ixtiyoriy)", "hint": "masalan: maktab formasi"},
    "headwear": {"noun": "O'lchamlar", "colors": True,
                 "presets": {"Bosh aylanasi": [str(n) for n in range(52, 63)]},
                 "field": "Turi (ixtiyoriy)", "hint": "masalan: do'ppi, kepka, qishki"},
    "socks": {"noun": "O'lchamlar", "colors": True,
              "presets": {"Oyoq": ["35-37", "38-40", "41-43", "44-46"]},
              "field": "Turi (ixtiyoriy)", "hint": "masalan: paxta, sport"},
    "pack_weight": {"noun": "Qadoq og'irligi", "colors": False,
                    "presets": {"Og'irlik": ["50 g", "100 g", "250 g", "500 g", "1 kg"]},
                    "field": "Brendi / navi (ixtiyoriy)", "hint": "masalan: ko'k choy, Ahmad"},
    "pack_volume": {"noun": "Qadoq hajmi", "colors": False,
                    "presets": {"Hajm": ["250 ml", "500 ml", "1 L", "1,5 L", "5 L"]},
                    "field": "Brendi / navi (ixtiyoriy)", "hint": "masalan: paxta yog'i, Oila"},
    "type": {"noun": "Turlari", "colors": True, "presets": {},
             "field": "Brendi (ixtiyoriy)", "hint": "masalan: Duracell, Samsung"},
    "color": {"noun": "", "colors": True, "presets": {},
              "field": "Navi (ixtiyoriy)", "hint": "masalan: gollandiya, mahalliy"},
}
SIZED = {"clothing", "shoes", "kids", "headwear", "socks"}
PACKS = {"pack_weight", "pack_volume"}

# Toifa nomidan taxmin (yangi toifa va mavjudlari uchun migratsiyada; admin panelda o'zgartiradi)
_GUESS = [
    ("kids", r"bolalar|chaqaloq"),
    ("shoes", r"poyabzal|krossovka|tufli|etik|botinka|shippak|sandal|oyoq kiyim"),
    ("socks", r"paypoq|kolgotka"),
    ("headwear", r"bosh kiyim|do'ppi|kepka|shapka|qalpoq"),
    ("clothing", r"kurtka|ko'ylak|koylak|futbolka|shim|jinsi|palto|kostyum|libos|sviter|xalat|"
                 r"yubka|mayka|kofta|pijama|kiyim"),
    ("pack_weight", r"choy|qahva|kofe|kir yuvish|kukun|ziravor|sovun"),
    ("pack_volume", r"yog'|shampun|idish yuvish|sharbat|ichimlik|\batir\b|parfyum|suv\b"),
    ("type", r"batareyka|kabel|zaryad|lampochka|quloqchin|telefon|chiroq"),
    ("color", r"gul|atirgul|lola|mato|ip\b"),
]
# Toifaga xos tayyor qiymatlar (turning umumiy ro'yxati o'rniga): choy 1 kg dan katta bo'lmaydi
_OPTIONS = {
    "choy": "100 g, 250 g, 500 g, 1 kg",
    "yog'": "0,5 L, 1 L, 3 L, 5 L",
    "shampun": "250 ml, 400 ml, 1 L",
    "idish yuvish": "500 ml, 1 L, 5 L",
    "kir yuvish kukuni": "400 g, 1 kg, 3 kg, 9 kg",
    "sovun": "90 g, 150 g, 200 g",
    "batareyka": "AA, AAA, C, D, 9V",
    "usb kabel": "Type-C, Lightning, Micro-USB",
    "zaryadlagich": "Type-C, USB, Simsiz",
    "lampochka": "5 W, 9 W, 12 W, 15 W",
    "quloqchin": "Simli, Simsiz",
}


def guess(name: str, shop_category: str = "") -> tuple[str, str]:
    """(variant_kind, variant_options) — toifa nomi va savdo turidan."""
    n = (name or "").lower().replace("ʻ", "'").replace("’", "'")
    kind = next((k for k, rx in _GUESS if re.search(rx, n)), None)
    shop_category = (shop_category or "").lower()
    if kind is None and "kiyim" in shop_category:
        kind = "clothing"
    elif kind is None and "gul" in shop_category:
        kind = "color"
    return kind or "none", _OPTIONS.get(n, "")


def kind_of(category) -> str:
    kind = getattr(category, "variant_kind", "") or "none"
    return kind if kind in KINDS else "none"


# Ro'yxat ajratgichi: ";" yoki vergul — lekin raqamlar orasidagi vergul o'nlik belgi ("0,5 L")
_LIST_SEP = re.compile(r";|,(?=\s)|(?<!\d),|,(?!\d)")


def split_list(raw) -> list[str]:
    """"0,5 L, 1 L; 5 L" → ["0,5 L", "1 L", "5 L"]; "50g,100g" → ["50g", "100g"]."""
    return [x.strip() for x in _LIST_SEP.split(str(raw or "")) if x.strip()]


def options_of(category) -> list[str]:
    kind = kind_of(category)
    return [normalize(x, kind) for x in split_list(getattr(category, "variant_options", ""))]


def spec(category) -> dict:
    """Frontend uchun: tur, o'lcham bo'limi sarlavhasi, tayyor qiymatlar, rang so'raladimi."""
    kind = kind_of(category)
    k = KINDS[kind]
    own = options_of(category)
    presets = {"Tayyor": own} if own else k["presets"]
    return {"kind": kind, "noun": k["noun"] if (presets or kind == "type") else "",
            "colors": k["colors"], "presets": presets, "field": k["field"], "hint": k["hint"],
            "pack": kind in PACKS}


_MEASURE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(g|gr|gramm|kg|kilo|ml|l|litr|w)\s*$", re.I)
_UNIT_CANON = {"g": "g", "gr": "g", "gramm": "g", "kg": "kg", "kilo": "kg", "ml": "ml",
               "l": "L", "litr": "L", "w": "W"}


def measure(text):
    """"250 g" → ("g", 250); "1 kg" → ("g", 1000); "0,5 L" → ("ml", 500). Aks holda None."""
    m = _MEASURE.match(str(text or ""))
    if not m:
        return None
    try:
        val = Decimal(m.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    unit = _UNIT_CANON[m.group(2).lower()]
    if unit == "kg":
        return ("g", val * 1000)
    if unit == "L":
        return ("ml", val * 1000)
    return (unit, val)


def _num(val: Decimal) -> str:
    return (str(int(val)) if val == val.to_integral() else format(val.normalize(), "f")).replace(".", ",")


def normalize(label, kind: str = "") -> str:
    """Bir xil yozuv: "xl"→"XL", "250G"→"250 g", "0.5l"→"0,5 L"; qadoq turida belgisiz son
    ham o'lchovga aylanadi: choy "250" → "250 g", "1" → "1 kg"; yog' "5" → "5 L"."""
    label = " ".join(str(label or "").split())[:20]
    m = _MEASURE.match(label)
    if m:
        return f"{m.group(1).replace('.', ',')} {_UNIT_CANON[m.group(2).lower()]}"
    if kind in PACKS and re.fullmatch(r"\d+(?:[.,]\d+)?", label):
        val = Decimal(label.replace(",", "."))
        small, big = ("g", "kg") if kind == "pack_weight" else ("ml", "L")
        return f"{_num(val)} {big if val < 20 else small}"
    if re.fullmatch(r"\d?x{0,3}[sml]|x{1,3}s|\d+xl", label, re.I):  # harfli razmer
        return label.upper()
    return label


def same(a, b) -> bool:
    """Bir variantmi: "250 g" = "250g" = "0,25 kg"; "xl" = "XL"."""
    ma, mb = measure(a), measure(b)
    if ma and mb:
        return ma == mb
    return normalize(a).upper() == normalize(b).upper()


_SIZE_LIKE = re.compile(r"\d?x{0,3}[sml]|x{1,3}s|\d+xl|\d{2,3}(?:[.,]5)?|\d{2}-\d{2}", re.I)


def size_class(sizes) -> str:
    """Model variantlari qaysi xil: "pack" (250 g, 1 L), "size" (M, 36, 35-37) yoki "type" (AA)."""
    sizes = [s for s in sizes if s]
    if sizes and all(measure(s) for s in sizes):
        return "pack"
    if sizes and all(_SIZE_LIKE.fullmatch(str(s).strip()) for s in sizes):
        return "size"
    return "type"


# "razmerini tanlang" / "qadog'ini tanlang"; bo'lim sarlavhalari
ASK = {"size": "razmerini", "pack": "qadog'ini", "type": "turini"}
TITLE = {"size": "Razmerlar", "pack": "Qadoqlar", "type": "Turlar"}


def section_title(classes) -> str:
    classes = set(classes)
    return TITLE[classes.pop()] if len(classes) == 1 else "Variantlar"
