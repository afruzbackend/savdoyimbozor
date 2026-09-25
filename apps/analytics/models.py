"""Tahlil: bozor narxi, kunlik rostlik balli (agregat), signal, tekshiruv, e'tiroz."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class MarketPrice(TimeStampedModel):
    """Bozor narxi (kunlik): mahsulot toifasi bo'yicha median/p25/p75 (so'm)."""

    market = models.ForeignKey("geo.Market", on_delete=models.CASCADE, related_name="prices")
    product_category = models.ForeignKey(
        "catalog.ProductCategory", on_delete=models.CASCADE, related_name="market_prices"
    )
    date = models.DateField(db_index=True)
    median = models.BigIntegerField(default=0)
    p25 = models.BigIntegerField(default=0)
    p75 = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = _("Bozor narxi")
        verbose_name_plural = _("Bozor narxlari")
        unique_together = ("market", "product_category", "date")


class DailyScore(TimeStampedModel):
    """Kunlik rostlik balli (oldindan hisoblangan agregat — dashboard tez ishlashi uchun)."""

    shop = models.ForeignKey("shops.Shop", on_delete=models.CASCADE, related_name="scores")
    date = models.DateField(db_index=True)
    truth_pct = models.PositiveSmallIntegerField(_("Rostlik %"), default=0)
    # Tarkib: {"cash": 80, "camera": null, "stock": 60, "price": 90}
    parts = models.JSONField(default=dict)
    weakest = models.CharField(_("Eng zaif qism"), max_length=20, blank=True)
    entered_sales = models.BigIntegerField(default=0)
    cash_amount = models.BigIntegerField(default=0)
    # Mustaqil manbalar yozilgandan qancha ko'p savdo ko'rsatdi = yashirilgan savdo (so'm)
    hidden_sales = models.BigIntegerField(_("Yashirilgan savdo (so'm)"), default=0)
    # Rostlik O'LCHANDIMI (biror solishtirish manbasi bor). False bo'lsa truth_pct=0 bu
    # "ma'lumot yo'q" — o'rtachalarga, reytingga, xavfli ro'yxatga KIRMAYDI.
    measured = models.BooleanField(_("O'lchangan"), default=False, db_index=True)

    class Meta:
        verbose_name = _("Kunlik ball")
        verbose_name_plural = _("Kunlik ballar")
        unique_together = ("shop", "date")
        indexes = [
            models.Index(fields=["shop", "date"]),
            models.Index(fields=["date", "truth_pct"]),
        ]

    @property
    def has_data(self) -> bool:
        """Solishtirish uchun biror manba (kassa/kamera/qoldiq/narx) bormi.

        Hech biri bo'lmasa rostlik O'LCHANMAYDI — 0% (yashiruvchi) EMAS,
        balki "ma'lumot yetarli emas" holati. Xarita/hisobotda kulrang ko'rsatiladi.
        """
        return any(v is not None for v in (self.parts or {}).values())


class Alert(TimeStampedModel):
    class Level(models.TextChoices):
        GREEN = "green", _("Yashil")
        YELLOW = "yellow", _("Sariq")
        RED = "red", _("Qizil")

    class Status(models.TextChoices):
        NEW = "new", _("Yangi")
        ASSIGNED = "assigned", _("Biriktirilgan")
        RESOLVED = "resolved", _("Yakunlangan")
        DISMISSED = "dismissed", _("E'tiborsiz")

    class Kind(models.TextChoices):
        TRUTH = "truth", _("Rostlik darajasi")
        CASH_MISMATCH = "cash_mismatch", _("Kassa nomuvofiqligi")
        ZERO_SALES = "zero_sales", _("Savdo kiritilmagan")
        ANOMALY = "anomaly", _("Savdo keskin tushdi")
        BUYER_REPORT = "buyer_report", _("Xaridor xabari")
        GATE_UNRECORDED = "gate_unrecorded", _("Hujjatsiz kirim")

    shop = models.ForeignKey("shops.Shop", on_delete=models.CASCADE, related_name="alerts")
    date = models.DateField()
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.TRUTH)
    level = models.CharField(max_length=10, choices=Level.choices)
    reason = models.CharField(_("Sabab"), max_length=300)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    assigned_to = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="alerts"
    )
    telegram_sent = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Signal")
        verbose_name_plural = _("Signallar")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["shop", "date"]),
        ]

    def __str__(self):
        return f"[{self.level}] {self.shop}: {self.reason}"


class Inspection(TimeStampedModel):
    """Tekshiruvchi natijasi — signalni tasdiqlaydi yoki rad etadi (aniqlik o'lchovi)."""

    class Result(models.TextChoices):
        CONFIRMED = "confirmed", _("Tasdiqlandi")
        FALSE = "false", _("Noto'g'ri signal")
        PENDING = "pending", _("Jarayonda")

    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="inspections")
    alert = models.ForeignKey(
        Alert, null=True, blank=True, on_delete=models.SET_NULL, related_name="inspections"
    )
    inspector = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inspections",
    )
    result = models.CharField(max_length=12, choices=Result.choices, default=Result.PENDING)
    act_number = models.CharField(_("Dalolatnoma"), max_length=60, blank=True)
    fine_amount = models.BigIntegerField(_("Jarima (so'm)"), null=True, blank=True)
    photo = models.ImageField(upload_to="inspections/%Y/%m/", blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Tekshiruv")
        verbose_name_plural = _("Tekshiruvlar")
        ordering = ["-created_at"]


class Appeal(TimeStampedModel):
    """Sotuvchi e'tirozi (signalga)."""

    class Status(models.TextChoices):
        NEW = "new", _("Yangi")
        ACCEPTED = "accepted", _("Qabul qilindi")
        REJECTED = "rejected", _("Rad etildi")

    shop = models.ForeignKey("shops.Shop", on_delete=models.CASCADE, related_name="appeals")
    alert = models.ForeignKey(
        Alert, null=True, blank=True, on_delete=models.SET_NULL, related_name="appeals"
    )
    author = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL)
    message = models.TextField(_("Matn"))
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    response = models.TextField(_("Javob"), blank=True)

    class Meta:
        verbose_name = _("E'tiroz")
        verbose_name_plural = _("E'tirozlar")
        ordering = ["-created_at"]


