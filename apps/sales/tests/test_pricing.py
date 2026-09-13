"""Narxlash mantig'i testlari — sof funksiyalar (bazasiz)."""

from types import SimpleNamespace

from apps.sales.services import pricing

SETTINGS = SimpleNamespace(
    discount_percents=[5, 10, 15],
    max_discount_no_cost_pct=30,
    rounding_max=1000,
)


def test_discount_buttons_percent_based():
    # Uzbek savdolashish: chegirma chek summasining foizi (yaxlitlangan)
    # 20 000 (step 500): 5%→1000, 10%→2000, 15%→3000
    assert pricing.discount_buttons(20_000, [5, 10, 15], 6_000) == [1_000, 2_000, 3_000]
    # 200 000 (step 1000): 5%→10000, 10%→20000, 15%→30000
    assert pricing.discount_buttons(200_000, [5, 10, 15], 60_000) == [10_000, 20_000, 30_000]


def test_discount_buttons_capped():
    # cap past bo'lsa tugmalar cap dan oshmaydi va takror bo'lmaydi
    assert pricing.discount_buttons(200_000, [5, 10, 15], 12_000) == [10_000, 12_000]


def test_discount_buttons_empty_when_zero():
    assert pricing.discount_buttons(0, [5, 10, 15], 0) == []


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
    assert r.discount == 30_000  # tannarxga cheklandi
    assert r.rounding == 600
    assert r.total == 100_000 - 30_000 - 600


def test_price_sale_no_cost_uses_pct():
    r = pricing.price_sale(100_000, 90_000, 0, items_cost=None, settings=SETTINGS)
    assert r.discount == 30_000  # 30% chegara
    assert r.total == 70_000
