from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    ADMIN = "admin", _("Administrator")
    MANAGER = "manager", _("Rahbar")          # hamma bozorlarni ko'radi
    INSPECTOR = "inspector", _("Inspektor")    # faqat o'z bozori
    SELLER = "seller", _("Sotuvchi")           # faqat o'z do'koni


class Language(models.TextChoices):
    UZ = "uz", _("O'zbekcha (lotin)")
    UZ_CYRL = "uz-cyrl", _("Ўзбекча (кирилл)")
    RU = "ru", _("Русский")


class User(AbstractUser):
    """Rollar bilan kengaytirilgan foydalanuvchi.

    - Inspektor `assigned_market` orqali bitta bozorga biriktiriladi.
    - Sotuvchi `assigned_shop` orqali bitta do'konga biriktiriladi.
    - Rahbar/admin hammasini ko'radi.
    """

    role = models.CharField(_("Rol"), max_length=20, choices=Role.choices, default=Role.SELLER)
    phone = models.CharField(_("Telefon"), max_length=20, blank=True)
    language = models.CharField(_("Til"), max_length=10, choices=Language.choices, default=Language.UZ)
    telegram_chat_id = models.CharField(_("Telegram chat ID"), max_length=40, blank=True)

    assigned_market = models.ForeignKey(
        "markets.Market", verbose_name=_("Biriktirilgan bozor"),
        null=True, blank=True, on_delete=models.SET_NULL, related_name="inspectors",
    )
    assigned_shop = models.ForeignKey(
        "markets.Shop", verbose_name=_("Biriktirilgan do'kon"),
        null=True, blank=True, on_delete=models.SET_NULL, related_name="sellers",
    )

    class Meta:
        verbose_name = _("Foydalanuvchi")
        verbose_name_plural = _("Foydalanuvchilar")

    # --- Qulaylik uchun rol tekshiruvlari ---
    @property
    def is_manager(self):
        return self.role == Role.MANAGER or self.is_superuser

    @property
    def is_inspector(self):
        return self.role == Role.INSPECTOR

    @property
    def is_seller(self):
        return self.role == Role.SELLER

    def visible_markets(self):
        """Ushbu foydalanuvchi ko'ra oladigan bozorlar QuerySet'i."""
        from markets.models import Market
        if self.is_manager:
            return Market.objects.all()
        if self.is_inspector and self.assigned_market_id:
            return Market.objects.filter(pk=self.assigned_market_id)
        if self.is_seller and self.assigned_shop_id:
            return Market.objects.filter(shops=self.assigned_shop).distinct()
        return Market.objects.none()

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
