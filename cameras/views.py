from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Camera


@login_required
def camera_list(request):
    """Kameralar holati: online/offline."""
    markets = request.user.visible_markets()
    cameras = Camera.objects.filter(market__in=markets).select_related("market")
    return render(request, "cameras/list.html", {
        "cameras": cameras,
        "online_count": sum(1 for c in cameras if c.is_online),
        "total_count": cameras.count(),
    })
