from django.contrib import admin

from .models import AuditLog, SmsMessage, SystemSettings


class EvidenceAdmin(admin.ModelAdmin):
    """Dalil yozuvlari (sotuv, kassa, tekshiruv, audit...) Django admin'da faqat KO'RILADI.

    Ilgari super admin /django-admin/ orqali sotuv summasini, deklaratsiyani yoki tekshiruv natijasini
    iz qoldirmasdan o'zgartira/o'chira olardi, audit jurnalini ham o'chira olardi. Tuzatish faqat
    ilovadagi yo'l bilan (Correction — eski qiymat saqlanadi, nazoratchiga signal).
    """

    def has_add_permission(self, request, *args):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class EvidenceInline(admin.TabularInline):
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SystemSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditLog)
class AuditLogAdmin(EvidenceAdmin):
    list_display = ("created_at", "user", "action", "interface", "path", "ip")
    list_filter = ("action", "interface")
    search_fields = ("user__username", "path")
    readonly_fields = [f.name for f in AuditLog._meta.fields]



@admin.register(SmsMessage)
class SmsMessageAdmin(EvidenceAdmin):
    list_display = ("created_at", "phone", "status", "provider", "key")
    list_filter = ("status", "provider")
    search_fields = ("phone", "key")
    readonly_fields = [f.name for f in SmsMessage._meta.fields]
