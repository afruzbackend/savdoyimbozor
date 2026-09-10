from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from analytics.models import Alert, DailyShopStat
from inspections.models import Inspection


def _date_range(request):
    today = timezone.localdate()
    start = request.GET.get("start")
    end = request.GET.get("end")
    from datetime import datetime
    try:
        start = datetime.strptime(start, "%Y-%m-%d").date() if start else today - timedelta(days=30)
    except ValueError:
        start = today - timedelta(days=30)
    try:
        end = datetime.strptime(end, "%Y-%m-%d").date() if end else today
    except ValueError:
        end = today
    return start, end


@login_required
def report_summary(request):
    markets = request.user.visible_markets()
    start, end = _date_range(request)

    stats = DailyShopStat.objects.filter(shop__market__in=markets, date__range=(start, end))
    alerts = Alert.objects.filter(shop__market__in=markets, date__range=(start, end))
    inspections = Inspection.objects.filter(shop__market__in=markets, created_at__date__range=(start, end))

    # AI aniqligi: tasdiqlangan / (tasdiqlangan + noto'g'ri)
    confirmed = inspections.filter(result=Inspection.Result.CONFIRMED).count()
    false_sig = inspections.filter(result=Inspection.Result.FALSE_SIGNAL).count()
    accuracy = round(confirmed / (confirmed + false_sig) * 100) if (confirmed + false_sig) else None

    ctx = {
        "start": start, "end": end,
        "total_visitors": stats.aggregate(s=Sum("visitor_count"))["s"] or 0,
        "total_sales": stats.aggregate(s=Sum("recorded_sales"))["s"] or 0,
        "alert_count": alerts.count(),
        "red_count": alerts.filter(level=Alert.Level.RED).count(),
        "inspection_count": inspections.count(),
        "confirmed": confirmed,
        "false_signal": false_sig,
        "accuracy": accuracy,
        "total_fines": inspections.aggregate(s=Sum("fine_amount"))["s"] or 0,
    }
    return render(request, "reports/summary.html", ctx)


@login_required
def export_excel(request):
    """Do'konlar bo'yicha savdo/deklaratsiya jadvalini Excel'ga chiqaradi."""
    import openpyxl
    markets = request.user.visible_markets()
    start, end = _date_range(request)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hisobot"
    ws.append(["Bozor", "Do'kon", "STIR", "Xaridorlar", "Kiritilgan savdo", "AI taxmini"])

    rows = (DailyShopStat.objects
            .filter(shop__market__in=markets, date__range=(start, end))
            .values("shop__market__name", "shop__name", "shop__stir")
            .annotate(v=Sum("visitor_count"), r=Sum("recorded_sales"), e=Sum("estimated_sales")))
    for row in rows:
        ws.append([row["shop__market__name"], row["shop__name"], row["shop__stir"],
                   row["v"] or 0, float(row["r"] or 0), float(row["e"] or 0)])

    resp = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="hisobot_{start}_{end}.xlsx"'
    wb.save(resp)
    return resp
