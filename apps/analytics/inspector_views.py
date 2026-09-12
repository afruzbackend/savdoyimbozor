"""Tekshiruvchi interfeysi: dashboard, bozor xaritasi, do'kon sahifasi, signallar, tekshiruv."""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.cameras.models import Camera
from apps.geo.models import Market

from .models import Alert, Appeal, DailyScore, Inspection


def _visible_shops(request):
    return request.user.visible_shops().select_related("market", "row", "category")


def _level(truth, cfg):
    if truth >= cfg.green_threshold:
        return "green"
    if truth >= cfg.yellow_threshold:
        return "yellow"
    return "red"


@login_required
def dashboard(request):
    from apps.core.models import SystemSettings

    cfg = SystemSettings.get_solo()
    shops = _visible_shops(request)
    today = timezone.localdate()

    latest = {
        s.shop_id: s
        for s in DailyScore.objects.filter(shop__in=shops, date=today).select_related(
            "shop", "shop__category", "shop__market"
        )
    }
    truths = [s.truth_pct for s in latest.values()]
    avg_truth = round(sum(truths) / len(truths)) if truths else None

    alerts = Alert.objects.filter(shop__in=shops).select_related("shop", "shop__market")
    new_alerts = alerts.filter(status=Alert.Status.NEW)

    insp = Inspection.objects.filter(shop__in=shops)
    confirmed = insp.filter(result=Inspection.Result.CONFIRMED).count()
    false_sig = insp.filter(result=Inspection.Result.FALSE).count()
    accuracy = round(confirmed / (confirmed + false_sig) * 100) if (confirmed + false_sig) else None

    # Eng xavfli do'konlar (bugungi ball bo'yicha)
    risky = sorted(latest.values(), key=lambda s: s.truth_pct)[:8]

    # Yashirilgan savdo (oxirgi 30 kun) + potensial qo'shimcha soliq
    from django.db.models import Sum

    since = today - timedelta(days=29)
    hidden = (
        DailyScore.objects.filter(shop__in=shops, date__gte=since).aggregate(
            h=Sum("hidden_sales")
        )["h"]
        or 0
    )
    potential_tax = int(hidden * cfg.tax_rate_percent / 100)

    ctx = {
        "shop_count": shops.count(),
        "red_count": new_alerts.filter(level="red").count(),
        "yellow_count": new_alerts.filter(level="yellow").count(),
        "avg_truth": avg_truth,
        "accuracy": accuracy,
        "alerts": new_alerts.order_by("-created_at")[:12],
        "risky": [(s, _level(s.truth_pct, cfg)) for s in risky],
        "today": today,
        "hidden_sales": int(hidden),
        "potential_tax": potential_tax,
        "tax_rate": cfg.tax_rate_percent,
    }
    return render(request, "inspector/dashboard.html", ctx)


@login_required
def market_map(request, pk=None):
    from apps.core.models import SystemSettings

    cfg = SystemSettings.get_solo()
    markets = Market.objects.filter(id__in=_visible_shops(request).values("market_id")).distinct()
    market = get_object_or_404(markets, pk=pk) if pk else markets.first()
    if market is None:
        return render(request, "inspector/market_map.html", {"markets": markets, "market": None})

    today = timezone.localdate()
    scores = {
        s.shop_id: s.truth_pct for s in DailyScore.objects.filter(shop__market=market, date=today)
    }

    # Bozor sxemasi: do'konlar QATOR bo'yicha guruhlanadi, har rasta rangli % belgi.
    from collections import defaultdict

    by_row = defaultdict(list)
    counts = {"green": 0, "yellow": 0, "red": 0, "none": 0}
    for shop in market.shops.filter(is_active=True).select_related("row").order_by("number"):
        t = scores.get(shop.id)
        lvl = _level(t, cfg) if t is not None else "none"
        counts[lvl] += 1
        row_label = shop.row.label if shop.row_id else "Boshqa"
        by_row[row_label].append(
            {
                "id": shop.id,
                "number": shop.number,
                "owner": shop.owner_name,
                "truth": t,
                "level": lvl,
            }
        )
    rows_data = [{"label": lbl, "stalls": by_row[lbl]} for lbl in sorted(by_row)]

    return render(
        request,
        "inspector/market_map.html",
        {
            "markets": markets,
            "market": market,
            "rows_data": rows_data,
            "counts": counts,
        },
    )


