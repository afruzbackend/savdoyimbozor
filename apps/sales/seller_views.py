"""Sotuvchi interfeysi ko'rinishlari (P2'da to'ldiriladi)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """Sotuvchi bosh sahifasi: bugungi savdo, rostlik, kam qoldiq."""
    return render(request, "seller/home.html", {"shop": getattr(request.user, "shop", None)})
