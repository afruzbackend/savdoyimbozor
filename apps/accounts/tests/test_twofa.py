"""Ikki bosqichli himoya (TOTP) va IP bo'yicha login cheklovi."""

import time

import pytest
from django.core.cache import cache
from django.test import Client

from apps.accounts import totp
from apps.core.models import SystemSettings
from conftest import INSPECTOR_HOST, PW, set_settings


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()


def _now_code(secret, offset=0):
    return totp.code_at(secret, int(time.time() // totp.PERIOD) + offset)


def test_rfc6238_vector():
    # RFC 6238 ilova B: kalit "12345678901234567890", T=59 → 94287082 (8 xona) → 287082
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp.code_at(secret, 59 // 30) == "287082"
    assert totp.verify(secret, "287 082", now=59) == 1
    assert totp.verify(secret, "287082", now=59, last_step=1) is None  # qayta ishlatib bo'lmaydi
    assert totp.verify(secret, "000000", now=59) is None


def _enable(user):
    secret = totp.new_secret()
    codes, hashes = totp.new_backup_codes()
    user.totp_secret, user.totp_enabled, user.backup_codes = secret, True, hashes
    user.save()
    return secret, codes


def _login(c, user, password=PW):
    return c.post("/login/", {"username": user.username, "password": password},
                  HTTP_HOST=INSPECTOR_HOST)


@pytest.mark.django_db
def test_login_requires_code_when_enabled(inspector):
    secret, _codes = _enable(inspector)
    c = Client()
    r = _login(c, inspector)
    assert r.status_code == 302 and r["Location"].endswith("/login/2fa/")
    assert r.wsgi_request.user.is_anonymous  # parol yetarli emas
    assert c.get("/", HTTP_HOST=INSPECTOR_HOST).wsgi_request.user.is_anonymous
    r = c.post("/login/2fa/", {"code": "111111"}, HTTP_HOST=INSPECTOR_HOST)
    assert r.wsgi_request.user.is_anonymous and "Kod noto" in r.content.decode()
    r = c.post("/login/2fa/", {"code": _now_code(secret)}, HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 302 and r.wsgi_request.user.is_authenticated
    inspector.refresh_from_db()
    assert inspector.totp_last_step > 0
    # Xuddi shu kod bilan ikkinchi kirish — qabul qilinmaydi (replay)
    c2 = Client()
    _login(c2, inspector)
    r = c2.post("/login/2fa/", {"code": totp.code_at(secret, inspector.totp_last_step)},
                HTTP_HOST=INSPECTOR_HOST)
    assert r.wsgi_request.user.is_anonymous


@pytest.mark.django_db
def test_backup_code_is_single_use(inspector):
    _secret, codes = _enable(inspector)
    c = Client()
    _login(c, inspector)
    r = c.post("/login/2fa/", {"code": codes[0].lower()}, HTTP_HOST=INSPECTOR_HOST)
    assert r.wsgi_request.user.is_authenticated
    inspector.refresh_from_db()
    assert len(inspector.backup_codes) == 7
    c2 = Client()
    _login(c2, inspector)
    r = c2.post("/login/2fa/", {"code": codes[0]}, HTTP_HOST=INSPECTOR_HOST)
    assert r.wsgi_request.user.is_anonymous


@pytest.mark.django_db
def test_too_many_wrong_codes_resets_login(inspector):
    _enable(inspector)
    c = Client()
    _login(c, inspector)
    for _ in range(5):
        r = c.post("/login/2fa/", {"code": "000000"}, HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 302 and r["Location"].endswith("/login/")
    assert c.get("/login/2fa/", HTTP_HOST=INSPECTOR_HOST)["Location"].endswith("/login/")


@pytest.mark.django_db
def test_2fa_page_without_password_step_redirects():
    r = Client().get("/login/2fa/")
    assert r.status_code == 302 and r["Location"].endswith("/login/")


@pytest.mark.django_db
def test_enroll_flow_and_disable(iclient, inspector):
    r = iclient.get("/profil/2fa/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200 and "<svg" in r.content.decode()
    secret = iclient.session["2fa_pending_secret"]
    iclient.post("/profil/2fa/", {"action": "enable", "code": "123123"}, HTTP_HOST=INSPECTOR_HOST)
    inspector.refresh_from_db()
    assert not inspector.totp_enabled
    r = iclient.post("/profil/2fa/", {"action": "enable", "code": _now_code(secret)},
                     HTTP_HOST=INSPECTOR_HOST)
    html = r.content.decode()
    inspector.refresh_from_db()
    assert inspector.totp_enabled and inspector.totp_secret == secret
    assert len(inspector.backup_codes) == 8 and "Zaxira kodlar" in html
    # O'chirish — joriy kod bilan (keyingi vaqt qadami, oldingisi ishlatilgan)
    iclient.post("/profil/2fa/", {"action": "disable", "code": _now_code(secret, 1)},
                 HTTP_HOST=INSPECTOR_HOST)
    inspector.refresh_from_db()
    assert not inspector.totp_enabled and inspector.totp_secret == ""


@pytest.mark.django_db
def test_policy_forces_staff_enrollment_but_not_sellers(iclient, sclient):
    set_settings(require_2fa_staff=True)
    r = iclient.get("/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 302 and r["Location"] == "/profil/2fa/"
    assert iclient.get("/profil/2fa/", HTTP_HOST=INSPECTOR_HOST).status_code == 200
    assert sclient.get("/", HTTP_HOST="sotuvchi.localhost").status_code == 200  # sotuvchiga emas


@pytest.mark.django_db
def test_policy_blocks_disable(iclient, inspector):
    secret, _ = _enable(inspector)
    set_settings(require_2fa_staff=True)
    iclient.post("/profil/2fa/", {"action": "disable", "code": _now_code(secret)},
                 HTTP_HOST=INSPECTOR_HOST)
    inspector.refresh_from_db()
    assert inspector.totp_enabled


@pytest.mark.django_db
def test_admin_resets_lost_phone_and_toggles_policy(aclient, inspector):
    _enable(inspector)
    aclient.post(f"/foydalanuvchilar/{inspector.pk}/2fa/", HTTP_HOST="panel.localhost")
    inspector.refresh_from_db()
    assert not inspector.totp_enabled and inspector.backup_codes == []
    aclient.post("/sozlamalar/", {"require_2fa_staff_present": "1", "require_2fa_staff": "on"},
                 HTTP_HOST="panel.localhost")
    assert SystemSettings.objects.get().require_2fa_staff is True


@pytest.mark.django_db
def test_ip_block_stops_password_checks(seller, inspector, settings):
    settings.LOGIN_IP_MAX_FAILS = 6
    attacker = Client(REMOTE_ADDR="203.0.113.50")
    for i in range(6):  # turli hisoblarga — har biri hisob chegarasidan past
        user = seller if i % 2 else inspector
        attacker.post("/login/", {"username": user.username, "password": "x"})
    r = attacker.post("/login/", {"username": seller.username, "password": PW})
    assert r.wsgi_request.user.is_anonymous and "Bu qurilmadan" in r.content.decode()
    seller.refresh_from_db()
    assert not seller.is_locked
    assert Client(REMOTE_ADDR="198.51.100.2").post(
        "/login/", {"username": seller.username, "password": PW}).wsgi_request.user.is_authenticated


@pytest.mark.django_db
def test_distributed_attack_still_locks_account(seller):
    cfg = SystemSettings.get_solo()
    total = cfg.login_max_attempts * 5
    for i in range(total):
        Client(REMOTE_ADDR=f"203.0.113.{i + 1}").post(
            "/login/", {"username": seller.username, "password": "x"})
    seller.refresh_from_db()
    assert seller.is_locked
