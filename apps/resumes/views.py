import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet
from drf_spectacular.utils import extend_schema

from apps.resumes.models import Resume
from apps.resumes.serializers import (
    ResumeListSerializer, ResumeDetailSerializer,
    ResumeCreateSerializer, ResumeUpdateSerializer,
    ResumeVersionSerializer, ATSAnalyzeSerializer,
    OptimizeSerializer,
)
from core.throttles import AiRateThrottle
from apps.resumes.services import ResumeService
from core.mixins import SuccessResponseMixin
from core.exceptions import NotFoundException as NotFoundError

logger = logging.getLogger(__name__)


class ResumeViewSet(SuccessResponseMixin, ViewSet):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ResumeListSerializer(many=True))
    def list(self, request):
        resumes = ResumeService.list_for_user(request.user)
        return self.success_response(data=ResumeListSerializer(resumes, many=True).data)

    @extend_schema(request=ResumeCreateSerializer, responses=ResumeDetailSerializer)
    def create(self, request):
        serializer = ResumeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resume = ResumeService.create(request.user, serializer.validated_data)
        return self.success_response(
            data=ResumeDetailSerializer(resume).data,
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(responses=ResumeDetailSerializer)
    def retrieve(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        return self.success_response(data=ResumeDetailSerializer(resume).data)

    @extend_schema(request=ResumeUpdateSerializer, responses=ResumeDetailSerializer)
    def partial_update(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        serializer = ResumeUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        resume = ResumeService.update(resume, serializer.validated_data, request.user)
        return self.success_response(data=ResumeDetailSerializer(resume).data)

    def destroy(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        ResumeService.delete(resume)
        return self.success_response(message="Resume deleted.", status_code=status.HTTP_200_OK)

    @extend_schema(responses=ResumeDetailSerializer)
    @action(detail=True, methods=["post"], url_path="set-primary")
    def set_primary(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        resume = ResumeService.set_primary(resume, request.user)
        return self.success_response(data=ResumeDetailSerializer(resume).data)

    @extend_schema(responses={"200": {"type": "object", "properties": {"html": {"type": "string"}}}})
    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        template_slug = request.query_params.get("template_slug") or None
        html = ResumeService.rebuild_preview(resume, template_slug=template_slug)
        return self.success_response(data={"html": html})

    @extend_schema(responses=ResumeVersionSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        versions = ResumeService.list_versions(resume)
        return self.success_response(data=ResumeVersionSerializer(versions, many=True).data)

    @extend_schema(responses=ResumeDetailSerializer)
    @action(detail=True, methods=["post"], url_path="duplicate")
    def duplicate(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        copy = ResumeService.duplicate(resume, request.user)
        return self.success_response(
            data=ResumeDetailSerializer(copy).data,
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(request=ATSAnalyzeSerializer)
    @action(detail=True, methods=["post"], url_path="ats-analyze")
    def ats_analyze(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        serializer = ATSAnalyzeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ResumeService.analyze_ats(
            resume, serializer.validated_data.get("job_description", "")
        )
        return self.success_response(data=result)

    @extend_schema(request=OptimizeSerializer)
    @action(detail=True, methods=["post"], url_path="optimize")
    def optimize(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        serializer = OptimizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.resumes.optimization_service import OptimizationService
        report = OptimizationService.analyze(
            resume, serializer.validated_data.get("job_description", "")
        )
        return self.success_response(data=report.to_dict())

    @extend_schema(responses={"200": {"type": "object"}})
    @action(detail=True, methods=["get"], url_path="optimization")
    def optimization(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        from apps.resumes.optimization_service import OptimizationService
        report = OptimizationService.get_report(resume)
        # Return null data (not 404) when no report exists yet.
        # 404 causes the frontend to show an error state instead of the correct
        # empty state ("No analysis yet — click Analyze Resume").
        return self.success_response(data=report.to_dict() if report else None)

    @extend_schema(request=OptimizeSerializer)
    @action(
        detail=True, methods=["post"], url_path="optimize-ai",
        throttle_classes=[AiRateThrottle],
    )
    def optimize_ai(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        serializer = OptimizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.resumes.ai_optimization_service import AIOptimizationService
        report = AIOptimizationService.enhance(
            resume,
            job_description=serializer.validated_data.get("job_description", ""),
            user=request.user,
        )
        return self.success_response(data=report.to_dict())

    @extend_schema(responses={"200": {"type": "object"}})
    @action(detail=True, methods=["get"], url_path="ai-optimization")
    def ai_optimization(self, request, pk=None):
        try:
            resume = ResumeService.get_for_user(pk, request.user)
        except Resume.DoesNotExist:
            raise NotFoundError("Resume not found.")
        from apps.resumes.ai_optimization_service import AIOptimizationService
        report = AIOptimizationService.get_report(resume)
        # Return null data (not 404) — same contract as GET /optimization/.
        return self.success_response(data=report.to_dict() if report else None)
