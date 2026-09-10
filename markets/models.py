from django.db import models
from django.utils.translation import gettext_lazy as _


class Market(models.Model):
    """Bozor."""
    name = models.CharField(_("Nomi"), max_length=200)
    region = models.CharField(_("Viloyat/tuman"), max_length=200, blank=True)
    address = models.CharField(_("Manzil"), max_length=300, blank=True)
    latitude = models.FloatField(_("Kenglik"), null=True, blank=True)
    longitude = models.FloatField(_("Uzunlik"), null=True, blank=True)
    is_active = models.BooleanField(_("Faol"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Bozor")
        verbose_name_plural = _("Bozorlar")
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductCategory(models.Model):
    """Mahsulot toifasi — kalibrlash va chirish me'yori shu yerda saqlanadi."""
    name = models.CharField(_("Nomi"), max_length=120, unique=True)
    # Bitta xaridor o'rtacha shuncha so'mlik oladi (kalibrlashda yangilanadi).
    avg_ticket = models.DecimalField(
        _("O'rtacha chek (so'm)"), max_digits=12, decimal_places=2, default=0,
        help_text=_("Halol do'konlar bo'yicha kalibrlangan o'rtacha savdo"))
    # Ruxsat etilgan chirish/yo'qotish ulushi (%). Undan oshsa signal.
    waste_norm_percent = models.DecimalField(
        _("Chirish me'yori (%)"), max_digits=5, decimal_places=2, default=5)

    class Meta:
        verbose_name = _("Mahsulot toifasi")
        verbose_name_plural = _("Mahsulot toifalari")

    def __str__(self):
        return self.name


class Shop(models.Model):
    """Do'kon / rasta."""
    market = models.ForeignKey(Market, verbose_name=_("Bozor"),
                               on_delete=models.CASCADE, related_name="shops")
    name = models.CharField(_("Do'kon nomi"), max_length=200)
    stir = models.CharField(_("STIR (soliq raqami)"), max_length=15, blank=True, db_index=True)
    owner_name = models.CharField(_("Egasi (F.I.O.)"), max_length=200, blank=True)
    owner_phone = models.CharField(_("Egasi telefoni"), max_length=20, blank=True)
    category = models.ForeignKey(ProductCategory, verbose_name=_("Toifa"),
                                 null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="shops")
    # Rastadagi joylashuvi (qatorli bozorlarda solishtirish uchun)
    row_label = models.CharField(_("Qator/joy"), max_length=60, blank=True)
    is_active = models.BooleanField(_("Faol"), default=True)
    # Dam olish kunlari (0=Dushanba ... 6=Yakshanba) — bo'sh kunda "savdo nol" signali berilmaydi
    closed_weekdays = models.CharField(
        _("Yopiq kunlar"), max_length=20, blank=True,
        help_text=_("Vergul bilan: 0=Du ... 6=Ya. Masalan '6' = yakshanba yopiq"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Do'kon")
        verbose_name_plural = _("Do'konlar")
        ordering = ["market", "name"]

    def __str__(self):
        return f"{self.name} — {self.market.name}"

    def closed_weekday_list(self):
        return [int(x) for x in self.closed_weekdays.split(",") if x.strip().isdigit()]

    def similar_shops(self):
        """O'xshash do'konlar: bir bozor + bir toifa. Yashiruvchini topish uchun asos."""
        qs = Shop.objects.filter(market=self.market, is_active=True).exclude(pk=self.pk)
        if self.category_id:
            qs = qs.filter(category=self.category)
        return qs
