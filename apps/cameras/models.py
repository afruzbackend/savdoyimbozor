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
        PRODUCT = "product", _("Mahsulot kuzatuvi")
        PACKAGED = "packaged", _("Paketga joylash")
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


class ProductObservation(TimeStampedModel):
    """Kamera ko'rgan mahsulot yoki paketlash jarayoni.

    Bu hodisa fiskal chek qatoriga avtomatik tenglashtirilmaydi: model noaniq
    chiqishi mumkin. Moslik faqat keyingi tekshiruv oqimida tasdiqlanadi.
    """

    class Kind(models.TextChoices):
        PRODUCT = "product", _("Mahsulot kuzatuvi")
        PACKAGED = "packaged", _("Paketga joylandi")

    class ReviewState(models.TextChoices):
        PENDING = "pending", _("Tekshiruv kerak")
        CONFIRMED = "confirmed", _("Tasdiqlangan")
        REJECTED = "rejected", _("Rad etilgan")

    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name="product_observations")
    shop = models.ForeignKey("shops.Shop", on_delete=models.PROTECT, related_name="product_observations")
    event_id = models.CharField(_("Worker hodisa ID"), max_length=64, unique=True)
    kind = models.CharField(_("Kuzatuv turi"), max_length=12, choices=Kind.choices)
    product_label = models.CharField(_("Model aniqlagan nom"), max_length=300)
    product_code = models.CharField(_("Model aniqlagan kod"), max_length=128, blank=True)
    quantity = models.DecimalField(_("Miqdor"), max_digits=12, decimal_places=3)
    confidence = models.DecimalField(_("Ishonch"), max_digits=4, decimal_places=3)
    started_at = models.DateTimeField(_("Boshlanish vaqti"), db_index=True)
    ended_at = models.DateTimeField(_("Tugash vaqti"), db_index=True)
    review_state = models.CharField(
        _("Tekshiruv holati"), max_length=12, choices=ReviewState.choices,
        default=ReviewState.PENDING,
    )
    evidence = models.JSONField(_("Dalil"), default=dict, blank=True)

    class Meta:
        verbose_name = _("Mahsulot/paket kuzatuvi")
        verbose_name_plural = _("Mahsulot/paket kuzatuvlari")
        ordering = ["-ended_at", "-id"]
        indexes = [
            models.Index(fields=["shop", "ended_at"]),
            models.Index(fields=["camera", "ended_at"]),
            models.Index(fields=["review_state", "ended_at"]),
        ]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.product_label} × {self.quantity:g}"
