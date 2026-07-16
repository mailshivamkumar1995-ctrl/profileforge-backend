from rest_framework.routers import DefaultRouter
from apps.exports.views import ExportViewSet

router = DefaultRouter()
router.register("", ExportViewSet, basename="export")

urlpatterns = router.urls
