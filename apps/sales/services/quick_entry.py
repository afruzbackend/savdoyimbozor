"""Tez kirim: erkin o'zbekcha matn (ovozdan yoki yozilgan) → kirim qatorlari.

    "pomidor o'n besh kilo sakkiz mingdan, kartoshka 2 qop"
    "15 kg olma narxi 12 000; banan 20 kilo 18 ming"
    "krossovka 36 razmerlik 10 ta 37 lik 50 ta"   → ikki qator (har razmer — alohida variant)
    "futbolka XL 10 ta, M 100 ta"                 → ikkinchisi ham futbolka (nom davom etadi)
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
# Harfli razmerlar. "m"/"l" raqamdan KEYIN kelsa — birlik (metr/litr), aks holda razmer.
LETTER_SIZES = {"xxs", "xs", "s", "m", "l", "xl", "xxl", "xxxl", "2xl", "3xl", "4xl", "5xl"}
SIZE_MARKERS = {"razmer", "razmeri", "razmerli", "razmerlik", "razmerdagi", "razmerlari", "raz",
                "o'lcham", "o'lchami", "o'lchamli", "o'lchamdagi", "size", "rost"}
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
    size: str = ""  # variant razmeri (M, XL, 36 ...)
    base_name: str = ""  # model nomi (yangi variant yaratish uchun)
    sibling_id: int | None = None  # shu modelning boshqa razmeri (toifa/narx/birlik shundan)
    choices: list | None = None  # razmer aytilmasa — tanlash uchun variantlar


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
    pending_size = False  # "razmer 36" — keyingi son razmer

    def size_text(val):
        return str(int(val)) if val == val.to_integral() else format(val.normalize(), "f")

    def add_num(val, *extra):
        nonlocal pending_size
        if pending_size:
            pending_size = False
            items.append(["size", size_text(val)])
        else:
            items.append(["num", val, False, *extra])

    def last_num_to_size():
        if items and items[-1][0] == "num":
            items[-1] = ["size", size_text(items[-1][1])]
            return True
        return False

    def flush():
        nonlocal words_acc
        if words_acc is not None:
            total, current = words_acc
            add_num(Decimal(str(total + current)))
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
            suf = m.group(2)
            if (m.group(1) + suf) in LETTER_SIZES:  # "2xl", "3xl"
                items.append(["size", (m.group(1) + suf).upper()])
                continue
            add_num(val, "digits")
            if suf in ("lik", "li") and last_num_to_size():  # "37lik"
                continue
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
            if tok in SIZE_MARKERS or tok.startswith(("razmer", "o'lcham")):
                if not last_num_to_size():  # "36 razmer" — oldingi son; "razmer 36" — keyingisi
                    pending_size = True
                continue
            if tok in ("lik", "li") and items and items[-1][0] == "num" and items[-1][3:4] == ["digits"]:
                last_num_to_size()  # "37 lik"
                continue
            if word in UNITS and items and items[-1][0] == "num":
                items.append(["unit", UNITS[word]])
            elif tok in LETTER_SIZES:
                items.append(["size", tok.upper()])
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


def _chunks(items):
    """Bir gapda bir necha razmer ("36 razmer 10 ta 37 razmer 50 ta") → har razmerga bo'lak.

    Qaytadi: (umumiy nom so'zlari va narx uchun prefiks, [bo'laklar]).
    """
    sizes = [i for i, it in enumerate(items) if it[0] == "size"]
    if len(sizes) <= 1:
        return [], [items]
    qty_at = [i for i, it in enumerate(items)
              if it[0] == "num" and i + 1 < len(items) and items[i + 1][0] == "unit"]
    qty_first = bool(qty_at) and qty_at[0] < sizes[0]  # "10 ta 36 razmer, 50 ta 37 ..."
    if qty_first:
        start = qty_at[0]
        cuts = [start] + [s + 1 for s in sizes[:-1]]
    else:
        start = sizes[0]
        cuts = sizes
    prefix = items[:start]
    chunks = [items[a:b] for a, b in zip(cuts, cuts[1:] + [len(items)], strict=True)]
    return prefix, chunks


def _analyze(items) -> dict:
    """Bitta qator tokenlari → {name, qty, unit, price, size, rest}."""
    nums = []  # (index, value, followed_by_unit, price_hint)
    unit = size = ""
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
        elif it[0] == "size" and not size:
            size = it[1]
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
    if unit == "g" and qty is not None:  # "500 gramm" → 0.5 kg
        qty, unit = qty / 1000, "kg"
    # Narx aniq aytilmagan bo'lsa — qolgan son (lekin u razmer bo'lishi ham mumkin: parse() hal qiladi)
    return {"name": " ".join(name_words), "qty": qty, "unit": unit, "size": size,
            "price": int(price) if price is not None else None,
            "rest": [int(v) if v == v.to_integral() else v for v in rest]}


def parse_segment_rows(text: str) -> list[dict]:
    """Bitta bo'lak (vergulgacha) → bir yoki bir necha qator (har razmerga bittadan)."""
    items = _classify(TOKEN_RE.findall(_norm(text)))
    prefix, chunks = _chunks(items)
    if not prefix and len(chunks) == 1:
        return [_analyze(chunks[0])]
    shared = _analyze(prefix) if prefix else {"name": "", "price": None, "rest": [], "unit": ""}
    rows = []
    for ch in chunks:
        r = _analyze(ch)
        r["name"] = " ".join(x for x in (shared["name"], r["name"]) if x)
        if r["price"] is None:
            r["price"] = shared["price"]
        r["unit"] = r["unit"] or shared["unit"]
        rows.append(r)
    # Nom gap oxirida bo'lsa ("10 ta 36 razmer 50 ta 37 razmer krossovka") — hamma razmerga
    names = {r["name"] for r in rows if r["name"]}
    if len(names) == 1:
        for r in rows:
            r["name"] = r["name"] or next(iter(names))
    # "... narxi 120 ming" oxirida bo'lsa — narxi yo'q qatorlarga ham
    last_price = next((r["price"] for r in reversed(rows) if r["price"] is not None), None)
    for r in rows:
        if r["price"] is None:
            r["price"] = last_price
    return rows


