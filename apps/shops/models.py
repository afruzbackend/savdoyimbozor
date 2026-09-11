"""Do'kon (rasta)."""
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Shop(TimeStampedModel):
    market = models.ForeignKey("geo.Market", verbose_name=_("Bozor"),
                               on_delete=models.PROTECT, related_name="shops")
    row = models.ForeignKey("geo.Row", verbose_name=_("Qator"), null=True, blank=True,
                            on_delete=models.SET_NULL, related_name="shops")
    category = models.ForeignKey("catalog.ShopCategory", verbose_name=_("Toifa"),
                                 null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="shops")
    number = models.CharField(_("Do'kon raqami"), max_length=20)
    stir = models.CharField(_("STIR"), max_length=15, blank=True, db_index=True)
    owner_name = models.CharField(_("Egasi"), max_length=200, blank=True)
    owner_phone = models.CharField(_("Egasi telefoni"), max_length=20, blank=True)
    # Xarita o'rni (bozor sxemasida)
    map_x = models.FloatField(null=True, blank=True)
    map_y = models.FloatField(null=True, blank=True)
    # Dam olish kunlari (0=Du ... 6=Ya), vergul bilan — yopiq kunda signal berilmaydi
    closed_weekdays = models.CharField(_("Yopiq kunlar"), max_length=20, blank=True)
    is_active = models.BooleanField(_("Faol"), default=True)

    class Meta:
        verbose_name = _("Do'kon")
        verbose_name_plural = _("Do'konlar")
        ordering = ["market", "number"]
        unique_together = ("market", "number")
        indexes = [models.Index(fields=["market", "is_active"]), models.Index(fields=["stir"])]

    def __str__(self):
        return f"№{self.number} — {self.market.name}"

    @property
    def display_name(self):
        base = self.owner_name or f"Do'kon №{self.number}"
        return base

    def closed_weekday_list(self):
        return [int(x) for x in self.closed_weekdays.split(",") if x.strip().isdigit()]

    def login_username(self):
        """Login formati: STIR-DO'KONRAQAMI."""
        return f"{self.stir}-{self.number}" if self.stir else f"shop-{self.number}"

    def similar_shops(self):
        """O'xshash do'konlar: bir bozor + bir toifa (nazorat solishtiruvi)."""
        qs = Shop.objects.filter(market=self.market, is_active=True).exclude(pk=self.pk)
        if self.category_id:
            qs = qs.filter(category=self.category)
        return qs
