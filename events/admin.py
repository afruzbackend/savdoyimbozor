from django.contrib import admin

from .models import (CameraTamperEvent, CustomerVisit, Return, Sale, SaleItem,
                     SaleObservation, StockWriteOff)


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("shop", "total_amount", "payment_type", "is_wholesale", "seller", "created_at")
    list_filter = ("payment_type", "is_wholesale", "shop__market")
    date_hierarchy = "created_at"
    inlines = [SaleItemInline]


@admin.register(CustomerVisit)
class CustomerVisitAdmin(admin.ModelAdmin):
    list_display = ("shop", "camera", "dwell_seconds", "timestamp")
    list_filter = ("shop__market",)
    date_hierarchy = "timestamp"


@admin.register(CameraTamperEvent)
class TamperAdmin(admin.ModelAdmin):
    list_display = ("camera", "kind", "duration_seconds", "timestamp")
    list_filter = ("kind",)


admin.site.register(SaleObservation)
admin.site.register(Return)
admin.site.register(StockWriteOff)
