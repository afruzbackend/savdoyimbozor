"""Rostlik dvigateli sof funksiyalari testlari (bazasiz)."""

from apps.analytics.scoring import services as s


def test_match_symmetric_and_none():
    assert s.match(100, 100) == 100
    assert round(s.match(50, 100)) == 50  # kam ko'rsatsa tushadi
    assert round(s.match(200, 100)) == 50  # ko'p ko'rsatsa ham tushadi
    assert s.match(0, 100) is None  # ma'lumot yo'q
    assert s.match(100, 0) is None


def test_price_score_bands():
    assert s.price_score(100, 100) == 100  # median = narx
    assert s.price_score(40, 100) == 0  # ≤0.4 → 0
    assert 40 < s.price_score(60, 100) < 70  # oraliqda chiziqli
    assert s.price_score(0, 100) is None


def test_weighted_truth_skips_missing_and_reweights():
    parts = {"cash": 90, "camera": None, "stock": 90, "price": None}
    w = {"cash": 35, "camera": 25, "stock": 25, "price": 15}
    r = s.weighted_truth(parts, w)
    assert r["truth"] == 90  # yo'q qismlar chiqarildi
    assert r["parts"]["camera"] is None


def test_weakest_part_caps_total():
    # Kassa 95 kuchli, lekin narx 5 — umumiy ball zaif qism + 15 dan oshmaydi
    parts = {"cash": 95, "camera": None, "stock": None, "price": 5}
    w = {"cash": 35, "camera": 25, "stock": 25, "price": 15}
    r = s.weighted_truth(parts, w, weakest_cap_bonus=15, yellow_threshold=50)
    assert r["truth"] <= 20
    assert r["weakest"] == "price"


def test_level_for():
    assert s.level_for(85, 80, 50) == "green"
    assert s.level_for(60, 80, 50) == "yellow"
    assert s.level_for(30, 80, 50) == "red"


def test_median():
    assert s._median([10, 20, 30]) == 20
    assert s._median([10, 20, 30, 40]) == 25
    assert s._median([]) == 0
