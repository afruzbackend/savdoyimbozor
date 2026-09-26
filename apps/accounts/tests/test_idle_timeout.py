"""Xodim uzoq faol bo'lmasa tizimdan chiqariladi; sotuvchiga qo'llanmaydi."""

import time

import pytest

from conftest import INSPECTOR_HOST, SELLER_HOST


def _age_session(client, seconds):
    s = client.session
    s["idle_last"] = int(time.time()) - seconds
    s.save()


@pytest.mark.django_db
def test_staff_logged_out_after_idle(iclient, settings):
    settings.STAFF_IDLE_MINUTES = 120
    assert iclient.get("/", HTTP_HOST=INSPECTOR_HOST).status_code == 200
    _age_session(iclient, 121 * 60)
    r = iclient.get("/signallar/?level=red", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 302 and r["Location"].startswith("/login/?timeout=1&next=/signallar/%3Flevel%3Dred")
    assert iclient.get("/", HTTP_HOST=INSPECTOR_HOST).wsgi_request.user.is_anonymous
    page = iclient.get("/login/?timeout=1").content.decode()
    assert "faollik bo" in page


@pytest.mark.django_db
def test_active_staff_stays_and_api_gets_401(iclient, settings):
    settings.STAFF_IDLE_MINUTES = 120
    iclient.get("/", HTTP_HOST=INSPECTOR_HOST)
    _age_session(iclient, 100 * 60)  # 100 daqiqa — hali chegarada emas
    assert iclient.get("/", HTTP_HOST=INSPECTOR_HOST).status_code == 200
    _age_session(iclient, 3 * 3600)
    r = iclient.get("/", HTTP_HOST=INSPECTOR_HOST, HTTP_HX_REQUEST="true")
    assert r.status_code == 401


@pytest.mark.django_db
def test_seller_not_affected(sclient, settings):
    settings.STAFF_IDLE_MINUTES = 120
    _age_session(sclient, 10 * 3600)
    assert sclient.get("/", HTTP_HOST=SELLER_HOST).status_code == 200


@pytest.mark.django_db
def test_disabled_with_zero(iclient, settings):
    settings.STAFF_IDLE_MINUTES = 0
    _age_session(iclient, 10 * 3600)
    assert iclient.get("/", HTTP_HOST=INSPECTOR_HOST).status_code == 200
