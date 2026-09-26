"""
Rostlik darajasi — sof funksiyalar (spec 5-bo'lim formulalari).

Bu yerda faqat hisoblash mantig'i; ma'lumot yig'ish P3'da `recompute_for_date` ichida.
Funksiyalar sof (I/O yo'q) — test qilish oson va sudda tushuntirish mumkin.
"""

from __future__ import annotations

from apps.core.dates import on_day
from apps.core.format import som


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

    return sum(s.total for s in Sale.objects.filter(shop=shop, **on_day("created_at", day)))


def _has_stock(shop):
    """Do'konda sotuvga tovar bormi (nol-savdo signalini asoslaydi)."""
    from apps.catalog.models import Product

    return Product.objects.filter(shop=shop, is_active=True, stock__gt=0).exists()


def _cash_declared(shop, day):
    # Manbalar QO'SHILMAYDI — eng ishonchlisi (Soliq API > kassa > Excel)
    from apps.cash.services import declared_for

    return declared_for(shop, day)


def _stock_estimate(shop, day):
    """Qoldiq bo'yicha sotilgan qiymat: kun yakuni (DailyClose) asosida.

    Σ(ertalab + kirim − chiqarilgan − qaytarilgan − kechqurun) × narx — apps.sales.services.stock.
    Kun yakuni kiritilmagan bo'lsa None (qoldiq qismi hisobga olinmaydi).
    """
    from apps.sales.models import DailyClose
    from apps.sales.services.stock import close_sold_value

    close = DailyClose.objects.filter(shop=shop, date=day).prefetch_related("lines").first()
    if not close:
        return None
    value = close_sold_value(close)
    return value if value and value > 0 else None


def _camera_estimate(shop, day, buyer_ratio, market_avg_check=0):
    """Kamera bahosi: tashriflar × buyer_ratio × o'rtacha chek. Kamera bo'lmasa None.

    O'rtacha chek — BOZOR bo'yicha (o'z chekiga emas): shunda sotuvchi har chekni
    arzon yozib kamera bahosini pasaytira olmaydi (mustaqillik kuchayadi).
    """
    from apps.cameras.models import CameraEvent

    visits = CameraEvent.objects.filter(shop=shop, type="visit", **on_day("ts", day)).count()
    if not visits:
        return None
    from apps.sales.models import Sale

    sales = list(Sale.objects.filter(shop=shop, **on_day("created_at", day)))
    own_avg = (sum(s.total for s in sales) / len(sales)) if sales else 0
    # Bozor o'rtachasi bilan o'z o'rtachasining KATTASI — pasaytirib aldashni to'sadi
    avg_check = max(own_avg, market_avg_check or 0)
    if avg_check <= 0:
        return None
    return int(visits * float(buyer_ratio) * avg_check)


