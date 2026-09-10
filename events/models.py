from django.db import models
from django.utils.translation import gettext_lazy as _


# ============================================================================
#  AI / KAMERA HODISALARI
#  Bularni AI worker `POST /api/events/` orqali yuboradi (kamera qo'shilganda).
#  Hozircha bo'sh turadi; sotuvchi qo'lda kiritgan savdolar bilan ishlaymiz.
# ============================================================================

class CustomerVisit(models.Model):
    """AI aniqlagan xaridor: peshtaxta oldida VISITOR_MIN_DWELL_SECONDS dan
    ko'proq to'xtagan odam. O'tib ketganlar va sotuvchining o'zi sanalmaydi."""
    shop = models.ForeignKey("markets.Shop", on_delete=models.CASCADE, related_name="visits")
    camera = models.ForeignKey("cameras.Camera", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="visits")
    timestamp = models.DateTimeField(_("Vaqt"), db_index=True)
    dwell_seconds = models.PositiveIntegerField(_("To'xtash (sek)"), default=0)
    # Bir xil odamni ikki marta sanamaslik uchun AI beradigan trek ID
    track_id = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = _("Xaridor tashrifi")
        verbose_name_plural = _("Xaridor tashriflari")
        indexes = [models.Index(fields=["shop", "timestamp"])]


class CameraTamperEvent(models.Model):
    """Kamera buzilgani/yopilgani — savdoni yashirish belgisi."""
    class Kind(models.TextChoices):
        COVERED = "covered", _("Yopilgan/to'silgan")
        MOVED = "moved", _("Burilgan/siljigan")
        OFFLINE = "offline", _("O'chib qolgan")
        BLURRED = "blurred", _("Xiralashgan")

    camera = models.ForeignKey("cameras.Camera", on_delete=models.CASCADE, related_name="tamper_events")
    timestamp = models.DateTimeField(_("Vaqt"), db_index=True)
    kind = models.CharField(_("Turi"), max_length=20, choices=Kind.choices)
    duration_seconds = models.PositiveIntegerField(_("Davomiyligi (sek)"), default=0)
    clip = models.FileField(_("Video dalil"), upload_to="tamper_clips/", blank=True)

    class Meta:
        verbose_name = _("Kamera buzilishi")
        verbose_name_plural = _("Kamera buzilishlari")


class SaleObservation(models.Model):
    """AI ko'rgan sotuv hodisasi (mahsulot + zona). Aniqligi past — signal uchun,
    dalil uchun emas. Har bittasiga qisqa video klip biriktiriladi."""
    shop = models.ForeignKey("markets.Shop", on_delete=models.CASCADE, related_name="observations")
    camera = models.ForeignKey("cameras.Camera", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="observations")
    timestamp = models.DateTimeField(_("Vaqt"), db_index=True)
    product_guess = models.CharField(_("Taxminiy mahsulot"), max_length=120, blank=True)
    confidence = models.FloatField(_("Ishonch"), default=0)  # 0..1
    clip = models.FileField(_("Video klip"), upload_to="sale_clips/", blank=True)

    class Meta:
        verbose_name = _("AI sotuv kuzatuvi")
        verbose_name_plural = _("AI sotuv kuzatuvlari")


# ============================================================================
#  SOTUVCHI QO'LDA KIRITADIGAN YOZUVLAR (MVP — kamerasiz ham ishlaydi)
# ============================================================================

class PaymentType(models.TextChoices):
    CASH = "cash", _("Naqd")
    CARD = "card", _("Karta")
    TRANSFER = "transfer", _("O'tkazma")


class Sale(models.Model):
    """Sotuvchi kiritgan savdo (chek)."""
    shop = models.ForeignKey("markets.Shop", on_delete=models.CASCADE, related_name="sales")
    seller = models.ForeignKey("accounts.User", null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="sales")
    created_at = models.DateTimeField(_("Vaqt"), auto_now_add=True, db_index=True)
    total_amount = models.DecimalField(_("Summa (so'm)"), max_digits=12, decimal_places=2, default=0)
    payment_type = models.CharField(_("To'lov turi"), max_length=12,
                                    choices=PaymentType.choices, default=PaymentType.CASH)
    is_wholesale = models.BooleanField(_("Ulgurji"), default=False)
    note = models.CharField(_("Izoh"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Savdo")
        verbose_name_plural = _("Savdolar")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.shop.name} — {self.total_amount} so'm"


class SaleItem(models.Model):
    """Savdodagi bitta mahsulot qatori."""
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product_name = models.CharField(_("Mahsulot"), max_length=150)
    quantity = models.DecimalField(_("Miqdor"), max_digits=10, decimal_places=3, default=1)
    unit = models.CharField(_("Birlik"), max_length=20, default="dona")
    unit_price = models.DecimalField(_("Narx (so'm)"), max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return self.quantity * self.unit_price


class Return(models.Model):
    """Qaytarish/almashtirish — sotuvni sun'iy kamaytirmaslik uchun alohida."""
    shop = models.ForeignKey("markets.Shop", on_delete=models.CASCADE, related_name="returns")
    seller = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    amount = models.DecimalField(_("Summa (so'm)"), max_digits=12, decimal_places=2, default=0)
    reason = models.CharField(_("Sabab"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Qaytarish")
        verbose_name_plural = _("Qaytarishlar")


class StockWriteOff(models.Model):
    """Hisobdan chiqarish (chirigan/buzilgan). Foto majburiy; me'yordan oshsa signal."""
    shop = models.ForeignKey("markets.Shop", on_delete=models.CASCADE, related_name="writeoffs")
    seller = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    product_name = models.CharField(_("Mahsulot"), max_length=150)
    quantity = models.DecimalField(_("Miqdor"), max_digits=10, decimal_places=3, default=0)
    unit = models.CharField(_("Birlik"), max_length=20, default="kg")
    photo = models.ImageField(_("Foto (majburiy)"), upload_to="writeoffs/")
    reason = models.CharField(_("Sabab"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Hisobdan chiqarish")
        verbose_name_plural = _("Hisobdan chiqarishlar")
