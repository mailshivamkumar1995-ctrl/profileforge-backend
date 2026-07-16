import logging
from rest_framework.views import exception_handler
from rest_framework.exceptions import APIException
from rest_framework import status
from django.http import Http404
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)


class ProfileForgeException(APIException):
    """Base exception for all application errors."""
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "APPLICATION_ERROR"

    def __init__(self, message=None, code=None, details=None):
        self.detail = message or self.default_detail
        self.error_code = code or self.__class__.error_code
        self.extra_details = details or {}
        super().__init__(detail=self.detail)


class ValidationException(ProfileForgeException):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "VALIDATION_ERROR"


class NotFoundException(ProfileForgeException):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class PermissionException(ProfileForgeException):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "PERMISSION_DENIED"


class ConflictException(ProfileForgeException):
    status_code = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"


class StorageException(ProfileForgeException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "STORAGE_ERROR"


class AIProviderException(ProfileForgeException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "AI_PROVIDER_ERROR"


def custom_exception_handler(exc, context):
    """Transform all exceptions into the standard error envelope."""
    request = context.get("request")
    request_id = getattr(request, "request_id", "") if request else ""

    # Map Django/DRF exceptions
    if isinstance(exc, Http404):
        exc = NotFoundException("Resource not found.")
    elif isinstance(exc, PermissionDenied):
        exc = PermissionException("Permission denied.")

    response = exception_handler(exc, context)

    if response is not None:
        error_code = getattr(exc, "error_code", "API_ERROR")
        message = _extract_message(exc)
        details = _extract_details(exc)

        response.data = {
            "success": False,
            "error": {
                "code": error_code,
                "message": message,
                "details": details,
                "request_id": request_id,
            },
        }

        if response.status_code >= 500:
            logger.error(
                "Server error",
                extra={"request_id": request_id, "exception": str(exc)},
                exc_info=True,
            )

    return response


def _extract_message(exc) -> str:
    detail = getattr(exc, "detail", str(exc))
    if isinstance(detail, list):
        return str(detail[0]) if detail else "An error occurred."
    if isinstance(detail, dict):
        first_key = next(iter(detail), None)
        if first_key:
            val = detail[first_key]
            return str(val[0]) if isinstance(val, list) else str(val)
    return str(detail)


def _extract_details(exc) -> dict:
    detail = getattr(exc, "detail", None)
    extra = getattr(exc, "extra_details", {})
    if isinstance(detail, dict):
        return {k: [str(v) for v in vs] if isinstance(vs, list) else [str(vs)] for k, vs in detail.items()}
    return extra
