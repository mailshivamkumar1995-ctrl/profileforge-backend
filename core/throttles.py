"""
Custom DRF throttle classes for ProfileForge AI.

SEC-005 fix: each throttle overrides allow_request() to fail closed when
the Redis cache backend is unavailable. Previously, IGNORE_EXCEPTIONS=True
in the cache config caused all cache.get() calls to return None during a
Redis outage, making throttles believe every request was the first —
effectively disabling rate limiting. With IGNORE_EXCEPTIONS removed, Redis
errors propagate; we catch them here and deny the request (fail closed).
"""
import logging

from django.core.cache import CacheKeyWarning  # noqa: F401 — ensure import works
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

logger = logging.getLogger(__name__)


class _FailClosedMixin:
    """
    Mixin that catches cache backend exceptions in allow_request() and
    denies the request (fail closed) instead of silently allowing it.

    This prevents rate-limiting bypass when Redis is unavailable.
    """

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception as exc:
            logger.error(
                "Throttle cache backend unavailable (%s: %s) — denying request (fail closed)",
                type(exc).__name__,
                exc,
            )
            return False


class LoginRateThrottle(_FailClosedMixin, AnonRateThrottle):
    """
    10 requests/minute per IP — prevents credential stuffing.
    Applied as anonymous throttle so it also covers unauthenticated attempts.
    """
    scope = "login"


class RegistrationRateThrottle(_FailClosedMixin, AnonRateThrottle):
    """
    5 requests/minute per IP — prevents automated account creation.
    Separate scope from login so abuse of one does not block the other.
    """
    scope = "registration"


class AiRateThrottle(_FailClosedMixin, UserRateThrottle):
    """
    20 requests/minute per user — limits AI provider cost exposure.
    Applied at the view level on: /generate/, /rewrite/, /improve-tone/, /improve-ats/
    """
    scope = "ai"


class UploadRateThrottle(_FailClosedMixin, UserRateThrottle):
    """
    10 requests/minute per user — prevents storage exhaustion via upload floods.
    """
    scope = "upload"


class ExportRateThrottle(_FailClosedMixin, UserRateThrottle):
    """
    20 requests/minute per user — limits Celery queue exhaustion.
    """
    scope = "export"


class PasswordResetRateThrottle(_FailClosedMixin, AnonRateThrottle):
    """
    3 requests/minute per IP — prevents reset-link spam and user enumeration via timing.
    Fail-closed: Redis outage denies rather than bypasses the throttle.
    """
    scope = "password_reset"


class CareerHubSearchThrottle(_FailClosedMixin, UserRateThrottle):
    """
    60 requests/minute per user — limits DB load from FTS job search queries.
    Separate scope from global user throttle (300/min) because FTS queries are
    significantly more expensive than standard API reads.
    Anonymous requests never reach this throttle — JWT blocks them first.
    """
    scope = "career_hub_search"
