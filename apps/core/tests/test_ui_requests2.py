"""Foydalanuvchi so'rovlari (2): xarita tartibi va 1-2 kunlik hisob, jarima darajalari + dalolatnoma,
telefon/raqam formatlash, diagramma sanalari uzluksiz, yagona grafik palitrasi."""

import datetime
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from apps.analytics.models import DailyScore, Inspection
from apps.core.format import clean_phone
from apps.geo.models import Row
from apps.shops.models import Shop
from conftest import INSPECTOR_HOST

PANEL_HOST = "panel.localhost"
VOL = {"cash": 70, "camera": None, "stock": None, "price": 100}


def _score(shop, days_ago, truth, parts=VOL):
    return DailyScore.objects.create(
        shop=shop,
        date=timezone.localdate() - datetime.timedelta(days=days_ago),
        truth_pct=truth,
        entered_sales=100000,
        cash_amount=70000,
        parts=parts,
        measured=any(parts.get(k) is not None for k in ("cash", "camera", "stock")),
    )


# ---------------- Xarita ----------------
@pytest.mark.django_db
def test_map_counts_shop_with_one_or_two_measured_days(iclient, shop):
    """Bugun hisoblanmagan, 2 kun oldin bitta o'lchangan kun bor — xarita "—" emas, hisoblaydi."""
    _score(shop, 2, 64)
    r = iclient.get("/xarita/", HTTP_HOST=INSPECTOR_HOST)
    st = r.context["rows_data"][0]["stalls"][0]
    assert st["truth"] == 64 and st["days"] == 1 and st["level"] != "none"


@pytest.mark.django_db
def test_map_ignores_price_only_days(iclient, shop):
    _score(shop, 0, 100, parts={"cash": None, "camera": None, "stock": None, "price": 100})
    r = iclient.get("/xarita/", HTTP_HOST=INSPECTOR_HOST)
    assert r.context["rows_data"][0]["stalls"][0]["truth"] is None


@pytest.mark.django_db
def test_map_rows_in_admin_order_numbers_natural_boshqa_last(iclient, shop):
    m = shop.market
    shop.row.order = 2
    shop.row.save()
    first = Row.objects.create(market=m, label="Meva qatori", order=1)
    for n in ("10", "9", "11"):
        Shop.objects.create(market=m, row=first, category=shop.category, number=n, stir="1" * 9)
    Shop.objects.create(market=m, row=None, category=shop.category, number="25", stir="2" * 9)
    r = iclient.get("/xarita/", HTTP_HOST=INSPECTOR_HOST)
    rows = r.context["rows_data"]
    assert [x["label"] for x in rows] == ["Meva qatori", "A", "Boshqa"]
    assert [s["number"] for s in rows[0]["stalls"]] == ["9", "10", "11"]
    assert 'title="№' not in r.content.decode()  # brauzer tooltip'i emas — o'zimizniki (data-tip)


@pytest.mark.django_db
def test_dashboard_uses_recent_days(iclient, shop):
    _score(shop, 3, 41)
    r = iclient.get("/", HTTP_HOST=INSPECTOR_HOST)
    assert r.context["avg_truth"] == 41
    assert [s.shop_id for s, _lvl in r.context["risky"]] == [shop.pk]


@pytest.mark.django_db
def test_shop_page_matches_map(iclient, shop):
    """Bugun faqat narx (o'lchanmagan), 2 kun oldin o'lchangan — do'kon sahifasi ham xarita kabi 58%, "—" emas."""
    _score(shop, 2, 58)
    _score(shop, 0, 100, parts={"cash": None, "camera": None, "stock": None, "price": 100})
    r = iclient.get(f"/dokon/{shop.pk}/", HTTP_HOST=INSPECTOR_HOST)
    assert r.context["recent"]["truth"] == 58
    assert r.context["parts_day"].parts["cash"] == 70  # tarkib — oxirgi o'lchangan kundan
    assert "сентябр" not in r.content.decode()  # sana o'zbekcha


