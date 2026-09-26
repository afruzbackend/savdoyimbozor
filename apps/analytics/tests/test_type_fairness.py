"""Savdo turiga qarab adolatli baholash: kamera ulushi, hafta kuni, dalil kuchi, solishtiruv."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.analytics.models import DailyScore
from apps.analytics.scoring.services import (
    _anomaly_baseline,
    buyer_ratio_for,
    recompute_for_date,
    suggested_buyer_ratios,
)
from apps.cameras.models import Camera, CameraEvent
from apps.catalog.models import Product, ProductCategory, ShopCategory
from apps.sales.models import Sale, SaleItem
from apps.shops.models import Shop
from conftest import INSPECTOR_HOST, SELLER_HOST, set_settings

PANEL_HOST = "panel.localhost"


def _visits(shop, n, day=None):
    cam, _ = Camera.objects.get_or_create(shop=shop, market=shop.market, defaults={"name": "k"})
    ts = timezone.make_aware(timezone.datetime.combine(day or timezone.localdate(), timezone.datetime.min.time())
                             + timedelta(hours=12))
    CameraEvent.objects.bulk_create([CameraEvent(camera=cam, shop=shop, type="visit", count=1, ts=ts)
                                     for _ in range(n)])


def _sales(shop, n, amount):
    Sale.objects.bulk_create([Sale(shop=shop, total=amount, subtotal=amount, payment_type="cash")
                              for _ in range(n)])


# ---------- Kamera: xaridor ulushi savdo turiga qarab ----------

@pytest.mark.django_db
def test_buyer_ratio_per_shop_category(shop):
    set_settings(buyer_ratio=Decimal("0.35"))
    from apps.core.models import SystemSettings

    cfg = SystemSettings.get_solo()
    assert buyer_ratio_for(shop, cfg) == 0.35  # tur ulushi yo'q — umumiy
    shop.category.buyer_ratio = Decimal("0.25")
    shop.category.save()
    shop.refresh_from_db()
    assert buyer_ratio_for(shop, cfg) == 0.25


@pytest.mark.django_db
def test_honest_clothing_shop_not_flagged_by_camera(shop):
    """Kiyim do'koni: 40 kishi keldi, 10 tasi oldi (25%). Umumiy 0,35 bilan kamera "14 ta sotuv
    bo'lishi kerak" deb 71% berardi; turning 0,25 ulushi bilan — 100%."""
    set_settings(buyer_ratio=Decimal("0.35"))
    day = timezone.localdate()
    _visits(shop, 40)
    _sales(shop, 10, 100_000)
    recompute_for_date(day)
    assert DailyScore.objects.get(shop=shop, date=day).parts["camera"] == 71
    shop.category.buyer_ratio = Decimal("0.25")
    shop.category.save()
    recompute_for_date(day)
    assert DailyScore.objects.get(shop=shop, date=day).parts["camera"] == 100


@pytest.mark.django_db
def test_suggested_ratio_uses_only_green_shop_days(shop):
    set_settings(green_threshold=80)
    today = timezone.localdate()
    for d in range(1, 7):
        day = today - timedelta(days=d)
        DailyScore.objects.create(shop=shop, date=day, truth_pct=95, measured=True)
        _visits(shop, 20, day)
        ts = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()) + timedelta(hours=12))
        for _ in range(5):
            s = Sale.objects.create(shop=shop, total=1, subtotal=1, payment_type="cash")
            Sale.objects.filter(pk=s.pk).update(created_at=ts)
    ratio, days = suggested_buyer_ratios()[shop.category_id]
    assert (ratio, days) == (0.25, 6)
    DailyScore.objects.filter(shop=shop).update(truth_pct=30)  # yashiruvchi kunlar hisobga kirmaydi
    assert shop.category_id not in suggested_buyer_ratios()


