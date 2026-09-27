"""Sotuv summasini tuzatish — savdoni yashirish yo'li bo'lmasin.

Xaridorga to'liq (QR) chek berib, keyin yozuvni kamaytirish: chekda xaridorga ko'rinadi,
keskin kamaytirish nazoratchiga signal, Z-hisobotdan keyin esa umuman mumkin emas.
"""

import pytest
from django.utils import timezone

from apps.analytics.models import Alert
from apps.analytics.scoring.services import recompute_for_date
from apps.sales.models import Correction, RegisterClose, Sale
from conftest import SELLER_HOST, set_settings


def _sale(shop, seller, total):
    return Sale.objects.create(shop=shop, seller=seller, subtotal=total, total=total, payment_type="cash")


def _fix(client, sale, new_total, reason="xato"):
    return client.post("/tuzatish/", {"sale": sale.pk, "new_total": str(new_total), "reason": reason},
                       HTTP_HOST=SELLER_HOST, follow=True)


@pytest.mark.django_db
def test_no_corrections_after_register_closed(sclient, shop, seller):
    s = _sale(shop, seller, 100_000)
    RegisterClose.objects.create(shop=shop, seller=seller, date=timezone.localdate(), expected_cash=100_000,
                                 counted_cash=100_000)
    r = _fix(sclient, s, 60_000)
    s.refresh_from_db()
    assert s.total == 100_000 and not Correction.objects.exists()
    assert "Z-hisobot" in r.content.decode()


@pytest.mark.django_db
def test_large_downward_corrections_raise_alert(sclient, shop, seller, product):
    set_settings(correction_alert_pct=10, correction_alert_min=100_000)
    big = _sale(shop, seller, 300_000)
    for _ in range(7):
        _sale(shop, seller, 100_000)
    _fix(sclient, big, 100_000)  # −200 000 → kunlik 1 000 000 dan 20%
    recompute_for_date(timezone.localdate(), final=True)
    a = Alert.objects.get(shop=shop, kind=Alert.Kind.CORRECTION)
    assert a.level == "red" and "−200 000" in a.reason and "20%" in a.reason


@pytest.mark.django_db
def test_small_correction_no_alert(sclient, shop, seller, product):
    set_settings(correction_alert_pct=10, correction_alert_min=100_000)
    s = _sale(shop, seller, 55_000)
    _fix(sclient, s, 50_000)  # 5 000 — oddiy xato
    recompute_for_date(timezone.localdate(), final=True)
    assert not Alert.objects.filter(shop=shop, kind=Alert.Kind.CORRECTION).exists()


@pytest.mark.django_db
def test_buyer_receipt_shows_correction(client, sclient, shop, seller):
    s = _sale(shop, seller, 100_000)
    code = s.ensure_public_code()
    _fix(sclient, s, 60_000, reason="noto'g'ri yozildi")
    html = client.get(f"/chek/{code}/").content.decode()
    assert "Sotuvchi bu chek summasini o" in html and "100 000" in html and "60 000" in html
    assert "noto" in html and "<details open" in html  # xabar berish shakli ochiq