def refresh_today_if_stale(seconds: int = 12) -> bool:
    """Bugungi rostlik ballari eskirgan bo'lsa qayta hisoblaydi (throttled).

    Sotuvdan keyin chaqiriladi — nazoratchi deyarli darhol yangi savdoni ko'radi.
    Har `seconds` da ko'pi bilan bir marta ishlaydi (tez-tez sotuvda yuk oshmasin).
    Qaytadi: recompute qilindimi (bool).
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.analytics.models import DailyScore

    today = timezone.localdate()
    newest = (
        DailyScore.objects.filter(date=today)
        .order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
    )
    if newest is not None and (timezone.now() - newest) < timedelta(seconds=seconds):
        return False
    try:
        ensure_finalized(today - timedelta(days=1))
        recompute_for_date(today)
        return True
    except Exception:  # noqa: BLE001 — sotuv baribir yozilsin
        return False


def ensure_finalized(day) -> bool:
    """O'tgan kunni (signallari bilan) bir marta yakuniy hisoblaydi.

    Celery beat (01:00) bo'lmagan muhitda ham kechagi signallar yo'qolmasin.
    Idempotent: signal (do'kon, kun, tur) bo'yicha takrorlanmaydi.
    """
    from django.core.cache import cache

    key = f"bn:finalized:{day.isoformat()}"
    if cache.get(key):
        return False
    recompute_for_date(day, final=True)
    cache.set(key, 1, 60 * 60 * 36)
    return True


def recompute_for_date(day, final: bool | None = None) -> int:
    """Berilgan kun uchun barcha faol do'kon rostlik ballarini qayta hisoblaydi.

    Har do'kon: kassa/kamera/narx (va qoldiq — mavjud bo'lsa) qismlari → weighted_truth →
    DailyScore. Yashil bo'lmasa va yopiq kun bo'lmasa → signal.

    final: kun TUGAGANmi. Tugamagan kun (bugun) uchun faqat ball yangilanadi (xarita jonli),
    SIGNAL YARATILMAYDI — ertalab hali sotmagan har do'konga "savdo yo'q", har kunlik
    o'rtachaga yetmagan savdoga "keskin tushdi" degan soxta qizil signallar chiqardi.
    None → avtomatik: kecha va undan oldingi kunlar yakuniy.
    """
    from django.utils import timezone as _tz

    if final is None:
        final = day < _tz.localdate()
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

    # === BATCHING: N+1 o'rniga bittalik agregat so'rovlar (300 do'konda ham tez) ===
    from collections import defaultdict
    from datetime import timedelta

    from django.db.models import Count, Sum

    from apps.cameras.models import CameraEvent
    from apps.catalog.models import Product
    from apps.sales.models import DailyClose, Sale

    shops = list(Shop.objects.filter(is_active=True).select_related("market"))
    ids = [s.id for s in shops]

    # Kiritilgan savdo + chek soni (do'kon bo'yicha, 1 so'rov)
    entered_by, checks_by = {}, {}
    for r in Sale.objects.filter(shop_id__in=ids, **on_day("created_at", day)).values("shop").annotate(
        t=Sum("total"), n=Count("id")
    ):
        entered_by[r["shop"]] = int(r["t"] or 0)
        checks_by[r["shop"]] = r["n"] or 0
    # Deklaratsiya (kassa) — 1 so'rov; bir kunga bir nechta manba bo'lsa eng ishonchlisi
    from apps.cash.services import declared_by_shop

    cash_by = declared_by_shop(ids, day)
    # Kamera tashriflari — 1 so'rov
    visits_by = {
        r["shop"]: r["c"]
        for r in CameraEvent.objects.filter(shop_id__in=ids, type="visit", **on_day("ts", day))
        .values("shop")
        .annotate(c=Count("id"))
    }
    # Bozor o'rtacha cheki (kamera mustaqilligi uchun) — do'kon jamlanmalaridan
    # MUHIM: bir xil SAVDO TURI ichida (ko'kat sotuvchi cheki kiyim do'koni cheki bilan
    # aralashsa, kamera bahosi o'n barobar oshib ketib, noto'g'ri ayblov bo'lardi).
    mkt_sum, mkt_cnt = defaultdict(int), defaultdict(int)
    for s in shops:
        key = (s.market_id, s.category_id)
        mkt_sum[key] += entered_by.get(s.id, 0)
        mkt_cnt[key] += checks_by.get(s.id, 0)
    avg_check_by_market = {
        k: (mkt_sum[k] / mkt_cnt[k]) if mkt_cnt[k] else 0 for k in mkt_sum
    }
    # Narx balli uchun mahsulotlar — 1 so'rov, do'kon bo'yicha guruh
    prices_by = defaultdict(list)
    stock_shop_ids = set()
    for r in Product.objects.filter(shop_id__in=ids, is_active=True).values(
        "shop", "category_id", "sell_price", "stock"
    ):
        if r["stock"] and r["stock"] > 0:
            stock_shop_ids.add(r["shop"])
        if r["category_id"] and r["sell_price"] > 0:
            prices_by[r["shop"]].append((r["category_id"], r["sell_price"]))
    # Anomaliya uchun 30-kunlik tarix — 1 so'rov
    prior_by = defaultdict(list)
    prior_qs = DailyScore.objects.filter(
        shop_id__in=ids,
        date__lt=day,
        date__gte=day - timedelta(days=30),
        entered_sales__gt=0,
    ).values("shop", "entered_sales")
    for r in prior_qs:
        prior_by[r["shop"]].append(r["entered_sales"])
    # Inspektor — bozor bo'yicha (do'kon boshiga takror so'rov emas)
    insp_by_market = {}
    for s in shops:
        if s.market_id not in insp_by_market:
            insp_by_market[s.market_id] = s.market.duty_inspector()
    # Qoldiq bahosi (DailyClose asosida) — 2 so'rov (close + lines), StockIn — 1 so'rov
    from apps.sales.services.stock import close_sold_value

    stock_val_by, has_close = {}, set()
    for c in DailyClose.objects.filter(shop_id__in=ids, date=day).select_related(
        "shop"
    ).prefetch_related("lines"):
        has_close.add(c.shop_id)
        stock_val_by[c.shop_id] = close_sold_value(c) or 0
    # Mavjud signallar (do'kon,tur) — 1 so'rov (har do'konga .exists() o'rniga)
    existing_alerts = set(
        Alert.objects.filter(shop_id__in=ids, date=day).values_list("shop_id", "kind")
    )
    # Hali hech kim ko'rmagan rostlik signallari: kechikib kelgan ma'lumot (Soliq API, Excel)
    # bilan qayta hisoblanganda yangilanadi yoki bekor qilinadi — halol do'kon nishonda qolmasin
    open_truth = {
        a.shop_id: a
        for a in Alert.objects.filter(shop_id__in=ids, date=day, kind=Alert.Kind.TRUTH,
                                      status=Alert.Status.NEW)
    }

    def _price_score_from(rows, medians):
        scores = [
            price_score(sp, medians.get(cid))
            for cid, sp in rows
            if price_score(sp, medians.get(cid)) is not None
        ]
        return (sum(scores) / len(scores)) if scores else None

    count = 0
    for shop in shops:
        entered = entered_by.get(shop.id, 0)
        cash = cash_by.get(shop.id, 0)
        # Kamera bahosi (dict'lardan; alohida so'rovsiz)
        visits = visits_by.get(shop.id, 0)
        cam = None
        if visits:
            own_avg = entered / checks_by[shop.id] if checks_by.get(shop.id) else 0
            avg_check = max(
                own_avg, avg_check_by_market.get((shop.market_id, shop.category_id), 0)
            )
            cam = int(visits * float(cfg.buyer_ratio) * avg_check) if avg_check > 0 else None
        stock_val = stock_val_by.get(shop.id) if shop.id in has_close else None
        if stock_val is not None and stock_val <= 0:
            stock_val = None
        price_val = _price_score_from(
            prices_by.get(shop.id, []), medians_by_market.get(shop.market_id, {})
        )
        inspector = insp_by_market.get(shop.market_id)

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

        # Yashirilgan savdo (soliqdan): haqiqiy savdo bahosi − deklaratsiya (kassa).
        # Haqiqiy savdo = yozilgan/kamera/qoldiq eng kattasi (eng ishonchli quyi chegara).
        # MUHIM: deklaratsiya YOZUVI bor bo'lsa (0 bo'lsa ham) hisoblanadi — nolga
        # deklaratsiya qilgan do'kon eng shubhali. Yozuv umuman yo'q bo'lsa (ma'lumot
        # kelmagan) — 0 (noto'g'ri ayblamaslik uchun). cash_by'da 0-summa ham bor.
        real_estimate = max(int(entered), int(cam or 0), int(stock_val or 0))
        has_declaration = shop.id in cash_by
        hidden = max(0, real_estimate - int(cash)) if has_declaration else 0

        DailyScore.objects.update_or_create(
            shop=shop,
            date=day,
            defaults={
                "truth_pct": result["truth"],
                "parts": result["parts"],
                "weakest": result["weakest"],
                "entered_sales": entered,
                "cash_amount": cash,
                "hidden_sales": hidden,
                "measured": any(v is not None for v in parts.values()),
            },
        )
        count += 1

        # Signal: faqat TUGAGAN kun uchun (yopiq kun bo'lmasa, ma'lumot bo'lsa)
        if not final or day.weekday() in shop.closed_weekday_list():
            continue

        # Nol-savdo: ochiq kun, tovari yoki kamera oqimi bor, lekin 0 savdo kiritilgan
        has_activity = cam or (stock_val and stock_val > 0) or (shop.id in stock_shop_ids)
        if entered == 0 and has_activity:
            if (shop.id, Alert.Kind.ZERO_SALES) not in existing_alerts:
                existing_alerts.add((shop.id, Alert.Kind.ZERO_SALES))
                za = Alert.objects.create(
                    shop=shop,
                    date=day,
                    kind=Alert.Kind.ZERO_SALES,
                    level="red",
                    reason="Do'kon ochiq, ammo shu kuni savdo kiritilmagan (tovar/kamera oqimi bor)",
                    assigned_to=inspector,
                )
                try:
                    from apps.analytics.notifications import notify_alert

                    notify_alert(za)
                except Exception:  # noqa: BLE001
                    pass
            continue  # nol-savdoda rostlik signali ortiqcha

        # Anomaliya: bugungi savdo 30-kunlik o'rtachadan keskin tushsa (batched tarix)
        if entered > 0 and (shop.id, Alert.Kind.ANOMALY) not in existing_alerts:
            if _anomaly_from(shop, day, entered, prior_by.get(shop.id, []), cfg, inspector):
                existing_alerts.add((shop.id, Alert.Kind.ANOMALY))

        if not any(v is not None for v in parts.values()):
            continue
        lvl = level_for(result["truth"], cfg.green_threshold, cfg.yellow_threshold)
        stale = open_truth.get(shop.id)
        if lvl == "green":
            if stale is not None:
                stale.status = Alert.Status.DISMISSED
                stale.reason = (stale.reason[:240] + " — yangi ma'lumot bilan bekor qilindi")[:300]
                stale.save(update_fields=["status", "reason", "updated_at"])
            continue
        reason = _alert_reason(result, parts, entered, cash)
        if (shop.id, Alert.Kind.TRUTH) in existing_alerts:
            if stale is not None and (stale.level != lvl or stale.reason != reason):
                stale.level, stale.reason = lvl, reason
                stale.save(update_fields=["level", "reason", "updated_at"])
            continue
        existing_alerts.add((shop.id, Alert.Kind.TRUTH))
        alert = Alert.objects.create(
            shop=shop,
            date=day,
            kind=Alert.Kind.TRUTH,
            level=lvl,
            reason=reason,
            assigned_to=inspector,
        )
        # Qizil signal → inspektorga darrov Telegram (token bo'lsa; aks holda jim o'tadi)
        if lvl == "red":
            try:
                from apps.analytics.notifications import notify_alert

                notify_alert(alert)
            except Exception:  # noqa: BLE001 — xabar asosiy oqimni buzmasin
                pass

    # Kassa nomuvofiqligi signali (Z-hisobot asosida, rostlik ballidan mustaqil)
    if final:
        _generate_cash_mismatch_alerts(day, cfg, existing_alerts, insp_by_market)
    return count


def _anomaly_from(shop, day, entered, prior, cfg, inspector):
    """Bugungi savdo 30-kunlik o'rtachadan keskin tushsa — signal. Qaytadi: yaratildimi (bool)."""
    from apps.analytics.models import Alert

    if len(prior) < 5:  # yetarli tarix bo'lmasa — baholamaymiz
        return False
    avg = sum(prior) / len(prior)
    if avg <= 0:
        return False
    drop_pct = round((1 - entered / avg) * 100)
    if drop_pct < cfg.anomaly_drop_pct:
        return False
    lvl = "red" if drop_pct >= 80 else "yellow"
    Alert.objects.create(
        shop=shop,
        date=day,
        kind=Alert.Kind.ANOMALY,
        level=lvl,
        reason=(
            f"Savdo keskin tushdi: shu kuni {som(entered)} so'm, "
            f"odatda ~{som(avg)} so'm ({drop_pct}% kam)"
        ),
        assigned_to=inspector,
    )
    return True


