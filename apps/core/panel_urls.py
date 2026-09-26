from django.urls import path

from . import panel_views as v

app_name = "panel"

urlpatterns = [
    path("", v.dashboard, name="home"),
    path("foydalanuvchilar/", v.user_list, name="users"),
    path("foydalanuvchilar/<int:pk>/", v.user_edit, name="user_edit"),
    path("foydalanuvchilar/<int:pk>/parol/", v.user_reset, name="user_reset"),
    path("dokon/<int:pk>/", v.shop_edit, name="shop_edit"),
    path("foydalanuvchilar/<int:pk>/holat/", v.user_toggle, name="user_toggle"),
    path("foydalanuvchilar/<int:pk>/2fa/", v.user_2fa_reset, name="user_2fa_reset"),
    path("foydalanuvchilar/<int:pk>/parol/korish/", v.user_password_reveal, name="user_password_reveal"),
    path("hisob/yangi/", v.account_create, name="account_create"),
    path("bozorlar/", v.markets, name="markets"),
    path("bozorlar/<int:pk>/", v.market_detail, name="market_detail"),
    path("toifalar/", v.categories, name="categories"),
    path("mahsulot-turlari/", v.product_categories, name="product_categories"),
    path("kameralar/", v.cameras, name="cameras"),
    path("import/dokonlar/", v.import_shops, name="import_shops"),
    path("import/kassa/", v.import_cash, name="import_cash"),
    path("import/kassa/soliq/", v.tax_sync_now, name="tax_sync"),
    path("login-varaqasi/", v.login_sheet, name="login_sheet"),
    path("sozlamalar/", v.settings_edit, name="settings"),
    path("audit/", v.audit_log, name="audit"),
    path("zaxira/", v.backup_now, name="backup_now"),
]
