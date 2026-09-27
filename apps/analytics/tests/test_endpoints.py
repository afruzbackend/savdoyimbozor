"""Nazoratchi qolgan endpointlari: hisobot, eksport, ombor, kamera, tekshiruv, signal amali."""

import pytest
from django.utils import timezone

from apps.analytics.models import Alert, Inspection
from conftest import INSPECTOR_HOST


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path",
    ["/hisobot/", "/kameralar/", "/qidiruv/", "/tekshiruv/yangi/", "/ombor/"],
)
def test_inspector_get_pages(iclient, shop, path):
    assert iclient.get(path, HTTP_HOST=INSPECTOR_HOST).status_code == 200


@pytest.mark.django_db
def test_shop_inventory_page(iclient, shop, product):
    assert iclient.get(f"/ombor/dokon/{shop.pk}/", HTTP_HOST=INSPECTOR_HOST).status_code == 200


@pytest.mark.django_db
def test_excel_export(iclient, shop):
    r = iclient.get("/hisobot/eksport/", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code == 200
    assert "spreadsheet" in r["Content-Type"]


@pytest.mark.django_db
def test_shop_search_one_result_redirects(iclient, shop):
    r = iclient.get(f"/qidiruv/?q={shop.number}", HTTP_HOST=INSPECTOR_HOST)
    assert r.status_code in (200, 302)


@pytest.mark.django_db
def test_alert_action_dismiss(iclient, shop):
    a = Alert.objects.create(shop=shop, date=timezone.localdate(), level="red", reason="x")
    r = iclient.post(
        f"/signallar/{a.pk}/amal/", {"action": "dismiss"}, HTTP_HOST=INSPECTOR_HOST
    )
    assert r.status_code in (200, 302)
    a.refresh_from_db()
    assert a.status == Alert.Status.DISMISSED


@pytest.mark.django_db
def test_inspection_create(iclient, shop):
    r = iclient.post(
        "/tekshiruv/yangi/",
        {"shop": shop.pk, "result": "confirmed", "act_number": "A-1", "fine_level": "small",
         "notes": "test"},
        HTTP_HOST=INSPECTOR_HOST,
    )
    assert r.status_code == 302
    assert Inspection.objects.filter(shop=shop, result="confirmed").exists()
