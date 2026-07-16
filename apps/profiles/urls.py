from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.profiles.views import (
    ProfileView, ReorderView,
    WorkExperienceViewSet, EducationViewSet, SkillViewSet,
    ProjectViewSet, CertificationViewSet, AchievementViewSet,
    PublicationViewSet,
)

router = DefaultRouter()
router.register(r"me/experience", WorkExperienceViewSet, basename="experience")
router.register(r"me/education", EducationViewSet, basename="education")
router.register(r"me/skills", SkillViewSet, basename="skills")
router.register(r"me/projects", ProjectViewSet, basename="projects")
router.register(r"me/certifications", CertificationViewSet, basename="certifications")
router.register(r"me/achievements", AchievementViewSet, basename="achievements")
router.register(r"me/publications", PublicationViewSet, basename="publications")

urlpatterns = [
    path("me/", ProfileView.as_view(), name="profile-me"),
    path("me/reorder/", ReorderView.as_view(), name="profile-reorder"),
    path("", include(router.urls)),
]
