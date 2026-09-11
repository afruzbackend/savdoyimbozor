from django.urls import path

from . import inspector_views as v

app_name = "inspector"

urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    path("xarita/", v.market_map, name="map"),
    path("xarita/<int:pk>/", v.market_map, name="map_market"),
    path("dokon/<int:pk>/", v.shop_detail, name="shop_detail"),
    path("signallar/", v.alerts_list, name="alerts"),
    path("signallar/<int:pk>/amal/", v.alert_action, name="alert_action"),
    path("tekshiruv/yangi/", v.inspection_create, name="inspection_create"),
    path("kameralar/", v.cameras_status, name="cameras"),
    path("hisobot/", v.reports, name="reports"),
    path("hisobot/eksport/", v.export_excel, name="export"),
]
