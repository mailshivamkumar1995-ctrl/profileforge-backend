from rest_framework.routers import DefaultRouter
from apps.portfolios.views import PortfolioViewSet

router = DefaultRouter()
router.register("", PortfolioViewSet, basename="portfolio")
urlpatterns = router.urls
