from django.contrib import admin

from .models import Camera


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ("name", "market", "is_active", "is_online", "last_heartbeat")
    list_filter = ("market", "is_active")
    search_fields = ("name",)
    filter_horizontal = ("shops",)
    readonly_fields = ("ingest_token", "last_heartbeat", "is_online")

    @admin.display(boolean=True, description="Online")
    def is_online(self, obj):
        return obj.is_online
