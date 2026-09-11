"""Foydalanuvchi va rollar. Login = STIR-SHOPNO (superadmin ochadi)."""
from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    SUPERADMIN = "superadmin", _("Super admin")
    INSPECTOR = "inspector", _("Tekshiruvchi")
    SELLER = "seller", _("Sotuvchi")


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
    language = models.CharField(_("Til"), max_length=10, choices=Language.choices, default=Language.UZ)
    telegram_id = models.CharField(_("Telegram ID"), max_length=40, blank=True)

    # Sotuvchi uchun
    shop = models.ForeignKey("shops.Shop", verbose_name=_("Do'kon"), null=True, blank=True,
                             on_delete=models.SET_NULL, related_name="staff")
    is_shop_owner = models.BooleanField(_("Do'kon egasi"), default=False)

    # Tekshiruvchi uchun
    assigned_markets = models.ManyToManyField("geo.Market", verbose_name=_("Biriktirilgan bozorlar"),
                                              blank=True, related_name="inspectors")

    # Xavfsizlik
    must_change_password = models.BooleanField(_("Parolni almashtirsin"), default=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

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
        if self.is_seller and self.shop_id:
            return Shop.objects.filter(pk=self.shop_id)
        return Shop.objects.none()

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
