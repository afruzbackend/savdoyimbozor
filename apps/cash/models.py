"""Kassa/deklaratsiya yozuvi. Boshida Excel, keyin Soliq API (source orqali adapter)."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class CashRecord(TimeStampedModel):
    class Source(models.TextChoices):
        EXCEL = "excel", _("Excel import")
        TAX_API = "tax_api", _("Soliq API")
        KASSA = "kassa", _("Virtual kassa")

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="cash_records")
    date = models.DateField(_("Sana"), db_index=True)
    amount = models.BigIntegerField(_("Summa (so'm)"), default=0)
    source = models.CharField(
        _("Manba"), max_length=12, choices=Source.choices, default=Source.EXCEL
    )

    class Meta:
        verbose_name = _("Kassa/Deklaratsiya")
        verbose_name_plural = _("Kassa/Deklaratsiya")
        unique_together = ("shop", "date", "source")
        indexes = [models.Index(fields=["shop", "date"])]

    def __str__(self):
        return f"{self.shop} {self.date}: {self.amount}"
