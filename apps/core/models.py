"""Asosiy modellar: umumiy baza, tizim sozlamalari, audit jurnali."""

from __future__ import annotations

import time

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

    # Kassa kamomadi signali: sanalgan naqd kutilgandan shu %dan ko'p kam bo'lsa signal
    cash_shortage_pct = models.PositiveSmallIntegerField(
        _("Kassa kamomadi chegarasi (%)"), default=15
    )
    # Soliq stavkasi — yashirilgan savdodan potensial qo'shimcha soliqni baholash uchun
    tax_rate_percent = models.PositiveSmallIntegerField(_("Soliq stavkasi (%)"), default=12)
    # Jarima ustamasi — dalolatnomadagi taxminiy jarima = yashirilgan soliq × (1 + ustama%)
    fine_penalty_percent = models.PositiveSmallIntegerField(
        _("Jarima ustamasi (%)"), default=100
    )
    # Anomaliya signali: kunlik savdo 30-kunlik o'rtachadan shu %dan ko'p tushsa
    anomaly_drop_pct = models.PositiveSmallIntegerField(
        _("Savdo tushishi chegarasi (%)"), default=60
    )

    # Kamera baholash koeffitsientlari
    buyer_ratio = models.DecimalField(
        _("Xaridorga aylanish ulushi"), max_digits=4, decimal_places=2, default=0.35
    )

    # Chegirma jadvali (JSON): chek summasi chegarasi → 3 ta tugma (ming so'm)
    discount_tiers = models.JSONField(
        _("Chegirma jadvali"), default=list, help_text=_("[[chegara, [t1,t2,t3]], ...] — so'mda")
    )
    # O'zbekcha savdolashish: chegirma tugmalari chek summasining foizi sifatida
    # hisoblanadi (yaxlitlanadi) — chek qanchaligidan qat'i nazar mantiqli chiqadi.
    discount_percents = models.JSONField(
        _("Chegirma foizlari"), default=list, help_text=_("[5, 10, 15] — chek summasidan %")
    )
    max_discount_no_cost_pct = models.PositiveSmallIntegerField(
        _("Tannarx noma'lum bo'lsa maks chegirma (%)"), default=30
    )
    rounding_max = models.PositiveIntegerField(_("Yaxlitlash maksimum (so'm)"), default=1000)

    # Kirim dalili: shu summadan (so'm) katta kirimga nakladnoy fotosi MAJBURIY
    stockin_photo_min = models.PositiveBigIntegerField(
        _("Nakladnoy majburiy summa (so'm)"), default=1_000_000
    )
    # Hisobdan chiqarish signali: 30 kunda chiqarilgan ulush mahsulot turi me'yoridan oshsa VA
    # qiymati shundan (so'm) kam bo'lmasa — mayda chiqimlarga signal yog'ilmasin
    writeoff_alert_min = models.PositiveBigIntegerField(
        _("Hisobdan chiqarish signali — kamida (so'm)"), default=200_000
    )
    # Sotuv summasini kamaytirish (tuzatish) signali: kunlik kiritilgan savdoning shu %idan VA shu
    # summadan ko'p kamaytirilsa — xaridorga to'liq chek berib, keyin yozuvni kamaytirish yo'li yopiladi
    correction_alert_pct = models.PositiveSmallIntegerField(
        _("Tuzatish signali — kunlik savdodan (%)"), default=10
    )
    correction_alert_min = models.PositiveBigIntegerField(
        _("Tuzatish signali — kamida (so'm)"), default=100_000
    )

    # Xavfsizlik
    login_max_attempts = models.PositiveSmallIntegerField(_("Maks kirish urinishi"), default=5)
    login_lock_minutes = models.PositiveSmallIntegerField(_("Blok davomiyligi (daq)"), default=15)
    # Admin / tekshiruvchi / prokuror uchun ikki bosqichli himoya majburiy
    require_2fa_staff = models.BooleanField(_("Xodimlarga 2FA majburiy"), default=False)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Tizim sozlamalari")
        verbose_name_plural = _("Tizim sozlamalari")

    def __str__(self):
        return "Tizim sozlamalari"

    # Jarayon keshi QISQA muddatli: prod'da bir nechta gunicorn worker + Celery bor —
    # admin bittasida o'zgartirsa, qolganlari ham ko'pi bilan shu vaqtda yangisini oladi
    # (ilgari qayta ishga tushirilmaguncha eski og'irlik/chegaralar bilan ishlardi).
    CACHE_SECONDS = 20

    def save(self, *args, **kwargs):
        self.pk = 1  # yagona yozuv
        super().save(*args, **kwargs)
        SystemSettings._cache = self
        SystemSettings._cache_at = time.monotonic()

    @classmethod
    def get_solo(cls) -> SystemSettings:
        cached = getattr(cls, "_cache", None)
        at = getattr(cls, "_cache_at", 0.0)
        if cached is not None and time.monotonic() - at < cls.CACHE_SECONDS:
            return cached
        obj, _created = cls.objects.get_or_create(pk=1, defaults=cls._defaults())
        cls._cache = obj
        cls._cache_at = time.monotonic()
        return obj

    # Standart chegirma pog'onalari (bozorda savdolashish uchun tayyor tugmalar)
    DEFAULT_DISCOUNT_TIERS = [
        [100_000, [5_000, 10_000, 20_000]],
        [300_000, [10_000, 20_000, 30_000]],
        [None, [50_000, 100_000, 200_000]],
    ]

    # O'zbekcha savdolashish foizlari (chek summasidan): kichik, mantiqli
    DEFAULT_DISCOUNT_PERCENTS = [5, 10, 15]

    @staticmethod
    def _defaults():
        return {
            "discount_tiers": SystemSettings.DEFAULT_DISCOUNT_TIERS,
            "discount_percents": SystemSettings.DEFAULT_DISCOUNT_PERCENTS,
        }


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


