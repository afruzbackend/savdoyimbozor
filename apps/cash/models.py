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


# Bir kunga bir nechta manba kelsa QO'SHILMAYDI — eng ishonchlisi olinadi
# (Excel qo'lda yuklangan, Soliq API esa fiskal ma'lumotning o'zi).
SOURCE_PRIORITY = {
    CashRecord.Source.TAX_API: 3,
    CashRecord.Source.KASSA: 2,
    CashRecord.Source.EXCEL: 1,
}


class DeclarationSync(TimeStampedModel):
    """Soliq/kassa sinxronlash jurnali — oxirgi holat panelda ko'rinadi."""

    source = models.CharField(max_length=12, choices=CashRecord.Source.choices)
    adapter = models.CharField(max_length=20, blank=True)
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    ok = models.BooleanField(default=False)
    fetched = models.PositiveIntegerField(default=0)  # kelgan qatorlar
    saved = models.PositiveIntegerField(default=0)  # yozilgan do'kon-kun
    unmatched = models.PositiveIntegerField(default=0)  # do'kon topilmagan qatorlar
    problems = models.JSONField(default=list, blank=True)  # birinchi xatolar namunasi
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Deklaratsiya sinxronlash")
        verbose_name_plural = _("Deklaratsiya sinxronlash")

    def __str__(self):
        return f"{self.get_source_display()} {self.created_at:%Y-%m-%d %H:%M} ({'ok' if self.ok else 'xato'})"
