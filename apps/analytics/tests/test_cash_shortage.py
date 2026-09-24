"""Kassa nomuvofiqligi va nol-savdo signallari (Z-hisobot asosida)."""

import pytest
from django.utils import timezone

from apps.analytics.models import Alert
from apps.analytics.scoring.services import recompute_for_date
from apps.sales.models import RegisterClose, Sale


@pytest.mark.django_db
def test_surplus_creates_red_alert(shop, seller):
    """Sandiqda yozilgandan ko'p naqd — yozilmagan savdo, kuchli (qizil) signal."""
    day = timezone.localdate()
    RegisterClose.objects.create(
        shop=shop, seller=seller, date=day,
        expected_cash=1_000_000, counted_cash=1_500_000,  # 50% ortiqcha
        checks_count=10,
    )
    recompute_for_date(day, final=True)
    a = Alert.objects.get(shop=shop, date=day, kind=Alert.Kind.CASH_MISMATCH)
    assert a.level == "red"
    assert "ortiqcha" in a.reason.lower()


@pytest.mark.django_db
def test_shortage_creates_alert(shop, seller):
    day = timezone.localdate()
    RegisterClose.objects.create(
        shop=shop, seller=seller, date=day,
        expected_cash=1_000_000, counted_cash=600_000,  # 40% kamomad
        checks_count=10,
    )
    recompute_for_date(day, final=True)
    a = Alert.objects.get(shop=shop, date=day, kind=Alert.Kind.CASH_MISMATCH)
    assert "kamomad" in a.reason.lower()


@pytest.mark.django_db
def test_small_mismatch_no_alert(shop, seller):
    day = timezone.localdate()
    RegisterClose.objects.create(
        shop=shop, seller=seller, date=day,
        expected_cash=1_000_000, counted_cash=950_000,  # 5% — chegaradan past
        checks_count=10,
    )
    recompute_for_date(day, final=True)
    assert not Alert.objects.filter(
        shop=shop, date=day, kind=Alert.Kind.CASH_MISMATCH
    ).exists()


@pytest.mark.django_db
def test_no_duplicate_mismatch_alert(shop, seller):
    day = timezone.localdate()
    RegisterClose.objects.create(
        shop=shop, seller=seller, date=day,
        expected_cash=1_000_000, counted_cash=1_500_000, checks_count=10,
    )
    recompute_for_date(day, final=True)
    recompute_for_date(day, final=True)
    assert (
        Alert.objects.filter(shop=shop, date=day, kind=Alert.Kind.CASH_MISMATCH).count() == 1
    )


@pytest.mark.django_db
def test_hidden_sales_computed(shop, seller):
    """Yozilgan savdo > deklaratsiya bo'lsa — yashirilgan savdo hisoblanadi."""
    from apps.analytics.models import DailyScore
    from apps.cash.models import CashRecord
    from apps.sales.models import Sale

    day = timezone.localdate()
    Sale.objects.create(shop=shop, seller=seller, total=1_000_000, payment_type="cash")
    CashRecord.objects.create(shop=shop, date=day, amount=300_000, source="excel")
    recompute_for_date(day, final=True)
    ds = DailyScore.objects.get(shop=shop, date=day)
    assert ds.hidden_sales == 700_000  # 1M real - 300k deklaratsiya


@pytest.mark.django_db
def test_zero_sales_with_stock_is_red(shop, seller, product):
    """Do'kon ochiq, tovari bor, lekin 0 savdo kiritilgan — qizil signal."""
    day = timezone.localdate()
    # product fikstura'sida stock=100, savdo yo'q
    recompute_for_date(day, final=True)
    a = Alert.objects.get(shop=shop, date=day, kind=Alert.Kind.ZERO_SALES)
    assert a.level == "red"


@pytest.mark.django_db
def test_sales_present_no_zero_alert(shop, seller, product):
    day = timezone.localdate()
    Sale.objects.create(shop=shop, seller=seller, total=50000, payment_type="cash")
    recompute_for_date(day, final=True)
    assert not Alert.objects.filter(
        shop=shop, date=day, kind=Alert.Kind.ZERO_SALES
    ).exists()


@pytest.mark.django_db
def test_no_alerts_for_unfinished_day(shop, seller, product):
    """Kun tugamagan (bugun, yakuniy emas) — ball yangilanadi, lekin signal YO'Q.

    Ilgari ertalab birinchi sotuvda butun bozorga "savdo yo'q" qizil signali chiqardi.
    """
    day = timezone.localdate()
    RegisterClose.objects.create(
        shop=shop, seller=seller, date=day,
        expected_cash=1_000_000, counted_cash=1_500_000, checks_count=10,
    )
    recompute_for_date(day)  # final avtomatik: bugun → False
    assert not Alert.objects.filter(shop=shop, date=day).exists()


@pytest.mark.django_db
def test_today_nosales_alert_does_not_force_appeal(sclient, shop, product):
    """Bugungi "savdo yo'q" signali sotuvchini E'tiroz sahifasiga majburlamaydi."""
    from conftest import SELLER_HOST

    Alert.objects.create(shop=shop, date=timezone.localdate(), kind=Alert.Kind.ZERO_SALES,
                         level="red", reason="x")
    r = sclient.get("/", HTTP_HOST=SELLER_HOST)
    assert r.status_code == 200
