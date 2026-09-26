"""Katalog: do'kon toifasi, umumiy mahsulot toifasi (bozor narxi uchun), mahsulot."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Unit(models.TextChoices):
    PIECE = "dona", _("dona")
    KG = "kg", _("kg")
    QOP = "qop", _("qop")
    BUNDLE = "bog'lam", _("bog'lam")
    LITER = "litr", _("litr")
    METER = "metr", _("metr")
    PACK = "quti", _("quti")


# Butun sanaladigan birliklar: 1,5 dona kurtka, 2,5 quti yoki bog'lam bo'lmaydi
# (kg/litr/metr/qop — bo'linadi: "yarim qop kartoshka" bozorda odatiy)
WHOLE_UNITS = frozenset({Unit.PIECE, Unit.PACK, Unit.BUNDLE})


def whole_qty_error(unit, qty, name="") -> str:
    """dona/quti/bog'lam miqdori butun son bo'lsin. Xato matni yoki "" (joyida)."""
    if unit in WHOLE_UNITS and qty is not None and qty != qty.to_integral_value():
        label = str(dict(Unit.choices).get(unit, unit))
        return f"«{name}» {label} bilan sanaladi — miqdor butun son bo'lsin (kiritildi: {qty:g})."
    return ""


class ShopCategory(TimeStampedModel):
    """Do'kon yo'nalishi: meva-sabzavot, kiyim, oziq-ovqat..."""

    name = models.CharField(_("Do'kon toifasi"), max_length=120, unique=True)
    # Kamera bahosi: peshtaxtaga kelganlarning qanchasi xarid qiladi. Turga qarab keskin farq
    # qiladi (non ~0,7, kiyim ~0,25) — bitta umumiy ulushda kiyim do'koni nohaq "yashiruvchi"
    # bo'lib chiqardi. Bo'sh — SystemSettings.buyer_ratio.
    buyer_ratio = models.DecimalField(
        _("Xaridorga aylanish ulushi"), max_digits=4, decimal_places=2, null=True, blank=True,
        help_text=_("Bo'sh — umumiy sozlama"),
    )

    class Meta:
        verbose_name = _("Do'kon toifasi")
        verbose_name_plural = _("Do'kon toifalari")
        ordering = ["name"]

    def __str__(self):
        return self.name


class VariantKind(models.TextChoices):
    """Mahsulot turiga mos variant: choyga kiyim razmeri emas — qadoq og'irligi (qoidalar: variants.py)."""

    NONE = "none", _("Variantsiz")
    CLOTHING = "clothing", _("Kiyim o'lchami (XS–3XL, 42–60)")
    SHOES = "shoes", _("Poyabzal o'lchami (35–46)")
    KIDS = "kids", _("Bolalar kiyimi (bo'y, sm)")
    HEADWEAR = "headwear", _("Bosh kiyim o'lchami (52–62)")
    SOCKS = "socks", _("Paypoq o'lchami (35-37...)")
    PACK_WEIGHT = "pack_weight", _("Qadoq og'irligi (g, kg)")
    PACK_VOLUME = "pack_volume", _("Qadoq hajmi (ml, L)")
    TYPE = "type", _("Turi / modeli")
    COLOR = "color", _("Faqat rang")


class ProductCategory(TimeStampedModel):
    """Umumiy mahsulot turi ("Pomidor", "Kurtka") — bozor narxini solishtirish uchun.

    Do'konga bog'liq emas; bir necha do'kondagi "Pomidor" bitta toifaga tegishli.
    """

    name = models.CharField(_("Mahsulot toifasi"), max_length=120, unique=True)
    shop_category = models.ForeignKey(
        ShopCategory,
        verbose_name=_("Do'kon toifasi"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_categories",
    )
    default_unit = models.CharField(
        _("Birlik"), max_length=10, choices=Unit.choices, default=Unit.PIECE
    )
    waste_norm_percent = models.DecimalField(
        _("Chirish me'yori (%)"), max_digits=5, decimal_places=2, default=5
    )
    variant_kind = models.CharField(
        _("Variant turi"), max_length=16, choices=VariantKind.choices, default=VariantKind.NONE
    )
    variant_options = models.CharField(
        _("Tayyor variantlar"), max_length=300, blank=True,
        help_text=_("Vergul bilan, masalan: 100 g, 250 g, 1 kg. Bo'sh — turning umumiy ro'yxati."),
    )

    class Meta:
        verbose_name = _("Mahsulot toifasi")
        verbose_name_plural = _("Mahsulot toifalari")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Yangi toifa turi aytilmasa — nomidan taxmin ("Krossovka" → poyabzal, "Choy" → qadoq).
        # Admin panelda aniq tanlagan bo'lsa (kind_explicit) — tegilmaydi.
        if (self._state.adding and not getattr(self, "kind_explicit", False)
                and self.variant_kind == VariantKind.NONE and not self.variant_options):
            from .variants import default_waste, guess

            shop_cat = self.shop_category.name if self.shop_category_id else ""
            self.variant_kind, self.variant_options = guess(self.name, shop_cat)
            if self.waste_norm_percent == 5:  # standart qiymat — turga moslanadi
                self.waste_norm_percent = default_waste(self.variant_kind, shop_cat)
        super().save(*args, **kwargs)


class Product(TimeStampedModel):
    """Do'konga tegishli mahsulot."""

    shop = models.ForeignKey(
        "shops.Shop", verbose_name=_("Do'kon"), on_delete=models.CASCADE, related_name="products"
    )
    category = models.ForeignKey(
        ProductCategory,
        verbose_name=_("Toifa"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="products",
    )
    name = models.CharField(_("Nomi"), max_length=200)
    # Variant (kiyim/poyabzal): bitta model — har o'lcham/rang alohida qoldiq va barkod bilan.
    # "Qaysi do'konda M o'lcham ko'ylak bor" degan savolga javob shu maydonlardan.
    base_name = models.CharField(_("Model"), max_length=200, blank=True, db_index=True)
    size = models.CharField(_("O'lcham"), max_length=20, blank=True, db_index=True)
    color = models.CharField(_("Rang"), max_length=40, blank=True)
    unit = models.CharField(_("Birlik"), max_length=10, choices=Unit.choices, default=Unit.PIECE)
    barcode = models.CharField(_("Barkod"), max_length=64, blank=True, db_index=True)
    buy_price = models.BigIntegerField(_("Tannarx (so'm)"), default=0)  # pul = butun son
    sell_price = models.BigIntegerField(_("Sotish narxi (so'm)"), default=0)
    pack_coeff = models.DecimalField(
        _("Qadoq koeffitsienti"),
        max_digits=10,
        decimal_places=3,
        default=1,
        help_text=_("1 qop = necha birlik"),
    )
    low_stock_threshold = models.DecimalField(
        _("Kam qoldiq chegarasi"), max_digits=12, decimal_places=3, default=0
    )
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
    def is_whole(self):
        """Butun son bilan sanaladimi (dona/quti/bog'lam) — forma maydoni qadami shunga qarab."""
        return self.unit in WHOLE_UNITS

    @property
    def is_low_stock(self):
        return self.low_stock_threshold and self.stock <= self.low_stock_threshold
