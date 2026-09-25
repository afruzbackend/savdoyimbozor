"""Deklaratsiya (kassa) — yagona manba: qaysi summa rostlikka kiradi va tashqi ma'lumot qanday yoziladi.

Qoidalar:
- Bir do'kon-kunga bir nechta manba kelsa, ular QO'SHILMAYDI: eng ishonchlisi olinadi
  (Soliq API > virtual kassa > Excel). Aks holda Excel + API ikki barobar summa berardi.
- Tashqi qator do'konga shunday bog'lanadi: kassa (FM/terminal) raqami → STIR + do'kon raqami →
  STIR (faqat bitta do'koni bo'lsa). Noaniq qator yozilmaydi — jurnalga tushadi.
- Bitta yuklamadagi bir do'kon-kun qatorlari (masalan, chek bo'yicha) jamlanadi va o'sha
  manbadagi eski qiymatni ALMASHTIRADI (qayta sinxronlash ikki marta qo'shmaydi).
"""

from __future__ import annotations

import datetime
from collections import defaultdict
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.cash.models import SOURCE_PRIORITY, CashRecord


@dataclass
class Declaration:
    """Tashqi manbadan kelgan bitta qator (kunlik jami yoki bitta chek)."""

    stir: str
    date: datetime.date
    amount: int
    shop_number: str = ""
    fiscal_id: str = ""


def _pick(records):
    """(source, amount) juftlaridan eng ustuvor manbaning summasi."""
    best = max(records, key=lambda r: SOURCE_PRIORITY.get(r[0], 0))
    return best[1]


def declared_by_shop(shop_ids, day) -> dict[int, int]:
    """{shop_id: deklaratsiya summasi} — har do'kon uchun eng ishonchli manba (1 so'rov)."""
    grouped = defaultdict(list)
    for shop_id, source, amount in CashRecord.objects.filter(
        shop_id__in=shop_ids, date=day
    ).values_list("shop_id", "source", "amount"):
        grouped[shop_id].append((source, amount))
    return {sid: int(_pick(recs)) for sid, recs in grouped.items()}


def declared_for(shop, day) -> int:
    return declared_by_shop([shop.pk], day).get(shop.pk, 0)


def source_for(shop, day) -> str:
    """Rostlikka qaysi manba kirgani (do'kon sahifasida ko'rsatish uchun); yo'q bo'lsa ''."""
    recs = list(CashRecord.objects.filter(shop=shop, date=day).values_list("source", "amount"))
    if not recs:
        return ""
    return max(recs, key=lambda r: SOURCE_PRIORITY.get(r[0], 0))[0]


def _digits(value) -> str:
    return "".join(c for c in str(value or "") if c.isdigit())


class ShopResolver:
    """Tashqi qatorni do'konga bog'lash — barcha faol do'konlar bir marta xotiraga olinadi."""

    def __init__(self):
        from apps.shops.models import Shop

        self.by_fiscal, self.by_stir_number, self.by_stir = {}, {}, defaultdict(list)
        for pk, stir, number, fiscal in Shop.objects.filter(is_active=True).values_list(
            "pk", "stir", "number", "fiscal_id"
        ):
            if fiscal:
                self.by_fiscal[fiscal.strip().upper()] = pk
            if stir:
                self.by_stir_number[(stir, str(number).strip())] = pk
                self.by_stir[stir].append(pk)

    def resolve(self, d: Declaration) -> tuple[int | None, str]:
        fiscal = (d.fiscal_id or "").strip().upper()
        if fiscal and fiscal in self.by_fiscal:
            return self.by_fiscal[fiscal], ""
        stir = _digits(d.stir)
        if not stir:
            return None, "STIR yo'q"
        number = str(d.shop_number or "").strip()
        if number:
            pk = self.by_stir_number.get((stir, number))
            return (pk, "") if pk else (None, f"STIR {stir}, do'kon №{number} topilmadi")
        shops = self.by_stir.get(stir, [])
        if len(shops) == 1:
            return shops[0], ""
        if not shops:
            return None, f"STIR {stir} tizimda yo'q"
        return None, f"STIR {stir} {len(shops)} ta do'konda — kassa raqami (FM) kerak"


@dataclass
class IngestResult:
    fetched: int = 0
    saved: int = 0
    unmatched: int = 0
    problems: list | None = None
    dates: set | None = None


@transaction.atomic
def ingest(declarations, source: str) -> IngestResult:
    """Tashqi qatorlarni CashRecord'ga yozadi (bir do'kon-kun = bitta yozuv, manba bo'yicha)."""
    today = timezone.localdate()
    resolver = ShopResolver()
    totals: dict[tuple[int, datetime.date], int] = defaultdict(int)
    res = IngestResult(problems=[], dates=set())
    for d in declarations:
        res.fetched += 1
        problem = ""
        if not isinstance(d.date, datetime.date) or d.date > today:
            problem = f"sana noto'g'ri ({d.date})"
        elif d.amount is None or d.amount < 0:
            problem = f"summa noto'g'ri ({d.amount})"
        shop_id = None
        if not problem:
            shop_id, problem = resolver.resolve(d)
        if problem:
            res.unmatched += 1
            if len(res.problems) < 20:
                res.problems.append(problem)
            continue
        totals[(shop_id, d.date)] += int(d.amount)
    for (shop_id, day), amount in totals.items():
        CashRecord.objects.update_or_create(
            shop_id=shop_id, date=day, source=source, defaults={"amount": amount}
        )
        res.dates.add(day)
    res.saved = len(totals)
    return res
