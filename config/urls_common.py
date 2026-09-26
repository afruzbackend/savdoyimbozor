"""Barcha interfeyslar uchun umumiy yo'llar: auth, til/tema, API."""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path

from apps.core import views as core_views
from apps.core.media import protected_media
from apps.core.views import service_worker
from apps.sales import public_views as receipt

common_patterns = [
    path("", include("apps.accounts.urls")),  # login/logout/profile/parol
    path("prefs/", include("apps.core.urls")),  # tema/til almashtirish, styleguide
    path("api/", include("apps.api.urls")),  # DRF
    path("sw.js", service_worker, name="service_worker"),  # PWA/offline — ildiz doirasi
    path("healthz/", core_views.healthz, name="healthz_root"),  # monitoring (Uptime Kuma, Docker)
    # Xaridorga QR chek — ochiq (login shart emas), kod yagona kalit
    path("chek/<str:code>/", receipt.receipt, name="receipt"),
    path("chek/<str:code>/qr.svg", receipt.receipt_qr, name="receipt_qr"),
    path("chek/<str:code>/xabar/", receipt.receipt_report, name="receipt_report"),
]

# Media (dalil fotolari) — FAQAT login + do'kon ruxsati bilan (apps.core.media)
common_patterns += [re_path(r"^media/(?P<path>.+)$", protected_media, name="protected_media")]

if settings.DEBUG:
    common_patterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
