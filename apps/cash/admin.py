from django.contrib import admin

from apps.core.admin import EvidenceAdmin

from .models import CashRecord, DeclarationSync, FiscalReceipt, FiscalReceiptLine


@admin.register(CashRecord)
class CashRecordAdmin(EvidenceAdmin):
    list_display = ("shop", "date", "amount", "source")
    list_filter = ("source", "date", "shop__market")
    search_fields = ("shop__number", "shop__stir")


class FiscalReceiptLineInline(admin.TabularInline):
    model = FiscalReceiptLine
    extra = 0
    can_delete = False
    readonly_fields = ("line_number", "product_name", "product_code", "quantity", "unit_price", "line_total")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(FiscalReceipt)
class FiscalReceiptAdmin(EvidenceAdmin):
    list_display = ("source_receipt_id", "shop", "issued_at", "status", "total", "source")
    list_filter = ("source", "status", "shop__market")
    search_fields = ("source_receipt_id", "fiscal_number", "shop__number", "shop__stir")
    readonly_fields = [f.name for f in FiscalReceipt._meta.fields]
    inlines = [FiscalReceiptLineInline]


@admin.register(DeclarationSync)
class DeclarationSyncAdmin(EvidenceAdmin):
    list_display = ("created_at", "source", "adapter", "ok", "fetched", "saved", "unmatched")
    list_filter = ("ok", "source")
    readonly_fields = [f.name for f in DeclarationSync._meta.fields]