class Notification(TimeStampedModel):
    """Foydalanuvchi bildirishnomasi: nasiya muddati, e'tiroz javobi, signal."""

    class Kind(models.TextChoices):
        DEBT_DUE = "debt_due", _("Nasiya muddati")
        APPEAL_REPLY = "appeal_reply", _("E'tiroz javobi")
        ALERT = "alert", _("Signal")
        INFO = "info", _("Ma'lumot")

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.INFO)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=300, blank=True)
    url = models.CharField(max_length=200, blank=True)
    key = models.CharField(max_length=120, blank=True)  # takrorlanmaslik uchun
    is_read = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("Bildirishnoma")
        verbose_name_plural = _("Bildirishnomalar")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "is_read", "-created_at"])]

    def __str__(self):
        return f"{self.user} — {self.title}"


def notify(user, kind, title, *, body="", url="", key=""):
    """Bildirishnoma yaratadi. `key` berilsa — takrorlamaydi (idempotent)."""
    if user is None:
        return None
    if key:
        obj, _created = Notification.objects.get_or_create(
            user=user, key=key, defaults={"kind": kind, "title": title, "body": body, "url": url}
        )
        return obj
    return Notification.objects.create(user=user, kind=kind, title=title, body=body, url=url)


class BackupLog(TimeStampedModel):
    """Zaxira nusxa jurnali: qachon, qancha, butunmi, bozordan tashqariga yuborildimi."""

    ok = models.BooleanField(_("Muvaffaqiyatli"), default=False)
    offsite_ok = models.BooleanField(_("Tashqariga yuborildi"), default=False)
    files = models.JSONField(default=list)  # [{"name", "size", "sha256"}]
    total_bytes = models.BigIntegerField(default=0)
    message = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Zaxira nusxa")
        verbose_name_plural = _("Zaxira nusxalar")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {'OK' if self.ok else 'XATO'}"


class SmsMessage(TimeStampedModel):
    """Yuborilgan SMS jurnali. `key` — idempotentlik: bir eslatma ikki marta ketmaydi."""

    class Status(models.TextChoices):
        SENT = "sent", _("Yuborildi")
        FAILED = "failed", _("Xato")
        INVALID = "invalid", _("Raqam noto'g'ri")

    key = models.CharField(max_length=120, unique=True)
    phone = models.CharField(max_length=20)
    text = models.CharField(max_length=480)
    status = models.CharField(max_length=10, choices=Status.choices)
    provider = models.CharField(max_length=20, blank=True)
    provider_id = models.CharField(max_length=80, blank=True)
    error = models.CharField(max_length=300, blank=True)
    shop = models.ForeignKey("shops.Shop", null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("SMS")
        verbose_name_plural = _("SMS jurnali")

    def __str__(self):
        return f"{self.phone} {self.get_status_display()}"
