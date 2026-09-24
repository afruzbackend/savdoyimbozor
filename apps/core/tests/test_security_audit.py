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
