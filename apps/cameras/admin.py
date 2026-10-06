from django.contrib import admin

from apps.core.admin import EvidenceAdmin

from .models import Camera, CameraEvent, ProductObservation


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


@admin.register(ProductObservation)
class ProductObservationAdmin(EvidenceAdmin):
    list_display = ("product_label", "kind", "quantity", "confidence", "shop", "ended_at", "review_state")
    list_filter = ("kind", "review_state", "shop__market")
    search_fields = ("product_label", "product_code", "event_id")
    date_hierarchy = "ended_at"