class Incident(TimeStampedModel):
    """Favqulodda holat (yong'in, suv toshqini, o'g'irlik...) — bozor holati MUHRLANADI.

    E'lon qilingan paytdagi har do'kon ombori (o'zgarmas jurnaldan) bir marta hisoblanib
    `snapshot` ga yoziladi va xeshlanadi. Keyin o'zgartirilmaydi — kompensatsiya,
    sug'urta va prokuratura uchun rasmiy asos. Xesh mos kelmasa sahifada ko'rinadi.
    """

    class Kind(models.TextChoices):
        FIRE = "fire", _("Yong'in")
        FLOOD = "flood", _("Suv toshqini")
        THEFT = "theft", _("O'g'irlik")
        COLLAPSE = "collapse", _("Qulash / avariya")
        OTHER = "other", _("Boshqa")

    market = models.ForeignKey("geo.Market", on_delete=models.PROTECT, related_name="incidents")
    kind = models.CharField(_("Turi"), max_length=12, choices=Kind.choices)
    occurred_at = models.DateTimeField(_("Sodir bo'lgan vaqt"), db_index=True)
    description = models.TextField(_("Tavsif"), blank=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="incidents"
    )
    number = models.CharField(_("Raqam"), max_length=30, blank=True)
    snapshot = models.JSONField(default=dict)
    snapshot_hash = models.CharField(max_length=64)
    total_value = models.BigIntegerField(_("Jami ombor qiymati"), default=0)
    shops_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = _("Favqulodda holat")
        verbose_name_plural = _("Favqulodda holatlar")
        ordering = ["-occurred_at"]

    def __str__(self):
        return f"{self.number} {self.get_kind_display()} — {self.market}"

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(
            snapshot_hash=self.snapshot_hash
        ).exists():
            raise ValueError("Muhrlangan holat o'zgartirilmaydi.")
        super().save(*args, **kwargs)
