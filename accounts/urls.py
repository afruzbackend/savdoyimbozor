from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.RoleLoginView.as_view(), name="login"),
    path("logout/", views.do_logout, name="logout"),
    path("profile/", views.profile, name="profile"),
]
