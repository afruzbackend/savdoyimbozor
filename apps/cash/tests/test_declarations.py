"""Soliq / onlayn kassa integratsiyasi: manba ustuvorligi, do'konga bog'lash, adapterlar, sinxron."""

import datetime
import io
import json
import urllib.error

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.analytics.models import Alert, DailyScore
from apps.analytics.scoring.services import recompute_for_date
from apps.cash.adapters import AdapterError
from apps.cash.adapters.base import parse_amount, parse_date
from apps.cash.adapters.http import HttpJsonAdapter
from apps.cash.models import CashRecord, DeclarationSync
from apps.cash.services import Declaration, declared_for, ingest
from apps.cash.sync import run_sync
from apps.sales.models import Sale
from apps.shops.models import Shop


def _yesterday():
    return timezone.localdate() - datetime.timedelta(days=1)


def _sale(shop, total, day):
    s = Sale.objects.create(shop=shop, total=total, subtotal=total, payment_type="cash")
    at = timezone.make_aware(datetime.datetime.combine(day, datetime.time(12)))
    Sale.objects.filter(pk=s.pk).update(created_at=at)
    return s


# ---------- Manba ustuvorligi: summalar QO'SHILMAYDI ----------

@pytest.mark.django_db
def test_sources_are_not_summed_most_reliable_wins(shop):
    day = _yesterday()
    CashRecord.objects.create(shop=shop, date=day, amount=100_000, source="excel")
    CashRecord.objects.create(shop=shop, date=day, amount=300_000, source="tax_api")
    assert declared_for(shop, day) == 300_000  # 400 000 emas
    _sale(shop, 300_000, day)
    recompute_for_date(day)
    assert DailyScore.objects.get(shop=shop, date=day).cash_amount == 300_000


# ---------- Do'konga bog'lash ----------

@pytest.mark.django_db
def test_ingest_resolves_shops_and_aggregates_receipts(shop, market):
    day = _yesterday()
    twin_a = Shop.objects.create(market=market, number="21", stir="555", fiscal_id="FM-A")
    twin_b = Shop.objects.create(market=market, number="22", stir="555")
    rows = [
        Declaration(stir=shop.stir, date=day, amount=40_000),  # yagona do'kon — STIR yetarli
        Declaration(stir=shop.stir, date=day, amount=60_000),  # shu kunning 2-cheki → jamlanadi
        Declaration(stir="555", date=day, amount=10_000, fiscal_id="fm-a"),  # FM bo'yicha
        Declaration(stir="555", date=day, amount=7_000, shop_number="22"),  # STIR + raqam
        Declaration(stir="555", date=day, amount=1),  # noaniq: 2 do'kon, FM yo'q
        Declaration(stir="999", date=day, amount=1),  # tizimda yo'q
        Declaration(stir=shop.stir, date=timezone.localdate() + datetime.timedelta(days=2),
                    amount=1),  # kelajak
    ]
    res = ingest(rows, "tax_api")
    assert (res.fetched, res.saved, res.unmatched) == (7, 3, 3)
    assert CashRecord.objects.get(shop=shop, date=day, source="tax_api").amount == 100_000
    assert CashRecord.objects.get(shop=twin_a, source="tax_api").amount == 10_000
    assert CashRecord.objects.get(shop=twin_b, source="tax_api").amount == 7_000
    assert any("kassa raqami" in p for p in res.problems)
    # Qayta sinxronlash qo'shmaydi — almashtiradi
    ingest([Declaration(stir=shop.stir, date=day, amount=90_000)], "tax_api")
    assert CashRecord.objects.get(shop=shop, date=day, source="tax_api").amount == 90_000


