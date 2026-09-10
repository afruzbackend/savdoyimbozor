from django.urls import path

from . import views

app_name = "markets"

urlpatterns = [
    path("", views.market_list, name="list"),
    path("<int:pk>/", views.market_detail, name="detail"),
    path("shop/<int:pk>/", views.shop_detail, name="shop_detail"),
]
