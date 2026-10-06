from django.contrib import admin

from apps.core.admin import EvidenceAdmin, EvidenceInline

from .models import (
    Correction,
    DailyClose,
    DailyCloseLine,
    Debt,
    ReceiptReport,
    RegisterClose,
    Sale,
    SaleItem,
    SaleReturn,
    StockAdjustment,
    StockIn,
    WriteOff,
)


class SaleItemInline(EvidenceInline):
    model = SaleItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(EvidenceAdmin):
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
class StockInAdmin(EvidenceAdmin):
    list_display = ("shop", "product", "quantity", "in_packs", "unit_price", "created_at")
    list_filter = ("shop__market",)


class DailyCloseLineInline(EvidenceInline):
    model = DailyCloseLine
    extra = 0


@admin.register(DailyClose)
class DailyCloseAdmin(EvidenceAdmin):
    list_display = ("shop", "date", "computed_sales", "entered_sales")
    list_filter = ("date", "shop__market")
    inlines = [DailyCloseLineInline]


admin.site.register(SaleReturn, EvidenceAdmin)
admin.site.register(WriteOff, EvidenceAdmin)
admin.site.register(Correction, EvidenceAdmin)
admin.site.register(Debt, EvidenceAdmin)
admin.site.register(RegisterClose, EvidenceAdmin)


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    """Qoldiqni faqat imzoli sanoq tuzatishi orqali o'zgartirish."""

    list_display = ("product", "counted_qty", "reason", "user", "created_at")
    search_fields = ("product__name", "reason", "user__username")
    autocomplete_fields = ("product",)
    readonly_fields = ("user", "created_at")

    def has_change_permission(self, request, obj=None):
        return obj is None

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change:
            return
        obj.user = request.user
        obj.save()


@admin.register(ReceiptReport)
class ReceiptReportAdmin(EvidenceAdmin):
    list_display = ("sale", "paid_amount", "created_at", "alert")
    readonly_fields = ("sale", "paid_amount", "comment", "alert", "created_at")
