"""Jarima darajalari tasnifi testlari (sof funksiya)."""

from apps.analytics.fines import classify_hidden


def test_warning_tier_small():
    t = classify_hidden(3_000_000)
    assert t["code"] == "warning" and t["warning_only"] is True


def test_criminal_tier():
    t = classify_hidden(50_000_000)
    assert t["code"] == "crime" and t["is_criminal"] is True


def test_grave_tier():
    t = classify_hidden(200_000_000)
    assert t["code"] == "grave" and t["is_criminal"] is True


def test_repeat_escalates_one_tier():
    base = classify_hidden(8_000_000)          # small
    rep = classify_hidden(8_000_000, repeat=True)  # -> medium
    assert base["code"] == "small"
    assert rep["code"] == "medium"
    assert rep["repeat"] is True