def _investigation(shop, peers, start, today):
    """Nazorat quroli: chegirma vs bozor, tannarxga yaqin sotuvlar."""
    from django.db.models import Sum

    from apps.sales.models import Sale, SaleItem

    rng = (start, today)

    def discount_pct(shops):
        agg = Sale.objects.filter(shop__in=shops, created_at__date__range=rng).aggregate(
            d=Sum("discount"), s=Sum("subtotal")
        )
        sub = agg["s"] or 0
        return round((agg["d"] or 0) / sub * 100, 1) if sub else 0.0

    # Tannarxga yaqin sotuvlar (narx tannarxdan ≤10% yuqori) — dumping/yashirish belgisi
    items = SaleItem.objects.filter(
        sale__shop=shop,
        sale__created_at__date__range=rng,
        product__isnull=False,
        product__buy_price__gt=0,
    ).select_related("product")
    near = total = 0
    for it in items:
        total += 1
        if it.unit_price <= it.product.buy_price * 1.1:
            near += 1

    return {
        "shop_discount": discount_pct([shop]),
        "market_discount": discount_pct(list(peers) + [shop]),
        "near_cost": near,
        "near_cost_total": total,
        "near_cost_pct": round(near / total * 100) if total else 0,
    }


@login_required
def shop_detail(request, pk):
    from apps.core.models import SystemSettings

    cfg = SystemSettings.get_solo()
    shop = get_object_or_404(_visible_shops(request), pk=pk)
    today = timezone.localdate()
    start = today - timedelta(days=13)

    scores = list(DailyScore.objects.filter(shop=shop, date__range=(start, today)).order_by("date"))
    latest = scores[-1] if scores else None
    level = _level(latest.truth_pct, cfg) if latest else "none"

    chart = {
        "labels": [s.date.strftime("%d.%m") for s in scores],
        "entered": [s.entered_sales for s in scores],
        "cash": [s.cash_amount for s in scores],
        "truth": [s.truth_pct for s in scores],
    }

    # O'xshash do'konlar (bir bozor + bir toifa) bilan solishtirish
    peers = shop.similar_shops()
    peer_scores = DailyScore.objects.filter(shop__in=peers, date=today)
    peer_avg = round(peer_scores.aggregate(a=Avg("truth_pct"))["a"] or 0)

    part_labels = {
        "cash": "Kassa / deklaratsiya",
        "camera": "Kamera",
        "stock": "Qoldiq",
        "price": "Narx",
    }
    parts = []
    if latest:
        for k, lbl in part_labels.items():
            v = latest.parts.get(k)
            parts.append(
                {
                    "key": k,
                    "label": lbl,
                    "value": v,
                    "level": _level(v, cfg) if v is not None else "none",
                }
            )

    ctx = {
        "shop": shop,
        "latest": latest,
        "level": level,
        "parts": parts,
        "chart": chart,  # json_script o'zi serializatsiya qiladi
        "peer_avg": peer_avg,
        "peer_count": peers.count(),
        "invest": _investigation(shop, peers, start, today),
        "alerts": shop.alerts.order_by("-created_at")[:8],
        "inspections": shop.inspections.select_related("inspector")[:6],
        "appeals": shop.appeals.all()[:5],
        "corrections": shop.corrections.select_related("user")[:8],
        "register_closes": shop.register_closes.order_by("-date")[:10],
    }
    return render(request, "inspector/shop_detail.html", ctx)


@login_required
def shop_evidence(request, pk):
    """Bitta do'kon uchun chop etsa bo'ladigan dalil to'plami (tekshiruv/akt uchun)."""

    from apps.core.models import SystemSettings

    cfg = SystemSettings.get_solo()
    shop = get_object_or_404(_visible_shops(request), pk=pk)
    today = timezone.localdate()
    start = today - timedelta(days=29)

    scores = list(DailyScore.objects.filter(shop=shop, date__range=(start, today)).order_by("date"))
    latest = scores[-1] if scores else None
    hidden = sum(s.hidden_sales for s in scores)
    potential_tax = int(hidden * cfg.tax_rate_percent / 100)
    peers = shop.similar_shops()

    ctx = {
        "shop": shop,
        "latest": latest,
        "level": _level(latest.truth_pct, cfg) if latest else "none",
        "start": start,
        "today": today,
        "hidden_sales": hidden,
        "potential_tax": potential_tax,
        "tax_rate": cfg.tax_rate_percent,
        "entered_total": sum(s.entered_sales for s in scores),
        "cash_total": sum(s.cash_amount for s in scores),
        "invest": _investigation(shop, peers, start, today),
        "alerts": shop.alerts.order_by("-created_at")[:15],
        "register_closes": shop.register_closes.order_by("-date")[:10],
        "inspections": shop.inspections.select_related("inspector")[:6],
        "now": timezone.now(),
        "inspector": request.user,
    }
    return render(request, "inspector/shop_evidence.html", ctx)


