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
def test_inspection_act_auto_generates(iclient, shop, inspector):
    """Jarima akti: act_number + jarima avtomatik to'ldiriladi, sahifa ochiladi."""
    from apps.analytics.models import Inspection

    insp = Inspection.objects.create(shop=shop, inspector=inspector, result="confirmed")
    r = iclient.get(f"/tekshiruv/{insp.pk}/akt/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200
    assert "DALOLATNOMA" in r.content.decode()
    insp.refresh_from_db()
    assert insp.act_number  # avtomatik raqam berildi
    assert insp.fine_amount is not None  # jarima avtomatik hisoblandi


@pytest.mark.django_db
def test_inspection_act_denied_for_other_market(sclient, shop):
    """Sotuvchi (yoki begona) akt sahifasiga kira olmaydi (urlconf/ruxsat)."""
    from apps.analytics.models import Inspection

    insp = Inspection.objects.create(shop=shop, result="confirmed")
    assert sclient.get(f"/tekshiruv/{insp.pk}/akt/").status_code == 404


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
def test_seller_sees_own_home_regardless_of_host(sclient):
    """BITTA host: sotuvchi qaysi host bilan kirsa ham o'z (sotuvchi) bosh sahifasi.

    Endi routing HOST emas, ROL bo'yicha — subdomain ahamiyatsiz.
    """
    r = sclient.get("/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200  # sotuvchi bosh sahifasi (redirect yo'q)


@pytest.mark.django_db
def test_seller_cannot_reach_inspector_urls(sclient, shop):
    """Sotuvchining urlconf'ida nazorat sahifalari yo'q → 404 (ruxsat avtomatik).

    Nazorat dashboard/xarita/do'kon mazmuni sotuvchiga umuman ko'rinmaydi.
    """
    assert sclient.get("/xarita/").status_code == 404
    assert sclient.get(f"/dokon/{shop.pk}/").status_code == 404
    assert sclient.get("/statistika/").status_code == 404


@pytest.mark.django_db
def test_inspector_home_renders(iclient):
    """Tekshiruvchi bosh sahifasi ochiladi."""
    assert iclient.get("/").status_code == 200


@pytest.mark.django_db
def test_ip_host_works_no_redirect(sclient):
    """127.0.0.1 (IP host)da ham sotuvchi o'z sahifasini ko'radi — redirect/loop yo'q."""
    r = sclient.get("/", HTTP_HOST="127.0.0.1:8000")
    assert r.status_code == 200


@pytest.mark.django_db
def test_login_page_opens(client):
    """Kirmagan foydalanuvchi login sahifasini ko'radi (istalgan host)."""
    r = client.get("/login/", HTTP_HOST="127.0.0.1:8000")
    assert r.status_code == 200
