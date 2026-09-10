from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "method", "path", "ip")
    list_filter = ("method",)
    search_fields = ("user__username", "path")
    readonly_fields = ("user", "timestamp", "method", "path", "ip", "action")

    def has_add_permission(self, request):
        return False
