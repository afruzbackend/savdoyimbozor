"""Har mahsulot turiga o'z varianti: choyga 3XL emas — qadoq (250 g); guruchga variant yo'q;
poyabzalga 35–46. Forma, server tekshiruvi, tez kirim va panel bir manbadan (variants.py)."""

import json
import re
from decimal import Decimal

import pytest

from apps.catalog import variants
from apps.catalog.models import Product, ProductCategory, VariantKind
from apps.catalog.sizes import size_key
from apps.sales.models import StockIn
from apps.sales.services.quick_entry import parse
from conftest import SELLER_HOST, photo_file

PANEL_HOST = "panel.localhost"


def test_kinds_match_model_choices():
    assert set(variants.KINDS) == set(VariantKind.values)


@pytest.mark.parametrize("name,kind", [
    ("Choy", "pack_weight"), ("Guruch", "none"), ("Pomidor", "none"), ("Krossovka", "shoes"),
    ("Poyabzal", "shoes"), ("Futbolka", "clothing"), ("Paypoq", "socks"), ("Bosh kiyim", "headwear"),
    ("Bolalar ko'ylagi", "kids"), ("Yog'", "pack_volume"), ("Batareyka", "type"), ("Atirgul", "color"),
])
def test_guess_kind_from_name(name, kind):
    assert variants.guess(name)[0] == kind


def test_guess_gives_category_specific_options():
    assert variants.guess("Choy") == ("pack_weight", "100 g, 250 g, 500 g, 1 kg")
    assert variants.guess("Ko'ylak", "Kiyim-kechak")[0] == "clothing"


@pytest.mark.parametrize("raw,kind,out", [
    ("250G", "", "250 g"), ("0.5l", "", "0,5 L"), ("250", "pack_weight", "250 g"),
    ("1", "pack_weight", "1 kg"), ("5", "pack_volume", "5 L"), ("500", "pack_volume", "500 ml"),
    ("xl", "clothing", "XL"), ("3xl", "clothing", "3XL"), ("xxs", "", "XXS"), ("36", "shoes", "36"),
])
def test_normalize(raw, kind, out):
    assert variants.normalize(raw, kind) == out


def test_measure_order_and_equality():
    assert sorted(["1 kg", "250 g", "500 g", "100 g"], key=size_key) == ["100 g", "250 g", "500 g", "1 kg"]
    assert sorted(["5 L", "0,5 L", "1 L"], key=size_key) == ["0,5 L", "1 L", "5 L"]
    assert sorted(["41-43", "35-37", "38-40"], key=size_key) == ["35-37", "38-40", "41-43"]
    assert variants.same("250g", "0,25 kg") and variants.same("xl", "XL") and not variants.same("M", "L")


def test_option_list_keeps_decimal_comma():
    assert variants.split_list("0,5 L, 1 L;5 L") == ["0,5 L", "1 L", "5 L"]
    assert variants.split_list("50g,100g, 1,5 kg") == ["50g", "100g", "1,5 kg"]
    yog = ProductCategory(name="Yog'", variant_kind="pack_volume", variant_options="0,5 L, 1 L, 3 L, 5 L")
    assert variants.spec(yog)["presets"] == {"Tayyor": ["0,5 L", "1 L", "3 L", "5 L"]}


def test_size_class():
    assert variants.size_class(["250 g", "1 kg"]) == "pack"
    assert variants.size_class(["M", "XL", "36", "35-37"]) == "size"
    assert variants.size_class(["AA", "AAA"]) == "type"


@pytest.mark.django_db
def test_new_category_guesses_kind_unless_admin_chose():
    assert ProductCategory.objects.create(name="Krossovka").variant_kind == "shoes"
    c = ProductCategory(name="Choy sovg'a to'plami", variant_kind="none")
    c.kind_explicit = True
    c.save()
    assert c.variant_kind == "none"  # admin aniq tanladi — taxmin qilinmaydi


