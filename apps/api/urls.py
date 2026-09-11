"""DRF router + funksional endpointlar. Bosqichma-bosqich to'ldiriladi."""
from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.cameras import api as cameras_api
from apps.sales import api as sales_api

router = DefaultRouter()
# P3: router.register("scores", ...); router.register("alerts", ...)

urlpatterns = [
    path("sales/", sales_api.create_sale_api, name="api_sale_create"),
    path("sales/today/", sales_api.today_summary_api, name="api_sale_today"),
    path("products/lookup/", sales_api.product_lookup_api, name="api_product_lookup"),
    # --- Kamera kontrakti (X-Camera-Token) ---
    path("cameras/config/", cameras_api.camera_config, name="api_camera_config"),
    path("cameras/heartbeat/", cameras_api.heartbeat, name="api_camera_heartbeat"),
    path("events/", cameras_api.ingest_events, name="api_camera_events"),
] + router.urls
