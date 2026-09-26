from __future__ import annotations

import datetime
import re
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.utils import timezone

from apps.cash.models import CashRecord
from apps.cash.services import Declaration


class AdapterError(Exception):
    """Manba bilan aloqa/format xatosi — jurnalga yoziladi, ma'lumot yozilmaydi."""


class BaseAdapter:
    name = ""
    source = CashRecord.Source.TAX_API

    def __init__(self):
        self.row_errors: list[str] = []  # o'qib bo'lmagan qatorlar (jurnalga tushadi)

    def fetch(self, date_from: datetime.date, date_to: datetime.date) -> Iterable[Declaration]:
        raise NotImplementedError

    def done(self) -> None:
        """Muvaffaqiyatli yozilgandan keyin chaqiriladi (masalan, fayllarni arxivga olish)."""


def parse_date(value) -> datetime.date:
    """Sana yoki vaqt belgisi → MAHALLIY kun (UTC chek vaqti 21:30Z = ertasi kun Toshkentda)."""
    if isinstance(value, datetime.datetime):
        return (timezone.localtime(value) if timezone.is_aware(value) else value).date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 20000 < value < 80000:
        # Excel katakchasi "Umumiy" formatda bo'lsa sana seriya raqami bo'lib keladi: 46289 → 2026-09-24
        return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(value)))
    text = str(value or "").strip()
    try:
        dt = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        return (timezone.localtime(dt) if timezone.is_aware(dt) else dt).date()
    except ValueError:
        pass
    for fmt in ("%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    raise AdapterError(f"sana formati noma'lum: {value!r}")


_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+$")
_THOUSANDS_DOT = re.compile(r"^-?\d{1,3}(\.\d{3})+$")
_CURRENCY = re.compile(r"(so['ʻ’`]?m|sum|сум|uzs)\.?", re.I)


def parse_amount(value, divisor: int = 1) -> int:
    """Summa → butun so'm. Soliq/buxgalteriya eksportlarida uchraydigan hamma ko'rinish:
    "1 234 567", "1,234,567", "1.234.567", "1,234,567.50", "1.234.567,50", "1 234 567 so'm",
    "1234567.50", 123456700 (tiyin, divisor=100). Oxirgi ajratgich — o'nlik (2 xona), qolgani ming."""
    if value is None or value == "":
        raise AdapterError("summa yo'q")
    if isinstance(value, bool):
        raise AdapterError(f"summa noto'g'ri: {value!r}")
    if isinstance(value, (int, float)):
        text = str(value)
    else:
        text = _CURRENCY.sub("", str(value))
        text = text.replace(" ", "").replace("\u00a0", "").replace("\u202f", "").replace("'", "")
        if "," in text and "." in text:
            # Ikkalasi bor: oxirgisi o'nlik ("1,250,000.00" yoki "1.250.000,00")
            dec = "," if text.rfind(",") > text.rfind(".") else "."
            text = text.replace("." if dec == "," else ",", "").replace(dec, ".")
        elif text.count(",") > 1 or _THOUSANDS.match(text):
            text = text.replace(",", "")  # ming ajratgich: "1,234,567"
        elif text.count(".") > 1 or _THOUSANDS_DOT.match(text):
            text = text.replace(".", "")  # ming ajratgich: "1.234.567"
        else:
            text = text.replace(",", ".")  # o'nlik vergul: "12,5"
    try:
        number = Decimal(text)
    except InvalidOperation as e:
        raise AdapterError(f"summa noto'g'ri: {value!r}") from e
    if not number.is_finite():
        raise AdapterError(f"summa noto'g'ri: {value!r}")
    # Pul: yarmi yuqoriga (Python round() "bank" usulida 12.5 → 12 qilardi)
    return int((number / (divisor or 1)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
