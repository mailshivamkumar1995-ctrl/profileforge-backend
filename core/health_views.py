import logging
from django.http import JsonResponse
from django.views import View
from django.db import connection
from django.core.cache import cache

logger = logging.getLogger(__name__)


class LivenessView(View):
    """K8s liveness probe — just confirms the process is alive."""

    def get(self, request):
        return JsonResponse({"status": "ok"}, status=200)


class ReadinessView(View):
    """K8s readiness probe — confirms DB and Redis are reachable."""

    def get(self, request):
        checks = {}
        healthy = True

        # Database check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            checks["database"] = "ok"
        except Exception as e:
            checks["database"] = f"error: {e}"
            healthy = False
            logger.error("Database health check failed", exc_info=True)

        # Redis check
        try:
            cache.set("health_check", "ok", timeout=5)
            val = cache.get("health_check")
            checks["redis"] = "ok" if val == "ok" else "error: cache miss"
        except Exception as e:
            checks["redis"] = f"error: {e}"
            healthy = False
            logger.error("Redis health check failed", exc_info=True)

        status_code = 200 if healthy else 503
        return JsonResponse({"status": "ok" if healthy else "degraded", "checks": checks}, status=status_code)


class HealthView(View):
    """Overall platform health with service details."""

    def get(self, request):
        checks = {}

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version()")
                row = cursor.fetchone()
            checks["database"] = {"status": "ok", "version": row[0] if row else "unknown"}
        except Exception as e:
            checks["database"] = {"status": "error", "message": str(e)}

        try:
            cache.set("health_check", "ok", timeout=5)
            checks["redis"] = {"status": "ok"}
        except Exception as e:
            checks["redis"] = {"status": "error", "message": str(e)}

        overall = "ok" if all(c.get("status") == "ok" for c in checks.values()) else "degraded"
        return JsonResponse({"status": overall, "services": checks})
