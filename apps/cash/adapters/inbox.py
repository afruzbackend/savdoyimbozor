"""Papka ("inbox") adapteri: Soliq/operator fayllarni TAX_INBOX_DIR ga tashlaydi (SFTP, YIP).

Fayl turlari:
  *.csv  — sarlavha qatori bilan: stir,date,amount[,shop_number][,fiscal_id]  (; ham bo'ladi)
  *.json — [ {"stir": ..., "date": ..., "amount": ..., "fiscal_id": ...}, ... ]
Har fayl to'liq kunlik ma'lumot bo'lsin. Muvaffaqiyatli yozilgach fayl `processed/` ga,
o'qib bo'lmasa `failed/` ga ko'chiriladi — bir fayl ikki marta hisoblanmaydi.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.cash.services import Declaration

from .base import AdapterError, BaseAdapter, parse_amount, parse_date

ALIASES = {
    "stir": ("stir", "inn", "tin"),
    "date": ("date", "sana", "day"),
    "amount": ("amount", "summa", "total", "sum"),
    "shop_number": ("shop_number", "dokon", "shop", "number"),
    "fiscal_id": ("fiscal_id", "fm", "terminal_id", "kassa"),
}


def _norm(row: dict) -> dict:
    low = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
    return {ours: next((low[a] for a in names if a in low), None) for ours, names in ALIASES.items()}


class InboxAdapter(BaseAdapter):
    name = "inbox"

    def __init__(self):
        super().__init__()
        self.dir = Path(settings.TAX_INBOX_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.files: list[Path] = []
        self.failed: list[Path] = []

    def fetch(self, date_from=None, date_to=None):
        # Sana oralig'i e'tiborga olinmaydi: papkadagi har yangi fayl o'qiladi
        rows = []
        for path in sorted(self.dir.glob("*")):
            if not path.is_file() or path.suffix.lower() not in (".csv", ".json"):
                continue
            try:
                raw = path.read_bytes().decode("utf-8-sig")
                items = self._json(raw) if path.suffix.lower() == ".json" else self._csv(raw)
            except (UnicodeDecodeError, ValueError, AdapterError) as e:
                self.row_errors.append(f"{path.name}: o'qib bo'lmadi ({e})")
                self.failed.append(path)
                continue
            for n, item in enumerate(items, start=1):
                try:
                    rows.append(self._row(item))
                except AdapterError as e:
                    self.row_errors.append(f"{path.name}:{n}: {e}")
            self.files.append(path)
        return rows

    @staticmethod
    def _json(raw):
        data = json.loads(raw)
        if isinstance(data, dict):
            data = data.get("results") or data.get("data") or []
        if not isinstance(data, list):
            raise AdapterError("JSON ro'yxat emas")
        return [x for x in data if isinstance(x, dict)]

    @staticmethod
    def _csv(raw):
        sample = raw[:2048]
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        return list(csv.DictReader(io.StringIO(raw), delimiter=delimiter))

    @staticmethod
    def _row(item: dict) -> Declaration:
        r = _norm(item)
        return Declaration(
            stir=str(r["stir"] or ""),
            date=parse_date(r["date"]),
            amount=parse_amount(r["amount"]),
            shop_number=str(r["shop_number"] or "").strip(),
            fiscal_id=str(r["fiscal_id"] or "").strip(),
        )

    def _move(self, paths, sub):
        target = self.dir / sub
        target.mkdir(exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        for p in paths:
            shutil.move(str(p), str(target / f"{stamp}-{p.name}"))

    def done(self):
        self._move(self.files, "processed")
        self._move(self.failed, "failed")
