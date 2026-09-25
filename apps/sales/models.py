"""Savdo domeni. Pul = butun son (so'm). Yozuv o'chmaydi (faqat Correction)."""

from datetime import UTC

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
    # Kirim DALILI: kompensatsiya kutilganda kirimni oshirib yozishga qarshi
    supplier_name = models.CharField(_("Yetkazib beruvchi"), max_length=200, blank=True)
    supplier_stir = models.CharField(_("Yetkazib beruvchi STIR"), max_length=15, blank=True)
    invoice_photo = models.ImageField(_("Nakladnoy fotosi"), upload_to="stockins/%Y/%m/", blank=True)

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
    # Xaridorga QR chek: taxmin qilib bo'lmaydigan kod (/chek/<kod>/, login shart emas)
    public_code = models.CharField(max_length=16, null=True, blank=True, unique=True)

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

    # O/0, I/1, L chiqarilgan — xaridor qo'lda terganda adashmasin
    CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

    def ensure_public_code(self) -> str:
        """Chek kodi (bo'lmasa yaratiladi). 31^10 ≈ 8·10^14 — terib topib bo'lmaydi."""
        if self.public_code:
            return self.public_code
        import secrets

        from django.db import IntegrityError, transaction

        for _attempt in range(5):
            code = "".join(secrets.choice(self.CODE_ALPHABET) for _ in range(10))
            try:
                with transaction.atomic():
                    updated = Sale.objects.filter(pk=self.pk, public_code__isnull=True).update(
                        public_code=code
                    )
            except IntegrityError:
                continue  # juda kam uchraydigan to'qnashuv — boshqa kod
            if not updated:  # parallel so'rov allaqachon bergan
                code = Sale.objects.values_list("public_code", flat=True).get(pk=self.pk)
            self.public_code = code
            return code
        raise RuntimeError("Chek kodi yaratilmadi")


class ReceiptReport(TimeStampedModel):
    """Xaridor chek sahifasidan: "men boshqa summa to'ladim". Chekka bitta xabar."""

    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name="buyer_report")
    paid_amount = models.BigIntegerField(_("Xaridor to'lagan (so'm)"))
    comment = models.CharField(_("Izoh"), max_length=300, blank=True)
    alert = models.ForeignKey(
        "analytics.Alert", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = _("Xaridor xabari")
        verbose_name_plural = _("Xaridor xabarlari")

    def __str__(self):
        return f"{self.sale_id}: {self.paid_amount}"


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
    # Kun yakunidagi rasta fotosi — qoldiqning ko'rinadigan dalili (yong'in/kompensatsiya)
    photo = models.ImageField(_("Rasta fotosi"), upload_to="closes/%Y/%m/", blank=True)

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
    # Xaridorga SMS eslatma (1 kun oldin, o'sha kuni, 3 kun o'tganda). Sotuvchi o'chira oladi.
    sms_remind = models.BooleanField(_("Xaridorga SMS eslatma"), default=True)
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


class StockMove(models.Model):
    """O'ZGARMAS tovar harakati jurnali (append-only) — har kirim/sotuv/chiqarish/sanoq.

    Nima uchun: "yong'in kuni soat 14:00 da har do'konda nima qancha bor edi?" degan
    savolga (kompensatsiya, prokuratura) ANIQ javob va dalil. Product.stock — faqat joriy
    holat; tarix shu jurnalda. Har yozuv oldingisining xeshini saqlaydi (zanjir): bitta
    yozuv o'zgartirilsa yoki o'chirilsa, zanjir buziladi va tekshiruvda ko'rinadi.
    """

    class Kind(models.TextChoices):
        OPENING = "opening", _("Boshlang'ich qoldiq")
        IN = "in", _("Kirim")
        SALE = "sale", _("Sotuv")
        WRITEOFF = "writeoff", _("Hisobdan chiqarish")
        RETURN = "return", _("Qaytarish")
        COUNT = "count", _("Sanoq (kun yakuni)")

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="stock_moves")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="moves"
    )
    kind = models.CharField(_("Tur"), max_length=10, choices=Kind.choices)
    qty = models.DecimalField(_("O'zgarish"), max_digits=12, decimal_places=3)  # +/−
    balance = models.DecimalField(_("Qoldiq (keyin)"), max_digits=12, decimal_places=3)
    unit_price = models.BigIntegerField(_("Narx (o'sha payt)"), default=0)
    ref = models.CharField(_("Hujjat"), max_length=60, blank=True)  # "Sale#12", "StockIn#5"
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(_("Vaqt"), db_index=True)
    prev_hash = models.CharField(max_length=64, blank=True)
    hash = models.CharField(max_length=64)

    class Meta:
        verbose_name = _("Tovar harakati")
        verbose_name_plural = _("Tovar harakatlari jurnali")
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["shop", "created_at"]),
            models.Index(fields=["product", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.qty:+g} → {self.balance:g} ({self.ref})"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("Tovar harakati jurnali o'zgartirilmaydi (faqat yangi yozuv).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Tovar harakati jurnali o'chirilmaydi.")

    def compute_hash(self) -> str:
        return stock_move_hash(
            self.prev_hash, self.shop_id, self.product_id, self.kind, self.qty,
            self.balance, self.unit_price, self.ref, self.created_at,
        )


def stock_move_hash(prev, shop_id, product_id, kind, qty, balance, price, ref, at) -> str:
    """Kanonik xesh: Decimal 3 xonali, vaqt UTC mikrosekundgacha (bazadan qaytganda ham bir xil)."""
    import hashlib
    from decimal import Decimal

    def d3(x):
        return f"{Decimal(x):.3f}"

    raw = "|".join([
        prev or "", str(shop_id), str(product_id), kind, d3(qty), d3(balance), str(int(price)),
        ref or "", at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f"),
    ])
    return hashlib.sha256(raw.encode()).hexdigest()
