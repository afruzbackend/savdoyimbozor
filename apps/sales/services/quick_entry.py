"""Tez kirim: erkin o'zbekcha matn (ovozdan yoki yozilgan) → kirim qatorlari.

    "pomidor o'n besh kilo sakkiz mingdan, kartoshka 2 qop"
    "15 kg olma narxi 12 000; banan 20 kilo 18 ming"
→   [{name: Pomidor, qty: 15, unit: kg, price: 8000}, {name: Kartoshka, qty: 2, packs}, ...]

Server tomonda BITTA manba: son-so'zlar, birliklar, narx belgilari, mahsulotni do'kon
katalogidan topish. Natija faqat TAKLIF — sotuvchi jadvalda tasdiqlaydi/tuzatadi.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation

APOSTROPHES = str.maketrans({"ʻ": "'", "’": "'", "‘": "'", "`": "'", "´": "'", "ʼ": "'"})

ONES = {"bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "tort": 4, "besh": 5, "olti": 6, "yetti": 7,
        "sakkiz": 8, "to'qqiz": 9, "toqqiz": 9, "nol": 0}
TENS = {"o'n": 10, "on": 10, "yigirma": 20, "o'ttiz": 30, "ottiz": 30, "qirq": 40, "ellik": 50,
        "oltmish": 60, "yetmish": 70, "sakson": 80, "to'qson": 90, "toqson": 90}
SCALES = {"ming": 1000, "million": 1_000_000, "mln": 1_000_000, "milliard": 1_000_000_000}

# birlik so'zi → catalog.Unit qiymati ("g" — kg ga o'giriladi)
UNITS = {
    "kilo": "kg", "kg": "kg", "kilogramm": "kg", "kilogram": "kg",
    "gramm": "g", "gr": "g",
    "dona": "dona", "ta": "dona", "shtuk": "dona",
    "litr": "litr", "l": "litr",
    "metr": "metr", "m": "metr",
    "qop": "qop", "meshok": "qop",
    "quti": "quti", "yashik": "quti", "karobka": "quti", "pachka": "quti", "blok": "quti",
    "qadoq": "quti",
    "bog'lam": "bog'lam", "bog'": "bog'lam", "boglam": "bog'lam",
}
PACK_UNITS = {"qop", "quti"}
PRICE_WORDS = {"narxi", "narx", "narxda", "narxi:", "baho", "bahosi"}
CURRENCY = {"so'm", "som", "sum", "so'mdan", "somdan", "so'mga", "somga"}
STOP = {"keldi", "oldim", "olindi", "tushdi", "kirim", "va", "yana", "hammasi", "jami",
        "dan", "ga", "lik", "har", "biri", "bittasi", "donasi", "kilosi"}
SUFFIXES = ("tadan", "dan", "ga", "lik", "ta", "si")

SPLIT_RE = re.compile(r"[\n;]+|\.(?!\d)|,\s+|\s+(?:va|keyin|yana)\s+")
TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?[a-z']*|[a-z']+")


@dataclass
class Row:
    raw: str
    name: str = ""
    product_id: int | None = None
    product_name: str = ""
    is_new: bool = False
    qty: str = ""  # Decimal matn ko'rinishida (JSON uchun)
    unit: str = ""
    in_packs: bool = False
    price: int | None = None
    error: str = ""


def _norm(text: str) -> str:
    return (text or "").translate(APOSTROPHES).lower()


def _strip_suffix(word: str) -> tuple[str, str]:
    for suf in SUFFIXES:
        if len(word) > len(suf) + 1 and word.endswith(suf):
            base = word[: -len(suf)]
            if base in ONES or base in TENS or base in SCALES or base in UNITS \
                    or base in CURRENCY or base == "yarim":
                return base, suf
    return word, ""


def _classify(tokens):
    """Tokenlar → [("num", Decimal, price_hint) | ("unit", (unit, packs)) | ("price",) | ("word", w)]."""
    items = []
    words_acc = None  # yig'ilayotgan son-so'z: [total, current]

    def flush():
        nonlocal words_acc
        if words_acc is not None:
            total, current = words_acc
            items.append(["num", Decimal(str(total + current)), False])
            words_acc = None

    for tok in tokens:
        m = re.fullmatch(r"(\d+(?:[.,]\d+)?)([a-z']*)", tok)
        if m:
            flush()
            try:
                val = Decimal(m.group(1).replace(",", "."))
            except InvalidOperation:
                continue
            # "8 000" — ming ajratgichli yozuv: oldingi 1–3 xonali songa 3 xonali qo'shiladi
            if (items and items[-1][0] == "num" and len(m.group(1)) == 3 and m.group(1).isdigit()
                    and items[-1][1] == items[-1][1].to_integral() and items[-1][1] < 1000
                    and items[-1][3:4] == ["digits"]):
                items[-1][1] = items[-1][1] * 1000 + val
                continue
            items.append(["num", val, False, "digits"])
            suf = m.group(2)
            if suf:
                base, s2 = _strip_suffix(suf)
                if base in UNITS:
                    items.append(["unit", UNITS[base]])  # "15kg"
                elif base in SCALES:
                    items[-1][1] *= SCALES[base]
                if suf in ("dan", "ga") or s2 in ("dan", "ga") or base in CURRENCY:
                    items[-1][2] = True
            continue
        word, suf = _strip_suffix(tok)
        if word in ONES or word in TENS:
            if words_acc is None:
                words_acc = [0, 0]
            words_acc[1] += ONES.get(word, 0) + TENS.get(word, 0)
        elif word == "yuz":
            if words_acc is None:
                words_acc = [0, 0]
            words_acc[1] = (words_acc[1] or 1) * 100
        elif word == "yarim":
            if words_acc is None and items and items[-1][0] == "num":
                items[-1][1] += Decimal("0.5")  # "2 yarim"
            else:
                if words_acc is None:
                    words_acc = [0, 0]
                words_acc[1] += 0.5
        elif word in SCALES:
            if words_acc is None and items and items[-1][0] == "num" and items[-1][3:4] == ["digits"]:
                items[-1][1] *= SCALES[word]  # "8 ming"
            else:
                if words_acc is None:
                    words_acc = [0, 0]
                words_acc[0] += (words_acc[1] or 1) * SCALES[word]
                words_acc[1] = 0
        else:
            flush()
            if word in UNITS and items and items[-1][0] == "num":
                items.append(["unit", UNITS[word]])
            elif word in PRICE_WORDS:
                items.append(["price"])
            elif word in CURRENCY:
                if items and items[-1][0] == "num":
                    items[-1][2] = True
            else:
                items.append(["word", tok])
            if suf in ("dan", "ga") and items and items[-1][0] == "num":
                items[-1][2] = True
            continue
        if suf in ("dan", "ga"):
            flush()
            items[-1][2] = True
    flush()
    return items


def parse_segment(text: str) -> dict:
    """Bitta bo'lak → {name, qty, unit, in_packs, price}."""
    items = _classify(TOKEN_RE.findall(_norm(text)))
    nums = []  # (index, value, followed_by_unit, price_hint)
    unit = ""
    name_words = []
    for i, it in enumerate(items):
        if it[0] == "num":
            nxt = items[i + 1] if i + 1 < len(items) else None
            prev = items[i - 1] if i else None
            has_unit = bool(nxt and nxt[0] == "unit")
            price_hint = it[2] or bool(prev and prev[0] == "price")
            nums.append((i, it[1], has_unit, price_hint))
            if has_unit and not unit:
                unit = nxt[1]
        elif it[0] == "word" and it[1] not in STOP:
            name_words.append(it[1])
    qty = price = None
    for _i, v, has_unit, hint in nums:
        if has_unit and qty is None and not hint:
            qty = v
    for _i, v, _u, hint in nums:
        if hint and price is None:
            price = v
    rest = [v for _i, v, _u, _h in nums if v is not qty and v is not price]
    if qty is None and rest:
        qty = rest.pop(0)
    if price is None and rest:
        price = rest.pop(0)
    if unit == "g" and qty is not None:  # "500 gramm" → 0.5 kg
        qty, unit = qty / 1000, "kg"
    return {"name": " ".join(name_words), "qty": qty, "unit": unit,
            "price": int(price) if price is not None else None}


