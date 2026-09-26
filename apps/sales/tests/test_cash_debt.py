"""Kassa: maydalik, nasiyaga sotuv, nasiya to'lovi — noto'g'ri "ortiqcha" signali bo'lmasin."""

import json

import pytest
from django.utils import timezone

from apps.sales.models import CashOpen, Debt, DebtPayment, RegisterClose, Sale
from conftest import SELLER_HOST, photo_file


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
                        "payment_type": "debt", "debtor_name": "Vali aka", "debtor_phone": "+99890",
                        "debtor_due": str(timezone.localdate())})
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
    sclient.post("/kun-yakuni/", {"photo": photo_file(), f"evening_{product.pk}": "120", "counted_cash": "300000"},
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
    sclient.post("/kun-yakuni/", {"photo": photo_file(), f"morning_{product.pk}": "10", f"evening_{product.pk}": "10",
                                  "counted_cash": "0"}, HTTP_HOST=SELLER_HOST)
    ln = DailyClose.objects.get(shop=shop, date=timezone.localdate()).lines.get()
    assert ln.morning_qty == Decimal("80")  # kechagi kechki sanoq, 10 emas


@pytest.mark.django_db
def test_product_price_edit_logged_and_archive(sclient, shop, product):
    from apps.sales.models import Correction

    old = product.sell_price
    sclient.post("/mahsulotlar/", {"action": "edit", "id": product.pk, "buy_price": "5000",
                                   "sell_price": str(old + 3000), "low_stock_threshold": "2",
                                   "pack_coeff": "20"}, HTTP_HOST=SELLER_HOST)
    product.refresh_from_db()
    assert product.sell_price == old + 3000 and product.pack_coeff == 20
    c = Correction.objects.get(shop=shop, target_model="Product", field="sell_price")
    assert c.old_value == str(old)
    sclient.post("/mahsulotlar/", {"action": "archive", "id": product.pk}, HTTP_HOST=SELLER_HOST)
    product.refresh_from_db()
    assert product.is_active is False


@pytest.mark.django_db
def test_stock_in_packs_uses_coefficient(sclient, shop, product):
    """Qopda kirim: 2 qop × 20 kg = 40 kg (ilgari koeffitsiyent kiritib bo'lmasdi)."""
    from decimal import Decimal

    product.pack_coeff = Decimal("20")
    product.stock = Decimal("0")
    product.save()
    sclient.post("/kirim/", {"product": product.pk, "quantity": "2", "unit_price": "10000",
                             "in_packs": "on"}, HTTP_HOST=SELLER_HOST)
    product.refresh_from_db()
    assert product.stock == Decimal("40")


@pytest.mark.django_db
def test_correcting_debt_sale_updates_debt(sclient, shop):
    r = _sale(sclient, {"items": [{"name": "x", "qty": 1, "unit_price": 90000}],
                        "payment_type": "debt", "debtor_name": "Vali",
                        "debtor_due": str(timezone.localdate())})
    sale_id = r.json()["id"]
    sclient.post("/tuzatish/", {"sale": sale_id, "new_total": "80000", "reason": "xato"},
                 HTTP_HOST=SELLER_HOST)
    assert Debt.objects.get(shop=shop).amount == 80000


@pytest.mark.django_db
def test_evening_reminder_without_celery(seller, shop):
    from datetime import datetime
    from unittest import mock

    from apps.core.models import Notification
    from apps.sales.management.commands import close_reminders as cr

    late = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.min.time())
                               .replace(hour=21))
    with mock.patch.object(cr.timezone, "localtime", return_value=late):
        assert cr.remind_if_due(seller) is True
        cr.remind_if_due(seller)  # ikkinchi marta — takrorlanmaydi
    assert Notification.objects.filter(user=seller, title="Kun yakunini yoping").count() == 1


@pytest.mark.django_db
def test_debt_sale_requires_due_date(sclient, shop):
    r = _sale(sclient, {"items": [{"name": "x", "qty": 1, "unit_price": 5000}],
                        "payment_type": "debt", "debtor_name": "Ali"})
    assert r.status_code == 400 and "sana" in r.json()["detail"]
    assert not Sale.objects.filter(shop=shop).exists()


@pytest.mark.django_db
def test_manual_debt_requires_future_due(sclient, shop):
    from datetime import timedelta

    sclient.post("/nasiya/", {"customer_name": "A", "amount": "1000"}, HTTP_HOST=SELLER_HOST)
    past = timezone.localdate() - timedelta(days=1)
    sclient.post("/nasiya/", {"customer_name": "B", "amount": "1000", "due_date": str(past)},
                 HTTP_HOST=SELLER_HOST)
    assert not Debt.objects.filter(shop=shop).exists()


