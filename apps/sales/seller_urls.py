from django.urls import path

from . import seller_views

app_name = "seller"

urlpatterns = [
    path("", seller_views.home, name="home"),
    path("sotuv/", seller_views.sale_screen, name="sale"),
]
