import secrets

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def make_token():
    return secrets.token_hex(24)


class Camera(models.Model):
    """Bozordagi kamera.

    Hozircha: ma'lumot saqlaydi, holatini ko'rsatadi.
    Keyinchalik: AI worker shu kamera oqimini o'qib, `events` API'ga hodisa yuboradi.
    Autentifikatsiya `ingest_token` orqali (POST /api/events/ Header: X-Camera-Token).
    """

    market = models.ForeignKey("markets.Market", verbose_name=_("Bozor"),
                               on_delete=models.CASCADE, related_name="cameras")
    # Bitta kamera bir yoki bir nechta do'konni qamrashi mumkin.
    shops = models.ManyToManyField("markets.Shop", verbose_name=_("Qamrovdagi do'konlar"),
                                   blank=True, related_name="cameras")
    name = models.CharField(_("Nomi/joyi"), max_length=200)
    # RTSP manzil — AI worker shundan video oladi. UI'da ko'rsatilmaydi.
    rtsp_url = models.CharField(_("RTSP manzil"), max_length=500, blank=True)
    ingest_token = models.CharField(_("Ingest token"), max_length=64,
                                    default=make_token, unique=True, editable=False)
    is_active = models.BooleanField(_("Faol"), default=True)
    # AI worker oxirgi marta hodisa yuborgan vaqt — online/offline shundan aniqlanadi.
    last_heartbeat = models.DateTimeField(_("Oxirgi signal"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    OFFLINE_AFTER_SECONDS = 120

    class Meta:
        verbose_name = _("Kamera")
        verbose_name_plural = _("Kameralar")
        ordering = ["market", "name"]

    def __str__(self):
        return f"{self.name} — {self.market.name}"

    @property
    def is_online(self):
        if not self.last_heartbeat:
            return False
        delta = (timezone.now() - self.last_heartbeat).total_seconds()
        return delta <= self.OFFLINE_AFTER_SECONDS

    def rotate_token(self):
        self.ingest_token = make_token()
        self.save(update_fields=["ingest_token"])
        return self.ingest_token