def parse_segment(text: str) -> dict:
    """Bitta bo'lak → birinchi qator (orqaga moslik; to'liq — parse_segment_rows)."""
    r = parse_segment_rows(text)[0]
    if r["price"] is None and r["rest"]:
        r["price"] = r["rest"][0]
    return r


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


def _base_of(p) -> str:
    return p.base_name or p.name.split(" — ")[0]


def _models(products) -> dict:
    """{model nomi (kichik harf): [razmerli variantlar]}."""
    out = {}
    for p in products:
        if p.size:
            out.setdefault(_norm(_base_of(p)), []).append(p)
    return out


def _find_model(name: str, models: dict):
    if not name:
        return None
    if name in models:
        return name
    for key in models:
        if key.startswith(name + " ") or name.startswith(key + " "):
            return key
    close = difflib.get_close_matches(name, list(models), n=1, cutoff=0.75)
    return close[0] if close else None


def _sizes_hint(variants) -> str:
    from apps.catalog.sizes import size_key as _size_key  # yagona tartib (XS < S < M, 36 < 37)

    return ", ".join(sorted({v.size for v in variants}, key=_size_key))


def parse(text: str, products) -> list[dict]:
    """Matn → kirim qatorlari (taklif). products — do'konning faol mahsulotlari."""
    products = list(products)
    models = _models(products)
    rows = []
    prev = None  # oldingi qator: "futbolka XL 10 ta, M 100 ta" — M ham futbolka
    for seg in SPLIT_RE.split(_norm(text)):
        seg = (seg or "").strip(" ,.-")
        if not seg or not TOKEN_RE.search(seg):
            continue
        for data in parse_segment_rows(seg):
            row = _build_row(seg, data, prev, products, models)
            rows.append(asdict(row))
            prev = (data["name"] or (prev[0] if prev else ""), row.price)
    return rows


def _build_row(seg, data, prev, products, models) -> Row:
    name = data["name"]
    inherited = False
    if not name and prev and prev[0] and (data["size"] or data["qty"] is not None):
        name, inherited = prev[0], True
    price, rest = data["price"], list(data["rest"])
    size = data["size"]
    model_key = _find_model(name, models)
    # Belgisiz raqamli razmer: "krossovka 36 10 ta" — 36 shu modelda bor razmer bo'lsa
    if not size and model_key:
        known = {v.size.upper() for v in models[model_key]}
        hit = next((x for x in rest if str(x).upper() in known), None)
        if hit is not None:
            size = str(hit).upper()
            rest.remove(hit)
    if price is None and rest:
        price = rest[0]
    if price is None and inherited and prev:
        price = prev[1]
    row = Row(raw=seg[:120], name=name[:120], unit=data["unit"], price=price, size=size)
    if data["qty"] is None or data["qty"] <= 0:
        row.error = "miqdor topilmadi"
    else:
        row.qty = format(data["qty"].normalize(), "f")
    if size:
        return _fill_variant(row, name, size, model_key, models)
    if model_key and not _match_exact(name, products):
        # Model razmerli, lekin razmer aytilmadi — ixtiyoriy razmerga yozib yubormaymiz
        variants = models[model_key]
        row.error = "razmerini tanlang: " + _sizes_hint(variants)
        row.product_name = _base_of(variants[0])
        from apps.catalog.sizes import size_key as _size_key

        row.choices = [{"size": v.size, "product_id": v.pk, "product_name": v.name,
                        "price": v.buy_price or None}
                       for v in sorted(variants, key=lambda v: _size_key(v.size))]
        return row
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
    return row


def _match_exact(name, products):
    """Razmersiz mahsulot shu nom bilan bormi (masalan, "Futbolka" alohida, razmersiz)."""
    return next((p for p in products if not p.size and _norm(p.name) == name), None)


def _fill_variant(row, name, size, model_key, models) -> Row:
    """Model + razmer → mavjud variant yoki shu modelning yangi varianti."""
    row.size = size
    if model_key:
        variants = models[model_key]
        base = _base_of(variants[0])
        p = next((v for v in variants if v.size.upper() == size.upper()), None)
        if p is not None:
            row.product_id, row.product_name, row.unit = p.pk, p.name, p.unit
            if row.price is None:
                row.price = p.buy_price or None
            return row
        sib = variants[0]
        row.is_new, row.base_name, row.sibling_id = True, base, sib.pk
        row.product_name, row.unit = f"{base} — {size}", sib.unit
        if row.price is None:
            row.price = sib.buy_price or None
        return row
    if not name:
        row.error = row.error or "mahsulot nomi topilmadi"
        return row
    base = name[:1].upper() + name[1:]
    row.is_new, row.base_name = True, base
    row.product_name, row.unit = f"{base} — {size}", row.unit or "dona"
    return row
