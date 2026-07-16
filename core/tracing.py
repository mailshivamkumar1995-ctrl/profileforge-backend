﻿"""
OpenTelemetry distributed tracing configuration for ProfileForge AI.

Instruments:
  - Django HTTP requests
  - Database queries (psycopg2)
  - Redis commands
  - Celery tasks
  - HTTP client calls (requests, httpx)
  - Custom AI API spans

Usage:
  Called from WSGI/ASGI entrypoint before Django loads.
  In gunicorn: post_fork hook calls configure_tracing().
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def configure_tracing() -> None:
    """Initialize OpenTelemetry with OTLP exporter to Tempo."""
    if not getattr(settings, "OTEL_ENABLED", False):
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        resource = Resource.create({
            SERVICE_NAME: "profileforge-backend",
            SERVICE_VERSION: getattr(settings, "APP_VERSION", "unknown"),
            "deployment.environment": settings.ENVIRONMENT,
        })

        provider = TracerProvider(resource=resource)

        otlp_endpoint = getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "http://tempo:4317")
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)

        # Instrument all libraries
        DjangoInstrumentor().instrument(
            tracer_provider=provider,
            request_hook=_django_request_hook,
            response_hook=_django_response_hook,
        )
        Psycopg2Instrumentor().instrument(tracer_provider=provider, enable_commenter=True)
        RedisInstrumentor().instrument(tracer_provider=provider)
        CeleryInstrumentor().instrument(tracer_provider=provider)
        RequestsInstrumentor().instrument(tracer_provider=provider)
        HTTPXClientInstrumentor().instrument(tracer_provider=provider)

        logger.info("OpenTelemetry tracing configured (endpoint: %s)", otlp_endpoint)

    except ImportError as e:
        logger.warning("OpenTelemetry packages not installed; tracing disabled: %s", e)
    except Exception as e:
        logger.error("Failed to configure OpenTelemetry: %s", e)


def _django_request_hook(span, request) -> None:
    """Enrich spans with ProfileForge-specific attributes."""
    if request.user and request.user.is_authenticated:
        span.set_attribute("app.user_id", str(request.user.id))
    span.set_attribute("app.path", request.path)


def _django_response_hook(span, request, response) -> None:
    span.set_attribute("http.response.status_code", response.status_code)


def get_tracer(name: str):
    """Get a tracer for the given instrumentation scope."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoopTracer()


class _NoopTracer:
    """Fallback when OTel is not installed."""

    class _NoopSpan:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def set_attribute(self, key, value):
            pass

        def record_exception(self, exc):
            pass

        def set_status(self, status):
            pass

    def start_as_current_span(self, name, **kwargs):
        return self._NoopSpan()
