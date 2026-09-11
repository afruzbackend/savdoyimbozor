"""
Rostlik darajasi — sof funksiyalar (spec 5-bo'lim formulalari).

Bu yerda faqat hisoblash mantig'i; ma'lumot yig'ish P3'da `recompute_for_date` ichida.
Funksiyalar sof (I/O yo'q) — test qilish oson va sudda tushuntirish mumkin.
"""

from __future__ import annotations


def match(a: float, b: float) -> float | None:
    """Ikki qiymat mosligi (%). Kam ham, ko'p ham yozsa tushadi.

    Biror qiymat 0 yoki noma'lum bo'lsa None (ma'lumot yetarli emas).
    """
    if not a or not b or a <= 0 or b <= 0:
        return None
    return min(a, b) / max(a, b) * 100.0


def price_score(
    avg_price: float, market_median: float, high: float = 0.8, low: float = 0.4
) -> float | None:
    """Narx balli: o'rtacha narx / bozor medianasi. ≥high→100, ≤low→0, orada chiziqli."""
    if not avg_price or not market_median or market_median <= 0:
        return None
    ratio = avg_price / market_median
    if ratio >= high:
        return 100.0
    if ratio <= low:
        return 0.0
    return (ratio - low) / (high - low) * 100.0


def weighted_truth(
    parts: dict[str, float | None],
    weights: dict[str, float],
    weakest_cap_bonus: float = 15.0,
    yellow_threshold: float = 50.0,
) -> dict:
    """Og'irlikli o'rtacha rostlik.

    - Ma'lumoti yo'q (None) qismlar chiqarib tashlanadi, og'irliklar qayta taqsimlanadi.
    - Eng zaif qism sariq chegaradan past bo'lsa: umumiy ball ≤ (o'sha qism + bonus).
      Sababi: bitta kuchli signal o'rtachada yo'qolib ketmasligi kerak.

    Qaytadi: {"truth": int, "weakest": str|"", "parts": {...}}
    """
    active = {k: v for k, v in parts.items() if v is not None}
    if not active:
        return {"truth": 0, "weakest": "", "parts": parts}

    total_w = sum(weights.get(k, 0) for k in active) or 1.0
    avg = sum(v * weights.get(k, 0) for k, v in active.items()) / total_w

    weakest_key = min(active, key=lambda k: active[k])
    weakest_val = active[weakest_key]

    truth = avg
    if weakest_val < yellow_threshold:
        truth = min(truth, weakest_val + weakest_cap_bonus)

    return {
        "truth": int(round(max(0.0, min(100.0, truth)))),
        "weakest": weakest_key if weakest_val < yellow_threshold else "",
        "parts": {k: (int(round(v)) if v is not None else None) for k, v in parts.items()},
    }


def level_for(truth: int, green: int, yellow: int) -> str:
    """Rang darajasi: ≥green yashil, ≥yellow sariq, aks holda qizil."""
    if truth >= green:
        return "green"
    if truth >= yellow:
        return "yellow"
    return "red"


def _median(values):
    vals = sorted(v for v in values if v)
    if not vals:
        return 0
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) // 2