def test_migration_resets_stale_price_only_measured_flag(db, shop):
    import importlib

    from django.apps import apps

    stale = DailyScore.objects.create(
        shop=shop,
        date=timezone.localdate(),
        truth_pct=100,
        measured=True,
        parts={"cash": None, "camera": None, "stock": None, "price": 100},
    )
    good = _score(shop, 1, 80)
    importlib.import_module("apps.analytics.migrations.0015_fix_measured_flag").forwards(apps, None)
    stale.refresh_from_db()
    good.refresh_from_db()
    assert stale.measured is False and good.measured is True


# ---------------- Diagramma ----------------
def test_day_series_keeps_missing_days_as_gaps():
    from apps.analytics.charts import day_series

    d = datetime.date(2026, 9, 21)
    s = day_series(
        {
            d: {"entered": 5, "cash": 4, "truth": 90},
            d + datetime.timedelta(days=2): {"entered": 1, "cash": 1, "truth": 95},
        },
        d,
        d + datetime.timedelta(days=2),
    )
    assert s["labels"] == ["21.09", "22.09", "23.09"]
    assert s["entered"] == [5, None, 1] and s["truth"] == [90, None, 95]


def test_all_charts_use_shared_palette():
    """Hamma diagramma bitta yordamchi (BN.salesChart) va --chart-* tokenlari orqali — ko'k/terrakota qotirilmagan."""
    base = Path(settings.BASE_DIR)
    for tpl in ("inspector/shop_detail.html", "inspector/statistics.html", "seller/report.html"):
        src = (base / "templates" / tpl).read_text(encoding="utf-8")
        assert "BN.salesChart" in src and "new Chart" not in src and "--brand-300" not in src, tpl
    tokens = (base / "static/css/tokens.css").read_text(encoding="utf-8")
    assert tokens.count("--chart-1:") == 3  # light + dark + tizim dark


# ---------------- Jarima ----------------
@pytest.mark.django_db
def test_confirmed_inspection_requires_act_number_and_level(iclient, shop):
    r = iclient.post(
        "/tekshiruv/yangi/",
        {"shop": shop.pk, "result": "confirmed", "notes": "kassasiz"},
        HTTP_HOST=INSPECTOR_HOST,
    )
    assert r.status_code == 200 and not Inspection.objects.exists()
    html = r.content.decode()
    assert "dalolatnoma raqami majburiy" in html and "Jarima darajasini tanlang" in html
    assert "kassasiz" in html  # yozilganlar yo'qolmaydi


@pytest.mark.django_db
def test_fine_amount_comes_from_level_not_from_client(iclient, shop):
    from apps.core.models import SystemSettings

    cfg = SystemSettings.get_solo()
    r = iclient.post(
        "/tekshiruv/yangi/",
        {
            "shop": shop.pk,
            "result": "confirmed",
            "act_number": "A-77",
            "fine_level": "medium",
            "fine_amount": "1",
        },
        HTTP_HOST=INSPECTOR_HOST,
    )
    insp = Inspection.objects.get()
    assert (
        r.status_code == 302 and insp.fine_level == "medium" and insp.fine_amount == cfg.fine_medium
    )
    act = iclient.get(f"/tekshiruv/{insp.pk}/akt/", HTTP_HOST=INSPECTOR_HOST).content.decode()
    assert "O&#x27;rta" in act or "O'rta" in act
    assert "221-modda" in act and "Jami to" in act


@pytest.mark.django_db
def test_duplicate_act_number_rejected(iclient, shop):
    Inspection.objects.create(shop=shop, result="confirmed", act_number="BN-2026-00001")
    r = iclient.post(
        "/tekshiruv/yangi/",
        {
            "shop": shop.pk,
            "result": "confirmed",
            "act_number": "bn-2026-00001",
            "fine_level": "small",
        },
        HTTP_HOST=INSPECTOR_HOST,
    )
    assert r.status_code == 200 and Inspection.objects.count() == 1
    assert "allaqachon bor" in r.content.decode()


