from django.contrib import admin

from apps.core.admin import EvidenceAdmin

from .models import Alert, Appeal, DailyScore, Inspection, MarketPrice


@admin.register(DailyScore)
class DailyScoreAdmin(EvidenceAdmin):
    list_display = ("shop", "date", "truth_pct", "weakest", "entered_sales", "cash_amount")
    list_filter = ("date", "shop__market")


@admin.register(Alert)
class AlertAdmin(EvidenceAdmin):
    list_display = ("shop", "date", "level", "status", "assigned_to", "telegram_sent")
    list_filter = ("level", "status", "shop__market")


@admin.register(Inspection)
class InspectionAdmin(EvidenceAdmin):
    list_display = ("shop", "inspector", "result", "fine_level", "fine_amount", "act_number", "created_at")
    list_filter = ("result", "fine_level", "shop__market")


admin.site.register(MarketPrice, EvidenceAdmin)
admin.site.register(Appeal, EvidenceAdmin)