@pytest.fixture
def cats(db):
    return {n: ProductCategory.objects.create(name=n, default_unit=u)
            for n, u in (("Choy", "dona"), ("Guruch", "kg"), ("Kurtka", "dona"), ("Yog'", "litr"))}


def _add(sclient, cat, **extra):
    data = {"category": cat.pk, "unit": cat.default_unit, "buy_price": "20000", "sell_price": "25000"}
    data.update(extra)
    return sclient.post("/mahsulotlar/", data, HTTP_HOST=SELLER_HOST, follow=True)


@pytest.mark.django_db
def test_tea_rejects_clothing_size_and_color(sclient, shop, cats):
    r = _add(sclient, cats["Choy"], sizes=["XL", "3XL"])
    assert not Product.objects.filter(shop=shop).exists()
    assert "Qadoq og" in r.content.decode()
    _add(sclient, cats["Choy"], sizes=["250 g"], colors="qora")
    assert not Product.objects.filter(shop=shop).exists()  # choyga rang yo'q


@pytest.mark.django_db
def test_tea_pack_variants_created_normalized(sclient, shop, cats):
    _add(sclient, cats["Choy"], sizes=["250", "1 kg", "250g"])
    names = sorted(Product.objects.filter(shop=shop).values_list("name", flat=True))
    assert names == ["Choy — 1 kg", "Choy — 250 g"]  # "250" va "250g" — bitta qadoq


@pytest.mark.django_db
def test_rice_and_bulk_units_have_no_variants(sclient, shop, cats):
    _add(sclient, cats["Guruch"], sizes=["M"])
    _add(sclient, cats["Yog'"], sizes=["1 L"])  # litr bilan (quyma) — qadoq emas
    _add(sclient, cats["Kurtka"], sizes=["250 g"])  # kiyimga gramm bo'lmaydi
    assert not Product.objects.filter(shop=shop).exists()
    _add(sclient, cats["Yog'"], unit="dona", sizes=["1 L", "5"])  # butilkada — dona
    assert set(Product.objects.filter(shop=shop).values_list("size", flat=True)) == {"1 L", "5 L"}


@pytest.mark.django_db
def test_products_page_sends_per_category_rules(sclient, shop, cats):
    html = sclient.get("/mahsulotlar/", HTTP_HOST=SELLER_HOST).content.decode()
    data = json.loads(re.search(r'id="catalog-data"[^>]*>(.*?)</script>', html, re.S).group(1))
    by = {c["name"]: c for c in data}
    assert by["Choy"]["pack"] and by["Choy"]["presets"] == {"Tayyor": ["100 g", "250 g", "500 g", "1 kg"]}
    assert by["Guruch"]["noun"] == "" and not by["Guruch"]["colors"]  # variant bo'limi chiqmaydi
    assert "XL" in by["Kurtka"]["presets"]["Harfli"] and by["Kurtka"]["colors"]
    assert "3XL" not in json.dumps(by["Choy"])


@pytest.fixture
def tea(shop, cats):
    return {sz: Product.objects.create(shop=shop, name=f"Choy — {sz}", base_name="Choy", size=sz,
                                       category=cats["Choy"], buy_price=p, sell_price=p + 5000)
            for sz, p in (("250 g", 20_000), ("1 kg", 70_000))}


def _rows(text, shop):
    return parse(text, Product.objects.filter(shop=shop, is_active=True))


@pytest.mark.django_db
def test_quick_entry_understands_packs(shop, tea):
    rows = _rows("choy 250 g 10 ta, 1 kg 5 ta", shop)
    assert [(r["product_id"], r["qty"]) for r in rows] == [(tea["250 g"].pk, "10"), (tea["1 kg"].pk, "5")]
    assert _rows("choy 250 grammlik 4 ta", shop)[0]["product_id"] == tea["250 g"].pk
    assert _rows("choy 250 3 ta", shop)[0]["product_id"] == tea["250 g"].pk  # belgisiz, lekin bitta mos
    ask = _rows("choy 10 ta", shop)[0]
    assert ask["product_id"] is None and ask["error"].startswith("qadog'ini tanlang")
    assert [c["size"] for c in ask["choices"]] == ["250 g", "1 kg"]


