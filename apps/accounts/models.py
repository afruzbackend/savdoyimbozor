"""Foydalanuvchi va rollar. Login = FAQAT raqam (superadmin ochadi: STIR+do'kon / inspektor 70xxxx)."""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    SUPERADMIN = "superadmin", _("Super admin")
    INSPECTOR = "inspector", _("Tekshiruvchi")
    SELLER = "seller", _("Sotuvchi")
    # Faqat KO'RADI (prokuratura/kuzatuvchi): hech narsani o'zgartira olmaydi, har ko'rishi auditda
    PROSECUTOR = "prosecutor", _("Prokuror (kuzatuvchi)")


class Language(models.TextChoices):
    UZ = "uz", _("O'zbekcha")
    UZ_CYRL = "uz-cyrl", _("Ўзбекча")
    RU = "ru", _("Русский")


class User(AbstractUser):
    """Rollar bilan kengaytirilgan foydalanuvchi.

    - Sotuvchi `shop`ga biriktiriladi (`is_shop_owner` — egasi xodim qo'sha oladi).
    - Tekshiruvchi `assigned_markets`ni ko'radi.
    - Ruxsat markazi: `visible_shops()`.
    """

    role = models.CharField(_("Rol"), max_length=16, choices=Role.choices, default=Role.SELLER)
    phone = models.CharField(_("Telefon"), max_length=20, blank=True)
    language = models.CharField(
        _("Til"), max_length=10, choices=Language.choices, default=Language.UZ
    )
    telegram_id = models.CharField(_("Telegram ID"), max_length=40, blank=True)
    notify_telegram = models.BooleanField(_("Telegram bildirishnoma"), default=True)

    # Sotuvchi uchun
    shop = models.ForeignKey(
        "shops.Shop",
        verbose_name=_("Do'kon"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="staff",
    )
    is_shop_owner = models.BooleanField(_("Do'kon egasi"), default=False)

    # Tekshiruvchi uchun
    assigned_markets = models.ManyToManyField(
        "geo.Market",
        verbose_name=_("Biriktirilgan bozorlar"),
        blank=True,
        related_name="inspectors",
    )

    # Xavfsizlik
    must_change_password = models.BooleanField(_("Parolni almashtirsin"), default=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    # Admin ko'rishi uchun joriy parol (ochiq matn). Login/parolni admin beradi,
    # o'zgargan bo'lsa ham admin ko'rib turishi kerak (davlat kredensial modeli).
    # ESLATMA: bu odatdagi xavfsizlik amaliyoti emas; faqat admin panelida ko'rinadi.
    visible_password = models.CharField(_("Joriy parol"), max_length=128, blank=True, default="")
    # Ikki bosqichli himoya (TOTP) — apps/accounts/totp.py
    totp_secret = models.CharField(max_length=64, blank=True, default="")
    totp_enabled = models.BooleanField(_("Ikki bosqichli himoya"), default=False)
    totp_last_step = models.BigIntegerField(default=0)  # bir kod ikki marta ishlatilmasin
    backup_codes = models.JSONField(default=list, blank=True)  # bir martalik, xeshlangan

    @property
    def is_staff_role(self):
        """Ikki bosqichli himoya majburiy bo'lishi mumkin bo'lgan rollar (sotuvchidan tashqari)."""
        return self.role in (Role.SUPERADMIN, Role.INSPECTOR, Role.PROSECUTOR) or self.is_superuser

    class Meta:
        verbose_name = _("Foydalanuvchi")
        verbose_name_plural = _("Foydalanuvchilar")

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    # --- Rol yordamchilar ---
    @property
    def is_superadmin(self):
        return self.role == Role.SUPERADMIN or self.is_superuser

    @property
    def is_inspector(self):
        return self.role == Role.INSPECTOR

    @property
    def is_prosecutor(self):
        return self.role == Role.PROSECUTOR

    @property
    def is_monitor(self):
        """Nazorat interfeysini ko'radiganlar: tekshiruvchi va prokuror (faqat ko'rish)."""
        return self.role in (Role.INSPECTOR, Role.PROSECUTOR)

    @property
    def is_seller(self):
        return self.role == Role.SELLER

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def visible_shops(self):
        """Foydalanuvchi ko'ra oladigan do'konlar QuerySet'i (markazlashgan ruxsat)."""
        from apps.shops.models import Shop

        if self.is_superadmin:
            return Shop.objects.all()
        if self.is_inspector:
            return Shop.objects.filter(market__in=self.assigned_markets.all())
        if self.is_prosecutor:
            # Bozor biriktirilgan bo'lsa — faqat o'shalar, aks holda butun respublika
            if self.assigned_markets.exists():
                return Shop.objects.filter(market__in=self.assigned_markets.all())
            return Shop.objects.all()
        if self.is_seller and self.shop_id:
            return Shop.objects.filter(pk=self.shop_id)
        return Shop.objects.none()

    def set_password_visible(self, raw_password):
        """Parolni o'rnatadi va admin ko'rishi uchun ochiq matnini ham saqlaydi."""
        self.set_password(raw_password)
        self.visible_password = raw_password or ""

    def register_failed_login(self, max_attempts: int, lock_minutes: int):
        self.failed_attempts += 1
        if self.failed_attempts >= max_attempts:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=lock_minutes)
            self.failed_attempts = 0
        self.save(update_fields=["failed_attempts", "locked_until"])

    def reset_lockout(self):
        if self.failed_attempts or self.locked_until:
            self.failed_attempts = 0
            self.locked_until = None
            self.save(update_fields=["failed_attempts", "locked_until"])
