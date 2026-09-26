"""Ikki bosqichli himoya: TOTP (RFC 6238) — Google Authenticator, Microsoft Authenticator va h.k.

Tashqi kutubxonasiz (hmac/sha1). Qayta ishlatishdan himoya: bir kod (vaqt qadami) faqat
bir marta qabul qilinadi (`User.totp_last_step`). Zaxira kodlar bir martalik, xeshlangan.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from django.conf import settings

PERIOD = 30
DIGITS = 6
ISSUER = "Bozor Nazorat"
BACKUP_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    s = secret.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret: str, step: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 10**DIGITS
    return f"{number:0{DIGITS}d}"


def verify(secret: str, code: str, *, last_step: int = 0, now: float | None = None,
           window: int = 1) -> int | None:
    """To'g'ri bo'lsa — mos vaqt qadami (keyingi safar shundan kattasi talab qilinadi), aks holda None.

    window=1: telefon soati ±30 soniya farq qilsa ham o'tadi.
    """
    code = "".join(c for c in str(code or "") if c.isdigit())
    if len(code) != DIGITS or not secret:
        return None
    current = int((time.time() if now is None else now) // PERIOD)
    for step in range(current - window, current + window + 1):
        if step > last_step and hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def provisioning_uri(secret: str, account: str) -> str:
    label = quote(f"{ISSUER}:{account}")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}"
            f"&digits={DIGITS}&period={PERIOD}")


def qr_svg(uri: str) -> str:
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    return img.to_string(encoding="unicode")


# ---------- Zaxira kodlar (telefon yo'qolganda) ----------

def _normalize_backup(code: str) -> str:
    return "".join(c for c in str(code or "").upper() if c.isalnum())


def _hash_backup(code: str) -> str:
    return hashlib.sha256((settings.SECRET_KEY + ":" + _normalize_backup(code)).encode()).hexdigest()


def new_backup_codes(n: int = 8) -> tuple[list[str], list[str]]:
    """(ko'rsatiladigan kodlar, saqlanadigan xeshlar). Kodlar faqat BIR MARTA ko'rsatiladi."""
    codes = []
    for _ in range(n):
        raw = "".join(secrets.choice(BACKUP_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes, [_hash_backup(c) for c in codes]


def use_backup_code(user, code: str) -> bool:
    """Zaxira kod to'g'ri bo'lsa — o'chiriladi (bir martalik) va True."""
    if len(_normalize_backup(code)) != 8:
        return False
    h = _hash_backup(code)
    codes = list(user.backup_codes or [])
    if h not in codes:
        return False
    codes.remove(h)
    user.backup_codes = codes
    user.save(update_fields=["backup_codes"])
    return True
