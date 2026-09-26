"""Razmerli tovar: 36 — 10 juft, 37 — 50 juft; XL — 10, M — 100 ta. Har razmer alohida qoldiq."""

import json
from decimal import Decimal

import pytest

from apps.catalog.models import Product, ProductCategory
from apps.catalog.sizes import product_order, size_key
from apps.sales.models import StockIn
from apps.sales.services.quick_entry import parse
from conftest import SELLER_HOST, photo_file


@pytest.fixture
def shoes(shop):
    cat = ProductCategory.objects.create(name="Poyabzal")
    out = {}
    for sz in ("36", "37", "38"):
        out[sz] = Product.objects.create(shop=shop, name=f"Krossovka — {sz}", base_name="Krossovka",
                                         size=sz, category=cat, buy_price=150_000, sell_price=220_000)
    return out


@pytest.fixture
def shirts(shop):
    cat = ProductCategory.objects.create(name="Kiyim")
    return {sz: Product.objects.create(shop=shop, name=f"Futbolka — {sz}", base_name="Futbolka",
                                       size=sz, category=cat, buy_price=40_000, sell_price=65_000,
                                       low_stock_threshold=Decimal("5"))
            for sz in ("M", "XL")}


def _rows(text, shop):
    return parse(text, Product.objects.filter(shop=shop, is_active=True))


@pytest.mark.django_db
def test_parse_two_sizes_in_one_sentence(shop, shoes):
    rows = _rows("krossovka 36 razmerlik 10 ta 37 lik 50 ta", shop)
    assert [(r["product_id"], r["qty"], r["size"]) for r in rows] == [
        (shoes["36"].pk, "10", "36"), (shoes["37"].pk, "50", "37")]
    assert all(r["price"] == 150_000 for r in rows)  # 36/37 narx deb olinmadi


@pytest.mark.django_db
def test_parse_letter_sizes_and_name_carryover(shop, shirts):
    rows = _rows("futbolka XL 10 ta, M 100 ta", shop)
    assert [(r["product_id"], r["qty"]) for r in rows] == [(shirts["XL"].pk, "10"), (shirts["M"].pk, "100")]


@pytest.mark.django_db
def test_parse_new_size_becomes_variant_and_bare_number_size(shop, shoes, shirts):
    new = _rows("futbolka L 20 ta 45 mingdan", shop)[0]
    assert new["is_new"] and new["base_name"] == "Futbolka" and new["size"] == "L"
    assert new["product_name"] == "Futbolka — L" and new["price"] == 45_000
    bare = _rows("krossovka 38 5 ta", shop)[0]  # "38" — belgisiz, lekin modelda bor razmer
    assert bare["product_id"] == shoes["38"].pk and bare["qty"] == "5"


@pytest.mark.django_db
def test_parse_missing_size_asks_instead_of_guessing(shop, shirts):
    row = _rows("futbolka 10 ta", shop)[0]
    assert row["product_id"] is None and row["error"].startswith("razmerini tanlang")
    assert [c["size"] for c in row["choices"]] == ["M", "XL"]


@pytest.mark.django_db
def test_parse_units_still_work(shop):
    row = _rows("mato 5 m 30000", shop)[0]
    assert row["unit"] == "metr" and row["qty"] == "5" and not row["size"]


