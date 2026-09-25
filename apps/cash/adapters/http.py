"""HTTPS JSON API adapteri (Soliq qo'mitasi / OFD / virtual kassa operatori).

So'rov:  GET {TAX_API_URL}?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
         Authorization: Bearer {TAX_API_TOKEN}
Javob:   [ {...}, ... ]  yoki  {"results": [...], "next": "<keyingi sahifa URL>"}
Maydonlar TAX_API_FIELDS bilan moslanadi (standart: stir, date, amount, fiscal_id, shop_number).
Summa tiyinda kelsa — TAX_API_AMOUNT_DIVISOR=100.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from apps.cash.services import Declaration

from .base import AdapterError, BaseAdapter, parse_amount, parse_date

DEFAULT_FIELDS = {
    "stir": "stir",
    "date": "date",
    "amount": "amount",
    "fiscal_id": "fiscal_id",
    "shop_number": "shop_number",
}
MAX_PAGES = 1000  # cheksiz "next" halqasidan himoya


def field_map() -> dict[str, str]:
    """TAX_API_FIELDS="stir=tin,amount=total" → standart xaritaning ustiga yoziladi."""
    fields = dict(DEFAULT_FIELDS)
    for pair in (settings.TAX_API_FIELDS or "").split(","):
        if "=" in pair:
            ours, theirs = (x.strip() for x in pair.split("=", 1))
            if ours in fields and theirs:
                fields[ours] = theirs
    return fields


def _get(obj: dict, path: str):
    """"receipt.total" kabi ichma-ich yo'l ham qo'llanadi."""
    for key in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


class HttpJsonAdapter(BaseAdapter):
    name = "http"

    def __init__(self):
        super().__init__()
        self.url = settings.TAX_API_URL
        if not self.url:
            raise AdapterError("TAX_API_URL sozlanmagan")
        scheme = urllib.parse.urlsplit(self.url).scheme
        if scheme != "https" and not settings.DEBUG:
            # Soliq ma'lumoti shifrsiz kanalda yuborilmasin
            raise AdapterError("TAX_API_URL https bo'lishi shart")
        self.fields = field_map()
        self.divisor = settings.TAX_API_AMOUNT_DIVISOR

    def _request(self, url: str):
        headers = {"Accept": "application/json", "User-Agent": "BozorNazorat/1.0"}
        if settings.TAX_API_TOKEN:
            headers["Authorization"] = f"Bearer {settings.TAX_API_TOKEN}"
        last = None
        for attempt in range(3):  # vaqtinchalik uzilishda qayta urinish
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=settings.TAX_API_TIMEOUT) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise AdapterError(f"Ruxsat yo'q ({e.code}) — TAX_API_TOKEN ni tekshiring") from e
                last = f"HTTP {e.code}"
                if e.code < 500:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = str(getattr(e, "reason", e))
            except json.JSONDecodeError as e:
                raise AdapterError("Javob JSON emas") from e
            if attempt < 2:
                time.sleep(2**attempt)
        raise AdapterError(f"Soliq API bilan aloqa yo'q: {last}")

    def fetch(self, date_from, date_to):
        sep = "&" if "?" in self.url else "?"
        url = f"{self.url}{sep}" + urllib.parse.urlencode(
            {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()}
        )
        rows = []
        for _page in range(MAX_PAGES):
            data = self._request(url)
            if isinstance(data, list):
                items, url = data, None
            elif isinstance(data, dict):
                items, url = data.get("results") or data.get("data") or [], data.get("next")
            else:
                raise AdapterError("Kutilmagan javob tuzilishi")
            for item in items:
                try:
                    rows.append(self._row(item))
                except AdapterError as e:  # bitta buzuq qator butun yuklamani to'xtatmasin
                    self.row_errors.append(str(e))
            if not url:
                return rows
            url = urllib.parse.urljoin(self.url, url)
            if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(self.url).netloc:
                # token begona hostga yuborilmasin
                raise AdapterError("next boshqa hostga ko'rsatmoqda — to'xtatildi")
        raise AdapterError("Sahifalar juda ko'p (next halqasi?)")

    def _row(self, item: dict) -> Declaration:
        f = self.fields
        return Declaration(
            stir=str(_get(item, f["stir"]) or ""),
            date=parse_date(_get(item, f["date"])),
            amount=parse_amount(_get(item, f["amount"]), self.divisor),
            fiscal_id=str(_get(item, f["fiscal_id"]) or ""),
            shop_number=str(_get(item, f["shop_number"]) or ""),
        )
