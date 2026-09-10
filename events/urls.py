from django.urls import path

from . import api, views

app_name = "events"

urlpatterns = [
    # Kamera/AI worker → backend
    path("events/", api.ingest_event, name="ingest"),
    path("heartbeat/", api.camera_heartbeat, name="heartbeat"),
    # Sotuvchi qo'lda savdo kiritishi (PWA)
    path("sale/new/", views.sale_create, name="sale_create"),
    path("writeoff/new/", views.writeoff_create, name="writeoff_create"),
]
