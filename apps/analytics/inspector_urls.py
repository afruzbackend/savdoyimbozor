from django.urls import path

from . import inspector_views

app_name = "inspector"

urlpatterns = [
    path("", inspector_views.dashboard, name="dashboard"),
]
