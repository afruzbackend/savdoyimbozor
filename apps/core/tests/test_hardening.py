"""Deploy oldi mustahkamlash: API chegarasi, til faqat tanlovdan, mahsulot turi katalogdan, prod'da API
faqat JSON, preflight tekshiruvi, statistika agregati."""

import datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.catalog.models import Product, ProductCategory, ShopCategory
from conftest import INSPECTOR_HOST, SELLER_HOST


def test_api_throttling_configured():
    from django.conf import settings

    rf = settings.REST_FRAMEWORK
    assert "rest_framework.throttling.UserRateThrottle" in rf["DEFAULT_THROTTLE_CLASSES"]
    assert {"user", "anon", "camera"} <= set(rf["DEFAULT_THROTTLE_RATES"])


def test_camera_throttle_is_per_token_not_per_ip():
    from django.test import RequestFactory

    from apps.api.throttles import CameraRateThrottle

    t = CameraRateThrottle()
    a = RequestFactory().post("/api/events/", HTTP_X_CAMERA_TOKEN="aaa", REMOTE_ADDR="10.0.0.1")
    b = RequestFactory().post("/api/events/", HTTP_X_CAMERA_TOKEN="bbb", REMOTE_ADDR="10.0.0.1")
    assert t.get_cache_key(a, None) != t.get_cache_key(b, None)  # bitta NAT ortidagi ikki kamera
    assert "aaa" not in t.get_cache_key(a, None)  # token keshda ochiq saqlanmaydi


@pytest.mark.django_db
def test_user_api_rate_limit_returns_429(sclient, settings):
    from django.core.cache import cache
    from rest_framework.settings import api_settings
    from rest_framework.throttling import UserRateThrottle

    cache.clear()
    old = UserRateThrottle.THROTTLE_RATES
    UserRateThrottle.THROTTLE_RATES = {**api_settings.DEFAULT_THROTTLE_RATES, "user": "3/min"}
    try:
        codes = [
            sclient.get("/api/sales/today/", HTTP_HOST=SELLER_HOST).status_code for _ in range(5)
        ]
    finally:
        UserRateThrottle.THROTTLE_RATES = old
    assert codes[:3] == [200, 200, 200] and codes[-1] == 429


def test_offline_queue_retries_on_429():
    from pathlib import Path

    from django.conf import settings

    js = (Path(settings.BASE_DIR) / "static/js/components.js").read_text(encoding="utf-8")
    assert "r.status === 429" in js and "rest.concat(q.slice(i))" in js


@pytest.mark.django_db
def test_server_language_ignores_browser_accept_language(iclient, shop):
    """Brauzer ruscha bo'lsa ham o'zbekcha interfeysda sana ruscha chiqmasin."""
    from apps.analytics.models import Alert

    Alert.objects.create(shop=shop, date=datetime.date(2026, 9, 24), level="red", reason="test")
    html = iclient.get(
        f"/dokon/{shop.pk}/", HTTP_HOST=INSPECTOR_HOST, HTTP_ACCEPT_LANGUAGE="ru-RU,ru;q=0.9"
    ).content
    assert "сентябр".encode() not in html
    iclient.cookies["django_language"] = "ru"  # foydalanuvchi o'zi rus tilini tanlagan
    r = iclient.get("/", HTTP_HOST=INSPECTOR_HOST)
    assert r.headers.get("Content-Language") == "ru"


@pytest.mark.django_db
def test_seller_cannot_pick_product_type_of_other_shop_type(sclient, shop):
    other = ProductCategory.objects.create(
        name="Kurtka", shop_category=ShopCategory.objects.create(name="Kiyim")
    )
    own = ProductCategory.objects.create(name="Olma", shop_category=shop.category)
    sclient.post(
        "/mahsulotlar/",
        {"category": other.pk, "unit": "piece", "sell_price": "5000"},
        HTTP_HOST=SELLER_HOST,
    )
    assert not Product.objects.filter(shop=shop, category=other).exists()
    sclient.post(
        "/mahsulotlar/",
        {"category": own.pk, "unit": "kg", "sell_price": "5000"},
        HTTP_HOST=SELLER_HOST,
    )
    assert Product.objects.filter(shop=shop, category=own).exists()


def test_prod_api_is_json_only(monkeypatch):
    import importlib
    import sys

    monkeypatch.setenv("SECRET_KEY", "x" * 60)
    saved = {
        k: sys.modules.pop(k)
        for k in ("config.settings.prod", "config.settings.base")
        if k in sys.modules
    }
    try:
        prod = importlib.import_module("config.settings.prod")
    finally:
        sys.modules.pop("config.settings.prod", None)
        sys.modules.update(saved)
    assert prod.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] == [
        "rest_framework.renderers.JSONRenderer"
    ]
    assert prod.DEBUG is False and prod.SESSION_COOKIE_SECURE


@pytest.mark.django_db
def test_preflight_fails_on_demo_password(shop):
    from apps.accounts.models import Role, User

    u = User.objects.create(
        username="admin", role=Role.SUPERADMIN, is_staff=True, is_superuser=True
    )
    u.set_password("demo1234")
    u.save()
    with pytest.raises(SystemExit) as e:
        call_command("preflight", "--allow-http")
    assert e.value.code == 1


@pytest.mark.django_db
def test_statistics_aggregates_in_db(iclient, shop):
    from apps.analytics.models import DailyScore

    today = timezone.localdate()
    for d, t in ((25, 40), (1, 80)):  # birinchi va ikkinchi yarim
        DailyScore.objects.create(
            shop=shop,
            date=today - datetime.timedelta(days=d),
            truth_pct=t,
            entered_sales=1000,
            cash_amount=500,
            measured=True,
            parts={"cash": t},
        )
    r = iclient.get("/statistika/", HTTP_HOST=INSPECTOR_HOST)
    row = r.context["rows"][0]
    assert (
        row["shop"] == shop
        and row["entered"] == 2000
        and row["avg_truth"] == 60
        and row["trend"] == 40
    )
