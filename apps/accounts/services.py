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


@transaction.atomic
def create_seller(shop, *, full_name="", phone="", is_owner=True) -> dict:
    """Do'konga sotuvchi hisobi ochadi. Qaytadi: {user, login, password}."""
    username = shop.login_username()
    base = username
    i = 1
    while User.objects.filter(username=username).exists():
        i += 1
        username = f"{base}-{i}"
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
    user.set_password(password)
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
        base = "insp"
        n = User.objects.filter(role=Role.INSPECTOR).count() + 1
        username = f"{base}{n:03d}"
        while User.objects.filter(username=username).exists():
            n += 1
            username = f"{base}{n:03d}"
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
    user.set_password(password)
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


def reset_password(user) -> str:
    """Yangi vaqtinchalik parol o'rnatadi, birinchi kirishda almashtiriladi."""
    password = generate_password()
    user.set_password(password)
    user.must_change_password = True
    user.reset_lockout()
    user.save()
    return password