@login_required
def alerts_list(request):
    shops = _visible_shops(request)
    alerts = Alert.objects.filter(shop__in=shops).select_related("shop", "shop__market")
    level = request.GET.get("level")
    status = request.GET.get("status", "")
    if level:
        alerts = alerts.filter(level=level)
    if status:
        alerts = alerts.filter(status=status)
    from apps.core.pagination import paginate

    page = paginate(request, alerts.order_by("-created_at"), per_page=50)
    qs = f"level={level or ''}&status={status}"
    return render(
        request,
        "inspector/alerts.html",
        {
            "alerts": page.object_list,
            "page": page,
            "querystring": qs,
            "level": level or "",
            "status": status,
        },
    )


@login_required
@require_POST
def alert_action(request, pk):
    shops = _visible_shops(request)
    alert = get_object_or_404(Alert, pk=pk, shop__in=shops)
    action = request.POST.get("action")
    if action == "assign_me":
        alert.assigned_to = request.user
        alert.status = Alert.Status.ASSIGNED
    elif action == "dismiss":
        alert.status = Alert.Status.DISMISSED
    elif action == "reopen":
        alert.status = Alert.Status.NEW
    alert.save()
    if request.htmx:
        return render(request, "inspector/_alert_row.html", {"a": alert})
    return redirect("inspector:alerts")


@login_required
def inspection_create(request):
    shops = _visible_shops(request)
    alert_id = request.GET.get("alert")
    alert = Alert.objects.filter(pk=alert_id, shop__in=shops).first() if alert_id else None
    preselect = alert.shop if alert else None

    if request.method == "POST":
        shop = get_object_or_404(shops, pk=request.POST.get("shop"))
        insp = Inspection.objects.create(
            shop=shop,
            alert_id=request.POST.get("alert") or None,
            inspector=request.user,
            result=request.POST.get("result", "pending"),
            act_number=request.POST.get("act_number", "")[:60],
            fine_amount=request.POST.get("fine_amount") or None,
            notes=request.POST.get("notes", ""),
            photo=request.FILES.get("photo"),
        )
        if insp.alert_id:
            insp.alert.status = Alert.Status.RESOLVED
            insp.alert.save(update_fields=["status"])
        from django.contrib import messages

        messages.success(request, "Tekshiruv natijasi saqlandi.")
        return redirect("inspector:alerts")

    return render(
        request,
        "inspector/inspection_form.html",
        {
            "shops": shops,
            "alert": alert,
            "preselect": preselect,
            "results": Inspection.Result.choices,
        },
    )


@login_required
def shop_search(request):
    """Do'kon qidirish: raqam yoki STIR bo'yicha. Bitta topilsa — to'g'ridan sahifaga."""
    q = request.GET.get("q", "").strip()
    results = []
    if q:
        from django.db.models import Q

        results = list(
            _visible_shops(request).filter(Q(number__icontains=q) | Q(stir__icontains=q))[:50]
        )
        if len(results) == 1:
            return redirect("inspector:shop_detail", pk=results[0].pk)
    return render(request, "inspector/shop_search.html", {"q": q, "results": results})


@login_required
@require_POST
def appeal_respond(request, pk):
    """Inspektor e'tirozga javob beradi (qabul/rad + matn)."""
    shops = _visible_shops(request)
    appeal = get_object_or_404(Appeal, pk=pk, shop__in=shops)
    action = request.POST.get("action")
    if action in ("accepted", "rejected"):
        appeal.status = action
        appeal.response = request.POST.get("response", "")[:2000]
        appeal.save(update_fields=["status", "response"])
        from django.contrib import messages

        from apps.core.models import Notification, notify

        target = appeal.author or getattr(appeal.shop, "staff", None)
        if hasattr(target, "first"):  # staff manager
            target = target.first()
        verdict = "qabul qilindi" if action == "accepted" else "rad etildi"
        notify(
            target,
            Notification.Kind.APPEAL_REPLY,
            f"E'tirozingizga javob: {verdict}",
            body=appeal.response[:200],
            url="/e-tiroz/",
            key=f"appeal:{appeal.id}:{action}",
        )
        messages.success(request, "E'tirozga javob berildi.")
    return redirect("inspector:shop_detail", pk=appeal.shop_id)


