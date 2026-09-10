from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditLog(models.Model):
    """Har bir muhim ko'rish/yuklab olish/o'zgartirish yozuvi."""
    user = models.ForeignKey("accounts.User", null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="audit_logs")
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=300)
    ip = models.GenericIPAddressField(null=True, blank=True)
    action = models.CharField(_("Amal"), max_length=120, blank=True)

    class Meta:
        verbose_name = _("Audit yozuvi")
        verbose_name_plural = _("Audit jurnali")
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.user} {self.method} {self.path}"
