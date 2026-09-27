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
    assert "yashirilgan savdo" in html and "Rostlik qanday aniqlanadi" in html


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
def test_dashboard_falls_back_to_last_measured_day(iclient, shop):
    """Ertalab bugungi ball yo'q — dashboard kechagi (oxirgi o'lchangan) kunni ko'rsatadi, bo'sh emas."""
    import datetime

    from django.utils import timezone

    from apps.analytics.models import DailyScore

    y = timezone.localdate() - datetime.timedelta(days=1)
    DailyScore.objects.create(shop=shop, date=y, truth_pct=31, entered_sales=100000,
                              cash_amount=300000, measured=True, parts={"cash": 33})
    r = iclient.get("/", HTTP_HOST=INSPECTOR_HOST)
    assert r.context["recent_days"] == 7
    assert r.context["avg_truth"] == 31
    assert [s.shop_id for s, _lvl in r.context["risky"]] == [shop.pk]


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


@pytest.mark.django_db
def test_inspection_act_is_frozen_to_creation_date(iclient, shop):
    """Akt sanasi/davri tekshiruv kuniga qotiriladi — keyin ochganda o'zgarmaydi."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.analytics.models import Inspection

    insp = Inspection.objects.create(shop=shop, result="confirmed")
    old = timezone.now() - timedelta(days=10)
    Inspection.objects.filter(pk=insp.pk).update(created_at=old)
    r = iclient.get(f"/tekshiruv/{insp.pk}/akt/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200
    assert timezone.localtime(old).strftime("%d.%m.%Y") in r.content.decode()


@pytest.mark.django_db
def test_inspection_cannot_resolve_foreign_alert(iclient, shop, market):
    """Boshqa do'kon signalini POST orqali yopib bo'lmaydi (IDOR)."""
    from apps.analytics.models import Alert
    from apps.shops.models import Shop

    other = Shop.objects.create(market=market, number="999", stir="1")
    foreign = Alert.objects.create(shop=other, date="2026-01-01", kind="truth", level="red",
                                   reason="x")
    iclient.post("/tekshiruv/yangi/", {"shop": shop.pk, "alert": foreign.pk, "result": "false"},
                 HTTP_HOST=INSPECTOR_HOST)
    foreign.refresh_from_db()
    assert foreign.status == Alert.Status.NEW


@pytest.mark.django_db
def test_appeals_and_inspections_lists_render(iclient, shop, inspector):
    from apps.analytics.models import Appeal, Inspection

    Appeal.objects.create(shop=shop, message="Kassa xato yuklangan")
    Inspection.objects.create(shop=shop, inspector=inspector, result="confirmed", act_number="BN-1")
    r = iclient.get("/e-tirozlar/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200 and "Kassa xato yuklangan" in r.content.decode()
    r = iclient.get("/tekshiruvlar/?q=BN-1", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200 and "BN-1" in r.content.decode()
    # Menyuda javobsiz e'tiroz soni ko'rinadi
    assert r.context["nav_appeals_new"] == 1


@pytest.mark.django_db
def test_appeal_reject_requires_reason_and_accept_dismisses_alert(iclient, shop):
    from datetime import date

    from apps.analytics.models import Alert, Appeal

    alert = Alert.objects.create(shop=shop, date=date.today(), level="red", reason="x")
    ap = Appeal.objects.create(shop=shop, alert=alert, message="asossiz")
    iclient.post(f"/e-tiroz/{ap.pk}/javob/", {"action": "rejected", "response": " "},
                 HTTP_HOST=INSPECTOR_HOST)
    ap.refresh_from_db()
    assert ap.status == "new"  # sababsiz rad etilmadi
    r = iclient.post(f"/e-tiroz/{ap.pk}/javob/",
                     {"action": "accepted", "next": "/e-tirozlar/"}, HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 302 and r["Location"] == "/e-tirozlar/"
    ap.refresh_from_db()
    alert.refresh_from_db()
    assert ap.status == "accepted"
    assert alert.status == "dismissed"  # asossiz signal yopildi
    # Qayta javob berib bo'lmaydi (qarorni jimgina o'zgartirish yo'q)
    iclient.post(f"/e-tiroz/{ap.pk}/javob/", {"action": "rejected", "response": "y"},
                 HTTP_HOST=INSPECTOR_HOST)
    ap.refresh_from_db()
    assert ap.status == "accepted"


@pytest.mark.django_db
def test_appeal_respond_ignores_external_next(iclient, shop):
    from apps.analytics.models import Appeal

    ap = Appeal.objects.create(shop=shop, message="m")
    r = iclient.post(f"/e-tiroz/{ap.pk}/javob/",
                     {"action": "accepted", "next": "https://evil.example/"},
                     HTTP_HOST=INSPECTOR_HOST)
    assert "evil" not in r["Location"]


@pytest.mark.django_db
def test_inspection_requires_explicit_result(iclient, shop):
    """Natija tanlanmasa tekshiruv yozilmaydi (jim "Tasdiqlandi" ayblovi yo'q)."""
    from apps.analytics.models import Inspection

    iclient.post("/tekshiruv/yangi/", {"shop": shop.pk}, HTTP_HOST=INSPECTOR_HOST)
    assert not Inspection.objects.filter(shop=shop).exists()
    iclient.post("/tekshiruv/yangi/", {"shop": shop.pk, "result": "false"},
                 HTTP_HOST=INSPECTOR_HOST)
    assert Inspection.objects.filter(shop=shop, result="false").exists()
