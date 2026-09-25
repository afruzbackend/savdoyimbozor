from django.contrib import admin

from .models import AuditLog, SmsMessage, SystemSettings


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SystemSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "interface", "path", "ip")
    list_filter = ("action", "interface")
    search_fields = ("user__username", "path")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SmsMessage)
class SmsMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "phone", "status", "provider", "key")
    list_filter = ("status", "provider")
    search_fields = ("phone", "key")
    readonly_fields = [f.name for f in SmsMessage._meta.fields]