@login_required
def inventory(request, pk=None):
    """Joriy ombor — har do'konda hozir qancha mahsulot bor (yong'in/nazorat uchun).

    Prokuratura ssenariysi: "bozor yondi, qaysi do'konda qancha mahsulot bor edi".
    """
    from django.db.models import Count, DecimalField, F, Q, Sum

    from apps.catalog.models import Product

    markets = Market.objects.filter(id__in=_visible_shops(request).values("market_id")).distinct()
    market = get_object_or_404(markets, pk=pk) if pk else markets.first()
    rows = []
    total_value = total_items = 0
    if market:
        # BITTA agregat so'rov: har do'kon bo'yicha qiymat/mahsulot soni (N+1 yo'q)
        agg = {
            r["shop"]: r
            for r in Product.objects.filter(shop__market=market, is_active=True)
            .values("shop")
            .annotate(
                value=Sum(F("stock") * F("sell_price"), output_field=DecimalField()),
                items=Count("id", filter=Q(stock__gt=0)),
                products=Count("id"),
            )
        }
        for shop in market.shops.filter(is_active=True).order_by("number"):
            a = agg.get(shop.id, {})
            value = int(a.get("value") or 0)
            items = a.get("items") or 0
            total_value += value
            total_items += items
            rows.append(
                {"shop": shop, "value": value, "items": items, "products": a.get("products") or 0}
            )
        rows.sort(key=lambda r: r["value"], reverse=True)
    return render(
        request,
        "inspector/inventory.html",
        {
            "markets": markets,
            "market": market,
            "rows": rows,
            "total_value": total_value,
            "total_items": total_items,
        },
    )


@login_required
def shop_inventory(request, pk):
    """Bitta do'kon joriy ombori — mahsulotlar ro'yxati (miqdor + qiymat)."""
    from apps.catalog.models import Product

    shop = get_object_or_404(_visible_shops(request), pk=pk)
    prods = list(Product.objects.filter(shop=shop, is_active=True).order_by("-stock"))
    for p in prods:
        p.line_value = int(p.stock * p.sell_price)
    total = sum(p.line_value for p in prods)
    return render(
        request,
        "inspector/shop_inventory.html",
        {"shop": shop, "products": prods, "total": total},
    )


@login_required
def cameras_status(request):
    shops = _visible_shops(request)
    cams = Camera.objects.filter(market__in=shops.values("market_id")).select_related(
        "market", "shop"
    )
    return render(
        request,
        "inspector/cameras.html",
        {"cameras": cams, "online": sum(1 for c in cams if c.is_online), "total": cams.count()},
    )


def _report_range(request):
    from datetime import datetime

    today = timezone.localdate()
    try:
        start = datetime.strptime(request.GET["start"], "%Y-%m-%d").date()
    except (KeyError, ValueError):
        start = today - timedelta(days=30)
    try:
        end = datetime.strptime(request.GET["end"], "%Y-%m-%d").date()
    except (KeyError, ValueError):
        end = today
    return start, end


@login_required
def reports(request):
    shops = _visible_shops(request)
    start, end = _report_range(request)
    scores = DailyScore.objects.filter(shop__in=shops, date__range=(start, end))
    insp = Inspection.objects.filter(shop__in=shops, created_at__date__range=(start, end))
    confirmed = insp.filter(result=Inspection.Result.CONFIRMED).count()
    false_sig = insp.filter(result=Inspection.Result.FALSE).count()
    ctx = {
        "start": start,
        "end": end,
        "entered": sum(s.entered_sales for s in scores),
        "cash": sum(s.cash_amount for s in scores),
        "avg_truth": round(scores.aggregate(a=Avg("truth_pct"))["a"] or 0),
        "alert_count": Alert.objects.filter(shop__in=shops, date__range=(start, end)).count(),
        "inspection_count": insp.count(),
        "confirmed": confirmed,
        "false_signal": false_sig,
        "accuracy": (
            round(confirmed / (confirmed + false_sig) * 100) if (confirmed + false_sig) else None
        ),
        "fines": sum(i.fine_amount or 0 for i in insp),
    }
    return render(request, "inspector/reports.html", ctx)


