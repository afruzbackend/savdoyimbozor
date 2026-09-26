from django.urls import path

from . import seller_views as v

app_name = "seller"

urlpatterns = [
    path("", v.home, name="home"),
    path("sotuv/", v.sale_screen, name="sale"),
    path("skaner/", v.scan_screen, name="scan"),
    path("mahsulotlar/", v.products, name="products"),
    path("mahsulotlar/barkodlar/", v.product_labels, name="product_labels"),
    path("kirim/", v.stock_in, name="stock_in"),
    path("kirim/tez/tahlil/", v.stock_in_quick_parse, name="stock_in_quick_parse"),
    path("kirim/tez/saqlash/", v.stock_in_quick_save, name="stock_in_quick_save"),
    path("kassa/", v.register, name="register"),
    path("kun-yakuni/", v.daily_close, name="daily_close"),
    path("qaytarish/", v.returns, name="returns"),
    path("hisobdan-chiqarish/", v.writeoff, name="writeoff"),
    path("nasiya/", v.debts, name="debts"),
    path("hisobot/", v.report, name="report"),
    path("reyting/", v.rating, name="rating"),
    path("tuzatish/", v.corrections, name="corrections"),
    path("e-tiroz/", v.appeals, name="appeals"),
    path("bildirishnomalar/", v.notifications, name="notifications"),
    path("bildirishnomalar/<int:pk>/", v.notification_open, name="notification_open"),
]
