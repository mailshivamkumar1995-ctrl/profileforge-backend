import logging
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from apps.portfolios.models import Portfolio
from apps.portfolios.serializers import (
    PortfolioListSerializer, PortfolioDetailSerializer,
    PortfolioCreateSerializer, PortfolioUpdateSerializer,
    PortfolioVersionSerializer, PublicPortfolioSerializer,
)
from apps.portfolios.services import PortfolioService
from apps.profiles.profile_utils import ProfileSerializer
from apps.profiles.models import UserProfile
from core.mixins import SuccessResponseMixin
from core.exceptions import NotFoundException as NotFoundError

logger = logging.getLogger(__name__)


class PortfolioViewSet(SuccessResponseMixin, ViewSet):
    permission_classes = [IsAuthenticated]

    def _get_or_404(self, user) -> Portfolio:
        try:
            return PortfolioService.get_for_user(user)
        except Portfolio.DoesNotExist:
            raise NotFoundError("Portfolio not found.")

    # ── Singleton portfolio per user ──────────────────────────────────────────

    @extend_schema(responses=PortfolioDetailSerializer)
    def list(self, request):
        """Returns the user's portfolio (creates if not exists)."""
        portfolio, _ = PortfolioService.get_or_create_for_user(request.user)
        return self.success_response(data=PortfolioDetailSerializer(portfolio).data)

    @extend_schema(request=PortfolioCreateSerializer, responses=PortfolioDetailSerializer)
    def create(self, request):
        """Explicitly create a portfolio (or return existing)."""
        portfolio, created = PortfolioService.get_or_create_for_user(request.user)
        if not created:
            return self.success_response(data=PortfolioDetailSerializer(portfolio).data)

        serializer = PortfolioCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        portfolio = PortfolioService.update(
            portfolio, serializer.validated_data, request.user
        )
        return self.success_response(
            data=PortfolioDetailSerializer(portfolio).data,
            status_code=status.HTTP_201_CREATED,
        )

    @extend_schema(responses=PortfolioDetailSerializer)
    def retrieve(self, request, pk=None):
        portfolio = self._get_or_404(request.user)
        return self.success_response(data=PortfolioDetailSerializer(portfolio).data)

    @extend_schema(request=PortfolioUpdateSerializer, responses=PortfolioDetailSerializer)
    def partial_update(self, request, pk=None):
        portfolio = self._get_or_404(request.user)
        serializer = PortfolioUpdateSerializer(
            data=request.data,
            partial=True,
            context={"portfolio_id": portfolio.id},
        )
        serializer.is_valid(raise_exception=True)
        portfolio = PortfolioService.update(portfolio, serializer.validated_data, request.user)
        return self.success_response(data=PortfolioDetailSerializer(portfolio).data)

    def destroy(self, request, pk=None):
        portfolio = self._get_or_404(request.user)
        PortfolioService.delete(portfolio)
        return self.success_response(message="Portfolio deleted.", status_code=status.HTTP_200_OK)

    # ── Extra actions ─────────────────────────────────────────────────────────

    @extend_schema(responses=PortfolioDetailSerializer)
    @action(detail=False, methods=["post"], url_path="publish")
    def publish(self, request):
        portfolio = self._get_or_404(request.user)
        portfolio = PortfolioService.publish(portfolio, request.user)
        return self.success_response(data=PortfolioDetailSerializer(portfolio).data)

    @extend_schema(responses=PortfolioDetailSerializer)
    @action(detail=False, methods=["post"], url_path="unpublish")
    def unpublish(self, request):
        portfolio = self._get_or_404(request.user)
        portfolio = PortfolioService.unpublish(portfolio)
        return self.success_response(data=PortfolioDetailSerializer(portfolio).data)

    @extend_schema(responses={"200": {"type": "object", "properties": {"html": {"type": "string"}}}})
    @action(detail=False, methods=["get"], url_path="preview")
    def preview(self, request):
        portfolio = self._get_or_404(request.user)
        html = PortfolioService.rebuild_preview(portfolio)
        return self.success_response(data={"html": html})

    @extend_schema(responses=PortfolioVersionSerializer(many=True))
    @action(detail=False, methods=["get"], url_path="versions")
    def versions(self, request):
        portfolio = self._get_or_404(request.user)
        versions = PortfolioService.list_versions(portfolio)
        return self.success_response(data=PortfolioVersionSerializer(versions, many=True).data)

    @extend_schema(responses={"200": {"type": "object"}})
    @action(detail=False, methods=["get"], url_path="seo")
    def seo(self, request):
        portfolio = self._get_or_404(request.user)
        seo_data = PortfolioService.generate_seo(portfolio)
        return self.success_response(data=seo_data)

    @extend_schema(responses=PortfolioDetailSerializer)
    @action(detail=False, methods=["post"], url_path="auto-fill-seo")
    def auto_fill_seo(self, request):
        portfolio = self._get_or_404(request.user)
        portfolio = PortfolioService.auto_fill_seo(portfolio, request.user)
        return self.success_response(data=PortfolioDetailSerializer(portfolio).data)

    @extend_schema(responses=PortfolioDetailSerializer)
    @action(detail=False, methods=["post"], url_path="toggle-section")
    def toggle_section(self, request):
        portfolio = self._get_or_404(request.user)
        section = request.data.get("section", "")
        enabled = bool(request.data.get("enabled", True))
        from apps.portfolios.models import SECTION_DEFAULTS
        if section not in SECTION_DEFAULTS:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"section": f"Unknown section: {section}"})
        portfolio = PortfolioService.toggle_section(portfolio, section, enabled, request.user)
        return self.success_response(data=PortfolioDetailSerializer(portfolio).data)

    @extend_schema(responses=PortfolioDetailSerializer)
    @action(detail=False, methods=["post"], url_path="reorder-sections")
    def reorder_sections(self, request):
        portfolio = self._get_or_404(request.user)
        order = request.data.get("order", [])
        if not isinstance(order, list):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"order": "Must be a list of section names."})
        portfolio = PortfolioService.reorder_sections(portfolio, order, request.user)
        return self.success_response(data=PortfolioDetailSerializer(portfolio).data)


