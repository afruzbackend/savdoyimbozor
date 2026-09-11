from django.contrib import admin

from .models import CashRecord


@admin.register(CashRecord)
class CashRecordAdmin(admin.ModelAdmin):
    list_display = ("shop", "date", "amount", "source")
    list_filter = ("source", "date", "shop__market")
    search_fields = ("shop__number", "shop__stir")
