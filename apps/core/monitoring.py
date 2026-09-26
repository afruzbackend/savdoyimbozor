"""Xato monitoringi (Sentry protokoli). Tavsiya: o'zimizning serverdagi GlitchTip (ochiq kodli,
Sentry bilan mos) — davlat ma'lumoti chet el xizmatiga chiqmaydi. SENTRY_DSN bo'sh bo'lsa o'chiq.

Yuborishdan OLDIN maxfiy qiymatlar tozalanadi: parol, token, 2FA kodi, sessiya/CSRF cookie,
kamera tokeni. `send_default_pii=False` — foydalanuvchi IP/cookie avtomatik yuborilmaydi.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

SENSITIVE = ("password", "passwd", "secret", "token", "code", "csrf", "sessionid", "cookie",
             "authorization", "visible_password", "totp", "backup", "api_key", "dsn")
MASK = "[tozalandi]"


def _is_sensitive(key) -> bool:
    k = str(key).lower()
    return any(s in k for s in SENSITIVE)


def scrub(value, depth=0):
    """dict/list ichidan maxfiy kalitlarni niqoblaydi (rekursiv, chuqurligi cheklangan)."""
    if depth > 8:
        return value
    if isinstance(value, dict):
        return {k: (MASK if _is_sensitive(k) else scrub(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(scrub(v, depth + 1) for v in value)
    return value


def before_send(event, hint=None):
    request = event.get("request") or {}
    for part in ("data", "headers", "cookies", "query_string", "env"):
        if isinstance(request.get(part), dict):
            request[part] = scrub(request[part])
        elif part in ("cookies", "query_string") and request.get(part):
            request[part] = MASK
    for exc in (event.get("exception") or {}).get("values", []) or []:
        for frame in (exc.get("stacktrace") or {}).get("frames", []) or []:
            if isinstance(frame.get("vars"), dict):
                frame["vars"] = scrub(frame["vars"])
    if isinstance(event.get("extra"), dict):
        event["extra"] = scrub(event["extra"])
    return event


def init(dsn: str, *, environment: str, traces: float, release: str = "") -> bool:
    """settings.py'dan chaqiriladi. Paket yo'q bo'lsa — ogohlantirish, ilova ishlayveradi."""
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
    except ImportError:
        log.warning("SENTRY_DSN berilgan, lekin sentry-sdk o'rnatilmagan — monitoring o'chiq")
        return False
    sentry_sdk.init(
        dsn=dsn,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        environment=environment,
        release=release or None,
        traces_sample_rate=traces,
        send_default_pii=False,
        before_send=before_send,
    )
    return True
