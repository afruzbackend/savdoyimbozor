"""Production sozlamalari."""

from .base import *  # noqa

DEBUG = False

# Hammaga ma'lum / qisqa SECRET_KEY bilan ishga tushmaydi: sessiya, parol tiklash, imzolangan
# qiymatlar va 2FA zaxira kodlari shu kalitga tayanadi.
_WEAK_KEYS = {"", "dev-insecure-change-me", "change-me-in-production"}
if SECRET_KEY in _WEAK_KEYS or len(SECRET_KEY) < 40:  # noqa: F405
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "SECRET_KEY production uchun o'rnatilmagan yoki kuchsiz (kamida 40 belgi). .env ga yangi kalit "
        "yozing: python -c \"import secrets; print(secrets.token_urlsafe(50))\""
    )

# HTTPS/xavfsizlik. HTTPS bo'lmagan (lokal Docker demo, http://localhost) uchun
# env orqali o'chirib qo'yish mumkin; haqiqiy prod'da (https) hammasi yoqilgan qoladi.
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)  # noqa: F405
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)  # noqa: F405
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
# Brauzerlar preload ro'yxati — domen uchun qaytarib bo'lmaydigan qaror, shuning uchun ixtiyoriy
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)  # noqa: F405
SILENCED_SYSTEM_CHECKS = [] if SECURE_HSTS_PRELOAD else ["security.W021"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Konteyner ichidagi healthcheck http orqali — https'ga yo'naltirilmasin
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
X_FRAME_OPTIONS = "DENY"

# API faqat JSON: brauzerda "Browsable API" sahifasi (endpointlar, maydonlar ro'yxati) ochilmasin
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"]}  # noqa: F405

# Django 5.1 da STATICFILES_STORAGE olib tashlangan (e'tiborsiz qolardi) — STORAGES orqali.
# WhiteNoise: fayl nomida xesh (abadiy kesh) + oldindan gzip/brotli siqilgan nusxalar.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "apps.core.storage.StaticStorage"},
}
