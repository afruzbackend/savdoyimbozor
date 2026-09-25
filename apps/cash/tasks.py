from celery import shared_task


@shared_task
def sync_declarations():
    """Soliq / onlayn kassa deklaratsiyasi (TAX_ADAPTER sozlanmagan bo'lsa — jim o'tadi)."""
    from apps.cash.sync import run_sync

    entry = run_sync()
    return None if entry is None else {"ok": entry.ok, "saved": entry.saved}
