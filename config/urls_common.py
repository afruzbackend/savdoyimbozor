"""Barcha interfeyslar uchun umumiy yo'llar: auth, til/tema, API."""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path

from apps.core.media import protected_media
from apps.core.views import service_worker

common_patterns = [
    path("", include("apps.accounts.urls")),  # login/logout/profile/parol
    path("prefs/", include("apps.core.urls")),  # tema/til almashtirish, styleguide
    path("api/", include("apps.api.urls")),  # DRF
    path("sw.js", service_worker, name="service_worker"),  # PWA/offline — ildiz doirasi
]

# Media (dalil fotolari) — FAQAT login + do'kon ruxsati bilan (apps.core.media)
common_patterns += [re_path(r"^media/(?P<path>.+)$", protected_media, name="protected_media")]

if settings.DEBUG:
    common_patterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