# ── Public Views ──────────────────────────────────────────────────────────────

class PublicPortfolioByUsernameView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={"200": {"type": "object"}})
    def get(self, request, username: str):
        try:
            portfolio = PortfolioService.get_by_username(username)
        except Portfolio.DoesNotExist:
            return Response({"detail": "Portfolio not found."}, status=status.HTTP_404_NOT_FOUND)

        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements", "publications",
        ).get(user=portfolio.user)
        profile_data = ProfileSerializer.to_dict(profile)
        from apps.portfolios.services import SEOGenerator
        seo_data = SEOGenerator.generate(profile_data, portfolio)

        return Response({
            "success": True,
            "data": {
                "portfolio": PublicPortfolioSerializer(portfolio).data,
                "profile": profile_data,
                "seo": seo_data,
            },
        })


class PublicPortfolioBySlugView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses={"200": {"type": "object"}})
    def get(self, request, slug: str):
        try:
            portfolio = PortfolioService.get_by_slug(slug)
        except Portfolio.DoesNotExist:
            return Response({"detail": "Portfolio not found."}, status=status.HTTP_404_NOT_FOUND)

        profile = UserProfile.objects.prefetch_related(
            "work_experiences", "educations", "skills",
            "projects", "certifications", "achievements", "publications",
        ).get(user=portfolio.user)
        profile_data = ProfileSerializer.to_dict(profile)
        from apps.portfolios.services import SEOGenerator
        seo_data = SEOGenerator.generate(profile_data, portfolio)

        return Response({
            "success": True,
            "data": {
                "portfolio": PublicPortfolioSerializer(portfolio).data,
                "profile": profile_data,
                "seo": seo_data,
            },
        })


class PublicPortfolioHTMLView(APIView):
    """Returns fully rendered HTML for embedding or server-side rendering."""
    permission_classes = [AllowAny]

    def get(self, request, username: str):
        try:
            portfolio = PortfolioService.get_by_username(username)
        except Portfolio.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        html = PortfolioService.rebuild_preview(portfolio)
        from django.http import HttpResponse
        return HttpResponse(html, content_type="text/html")
