"""Login urinishlarini cheklash: IP bo'yicha va (hisob, IP) juftligi bo'yicha.

Nega faqat hisobni bloklash yetmaydi: loginlar raqamli va taxmin qilinadi (STIR + do'kon
raqami). Hisobni har qanday 5 xato bloklasa, bitta skript butun bozor sotuvchilarini
bloklab qo'yardi (DoS). Shuning uchun:
  - (hisob, IP) juftligi: 5 xato → FAQAT shu qurilmadan shu hisobga kirish vaqtincha yopiq;
    haqiqiy egasi o'z telefonidan kiraveradi.
  - IP: 15 daqiqada 20 xato → shu IP'dan umuman urinib bo'lmaydi (parol tekshirilmaydi).
  - Hisob (bazada): turli IP'lardan jami 5×5 xato → hisob bloklanadi (tarqoq hujum).
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache

IP_WINDOW = 15 * 60
GLOBAL_FACTOR = 5  # hisob bazada bloklanishi uchun: login_max_attempts × shu


def _incr(key: str, ttl: int) -> int:
    cache.add(key, 0, ttl)
    try:
        return cache.incr(key)
    except ValueError:  # kalit shu orada muddati tugagan
        cache.set(key, 1, ttl)
        return 1


def ip_blocked(ip: str) -> bool:
    return bool(ip) and bool(cache.get(f"login:ipblock:{ip}"))


def pair_blocked(user, ip: str) -> bool:
    return user is not None and bool(cache.get(f"login:pairblock:{user.pk}:{ip}"))


def register_failure(ip: str, user, cfg) -> None:
    if ip and _incr(f"login:ipfail:{ip}", IP_WINDOW) >= settings.LOGIN_IP_MAX_FAILS:
        cache.set(f"login:ipblock:{ip}", 1, settings.LOGIN_IP_BLOCK_MINUTES * 60)
        cache.delete(f"login:ipfail:{ip}")
    if user is None:
        return
    lock = cfg.login_lock_minutes * 60
    if _incr(f"login:pairfail:{user.pk}:{ip}", lock) >= cfg.login_max_attempts:
        cache.set(f"login:pairblock:{user.pk}:{ip}", 1, lock)
        cache.delete(f"login:pairfail:{user.pk}:{ip}")
    user.register_failed_login(cfg.login_max_attempts * GLOBAL_FACTOR, cfg.login_lock_minutes)


def register_success(ip: str, user) -> None:
    cache.delete(f"login:pairfail:{user.pk}:{ip}")
    user.reset_lockout()