def test_parse_amount_and_date():
    assert parse_amount("1 234 567") == 1234567
    assert parse_amount("1,234,567") == 1234567
    assert parse_amount("1234567.50") == 1234568
    assert parse_amount("12,5") == 13
    assert parse_amount(123456700, divisor=100) == 1234567
    with pytest.raises(AdapterError):
        parse_amount("abc")
    assert parse_date("24.09.2026") == datetime.date(2026, 9, 24)
    assert parse_date("2026-09-24") == datetime.date(2026, 9, 24)
    # UTC 21:30 — Toshkentda (UTC+5) ertasi kun
    assert parse_date("2026-09-24T21:30:00Z") == datetime.date(2026, 9, 25)


# ---------- Inbox (papka) adapteri ----------

@pytest.mark.django_db
def test_inbox_sync_writes_moves_files_and_recomputes(shop, settings, tmp_path):
    settings.TAX_ADAPTER = "inbox"
    settings.TAX_INBOX_DIR = str(tmp_path / "inbox")
    day = _yesterday()
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.csv").write_bytes(
        ("﻿INN;Sana;Summa\n" f"{shop.stir};{day:%d.%m.%Y};150 000\n"
         f"{shop.stir};buzuq;1\n").encode()
    )
    (inbox / "b.json").write_text(json.dumps([{"stir": "404", "date": day.isoformat(), "amount": 5}]))
    (inbox / "c.json").write_text("{buzuq")
    _sale(shop, 150_000, day)

    entry = run_sync()
    assert entry.ok
    assert CashRecord.objects.get(shop=shop, date=day, source="tax_api").amount == 150_000
    assert entry.saved == 1 and entry.unmatched == 3  # buzuq sana + noma'lum STIR + buzuq fayl
    assert sorted(p.name.split("-", 2)[-1] for p in (inbox / "processed").iterdir()) == ["a.csv", "b.json"]
    assert [p.name.split("-", 2)[-1] for p in (inbox / "failed").iterdir()] == ["c.json"]
    assert not list(inbox.glob("*.csv"))
    # Rostlik yangi deklaratsiya bilan qayta hisoblandi
    assert DailyScore.objects.get(shop=shop, date=day).cash_amount == 150_000


