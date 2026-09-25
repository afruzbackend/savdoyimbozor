from django.contrib import admin

from .models import CashRecord, DeclarationSync


@admin.register(CashRecord)
class CashRecordAdmin(admin.ModelAdmin):
    list_display = ("shop", "date", "amount", "source")
    list_filter = ("source", "date", "shop__market")
    search_fields = ("shop__number", "shop__stir")


@admin.register(DeclarationSync)
class DeclarationSyncAdmin(admin.ModelAdmin):
    list_display = ("created_at", "source", "adapter", "ok", "fetched", "saved", "unmatched")
    list_filter = ("ok", "source")
    readonly_fields = [f.name for f in DeclarationSync._meta.fields]
