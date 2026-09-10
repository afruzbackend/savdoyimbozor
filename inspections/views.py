from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from analytics.models import Alert
from markets.models import Shop

from .models import Inspection, InspectionPhoto


@login_required
def inspection_list(request):
    markets = request.user.visible_markets()
    qs = Inspection.objects.filter(shop__market__in=markets).select_related("shop", "inspector")
    if request.user.is_inspector:
        qs = qs.filter(inspector=request.user)
    return render(request, "inspections/list.html", {"inspections": qs[:200]})


@login_required
def inspection_create(request):
    """Inspektor tekshiruv natijasini kiritadi (PWA'dan)."""
    markets = request.user.visible_markets()
    alert_id = request.GET.get("alert")
    alert = None
    shop = None
    if alert_id:
        alert = get_object_or_404(Alert, pk=alert_id, shop__market__in=markets)
        shop = alert.shop

    if request.method == "POST":
        shop = get_object_or_404(Shop, pk=request.POST.get("shop"), market__in=markets)
        insp = Inspection.objects.create(
            shop=shop,
            alert_id=request.POST.get("alert") or None,
            inspector=request.user,
            visited_at=timezone.now(),
            result=request.POST.get("result", Inspection.Result.PENDING),
            act_number=request.POST.get("act_number", "")[:60],
            fine_amount=request.POST.get("fine_amount") or None,
            notes=request.POST.get("notes", ""),
        )
        for f in request.FILES.getlist("photos"):
            InspectionPhoto.objects.create(inspection=insp, photo=f)
        # Signalni yakunlaймiz
        if insp.alert_id:
            insp.alert.status = Alert.Status.RESOLVED
            insp.alert.save(update_fields=["status"])
        messages.success(request, "Tekshiruv qayd etildi.")
        return redirect("inspections:list")

    shops = Shop.objects.filter(market__in=markets, is_active=True)
    return render(request, "inspections/form.html", {
        "alert": alert, "shop": shop, "shops": shops,
        "results": Inspection.Result.choices,
    })
