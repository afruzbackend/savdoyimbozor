from django.db import models
from django.utils.translation import gettext_lazy as _


class Declaration(models.Model):
    """Do'kon deklaratsiya qilgan savdo (soliqqa ko'rsatilgan).

    Pilotda soliqchilar Excel yuklaydi; keyin rasmiy API'ga ulanadi.
    """
    shop = models.ForeignKey("markets.Shop", on_delete=models.CASCADE, related_name="declarations")
    year = models.PositiveIntegerField(_("Yil"))
    month = models.PositiveIntegerField(_("Oy"))  # 1..12
    declared_amount = models.DecimalField(_("Deklaratsiya (so'm)"), max_digits=14, decimal_places=2)
    source = models.CharField(_("Manba"), max_length=50, default="excel")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Deklaratsiya")
        verbose_name_plural = _("Deklaratsiyalar")
        unique_together = ("shop", "year", "month")

    def __str__(self):
        return f"{self.shop.name} {self.year}-{self.month:02d}: {self.declared_amount}"


class DailyShopStat(models.Model):
    """Kunlik yig'ma statistika (dashboard tez ishlashi uchun oldindan hisoblanadi)."""
    shop = models.ForeignKey("markets.Shop", on_delete=models.CASCADE, related_name="daily_stats")
    date = models.DateField(_("Sana"), db_index=True)
    visitor_count = models.PositiveIntegerField(_("Xaridorlar"), default=0)     # AI'dan
    recorded_sales = models.DecimalField(_("Kiritilgan savdo"), max_digits=14, decimal_places=2, default=0)  # sotuvchidan
    estimated_sales = models.DecimalField(_("AI taxmini"), max_digits=14, decimal_places=2, default=0)       # xaridor*o'rtacha chek
    camera_uptime_pct = models.DecimalField(_("Kamera ishlashi (%)"), max_digits=5, decimal_places=2, default=0)

    class Meta:
        verbose_name = _("Kunlik statistika")
        verbose_name_plural = _("Kunlik statistikalar")
        unique_together = ("shop", "date")
        ordering = ["-date"]


class Alert(models.Model):
    """Shubhali holat signali. Inspektorga yo'naltiriladi."""
    class Level(models.TextChoices):
        GREEN = "green", _("Yashil")
        YELLOW = "yellow", _("Sariq")
        RED = "red", _("Qizil")

    class Status(models.TextChoices):
        NEW = "new", _("Yangi")
        ASSIGNED = "assigned", _("Biriktirilgan")
        RESOLVED = "resolved", _("Yakunlangan")
        DISMISSED = "dismissed", _("E'tiborsiz")

    shop = models.ForeignKey("markets.Shop", on_delete=models.CASCADE, related_name="alerts")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    date = models.DateField(_("Tegishli sana"))
    level = models.CharField(_("Daraja"), max_length=10, choices=Level.choices)
    message = models.CharField(_("Sabab"), max_length=300)
    status = models.CharField(_("Holat"), max_length=12, choices=Status.choices, default=Status.NEW)
    assigned_to = models.ForeignKey("accounts.User", null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="alerts")
    telegram_sent = models.BooleanField(_("Telegram yuborildi"), default=False)

    class Meta:
        verbose_name = _("Ogohlantirish")
        verbose_name_plural = _("Ogohlantirishlar")
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_level_display()}] {self.shop.name}: {self.message}"
