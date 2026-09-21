"""Bosh admin (panel): do'kon+sotuvchi yaratish, rol chegarasi."""

import pytest
from django.test import Client

from apps.accounts.services import create_inspector
from apps.shops.models import Shop
from conftest import PW

PANEL_HOST = "panel.localhost"


@pytest.mark.django_db
def test_admin_creates_shop_with_location(aclient, market):
    from apps.catalog.models import ShopCategory

    cat = ShopCategory.objects.create(name="Meva-sabzavot")
    r = aclient.post(
        "/hisob/yangi/",
        {
            "role": "seller", "full_name": "Yangi Sotuvchi", "phone": "+998901112233",
            "number": "77", "stir": "555555555", "market": market.pk, "category": cat.pk,
            "address": "Chorsu 3-qator", "latitude": "41.325", "longitude": "69.24",
        },
        HTTP_HOST=PANEL_HOST,
    )
    assert r.status_code == 302
    s = Shop.objects.get(number="77")
    assert s.stir == "555555555"
    assert s.category == cat  # savdo turi
    assert s.latitude == 41.325
    assert s.staff.exists()  # sotuvchi ochildi


@pytest.mark.django_db
def test_admin_page_renders(aclient):
    for p in ["/", "/foydalanuvchilar/", "/hisob/yangi/"]:
        assert aclient.get(p, HTTP_HOST=PANEL_HOST).status_code == 200


@pytest.mark.django_db
def test_inspector_cannot_open_panel(market):
    """Tekshiruvchi panel sahifalariga kira olmaydi — urlconf'ida yo'q (404).

    Bosh sahifasida o'z (nazorat) dashboardini ko'radi.
    """
    cred = create_inspector("Nodir", [market])
    u = cred["user"]
    u.set_password(PW)
    u.must_change_password = False
    u.save()
    c = Client()
    c.force_login(u)
    assert c.get("/").status_code == 200  # o'z dashboardi
    assert c.get("/foydalanuvchilar/").status_code == 404  # panel sahifasi — yo'q
    assert c.get("/hisob/yangi/").status_code == 404


@pytest.mark.django_db
def test_seller_blocked_from_panel(sclient):
    """Sotuvchi panel sahifalariga kira olmaydi (404), bosh sahifasida o'z sahifasi."""
    assert sclient.get("/").status_code == 200
    assert sclient.get("/foydalanuvchilar/").status_code == 404


@pytest.mark.django_db
def test_admin_cannot_block_self(aclient, admin_user):
    """Admin o'zini bloklay olmaydi (aks holda tizimга kira olmay qoladi)."""
    r = aclient.post(
        f"/foydalanuvchilar/{admin_user.pk}/holat/", HTTP_HOST=PANEL_HOST
    )
    assert r.status_code == 302
    admin_user.refresh_from_db()
    assert admin_user.is_active is True


@pytest.mark.django_db
def test_cannot_block_last_superadmin(aclient, admin_user):
    """Oxirgi faol super adminni (o'zidan boshqa admin yo'q) bloklab bo'lmaydi."""
    from apps.accounts.models import Role, User

    other = User.objects.create(
        username="admin2", role=Role.SUPERADMIN, is_staff=True, is_superuser=True
    )
    other.set_password(PW)
    other.must_change_password = False
    other.save()
    # admin_user admin2'ni bloklaydi -> qoladi 1 ta faol admin (admin_user) -> ruxsat
    r = aclient.post(f"/foydalanuvchilar/{other.pk}/holat/", HTTP_HOST=PANEL_HOST)
    assert r.status_code == 302
    other.refresh_from_db()
    assert other.is_active is False
    # endi admin2 (bloklangan) qayta faollashsin, keyin admin_user'ni bloklashga urinib ko'ramiz:
    # faqat 1 ta faol admin qolgani uchun (admin2 bloklangan) admin_user'ni bloklab bo'lmaydi
    c2 = Client()
    other.is_active = True
    other.save()
    c2.force_login(other)
    # admin2 admin_user'ni bloklaydi (2 ta faol admin bor) -> ruxsat, qoladi admin2
    r = c2.post(f"/foydalanuvchilar/{admin_user.pk}/holat/", HTTP_HOST=PANEL_HOST)
    admin_user.refresh_from_db()
    assert admin_user.is_active is False
    # endi faqat admin2 faol -> admin2 o'zini bloklay olmaydi (self guard)
    r = c2.post(f"/foydalanuvchilar/{other.pk}/holat/", HTTP_HOST=PANEL_HOST)
    other.refresh_from_db()
    assert other.is_active is True
