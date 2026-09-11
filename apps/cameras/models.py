"""Kamera va hodisalar. Kontrakt tayyor — eventlar hozircha soxta (simulate_camera).

Kamera qo'shilganda o'zgarmaydigan kontrakt:
  GET  /api/cameras/config/   (token bilan) — worker konfiguratsiyani oladi
  POST /api/events/           (token bilan) — worker hodisa yuboradi
  POST /api/cameras/heartbeat/
"""

import secrets

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


def make_token():
    return secrets.token_hex(24)


class Camera(TimeStampedModel):
    class Kind(models.TextChoices):
        COUNTER = "counter", _("Peshtaxta (xaridor sanash)")
        OVERVIEW = "overview", _("Umumiy ko'rinish")
        GATE = "gate", _("Darvoza (ANPR/kirim)")

    class Status(models.TextChoices):
        ONLINE = "online", _("Online")
        OFFLINE = "offline", _("Offline")
        TAMPERED = "tampered", _("Buzilgan")

    shop = models.ForeignKey(
        "shops.Shop",
        verbose_name=_("Do'kon"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cameras",
    )
    market = models.ForeignKey(
        "geo.Market", verbose_name=_("Bozor"), on_delete=models.CASCADE, related_name="cameras"
    )
    name = models.CharField(_("Nomi/joyi"), max_length=200)
    kind = models.CharField(_("Turi"), max_length=12, choices=Kind.choices, default=Kind.COUNTER)
    rtsp_main = models.CharField(_("RTSP asosiy"), max_length=500, blank=True)
    rtsp_sub = models.CharField(_("RTSP substream"), max_length=500, blank=True)
    # Zonalar (snapshotda chiziladigan poligon nuqtalari, normallashtirilgan 0..1)
    counter_zone = models.JSONField(_("Peshtaxta zonasi"), default=list, blank=True)
    staff_zone = models.JSONField(_("Sotuvchi zonasi"), default=list, blank=True)  # sanalmaydi
    token = models.CharField(
        _("Token"), max_length=64, default=make_token, unique=True, editable=False
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OFFLINE)
    last_seen = models.DateTimeField(_("Oxirgi signal"), null=True, blank=True)
    is_active = models.BooleanField(_("Faol"), default=True)

    OFFLINE_AFTER_SECONDS = 120

    class Meta:
        verbose_name = _("Kamera")
        verbose_name_plural = _("Kameralar")
        ordering = ["market", "name"]

    def __str__(self):
        return f"{self.name} — {self.market.name}"

    @property
    def is_online(self):
        if not self.last_seen:
            return False
        return (timezone.now() - self.last_seen).total_seconds() <= self.OFFLINE_AFTER_SECONDS


class CameraEvent(models.Model):
    """AI worker yuboradigan hodisa. Milliardlab bo'lishi mumkin — indeks muhim."""

    class Type(models.TextChoices):
        VISIT = "visit", _("Xaridor tashrifi")
        TAMPER = "tamper", _("Kamera buzilishi")
        SALE = "sale", _("Sotuv kuzatuvi")
        GATE_IN = "gate_in", _("Kirim (darvoza)")
        HEARTBEAT = "heartbeat", _("Tiriklik")

    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name="events")
    shop = models.ForeignKey(
        "shops.Shop", null=True, blank=True, on_delete=models.SET_NULL, related_name="camera_events"
    )
    type = models.CharField(max_length=12, choices=Type.choices)
    count = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict, blank=True)
    clip = models.FileField(upload_to="clips/%Y/%m/", blank=True)
    ts = models.DateTimeField(_("Vaqt"), db_index=True)

    class Meta:
        verbose_name = _("Kamera hodisasi")
        verbose_name_plural = _("Kamera hodisalari")
        ordering = ["-ts"]
        indexes = [
            models.Index(fields=["shop", "ts"]),
            models.Index(fields=["camera", "ts"]),
            models.Index(fields=["type", "ts"]),
        ]

    def __str__(self):
        return f"{self.get_type_display()} — {self.camera_id} @ {self.ts:%Y-%m-%d %H:%M}"
