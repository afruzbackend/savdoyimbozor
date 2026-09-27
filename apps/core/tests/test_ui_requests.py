"""Foydalanuvchi so'ragan tuzatishlar: rostlik "o'lchanmagan", do'kondan tekshiruv, band raqam xatosi,
savdo turi + mahsulot turlari (kamida 1), standart brauzer elementlari yo'q."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from apps.analytics.models import Alert, DailyScore
from apps.analytics.scoring.services import recompute_for_date
from apps.catalog.models import ProductCategory, ShopCategory
from apps.sales.models import Sale
from apps.shops.models import Shop
from conftest import INSPECTOR_HOST

PANEL_HOST = "panel.localhost"


@pytest.mark.django_db
def test_price_only_is_not_measured_and_no_truth_alert(shop, seller, product):
    """Kassa/kamera/sanoq yo'q, faqat narx — rostlik O'LCHANMAGAN (oldin 1 000 so'm yozgan do'kon 100% yashil edi)."""
    Sale.objects.create(shop=shop, seller=seller, subtotal=1000, total=1000, payment_type="cash")
    day = timezone.localdate()
    recompute_for_date(day, final=True)
    ds = DailyScore.objects.get(shop=shop, date=day)
    assert ds.parts["price"] is not None and ds.measured is False and ds.has_data is False
    assert not Alert.objects.filter(shop=shop, date=day, kind=Alert.Kind.TRUTH).exists()


@pytest.mark.django_db
def test_inspection_from_shop_page_preselects_shop(iclient, shop):
    r = iclient.get(f"/tekshiruv/yangi/?shop={shop.pk}", HTTP_HOST=INSPECTOR_HOST)
    assert r.context["preselect"] == shop
    html = r.content.decode()
    assert re.search(rf'value="{shop.pk}"\s+selected', html)


@pytest.mark.django_db
def test_taken_shop_number_is_an_error_not_silently_changed(aclient, shop):
    cat = shop.category
    ProductCategory.objects.create(name="Olma", shop_category=cat)
    before = Shop.objects.count()
    r = aclient.post("/hisob/yangi/", {"role": "seller", "mode": "new", "full_name": "Vali Aliyev",
                                       "number": shop.number, "stir": "987654321", "market": shop.market_id,
                                       "category": cat.pk}, HTTP_HOST=PANEL_HOST, follow=True)
    assert Shop.objects.count() == before  # 28 bo'lib ketmadi
    assert "band" in r.content.decode()
    # Bo'sh qoldirilsa — avtomatik keyingi raqam
    aclient.post("/hisob/yangi/", {"role": "seller", "mode": "new", "full_name": "Vali Aliyev", "number": "",
                                   "stir": "987654321", "market": shop.market_id, "category": cat.pk},
                 HTTP_HOST=PANEL_HOST)
    assert Shop.objects.count() == before + 1


@pytest.mark.django_db
def test_new_shop_category_requires_product_types_and_opens_them(aclient):
    r = aclient.post("/toifalar/", {"action": "add", "name": "Guruchlar", "product_types": " "},
                     HTTP_HOST=PANEL_HOST)
    assert not ShopCategory.objects.filter(name="Guruchlar").exists()
    r = aclient.post("/toifalar/", {"action": "add", "name": "Guruchlar", "default_unit": "kg",
                                    "product_types": "Lazer guruch, Devzira, lazer guruch"}, HTTP_HOST=PANEL_HOST)
    sc = ShopCategory.objects.get(name="Guruchlar")
    names = sorted(sc.product_categories.values_list("name", flat=True))
    assert names == ["Devzira", "Lazer guruch"]
    assert set(sc.product_categories.values_list("default_unit", flat=True)) == {"kg"}
    assert r.status_code == 302 and r["Location"].endswith(f"/mahsulot-turlari/?turi={sc.pk}")


@pytest.mark.django_db
def test_seller_account_needs_category_with_product_types(aclient, market):
    empty = ShopCategory.objects.create(name="Bo'sh tur")
    aclient.post("/hisob/yangi/", {"role": "seller", "mode": "new", "full_name": "Ali", "number": "",
                                   "stir": "123123123", "market": market.pk, "category": empty.pk},
                 HTTP_HOST=PANEL_HOST)
    assert not Shop.objects.filter(stir="123123123").exists()


def test_no_browser_default_widgets_left():
    """Standart fayl tanlagich, brauzer pattern-ogohlantirishi, → matnli tugmalar qolmagan."""
    base = Path(settings.BASE_DIR) / "templates"
    for f in base.rglob("*.html"):
        html = f.read_text(encoding="utf-8")
        for m in re.finditer(r'<input[^>]*type="file"[^>]*>', html):
            assert "hidden" in m.group(0), f"{f}: standart fayl tanlagich"
        assert 'pattern="' not in html, f"{f}: brauzer pattern-ogohlantirishi"
        assert not re.search(r"→\s*</a>|<a[^>]*>\s*←", html), f"{f}: strelkali matn-tugma"
    assert 'data-time' in (base / "inspector/inventory.html").read_text(encoding="utf-8")
