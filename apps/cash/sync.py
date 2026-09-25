"""Deklaratsiyani tashqi manbadan olish: adapter → ingest → rostlikni qayta hisoblash → jurnal."""

from __future__ import annotations

import datetime
import logging

from django.conf import settings
from django.utils import timezone

from apps.cash.adapters import AdapterError, get_adapter
from apps.cash.models import DeclarationSync
from apps.cash.services import ingest

log = logging.getLogger(__name__)


def default_range(today=None) -> tuple[datetime.date, datetime.date]:
    """Kecha va undan oldingi TAX_SYNC_DAYS-1 kun (Soliq tuzatishlari kechikib keladi)."""
    today = today or timezone.localdate()
    days = max(1, settings.TAX_SYNC_DAYS)
    return today - datetime.timedelta(days=days), today - datetime.timedelta(days=1)


def run_sync(date_from=None, date_to=None, adapter=None) -> DeclarationSync | None:
    """Bitta sinxronlash. Adapter sozlanmagan bo'lsa None (jim o'tadi)."""
    try:
        adapter = adapter or get_adapter()
    except AdapterError as e:
        return DeclarationSync.objects.create(source="tax_api", message=f"XATO: {e}")
    if adapter is None:
        return None
    if date_from is None or date_to is None:
        date_from, date_to = default_range()
    entry = DeclarationSync(source=adapter.source, adapter=adapter.name,
                            date_from=date_from, date_to=date_to)
    try:
        rows = list(adapter.fetch(date_from, date_to))
        result = ingest(rows, adapter.source)
        adapter.done()
    except AdapterError as e:
        entry.message = f"XATO: {e}"
        entry.problems = adapter.row_errors[:20]
        entry.save()
        log.warning("Deklaratsiya sinxronlash xatosi: %s", e)
        return entry
    except Exception as e:  # noqa: BLE001 — kutilmagan xato ham jurnalda ko'rinsin
        entry.message = f"XATO: {type(e).__name__}: {e}"
        entry.save()
        log.exception("Deklaratsiya sinxronlash yiqildi")
        return entry

    # Ta'sirlangan kunlar rostligi qayta hisoblanadi (o'tgan kun — yakuniy, signal bilan)
    from apps.analytics.scoring.services import recompute_for_date

    for day in sorted(result.dates):
        recompute_for_date(day)

    entry.ok = True
    entry.fetched = result.fetched + len(adapter.row_errors)
    entry.saved = result.saved
    entry.unmatched = result.unmatched + len(adapter.row_errors)
    entry.problems = (adapter.row_errors + result.problems)[:20]
    entry.message = f"{result.saved} ta do'kon-kun yozildi, {len(result.dates)} kun qayta hisoblandi."
    entry.save()
    return entry


def status() -> dict:
    """Panel kartasi uchun: sozlanganmi, oxirgi urinish va oxirgi muvaffaqiyatli sinxron."""
    last = DeclarationSync.objects.first()
    last_ok = DeclarationSync.objects.filter(ok=True).first()
    stale = bool(settings.TAX_ADAPTER) and (
        last_ok is None or timezone.now() - last_ok.created_at > datetime.timedelta(hours=36)
    )
    return {
        "adapter": settings.TAX_ADAPTER,
        "last": last,
        "last_ok": last_ok,
        "stale": stale,
    }