@pytest.mark.django_db
def test_quick_entry_weight_is_still_quantity_for_bulk(shop, product):
    row = _rows("pomidor 15 kg", shop)[0]
    assert row["product_id"] == product.pk and row["qty"] == "15" and not row["size"]


@pytest.mark.django_db
def test_quick_save_new_pack_does_not_copy_other_pack_price(sclient, shop, tea):
    rows = [{"product_id": None, "product_name": "Choy — 500 g", "base_name": "Choy", "size": "500g",
             "qty": "10", "price": 38_000}]
    r = sclient.post("/kirim/tez/saqlash/", {"rows": json.dumps(rows), "invoice_photo": photo_file()},
                     HTTP_HOST=SELLER_HOST, follow=True)
    new = Product.objects.get(shop=shop, base_name="Choy", size="500 g")
    assert new.stock == Decimal("10") and new.buy_price == 38_000 and new.category == tea["1 kg"].category
    assert new.sell_price == 0  # 250 g narxida sotilib ketmasin
    assert "Sotish narxini" in r.content.decode()
    assert StockIn.objects.filter(product=new).count() == 1


@pytest.mark.django_db
def test_section_titles_follow_variant_kind(sclient, shop, tea):
    html = sclient.get("/kirim/", HTTP_HOST=SELLER_HOST).content.decode()
    assert "Qadoqlar</button>" in html
    html = sclient.get("/mahsulotlar/", HTTP_HOST=SELLER_HOST).content.decode()
    assert "Qadoqlar bo&#x27;yicha qoldiq" in html or "Qadoqlar bo'yicha qoldiq" in html


@pytest.mark.django_db
def test_panel_manages_product_categories(aclient, cats):
    r = aclient.get("/mahsulot-turlari/", HTTP_HOST=PANEL_HOST)
    assert r.status_code == 200 and "Choy" in r.content.decode()
    aclient.post("/mahsulot-turlari/", {"action": "add", "name": "Choy sovg'a to'plami",
                                        "variant_kind": "none", "default_unit": "dona"},
                 HTTP_HOST=PANEL_HOST)
    assert ProductCategory.objects.get(name="Choy sovg'a to'plami").variant_kind == "none"
    aclient.post("/mahsulot-turlari/", {"action": "edit", "id": cats["Choy"].pk, "name": "Choy",
                                        "variant_kind": "pack_weight", "default_unit": "dona",
                                        "variant_options": "50g, 100, 1 kg"}, HTTP_HOST=PANEL_HOST)
    cats["Choy"].refresh_from_db()
    assert cats["Choy"].variant_options == "50 g, 100 g, 1 kg"
    # Qadoq turiga razmer yozib bo'lmaydi
    aclient.post("/mahsulot-turlari/", {"action": "edit", "id": cats["Choy"].pk, "name": "Choy",
                                        "variant_kind": "pack_weight", "default_unit": "dona",
                                        "variant_options": "XL"}, HTTP_HOST=PANEL_HOST)
    cats["Choy"].refresh_from_db()
    assert cats["Choy"].variant_options == "50 g, 100 g, 1 kg"


@pytest.mark.django_db
def test_panel_does_not_delete_used_category(aclient, tea, cats):
    aclient.post("/mahsulot-turlari/", {"action": "delete", "id": cats["Choy"].pk}, HTTP_HOST=PANEL_HOST)
    assert ProductCategory.objects.filter(pk=cats["Choy"].pk).exists()
    aclient.post("/mahsulot-turlari/", {"action": "delete", "id": cats["Guruch"].pk}, HTTP_HOST=PANEL_HOST)
    assert not ProductCategory.objects.filter(pk=cats["Guruch"].pk).exists()


@pytest.mark.django_db
def test_seller_cannot_reach_panel_categories(sclient):
    assert sclient.get("/mahsulot-turlari/", HTTP_HOST=SELLER_HOST).status_code == 404
