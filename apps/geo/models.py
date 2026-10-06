"""Hudud iyerarxiyasi: viloyat → bozor → qator. Hisobotlar viloyat kesimida."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Region(TimeStampedModel):
    name = models.CharField(_("Viloyat"), max_length=120, unique=True)
    code = models.CharField(_("Kod"), max_length=10, blank=True)

    class Meta:
        verbose_name = _("Viloyat")
        verbose_name_plural = _("Viloyatlar")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Market(TimeStampedModel):
    region = models.ForeignKey(
        Region, verbose_name=_("Viloyat"), on_delete=models.PROTECT, related_name="markets"
    )
    name = models.CharField(_("Bozor"), max_length=200)
    address = models.CharField(_("Manzil"), max_length=300, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(_("Faol"), default=True)

    class Meta:
        verbose_name = _("Bozor")
        verbose_name_plural = _("Bozorlar")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def duty_inspector(self):
        """Signal biriktiriladigan tekshiruvchi. Prokuror (kuzatuvchi) ham shu bozorga
        biriktirilishi mumkin — unga signal BERILMAYDI (u faqat ko'radi)."""
        return self.inspectors.filter(role="inspector", is_active=True).order_by("pk").first()


class Row(TimeStampedModel):
    """Bozor ichidagi qator (rasta liniyasi) — xarita va solishtirish uchun."""

    market = models.ForeignKey(
        Market, verbose_name=_("Bozor"), on_delete=models.CASCADE, related_name="rows"
    )
    label = models.CharField(_("Qator"), max_length=60)
    order = models.PositiveSmallIntegerField(_("Tartib"), default=0)

    class Meta:
        verbose_name = _("Qator")
        verbose_name_plural = _("Qatorlar")
        ordering = ["market", "order", "label"]
        unique_together = ("market", "label")

    def __str__(self):
        return f"{self.market.name} — {self.label}"

