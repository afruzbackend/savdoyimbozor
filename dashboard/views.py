from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from analytics.models import Alert, DailyShopStat
from cameras.models import Camera
from markets.models import Market, Shop


@login_required
def home(request):
    user = request.user
    # Sotuvchi to'g'ridan-to'g'ri savdo kiritish ekraniga
    if user.is_seller:
        return redirect("events:sale_create")

    markets = user.visible_markets()
    today = timezone.localdate()

    alerts_today = (Alert.objects
                    .filter(shop__market__in=markets)
                    .select_related("shop", "shop__market")
                    .order_by("-created_at"))
    cameras = Camera.objects.filter(market__in=markets)

    market_cards = []
    for m in markets:
        shops = Shop.objects.filter(market=m, is_active=True)
        m_alerts = Alert.objects.filter(shop__market=m, status=Alert.Status.NEW)
        market_cards.append({
            "market": m,
            "shop_count": shops.count(),
            "red": m_alerts.filter(level=Alert.Level.RED).count(),
            "yellow": m_alerts.filter(level=Alert.Level.YELLOW).count(),
        })

    ctx = {
        "market_cards": market_cards,
        "alerts": alerts_today[:15],
        "new_alert_count": alerts_today.filter(status=Alert.Status.NEW).count(),
        "red_count": alerts_today.filter(level=Alert.Level.RED, status=Alert.Status.NEW).count(),
        "camera_online": sum(1 for c in cameras if c.is_online),
        "camera_total": cameras.count(),
        "today": today,
    }
    return render(request, "dashboard/home.html", ctx)
