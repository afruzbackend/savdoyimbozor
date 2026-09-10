from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_summary, name="summary"),
    path("export/", views.export_excel, name="export"),
]
