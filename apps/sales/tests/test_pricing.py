"""Narxlash mantig'i testlari — sof funksiyalar (bazasiz)."""
from types import SimpleNamespace

from apps.sales.services import pricing

SETTINGS = SimpleNamespace(
    discount_tiers=[
        [50_000, [2_000, 5_000, 10_000]],
        [200_000, [5_000, 10_000, 20_000]],
        [1_000_000, [10_000, 20_000, 50_000]],
        [3_000_000, [50_000, 100_000, 200_000]],
        [None, [100_000, 200_000, 300_000]],
    ],
    max_discount_no_cost_pct=30,
    rounding_max=1000,
)


def test_discount_buttons_by_tier():
    assert pricing.discount_buttons(40_000, SETTINGS.discount_tiers) == [2_000, 5_000, 10_000]
    assert pricing.discount_buttons(150_000, SETTINGS.discount_tiers) == [5_000, 10_000, 20_000]
    assert pricing.discount_buttons(9_000_000, SETTINGS.discount_tiers) == [100_000, 200_000, 300_000]


def test_max_discount_with_known_cost():
    # subtotal 100k, tannarx 70k → maks chegirma 30k
    assert pricing.max_discount(100_000, 70_000, 30) == 30_000


def test_max_discount_without_cost_capped_at_pct():
    # tannarx noma'lum → 30%
    assert pricing.max_discount(100_000, None, 30) == 30_000


def test_clamp_discount_respects_cost_floor():
    # 50k chegirma so'ralgan, lekin tannarx 70k → faqat 30k ruxsat
    assert pricing.clamp_discount(100_000, 50_000, 70_000, 30) == 30_000


def test_rounding_only_down_and_capped():
    assert pricing.apply_rounding(98_600, 600, 1000) == 600
    assert pricing.apply_rounding(98_600, 5000, 1000) == 1000  # maks 1000
    assert pricing.apply_rounding(98_600, 0, 1000) == 0


def test_price_sale_end_to_end():
    r = pricing.price_sale(100_000, 50_000, 600, items_cost=70_000, settings=SETTINGS)
    assert r.subtotal == 100_000
    assert r.discount == 30_000      # tannarxga cheklandi
    assert r.rounding == 600
    assert r.total == 100_000 - 30_000 - 600


def test_price_sale_no_cost_uses_pct():
    r = pricing.price_sale(100_000, 90_000, 0, items_cost=None, settings=SETTINGS)
    assert r.discount == 30_000      # 30% chegara
    assert r.total == 70_000
