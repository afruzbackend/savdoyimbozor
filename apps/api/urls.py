"""DRF router — barcha app viewset'larini yig'adi (bosqichma-bosqich to'ldiriladi)."""
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

# P2: router.register("sales", SaleViewSet)
# P3: router.register("scores", DailyScoreViewSet); router.register("alerts", AlertViewSet)
# P5: kamera event/config endpoint'lari

urlpatterns = router.urls
