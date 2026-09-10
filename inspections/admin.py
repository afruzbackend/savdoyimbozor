from django.contrib import admin

from .models import Inspection, InspectionPhoto


class PhotoInline(admin.TabularInline):
    model = InspectionPhoto
    extra = 0


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = ("shop", "inspector", "result", "fine_amount", "act_number", "created_at")
    list_filter = ("result", "shop__market")
    search_fields = ("shop__name", "act_number")
    inlines = [PhotoInline]
