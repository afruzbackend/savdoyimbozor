from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("markets/", include("markets.urls")),
    path("cameras/", include("cameras.urls")),
    path("inspections/", include("inspections.urls")),
    path("reports/", include("reports.urls")),
    path("analytics/", include("analytics.urls")),
    # Kamera/AI worker → backend hodisa yuborish API'si
    path("api/", include("events.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
