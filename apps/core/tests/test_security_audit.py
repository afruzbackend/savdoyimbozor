"""Chuqur audit topgan xavfsizlik baglari — qaytib buzilmasin."""

import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from conftest import INSPECTOR_HOST, PW, SELLER_HOST


def _png_bytes():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


# ---------- Media: dalil fotolari ochiq emas ----------

@pytest.mark.django_db
def test_media_requires_login_and_ownership(sclient, shop, product, market, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    photo = SimpleUploadedFile("w.png", _png_bytes(), content_type="image/png")
    sclient.post("/hisobdan-chiqarish/", {"product": product.pk, "quantity": "1",
                                          "reason": "chirigan", "photo": photo},
                 HTTP_HOST=SELLER_HOST)
    from apps.sales.models import WriteOff

    wo = WriteOff.objects.get(shop=shop)
    url = "/media/" + wo.photo.name
    # Egasi ko'radi
    assert sclient.get(url, HTTP_HOST=SELLER_HOST).status_code == 200
    # Login qilmagan — yo'q
    assert Client().get(url).status_code == 404
    # Boshqa do'kon sotuvchisi — yo'q
    from apps.accounts.services import create_seller
    from apps.shops.models import Shop

    other = Shop.objects.create(market=market, number="909", stir="5")
    u = create_seller(other, full_name="Begona")["user"]
    u.must_change_password = False
    u.save()
    c = Client()
    c.force_login(u)
    assert c.get(url, HTTP_HOST=SELLER_HOST).status_code == 404


@pytest.mark.django_db
def test_writeoff_rejects_non_image(sclient, shop, product):
    from apps.sales.models import WriteOff

    fake = SimpleUploadedFile("x.html", b"<script>alert(1)</script>", content_type="text/html")
    sclient.post("/hisobdan-chiqarish/", {"product": product.pk, "quantity": "1",
                                          "reason": "x", "photo": fake}, HTTP_HOST=SELLER_HOST)
    fake = SimpleUploadedFile("x.png", b"<script>alert(1)</script>", content_type="image/png")
    sclient.post("/hisobdan-chiqarish/", {"product": product.pk, "quantity": "1",
                                          "reason": "x", "photo": fake}, HTTP_HOST=SELLER_HOST)
    assert not WriteOff.objects.filter(shop=shop).exists()


# ---------- Kamera API: noto'g'ri format 500 bermasin ----------

@pytest.mark.django_db
@pytest.mark.parametrize("body", [
    {"events": ["abc", 5]},
    {"events": "notalist"},
    {"type": "visit", "payload": {"count": "abc"}},
    {"type": "visit", "timestamp": "2099-01-01T00:00:00Z"},
    {"type": "visit", "timestamp": "garbage"},
    {"type": "visit", "shop_id": "abc"},
])
def test_camera_events_bad_input_no_500(market, body):
    from apps.cameras.models import Camera

    cam = Camera.objects.create(name="k", market=market)
    r = Client().post("/api/events/", json.dumps(body), content_type="application/json",
                      HTTP_X_CAMERA_TOKEN=cam.token)
    assert r.status_code in (201, 400)


@pytest.mark.django_db
def test_camera_future_event_rejected(market):
    from apps.cameras.models import Camera, CameraEvent

    cam = Camera.objects.create(name="k", market=market)
    Client().post("/api/events/", json.dumps({"type": "visit",
                                              "timestamp": "2099-01-01T00:00:00Z"}),
                  content_type="application/json", HTTP_X_CAMERA_TOKEN=cam.token)
    assert not CameraEvent.objects.exists()


@pytest.mark.django_db
def test_camera_with_events_cannot_be_deleted(aclient, market):
    from apps.cameras.models import Camera, CameraEvent

    cam = Camera.objects.create(name="k", market=market)
    from django.utils import timezone

    CameraEvent.objects.create(camera=cam, type="visit", ts=timezone.now())
    aclient.post("/kameralar/", {"action": "delete", "id": cam.pk}, HTTP_HOST="panel.localhost")
    assert Camera.objects.filter(pk=cam.pk).exists()
    old = cam.token
    aclient.post("/kameralar/", {"action": "rotate", "id": cam.pk}, HTTP_HOST="panel.localhost")
    cam.refresh_from_db()
    assert cam.token != old


# ---------- Auth ----------

@pytest.mark.django_db
def test_forced_password_change_cannot_be_skipped(shop):
    from apps.accounts.services import create_seller

    u = create_seller(shop, full_name="Yangi")["user"]  # must_change_password=True
    c = Client()
    c.force_login(u)
    r = c.get("/", HTTP_HOST=SELLER_HOST)
    assert r.status_code == 302 and r["Location"].endswith("/password/change/")
    r = c.post("/api/sales/", "{}", content_type="application/json", HTTP_HOST=SELLER_HOST)
    assert r.status_code == 403


@pytest.mark.django_db
def test_weak_or_same_password_rejected(sclient, seller):
    sclient.post("/password/change/", {"password1": "123456", "password2": "123456"},
                 HTTP_HOST=SELLER_HOST)
    seller.refresh_from_db()
    assert not seller.check_password("123456")
    sclient.post("/password/change/", {"password1": PW, "password2": PW}, HTTP_HOST=SELLER_HOST)
    seller.refresh_from_db()
    assert seller.check_password(PW)  # o'zgarmadi (eski bilan bir xil rad etildi)


@pytest.mark.django_db
def test_createsuperuser_lands_in_panel():
    from apps.accounts.models import User

    u = User.objects.create_superuser("root", password=PW)  # rol standart: seller
    u.must_change_password = False
    u.save()
    c = Client()
    c.force_login(u)
    r = c.get("/foydalanuvchilar/")
    assert r.status_code == 200  # panel sahifasi


@pytest.mark.django_db
def test_admin_can_save_own_phone(aclient, admin_user):
    """Panelda /sozlamalar/ (tizim) va hisob sozlamalari to'qnashmasin."""
    aclient.post("/profil/sozlamalar/", {"phone": "+998901234567"}, HTTP_HOST="panel.localhost")
    admin_user.refresh_from_db()
    assert admin_user.phone == "+998901234567"


@pytest.mark.django_db
def test_export_and_shop_view_are_audited(iclient, shop):
    from apps.core.models import AuditLog

    iclient.get("/hisobot/eksport/", HTTP_HOST=INSPECTOR_HOST)
    iclient.get(f"/dokon/{shop.pk}/", HTTP_HOST=INSPECTOR_HOST)
    assert AuditLog.objects.filter(action="export").exists()
    assert AuditLog.objects.filter(action="view", path=f"/dokon/{shop.pk}/").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("path,data", [
    ("/kirim/", {"product": "abc", "quantity": "1", "unit_price": "1"}),
    ("/qaytarish/", {"product": "abc", "quantity": "1", "reason": "x"}),
    ("/nasiya/", {"pay": "abc"}),
    ("/tuzatish/", {"sale": "abc", "new_total": "1", "reason": "x"}),
])
def test_non_numeric_ids_no_500(sclient, shop, path, data):
    r = sclient.post(path, data, HTTP_HOST=SELLER_HOST)
    assert r.status_code in (302, 404)


@pytest.mark.django_db
def test_seller_cannot_self_resolve_alert(sclient, shop):
    from datetime import timedelta

    from django.utils import timezone

    from apps.analytics.models import Alert

    al = Alert.objects.create(shop=shop, date=timezone.localdate() - timedelta(days=1),
                              kind="zero_sales", level="red", reason="x")
    sclient.post("/e-tiroz/", {"nosales_alert": al.pk, "message": "yopiq edi"},
                 HTTP_HOST=SELLER_HOST)
    al.refresh_from_db()
    assert al.status == "new"


@pytest.mark.django_db
def test_alert_dismiss_audited_with_detail(iclient, shop):
    from django.utils import timezone

    from apps.analytics.models import Alert
    from apps.core.models import AuditLog

    al = Alert.objects.create(shop=shop, date=timezone.localdate(), level="red", reason="x")
    iclient.post(f"/signallar/{al.pk}/amal/", {"action": "dismiss"}, HTTP_HOST=INSPECTOR_HOST)
    log = AuditLog.objects.filter(path=f"/signallar/{al.pk}/amal/").latest("created_at")
    assert "e'tiborsiz" in log.detail and f"№{shop.number}" in log.detail


@pytest.mark.django_db
def test_login_attempts_audited_once_with_ip(seller):
    from apps.core.models import AuditLog

    c = Client()
    c.post("/login/", {"username": seller.username, "password": "xato-parol"},
           REMOTE_ADDR="10.0.0.7")
    c.post("/login/", {"username": seller.username, "password": PW}, REMOTE_ADDR="10.0.0.7")
    logs = list(AuditLog.objects.filter(path="/login/").order_by("created_at"))
    assert len(logs) == 2  # har urinish bitta yozuv (ikki marta emas)
    assert "Xato parol" in logs[0].detail and logs[0].ip == "10.0.0.7"
    assert logs[1].detail == "Muvaffaqiyatli kirish" and logs[1].interface == "seller"


# ---------- Xato sahifalari (motion-dizayn) ----------

@pytest.mark.django_db
def test_error_pages_render_custom_scenes(client, sclient):
    r = client.get("/bunday-sahifa-yoq/")
    assert r.status_code == 404 and "Bu rasta bo" in r.content.decode()
    # CSRF — "Sahifa eskirdi"
    c = Client(enforce_csrf_checks=True)
    r = c.post("/login/", {"username": "x", "password": "y"})
    assert r.status_code == 403 and "Sahifa eskirdi" in r.content.decode()
    # 500 shablon so'rovsiz ham chiqadi (Django server_error kabi)
    from django.template import loader

    html = loader.get_template("500.html").render()
    assert "Tarozi biroz qiyshaydi" in html and "{#" not in html
    for code in ("400", "403", "404", "500", "csrf"):
        r = sclient.get(f"/prefs/xato/{code}/", HTTP_HOST=SELLER_HOST)
        assert r.status_code == 200 and "{#" not in r.content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/", "/sotuv/", "/skaner/", "/nasiya/", "/mahsulotlar/", "/kirim/",
                                  "/kassa/", "/kun-yakuni/", "/qaytarish/", "/e-tiroz/"])