@login_required
def statistics(request):
    """Sotuv dinamikasi (grafik) + sotuvchilar statistikasi (jadval, trend bilan)."""
    from collections import defaultdict

    from django.db.models import Count, Sum

    from apps.core.models import SystemSettings

    cfg = SystemSettings.get_solo()
    shops = _visible_shops(request)
    start, end = _report_range(request)

    scores = list(
        DailyScore.objects.filter(shop__in=shops, date__range=(start, end)).select_related("shop")
    )

    # 1) Sotuv dinamikasi — kunlik agregat (barcha ko'rinadigan do'konlar bo'yicha)
    by_date = defaultdict(lambda: {"entered": 0, "cash": 0, "truth": [], "count": 0})
    for s in scores:
        d = by_date[s.date]
        d["entered"] += s.entered_sales
        d["cash"] += s.cash_amount
        d["truth"].append(s.truth_pct)
        d["count"] += 1
    days = sorted(by_date)
    dynamics = {
        "labels": [d.strftime("%d.%m") for d in days],
        "entered": [by_date[d]["entered"] for d in days],
        "cash": [by_date[d]["cash"] for d in days],
        "truth": [round(sum(by_date[d]["truth"]) / len(by_date[d]["truth"])) for d in days],
    }

    # 2) Sotuvchilar statistikasi — har do'kon: savdo, o'rtacha rostlik, signal, trend
    per_shop = defaultdict(lambda: {"entered": 0, "cash": 0, "truth": []})
    mid = start + (end - start) / 2  # trend: davr ikkiga bo'linadi
    half = defaultdict(lambda: {"a": [], "b": []})  # a=birinchi yarim, b=ikkinchi yarim
    for s in scores:
        p = per_shop[s.shop_id]
        p["entered"] += s.entered_sales
        p["cash"] += s.cash_amount
        p["truth"].append(s.truth_pct)
        half[s.shop_id]["b" if s.date >= mid else "a"].append(s.truth_pct)

    alert_counts = dict(
        Alert.objects.filter(shop__in=shops, date__range=(start, end))
        .values_list("shop")
        .annotate(n=Count("id"))
    )
    shop_by_id = {s.id: s for s in shops}

    rows = []
    for sid, p in per_shop.items():
        shop = shop_by_id.get(sid)
        if shop is None:
            continue
        avg_truth = round(sum(p["truth"]) / len(p["truth"])) if p["truth"] else 0
        a, b = half[sid]["a"], half[sid]["b"]
        trend = None
        if a and b:
            trend = round(sum(b) / len(b) - sum(a) / len(a))
        rows.append(
            {
                "shop": shop,
                "entered": p["entered"],
                "cash": p["cash"],
                "avg_truth": avg_truth,
                "level": _level(avg_truth, cfg),
                "alerts": alert_counts.get(sid, 0),
                "trend": trend,
            }
        )
    sort = request.GET.get("sort", "truth")
    keymap = {
        "truth": lambda r: r["avg_truth"],
        "entered": lambda r: -r["entered"],
        "alerts": lambda r: -r["alerts"],
    }
    rows.sort(key=keymap.get(sort, keymap["truth"]))

    totals = DailyScore.objects.filter(shop__in=shops, date__range=(start, end)).aggregate(
        e=Sum("entered_sales"), c=Sum("cash_amount"), t=Avg("truth_pct")
    )
    from apps.core.pagination import paginate

    seller_count = len(rows)
    page = paginate(request, rows, per_page=50)
    ctx = {
        "start": start,
        "end": end,
        "sort": sort,
        "dynamics": dynamics,
        "rows": page.object_list,
        "page": page,
        "querystring": f"start={start:%Y-%m-%d}&end={end:%Y-%m-%d}&sort={sort}",
        "total_entered": int(totals["e"] or 0),
        "total_cash": int(totals["c"] or 0),
        "avg_truth": round(totals["t"] or 0),
        "seller_count": seller_count,
    }
    return render(request, "inspector/statistics.html", ctx)


@login_required
def export_excel(request):
    import openpyxl

    shops = _visible_shops(request)
    start, end = _report_range(request)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hisobot"
    ws.append(
        [
            "Bozor",
            "Do'kon",
            "STIR",
            "Egasi",
            "O'rtacha rostlik %",
            "Kiritilgan (so'm)",
            "Deklaratsiya (so'm)",
        ]
    )
    from django.db.models import Sum

    rows = (
        DailyScore.objects.filter(shop__in=shops, date__range=(start, end))
        .values("shop__market__name", "shop__number", "shop__stir", "shop__owner_name")
        .annotate(t=Avg("truth_pct"), e=Sum("entered_sales"), c=Sum("cash_amount"))
    )
    for r in rows:
        ws.append(
            [
                r["shop__market__name"],
                r["shop__number"],
                r["shop__stir"],
                r["shop__owner_name"],
                round(r["t"] or 0),
                int(r["e"] or 0),
                int(r["c"] or 0),
            ]
        )
    from django.http import HttpResponse

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resp["Content-Disposition"] = f'attachment; filename="hisobot_{start}_{end}.xlsx"'
    wb.save(resp)
    return resp