@pytest.mark.django_db
def test_quick_save_creates_variant_from_sibling_and_adds_stock(sclient, shop, shirts):
    rows = [{"product_id": shirts["M"].pk, "qty": "100", "price": 40_000, "size": "M"},
            {"product_id": None, "product_name": "Futbolka — L", "base_name": "Futbolka", "size": "l",
             "qty": "30", "price": 42_000}]
    # 5.26 mln so'm — nakladnoy fotosisiz rad etiladi (dalil qoidasi razmerli kirimda ham)
    sclient.post("/kirim/tez/saqlash/", {"rows": json.dumps(rows)}, HTTP_HOST=SELLER_HOST)
    assert not StockIn.objects.exists()
    r = sclient.post("/kirim/tez/saqlash/", {"rows": json.dumps(rows), "invoice_photo": photo_file()},
                     HTTP_HOST=SELLER_HOST)
    assert r.status_code == 302
    shirts["M"].refresh_from_db()
    assert shirts["M"].stock == 100
    new = Product.objects.get(shop=shop, base_name="Futbolka", size="L")
    assert new.stock == 30 and new.name == "Futbolka — L" and new.barcode
    assert new.category == shirts["M"].category and new.sell_price == 65_000  # qardosh razmerdan
    # Qayta kelsa — o'sha variant (dublikat yaratilmaydi)
    rows[1]["qty"] = "5"
    sclient.post("/kirim/tez/saqlash/", {"rows": json.dumps(rows[1:])}, HTTP_HOST=SELLER_HOST)
    assert Product.objects.filter(shop=shop, base_name="Futbolka", size="L").count() == 1
    assert StockIn.objects.filter(product=new).count() == 2


@pytest.mark.django_db
def test_stock_in_page_offers_size_grid(sclient, shoes):
    html = sclient.get("/kirim/", HTTP_HOST=SELLER_HOST).content.decode()
    assert "Razmerlar" in html and 'id="size-models"' in html and "Krossovka" in html


@pytest.mark.django_db
def test_products_page_shows_size_matrix(sclient, shop, shirts):
    shirts["M"].stock, shirts["XL"].stock = Decimal("100"), Decimal("3")
    shirts["M"].save(), shirts["XL"].save()
    html = sclient.get("/mahsulotlar/", HTTP_HOST=SELLER_HOST).content.decode()
    assert "Razmerlar bo'yicha qoldiq" in html or "Razmerlar bo&#x27;yicha qoldiq" in html
    assert 'class="size-stock low"' in html  # XL: 3 ≤ 5 — kam qoldi


def test_size_order():
    assert sorted(["XL", "S", "M", "XS", "L", "2XL"], key=size_key) == ["XS", "S", "M", "L", "XL", "2XL"]
    assert sorted(["40", "36", "110", "37"], key=size_key) == ["36", "37", "40", "110"]


@pytest.mark.django_db
def test_lists_keep_sizes_in_logical_order(shop, shirts):
    Product.objects.create(shop=shop, name="Futbolka — S", base_name="Futbolka", size="S")
    Product.objects.create(shop=shop, name="Anor", unit="kg")
    names = [p.name for p in sorted(Product.objects.filter(shop=shop), key=product_order)]
    assert names == ["Anor", "Futbolka — S", "Futbolka — M", "Futbolka — XL", "Pomidor"] or \
        names.index("Futbolka — S") < names.index("Futbolka — M") < names.index("Futbolka — XL")


@pytest.mark.django_db
def test_inspector_inventory_lists_sizes_in_order(iclient, shop, shirts):
    from conftest import INSPECTOR_HOST

    Product.objects.create(shop=shop, name="Futbolka — S", base_name="Futbolka", size="S", stock=7,
                           sell_price=65_000)
    for p in shirts.values():
        p.stock = Decimal("10")
        p.save()
    html = iclient.get(f"/ombor/dokon/{shop.pk}/", HTTP_HOST=INSPECTOR_HOST).content.decode()
    pos = [html.index(n) for n in ("Futbolka — S", "Futbolka — M", "Futbolka — XL")]
    assert pos == sorted(pos)  # qiymat bo'yicha emas — model → razmer tartibida


@pytest.mark.django_db
def test_scan_lookup_finds_by_name_and_size_in_order_with_stock(sclient, shop, shirts):
    Product.objects.create(shop=shop, name="Futbolka — S", base_name="Futbolka", size="S")
    r = sclient.get("/api/products/lookup/?q=futbolka", HTTP_HOST=SELLER_HOST).json()
    assert [x["size"] for x in r] == ["S", "M", "XL"] and "stock" in r[0]
    r = sclient.get("/api/products/lookup/?q=futbolka m", HTTP_HOST=SELLER_HOST).json()
    assert [x["name"] for x in r] == ["Futbolka — M"]
