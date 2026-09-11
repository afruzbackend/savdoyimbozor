"""DRF router + funksional endpointlar. Bosqichma-bosqich to'ldiriladi."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.sales import api as sales_api

router = DefaultRouter()
# P3: router.register("scores", ...); router.register("alerts", ...)

urlpatterns = [
    path("sales/", sales_api.create_sale_api, name="api_sale_create"),
    path("sales/today/", sales_api.today_summary_api, name="api_sale_today"),
] + router.urls
