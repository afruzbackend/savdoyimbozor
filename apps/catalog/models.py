"""Katalog: do'kon toifasi, umumiy mahsulot toifasi (bozor narxi uchun), mahsulot."""
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Unit(models.TextChoices):
    PIECE = "dona", _("dona")
    KG = "kg", _("kg")
    LITER = "litr", _("litr")
    METER = "metr", _("metr")
    PACK = "quti", _("quti")


class ShopCategory(TimeStampedModel):
    """Do'kon yo'nalishi: meva-sabzavot, kiyim, oziq-ovqat..."""
    name = models.CharField(_("Do'kon toifasi"), max_length=120, unique=True)

    class Meta:
        verbose_name = _("Do'kon toifasi")
        verbose_name_plural = _("Do'kon toifalari")
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductCategory(TimeStampedModel):
    """Umumiy mahsulot turi ("Pomidor", "Kurtka") — bozor narxini solishtirish uchun.

    Do'konga bog'liq emas; bir necha do'kondagi "Pomidor" bitta toifaga tegishli.
    """
    name = models.CharField(_("Mahsulot toifasi"), max_length=120, unique=True)
    shop_category = models.ForeignKey(ShopCategory, verbose_name=_("Do'kon toifasi"),
                                      null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name="product_categories")
    default_unit = models.CharField(_("Birlik"), max_length=10, choices=Unit.choices,
                                    default=Unit.PIECE)
    waste_norm_percent = models.DecimalField(_("Chirish me'yori (%)"), max_digits=5,
                                             decimal_places=2, default=5)

    class Meta:
        verbose_name = _("Mahsulot toifasi")
        verbose_name_plural = _("Mahsulot toifalari")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(TimeStampedModel):
    """Do'konga tegishli mahsulot."""
    shop = models.ForeignKey("shops.Shop", verbose_name=_("Do'kon"),
                             on_delete=models.CASCADE, related_name="products")
    category = models.ForeignKey(ProductCategory, verbose_name=_("Toifa"),
                                 null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="products")
    name = models.CharField(_("Nomi"), max_length=200)
    unit = models.CharField(_("Birlik"), max_length=10, choices=Unit.choices, default=Unit.PIECE)
    barcode = models.CharField(_("Barkod"), max_length=64, blank=True, db_index=True)
    buy_price = models.BigIntegerField(_("Tannarx (so'm)"), default=0)      # pul = butun son
    sell_price = models.BigIntegerField(_("Sotish narxi (so'm)"), default=0)
    pack_coeff = models.DecimalField(_("Qadoq koeffitsienti"), max_digits=10, decimal_places=3,
                                     default=1, help_text=_("1 qop = necha birlik"))
    low_stock_threshold = models.DecimalField(_("Kam qoldiq chegarasi"), max_digits=12,
                                              decimal_places=3, default=0)
    stock = models.DecimalField(_("Joriy qoldiq"), max_digits=12, decimal_places=3, default=0)
    is_active = models.BooleanField(_("Faol"), default=True)

    class Meta:
        verbose_name = _("Mahsulot")
        verbose_name_plural = _("Mahsulotlar")
        ordering = ["name"]
        indexes = [models.Index(fields=["shop", "is_active"])]

    def __str__(self):
        return self.name

    @property
    def is_low_stock(self):
        return self.low_stock_threshold and self.stock <= self.low_stock_threshold
