from django.urls import path

from . import inspector_views as v

app_name = "inspector"

urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    path("xarita/", v.market_map, name="map"),
    path("xarita/<int:pk>/", v.market_map, name="map_market"),
    path("dokon/<int:pk>/", v.shop_detail, name="shop_detail"),
    path("dokon/<int:pk>/dalil/", v.shop_evidence, name="shop_evidence"),
    path("qidiruv/", v.shop_search, name="shop_search"),
    path("signallar/", v.alerts_list, name="alerts"),
    path("signallar/<int:pk>/amal/", v.alert_action, name="alert_action"),
    path("tekshiruvlar/", v.inspections_list, name="inspections"),
    path("tekshiruv/yangi/", v.inspection_create, name="inspection_create"),
    path("tekshiruv/<int:pk>/akt/", v.inspection_act, name="inspection_act"),
    path("e-tirozlar/", v.appeals_list, name="appeals"),
    path("e-tiroz/<int:pk>/javob/", v.appeal_respond, name="appeal_respond"),
    path("hodisalar/", v.incidents_list, name="incidents"),
    path("hodisalar/yangi/", v.incident_create, name="incident_create"),
    path("hodisalar/<int:pk>/", v.incident_detail, name="incident_detail"),
    path("hodisalar/<int:pk>/excel/", v.incident_export, name="incident_export"),
    path("ombor/", v.inventory, name="inventory"),
    path("ombor/<int:pk>/", v.inventory, name="inventory_market"),
    path("ombor/dokon/<int:pk>/", v.shop_inventory, name="shop_inventory"),
    path("kameralar/", v.cameras_status, name="cameras"),
    path("statistika/", v.statistics, name="statistics"),
    path("hisobot/", v.reports, name="reports"),
    path("hisobot/eksport/", v.export_excel, name="export"),
]
