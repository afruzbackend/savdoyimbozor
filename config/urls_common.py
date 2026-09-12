"""Barcha interfeyslar uchun umumiy yo'llar: auth, til/tema, API."""

from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.static import serve

common_patterns = [
    path("", include("apps.accounts.urls")),  # login/logout/profile/parol
    path("prefs/", include("apps.core.urls")),  # tema/til almashtirish, styleguide
    path("api/", include("apps.api.urls")),  # DRF
]

if settings.DEBUG:
    common_patterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    common_patterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
else:
    # DEBUG=False (lokal demo): statikni WhiteNoise beradi; media (fotolar)ni bu yerda uzatamiz.
    # Prod'da nginx /media/ ni ushlaydi — bu faqat zaxira.
    common_patterns += [
        re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
