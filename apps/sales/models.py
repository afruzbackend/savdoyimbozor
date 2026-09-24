"""Savdo domeni. Pul = butun son (so'm). Yozuv o'chmaydi (faqat Correction)."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class PaymentType(models.TextChoices):
    CASH = "cash", _("Naqd")
    CARD = "card", _("Karta")
    TRANSFER = "transfer", _("O'tkazma")
    DEBT = "debt", _("Nasiya")  # pul keyin — sandiqqa tushmaydi, nasiya daftariga yoziladi


class SaleMode(models.TextChoices):
    SCAN = "scan", _("Skaner")
    QUICK = "quick", _("Tez")


class StockIn(TimeStampedModel):
    """Kirim — do'konga mahsulot kelishi (qopda ham)."""

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="stock_ins")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="stock_ins"
    )
    seller = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.DecimalField(_("Miqdor"), max_digits=12, decimal_places=3)
    in_packs = models.BooleanField(_("Qopda"), default=False)
    unit_price = models.BigIntegerField(_("Kelish narxi (so'm)"), default=0)
    source = models.CharField(_("Manba"), max_length=30, default="manual")

    class Meta:
        verbose_name = _("Kirim")
        verbose_name_plural = _("Kirimlar")
        indexes = [models.Index(fields=["shop", "-created_at"])]


class Sale(TimeStampedModel):
    """Sotuv (chek)."""

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="sales")
    seller = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="sales"
    )
    mode = models.CharField(
        _("Rejim"), max_length=8, choices=SaleMode.choices, default=SaleMode.QUICK
    )
    subtotal = models.BigIntegerField(_("Oraliq summa"), default=0)
    discount = models.BigIntegerField(_("Chegirma"), default=0)
    rounding = models.BigIntegerField(
        _("Yaxlitlash"), default=0
    )  # faqat pastga, statistikaga kirmaydi
    total = models.BigIntegerField(_("Jami (so'm)"), default=0)
    payment_type = models.CharField(
        _("To'lov"), max_length=12, choices=PaymentType.choices, default=PaymentType.CASH
    )
    is_wholesale = models.BooleanField(_("Ulgurji"), default=False)
    # Vaqt serverdan; client vaqti va kechikish belgisi (offline navbat uchun)
    client_ts = models.DateTimeField(_("Qurilma vaqti"), null=True, blank=True)
    is_late = models.BooleanField(_("Kech kiritilgan"), default=False)
    # Qurilma bergan noyob id — offline navbatdan qayta yuborilganda dublikat bo'lmasin
    client_uid = models.CharField(_("Qurilma ID"), max_length=64, blank=True, default="")
    note = models.CharField(_("Izoh"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Sotuv")
        verbose_name_plural = _("Sotuvlar")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["shop", "-created_at"]),
            models.Index(fields=["-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["shop", "client_uid"],
                condition=~models.Q(client_uid=""),
                name="uniq_sale_shop_client_uid",
            )
        ]

    def __str__(self):
        return f"{self.shop} — {self.total} so'm"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sale_items",
    )
    product_name = models.CharField(_("Mahsulot"), max_length=200)
    quantity = models.DecimalField(_("Miqdor"), max_digits=12, decimal_places=3, default=1)
    unit_price = models.BigIntegerField(_("Narx (so'm)"), default=0)
    line_total = models.BigIntegerField(_("Qator jami"), default=0)

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"


