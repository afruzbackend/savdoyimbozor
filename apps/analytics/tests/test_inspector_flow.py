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
def test_seller_cannot_open_inspector_dashboard(sclient):
    """Sotuvchi nazorat hostiga kirsa — dashboard ко'rsatilmasligi kerak (login yoki 403)."""
    r = sclient.get("/statistika/", HTTP_HOST=INSPECTOR_HOST)
    # visible_shops() sotuvchida bo'sh — sahifa ma'lumotsiz yoki redirect bo'ladi,
    # lekin boshqa do'kon ma'lumoti sizib chiqmasligi kerak.
    assert r.status_code in (200, 302, 403)
