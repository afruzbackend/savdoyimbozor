"""nazorat.* — tekshiruvchi interfeysi (standart)."""

from django.urls import include, path

from .urls_common import common_patterns

urlpatterns = [
    path("", include("apps.analytics.inspector_urls")),
] + common_patterns
