"""Kassa kamomadi signali (Z-hisobot asosida, rostlik ballidan mustaqil)."""

import pytest
from django.utils import timezone

from apps.analytics.models import Alert
from apps.analytics.scoring.services import recompute_for_date
from apps.sales.models import RegisterClose


@pytest.mark.django_db
def test_shortage_creates_alert(shop, seller):
    day = timezone.localdate()
    RegisterClose.objects.create(
        shop=shop, seller=seller, date=day,
        expected_cash=1_000_000, counted_cash=600_000,  # 40% kamomad
        card_total=0, transfer_total=0, checks_count=10,
    )
    recompute_for_date(day)
    a = Alert.objects.filter(shop=shop, date=day, kind=Alert.Kind.CASH_SHORTAGE).first()
    assert a is not None
    assert a.level == "red"  # 40% ≥ 2×15% → qizil


@pytest.mark.django_db
def test_small_shortage_no_alert(shop, seller):
    day = timezone.localdate()
    RegisterClose.objects.create(
        shop=shop, seller=seller, date=day,
        expected_cash=1_000_000, counted_cash=950_000,  # 5% — chegaradan past
        checks_count=10,
    )
    recompute_for_date(day)
    assert not Alert.objects.filter(
        shop=shop, date=day, kind=Alert.Kind.CASH_SHORTAGE
    ).exists()


@pytest.mark.django_db
def test_moderate_shortage_is_yellow(shop, seller):
    day = timezone.localdate()
    RegisterClose.objects.create(
        shop=shop, seller=seller, date=day,
        expected_cash=1_000_000, counted_cash=800_000,  # 20% — chegara..2×chegara orasi
        checks_count=10,
    )
    recompute_for_date(day)
    a = Alert.objects.get(shop=shop, date=day, kind=Alert.Kind.CASH_SHORTAGE)
    assert a.level == "yellow"


@pytest.mark.django_db
def test_no_duplicate_shortage_alert(shop, seller):
    day = timezone.localdate()
    RegisterClose.objects.create(
        shop=shop, seller=seller, date=day,
        expected_cash=1_000_000, counted_cash=600_000, checks_count=10,
    )
    recompute_for_date(day)
    recompute_for_date(day)  # ikkinchi marta — takror signal bo'lmasin
    assert (
        Alert.objects.filter(shop=shop, date=day, kind=Alert.Kind.CASH_SHORTAGE).count() == 1
    )
