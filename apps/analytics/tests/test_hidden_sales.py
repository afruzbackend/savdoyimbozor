"""Yashirilgan savdo mantig'i: deklaratsiya-nol vs deklaratsiya-yo'q farqi."""

import pytest
from django.utils import timezone

from apps.analytics.models import DailyScore
from apps.analytics.scoring.services import recompute_for_date
from apps.cash.models import CashRecord
from apps.sales.models import Sale
from apps.shops.models import Shop


@pytest.mark.django_db
def test_hidden_counts_declared_zero_but_not_missing(market, seller):
    day = timezone.localdate()
    # Do'kon A: 100 000 savdo, deklaratsiya YOZUVI bor lekin 0 → yashirilgan = 100 000
    a = Shop.objects.create(market=market, number="A1", stir="100000001")
    Sale.objects.create(shop=a, seller=seller, total=100_000, subtotal=100_000)
    CashRecord.objects.create(shop=a, date=day, amount=0, source="excel")

    # Do'kon B: 100 000 savdo, deklaratsiya YOZUVI umuman yo'q → yashirilgan = 0 (ma'lumot yo'q)
    b = Shop.objects.create(market=market, number="B1", stir="100000002")
    Sale.objects.create(shop=b, seller=seller, total=100_000, subtotal=100_000)

    recompute_for_date(day)

    sa = DailyScore.objects.get(shop=a, date=day)
    sb = DailyScore.objects.get(shop=b, date=day)
    assert sa.hidden_sales == 100_000  # nolga deklaratsiya qilgan — to'liq yashirilgan
    assert sb.hidden_sales == 0  # deklaratsiya kelmagan — ayblanmaydi


@pytest.mark.django_db
def test_hidden_is_gap_when_partially_declared(market, seller):
    day = timezone.localdate()
    c = Shop.objects.create(market=market, number="C1", stir="100000003")
    Sale.objects.create(shop=c, seller=seller, total=100_000, subtotal=100_000)
    CashRecord.objects.create(shop=c, date=day, amount=60_000, source="excel")
    recompute_for_date(day)
    sc = DailyScore.objects.get(shop=c, date=day)
    assert sc.hidden_sales == 40_000  # 100k real − 60k deklaratsiya
