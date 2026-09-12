"""Bosh admin (panel): do'kon+sotuvchi yaratish, rol chegarasi."""

import pytest
from django.test import Client

from apps.accounts.services import create_inspector
from apps.shops.models import Shop
from conftest import PW

PANEL_HOST = "panel.localhost"


@pytest.fixture
def admin_user(db):
    from apps.accounts.models import Role, User

    u = User.objects.create(username="admin1", role=Role.SUPERADMIN, is_staff=True, is_superuser=True)
    u.set_password(PW)
    u.must_change_password = False
    u.save()
    return u


@pytest.fixture
def aclient(admin_user):
    c = Client()
    c.force_login(admin_user)
    return c


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
    """Tekshiruvchi panel hostiga kirsa — o'z hostiga yo'naltiriladi (403 emas, redirect)."""
    cred = create_inspector("Nodir", [market])
    u = cred["user"]
    u.set_password(PW)
    u.must_change_password = False
    u.save()
    c = Client()
    c.force_login(u)
    r = c.get("/", HTTP_HOST=PANEL_HOST)
    assert r.status_code == 302
    assert "nazorat." in r.url  # o'z interfeysiga
    assert "panel." not in r.url


@pytest.mark.django_db
def test_seller_blocked_from_panel(sclient):
    r = sclient.get("/", HTTP_HOST=PANEL_HOST)
    assert r.status_code == 302
    assert "sotuvchi." in r.url
