from django.contrib import admin

from .models import (
    Correction,
    DailyClose,
    DailyCloseLine,
    Debt,
    Sale,
    SaleItem,
    SaleReturn,
    StockIn,
    WriteOff,
)


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "shop",
        "total",
        "discount",
        "payment_type",
        "is_wholesale",
        "seller",
        "created_at",
    )
    list_filter = ("payment_type", "is_wholesale", "mode", "shop__market")
    date_hierarchy = "created_at"
    inlines = [SaleItemInline]
    autocomplete_fields = ("shop",)


@admin.register(StockIn)
class StockInAdmin(admin.ModelAdmin):
    list_display = ("shop", "product", "quantity", "in_packs", "unit_price", "created_at")
    list_filter = ("shop__market",)


class DailyCloseLineInline(admin.TabularInline):
    model = DailyCloseLine
    extra = 0


@admin.register(DailyClose)
class DailyCloseAdmin(admin.ModelAdmin):
    list_display = ("shop", "date", "computed_sales", "entered_sales")
    list_filter = ("date", "shop__market")
    inlines = [DailyCloseLineInline]


admin.site.register(SaleReturn)
admin.site.register(WriteOff)
admin.site.register(Correction)
admin.site.register(Debt)
