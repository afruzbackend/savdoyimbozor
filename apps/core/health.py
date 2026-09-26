"""Tizim holati — monitoring (Uptime Kuma, Zabbix, Docker healthcheck) va panel kartasi uchun.

Har tekshiruv: {"name", "status": ok|warn|fail|unknown, "detail"}. Umumiy holat:
fail (baza/kesh ishlamasa) → HTTP 503; warn bo'lsa "degraded" (200, xizmat ishlayapti).
"""

from __future__ import annotations

import shutil
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils import timezone

HEARTBEAT_KEY = "health:celery:beat"
HEARTBEAT_MAX_AGE = 5 * 60


def _check(name, fn):
    try:
        status, detail = fn()
    except Exception as e:  # noqa: BLE001 — tekshiruv yiqilsa ham javob qaytsin
        status, detail = "fail", f"{type(e).__name__}: {e}"[:200]
    return {"name": name, "status": status, "detail": detail}


def _db():
    t = time.perf_counter()
    with connection.cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()
    ms = (time.perf_counter() - t) * 1000
    return ("ok" if ms < 200 else "warn"), f"{ms:.0f} ms"


def _cache():
    key = "health:probe"
    cache.set(key, "1", 30)
    return ("ok", settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1]) if cache.get(key) == "1" \
        else ("fail", "yozilgan qiymat o'qilmadi")


def _disk():
    worst = None
    for label, path in (("media", settings.MEDIA_ROOT), ("zaxira", settings.BACKUP_DIR)):
        p = Path(path)
        while not p.exists() and p.parent != p:
            p = p.parent
        u = shutil.disk_usage(p)
        free_pct = u.free / u.total * 100
        item = (free_pct, f"{label}: {u.free / 1e9:.1f} GB bo'sh ({free_pct:.0f}%)")
        worst = item if worst is None or item[0] < worst[0] else worst
    status = "ok" if worst[0] >= 15 else ("warn" if worst[0] >= 5 else "fail")
    return status, worst[1]


def _backup():
    from apps.core.models import BackupLog

    last = BackupLog.objects.filter(ok=True).first()
    if last is None:
        return "warn", "hali olinmagan"
    age = timezone.now() - last.created_at
    hours = age.total_seconds() / 3600
    status = "ok" if age <= timedelta(hours=26) and last.offsite_ok else "warn"
    where = "tashqarida ham" if last.offsite_ok else "faqat shu serverda"
    return status, f"{hours:.0f} soat oldin, {where}"


def _celery():
    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        return "unknown", "eager rejim (dev) — beat ishlatilmaydi"
    beat = cache.get(HEARTBEAT_KEY)
    if beat is None:
        return "warn", "beat yurak urishi yo'q (celery beat ishlamayapti yoki kesh umumiy emas)"
    age = time.time() - float(beat)
    return ("ok" if age <= HEARTBEAT_MAX_AGE else "warn"), f"{age:.0f} s oldin"


def _cameras():
    from apps.cameras.models import Camera

    active = Camera.objects.filter(is_active=True)
    total = active.count()
    if not total:
        return "unknown", "kamera ulanmagan"
    stale = active.filter(last_seen__lt=timezone.now() - timedelta(minutes=10)).count() + \
        active.filter(last_seen__isnull=True).count()
    tampered = active.filter(status=Camera.Status.TAMPERED).count()
    status = "ok" if not stale and not tampered else "warn"
    return status, f"{total - stale}/{total} aloqada" + (f", {tampered} buzilgan" if tampered else "")


def _tax():
    if not settings.TAX_ADAPTER:
        return "unknown", "sozlanmagan (Excel)"
    from apps.cash.sync import status

    s = status()
    if s["last"] and not s["last"].ok:
        return "warn", "oxirgi sinxron xato"
    return ("warn", "36 soatdan beri sinxron yo'q") if s["stale"] else ("ok", "sinxron")


def _sms():
    if not settings.SMS_BACKEND:
        return "unknown", "ulanmagan"
    from apps.core.models import SmsMessage

    failed = SmsMessage.objects.filter(status="failed",
                                       created_at__gte=timezone.now() - timedelta(days=1)).count()
    return ("warn", f"24 soatda {failed} xato") if failed else ("ok", settings.SMS_BACKEND)


CHECKS = [("database", _db), ("cache", _cache), ("disk", _disk), ("backup", _backup),
          ("celery", _celery), ("cameras", _cameras), ("tax_sync", _tax), ("sms", _sms)]
CRITICAL = {"database", "cache"}


def run(full: bool = True) -> dict:
    """full=False — faqat baza va kesh (ochiq so'rov: arzon, hujumda og'irlik bermaydi)."""
    checks = [_check(name, fn) for name, fn in CHECKS if full or name in CRITICAL]
    if any(c["status"] == "fail" and c["name"] in CRITICAL for c in checks):
        overall = "fail"
    elif any(c["status"] in ("warn", "fail") for c in checks):
        overall = "degraded"
    else:
        overall = "ok"
    return {"status": overall, "time": timezone.now().isoformat(timespec="seconds"),
            "checks": checks}


def beat() -> None:
    """Celery beat har daqiqada chaqiradi — "fon vazifalari tirik" belgisi."""
    cache.set(HEARTBEAT_KEY, str(time.time()), HEARTBEAT_MAX_AGE * 4)
