import threading

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema

from apps.profiles.models import (
    UserProfile, WorkExperience, Education, Skill,
    Project, Certification, Achievement, Publication,
)
from apps.profiles.serializers import (
    UserProfileSerializer, WorkExperienceSerializer, EducationSerializer,
    SkillSerializer, ProjectSerializer, CertificationSerializer,
    AchievementSerializer, PublicationSerializer, ReorderSerializer,
)
from apps.profiles.services import ProfileService
from core.mixins import SuccessResponseMixin, OwnershipMixin


def _fire_sync(user) -> None:
    """Dispatch Celery sync tasks in a daemon thread so the HTTP response is never blocked."""
    threading.Thread(target=ProfileService._trigger_sync, args=(user,), daemon=True).start()


class ProfileView(SuccessResponseMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = ProfileService.get_profile(request.user)
        return self.success_response(data=UserProfileSerializer(profile).data)

    def patch(self, request):
        profile = ProfileService.get_basic_profile(request.user)
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = ProfileService.update_profile(request.user, serializer.validated_data)
        return self.success_response(data=UserProfileSerializer(updated).data)


class ReorderView(SuccessResponseMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ProfileService.reorder_section(
            request.user,
            serializer.validated_data["section"],
            serializer.validated_data["items"],
        )
        return self.success_response(message="Reordered successfully.")


class BaseProfileSectionViewSet(SuccessResponseMixin, OwnershipMixin, ModelViewSet):
    permission_classes = [IsAuthenticated]
    owner_field = "profile__user"

    def get_profile(self):
        return ProfileService.get_basic_profile(self.request.user)

    def perform_create(self, serializer):
        profile = self.get_profile()
        serializer.save(profile=profile)
        _fire_sync(self.request.user)

    def perform_update(self, serializer):
        serializer.save()
        _fire_sync(self.request.user)

    def perform_destroy(self, instance):
        instance.delete()
        _fire_sync(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.success_response(data=serializer.data, status_code=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return self.success_response(data=serializer.data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}
        return self.success_response(data=serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return self.success_response()


class WorkExperienceViewSet(BaseProfileSectionViewSet):
    serializer_class = WorkExperienceSerializer
    queryset = WorkExperience.objects.all()


class EducationViewSet(BaseProfileSectionViewSet):
    serializer_class = EducationSerializer
    queryset = Education.objects.all()


class SkillViewSet(BaseProfileSectionViewSet):
    serializer_class = SkillSerializer
    queryset = Skill.objects.all()

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk_upsert(self, request):
        """Bulk create/update skills from a list."""
        skills_data = request.data.get("skills", [])
        created_skills = ProfileService.bulk_upsert_skills(request.user, skills_data)
        return self.success_response(data=SkillSerializer(created_skills, many=True).data)


class ProjectViewSet(BaseProfileSectionViewSet):
    serializer_class = ProjectSerializer
    queryset = Project.objects.all()


class CertificationViewSet(BaseProfileSectionViewSet):
    serializer_class = CertificationSerializer
    queryset = Certification.objects.all()


class AchievementViewSet(BaseProfileSectionViewSet):
    serializer_class = AchievementSerializer
    queryset = Achievement.objects.all()


class PublicationViewSet(BaseProfileSectionViewSet):
    serializer_class = PublicationSerializer
    queryset = Publication.objects.all()
