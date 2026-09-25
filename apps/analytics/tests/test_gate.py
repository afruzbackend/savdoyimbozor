"""Darvoza kamerasi ↔ kirim: tushirish bor, kirim yo'q → "hujjatsiz kirim" signali."""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.analytics.gate import check_day, shop_summary, window_closed
from apps.analytics.models import Alert
from apps.cameras.models import Camera, CameraEvent
from apps.sales.models import StockIn
from conftest import INSPECTOR_HOST


def _at(day, hh, mm=0):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hh, mm)))


@pytest.fixture
def gate(market):
    return Camera.objects.create(market=market, kind=Camera.Kind.GATE, name="Darvoza")


def _unload(gate, shop, ts, count=5, plate="01A777AA"):
    return CameraEvent.objects.create(camera=gate, shop=shop, type=CameraEvent.Type.GATE_IN,
                                      count=count, payload={"plate": plate, "count": count}, ts=ts)


def _stockin(shop, product, ts):
    si = StockIn.objects.create(shop=shop, product=product, quantity=Decimal("10"), unit_price=5000)
    StockIn.objects.filter(pk=si.pk).update(created_at=ts)
    return si


@pytest.mark.django_db
def test_unrecorded_delivery_raises_alert(gate, shop, product, inspector):
    day = timezone.localdate() - datetime.timedelta(days=2)
    _unload(gate, shop, _at(day, 7, 20), count=6)
    _unload(gate, shop, _at(day, 15, 5), count=4)
    assert check_day(day) == 1
    a = Alert.objects.get(kind="gate_unrecorded", shop=shop)
    assert a.level == "red" and a.assigned_to == inspector and a.date == day
    assert "07:20" in a.reason and "15:05" in a.reason and "~10" in a.reason and "01A777AA" in a.reason
    assert check_day(day) == 0  # takroriy tekshiruv dublikat bermaydi


@pytest.mark.django_db
def test_recorded_delivery_is_fine_including_next_morning(gate, shop, product):
    day = timezone.localdate() - datetime.timedelta(days=2)
    _unload(gate, shop, _at(day, 9))
    _stockin(shop, product, _at(day, 9, 40))  # tushirishdan keyin kirim
    _unload(gate, shop, _at(day, 21, 30))
    _stockin(shop, product, _at(day + datetime.timedelta(days=1), 8, 15))  # ertasi ertalab kiritdi
    assert check_day(day) == 0
    assert not Alert.objects.filter(kind="gate_unrecorded").exists()
    rows = shop_summary(shop)
    assert rows[0]["events"] == 2 and not rows[0]["missing"]


@pytest.mark.django_db
def test_stockin_outside_window_does_not_cover(gate, shop, product):
    day = timezone.localdate() - datetime.timedelta(days=2)
    _unload(gate, shop, _at(day, 8), count=2)
    _stockin(shop, product, _at(day, 5))  # 3 soat OLDIN — bu yetkazib berish emas
    assert check_day(day) == 1
    assert Alert.objects.get(kind="gate_unrecorded").level == "yellow"  # bitta, kichik


@pytest.mark.django_db
def test_waits_until_window_closes(gate, shop):
    yesterday = timezone.localdate() - datetime.timedelta(days=1)
    _unload(gate, shop, _at(yesterday, 23, 0))
    end = _at(yesterday + datetime.timedelta(days=1), 0)
    assert not window_closed(yesterday, now=end + datetime.timedelta(hours=13))
    assert window_closed(yesterday, now=end + datetime.timedelta(hours=14))
    if not window_closed(yesterday):
        assert check_day(yesterday) == 0  # sotuvchi hali kiritishga ulguradi
    assert check_day(yesterday, force=True) == 1


@pytest.mark.django_db
def test_market_gate_events_without_shop_are_ignored(gate, shop):
    day = timezone.localdate() - datetime.timedelta(days=2)
    CameraEvent.objects.create(camera=gate, shop=None, type=CameraEvent.Type.GATE_IN, count=1,
                               payload={"plate": "01B111BB"}, ts=_at(day, 10))
    assert check_day(day) == 0


@pytest.mark.django_db
def test_shop_detail_shows_gate_table(iclient, gate, shop):
    day = timezone.localdate() - datetime.timedelta(days=2)
    _unload(gate, shop, _at(day, 7, 20))
    html = iclient.get(f"/dokon/{shop.pk}/", HTTP_HOST=INSPECTOR_HOST).content.decode()
    assert "Darvoza kamerasi va kirim" in html and "yozilmagan: 1" in html


@pytest.mark.django_db
def test_gate_events_via_contract_api(client, gate, shop):
    """Kontrakt o'zgarmagan: gate_in hodisasi /api/events/ orqali keladi."""
    gate.refresh_from_db()
    r = client.post("/api/events/", {"type": "gate_in", "shop_id": shop.pk,
                                     "payload": {"plate": "01C222CC", "count": 3}},
                    content_type="application/json", HTTP_X_CAMERA_TOKEN=gate.token)
    assert r.status_code == 201 and r.json()["created"] == 1
    ev = CameraEvent.objects.get(type="gate_in")
    assert ev.shop == shop and ev.count == 3