def test_no_raw_template_comments_on_seller_pages(sclient, shop, path):
    """Ko'p qatorli {# #} izoh sahifaga matn bo'lib chiqmasin."""
    r = sclient.get(path, HTTP_HOST=SELLER_HOST)
    assert r.status_code == 200
    assert "{#" not in r.content.decode() and "#}" not in r.content.decode()


# ---------- Audit IP soxtalashtirilmaydi ----------

def test_client_ip_ignores_spoofed_forwarded_for(settings, rf):
    from apps.core.net import client_ip

    req = rf.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6", REMOTE_ADDR="10.0.0.5")
    settings.BEHIND_PROXY = False
    assert client_ip(req) == "10.0.0.5"  # to'g'ridan-to'g'ri: sarlavhaga ishonilmaydi
    settings.BEHIND_PROXY = True
    # nginx: X-Forwarded-For = "<mijoz yozgani>, <haqiqiy IP>", X-Real-IP = haqiqiy IP
    req = rf.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9", HTTP_X_REAL_IP="203.0.113.9",
                 REMOTE_ADDR="172.18.0.3")
    assert client_ip(req) == "203.0.113.9"
    req = rf.get("/", HTTP_X_FORWARDED_FOR="6.6.6.6, 203.0.113.9", REMOTE_ADDR="172.18.0.3")
    assert client_ip(req) == "203.0.113.9"


