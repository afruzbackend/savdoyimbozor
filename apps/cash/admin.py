from django.contrib import admin

from apps.core.admin import EvidenceAdmin

from .models import CashRecord, DeclarationSync


@admin.register(CashRecord)
class CashRecordAdmin(EvidenceAdmin):
    list_display = ("shop", "date", "amount", "source")
    list_filter = ("source", "date", "shop__market")
    search_fields = ("shop__number", "shop__stir")


@admin.register(DeclarationSync)
class DeclarationSyncAdmin(EvidenceAdmin):
    list_display = ("created_at", "source", "adapter", "ok", "fetched", "saved", "unmatched")
    list_filter = ("ok", "source")
    readonly_fields = [f.name for f in DeclarationSync._meta.fields]
