"""Login oqimi: blok, parol almashtirish, muvaffaqiyatli kirish."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import SystemSettings
from conftest import PW, SELLER_HOST


@pytest.mark.django_db
def test_wrong_password_locks_after_max_attempts(seller):
    cfg = SystemSettings.get_solo()
    c = Client()
    url = reverse("login")
    for _ in range(cfg.login_max_attempts):
        c.post(url, {"username": seller.username, "password": "notright"}, HTTP_HOST=SELLER_HOST)
    seller.refresh_from_db()
    assert seller.is_locked  # maks urinishdan keyin bloklanadi


@pytest.mark.django_db
def test_locked_account_rejected_even_with_correct_password(seller):
    from django.utils import timezone

    seller.locked_until = timezone.now() + timezone.timedelta(minutes=15)
    seller.save(update_fields=["locked_until"])
    c = Client()
    r = c.post(
        reverse("login"),
        {"username": seller.username, "password": PW},
        HTTP_HOST=SELLER_HOST,
    )
    assert r.wsgi_request.user.is_anonymous  # to'g'ri parol ham blok paytida o'tmaydi


@pytest.mark.django_db
def test_successful_login_resets_lockout(seller):
    seller.failed_attempts = 3
    seller.save(update_fields=["failed_attempts"])
    c = Client()
    r = c.post(
        reverse("login"),
        {"username": seller.username, "password": PW},
        HTTP_HOST=SELLER_HOST,
        follow=True,
    )
    seller.refresh_from_db()
    assert seller.failed_attempts == 0
    assert r.wsgi_request.user.is_authenticated


@pytest.mark.django_db
def test_must_change_password_redirects(shop):
    from apps.accounts.services import create_seller

    cred = create_seller(shop, full_name="Yangi Sotuvchi")
    c = Client()
    r = c.post(
        reverse("login"),
        {"username": cred["login"], "password": cred["password"]},
        HTTP_HOST=SELLER_HOST,
    )
    assert r.status_code == 302
    assert reverse("password_change") in r.url


@pytest.mark.django_db
def test_admin_sees_current_password(shop):
    """Admin joriy parolni ko'radi: yaratishda, reset'da va self-almashtirishdan keyin."""
    from apps.accounts.services import create_seller, reset_password

    cred = create_seller(shop, full_name="Sardor")
    u = cred["user"]
    # 1) Yaratilganda ochiq parol saqlanadi
    assert u.visible_password == cred["password"]
    # 2) Admin reset qilganda yangilanadi
    newpw = reset_password(u)
    u.refresh_from_db()
    assert u.visible_password == newpw
    # 3) Sotuvchi o'zi almashtirsa ham admin joriy parolni ko'radi
    c = Client()
    c.force_login(u)
    c.post(
        reverse("password_change"),
        {"password1": "YangiParol9", "password2": "YangiParol9"},
        HTTP_HOST=SELLER_HOST,
    )
    u.refresh_from_db()
    assert u.visible_password == "YangiParol9"
    assert u.check_password("YangiParol9")  # haqiqiy parol ham o'zgargan
