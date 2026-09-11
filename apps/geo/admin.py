from django.contrib import admin

from .models import Market, Region, Row


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name",)


@admin.register(Market)
class MarketAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "is_active")
    list_filter = ("region", "is_active")
    search_fields = ("name", "address")


@admin.register(Row)
class RowAdmin(admin.ModelAdmin):
    list_display = ("label", "market", "order")
    list_filter = ("market",)
    search_fields = ("label", "market__name")
