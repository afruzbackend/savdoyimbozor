from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("login/2fa/", views.login_2fa, name="login_2fa"),
    path("profil/2fa/", views.twofa_setup, name="twofa_setup"),
    path("logout/", views.logout_view, name="logout"),
    path("password/change/", views.password_change, name="password_change"),
    path("profile/", views.profile, name="profile"),
    # "sozlamalar/" panelda TIZIM sozlamalari — to'qnashmasin (admin telefoni saqlanmasdi)
    path("profil/sozlamalar/", views.account_settings, name="account_settings"),
]
