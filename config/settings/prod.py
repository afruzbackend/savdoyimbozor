"""Production sozlamalari."""

from .base import *  # noqa

DEBUG = False

# HTTPS/xavfsizlik. HTTPS bo'lmagan (lokal Docker demo, http://localhost) uchun
# env orqali o'chirib qo'yish mumkin; haqiqiy prod'da (https) hammasi yoqilgan qoladi.
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=True)  # noqa: F405
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=True)  # noqa: F405
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
X_FRAME_OPTIONS = "DENY"

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"
