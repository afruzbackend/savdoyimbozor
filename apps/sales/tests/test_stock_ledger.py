"""O'zgarmas ombor jurnali: har harakat yoziladi, vaqt bo'yicha holat, buzish aniqlanadi."""

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.sales.models import StockMove
from apps.sales.services.stock import stock_at, verify_chain
from conftest import INSPECTOR_HOST, SELLER_HOST


def _sale(client, body):
    return client.post("/api/sales/", json.dumps(body), content_type="application/json",
                       HTTP_HOST=SELLER_HOST)


@pytest.mark.django_db
def test_every_movement_is_journaled(sclient, shop, product):
    product.stock = Decimal("0")
    product.sell_price = 10000
    product.save()
    sclient.post("/kirim/", {"product": product.pk, "quantity": "50", "unit_price": "7000"},
                 HTTP_HOST=SELLER_HOST)
    _sale(sclient, {"items": [{"product_id": product.pk, "name": "x", "qty": 5,
                               "unit_price": 10000}], "mode": "scan"})
    sclient.post("/kun-yakuni/", {f"evening_{product.pk}": "44", "counted_cash": "50000"},
                 HTTP_HOST=SELLER_HOST)
    moves = list(StockMove.objects.filter(product=product).order_by("created_at", "id"))
    assert [m.kind for m in moves] == ["in", "sale", "count"]
    assert [m.balance for m in moves] == [Decimal("50"), Decimal("45"), Decimal("44")]
    assert moves[2].qty == Decimal("-1")  # sanoq 1 dona kam topdi
    product.refresh_from_db()
    assert product.stock == Decimal("44")
    assert verify_chain(shop)[0] is True


@pytest.mark.django_db
def test_stock_at_past_moment(sclient, shop, product):
    product.stock = Decimal("0")
    product.save()
    sclient.post("/kirim/", {"product": product.pk, "quantity": "30", "unit_price": "1"},
                 HTTP_HOST=SELLER_HOST)
    mid = timezone.now()
    sclient.post("/kirim/", {"product": product.pk, "quantity": "20", "unit_price": "1"},
                 HTTP_HOST=SELLER_HOST)
    assert stock_at([shop], mid)[product.pk][0] == Decimal("30")
    assert stock_at([shop], timezone.now())[product.pk][0] == Decimal("50")
    assert product.pk not in stock_at([shop], mid - timedelta(hours=1))


@pytest.mark.django_db
def test_tampering_breaks_chain(sclient, shop, product):
    sclient.post("/kirim/", {"product": product.pk, "quantity": "10", "unit_price": "1"},
                 HTTP_HOST=SELLER_HOST)
    sclient.post("/kirim/", {"product": product.pk, "quantity": "5", "unit_price": "1"},
                 HTTP_HOST=SELLER_HOST)
    m = StockMove.objects.filter(shop=shop).order_by("created_at").first()
    with pytest.raises(ValueError):
        m.save()  # model darajasida o'zgartirib bo'lmaydi
    # Bazada to'g'ridan-to'g'ri o'zgartirish — zanjir buziladi va aniqlanadi
    StockMove.objects.filter(pk=m.pk).update(balance=Decimal("999"))
    ok, bad_id, _n = verify_chain(shop)
    assert ok is False and bad_id == m.pk


@pytest.mark.django_db
def test_writeoff_cannot_go_negative_under_lock(sclient, shop, product):
    from apps.sales.services.stock import NegativeStock, record_move

    product.stock = Decimal("3")
    product.save()
    with pytest.raises(NegativeStock):
        record_move(product, StockMove.Kind.WRITEOFF, delta=-5, allow_negative=False)
    product.refresh_from_db()
    assert product.stock == Decimal("3")


@pytest.mark.django_db
def test_inventory_at_time_pages(iclient, sclient, shop, product):
    sclient.post("/kirim/", {"product": product.pk, "quantity": "10", "unit_price": "1"},
                 HTTP_HOST=SELLER_HOST)
    now = timezone.localtime()
    q = f"?sana={now:%Y-%m-%d}&vaqt={now:%H:%M}"
    r = iclient.get(f"/ombor/{q}", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200 and r.context["at"] is not None
    r = iclient.get(f"/ombor/dokon/{shop.pk}/{q}", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200
    assert r.context["chain_ok"] is True
    assert any(ln["p"].pk == product.pk for ln in r.context["lines"])
