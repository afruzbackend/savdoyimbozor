"""sotuvchi.* — sotuvchi interfeysi."""

from django.urls import include, path

from .urls_common import common_patterns

urlpatterns = [
    path("", include("apps.sales.seller_urls")),
] + common_patterns
