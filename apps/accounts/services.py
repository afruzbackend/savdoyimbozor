"""Hisob ochish xizmatlari — super admin foydalanadi.

Sotuvchi login = STIR-DO'KONRAQAMI. Vaqtinchalik parol generatsiya qilinadi,
birinchi kirishda almashtirish majburiy (must_change_password=True).
"""

from __future__ import annotations

import secrets

from django.db import transaction

from .models import Role, User

# Chalkashtirmaydigan belgilar (0/O, 1/l yo'q)
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_password(length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def _unique_numeric_username(base) -> str:
    """FAQAT raqamli, betakror login. Band bo'lsa oxiriga raqam qo'shiladi (baribir raqam)."""
    base = "".join(c for c in str(base) if c.isdigit()) or "1"
    username = base
    i = 1
    while User.objects.filter(username=username).exists():
        i += 1
        username = f"{base}{i}"
    return username


@transaction.atomic
def create_seller(shop, *, full_name="", phone="", is_owner=True) -> dict:
    """Do'konga sotuvchi hisobi ochadi. Login FAQAT raqam. Qaytadi: {user, login, password}."""
    username = _unique_numeric_username(shop.login_username())
    password = generate_password()
    parts = full_name.split()
    user = User.objects.create(
        username=username,
        role=Role.SELLER,
        shop=shop,
        is_shop_owner=is_owner,
        first_name=parts[0] if parts else (shop.owner_name or "Sotuvchi"),
        last_name=" ".join(parts[1:]),
        phone=phone or shop.owner_phone,
        must_change_password=True,
    )
    user.set_password_visible(password)
    user.save()
    return {
        "user": user,
        "login": username,
        "password": password,
        "name": user.get_full_name() or shop.owner_name,
        "shop": str(shop),
    }


@transaction.atomic
def create_inspector(full_name, markets, *, phone="", username=None) -> dict:
    """Tekshiruvchi hisobi ochadi."""
    if not username:
        # Inspektor logini FAQAT raqam. 70-prefiks STIR asosidagi seller loginlaridan ajratadi.
        n = User.objects.filter(role=Role.INSPECTOR).count() + 1
        username = _unique_numeric_username(f"70{n:04d}")
    password = generate_password()
    parts = full_name.split()
    user = User.objects.create(
        username=username,
        role=Role.INSPECTOR,
        first_name=parts[0] if parts else "Inspektor",
        last_name=" ".join(parts[1:]),
        phone=phone,
        must_change_password=True,
    )
    user.set_password_visible(password)
    user.save()
    if markets:
        user.assigned_markets.set(markets)
    return {
        "user": user,
        "login": username,
        "password": password,
        "name": user.get_full_name(),
        "shop": "—",
    }


@transaction.atomic
def create_prosecutor(full_name, markets, *, phone="") -> dict:
    """Prokuror (kuzatuvchi) hisobi — FAQAT ko'rish. Bozor berilmasa — butun respublika."""
    n = User.objects.filter(role=Role.PROSECUTOR).count() + 1
    username = _unique_numeric_username(f"90{n:04d}")
    password = generate_password()
    parts = full_name.split()
    user = User.objects.create(
        username=username,
        role=Role.PROSECUTOR,
        first_name=parts[0] if parts else "Kuzatuvchi",
        last_name=" ".join(parts[1:]),
        phone=phone,
        must_change_password=True,
    )
    user.set_password_visible(password)
    user.save()
    if markets:
        user.assigned_markets.set(markets)
    return {"user": user, "login": username, "password": password,
            "name": user.get_full_name(), "shop": "—"}


def reset_password(user) -> str:
    """Yangi vaqtinchalik parol o'rnatadi, birinchi kirishda almashtiriladi."""
    password = generate_password()
    user.set_password_visible(password)
    user.must_change_password = True
    user.reset_lockout()
    user.save()
    return password
