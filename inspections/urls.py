from django.urls import path

from . import views

app_name = "inspections"

urlpatterns = [
    path("", views.inspection_list, name="list"),
    path("new/", views.inspection_create, name="create"),
]
