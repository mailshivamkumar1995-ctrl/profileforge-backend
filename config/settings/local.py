"""Local development settings — safe for production Docker image (no dev extras)."""
from .base import *  # noqa

DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
LOGGING["loggers"]["apps"]["level"] = "DEBUG"

# Local uses plain redis:// (in-cluster) — SSL cert requirements don't apply.
CELERY_BROKER_USE_SSL = None
CELERY_REDIS_BACKEND_USE_SSL = None

# Fail fast if Redis is unreachable so the request thread (and daemon threads)
# don't hang for OS-default TCP timeout (~60-120 s).
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "socket_timeout": 5,
    "socket_connect_timeout": 3,
}