@pytest.mark.django_db
def test_panel_sets_category_ratio(aclient, shop):
    aclient.post("/toifalar/", {"action": "ratio", "id": shop.category_id, "buyer_ratio": "0,3"},
                 HTTP_HOST=PANEL_HOST)
    shop.category.refresh_from_db()
    assert shop.category.buyer_ratio == Decimal("0.30")
    aclient.post("/toifalar/", {"action": "ratio", "id": shop.category_id, "buyer_ratio": "5"},
                 HTTP_HOST=PANEL_HOST)
    shop.category.refresh_from_db()
    assert shop.category.buyer_ratio == Decimal("0.30")  # noto'g'ri — rad
    aclient.post("/toifalar/", {"action": "ratio", "id": shop.category_id, "buyer_ratio": ""},
                 HTTP_HOST=PANEL_HOST)
    shop.category.refresh_from_db()
    assert shop.category.buyer_ratio is None  # bo'sh — umumiy sozlamaga qaytadi
    assert aclient.get("/toifalar/", HTTP_HOST=PANEL_HOST).status_code == 200


# ---------- Anomaliya: bir xil hafta kuni bilan ----------

def test_anomaly_compares_same_weekday():
    monday = date(2026, 9, 21)
    prior = []
    for w in range(1, 9):
        prior.append((monday - timedelta(weeks=w), 300_000))  # dushanbalar sust
        prior.append((monday - timedelta(weeks=w) - timedelta(days=1), 2_000_000))  # yakshanbalar gavjum
    avg, label = _anomaly_baseline(monday, prior)
    assert avg == 300_000 and "dushanba" in label  # 30 kun o'rtachasi ~1,15 mln — soxta signal berardi


def test_anomaly_falls_back_to_recent_days():
    day = date(2026, 9, 21)
    prior = [(day - timedelta(days=d), 100_000) for d in (2, 3, 4, 5, 6)]
    assert _anomaly_baseline(day, prior) == (100_000, "odatda")
    assert _anomaly_baseline(day, prior[:3]) is None


# ---------- Solishtiruv: tannarxga yaqin sotuvlar o'xshash do'konlar bilan ----------

@pytest.mark.django_db
def test_near_cost_shown_with_peer_share(iclient, shop, product):
    peer = Shop.objects.create(market=shop.market, row=shop.row, category=shop.category, number="2",
                               stir="222", owner_name="Vali")
    pp = Product.objects.create(shop=peer, name="Pomidor", category=product.category, buy_price=8000,
                                sell_price=12000)
    for p, sh, price in ((product, shop, 8500), (pp, peer, 8600)):  # ikkalasida ham ustama ~6%
        s = Sale.objects.create(shop=sh, total=price, subtotal=price, payment_type="cash")
        SaleItem.objects.create(sale=s, product=p, product_name=p.name, quantity=1, unit_price=price,
                                line_total=price)
    inv = iclient.get(f"/dokon/{shop.pk}/", HTTP_HOST=INSPECTOR_HOST).context["invest"]
    assert inv["near_cost_pct"] == 100 and inv["peer_near_cost_pct"] == 100
    assert inv["near_cost_flag"] is False  # shu turda hamma shunday — shubhali emas


# ---------- Reyting: mahsulot turi bo'yicha, summa bilan ----------

@pytest.mark.django_db
def test_product_rating_by_type_and_amount(sclient, shop):
    cat = ProductCategory.objects.create(name="Choy")
    other = Shop.objects.create(market=shop.market, row=shop.row, category=shop.category, number="2",
                                stir="333", owner_name="Vali")
    mine = [Product.objects.create(shop=shop, name=f"Choy — {sz}", base_name="Choy", size=sz, category=cat)
            for sz in ("250 g", "1 kg")]
    theirs = Product.objects.create(shop=other, name="Choy", category=cat, unit="kg")
    for p, qty, price in ((mine[0], 10, 25_000), (mine[1], 2, 90_000), (theirs, 3, 90_000)):
        s = Sale.objects.create(shop=p.shop, total=qty * price, subtotal=qty * price, payment_type="cash")
        SaleItem.objects.create(sale=s, product=p, product_name=p.name, quantity=qty, unit_price=price,
                                line_total=qty * price)
    ranks = sclient.get("/reyting/", HTTP_HOST=SELLER_HOST).context["product_ranks"]
    # Men: 250 000 + 180 000 = 430 000 (ikki qadoq birga) > qo'shni 270 000 (3 kg quyma)
    assert ranks == [{"name": "Choy", "pos": 1, "total": 2, "amount": 430_000}]


@pytest.mark.django_db
def test_new_shop_category_has_no_ratio_until_admin_sets():
    assert ShopCategory.objects.create(name="Kiyim-kechak").buyer_ratio is None