def compute_market_prices(market, day):
    """Bozor narxi: har mahsulot toifasi uchun median sotish narxi (so'm)."""
    from apps.analytics.models import MarketPrice
    from apps.catalog.models import Product

    by_cat = {}
    for p in Product.objects.filter(
        shop__market=market, is_active=True, category__isnull=False, sell_price__gt=0
    ):
        by_cat.setdefault(p.category_id, []).append(p.sell_price)

    result = {}
    for cat_id, prices in by_cat.items():
        prices.sort()
        med = _median(prices)
        n = len(prices)
        p25 = prices[max(0, n // 4)]
        p75 = prices[min(n - 1, 3 * n // 4)]
        MarketPrice.objects.update_or_create(
            market=market,
            product_category_id=cat_id,
            date=day,
            defaults={"median": med, "p25": p25, "p75": p75},
        )
        result[cat_id] = med
    return result


def _shop_price_score(shop, medians):
    """Do'kon narx balli: mahsulotlari narxini bozor medianasi bilan solishtiradi."""
    from apps.catalog.models import Product

    scores = []
    for p in Product.objects.filter(
        shop=shop, is_active=True, category__isnull=False, sell_price__gt=0
    ):
        med = medians.get(p.category_id)
        s = price_score(p.sell_price, med)
        if s is not None:
            scores.append(s)
    if not scores:
        return None
    return sum(scores) / len(scores)


def _entered_sales(shop, day):
    from apps.sales.models import Sale

    return sum(s.total for s in Sale.objects.filter(shop=shop, created_at__date=day))


def _cash_declared(shop, day):
    from apps.cash.models import CashRecord

    return sum(c.amount for c in CashRecord.objects.filter(shop=shop, date=day))


def _stock_estimate(shop, day):
    """Qoldiq bo'yicha sotilgan qiymat: kun yakuni (DailyClose) asosida.

    Σ(ertalab + kirim + qaytgan − chiqarilgan − kechqurun) × narx.
    Kun yakuni kiritilmagan bo'lsa None (qoldiq qismi hisobga olinmaydi).
    """
    from apps.sales.models import DailyClose, StockIn

    close = DailyClose.objects.filter(shop=shop, date=day).prefetch_related("lines").first()
    if not close:
        return None
    value = 0
    for line in close.lines.all():
        sold_qty = float(line.morning_qty) - float(line.evening_qty)
        if sold_qty > 0:
            value += int(sold_qty * line.unit_price)
    # Kun ichidagi kirim qo'shiladi, hisobdan chiqarish/qaytarish tuzatiladi
    stock_in = sum(
        int(float(s.quantity) * s.unit_price)
        for s in StockIn.objects.filter(shop=shop, created_at__date=day)
    )
    value += stock_in
    # (WriteOff/SaleReturn summasi kelajakda narx bilan aniqroq ulanadi)
    return value if value > 0 else None


def _camera_estimate(shop, day, buyer_ratio):
    """Kamera bahosi: tashriflar × buyer_ratio × o'rtacha chek. Kamera bo'lmasa None."""
    from apps.cameras.models import CameraEvent

    visits = CameraEvent.objects.filter(shop=shop, type="visit", ts__date=day).count()
    if not visits:
        return None
    from apps.sales.models import Sale

    sales = list(Sale.objects.filter(shop=shop, created_at__date=day))
    if not sales:
        return None
    avg_check = sum(s.total for s in sales) / len(sales)
    return int(visits * float(buyer_ratio) * avg_check)


def recompute_for_date(day) -> int:
    """Berilgan kun uchun barcha faol do'kon rostlik ballarini qayta hisoblaydi.

    Har do'kon: kassa/kamera/narx (va qoldiq — mavjud bo'lsa) qismlari → weighted_truth →
    DailyScore. Yashil bo'lmasa va yopiq kun bo'lmasa → signal.
    """
    from apps.analytics.models import Alert, DailyScore
    from apps.core.models import SystemSettings
    from apps.geo.models import Market
    from apps.shops.models import Shop

    cfg = SystemSettings.get_solo()
    weights = {
        "cash": cfg.weight_cash,
        "camera": cfg.weight_camera,
        "stock": cfg.weight_stock,
        "price": cfg.weight_price,
    }

    # Bozor narxlarini oldindan hisoblaymiz (do'kon narx balli uchun)
    medians_by_market = {m.id: compute_market_prices(m, day) for m in Market.objects.all()}

    count = 0
    for shop in Shop.objects.filter(is_active=True).select_related("market"):
        entered = _entered_sales(shop, day)
        cash = _cash_declared(shop, day)
        cam = _camera_estimate(shop, day, cfg.buyer_ratio)
        stock_val = _stock_estimate(shop, day)
        price_val = _shop_price_score(shop, medians_by_market.get(shop.market_id, {}))

        parts = {
            "cash": match(cash, entered),
            "camera": match(cam, entered) if cam is not None else None,
            "stock": match(stock_val, entered) if stock_val is not None else None,
            "price": price_val,
        }
        result = weighted_truth(
            parts,
            weights,
            weakest_cap_bonus=cfg.weakest_part_cap,
            yellow_threshold=cfg.yellow_threshold,
        )

        DailyScore.objects.update_or_create(
            shop=shop,
            date=day,
            defaults={
                "truth_pct": result["truth"],
                "parts": result["parts"],
                "weakest": result["weakest"],
                "entered_sales": entered,
                "cash_amount": cash,
            },
        )
        count += 1

        # Signal (yopiq kun bo'lmasa, ma'lumot bo'lsa)
        if day.weekday() in shop.closed_weekday_list():
            continue
        if not any(v is not None for v in parts.values()):
            continue
        lvl = level_for(result["truth"], cfg.green_threshold, cfg.yellow_threshold)
        if lvl == "green":
            continue
        if Alert.objects.filter(shop=shop, date=day).exists():
            continue
        reason = _alert_reason(result, parts, entered, cash)
        alert = Alert.objects.create(
            shop=shop,
            date=day,
            level=lvl,
            reason=reason,
            assigned_to=shop.market.inspectors.first(),
        )
        # Qizil signal → inspektorga darrov Telegram (token bo'lsa; aks holda jim o'tadi)
        if lvl == "red":
            try:
                from apps.analytics.notifications import notify_alert

                notify_alert(alert)
            except Exception:  # noqa: BLE001 — xabar asosiy oqimni buzmasin
                pass
    return count


def _alert_reason(result, parts, entered, cash):
    weakest = result.get("weakest")
    if weakest == "cash" and entered:
        pct = round((1 - (cash / entered)) * 100) if entered else 0
        return f"Deklaratsiya kiritilgandan {pct}% past (kassa {int(cash):,} / savdo {int(entered):,} so'm)"
    if weakest == "price":
        return "Narx bozor medianasidan sezilarli past"
    if weakest == "camera":
        return "Kamera bahosi kiritilgan savdodan farq qilmoqda"
    return f"Rostlik darajasi past ({result['truth']}%)"
