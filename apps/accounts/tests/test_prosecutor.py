"""Prokuror (kuzatuvchi) roli: hamma narsani KO'RADI, hech narsani o'zgartirmaydi, har ko'rishi auditda."""

import datetime

import pytest
from django.test import Client
from django.utils import timezone

from conftest import INSPECTOR_HOST, PW


@pytest.fixture
def prosecutor(market):
    from apps.accounts.services import create_prosecutor

    user = create_prosecutor("Aziz Prokurorov", [])["user"]
    user.set_password(PW)
    user.must_change_password = False
    user.save()
    return user


@pytest.fixture
def pclient(prosecutor):
    c = Client()
    c.force_login(prosecutor)
    return c


@pytest.fixture
def alert(shop):
    from apps.analytics.models import Alert

    return Alert.objects.create(shop=shop, date=timezone.localdate() - datetime.timedelta(days=1),
                                level="red", reason="Kassa bilan farq")


@pytest.mark.django_db
def test_login_is_numeric_and_sees_all_markets(prosecutor, shop, market):
    from apps.accounts.models import Role
    from apps.geo.models import Market
    from apps.shops.models import Shop

    assert prosecutor.role == Role.PROSECUTOR
    assert prosecutor.username.isdigit() and prosecutor.username.startswith("90")
    assert prosecutor.is_monitor and not prosecutor.is_inspector
    # Bozor biriktirilmagan — butun respublika ko'rinadi
    other_market = Market.objects.create(region=market.region, name="Oloy")
    other = Shop.objects.create(market=other_market, number="7", stir="77")
    assert set(prosecutor.visible_shops()) == {shop, other}
    # Bozor biriktirilsa — faqat o'shalar
    prosecutor.assigned_markets.set([other_market])
    assert list(prosecutor.visible_shops()) == [other]


@pytest.mark.django_db
def test_can_view_monitoring_pages(pclient, shop, alert):
    for url in ("/", "/xarita/", "/signallar/", "/tekshiruvlar/", "/e-tirozlar/", "/hodisalar/",
                "/ombor/", f"/ombor/dokon/{shop.pk}/", f"/dokon/{shop.pk}/", "/qidiruv/?q=Ali",
                "/statistika/", "/hisobot/", "/kameralar/"):
        r = pclient.get(url, HTTP_HOST=INSPECTOR_HOST)
        assert r.status_code == 200, url
        assert "Faqat ko'rish" in r.content.decode(), url


@pytest.mark.django_db
def test_every_write_is_blocked(pclient, shop, alert):
    from apps.analytics.models import Alert, Incident, Inspection

    posts = [
        (f"/signallar/{alert.pk}/amal/", {"action": "dismiss"}),
        ("/tekshiruv/yangi/", {"shop": shop.pk, "result": "ok"}),
        ("/hodisalar/yangi/", {"kind": "fire", "market": shop.market_id}),
        ("/e-tiroz/1/javob/", {"action": "accepted"}),
    ]
    for url, data in posts:
        r = pclient.post(url, data, HTTP_HOST=INSPECTOR_HOST)
        assert r.status_code == 403, url
        assert "Kuzatuvchi rejimi" in r.content.decode()
    alert.refresh_from_db()
    assert alert.status == Alert.Status.NEW
    assert not Inspection.objects.exists() and not Incident.objects.exists()
    # Yaratish formalari ham ochilmaydi
    for url in ("/tekshiruv/yangi/", "/hodisalar/yangi/"):
        assert pclient.get(url, HTTP_HOST=INSPECTOR_HOST).status_code == 403, url


@pytest.mark.django_db
def test_action_buttons_hidden(pclient, iclient, shop, alert):
    page = pclient.get("/signallar/", HTTP_HOST=INSPECTOR_HOST).content.decode()
    assert f"/signallar/{alert.pk}/amal/" not in page
    assert "/tekshiruv/yangi/" not in pclient.get(f"/dokon/{shop.pk}/",
                                                  HTTP_HOST=INSPECTOR_HOST).content.decode()
    assert "/hodisalar/yangi/" not in pclient.get("/hodisalar/",
                                                  HTTP_HOST=INSPECTOR_HOST).content.decode()
    # Oddiy inspektorda tugmalar bor va "Faqat ko'rish" belgisi yo'q
    ipage = iclient.get("/signallar/", HTTP_HOST=INSPECTOR_HOST).content.decode()
    assert f"/signallar/{alert.pk}/amal/" in ipage
    assert "Faqat ko'rish" not in ipage


@pytest.mark.django_db
def test_every_view_is_audited(pclient, prosecutor, shop):
    from apps.core.models import AuditLog

    pclient.get("/hisobot/", HTTP_HOST=INSPECTOR_HOST)
    pclient.get(f"/dokon/{shop.pk}/", HTTP_HOST=INSPECTOR_HOST)
    paths = set(AuditLog.objects.filter(user=prosecutor, action="view").values_list("path", flat=True))
    assert {"/hisobot/", f"/dokon/{shop.pk}/"} <= paths


@pytest.mark.django_db
def test_own_settings_still_allowed(pclient, prosecutor):
    r = pclient.post("/logout/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code in (200, 302)


@pytest.mark.django_db
def test_panel_creates_prosecutor_without_markets(aclient, market):
    from apps.accounts.models import Role, User

    r = aclient.post("/hisob/yangi/", {"role": "prosecutor", "full_name": "Kamola Nazorat"},
                     HTTP_HOST="panel.localhost")
    assert r.status_code == 302
    u = User.objects.get(role=Role.PROSECUTOR)
    assert u.first_name == "Kamola" and u.must_change_password
    assert not u.assigned_markets.exists()
    # Tahrirda bozor biriktiriladi
    r = aclient.post(f"/foydalanuvchilar/{u.pk}/", {"full_name": "Kamola Nazorat",
                                                    "markets": [market.pk, "x"]},
                     HTTP_HOST="panel.localhost")
    assert r.status_code == 302
    assert list(u.assigned_markets.all()) == [market]
