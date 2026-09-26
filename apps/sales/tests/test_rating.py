"""Reyting: do'kon va mahsulot o'rni to'g'ri; og'ir yig'indi keshlanadi."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.catalog.models import Product
from apps.sales.models import Sale, SaleItem
from apps.shops.models import Shop
from conftest import SELLER_HOST


def _sell(shop, product, qty, price):
    s = Sale.objects.create(shop=shop, total=qty * price, subtotal=qty * price)
    SaleItem.objects.create(sale=s, product=product, product_name=product.name, quantity=qty,
                            unit_price=price, line_total=qty * price)


@pytest.mark.django_db
def test_rating_positions_and_cache(sclient, shop, product):
    a = Shop.objects.create(market=shop.market, category=shop.category, number="2", stir="2")
    b = Shop.objects.create(market=shop.market, category=shop.category, number="3", stir="3")
    pa = Product.objects.create(shop=a, name="Pomidor", category=product.category, sell_price=1)
    pb = Product.objects.create(shop=b, name="Pomidor", category=product.category, sell_price=1)
    _sell(a, pa, 50, 10_000)   # 500 000
    _sell(shop, product, 20, 10_000)  # 200 000 — 2-o'rin
    _sell(b, pb, 5, 10_000)    # 50 000
    r = sclient.get("/reyting/", HTTP_HOST=SELLER_HOST)
    ctx = r.context
    assert (ctx["overall_pos"], ctx["overall_total"]) == (2, 3)
    assert (ctx["cat_pos"], ctx["cat_total"]) == (2, 3)
    assert ctx["my_sales"] == 200_000
    assert ctx["product_ranks"][0]["pos"] == 2 and ctx["product_ranks"][0]["total"] == 3
    # Takroriy ochish: bozor yig'indilari keshdan — og'ir so'rovlar qaytarilmaydi
    with CaptureQueriesContext(connection) as q:
        sclient.get("/reyting/", HTTP_HOST=SELLER_HOST)
    heavy = [x["sql"] for x in q.captured_queries if "sales_saleitem" in x["sql"]
             or ('SUM("sales_sale"."total")' in x["sql"] and "shop_id\" = " not in x["sql"])]
    assert not heavy, heavy
