from rest_framework.routers import DefaultRouter
from apps.cover_letters.views import CoverLetterViewSet

router = DefaultRouter()
router.register("", CoverLetterViewSet, basename="cover-letter")
urlpatterns = router.urls
