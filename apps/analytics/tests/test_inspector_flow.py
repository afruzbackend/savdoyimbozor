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
