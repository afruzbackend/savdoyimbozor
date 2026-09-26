"""Login oqimi: blok, parol almashtirish, muvaffaqiyatli kirish."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import SystemSettings
from conftest import PW, SELLER_HOST


@pytest.mark.django_db
def test_wrong_password_locks_after_max_attempts(seller):
    """Maks xatodan keyin SHU qurilmadan kirish yopiladi (to'g'ri parol ham o'tmaydi),
    lekin hujumchi haqiqiy egani o'z telefonidan bloklab qo'ya olmaydi (DoS himoyasi)."""
    from django.core.cache import cache

    cache.clear()
    cfg = SystemSettings.get_solo()
    c = Client(REMOTE_ADDR="10.0.0.66")
    url = reverse("login")
    for _ in range(cfg.login_max_attempts):
        c.post(url, {"username": seller.username, "password": "notright"}, HTTP_HOST=SELLER_HOST)
    r = c.post(url, {"username": seller.username, "password": PW}, HTTP_HOST=SELLER_HOST)
    assert r.wsgi_request.user.is_anonymous
    assert "vaqtincha bloklangan" in r.content.decode()
    seller.refresh_from_db()
    assert not seller.is_locked  # hisob bazada bloklanmagan
    owner = Client(REMOTE_ADDR="10.0.0.7")
    r = owner.post(url, {"username": seller.username, "password": PW}, HTTP_HOST=SELLER_HOST)
    assert r.wsgi_request.user.is_authenticated


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
def test_issued_login_is_numeric_only(shop, market):
    """Admin bergan login FAQAT raqamdan iborat (seller + inspector)."""
    from apps.accounts.services import create_inspector, create_seller

    s = create_seller(shop, full_name="Ali Vali")
    assert s["login"].isdigit(), s["login"]
    i = create_inspector("Nodir Inspektor", [market])
    assert i["login"].isdigit(), i["login"]


@pytest.mark.django_db
def test_issued_login_unique_and_numeric_on_collision(shop, market):
    """Bir xil STIR+raqam (boshqa bozorda) bo'lsa ham login betakror va baribir raqamli."""
    from apps.accounts.services import create_seller
    from apps.geo.models import Market, Region
    from apps.shops.models import Shop

    a = create_seller(shop, full_name="Bir")
    # Boshqa bozor, lekin bir xil STIR va do'kon raqami -> login_username() bir xil chiqadi
    m2 = Market.objects.create(region=Region.objects.first() or market.region, name="Ikkinchi bozor")
    shop2 = Shop.objects.create(market=m2, number=shop.number, stir=shop.stir)
    b = create_seller(shop2, full_name="Ikki")
    assert a["login"] != b["login"]
    assert a["login"].isdigit() and b["login"].isdigit()


@pytest.mark.django_db
def test_admin_sees_only_issued_temporary_password(shop):
    """Admin faqat O'ZI BERGAN vaqtinchalik parolni ko'radi (login varaqasi yo'qolsa). Egasi o'zi
    tanlagan parol ochiq saqlanmaydi — baza sizib chiqsa ham, admin ham ko'rmaydi."""
    from apps.accounts.services import create_seller, reset_password

    cred = create_seller(shop, full_name="Sardor")
    u = cred["user"]
    assert u.visible_password == cred["password"] and len(cred["password"]) >= 10
    newpw = reset_password(u)
    u.refresh_from_db()
    assert u.visible_password == newpw
    c = Client()
    c.force_login(u)
    c.post(reverse("password_change"), {"password1": "YangiParol9", "password2": "YangiParol9"},
           HTTP_HOST=SELLER_HOST)
    u.refresh_from_db()
    assert u.visible_password == ""  # o'zi tanlagani — faqat xesh
    assert u.check_password("YangiParol9")


@pytest.mark.django_db
def test_password_policy_by_role(shop, inspector):
    """Sotuvchi — kamida 8, xodim — kamida 12; faqat raqam va keng tarqalgan parollar rad."""
    from apps.accounts.services import create_seller

    seller = create_seller(shop, full_name="Ali")["user"]
    c = Client()
    c.force_login(seller)
    for bad in ("Ab1234", "12345678901", "password1"):
        c.post(reverse("password_change"), {"password1": bad, "password2": bad}, HTTP_HOST=SELLER_HOST)
        seller.refresh_from_db()
        assert not seller.check_password(bad), bad
    c.post(reverse("password_change"), {"password1": "Bozor2026x", "password2": "Bozor2026x"},
           HTTP_HOST=SELLER_HOST)
    seller.refresh_from_db()
    assert seller.check_password("Bozor2026x")
    c.force_login(inspector)
    c.post(reverse("password_change"), {"password1": "Nazorat2026", "password2": "Nazorat2026"},
           HTTP_HOST="nazorat.localhost")  # 11 belgi — xodimga kam
    inspector.refresh_from_db()
    assert not inspector.check_password("Nazorat2026")
    c.post(reverse("password_change"), {"password1": "Nazorat-2026x", "password2": "Nazorat-2026x"},
           HTTP_HOST="nazorat.localhost")
    inspector.refresh_from_db()
    assert inspector.check_password("Nazorat-2026x") and inspector.visible_password == ""
