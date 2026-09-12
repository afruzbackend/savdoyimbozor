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
    r = aclient.post(
        "/import/dokonlar/", {"market": market.pk, "file": f}, HTTP_HOST=PANEL_HOST
    )
    assert r.status_code == 302
    assert Shop.objects.filter(number="101", stir="111222333").exists()
    assert Shop.objects.filter(number="102").exists()


@pytest.mark.django_db
def test_import_cash(aclient, shop):
    f = _xlsx([
        ["STIR", "Sana", "Summa"],
        [shop.stir, "2026-09-10", 500000],
    ])
    r = aclient.post("/import/kassa/", {"file": f}, HTTP_HOST=PANEL_HOST)
    assert r.status_code == 302
    assert CashRecord.objects.filter(shop=shop, amount=500000).exists()