class SaleReturn(TimeStampedModel):
    """Qaytarish/almashtirish — savdoni sun'iy kamaytirmaslik uchun alohida."""

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="returns")
    sale = models.ForeignKey(
        Sale, null=True, blank=True, on_delete=models.SET_NULL, related_name="returns"
    )
    seller = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    product = models.ForeignKey(
        "catalog.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="returns"
    )
    quantity = models.DecimalField(_("Miqdor"), max_digits=12, decimal_places=3, default=0)
    amount = models.BigIntegerField(_("Summa (so'm)"), default=0)
    reason = models.CharField(_("Sabab"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Qaytarish")
        verbose_name_plural = _("Qaytarishlar")


class WriteOff(TimeStampedModel):
    """Hisobdan chiqarish (chirigan/buzilgan). Foto majburiy; me'yordan oshsa signal."""

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="writeoffs")
    product = models.ForeignKey(
        "catalog.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="writeoffs",
    )
    seller = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    product_name = models.CharField(_("Mahsulot"), max_length=200)
    quantity = models.DecimalField(_("Miqdor"), max_digits=12, decimal_places=3, default=0)
    photo = models.ImageField(_("Foto"), upload_to="writeoffs/%Y/%m/")
    reason = models.CharField(_("Sabab"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Hisobdan chiqarish")
        verbose_name_plural = _("Hisobdan chiqarishlar")


class DailyClose(TimeStampedModel):
    """Kun yakuni: ertalabki qoldiq + kirim − chiqim − kechki qoldiq."""

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="daily_closes")
    seller = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    date = models.DateField(_("Sana"), db_index=True)
    computed_sales = models.BigIntegerField(_("Hisoblangan savdo"), default=0)
    entered_sales = models.BigIntegerField(_("Kiritilgan savdo"), default=0)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = _("Kun yakuni")
        verbose_name_plural = _("Kun yakunlari")
        unique_together = ("shop", "date")


class DailyCloseLine(models.Model):
    close = models.ForeignKey(DailyClose, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("catalog.Product", null=True, blank=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=200)
    morning_qty = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    evening_qty = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    unit_price = models.BigIntegerField(default=0)

    def __str__(self):
        return f"{self.product_name}: {self.morning_qty}→{self.evening_qty}"


class Correction(TimeStampedModel):
    """Tuzatish tarixi — yozuv o'chmaydi, eski qiymat saqlanadi."""

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="corrections")
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    target_model = models.CharField(max_length=60)
    target_id = models.BigIntegerField()
    field = models.CharField(max_length=60)
    old_value = models.CharField(max_length=200)
    new_value = models.CharField(max_length=200)
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = _("Tuzatish")
        verbose_name_plural = _("Tuzatishlar")


class RegisterClose(TimeStampedModel):
    """Kassa yopish (Z-hisobot) — kun oxirida sotuvchi naqdni sanaydi.

    MUHIM: bu CashRecord (mustaqil deklaratsiya) EMAS. Rostlik uchun kassa
    manbasi tashqi (Excel/Soliq) bo'lib qoladi. Bu yozuv sotuvchining o'z
    kassasini boshqarishi uchun; sanagan naqd bilan kutilgan naqd farqi
    (kamomad/ortiqcha) inspektor uchun ham signal bo'lishi mumkin.
    """

    shop = models.ForeignKey(
        "shops.Shop", on_delete=models.PROTECT, related_name="register_closes"
    )
    seller = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    date = models.DateField(_("Sana"), db_index=True)
    # Kutilgan naqd = ertalabki maydalik + naqd sotuv + nasiyadan qaytgan naqd
    expected_cash = models.BigIntegerField(_("Kutilgan naqd (so'm)"), default=0)
    opening_cash = models.BigIntegerField(_("Ertalabki maydalik (so'm)"), default=0)
    debt_cash_in = models.BigIntegerField(_("Nasiyadan qaytgan naqd (so'm)"), default=0)
    counted_cash = models.BigIntegerField(_("Sanalgan naqd (so'm)"), default=0)
    card_total = models.BigIntegerField(_("Karta (so'm)"), default=0)
    transfer_total = models.BigIntegerField(_("O'tkazma (so'm)"), default=0)
    checks_count = models.PositiveIntegerField(_("Cheklar soni"), default=0)
    note = models.CharField(_("Izoh"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Kassa yopish")
        verbose_name_plural = _("Kassa yopishlar")
        unique_together = ("shop", "date")
        indexes = [models.Index(fields=["shop", "-date"])]

    @property
    def difference(self):
        """Sanalgan − kutilgan (manfiy = kamomad)."""
        return self.counted_cash - self.expected_cash

    def __str__(self):
        return f"{self.shop} Z-{self.date}: {self.counted_cash}"


class CashOpen(TimeStampedModel):
    """Kun boshidagi sandiqdagi maydalik (qaytim uchun).

    Faqat kunning BIRINCHI sotuvidan oldin kiritiladi/o'zgartiriladi — aks holda
    kechqurun yozilmagan savdo pulini "maydalik edi" deb yashirish mumkin bo'lardi.
    Kiritilmasa kechqurun maydalik "ortiqcha" bo'lib, noto'g'ri signal chiqardi.
    """

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="cash_opens")
    seller = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    date = models.DateField(_("Sana"), db_index=True)
    amount = models.BigIntegerField(_("Maydalik (so'm)"), default=0)

    class Meta:
        verbose_name = _("Kun boshi maydaligi")
        verbose_name_plural = _("Kun boshi maydaliklari")
        unique_together = ("shop", "date")


class Debt(TimeStampedModel):
    """Nasiya daftari."""

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="debts")
    customer_name = models.CharField(_("Xaridor"), max_length=200)
    customer_phone = models.CharField(_("Telefon"), max_length=20, blank=True)
    amount = models.BigIntegerField(_("Summa (so'm)"), default=0)
    due_date = models.DateField(_("Qaytarish sanasi"), null=True, blank=True, db_index=True)
    paid_amount = models.BigIntegerField(_("To'langan qismi (so'm)"), default=0)
    is_paid = models.BooleanField(_("To'langan"), default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    # Sotuv ekranida "Nasiya" bilan sotilgan bo'lsa — o'sha chek
    sale = models.ForeignKey(
        Sale, null=True, blank=True, on_delete=models.SET_NULL, related_name="debt_records"
    )

    class Meta:
        verbose_name = _("Nasiya")
        verbose_name_plural = _("Nasiyalar")

    @property
    def remaining(self):
        return max(0, self.amount - self.paid_amount)


class DebtPayment(TimeStampedModel):
    """Nasiya to'lovi (qisman ham). Naqd to'lov kassadagi kutilgan naqdga qo'shiladi."""

    debt = models.ForeignKey(Debt, on_delete=models.PROTECT, related_name="payments")
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="debt_payments")
    seller = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.BigIntegerField(_("Summa (so'm)"))
    method = models.CharField(
        _("To'lov"), max_length=12, choices=PaymentType.choices[:3], default=PaymentType.CASH
    )

    class Meta:
        verbose_name = _("Nasiya to'lovi")
        verbose_name_plural = _("Nasiya to'lovlari")
        indexes = [models.Index(fields=["shop", "-created_at"])]
