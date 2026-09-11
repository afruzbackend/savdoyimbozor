"""Sotuvchi interfeysi ko'rinishlari."""
import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.core.models import SystemSettings

from .models import Sale
from .services import pricing


def _shop(request):
    return getattr(request.user, "shop", None)


@login_required
def home(request):
    """Bosh sahifa: bugungi savdo, rostlik, so'nggi sotuvlar."""
    shop = _shop(request)
    today = timezone.localdate()
    sales = Sale.objects.filter(shop=shop, created_at__date=today) if shop else Sale.objects.none()
    total = sum(s.total for s in sales)
    return render(request, "seller/home.html", {
        "shop": shop,
        "today_total": total,
        "today_count": sales.count(),
        "recent": sales.order_by("-created_at")[:8],
    })


@login_required
def sale_screen(request):
    """Tez sotuv ekrani (Alpine). Narxlash qoidasi serverdan JSON bilan uzatiladi."""
    shop = _shop(request)
    if shop is None:
        return redirect("seller:home")
    cfg = pricing.frontend_config(SystemSettings.get_solo())
    return render(request, "seller/sale.html", {
        "shop": shop,
        "pricing_config": json.dumps(cfg),
    })
