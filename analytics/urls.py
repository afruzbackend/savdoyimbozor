from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("alerts/", views.alert_list, name="alerts"),
    path("alerts/<int:pk>/action/", views.alert_action, name="alert_action"),
    path("declarations/upload/", views.declaration_upload, name="declaration_upload"),
]
