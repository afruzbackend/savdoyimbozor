"""Tekshiruvchi interfeysi ko'rinishlari (P3'da to'ldiriladi)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def dashboard(request):
    """Tekshiruvchi dashboard: xavf reytingi, signal lentasi, aniqlik %."""
    return render(request, "inspector/dashboard.html")
