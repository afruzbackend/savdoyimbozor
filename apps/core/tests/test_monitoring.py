"""Monitoring: /healthz/ (ochiq — minimal, token/admin — batafsil), xato yuborishda tozalash."""

import pytest
from django.test import Client

from apps.core import health, monitoring


@pytest.mark.django_db
def test_public_healthz_is_minimal_and_cheap(django_assert_max_num_queries):
    with django_assert_max_num_queries(2):
        r = Client().get("/healthz/")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r["Cache-Control"] == "no-store"
    assert Client().get("/prefs/healthz/").status_code == 200  # eski manzil ham ishlaydi


@pytest.mark.django_db
def test_detailed_with_token_or_admin(settings, aclient):
    settings.HEALTH_TOKEN = "s3cret"
    r = Client().get("/healthz/", HTTP_X_HEALTH_TOKEN="s3cret")
    names = {c["name"] for c in r.json()["checks"]}
    assert {"database", "cache", "disk", "backup", "celery", "cameras", "tax_sync", "sms"} <= names
    assert "checks" not in Client().get("/healthz/", HTTP_X_HEALTH_TOKEN="wrong").json()
    assert "checks" in aclient.get("/healthz/", HTTP_HOST="panel.localhost").json()


@pytest.mark.django_db
def test_database_failure_gives_503(monkeypatch):
    def boom():
        raise RuntimeError("db yo'q")

    monkeypatch.setattr(health, "CHECKS", [("database", boom)] + health.CHECKS[1:])
    r = Client().get("/healthz/")
    assert r.status_code == 503 and r.json()["status"] == "fail"


@pytest.mark.django_db
def test_warnings_are_degraded_not_down(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    data = health.run(full=True)  # beat yurak urishi yo'q, zaxira olinmagan → ogohlantirish
    assert data["status"] == "degraded"
    health.beat()
    assert next(c for c in health.run()["checks"] if c["name"] == "celery")["status"] == "ok"


@pytest.mark.django_db
def test_panel_dashboard_shows_health(aclient):
    html = aclient.get("/", HTTP_HOST="panel.localhost").content.decode()
    assert "Tizim holati" in html and "health-item" in html


def test_scrub_removes_secrets_before_sending():
    event = {
        "request": {"data": {"username": "700001", "password": "P@ss", "code": "123456"},
                    "headers": {"Authorization": "Bearer x", "X-Camera-Token": "cam", "Host": "h"},
                    "cookies": {"sessionid": "abc"}, "query_string": "token=1"},
        "exception": {"values": [{"stacktrace": {"frames": [
            {"vars": {"totp_secret": "JBSW", "visible_password": "p", "shop": "№1"}}]}}]},
        "extra": {"api_key": "k", "nested": {"csrf": "t", "ok": 1}},
    }
    out = monitoring.before_send(event)
    req = out["request"]
    assert req["data"]["username"] == "700001"
    assert req["data"]["password"] == req["data"]["code"] == monitoring.MASK
    assert req["headers"]["Authorization"] == req["headers"]["X-Camera-Token"] == monitoring.MASK
    assert req["headers"]["Host"] == "h"
    assert req["cookies"]["sessionid"] == monitoring.MASK
    frame = out["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]
    assert frame["totp_secret"] == frame["visible_password"] == monitoring.MASK
    assert frame["shop"] == "№1"
    assert out["extra"]["api_key"] == monitoring.MASK and out["extra"]["nested"]["ok"] == 1


def test_monitoring_off_without_dsn():
    assert monitoring.init("", environment="test", traces=0.0) is False
