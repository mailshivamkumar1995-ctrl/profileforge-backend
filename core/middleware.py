import time
import uuid
import logging

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class RequestIDMiddleware(MiddlewareMixin):
    """Attaches a unique X-Request-ID to every request and response."""

    def process_request(self, request):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.request_id = request_id
        request._start_time = time.monotonic()

    def process_response(self, request, response):
        request_id = getattr(request, "request_id", str(uuid.uuid4()))
        response["X-Request-ID"] = request_id
        return response


class AuditLogMiddleware(MiddlewareMixin):
    """Creates audit log entries for mutating API requests."""

    AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
    SKIP_PATHS = {"/health/", "/metrics/", "/api/schema/", "/admin/"}

    def process_response(self, request, response):
        if request.method not in self.AUDIT_METHODS:
            return response

        path = request.path_info
        if any(path.startswith(p) for p in self.SKIP_PATHS):
            return response

        duration_ms = None
        start_time = getattr(request, "_start_time", None)
        if start_time:
            duration_ms = int((time.monotonic() - start_time) * 1000)

        try:
            from core.models import AuditLog, AuditAction
            from core.audit import resolve_action

            action = resolve_action(request.method, response.status_code)
            user = request.user if request.user.is_authenticated else None

            AuditLog.objects.create(
                user=user,
                request_id=getattr(request, "request_id", ""),
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                method=request.method,
                path=path,
                action=action,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        except Exception:
            logger.exception("Failed to write audit log")

        return response

    @staticmethod
    def _get_client_ip(request) -> str:
        from core.security import get_client_ip
        return get_client_ip(request)
