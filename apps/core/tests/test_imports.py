"""Bosh admin Excel importlari: do'konlar va kassa/deklaratsiya."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cash.models import CashRecord
from apps.shops.models import Shop

PANEL_HOST = "panel.localhost"


def _xlsx(rows):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(
        "f.xlsx", buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@pytest.mark.django_db
def test_import_shops(aclient, market):
    f = _xlsx([
        ["Raqam", "STIR", "Egasi", "Telefon", "Toifa", "Qator"],
        ["101", "111222333", "Ali Aliyev", "+998901112233", "", ""],
        ["102", "444555666", "Vali Valiyev", "+998907778899", "", ""],
    ])
    from apps.catalog.models import ShopCategory

    cat = ShopCategory.objects.create(name="Meva")
    r = aclient.post(
        "/import/dokonlar/", {"market": market.pk, "file": f, "category": cat.pk},
        HTTP_HOST=PANEL_HOST,
    )
    assert r.status_code == 302
    assert Shop.objects.filter(number="101", stir="111222333", category=cat).exists()
    assert Shop.objects.filter(number="102").exists()


@pytest.mark.django_db
def test_import_shops_without_category_skipped(aclient, market):
    f = _xlsx([
        ["Raqam", "STIR", "Egasi", "Telefon", "Toifa", "Qator"],
        ["201", "111222333", "Ali", "", "", ""],
    ])
    aclient.post("/import/dokonlar/", {"market": market.pk, "file": f}, HTTP_HOST=PANEL_HOST)
    assert not Shop.objects.filter(number="201").exists()


@pytest.mark.django_db
def test_import_bad_file_no_crash(aclient, market):
    bad = SimpleUploadedFile("x.xlsx", b"not an excel file")
    r = aclient.post("/import/dokonlar/", {"market": market.pk, "file": bad}, HTTP_HOST=PANEL_HOST)
    assert r.status_code == 302
    bad = SimpleUploadedFile("x.xlsx", b"not an excel file")
    r = aclient.post("/import/kassa/", {"file": bad}, HTTP_HOST=PANEL_HOST)
    assert r.status_code == 302


@pytest.mark.django_db
def test_import_cash_rejects_future_date(aclient, shop):
    f = _xlsx([["STIR", "Sana", "Summa"], [shop.stir, "2099-01-01", 5000]])
    aclient.post("/import/kassa/", {"file": f}, HTTP_HOST=PANEL_HOST)
    assert not CashRecord.objects.filter(shop=shop).exists()


@pytest.mark.django_db
def test_import_cash(aclient, shop):
    f = _xlsx([
        ["STIR", "Sana", "Summa"],
        [shop.stir, "2026-09-10", 500000],
    ])
    r = aclient.post("/import/kassa/", {"file": f}, HTTP_HOST=PANEL_HOST)
    assert r.status_code == 302
    assert CashRecord.objects.filter(shop=shop, amount=500000).exists()
