"""Umumiy formatlash va xavfsiz parsing yordamchilari."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


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


def _clean_num(value) -> str:
    """Foydalanuvchi yozgan sonni tozalaydi: "25 000", "12,5", "1 000.00" -> parse qilinadigan."""
    s = str(value).strip().replace(" ", "").replace(" ", "")
    return s.replace(",", ".")


# Aqlli yuqori chegara: 9 kvadrillion so'm (BigInteger va JS xavfsiz butun son ichida).
# "1e999" kabi ulkan son bazada to'lib ketib 500 xato bermasin.
MAX_INT = 9_000_000_000_000_000


def to_int(value, default=None):
    """Formadan kelgan qiymat -> butun son (so'm). Bo'sh/xato bo'lsa `default`.

    `int(request.POST[...])` o'rniga — "12.5", "abc", "25 000", "1e999" kabi
    kiritishda 500 xato (crash) bo'lmasin.
    """
    if value is None:
        return default
    s = _clean_num(value)
    if s == "":
        return default
    try:
        d = Decimal(s)
        if not d.is_finite() or abs(d) > MAX_INT:
            return default
        return int(d)
    except (InvalidOperation, ValueError, OverflowError):
        return default


def to_dec(value, default=None):
    """Formadan kelgan qiymat -> Decimal (miqdor). Bo'sh/xato bo'lsa `default`."""
    if value is None:
        return default
    s = _clean_num(value)
    if s == "":
        return default
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return default
    if not d.is_finite() or abs(d) > 1_000_000_000:  # miqdor uchun aqlli chegara
        return default
    return d


def excel_str(value) -> str:
    """Excel katakchasini matnga: 25.0 (float) -> "25", 300000001.0 -> "300000001"."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


# Excel formula in'ektsiyasi (OWASP): shu belgilar bilan boshlangan matn formula bo'lib ishlaydi
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def excel_safe(value):
    """Eksport katakchasi: foydalanuvchi matni "=HYPERLINK(...)" bo'lsa formula bo'lib ketmasin —
    oldiga ' qo'yiladi (Excel uni matn deb ko'rsatadi). Sonlar tegilmaydi."""
    if isinstance(value, str) and value[:1] in _FORMULA_START:
        return "'" + value
    return value


def excel_row(values):
    return [excel_safe(v) for v in values]


PHONE_ERROR = "Telefon noto'g'ri — masalan +998 90 123 45 67"


def clean_phone(raw) -> str | None:
    """Telefon → "+998 90 123 45 67" (hamma joyda bir xil ko'rinish). Bo'sh (yoki faqat "+998") → "".
    Noto'g'ri → None (formada xato ko'rsatiladi). "90 1234567", "998901234567", "8 90..." ham qabul."""
    from apps.core.sms import normalize_phone

    digits = "".join(c for c in str(raw or "") if c.isdigit())
    if digits in ("", "998"):
        return ""
    n = normalize_phone(digits)
    if n is None:
        return None
    return f"+{n[:3]} {n[3:5]} {n[5:8]} {n[8:10]} {n[10:12]}"
