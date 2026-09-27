"""To'liq tekshiruv (3): e'tibordan chetda qolganlar — aralash do'kon raqamlari, sotuvchi hisobotidagi
rostlik, xorijiy telefon, eski raqamlar, Excel importda noto'g'ri telefon, Django admin'da dalillar
o'zgarmasligi, CSRF-xavfsiz chiqish, sessiyalarni tozalash, Excel hajmi."""

import datetime
import importlib

import pytest
from django.contrib import admin
from django.test import RequestFactory
from django.utils import timezone

from apps.analytics.models import DailyScore
from apps.core.format import clean_phone
from apps.shops.models import Shop
from conftest import INSPECTOR_HOST, SELLER_HOST

PANEL_HOST = "panel.localhost"
VOL = {"cash": 70, "camera": None, "stock": None, "price": 100}


def _score(shop, days_ago, truth):
    return DailyScore.objects.create(
        shop=shop,
        date=timezone.localdate() - datetime.timedelta(days=days_ago),
        truth_pct=truth,
        entered_sales=100000,
        cash_amount=70000,
        parts=VOL,
        measured=True,
    )


@pytest.mark.django_db
def test_map_with_letter_and_digit_numbers_does_not_crash(iclient, shop):
    """ "A12" va "9" bir qatorda — ilgari tartiblashda int bilan str to'qnashib 500 bo'lardi."""
    for n in ("A12", "9", "12B", "10"):
        Shop.objects.create(
            market=shop.market, row=shop.row, category=shop.category, number=n, stir="1" * 9
        )
    r = iclient.get("/xarita/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200
    assert [s["number"] for s in r.context["rows_data"][0]["stalls"]] == [
        "1",
        "9",
        "10",
        "12B",
        "A12",
    ]


@pytest.mark.django_db
def test_seller_report_uses_recent_days_and_real_average_check(sclient, shop, seller):
    from apps.sales.models import Sale

    _score(shop, 2, 67)
    Sale.objects.create(shop=shop, seller=seller, subtotal=30000, total=30000, payment_type="cash")
    Sale.objects.create(shop=shop, seller=seller, subtotal=10000, total=10000, payment_type="cash")
    r = sclient.get("/hisobot/", HTTP_HOST=SELLER_HOST)
    assert r.context["recent"]["truth"] == 67 and r.context["level"] == "yellow"
    html = r.content.decode()
    assert "O&#x27;rtacha chek" in html or "O'rtacha chek" in html
    assert r.context["metrics"]["avg_check"] == 20000
    assert "Jami cheklar" not in html  # "Sotuvlar soni" bilan bir xil raqam takrorlanardi


@pytest.mark.parametrize(
    "raw,out",
    [
        ("+7 701 123 45 67", "+77011234567"),  # Qozog'iston
        ("+996 555 123 456", "+996555123456"),  # Qirg'iziston
        ("+1 23", None),
        ("+998 90 12", None),
    ],
)
def test_clean_phone_accepts_foreign_numbers(raw, out):
    assert clean_phone(raw) == out


@pytest.mark.django_db
def test_old_phones_are_normalized_by_migration(shop, seller):
    shop.owner_phone = "+998909586960"
    shop.save(update_fields=["owner_phone"])
    seller.phone = "90 123 45 67"
    seller.save(update_fields=["phone"])
    from django.apps import apps

    importlib.import_module("apps.core.migrations.0014_normalize_phones").forwards(apps, None)
    shop.refresh_from_db()
    seller.refresh_from_db()
    assert shop.owner_phone == "+998 90 958 69 60" and seller.phone == "+998 90 123 45 67"


@pytest.mark.django_db
def test_excel_import_keeps_shop_when_phone_is_bad(aclient, market):
    from apps.catalog.models import ShopCategory
    from apps.core.tests.test_imports import _xlsx

    cat = ShopCategory.objects.create(name="Meva")
    f = _xlsx([["Raqam", "STIR", "Egasi", "Telefon"], ["201", "111222333", "Ali", "90-12"]])
    r = aclient.post(
        "/import/dokonlar/",
        {"market": market.pk, "file": f, "category": cat.pk},
        HTTP_HOST=PANEL_HOST,
        follow=True,
    )
    sh = Shop.objects.get(number="201")
    assert sh.owner_phone == ""
    assert "Telefon noto" in r.content.decode()


def test_evidence_is_read_only_in_django_admin():
    from apps.analytics.models import Alert, DailyScore, Inspection
    from apps.cash.models import CashRecord
    from apps.core.models import AuditLog
    from apps.sales.models import Correction, Sale, StockIn, WriteOff

    req = RequestFactory().get("/")
    req.user = type(
        "U",
        (),
        {"is_active": True, "is_staff": True, "is_superuser": True, "has_perm": lambda *a: True},
    )()
    for model in (
        Sale,
        StockIn,
        WriteOff,
        Correction,
        CashRecord,
        Inspection,
        Alert,
        DailyScore,
        AuditLog,
    ):
        ma = admin.site._registry[model]
        assert not ma.has_change_permission(req) and not ma.has_delete_permission(
            req
        ), model.__name__
        assert not ma.has_add_permission(req), model.__name__


@pytest.mark.django_db
def test_logout_requires_post(sclient):
    r = sclient.get("/logout/", HTTP_HOST=SELLER_HOST)
    assert r.status_code == 302
    assert sclient.get("/", HTTP_HOST=SELLER_HOST).status_code == 200  # GET bilan chiqarilmadi
    sclient.post("/logout/", HTTP_HOST=SELLER_HOST)
    assert sclient.get("/", HTTP_HOST=SELLER_HOST).status_code in (302, 200)
    assert "_auth_user_id" not in sclient.session


@pytest.mark.django_db
def test_pricing_config_via_json_script(sclient):
    html = sclient.get("/sotuv/", HTTP_HOST=SELLER_HOST).content.decode()
    assert 'id="pricing-config"' in html and "pricing_config|safe" not in html


def test_sessions_cleared_nightly():
    from config.celery import app

    assert any(
        v["task"] == "apps.core.tasks.clear_sessions" for v in app.conf.beat_schedule.values()
    )


@pytest.mark.django_db
def test_excel_size_limit(aclient, market):
    from django.core.files.uploadedfile import SimpleUploadedFile

    big = SimpleUploadedFile("f.xlsx", b"0" * (10 * 1024 * 1024 + 1))
    r = aclient.post(
        "/import/dokonlar/", {"market": market.pk, "file": big}, HTTP_HOST=PANEL_HOST, follow=True
    )
    assert "juda katta" in r.content.decode()