def _match_product(name: str, products):
    """Do'kon katalogidan eng yaqin mahsulot (yoki None)."""
    if not name:
        return None
    by_name = {_norm(p.name): p for p in products}
    if name in by_name:
        return by_name[name]
    for key, p in by_name.items():  # "pomidor" ↔ "Pomidor (qizil)"
        if name == key.split(" (")[0] or key.startswith(name + " ") or name.startswith(key + " "):
            return p
    close = difflib.get_close_matches(name, list(by_name), n=1, cutoff=0.75)
    if close:
        return by_name[close[0]]
    first = name.split()[0]
    close = difflib.get_close_matches(first, [k.split()[0] for k in by_name], n=1, cutoff=0.8)
    if close:
        return next(p for k, p in by_name.items() if k.split()[0] == close[0])
    return None


def parse(text: str, products) -> list[dict]:
    """Matn → kirim qatorlari (taklif). products — do'konning faol mahsulotlari."""
    products = list(products)
    rows = []
    for seg in SPLIT_RE.split(_norm(text)):
        seg = (seg or "").strip(" ,.-")
        if not seg or not TOKEN_RE.search(seg):
            continue
        data = parse_segment(seg)
        row = Row(raw=seg[:120], name=data["name"][:120], unit=data["unit"], price=data["price"])
        if data["qty"] is None or data["qty"] <= 0:
            row.error = "miqdor topilmadi"
        else:
            row.qty = format(data["qty"].normalize(), "f")
        p = _match_product(row.name, products)
        if p is not None:
            row.product_id, row.product_name = p.pk, p.name
            # "2 qop" kg'lik mahsulotga — qadoqda (miqdor × qadoq koeffitsienti)
            if row.unit in PACK_UNITS and p.unit not in PACK_UNITS and (p.pack_coeff or 1) > 1:
                row.in_packs = True
            row.unit = p.unit
            if row.price is None:
                row.price = p.buy_price or None
        elif row.name:
            row.is_new = True
            row.product_name = row.name[:1].upper() + row.name[1:]
            row.unit = row.unit or "dona"
        else:
            row.error = row.error or "mahsulot nomi topilmadi"
        rows.append(asdict(row))
    return rows