# ---------- HTTP adapter ----------

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.django_db
def test_http_adapter_pages_mapping_and_tiyin(shop, settings, monkeypatch):
    settings.TAX_API_URL = "https://soliq.example/api/decl"
    settings.TAX_API_TOKEN = "t0k"
    settings.TAX_API_FIELDS = "stir=tin,amount=receipt.total,date=day"
    settings.TAX_API_AMOUNT_DIVISOR = 100
    day = _yesterday()
    pages = {
        "first": {"results": [{"tin": shop.stir, "day": day.isoformat(), "receipt": {"total": 5_000_000}}],
                  "next": "/api/decl?page=2"},
        "second": [{"tin": shop.stir, "day": day.isoformat(), "receipt": {"total": 2_500_000}},
                   {"tin": shop.stir, "day": "?", "receipt": {"total": 1}}],
    }
    seen = []

    def fake_urlopen(req, timeout):
        seen.append((req.full_url, req.headers.get("Authorization")))
        return _Resp(json.dumps(pages["second" if "page=2" in req.full_url else "first"]).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    entry = run_sync(day, day, adapter=HttpJsonAdapter())
    assert entry.ok, entry.message
    assert CashRecord.objects.get(shop=shop, date=day, source="tax_api").amount == 75_000
    assert entry.unmatched == 1  # buzuq sana
    assert "date_from=" in seen[0][0] and seen[1][0] == "https://soliq.example/api/decl?page=2"
    assert all(auth == "Bearer t0k" for _u, auth in seen)


@pytest.mark.django_db
def test_http_adapter_errors_are_logged_not_raised(settings, monkeypatch):
    settings.TAX_API_URL = "https://soliq.example/api/decl"

    def denied(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", denied)
    entry = run_sync(_yesterday(), _yesterday(), adapter=HttpJsonAdapter())
    assert not entry.ok and "TAX_API_TOKEN" in entry.message
    # Token begona hostga yuborilmaydi
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda req, timeout: _Resp(b'{"results": [], "next": "https://evil.example/x"}'))
    entry = run_sync(_yesterday(), _yesterday(), adapter=HttpJsonAdapter())
    assert not entry.ok and "boshqa host" in entry.message


def test_http_adapter_requires_https(settings):
    settings.DEBUG = False
    settings.TAX_API_URL = "http://soliq.example/api"
    with pytest.raises(AdapterError):
        HttpJsonAdapter()


# ---------- Kechikkan ma'lumot eski signalni tozalaydi ----------

@pytest.mark.django_db
def test_late_declaration_dismisses_stale_alert(shop, inspector):
    day = _yesterday()
    _sale(shop, 500_000, day)
    CashRecord.objects.create(shop=shop, date=day, amount=100_000, source="excel")
    recompute_for_date(day)
    alert = Alert.objects.get(shop=shop, date=day, kind="truth")
    assert alert.status == "new" and alert.level == "red"
    # 04:15 — Soliqdan to'liq deklaratsiya keldi: do'kon halol
    ingest([Declaration(stir=shop.stir, date=day, amount=500_000)], "tax_api")
    recompute_for_date(day)
    alert.refresh_from_db()
    assert alert.status == "dismissed" and "bekor qilindi" in alert.reason
    # Inspektor ish boshlagan signal o'zgartirilmaydi
    alert.status = "assigned"
    alert.save()
    recompute_for_date(day)
    alert.refresh_from_db()
    assert alert.status == "assigned"


# ---------- Buyruq va panel ----------

@pytest.mark.django_db
def test_command_and_panel_when_not_configured(aclient, settings):
    settings.TAX_ADAPTER = ""
    out = io.StringIO()
    call_command("sync_declarations", stdout=out)
    assert "sozlanmagan" in out.getvalue()
    r = aclient.get("/import/kassa/", HTTP_HOST="panel.localhost")
    assert r.status_code == 200 and "sozlanmagan" in r.content.decode()
    r = aclient.post("/import/kassa/soliq/", HTTP_HOST="panel.localhost", follow=True)
    assert "sozlanmagan" in r.content.decode()
    assert not DeclarationSync.objects.exists()


@pytest.mark.django_db
def test_panel_sync_button_with_inbox(aclient, shop, settings, tmp_path):
    settings.TAX_ADAPTER = "inbox"
    settings.TAX_INBOX_DIR = str(tmp_path / "in")
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "d.csv").write_text(f"stir,date,amount\n{shop.stir},{_yesterday()},9000\n")
    r = aclient.post("/import/kassa/soliq/", HTTP_HOST="panel.localhost", follow=True)
    assert r.status_code == 200
    assert CashRecord.objects.filter(shop=shop, source="tax_api", amount=9000).exists()
    page = aclient.get("/import/kassa/", HTTP_HOST="panel.localhost").content.decode()
    assert "ishlamoqda" in page


@pytest.mark.django_db
def test_shop_fiscal_id_unique_in_panel(aclient, shop, market):
    other = Shop.objects.create(market=market, number="31", stir="31", fiscal_id="FM-9")
    data = {"owner_name": shop.owner_name, "stir": shop.stir, "number": shop.number,
            "category": shop.category_id, "fiscal_id": "fm-9", "is_active": "on"}
    aclient.post(f"/dokon/{shop.pk}/", data, HTTP_HOST="panel.localhost")
    shop.refresh_from_db()
    assert shop.fiscal_id == ""  # band raqam berilmaydi
    other.fiscal_id = ""
    other.save()
    aclient.post(f"/dokon/{shop.pk}/", data, HTTP_HOST="panel.localhost")
    shop.refresh_from_db()
    assert shop.fiscal_id == "FM-9"


def test_parse_amount_export_formats():
    assert parse_amount("1.234.567") == 1234567
    assert parse_amount("1,250,000.00") == 1250000
    assert parse_amount("1.250.000,50") == 1250001
    assert parse_amount("1 250 000 so'm") == 1250000
    assert parse_amount("1250000 UZS") == 1250000
    assert parse_date(46289) == datetime.date(2026, 9, 24)  # Excel seriya raqami
