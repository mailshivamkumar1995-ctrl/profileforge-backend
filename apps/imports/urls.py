from rest_framework.routers import DefaultRouter
from apps.imports.views import ImportViewSet

router = DefaultRouter()
router.register("", ImportViewSet, basename="import")

urlpatterns = router.urls
