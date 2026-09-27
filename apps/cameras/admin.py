from django.contrib import admin

from apps.core.admin import EvidenceAdmin

from .models import Camera, CameraEvent


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ("name", "market", "shop", "kind", "status", "is_online", "last_seen")
    list_filter = ("kind", "status", "market")
    search_fields = ("name",)
    autocomplete_fields = ("market", "shop")
    readonly_fields = ("token", "last_seen", "is_online")

    @admin.display(boolean=True, description="Online")
    def is_online(self, obj):
        return obj.is_online


@admin.register(CameraEvent)
class CameraEventAdmin(EvidenceAdmin):
    list_display = ("camera", "type", "count", "ts")
    list_filter = ("type",)
    date_hierarchy = "ts"
