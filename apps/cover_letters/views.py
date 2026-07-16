import logging
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet
from drf_spectacular.utils import extend_schema

from apps.cover_letters.models import CoverLetter
from apps.cover_letters.serializers import (
    CoverLetterListSerializer, CoverLetterDetailSerializer,
    CoverLetterCreateSerializer, CoverLetterUpdateSerializer,
    CoverLetterVersionSerializer, CoverLetterGenerateSerializer,
    CoverLetterRewriteSerializer, CoverLetterImproveToneSerializer,
)
from apps.cover_letters.services import CoverLetterService
from core.mixins import SuccessResponseMixin
from core.exceptions import NotFoundException as NotFoundError
from core.throttles import AiRateThrottle

logger = logging.getLogger(__name__)


class CoverLetterViewSet(SuccessResponseMixin, ViewSet):
    permission_classes = [IsAuthenticated]

    def _get_or_404(self, pk: str, user) -> CoverLetter:
        try:
            return CoverLetterService.get_for_user(pk, user)
        except CoverLetter.DoesNotExist:
            raise NotFoundError("Cover letter not found.")

    @extend_schema(responses=CoverLetterListSerializer(many=True))
    def list(self, request):
        letters = CoverLetterService.list_for_user(request.user)
        return self.success_response(data=CoverLetterListSerializer(letters, many=True).data)

    @extend_schema(request=CoverLetterCreateSerializer, responses=CoverLetterDetailSerializer)
    def create(self, request):
        serializer = CoverLetterCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        letter = CoverLetterService.create(request.user, serializer.validated_data)
        return self.success_response(
            data=CoverLetterDetailSerializer(letter).data,
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(responses=CoverLetterDetailSerializer)
    def retrieve(self, request, pk=None):
        letter = self._get_or_404(pk, request.user)
        return self.success_response(data=CoverLetterDetailSerializer(letter).data)

    @extend_schema(request=CoverLetterUpdateSerializer, responses=CoverLetterDetailSerializer)
    def partial_update(self, request, pk=None):
        letter = self._get_or_404(pk, request.user)
        serializer = CoverLetterUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        letter = CoverLetterService.update(letter, serializer.validated_data, request.user)
        return self.success_response(data=CoverLetterDetailSerializer(letter).data)

    def destroy(self, request, pk=None):
        letter = self._get_or_404(pk, request.user)
        CoverLetterService.delete(letter)
        return self.success_response(message="Cover letter deleted.", status_code=status.HTTP_200_OK)

    # ── Extra actions ─────────────────────────────────────────────────────────

    @extend_schema(responses=CoverLetterDetailSerializer)
    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate(self, request, pk=None):
        letter = self._get_or_404(pk, request.user)
        copy = CoverLetterService.duplicate(letter, request.user)
        return self.success_response(
            data=CoverLetterDetailSerializer(copy).data,
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(responses=CoverLetterDetailSerializer)
    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        letter = self._get_or_404(pk, request.user)
        letter = CoverLetterService.archive(letter)
        return self.success_response(data=CoverLetterDetailSerializer(letter).data)

    @extend_schema(responses={"200": {"type": "object", "properties": {"html": {"type": "string"}}}})
    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request, pk=None):
        letter = self._get_or_404(pk, request.user)
        html = CoverLetterService.rebuild_preview(letter)
        return self.success_response(data={"html": html})

    @extend_schema(responses=CoverLetterVersionSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request, pk=None):
        letter = self._get_or_404(pk, request.user)
        versions = CoverLetterService.list_versions(letter)
        return self.success_response(data=CoverLetterVersionSerializer(versions, many=True).data)

    @extend_schema(request=CoverLetterGenerateSerializer, responses=CoverLetterDetailSerializer)
    @action(detail=True, methods=["post"], url_path="generate",
            throttle_classes=[AiRateThrottle])  # FINDING-007
    def generate(self, request, pk=None):
        letter = self._get_or_404(pk, request.user)
        serializer = CoverLetterGenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        letter = CoverLetterService.generate_from_profile(
            cover_letter=letter,
            user=request.user,
            tone=serializer.validated_data.get("tone", ""),
            job_description=serializer.validated_data.get("job_description", ""),
        )
        return self.success_response(data=CoverLetterDetailSerializer(letter).data)

    @extend_schema(request=CoverLetterRewriteSerializer, responses=CoverLetterDetailSerializer)
    @action(detail=True, methods=["post"], url_path="rewrite",
            throttle_classes=[AiRateThrottle])  # FINDING-007
    def rewrite(self, request, pk=None):
        letter = self._get_or_404(pk, request.user)
        serializer = CoverLetterRewriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        letter = CoverLetterService.rewrite(
            cover_letter=letter,
            user=request.user,
            instruction=serializer.validated_data.get("instruction", ""),
        )
        return self.success_response(data=CoverLetterDetailSerializer(letter).data)

    @extend_schema(request=CoverLetterImproveToneSerializer, responses=CoverLetterDetailSerializer)
    @action(detail=True, methods=["post"], url_path="improve-tone",
            throttle_classes=[AiRateThrottle])  # FINDING-007
    def improve_tone(self, request, pk=None):
        letter = self._get_or_404(pk, request.user)
        serializer = CoverLetterImproveToneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        letter = CoverLetterService.improve_tone(
            cover_letter=letter,
            user=request.user,
            tone=serializer.validated_data["tone"],
        )
        return self.success_response(data=CoverLetterDetailSerializer(letter).data)

    @extend_schema(responses=CoverLetterDetailSerializer)
    @action(detail=True, methods=["post"], url_path="improve-ats",
            throttle_classes=[AiRateThrottle])  # FINDING-007
    def improve_ats(self, request, pk=None):
        letter = self._get_or_404(pk, request.user)
        letter = CoverLetterService.improve_ats(cover_letter=letter, user=request.user)
        return self.success_response(data=CoverLetterDetailSerializer(letter).data)
