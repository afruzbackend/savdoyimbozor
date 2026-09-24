"""Himoyalangan media: dalil fotolari faqat ruxsati borlarga + yuklashni tekshirish.

Ilgari /media/ hammaga ochiq edi (login ham so'ralmasdi): hisobdan chiqarish va tekshiruv
fotolari (dalil) yo'lini bilgan har kim ko'ra olardi. Yana: "foto" sifatida istalgan fayl
(masalan .html) yuklab, sayt domenidan ochish mumkin edi (stored XSS).
"""

from __future__ import annotations

import posixpath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.views.static import serve

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB — telefon fotosi uchun yetarli


def validate_image_upload(f) -> None:
    """Yuklangan fayl HAQIQIY rasm ekanini tekshiradi (kengaytma + hajm + Pillow)."""
    if f is None:
        raise ValidationError("Foto tanlanmagan.")
    ext = posixpath.splitext((f.name or "").lower())[1]
    if ext not in ALLOWED_IMAGE_EXT:
        raise ValidationError("Faqat rasm yuklang (JPG, PNG yoki WEBP).")
    if f.size and f.size > MAX_IMAGE_BYTES:
        raise ValidationError("Foto juda katta (10 MB dan oshmasin).")
    try:
        from PIL import Image

        pos = f.tell() if hasattr(f, "tell") else 0
        with Image.open(f) as img:
            img.verify()
        f.seek(pos)
    except Exception as e:  # noqa: BLE001 — har qanday buzuq/soxta fayl rad etiladi
        raise ValidationError("Fayl rasm emas yoki buzilgan.") from e


def _allowed(user, path: str) -> bool:
    """Foydalanuvchi shu media faylni ko'ra oladimi (do'kon ruxsati bo'yicha)."""
    if getattr(user, "is_superadmin", False):
        return True
    shops = user.visible_shops()
    top = path.split("/", 1)[0]
    if top == "writeoffs":
        from apps.sales.models import WriteOff

        return WriteOff.objects.filter(photo=path, shop__in=shops).exists()
    if top == "inspections" and user.is_inspector:
        from apps.analytics.models import Inspection

        return Inspection.objects.filter(photo=path, shop__in=shops).exists()
    if top == "clips" and user.is_inspector:
        from apps.cameras.models import CameraEvent

        return CameraEvent.objects.filter(clip=path, shop__in=shops).exists()
    return False


def protected_media(request, path):
    user = request.user
    if not user.is_authenticated:
        raise Http404
    path = posixpath.normpath(path).lstrip("/")
    if path.startswith("..") or not _allowed(user, path):
        raise Http404
    if getattr(settings, "MEDIA_X_ACCEL", False):
        # Prod: faylni nginx beradi (ichki location), Django faqat ruxsat tekshiradi
        resp = HttpResponse()
        resp["X-Accel-Redirect"] = f"/protected-media/{path}"
        resp["Content-Type"] = ""
    else:
        resp = serve(request, path, document_root=settings.MEDIA_ROOT)
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "private, max-age=3600"
    resp["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; sandbox"
    return resp
