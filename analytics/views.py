from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from markets.models import Shop

from .models import Alert, Declaration


@login_required
def alert_list(request):
    """Ogohlantirishlar ro'yxati (inspektor/rahbar uchun)."""
    markets = request.user.visible_markets()
    alerts = Alert.objects.filter(shop__market__in=markets).select_related("shop", "shop__market")
    level = request.GET.get("level")
    if level:
        alerts = alerts.filter(level=level)
    status = request.GET.get("status")
    if status:
        alerts = alerts.filter(status=status)
    return render(request, "analytics/alerts.html", {
        "alerts": alerts[:200],
        "level": level or "",
        "status": status or "",
    })


@login_required
@require_POST
def alert_action(request, pk):
    """Signal holatini o'zgartirish: menga biriktirish / e'tiborsiz qoldirish.

    HTMX so'rovida yangilangan qatorni qaytaradi, aks holda ro'yxatga qaytadi.
    """
    markets = request.user.visible_markets()
    alert = get_object_or_404(Alert, pk=pk, shop__market__in=markets)
    action = request.POST.get("action")

    if action == "assign_me":
        alert.assigned_to = request.user
        alert.status = Alert.Status.ASSIGNED
        alert.save(update_fields=["assigned_to", "status"])
    elif action == "dismiss":
        alert.status = Alert.Status.DISMISSED
        alert.save(update_fields=["status"])
    elif action == "reopen":
        alert.status = Alert.Status.NEW
        alert.save(update_fields=["status"])

    if request.htmx:
        return render(request, "analytics/_alert_row.html", {"a": alert})
    return redirect("analytics:alerts")


@login_required
def declaration_upload(request):
    """Soliqchi Excel yuklaydi: STIR, yil, oy, summa. (openpyxl bilan)"""
    if not request.user.is_manager:
        messages.error(request, "Ruxsat yo'q.")
        return redirect("dashboard:home")

    if request.method == "POST" and request.FILES.get("file"):
        import openpyxl
        wb = openpyxl.load_workbook(request.FILES["file"], data_only=True)
        ws = wb.active
        added, skipped = 0, 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or row[0] is None:
                continue
            stir = str(row[0]).strip()
            shop = Shop.objects.filter(stir=stir).first()
            if not shop:
                skipped += 1
                continue
            try:
                Declaration.objects.update_or_create(
                    shop=shop, year=int(row[1]), month=int(row[2]),
                    defaults={"declared_amount": row[3] or 0},
                )
                added += 1
            except (ValueError, TypeError):
                skipped += 1
        messages.success(request, f"{added} ta deklaratsiya yuklandi, {skipped} ta o'tkazib yuborildi.")
        return redirect("analytics:declaration_upload")

    return render(request, "analytics/declaration_upload.html")
