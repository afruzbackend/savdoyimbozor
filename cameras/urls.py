from django.urls import path

from . import views

app_name = "cameras"

urlpatterns = [
    path("", views.camera_list, name="list"),
]