# ---------- Production: ma'lum/kuchsiz SECRET_KEY bilan ishga tushmaydi ----------

def test_prod_refuses_weak_secret_key():
    import os
    import subprocess
    import sys

    def run(key):
        env = dict(os.environ, DJANGO_SETTINGS_MODULE="config.settings.prod", SECRET_KEY=key,
                   DEBUG="False", ALLOWED_HOSTS="x", CSRF_TRUSTED_ORIGINS="https://x")
        return subprocess.run([sys.executable, "-c", "import django; django.setup()"],
                              env=env, capture_output=True, text=True, timeout=120)

    weak = run("change-me-in-production")
    assert weak.returncode != 0 and "SECRET_KEY" in weak.stderr
    assert run("k" * 50).returncode == 0


@pytest.mark.django_db
def test_security_headers_csp_and_permissions(client):
    """CSP: manba faqat o'z domeni (XSS bo'lsa ham begona skript/so'rov yo'q); kamera/mikrofon faqat o'zimizga."""
    r = client.get("/login/")
    csp = r["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "object-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert "connect-src 'self'" in csp and "http" not in csp  # tashqi manba ruxsat etilmagan
    assert "camera=(self)" in r["Permissions-Policy"] and "geolocation=()" in r["Permissions-Policy"]