@pytest.mark.django_db
def test_false_signal_has_no_fine(iclient, shop):
    iclient.post(
        "/tekshiruv/yangi/",
        {"shop": shop.pk, "result": "false", "fine_level": "high"},
        HTTP_HOST=INSPECTOR_HOST,
    )
    insp = Inspection.objects.get()
    assert insp.fine_level == "" and insp.fine_amount is None


def test_fine_level_suggestion():
    from apps.analytics.fines import suggest_level

    assert suggest_level(1_000_000, 0) == "small"
    assert suggest_level(1_000_000, 1) == "medium"  # yil ichida takroran
    assert suggest_level(1_000_000, 2) == "high"
    assert suggest_level(50_000_000, 0) == "high"  # jinoyat miqyosi


@pytest.mark.django_db
def test_form_suggests_level_for_repeat_offender(iclient, shop):
    Inspection.objects.create(shop=shop, result="confirmed", act_number="X-1")
    r = iclient.get(f"/tekshiruv/yangi/?shop={shop.pk}", HTTP_HOST=INSPECTOR_HOST)
    assert r.context["fine_hints"][shop.pk]["level"] == "medium"
    assert [f["code"] for f in r.context["fine_levels"]] == ["small", "medium", "high"]


@pytest.mark.django_db
def test_panel_fine_amounts_must_be_ordered(aclient):
    from apps.core.models import SystemSettings

    aclient.post(
        "/sozlamalar/",
        {"fine_small": "30 000 000", "fine_medium": "10 000 000", "fine_high": "20 000 000"},
        HTTP_HOST=PANEL_HOST,
    )
    assert SystemSettings.get_solo().fine_small == 5_000_000  # rad etildi
    aclient.post(
        "/sozlamalar/",
        {"fine_small": "6 000 000", "fine_medium": "12 000 000", "fine_high": "24 000 000"},
        HTTP_HOST=PANEL_HOST,
    )
    cfg = SystemSettings.get_solo()
    assert (cfg.fine_small, cfg.fine_medium, cfg.fine_high) == (6_000_000, 12_000_000, 24_000_000)


# ---------------- Telefon / raqam ----------------
@pytest.mark.parametrize(
    "raw,out",
    [
        ("901234567", "+998 90 123 45 67"),
        ("+998 90 123-45-67", "+998 90 123 45 67"),
        ("998991234567", "+998 99 123 45 67"),
        ("8 90 123 45 67", "+998 90 123 45 67"),
        ("", ""),
        ("+998 ", ""),
        ("12345", None),
        ("+7 999 123 45 67", None),
    ],
)
def test_clean_phone(raw, out):
    assert clean_phone(raw) == out


@pytest.mark.django_db
def test_settings_phone_saved_in_one_format(sclient, seller):
    sclient.post("/profil/sozlamalar/", {"phone": "90 123 45 67"})
    seller.refresh_from_db()
    assert seller.phone == "+998 90 123 45 67"
    sclient.post("/profil/sozlamalar/", {"phone": "123"})
    seller.refresh_from_db()
    assert seller.phone == "+998 90 123 45 67"  # noto'g'ri raqam yozilmadi


def test_phone_and_number_inputs_are_masked():
    base = Path(settings.BASE_DIR) / "templates"
    for tpl in (
        "shell.html",
        "panel/account_create.html",
        "panel/shop_edit.html",
        "panel/user_edit.html",
        "seller/debts.html",
        "seller/sale.html",
        "seller/scan.html",
        "registration/settings.html",
    ):
        src = (base / tpl).read_text(encoding="utf-8")
        assert "data-phone" in src and 'placeholder="+998..."' not in src, tpl
    assert 'data-digits="9"' in (base / "panel/account_create.html").read_text(encoding="utf-8")
    for tpl in ("seller/home.html", "seller/register.html", "seller/daily_close.html"):
        src = (base / tpl).read_text(encoding="utf-8")
        assert "data-money" in src and 'type="number" name="opening_cash"' not in src, tpl
