from django.urls import path

from . import seller_views as v

app_name = "seller"

urlpatterns = [
    path("", v.home, name="home"),
    path("sotuv/", v.sale_screen, name="sale"),
    path("skaner/", v.scan_screen, name="scan"),
    path("mahsulotlar/", v.products, name="products"),
    path("kirim/", v.stock_in, name="stock_in"),
    path("kun-yakuni/", v.daily_close, name="daily_close"),
    path("qaytarish/", v.returns, name="returns"),
    path("hisobdan-chiqarish/", v.writeoff, name="writeoff"),
    path("nasiya/", v.debts, name="debts"),
    path("hisobot/", v.report, name="report"),
    path("reyting/", v.rating, name="rating"),
    path("tuzatish/", v.corrections, name="corrections"),
    path("e-tiroz/", v.appeals, name="appeals"),
]
