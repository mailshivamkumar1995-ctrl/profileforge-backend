from rest_framework.routers import DefaultRouter
from apps.templates_engine.views import TemplateViewSet

router = DefaultRouter()
router.register("", TemplateViewSet, basename="template")
urlpatterns = router.urls
