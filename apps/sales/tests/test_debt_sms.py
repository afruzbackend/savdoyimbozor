"""Xaridorga nasiya SMS eslatmasi: bosqichlar, idempotentlik, raqam, o'chirish, backendlar."""

import datetime
import io
import json
import urllib.error

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.core import sms
from apps.core.models import SmsMessage
from apps.sales.models import Debt
from apps.sales.services.debts import buyer_sms_reminders
from conftest import SELLER_HOST


def _debt(shop, due, phone="+998 90 123-45-67", **kw):
    return Debt.objects.create(shop=shop, customer_name="Karim aka", customer_phone=phone,
                               amount=kw.pop("amount", 150_000), due_date=due, **kw)


def test_normalize_phone():
    assert sms.normalize_phone("+998 90 123-45-67") == "998901234567"
    assert sms.normalize_phone("90 1234567") == "998901234567"
    assert sms.normalize_phone("8 901234567") == "998901234567"
    assert sms.normalize_phone("12345") is None
    assert sms.normalize_phone("+7 916 123 45 67") is None


@pytest.mark.django_db
def test_stages_and_idempotency(shop, settings):
    settings.SMS_BACKEND = "console"
    today = timezone.localdate()
    tomorrow = _debt(shop, today + datetime.timedelta(days=1))
    due_today = _debt(shop, today)
    overdue3 = _debt(shop, today - datetime.timedelta(days=3))
    _debt(shop, today - datetime.timedelta(days=1))  # 1 kun o'tgan — bu kuni SMS yo'q
    _debt(shop, today + datetime.timedelta(days=5))  # hali erta
    _debt(shop, today, phone="")  # telefon yo'q
    _debt(shop, today, sms_remind=False)  # sotuvchi o'chirgan
    _debt(shop, today, is_paid=True)  # to'langan
    _debt(shop, today, amount=10_000, paid_amount=10_000)  # qoldiq 0

    stats = buyer_sms_reminders()
    assert stats["sent"] == 3
    texts = {m.key.split(":")[1]: m.text for m in SmsMessage.objects.all()}
    assert "ertaga" in texts[str(tomorrow.pk)] and "150 000" in texts[str(tomorrow.pk)]
    assert "bugun" in texts[str(due_today.pk)]
    assert "o'tgan" in texts[str(overdue3.pk)]
    assert all(len(t) <= 160 for t in texts.values())  # bitta SMS
    assert all(m.phone == "998901234567" for m in SmsMessage.objects.all())
    # Takroriy ishga tushish — qayta yubormaydi
    assert buyer_sms_reminders()["sent"] == 0
    assert SmsMessage.objects.count() == 3


@pytest.mark.django_db
def test_disabled_backend_sends_nothing(shop, settings):
    settings.SMS_BACKEND = ""
    _debt(shop, timezone.localdate())
    assert buyer_sms_reminders() == {"sent": 0, "failed": 0, "invalid": 0}
    assert not SmsMessage.objects.exists()


@pytest.mark.django_db
def test_invalid_number_logged_once(shop, settings):
    settings.SMS_BACKEND = "console"
    _debt(shop, timezone.localdate(), phone="123")
    assert buyer_sms_reminders()["invalid"] == 1
    assert buyer_sms_reminders()["invalid"] == 0  # yaroqsiz raqamga qayta urinilmaydi


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.mark.django_db
def test_eskiz_backend_token_refresh_and_retry_after_failure(shop, settings, monkeypatch):
    settings.SMS_BACKEND = "eskiz"
    settings.SMS_ESKIZ_EMAIL, settings.SMS_ESKIZ_PASSWORD = "a@b.uz", "x"
    cache.clear()
    calls = []
    state = {"down": True, "expired": True}

    def fake(req, timeout):
        calls.append(req.full_url)
        if req.full_url.endswith("/auth/login"):
            return _Resp(json.dumps({"data": {"token": f"T{len(calls)}"}}).encode())
        if state["down"]:
            raise urllib.error.URLError("timeout")
        if state["expired"]:
            state["expired"] = False
            raise urllib.error.HTTPError(req.full_url, 401, "exp", {}, None)
        assert req.headers["Authorization"].startswith("Bearer T")
        return _Resp(b'{"id": "abc-1", "status": "waiting"}')

    monkeypatch.setattr("urllib.request.urlopen", fake)
    _debt(shop, timezone.localdate())
    assert buyer_sms_reminders()["failed"] == 1  # tarmoq yo'q
    state["down"] = False
    assert buyer_sms_reminders()["sent"] == 1  # 15:00 dagi qayta urinish — token yangilanib ketdi
    m = SmsMessage.objects.get()
    assert m.status == "sent" and m.provider_id == "abc-1" and m.error == ""
    assert sum(u.endswith("/auth/login") for u in calls) == 2


@pytest.mark.django_db
def test_seller_toggles_sms_and_sees_status(sclient, shop, settings):
    settings.SMS_BACKEND = "console"
    d = _debt(shop, timezone.localdate())
    buyer_sms_reminders()
    html = sclient.get("/nasiya/", HTTP_HOST=SELLER_HOST).content.decode()
    assert "SMS eslatma yoqilgan" in html and "yuborildi" in html
    sclient.post("/nasiya/", {"sms_toggle": d.pk}, HTTP_HOST=SELLER_HOST)
    d.refresh_from_db()
    assert d.sms_remind is False
    # Yangi nasiya: switch o'chiq bo'lsa — SMS yuborilmaydi
    due = (timezone.localdate() + datetime.timedelta(days=3)).isoformat()
    sclient.post("/nasiya/", {"customer_name": "Olim", "customer_phone": "901112233",
                              "amount": "50 000", "due_date": due}, HTTP_HOST=SELLER_HOST)
    assert Debt.objects.get(customer_name="Olim").sms_remind is False
    sclient.post("/nasiya/", {"customer_name": "Vali", "amount": "50000", "due_date": due,
                              "sms_remind": "on"}, HTTP_HOST=SELLER_HOST)
    assert Debt.objects.get(customer_name="Vali").sms_remind is True


@pytest.mark.django_db
def test_other_shop_cannot_toggle(sclient, market):
    from apps.shops.models import Shop

    other = Shop.objects.create(market=market, number="77", stir="77")
    d = _debt(other, timezone.localdate())
    r = sclient.post("/nasiya/", {"sms_toggle": d.pk}, HTTP_HOST=SELLER_HOST)
    assert r.status_code == 404
    d.refresh_from_db()
    assert d.sms_remind is True


@pytest.mark.django_db
def test_panel_shows_sms_card(aclient, settings):
    settings.SMS_BACKEND = ""
    assert "ulanmagan" in aclient.get("/", HTTP_HOST="panel.localhost").content.decode()
