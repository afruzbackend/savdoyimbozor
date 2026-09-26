"""Oflayn navbat: real sotuv yo'qolmaydi va QILINGAN kuniga yoziladi.

23:50 dagi sotuv ertalab yuborilsa kechagi kunga tushadi (bugungiga emas); qoldiq hisobda yetmasa
ham qabul qilinadi (tovar ketib bo'lgan); yopilgan kassa yangilanadi va soxta kassa signali bekor.
"""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.analytics.models import Alert, DailyScore
from apps.analytics.scoring.services import refresh_today_if_stale
from apps.sales.models import RegisterClose, Sale
from conftest import SELLER_HOST


def _post(client, body):
    return client.post("/api/sales/", json.dumps(body), content_type="application/json",
                       HTTP_HOST=SELLER_HOST)


def _body(product, qty=1, price=12_000, **extra):
    b = {"items": [{"product_id": product.pk, "name": product.name, "qty": qty, "unit_price": price}],
         "discount": 0, "rounding": 0, "payment_type": "cash", "mode": "scan"}
    b.update(extra)
    return b


def _yesterday_2350():
    y = timezone.localdate() - timedelta(days=1)
    return timezone.make_aware(timezone.datetime.combine(y, timezone.datetime.min.time())
                               + timedelta(hours=23, minutes=50))


@pytest.mark.django_db
def test_offline_sale_lands_on_the_day_it_happened(sclient, shop, product):
    ts = _yesterday_2350()
    r = _post(sclient, _body(product, offline=True, client_ts=ts.isoformat(), client_uid="u1"))
    assert r.status_code == 201
    sale = Sale.objects.get(client_uid="u1")
    assert timezone.localtime(sale.created_at) == timezone.localtime(ts)  # kechagi kun, 23:50
    assert sale.is_late and sale.note.startswith("Oflayn sotuv")  # iz qoladi
    # Qayta yuborish — dublikat emas
    assert _post(sclient, _body(product, offline=True, client_ts=ts.isoformat(), client_uid="u1")).status_code == 200
    assert Sale.objects.filter(client_uid="u1").count() == 1


@pytest.mark.django_db
def test_offline_sale_accepted_even_if_stock_ran_out(sclient, shop, product):
    product.stock = Decimal("1")
    product.save(update_fields=["stock"])
    assert _post(sclient, _body(product, qty=3)).status_code == 400  # onlayn — qoldiq tekshiriladi
    r = _post(sclient, _body(product, qty=3, offline=True, client_ts=timezone.now().isoformat()))
    assert r.status_code == 201  # tovar qo'ldan ketib bo'lgan — sotuv yo'qolmasin
    product.refresh_from_db()
    assert product.stock == Decimal("-2")  # kun yakuni sanog'ida tuzaladi


@pytest.mark.django_db
def test_too_old_offline_sale_recorded_now_with_device_time_in_note(sclient, shop, product):
    old = timezone.now() - timedelta(days=5)
    r = _post(sclient, _body(product, offline=True, client_ts=old.isoformat(), client_uid="old"))
    assert r.status_code == 201
    sale = Sale.objects.get(client_uid="old")
    assert timezone.localdate(sale.created_at) == timezone.localdate()
    assert "qurilma vaqti" in sale.note


@pytest.mark.django_db
def test_queued_sale_of_other_shop_is_not_booked_here(sclient, shop, product):
    r = _post(sclient, _body(product, offline=True, shop_hint=shop.pk + 999))
    assert r.status_code == 409 and not Sale.objects.exists()


@pytest.mark.django_db
def test_late_sale_fixes_closed_register_and_recomputes_day(sclient, shop, seller, product,
                                                              django_capture_on_commit_callbacks):
    from conftest import set_settings

    set_settings(cash_shortage_pct=15)
    y = timezone.localdate() - timedelta(days=1)
    # Kecha kassa yopilgan: sandiqda 100 000, yozilgan 0 — "ortiqcha" signali
    RegisterClose.objects.create(shop=shop, seller=seller, date=y, expected_cash=0, counted_cash=100_000)
    alert = Alert.objects.create(shop=shop, date=y, kind=Alert.Kind.CASH_MISMATCH, level="red",
                                 reason="Kassa ortiqchasi: sandiqda 100 000 / yozilgan 0 so'm")
    with django_capture_on_commit_callbacks(execute=True):
        r = _post(sclient, _body(product, qty=1, price=100_000, offline=True,
                                 client_ts=_yesterday_2350().isoformat()))
    assert r.status_code == 201
    rc = RegisterClose.objects.get(shop=shop, date=y)
    assert rc.expected_cash == 100_000 and rc.counted_cash == 100_000 and "oflayn" in rc.note
    alert.refresh_from_db()
    assert alert.status == Alert.Status.DISMISSED and "oflayn" in alert.reason
    # O'sha kun rostligi keyingi yangilashda qayta hisoblanadi
    refresh_today_if_stale(seconds=0)
    assert DailyScore.objects.get(shop=shop, date=y).entered_sales == 100_000


@pytest.mark.django_db
def test_queue_script_never_silently_drops(sclient):
    """Brauzer navbati: 4xx da o'chirib yubormaydi (eski xulq — "dropped++")."""
    from pathlib import Path

    from django.conf import settings

    js = (Path(settings.BASE_DIR) / "static/js/components.js").read_text(encoding="utf-8")
    assert "dropped++" not in js and "saleQueueRejected" in js and "r.status === 403" in js
    html = sclient.get("/", HTTP_HOST=SELLER_HOST, follow=True).content.decode()
    assert "window.BN_SHOP" in html
