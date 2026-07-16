from django.urls import path
from core.health_views import LivenessView, ReadinessView, HealthView

urlpatterns = [
    path("", HealthView.as_view(), name="health"),
    path("live/", LivenessView.as_view(), name="health-live"),
    path("ready/", ReadinessView.as_view(), name="health-ready"),
]
