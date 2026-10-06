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


class FiscalReceipt(TimeStampedModel):
    """Tashqi kassa/Soliq manbasidan kelgan bitta fiskal chek.

    CashRecord kunlik jami bo'lib qoladi; mahsulot bilan solishtirish faqat ushbu
    chek va uning qatorlari kelganda bajariladi. Tashqi format tasdiqlanmaguncha
    hech qaysi adapter bu modelni taxminiy ma'lumot bilan to'ldirmaydi.
    """

    class Status(models.TextChoices):
        ISSUED = "issued", _("Rasmiylashtirilgan")
        RETURNED = "returned", _("Qaytarish cheki")
        CANCELLED = "cancelled", _("Bekor qilingan")

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="fiscal_receipts")
    source = models.CharField(_("Manba"), max_length=12, choices=CashRecord.Source.choices)
    source_receipt_id = models.CharField(
        _("Manbadagi chek ID"), max_length=128,
        help_text=_("Tashqi tizimdagi barqaror, takrorlanmaydigan chek identifikatori."),
    )
    fiscal_number = models.CharField(_("Fiskal raqam"), max_length=100, blank=True)
    issued_at = models.DateTimeField(_("Chek vaqti"), db_index=True)
    status = models.CharField(_("Holat"), max_length=12, choices=Status.choices, default=Status.ISSUED)
    original_receipt = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="return_receipts",
        verbose_name=_("Asl chek"),
    )
    total = models.BigIntegerField(_("Chek jami (so'm)"), default=0)
    raw_payload = models.JSONField(
        _("Manba javobi"), default=dict, blank=True,
        help_text=_("Manba formatini keyin tekshirish uchun o'zgartirilmagan javob."),
    )

    class Meta:
        verbose_name = _("Fiskal chek")
        verbose_name_plural = _("Fiskal cheklar")
        ordering = ["-issued_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "source_receipt_id"], name="uniq_fiscal_receipt_source_id"
            )
        ]
        indexes = [models.Index(fields=["shop", "issued_at"]), models.Index(fields=["status", "issued_at"])]

    def __str__(self):
        return f"{self.shop} · {self.source_receipt_id} · {self.total}"


class FiscalReceiptLine(models.Model):
    """Fiskal chekdagi mahsulot qatori; lokal SKUga taxmin bilan bog'lanmaydi."""

    receipt = models.ForeignKey(FiscalReceipt, on_delete=models.CASCADE, related_name="lines")
    line_number = models.PositiveIntegerField(_("Qator raqami"))
    product_name = models.CharField(_("Mahsulot nomi"), max_length=300)
    product_code = models.CharField(_("Mahsulot kodi"), max_length=128, blank=True)
    quantity = models.DecimalField(_("Miqdor"), max_digits=12, decimal_places=3)
    unit_price = models.BigIntegerField(_("Birlik narxi (so'm)"), default=0)
    line_total = models.BigIntegerField(_("Qator jami (so'm)"), default=0)

    class Meta:
        verbose_name = _("Fiskal chek qatori")
        verbose_name_plural = _("Fiskal chek qatorlari")
        ordering = ["line_number", "id"]
        constraints = [
            models.UniqueConstraint(fields=["receipt", "line_number"], name="uniq_fiscal_receipt_line")
        ]

    def __str__(self):
        return f"{self.receipt_id} #{self.line_number}: {self.product_name}"


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
