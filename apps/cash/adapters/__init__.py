"""Soliq / onlayn kassa adapterlari — tashqi manbadan `Declaration` qatorlarini oladi.

Yangi manba qo'shish: `BaseAdapter` dan meros oling, `fetch()` ni yozing va shu yerdagi
ADAPTERS ga ro'yxatdan o'tkazing. Yozish/do'konga bog'lash — `apps.cash.services.ingest`.
"""

from __future__ import annotations

from django.conf import settings

from .base import AdapterError, BaseAdapter
from .http import HttpJsonAdapter
from .inbox import InboxAdapter

ADAPTERS: dict[str, type[BaseAdapter]] = {
    "http": HttpJsonAdapter,
    "inbox": InboxAdapter,
}

__all__ = ["ADAPTERS", "AdapterError", "BaseAdapter", "get_adapter"]


def get_adapter() -> BaseAdapter | None:
    """Sozlangan adapter (TAX_ADAPTER) yoki None — o'chiq bo'lsa."""
    name = (settings.TAX_ADAPTER or "").strip().lower()
    if not name:
        return None
    cls = ADAPTERS.get(name)
    if cls is None:
        raise AdapterError(f"Noma'lum TAX_ADAPTER: {name!r} (mumkin: {', '.join(ADAPTERS)})")
    return cls()
