from django.urls import path

from . import views

urlpatterns = [
    path("theme/", views.set_theme, name="set_theme"),
    path("language/", views.set_language, name="set_language"),
    path("styleguide/", views.styleguide, name="styleguide"),
    path("healthz/", views.healthz, name="healthz"),
    path("xato/<str:code>/", views.error_preview, name="error_preview"),
]
