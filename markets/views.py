from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from analytics.models import Alert, DailyShopStat
from analytics.services import peer_comparison
from events.models import CameraTamperEvent, SaleObservation

from .models import Market, Shop


@login_required
def market_list(request):
    markets = request.user.visible_markets()
    cards = []
    for m in markets:
        new_alerts = Alert.objects.filter(shop__market=m, status=Alert.Status.NEW)
        cards.append({
            "market": m,
            "shop_count": m.shops.filter(is_active=True).count(),
            "red": new_alerts.filter(level=Alert.Level.RED).count(),
            "yellow": new_alerts.filter(level=Alert.Level.YELLOW).count(),
        })
    return render(request, "markets/market_list.html", {"cards": cards})


@login_required
def market_detail(request, pk):
    markets = request.user.visible_markets()
    market = get_object_or_404(Market, pk=pk)
    if not markets.filter(pk=pk).exists():
        return render(request, "403.html", status=403)

    today = timezone.localdate()
    shops = []
    for shop in market.shops.filter(is_active=True).select_related("category"):
        stat = DailyShopStat.objects.filter(shop=shop, date=today).first()
        alert = (Alert.objects.filter(shop=shop, status=Alert.Status.NEW)
                 .order_by("-level").first())
        shops.append({
            "shop": shop,
            "visitors": stat.visitor_count if stat else 0,
            "sales": stat.recorded_sales if stat else 0,
            "level": alert.level if alert else "green",
        })
    # Xavflilar tepada
    order = {"red": 0, "yellow": 1, "green": 2}
    shops.sort(key=lambda s: order.get(s["level"], 3))
    return render(request, "markets/market_detail.html", {"market": market, "shops": shops})


@login_required
def shop_detail(request, pk):
    markets = request.user.visible_markets()
    shop = get_object_or_404(Shop.objects.select_related("market", "category"), pk=pk)
    if not markets.filter(pk=shop.market_id).exists():
        return render(request, "403.html", status=403)

    today = timezone.localdate()
    start = today - timedelta(days=14)
    stats = list(DailyShopStat.objects.filter(shop=shop, date__range=(start, today)).order_by("date"))

    chart = {
        "labels": [s.date.strftime("%d.%m") for s in stats],
        "visitors": [s.visitor_count for s in stats],
        "sales": [float(s.recorded_sales) for s in stats],
        "estimated": [float(s.estimated_sales) for s in stats],
    }

    ctx = {
        "shop": shop,
        "chart": chart,
        "peer": peer_comparison(shop, today),
        "alerts": Alert.objects.filter(shop=shop).order_by("-created_at")[:10],
        "observations": SaleObservation.objects.filter(shop=shop).order_by("-timestamp")[:12],
        "declarations": shop.declarations.order_by("-year", "-month")[:6],
    }
    return render(request, "markets/shop_detail.html", ctx)
