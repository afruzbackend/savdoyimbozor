from django.contrib import admin

from .models import Alert, DailyShopStat, Declaration


@admin.register(Declaration)
class DeclarationAdmin(admin.ModelAdmin):
    list_display = ("shop", "year", "month", "declared_amount", "source")
    list_filter = ("year", "month", "shop__market")
    search_fields = ("shop__name", "shop__stir")


@admin.register(DailyShopStat)
class DailyShopStatAdmin(admin.ModelAdmin):
    list_display = ("shop", "date", "visitor_count", "recorded_sales", "estimated_sales")
    list_filter = ("date", "shop__market")


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("shop", "date", "level", "status", "assigned_to", "telegram_sent")
    list_filter = ("level", "status", "shop__market")
    search_fields = ("shop__name",)
