import logging
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.imports.models import ImportJob, ImportStatus
from apps.imports.serializers import (
    ImportJobListSerializer, ImportJobDetailSerializer,
    ImportUploadSerializer, ApplyMappingSerializer,
)
from apps.imports.services import ImportService
from core.mixins import SuccessResponseMixin
from core.exceptions import NotFoundException
from core.throttles import UploadRateThrottle

logger = logging.getLogger(__name__)


class ImportViewSet(SuccessResponseMixin, ViewSet):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def list(self, request):
        """List all import jobs for the current user."""
        jobs = ImportService.list_for_user(request.user)
        return self.success_response(data=ImportJobListSerializer(jobs, many=True).data)

    def retrieve(self, request, pk=None):
        """Get import job detail including mapping_review."""
        try:
            job = ImportService.get_for_user(pk, request.user)
        except ImportJob.DoesNotExist:
            raise NotFoundException("Import job not found.")
        return self.success_response(data=ImportJobDetailSerializer(job).data)

    def destroy(self, request, pk=None):
        """Delete an import job and its stored file."""
        try:
            job = ImportService.get_for_user(pk, request.user)
        except ImportJob.DoesNotExist:
            raise NotFoundException("Import job not found.")
        ImportService.delete(job)
        return self.success_response(message="Import job deleted.", status_code=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="upload",
            throttle_classes=[UploadRateThrottle])
    def upload(self, request):
        """Upload a document for import. Enqueues async parsing."""
        serializer = ImportUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = ImportService.upload(request.user, serializer.validated_data["file"])
        return self.success_response(
            data=ImportJobDetailSerializer(job).data,
            status_code=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["post"], url_path="apply")
    def apply_mapping(self, request, pk=None):
        """Apply user-approved field mappings to the profile."""
        try:
            job = ImportService.get_for_user(pk, request.user)
        except ImportJob.DoesNotExist:
            raise NotFoundException("Import job not found.")

        if job.status != ImportStatus.REVIEW_REQUIRED:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({
                "status": f"Cannot apply mapping in status '{job.status}'. "
                          f"Job must be in 'review_required' state."
            })

        serializer = ApplyMappingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = ImportService.apply_mapping(job, serializer.validated_data)
        return self.success_response(
            data=ImportJobDetailSerializer(job).data,
            message="Profile updated from import.",
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancel a pending or processing import job."""
        try:
            job = ImportService.get_for_user(pk, request.user)
        except ImportJob.DoesNotExist:
            raise NotFoundException("Import job not found.")
        job = ImportService.cancel(job)
        return self.success_response(data=ImportJobDetailSerializer(job).data)
