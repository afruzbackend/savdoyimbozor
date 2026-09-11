from django.urls import path

from . import panel_views as v

app_name = "panel"

urlpatterns = [
    path("", v.dashboard, name="home"),
    path("foydalanuvchilar/", v.user_list, name="users"),
    path("foydalanuvchilar/<int:pk>/parol/", v.user_reset, name="user_reset"),
    path("foydalanuvchilar/<int:pk>/holat/", v.user_toggle, name="user_toggle"),
    path("hisob/yangi/", v.account_create, name="account_create"),
    path("import/dokonlar/", v.import_shops, name="import_shops"),
    path("import/kassa/", v.import_cash, name="import_cash"),
    path("login-varaqasi/", v.login_sheet, name="login_sheet"),
    path("sozlamalar/", v.settings_edit, name="settings"),
    path("audit/", v.audit_log, name="audit"),
]
