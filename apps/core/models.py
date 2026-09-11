"""Asosiy modellar: umumiy baza, tizim sozlamalari, audit jurnali."""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """Barcha modellar uchun umumiy vaqt maydonlari."""

    created_at = models.DateTimeField(_("Yaratilgan"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("Yangilangan"), auto_now=True)

    class Meta:
        abstract = True


class SystemSettings(models.Model):
    """Yagona yozuv — barcha sozlanadigan chegaralar. Kodda qotirilmaydi.

    `SystemSettings.get_solo()` orqali olinadi (keshlanadi).
    """

    # Rostlik rang chegaralari (%)
    green_threshold = models.PositiveSmallIntegerField(_("Yashil chegara"), default=80)
    yellow_threshold = models.PositiveSmallIntegerField(_("Sariq chegara"), default=50)

    # Rostlik og'irliklari (yig'indisi muhim emas — normallashtiriladi)
    weight_cash = models.PositiveSmallIntegerField(_("Kassa og'irligi"), default=35)
    weight_camera = models.PositiveSmallIntegerField(_("Kamera og'irligi"), default=25)
    weight_stock = models.PositiveSmallIntegerField(_("Qoldiq og'irligi"), default=25)
    weight_price = models.PositiveSmallIntegerField(_("Narx og'irligi"), default=15)

    # "Eng zaif qism" jarimasi: umumiy ball ≤ (zaif qism + shu qiymat)
    weakest_part_cap = models.PositiveSmallIntegerField(_("Eng zaif qism qo'shimchasi"), default=15)

    # Kamera baholash koeffitsientlari
    buyer_ratio = models.DecimalField(
        _("Xaridorga aylanish ulushi"), max_digits=4, decimal_places=2, default=0.35
    )

    # Chegirma jadvali (JSON): chek summasi chegarasi → 3 ta tugma (ming so'm)
    discount_tiers = models.JSONField(
        _("Chegirma jadvali"), default=list, help_text=_("[[chegara, [t1,t2,t3]], ...] — so'mda")
    )
    max_discount_no_cost_pct = models.PositiveSmallIntegerField(
        _("Tannarx noma'lum bo'lsa maks chegirma (%)"), default=30
    )
    rounding_max = models.PositiveIntegerField(_("Yaxlitlash maksimum (so'm)"), default=1000)

    # Xavfsizlik
    login_max_attempts = models.PositiveSmallIntegerField(_("Maks kirish urinishi"), default=5)
    login_lock_minutes = models.PositiveSmallIntegerField(_("Blok davomiyligi (daq)"), default=15)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Tizim sozlamalari")
        verbose_name_plural = _("Tizim sozlamalari")

    def __str__(self):
        return "Tizim sozlamalari"

    def save(self, *args, **kwargs):
        self.pk = 1  # yagona yozuv
        super().save(*args, **kwargs)
        SystemSettings._cache = self

    @classmethod
    def get_solo(cls) -> SystemSettings:
        cached = getattr(cls, "_cache", None)
        if cached is not None:
            return cached
        obj, _created = cls.objects.get_or_create(pk=1, defaults=cls._defaults())
        cls._cache = obj
        return obj

    # Standart chegirma pog'onalari (bozorda savdolashish uchun tayyor tugmalar)
    DEFAULT_DISCOUNT_TIERS = [
        [100_000, [5_000, 10_000, 20_000]],
        [300_000, [10_000, 20_000, 30_000]],
        [None, [50_000, 100_000, 200_000]],
    ]

    @staticmethod
    def _defaults():
        return {"discount_tiers": SystemSettings.DEFAULT_DISCOUNT_TIERS}


class AuditLog(TimeStampedModel):
    """O'zgartirilmaydigan log: kirish, ko'rish, eksport, tekshiruv, sozlama."""

    class Action(models.TextChoices):
        LOGIN = "login", _("Kirish")
        VIEW = "view", _("Ko'rish")
        EXPORT = "export", _("Eksport")
        WRITE = "write", _("O'zgartirish")
        SETTINGS = "settings", _("Sozlama")

    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    action = models.CharField(_("Amal"), max_length=16, choices=Action.choices, default=Action.VIEW)
    method = models.CharField(max_length=8, blank=True)
    path = models.CharField(max_length=300, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    interface = models.CharField(max_length=16, blank=True)  # seller/inspector/panel
    detail = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = _("Audit yozuvi")
        verbose_name_plural = _("Audit jurnali")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.user} {self.action}"
