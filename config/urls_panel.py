"""panel.* — super admin interfeysi."""
from django.contrib import admin
from django.urls import include, path

from .urls_common import common_patterns

urlpatterns = [
    path("django-admin/", admin.site.urls),          # texnik admin
    path("", include("apps.core.panel_urls")),        # super admin interfeysi
] + common_patterns