def _generate_cash_mismatch_alerts(day, cfg, existing_alerts=None, insp_by_market=None):
    """Sandiqdagi naqd yozilgan naqd savdodan sezilarli farq qilsa — signal.

    Ikki yo'nalish:
    - ORTIQCHA (sandiqda ko'p): yozilmagan naqd savdo — soliq yashirishning asosiy
      belgisi (kuchliroq signal).
    - KAMOMAD (sandiqda kam): pul yo'qolgan / soxta savdo — o'g'irlik/nomuvofiqlik.
    Rostlik ballidan mustaqil. kind=CASH_MISMATCH.
    """
    from apps.analytics.models import Alert
    from apps.sales.models import RegisterClose

    if existing_alerts is None:
        existing_alerts = set(
            Alert.objects.filter(date=day, kind=Alert.Kind.CASH_MISMATCH).values_list(
                "shop_id", "kind"
            )
        )
    if insp_by_market is None:
        insp_by_market = {}

    threshold = cfg.cash_shortage_pct or 15
    for z in RegisterClose.objects.filter(date=day).select_related("shop", "shop__market"):
        if z.expected_cash <= 0:
            continue
        diff = z.counted_cash - z.expected_cash  # + ortiqcha, − kamomad
        pct = round(abs(diff) / z.expected_cash * 100)
        if pct < threshold:
            continue
        if (z.shop_id, Alert.Kind.CASH_MISMATCH) in existing_alerts:
            continue
        existing_alerts.add((z.shop_id, Alert.Kind.CASH_MISMATCH))
        lvl = "red" if pct >= threshold * 2 else "yellow"
        if diff > 0:
            # Ortiqcha — yozilmagan savdo belgisi, past chegaradayoq jiddiy
            lvl = "red" if pct >= threshold else "yellow"
            reason = (
                f"Kassa ortiqchasi: sandiqda {som(z.counted_cash)} / "
                f"yozilgan {som(z.expected_cash)} so'm ({pct}% ko'p) — "
                f"yozilmagan naqd savdo belgisi"
            )
        else:
            reason = (
                f"Kassa kamomadi: sandiqda {som(z.counted_cash)} / "
                f"kutilgan {som(z.expected_cash)} so'm ({pct}% kam)"
            )
        inspector = insp_by_market.get(z.shop.market_id)
        if inspector is None and z.shop.market_id not in insp_by_market:
            inspector = z.shop.market.duty_inspector()
        alert = Alert.objects.create(
            shop_id=z.shop_id,
            date=day,
            kind=Alert.Kind.CASH_MISMATCH,
            level=lvl,
            reason=reason,
            assigned_to=inspector,
        )
        if lvl == "red":
            try:
                from apps.analytics.notifications import notify_alert

                notify_alert(alert)
            except Exception:  # noqa: BLE001
                pass


def _alert_reason(result, parts, entered, cash):
    weakest = result.get("weakest")
    if weakest == "cash" and entered:
        pct = round((1 - (cash / entered)) * 100) if entered else 0
        return f"Deklaratsiya kiritilgandan {pct}% past (kassa {som(cash)} / savdo {som(entered)} so'm)"
    if weakest == "price":
        return "Narx bozor medianasidan sezilarli past"
    if weakest == "camera":
        return "Kamera bahosi kiritilgan savdodan farq qilmoqda"
    return f"Rostlik darajasi past ({result['truth']}%)"
