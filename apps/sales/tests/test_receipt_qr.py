"""Xaridorga QR chek: ochiq sahifa, QR, xaridor xabari → signal, suiiste'moldan himoya."""

import datetime

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from conftest import SELLER_HOST


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


def _sell(sclient, total=50_000):
    r = sclient.post("/api/sales/", {"items": [{"name": "Olma", "qty": 2, "unit_price": total // 2}],
                                     "payment_type": "cash"},
                     content_type="application/json", HTTP_HOST=SELLER_HOST)
    assert r.status_code == 201, r.content
    return r.json()


@pytest.mark.django_db
def test_sale_returns_receipt_and_public_page_works(sclient, shop):
    d = _sell(sclient)
    code = d["receipt_code"]
    assert len(code) == 10 and d["receipt_url"].endswith(f"/chek/{code}/")
    anon = Client()
    r = anon.get(f"/chek/{code}/")
    html = r.content.decode().replace(" ", " ")  # ming ajratgich — bo'linmas bo'shliq
    assert r.status_code == 200
    assert "50 000" in html and "Olma" in html and f"№{shop.number}" in html
    assert "noindex" in html and "fiskal chek emas" in html
    qr = anon.get(f"/chek/{code}/qr.svg")
    assert qr.status_code == 200 and qr["Content-Type"] == "image/svg+xml"
    assert b"<svg" in qr.content
    # Kichik harf bilan terilsa ham ochiladi, noto'g'ri kod — 404
    assert anon.get(f"/chek/{code.lower()}/").status_code == 200
    assert anon.get("/chek/AAAAAAAAAA/").status_code == 404
    assert anon.get("/chek/../../etc/").status_code == 404


@pytest.mark.django_db
def test_public_base_url_used_in_qr(sclient, settings):
    settings.PUBLIC_BASE_URL = "https://bozor.soliq.uz/"
    d = _sell(sclient)
    assert d["receipt_url"] == f"https://bozor.soliq.uz/chek/{d['receipt_code']}/"


@pytest.mark.django_db
def test_buyer_overpaid_report_creates_red_alert_once(sclient, shop, inspector):
    from apps.analytics.models import Alert
    from apps.sales.models import ReceiptReport

    code = _sell(sclient)["receipt_code"]
    anon = Client()
    r = anon.post(f"/chek/{code}/xabar/", {"paid_amount": "80 000", "comment": "3 kg oldim"})
    assert r.status_code == 302 and r["Location"].endswith("?sent=1")
    rep = ReceiptReport.objects.get()
    assert rep.paid_amount == 80_000 and rep.alert is not None
    a = Alert.objects.get(kind="buyer_report")
    assert a.level == "red" and a.assigned_to == inspector and "+30 000" in a.reason
    # Ikkinchi xabar qabul qilinmaydi (chekka bitta)
    anon.post(f"/chek/{code}/xabar/", {"paid_amount": "90000"})
    assert ReceiptReport.objects.count() == 1 and Alert.objects.filter(kind="buyer_report").count() == 1
    assert "xabaringiz qabul qilindi" in anon.get(f"/chek/{code}/").content.decode()


@pytest.mark.django_db
def test_small_gap_or_underpay_is_recorded_without_alert(sclient):
    from apps.analytics.models import Alert
    from apps.sales.models import ReceiptReport

    a = _sell(sclient, 50_000)["receipt_code"]
    b = _sell(sclient, 40_000)["receipt_code"]
    Client().post(f"/chek/{a}/xabar/", {"paid_amount": "51000"})  # yaxlitlash darajasidagi farq
    Client().post(f"/chek/{b}/xabar/", {"paid_amount": "30000"})  # kam to'lagan — soliqqa zarar yo'q
    assert ReceiptReport.objects.count() == 2
    assert not Alert.objects.filter(kind="buyer_report").exists()


@pytest.mark.django_db
def test_report_validation_window_and_throttle(sclient, settings):
    from apps.sales.models import ReceiptReport, Sale

    code = _sell(sclient)["receipt_code"]
    anon = Client()
    assert anon.post(f"/chek/{code}/xabar/", {"paid_amount": "abc"}).status_code == 400
    assert anon.post(f"/chek/{code}/xabar/", {"paid_amount": "-5"}).status_code == 400
    # Muddati o'tgan chek
    Sale.objects.filter(public_code=code).update(
        created_at=timezone.now() - datetime.timedelta(days=settings.RECEIPT_REPORT_DAYS + 1))
    anon.post(f"/chek/{code}/xabar/", {"paid_amount": "90000"})
    assert not ReceiptReport.objects.exists()
    assert "muddati tugagan" in anon.get(f"/chek/{code}/").content.decode()
    # Bitta manzildan ko'p urinish — 429
    codes = [_sell(sclient)["receipt_code"] for _ in range(3)]
    cache.set("receipt-report:127.0.0.1", 10, 3600)
    assert anon.post(f"/chek/{codes[0]}/xabar/", {"paid_amount": "90000"}).status_code == 429


@pytest.mark.django_db
def test_home_recent_sales_have_qr_buttons(sclient):
    code = _sell(sclient)["receipt_code"]
    html = sclient.get("/", HTTP_HOST=SELLER_HOST).content.decode()
    assert f'data-receipt-qr="/chek/{code}/qr.svg"' in html


@pytest.mark.django_db
def test_prosecutor_is_never_assigned_alerts(sclient, market, inspector):
    """Prokuror ham bozorga biriktirilgan bo'lsa ham signal tekshiruvchiga beriladi."""
    from apps.accounts.services import create_prosecutor
    from apps.analytics.models import Alert

    pros = create_prosecutor("Kuzatuvchi", [market])["user"]
    assert market.duty_inspector() == inspector
    code = _sell(sclient)["receipt_code"]
    Client().post(f"/chek/{code}/xabar/", {"paid_amount": "90000"})
    assert Alert.objects.get(kind="buyer_report").assigned_to != pros
