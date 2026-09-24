"""Kassa: maydalik, nasiyaga sotuv, nasiya to'lovi — noto'g'ri "ortiqcha" signali bo'lmasin."""

import json

import pytest
from django.utils import timezone

from apps.sales.models import CashOpen, Debt, DebtPayment, RegisterClose, Sale
from conftest import SELLER_HOST


def _sale(client, body):
    return client.post("/api/sales/", json.dumps(body), content_type="application/json",
                       HTTP_HOST=SELLER_HOST)


@pytest.mark.django_db
def test_opening_cash_counts_in_expected(sclient, shop):
    sclient.post("/kassa/", {"action": "opening", "opening_cash": "200000"}, HTTP_HOST=SELLER_HOST)
    assert CashOpen.objects.get(shop=shop).amount == 200000
    _sale(sclient, {"items": [{"name": "x", "qty": 1, "unit_price": 50000}], "payment_type": "cash"})
    # Sandiqda: 200k maydalik + 50k savdo = 250k — ORTIQCHA emas
    sclient.post("/kassa/", {"counted_cash": "250000"}, HTTP_HOST=SELLER_HOST)
    z = RegisterClose.objects.get(shop=shop)
    assert z.expected_cash == 250000 and z.opening_cash == 200000
    assert z.difference == 0


@pytest.mark.django_db
def test_opening_locked_after_first_sale(sclient, shop):
    _sale(sclient, {"items": [{"name": "x", "qty": 1, "unit_price": 5000}]})
    sclient.post("/kassa/", {"action": "opening", "opening_cash": "900000"}, HTTP_HOST=SELLER_HOST)
    # Sotuvdan keyin "maydalik edi" deb yashirib bo'lmaydi
    assert not CashOpen.objects.filter(shop=shop).exists()


@pytest.mark.django_db
def test_debt_sale_requires_name_and_creates_debt(sclient, shop):
    r = _sale(sclient, {"items": [{"name": "x", "qty": 1, "unit_price": 80000}],
                        "payment_type": "debt"})
    assert r.status_code == 400
    assert not Sale.objects.filter(shop=shop).exists()
    r = _sale(sclient, {"items": [{"name": "x", "qty": 1, "unit_price": 80000}],
                        "payment_type": "debt", "debtor_name": "Vali aka", "debtor_phone": "+99890"})
    assert r.status_code == 201
    sale = Sale.objects.get(shop=shop)
    d = Debt.objects.get(shop=shop)
    assert d.sale == sale and d.amount == 80000 and d.customer_name == "Vali aka"
    # Nasiyaga sotuv sandiqqa tushmaydi — kutilgan naqdga kirmaydi
    sclient.post("/kassa/", {"counted_cash": "0"}, HTTP_HOST=SELLER_HOST)
    assert RegisterClose.objects.get(shop=shop).difference == 0


@pytest.mark.django_db
def test_partial_debt_payment_and_cash_expected(sclient, shop):
    d = Debt.objects.create(shop=shop, customer_name="Ali", amount=100000)
    sclient.post("/nasiya/", {"pay": d.pk, "amount": "30000", "method": "cash"},
                 HTTP_HOST=SELLER_HOST)
    d.refresh_from_db()
    assert d.paid_amount == 30000 and d.remaining == 70000 and not d.is_paid
    # Qoldiqdan ko'p to'lab bo'lmaydi
    sclient.post("/nasiya/", {"pay": d.pk, "amount": "999999", "method": "cash"},
                 HTTP_HOST=SELLER_HOST)
    d.refresh_from_db()
    assert d.paid_amount == 30000
    # Karta bilan qolgani — to'liq yopiladi
    sclient.post("/nasiya/", {"pay": d.pk, "amount": "70000", "method": "card"},
                 HTTP_HOST=SELLER_HOST)
    d.refresh_from_db()
    assert d.is_paid and d.remaining == 0
    assert DebtPayment.objects.filter(debt=d).count() == 2
    # Faqat NAQD qaytgan nasiya (30k) sandiqdagi kutilgan naqdga qo'shiladi
    sclient.post("/kassa/", {"counted_cash": "30000"}, HTTP_HOST=SELLER_HOST)
    z = RegisterClose.objects.get(shop=shop, date=timezone.localdate())
    assert z.debt_cash_in == 30000 and z.difference == 0


@pytest.mark.django_db
def test_debt_payment_other_shop_404(sclient, shop, market):
    from apps.shops.models import Shop

    other = Shop.objects.create(market=market, number="777", stir="9")
    d = Debt.objects.create(shop=other, customer_name="Begona", amount=5000)
    r = sclient.post("/nasiya/", {"pay": d.pk, "amount": "5000"}, HTTP_HOST=SELLER_HOST)
    assert r.status_code == 404


@pytest.mark.django_db
def test_stock_in_is_not_counted_as_sold(sclient, shop, product):
    """Kirim bo'lgan kuni halol sotuvchi "yashirilgan savdo" bo'lib chiqmasin.

    Ertalab 100, kirim 50, sotuv 30 (skaner), kechqurun 120 → jismoniy sotilgan 30.
    Ilgari: (100−120 → 0) + BUTUN kirim qiymati = "sotilgan" deb olinardi.
    """
    from decimal import Decimal

    from apps.analytics.scoring.services import _stock_estimate

    product.stock = Decimal("100")
    product.sell_price = 10000
    product.save()
    sclient.post("/kirim/", {"product": product.pk, "quantity": "50", "unit_price": "7000"},
                 HTTP_HOST=SELLER_HOST)
    r = _sale(sclient, {"items": [{"product_id": product.pk, "name": product.name, "qty": 30,
                                   "unit_price": 10000}], "mode": "scan"})
    assert r.status_code == 201
    sclient.post("/kun-yakuni/", {f"evening_{product.pk}": "120", "counted_cash": "300000"},
                 HTTP_HOST=SELLER_HOST)
    from apps.sales.models import DailyClose

    close = DailyClose.objects.get(shop=shop)
    ln = close.lines.get()
    assert ln.morning_qty == Decimal("100")  # tizim hisobi: 120 + 30 − 50
    assert close.computed_sales == 300000  # 30 × 10 000
    assert _stock_estimate(shop, timezone.localdate()) == 300000
    product.refresh_from_db()
    assert product.stock == Decimal("120")  # sanoqqa tenglashdi


@pytest.mark.django_db
def test_morning_locked_after_previous_count(sclient, shop, product):
    """Kechagi sanoq bo'lsa ertalabni o'zgartirib "hech narsa sotilmadi" deb bo'lmaydi."""
    from datetime import timedelta
    from decimal import Decimal

    from apps.sales.models import DailyClose, DailyCloseLine

    y = timezone.localdate() - timedelta(days=1)
    c = DailyClose.objects.create(shop=shop, date=y)
    DailyCloseLine.objects.create(close=c, product=product, product_name=product.name,
                                  morning_qty=90, evening_qty=80, unit_price=product.sell_price)
    sclient.post("/kun-yakuni/", {f"morning_{product.pk}": "10", f"evening_{product.pk}": "10",
                                  "counted_cash": "0"}, HTTP_HOST=SELLER_HOST)
    ln = DailyClose.objects.get(shop=shop, date=timezone.localdate()).lines.get()
    assert ln.morning_qty == Decimal("80")  # kechagi kechki sanoq, 10 emas
