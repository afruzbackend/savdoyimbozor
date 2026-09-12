"""Nazoratchi oqimi: sahifalar, statistika, ruxsat chegarasi."""

import pytest

from conftest import INSPECTOR_HOST


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path", ["/", "/xarita/", "/statistika/", "/hisobot/", "/signallar/", "/qidiruv/"]
)
def test_inspector_pages_render(iclient, shop, path):
    r = iclient.get(path, HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200


@pytest.mark.django_db
def test_shop_detail_visible_to_assigned_inspector(iclient, shop):
    r = iclient.get(f"/dokon/{shop.pk}/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200


@pytest.mark.django_db
def test_evidence_page_renders(iclient, shop):
    """Dalil to'plami sahifasi ochiladi va asosiy bo'limlar bor."""
    r = iclient.get(f"/dokon/{shop.pk}/dalil/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200
    html = r.content.decode()
    assert "Tekshiruv dalil" in html
    assert "Yashirilgan savdo" in html


@pytest.mark.django_db
def test_dashboard_shows_hidden_sales(iclient, shop):
    r = iclient.get("/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200
    assert "yashirilgan savdo" in r.content.decode().lower()


@pytest.mark.django_db
def test_statistics_shows_seller_row(iclient, shop, seller):
    from django.utils import timezone

    from apps.analytics.models import DailyScore

    DailyScore.objects.create(
        shop=shop, date=timezone.localdate(), truth_pct=72, entered_sales=100000, cash_amount=90000
    )
    r = iclient.get("/statistika/", HTTP_HOST=INSPECTOR_HOST)
    html = r.content.decode()
    assert f"№{shop.number}" in html
    assert "Sotuvchilar statistikasi" in html


@pytest.mark.django_db
def test_seller_redirected_off_inspector_host(sclient):
    """Sotuvchi nazorat hostiga kirsa — o'z (sotuvchi) hostiga yo'naltiriladi."""
    r = sclient.get("/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 302
    assert "sotuvchi." in r.url  # o'z interfeysiga qaytariladi
    assert "nazorat." not in r.url


@pytest.mark.django_db
def test_seller_dashboard_not_leaked_on_inspector_host(sclient):
    """Nazorat dashboard mazmuni sotuvchiga sizib chiqmasligi kerak."""
    r = sclient.get("/", HTTP_HOST=INSPECTOR_HOST)
    # Redirect bo'ladi — nazorat mazmuni umuman render qilinmaydi
    assert r.status_code == 302


@pytest.mark.django_db
def test_inspector_stays_on_inspector_host(iclient):
    """Tekshiruvchi o'z hostида qoladi (yo'naltirilmaydi)."""
    r = iclient.get("/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200


@pytest.mark.django_db
def test_ip_host_redirects_to_valid_localhost_not_broken_host(sclient):
    """127.0.0.1 (IP host)da rol mos kelmasa — buzuq host emas, to'g'ri *.localhost.

    Regressiya: ilgari '127.0.0.1' → 'sotuvchi.0.0.1' (ERR_INVALID_REDIRECT/loop).
    """
    r = sclient.get("/", HTTP_HOST="127.0.0.1:8000")
    assert r.status_code == 302
    assert "sotuvchi.localhost" in r.url  # to'g'ri dev manzili
    assert "0.0.1" not in r.url  # buzuq host yasalmaydi


@pytest.mark.django_db
def test_ip_host_login_page_not_redirected(client):
    """127.0.0.1/login/ — loop bo'lmasin (login sahifasi ochilaveradi)."""
    r = client.get("/login/", HTTP_HOST="127.0.0.1:8000")
    assert r.status_code == 200