@pytest.mark.django_db
def test_debt_reminders_day_before_and_on_day(seller, shop):
    """1 kun oldin va o'sha kuni — alohida eslatma, har biri bir marta."""
    from datetime import timedelta
    from unittest import mock

    from apps.core.models import Notification
    from apps.sales.services import debts as ds

    today = timezone.localdate()
    Debt.objects.create(shop=shop, customer_name="Vali", amount=50000,
                        due_date=today + timedelta(days=1))
    assert ds.debt_reminders(seller, shop) == 1
    assert ds.debt_reminders(seller, shop) == 0  # takrorlanmaydi
    n = Notification.objects.get(user=seller)
    assert n.title.startswith("Ertaga")
    # Ertasi kun — "Bugun" eslatmasi
    with mock.patch.object(ds.timezone, "localdate", return_value=today + timedelta(days=1)):
        assert ds.debt_reminders(seller, shop) == 1
    assert Notification.objects.filter(user=seller, title__startswith="Bugun").exists()


@pytest.mark.django_db
def test_extend_debt_due(sclient, shop):
    from datetime import timedelta

    d = Debt.objects.create(shop=shop, customer_name="Vali", amount=50000,
                            due_date=timezone.localdate())
    new = timezone.localdate() + timedelta(days=7)
    sclient.post("/nasiya/", {"extend": d.pk, "due_date": str(new)}, HTTP_HOST=SELLER_HOST)
    d.refresh_from_db()
    assert d.due_date == new


@pytest.mark.django_db
def test_large_stock_in_requires_invoice_photo(sclient, shop, product, settings, tmp_path):
    import io
    from decimal import Decimal

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from apps.sales.models import StockIn

    settings.MEDIA_ROOT = str(tmp_path)
    before = product.stock
    # 100 × 20 000 = 2 mln > 1 mln — fotosiz rad etiladi
    sclient.post("/kirim/", {"product": product.pk, "quantity": "100", "unit_price": "20000"},
                 HTTP_HOST=SELLER_HOST)
    product.refresh_from_db()
    assert product.stock == before and not StockIn.objects.filter(shop=shop).exists()
    buf = io.BytesIO()
    Image.new("RGB", (3, 3), (0, 0, 0)).save(buf, format="JPEG")
    photo = SimpleUploadedFile("n.jpg", buf.getvalue(), content_type="image/jpeg")
    sclient.post("/kirim/", {"product": product.pk, "quantity": "100", "unit_price": "20000",
                             "supplier_name": "Ota-bola MChJ", "supplier_stir": "305 111 222",
                             "invoice_photo": photo}, HTTP_HOST=SELLER_HOST)
    si = StockIn.objects.get(shop=shop)
    assert si.invoice_photo and si.supplier_stir == "305111222"
    product.refresh_from_db()
    assert product.stock == before + Decimal("100")


@pytest.mark.django_db(transaction=True)
def test_debt_payment_works_outside_test_transaction(sclient, shop):
    """Haqiqiy server autocommit rejimida: select_for_update tranzaksiyasiz 500 berardi.

    Oddiy testlar har testni tranzaksiyaga o'raydi — xato ko'rinmagan. transaction=True —
    xuddi runserver/gunicorn kabi.
    """
    d = Debt.objects.create(shop=shop, customer_name="Ali", amount=100000)
    r = sclient.post("/nasiya/", {"pay": d.pk, "amount": "30000", "method": "cash"},
                     HTTP_HOST=SELLER_HOST)
    assert r.status_code == 302
    d.refresh_from_db()
    assert d.paid_amount == 30000


@pytest.mark.django_db(transaction=True)
def test_sale_and_stock_moves_work_outside_test_transaction(sclient, shop, product):
    """Sotuv va qoldiq jurnali ham (select_for_update) — haqiqiy autocommit rejimida."""
    import json

    body = {"items": [{"product_id": product.pk, "name": product.name, "qty": 1, "unit_price": 12000}],
            "discount": 0, "rounding": 0, "payment_type": "cash", "mode": "scan"}
    r = sclient.post("/api/sales/", json.dumps(body), content_type="application/json", HTTP_HOST=SELLER_HOST)
    assert r.status_code == 201
