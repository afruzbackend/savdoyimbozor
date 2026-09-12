"""Nazoratchi sahifalari: sxema, pagination, so'rov soni (N+1 qo'riqlash)."""

import pytest
from django.utils import timezone

from apps.analytics.models import Alert
from apps.catalog.models import Product
from conftest import INSPECTOR_HOST


@pytest.mark.django_db
def test_market_schema_renders(iclient, shop):
    r = iclient.get("/xarita/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200
    html = r.content.decode()
    assert "Bozor sxemasi" in html
    assert "bazaar" in html  # rastalar sxemasi (Leaflet emas)


@pytest.mark.django_db
def test_alerts_pagination(iclient, shop):
    for i in range(60):
        Alert.objects.create(
            shop=shop, date=timezone.localdate(), kind=Alert.Kind.TRUTH, level="yellow",
            reason=f"signal {i}",
        )
    r1 = iclient.get("/signallar/", HTTP_HOST=INSPECTOR_HOST)
    assert r1.context["page"].paginator.num_pages >= 2
    assert len(r1.context["alerts"]) == 50  # bir sahifada 50
    r2 = iclient.get("/signallar/?page=2", HTTP_HOST=INSPECTOR_HOST)
    assert r2.status_code == 200
    assert r2.context["page"].number == 2


@pytest.mark.django_db
def test_inventory_no_n_plus_1(iclient, market, django_assert_max_num_queries):
    """Ombor sahifasi do'kon soniga qarab N+1 bermasligi kerak."""
    from apps.geo.models import Row
    from apps.shops.models import Shop

    row = Row.objects.create(market=market, label="A")
    for i in range(20):
        s = Shop.objects.create(market=market, row=row, number=f"inv{i}", stir=f"{i}")
        Product.objects.create(shop=s, name="Mahsulot", sell_price=1000, stock=5)
    # 20 do'kon bo'lsa ham so'rov soni past va barqaror bo'lishi kerak
    with django_assert_max_num_queries(12):
        r = iclient.get("/ombor/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200


@pytest.mark.django_db
def test_dashboard_query_budget(iclient, shop, django_assert_max_num_queries):
    with django_assert_max_num_queries(20):
        r = iclient.get("/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200
