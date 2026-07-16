import logging
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from apps.exports.models import ExportJob, ExportStatus
from apps.exports.serializers import (
    ExportJobListSerializer, ExportJobDetailSerializer, ExportRequestSerializer,
)
from apps.exports.services import ExportService
from core.mixins import SuccessResponseMixin
from core.exceptions import NotFoundException, ValidationException

logger = logging.getLogger(__name__)


class ExportViewSet(SuccessResponseMixin, ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """List all export jobs for the current user."""
        resource_type = request.query_params.get("resource_type")
        jobs = ExportService.list_for_user(request.user, resource_type=resource_type)
        return self.success_response(data=ExportJobListSerializer(jobs, many=True).data)

    def retrieve(self, request, pk=None):
        """Get export job detail including download URL."""
        try:
            job = ExportService.get_for_user(pk, request.user)
        except ExportJob.DoesNotExist:
            raise NotFoundException("Export job not found.")
        return self.success_response(data=ExportJobDetailSerializer(job).data)

    def destroy(self, request, pk=None):
        """Delete an export job and its stored file."""
        try:
            job = ExportService.get_for_user(pk, request.user)
        except ExportJob.DoesNotExist:
            raise NotFoundException("Export job not found.")
        ExportService.delete(job)
        return self.success_response(message="Export deleted.", status_code=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="request")
    def request_export(self, request):
        """Request a new export. Returns job ID immediately (202 Accepted)."""
        serializer = ExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        job = ExportService.request(
            user=request.user,
            resource_type=data["resource_type"],
            resource_id=str(data["resource_id"]),
            fmt=data["format"],
            template_slug=data.get("template_slug"),
        )
        return self.success_response(
            data=ExportJobDetailSerializer(job).data,
            status_code=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="download")
    def download(self, request, pk=None):
        """Get a fresh signed download URL for a completed export."""
        try:
            job = ExportService.get_for_user(pk, request.user)
        except ExportJob.DoesNotExist:
            raise NotFoundException("Export job not found.")
        if job.status != ExportStatus.COMPLETED:
            raise ValidationException(f"Export is not ready. Current status: {job.status}")
        url = ExportService.get_download_url(job)
        return self.success_response(data={
            "download_url": url,
            "expires_at": job.url_expires_at,
            "filename": ExportService.get_download_filename(job),
        })

    @action(detail=True, methods=["post"], url_path="regenerate")
    def regenerate(self, request, pk=None):
        """Create a new export job for the same resource with latest data."""
        try:
            job = ExportService.get_for_user(pk, request.user)
        except ExportJob.DoesNotExist:
            raise NotFoundException("Export job not found.")
        new_job = ExportService.regenerate(job)
        return self.success_response(
            data=ExportJobDetailSerializer(new_job).data,
            status_code=status.HTTP_202_ACCEPTED,
        )
