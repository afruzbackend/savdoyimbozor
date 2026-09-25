"""SMS yuborish — yagona kirish nuqtasi `send(key, phone, text)` (idempotent, jurnal bilan).

Backend `SMS_BACKEND` bilan tanlanadi (config/settings/base.py). Xato asosiy oqimni
to'xtatmaydi: natija `SmsMessage` jurnaliga yoziladi, panelda ko'rinadi.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError

log = logging.getLogger(__name__)

TIMEOUT = 15


class SmsError(Exception):
    pass


def normalize_phone(raw) -> str | None:
    """O'zbekiston raqami → "998XXXXXXXXX". "+998 90 123-45-67", "90 1234567", "8 90..." ham."""
    digits = "".join(c for c in str(raw or "") if c.isdigit())
    if len(digits) == 9:
        digits = "998" + digits
    elif len(digits) == 10 and digits.startswith("8"):
        digits = "998" + digits[1:]
    if len(digits) == 12 and digits.startswith("998"):
        return digits
    return None


def enabled() -> bool:
    return bool((settings.SMS_BACKEND or "").strip())


# ---------- Backendlar: (provider_id) qaytaradi yoki SmsError ----------

def _post(url, data: dict, headers: dict, *, form=False):
    body = (urllib.parse.urlencode(data) if form else json.dumps(data)).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json",
               "Accept": "application/json", **headers}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8") or "{}"
    except urllib.error.HTTPError as e:
        raise SmsError(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SmsError(f"aloqa yo'q: {getattr(e, 'reason', e)}") from e
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _console(phone, text):
    log.info("SMS (console) → %s: %s", phone, text)
    return "console"


ESKIZ = "https://notify.eskiz.uz/api"
ESKIZ_TOKEN_KEY = "sms:eskiz:token"


def _eskiz_token(refresh=False) -> str:
    token = None if refresh else cache.get(ESKIZ_TOKEN_KEY)
    if token:
        return token
    if not (settings.SMS_ESKIZ_EMAIL and settings.SMS_ESKIZ_PASSWORD):
        raise SmsError("SMS_ESKIZ_EMAIL / SMS_ESKIZ_PASSWORD sozlanmagan")
    data = _post(f"{ESKIZ}/auth/login", {"email": settings.SMS_ESKIZ_EMAIL,
                                         "password": settings.SMS_ESKIZ_PASSWORD}, {}, form=True)
    token = (data.get("data") or {}).get("token")
    if not token:
        raise SmsError("Eskiz: token olinmadi")
    cache.set(ESKIZ_TOKEN_KEY, token, 60 * 60 * 24 * 25)  # token ~30 kun amal qiladi
    return token


def _eskiz(phone, text):
    payload = {"mobile_phone": phone, "message": text, "from": settings.SMS_FROM}
    try:
        data = _post(f"{ESKIZ}/message/sms/send", payload,
                     {"Authorization": f"Bearer {_eskiz_token()}"}, form=True)
    except SmsError as e:
        if "401" not in str(e):
            raise
        data = _post(f"{ESKIZ}/message/sms/send", payload,  # token eskirgan — yangilab qayta
                     {"Authorization": f"Bearer {_eskiz_token(refresh=True)}"}, form=True)
    return str(data.get("id") or data.get("message_id") or "")


def _http(phone, text):
    if not settings.SMS_HTTP_URL:
        raise SmsError("SMS_HTTP_URL sozlanmagan")
    headers = {"Authorization": f"Bearer {settings.SMS_HTTP_TOKEN}"} if settings.SMS_HTTP_TOKEN else {}
    data = _post(settings.SMS_HTTP_URL, {"phone": phone, "text": text, "from": settings.SMS_FROM},
                 headers)
    return str(data.get("id") or "")


BACKENDS = {"console": _console, "eskiz": _eskiz, "http": _http}


def send(key: str, phone_raw: str, text: str, *, shop=None):
    """SMS yuboradi va jurnalga yozadi. Shu `key` bilan yuborilgan bo'lsa — qayta yubormaydi.

    Qaytadi: SmsMessage yoki None (SMS o'chiq / allaqachon yuborilgan).
    """
    from apps.core.models import SmsMessage

    name = (settings.SMS_BACKEND or "").strip().lower()
    if not name:
        return None
    msg = SmsMessage.objects.filter(key=key[:120]).first()
    if msg is not None and msg.status != SmsMessage.Status.FAILED:
        return None  # yuborilgan yoki raqam yaroqsiz — qayta urinilmaydi
    phone = normalize_phone(phone_raw)
    if msg is None:
        msg = SmsMessage(key=key[:120])
    # Tarmoq xatosi bo'lgan eslatma keyingi ishga tushishda qayta yuboriladi (o'sha yozuv)
    msg.phone, msg.text, msg.provider, msg.shop = (
        (phone or str(phone_raw or ""))[:20], text[:480], name, shop)
    msg.error, msg.provider_id = "", ""
    if phone is None:
        msg.status, msg.error = SmsMessage.Status.INVALID, "O'zbekiston raqami emas"
    else:
        backend = BACKENDS.get(name)
        try:
            if backend is None:
                raise SmsError(f"Noma'lum SMS_BACKEND: {name}")
            msg.provider_id = backend(phone, text)[:80]
            msg.status = SmsMessage.Status.SENT
        except SmsError as e:
            msg.status, msg.error = SmsMessage.Status.FAILED, str(e)[:300]
            log.warning("SMS yuborilmadi (%s): %s", key, e)
    try:
        msg.save()
    except IntegrityError:  # parallel ishga tushgan vazifa allaqachon yozgan
        return None
    return msg
