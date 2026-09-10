from django.db import models
from django.utils.translation import gettext_lazy as _


class Inspection(models.Model):
    """Inspektor tekshiruvi. Natija AI signalini tasdiqlaydi yoki rad etadi —
    shu orqali tizim aniqligini o'lchaymiz va vaqt o'tib yaxshilaymiz."""

    class Result(models.TextChoices):
        CONFIRMED = "confirmed", _("Tasdiqlandi (savdo yashirilgan)")
        FALSE_SIGNAL = "false_signal", _("Noto'g'ri signal")
        PENDING = "pending", _("Jarayonda")

    shop = models.ForeignKey("markets.Shop", on_delete=models.CASCADE, related_name="inspections")
    alert = models.ForeignKey("analytics.Alert", null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="inspections")
    inspector = models.ForeignKey("accounts.User", null=True, blank=True,
                                  on_delete=models.SET_NULL, related_name="inspections")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    visited_at = models.DateTimeField(_("Tashrif vaqti"), null=True, blank=True)
    result = models.CharField(_("Natija"), max_length=15,
                              choices=Result.choices, default=Result.PENDING)
    act_number = models.CharField(_("Dalolatnoma raqami"), max_length=60, blank=True)
    fine_amount = models.DecimalField(_("Jarima (so'm)"), max_digits=14, decimal_places=2,
                                      null=True, blank=True)
    notes = models.TextField(_("Izoh"), blank=True)

    class Meta:
        verbose_name = _("Tekshiruv")
        verbose_name_plural = _("Tekshiruvlar")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.shop.name} — {self.get_result_display()}"


class InspectionPhoto(models.Model):
    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name="photos")
    photo = models.ImageField(upload_to="inspections/")
    caption = models.CharField(max_length=200, blank=True)
