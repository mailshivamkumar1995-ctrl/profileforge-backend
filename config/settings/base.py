"""
ProfileForge AI — Base Django Settings
All environments inherit from this file.
"""
import os
from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost", cast=Csv())
ADMIN_URL = config("DJANGO_ADMIN_URL", default="admin/")
SHOW_API_DOCS = config("SHOW_API_DOCS", default=False, cast=bool)

# ─── Application ──────────────────────────────────────────────────────────────

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "csp",                 # SEC-004: Content Security Policy enforcement
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",
    "django_prometheus",
]

LOCAL_APPS = [
    "apps.authentication",
    "apps.profiles",
    "apps.resumes",
    "apps.cover_letters",
    "apps.portfolios",
    "apps.templates_engine",
    "apps.imports",
    "apps.exports",
    "apps.ai_engine",
    "apps.notifications",
    "apps.career_hub",
    "core",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ─── Middleware ────────────────────────────────────────────────────────────────

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",              # SEC-004: enforce Content-Security-Policy header
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.RequestIDMiddleware",
    "core.middleware.AuditLogMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ─── Database ─────────────────────────────────────────────────────────────────

import dj_database_url

DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL", default="postgresql://postgres:postgres@localhost:5432/resumeforge_dev"),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Auth ─────────────────────────────────────────────────────────────────────

AUTH_USER_MODEL = "authentication.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ─── REST Framework ───────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # SEC-002: custom backend that invalidates tokens issued before password change
        "core.authentication.PasswordAwareJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("RATE_LIMIT_ANON", default="60/minute"),
        "user": config("RATE_LIMIT_USER", default="300/minute"),
        "ai": config("RATE_LIMIT_AI", default="20/minute"),
        "login": config("RATE_LIMIT_LOGIN", default="10/minute"),
        "registration": config("RATE_LIMIT_REGISTRATION", default="5/minute"),
        "upload": config("RATE_LIMIT_UPLOAD", default="10/minute"),
        "export": config("RATE_LIMIT_EXPORT", default="20/minute"),
        "password_reset": config("RATE_LIMIT_PASSWORD_RESET", default="3/minute"),
        "career_hub_search": config("RATE_LIMIT_CAREER_HUB_SEARCH", default="60/minute"),
    },
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# ─── JWT ──────────────────────────────────────────────────────────────────────

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=15, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.authentication.serializers.CustomTokenObtainPairSerializer",
}

# ─── CORS ─────────────────────────────────────────────────────────────────────

CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="http://localhost:3000", cast=Csv())
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "x-request-id",
    "x-csrftoken",
]

# ─── Redis / Cache ─────────────────────────────────────────────────────────────
# ACA-006: three separate Redis logical databases to prevent key namespace
# collisions and memory contention between cache, Celery broker, and results.
#
#   DB 0 — Django cache (throttle counters, session data, view cache)
#   DB 1 — Celery broker (task queue, kombu messages)
#   DB 2 — Celery result backend (task state and return values)
#
# In production each env var is set to its own endpoint/database in
# the K8s ConfigMap (helm/backend/templates/configmap.yaml).
# In local dev all three default to the same Redis on different logical DBs.

REDIS_BASE_URL = config("REDIS_URL", default="redis://localhost:6379")
REDIS_CACHE_URL = config("REDIS_CACHE_URL", default=f"{REDIS_BASE_URL}/0")
REDIS_BROKER_URL = config("REDIS_BROKER_URL", default=f"{REDIS_BASE_URL}/1")
REDIS_RESULT_URL = config("REDIS_RESULT_URL", default=f"{REDIS_BASE_URL}/2")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_CACHE_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "CONNECTION_POOL_KWARGS": {"max_connections": 50},
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            # SEC-005: IGNORE_EXCEPTIONS removed. Redis errors propagate so
            # throttle classes can detect the outage and fail closed.
        },
        "KEY_PREFIX": "profileforge",
        "TIMEOUT": 300,
    }
}

# CQ-013: use cached_db so sessions survive a Redis outage
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_CACHE_ALIAS = "default"

# ─── Celery ───────────────────────────────────────────────────────────────────

import ssl

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=REDIS_BROKER_URL)
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=REDIS_RESULT_URL)
# Required by Celery 5.4+ when using rediss:// — must explicitly declare cert requirements
CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": ssl.CERT_REQUIRED} if CELERY_BROKER_URL.startswith("rediss://") else None
CELERY_REDIS_BACKEND_USE_SSL = {"ssl_cert_reqs": ssl.CERT_REQUIRED} if CELERY_RESULT_BACKEND.startswith("rediss://") else None
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 600  # 10 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 540  # 9 minutes
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True

CELERY_TASK_QUEUES = {
    "default": {"routing_key": "default"},
    "resume": {"routing_key": "resume"},
    "portfolio": {"routing_key": "portfolio"},
    "imports": {"routing_key": "imports"},
    "ai": {"routing_key": "ai"},
    "notifications": {"routing_key": "notifications"},
    "career_hub": {"routing_key": "career_hub"},
}

CELERY_TASK_DEFAULT_QUEUE = "default"

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "career-hub-sync-jobs": {
        "task": "career_hub.sync_jobs",
        "schedule": crontab(hour="*/6"),          # 00:00, 06:00, 12:00, 18:00 UTC
    },
    "career-hub-fan-out-recommendations": {
        "task": "career_hub.fan_out_recommendations",
        "schedule": crontab(minute=0, hour="1,7,13,19"),  # 01:00, 07:00, 13:00, 19:00 UTC (1h after sync)
    },
}

# ─── Storage ──────────────────────────────────────────────────────────────────

STORAGE_BACKEND = config("STORAGE_BACKEND", default="minio")

# S3/MinIO settings
AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID", default=config("MINIO_ACCESS_KEY", default=""))
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default=config("MINIO_SECRET_KEY", default=""))
AWS_STORAGE_BUCKET_NAME = config("AWS_S3_BUCKET_NAME", default=config("MINIO_BUCKET_NAME", default="profileforge-dev"))
AWS_S3_REGION_NAME = config("AWS_S3_REGION", default="us-east-1")
AWS_S3_ENDPOINT_URL = config("MINIO_ENDPOINT", default=None)
if AWS_S3_ENDPOINT_URL and not AWS_S3_ENDPOINT_URL.startswith("http"):
    minio_ssl = config("MINIO_USE_SSL", default=False, cast=bool)
    scheme = "https" if minio_ssl else "http"
    AWS_S3_ENDPOINT_URL = f"{scheme}://{AWS_S3_ENDPOINT_URL}"

# External endpoint for pre-signed URL generation (browser-accessible host)
# Set MINIO_EXTERNAL_ENDPOINT to the host:port reachable from the browser.
# Defaults to the internal endpoint when not set (single-node or direct-access deployments).
AWS_S3_EXTERNAL_ENDPOINT_URL = config("MINIO_EXTERNAL_ENDPOINT", default=None)
if AWS_S3_EXTERNAL_ENDPOINT_URL and not AWS_S3_EXTERNAL_ENDPOINT_URL.startswith("http"):
    minio_ssl = config("MINIO_USE_SSL", default=False, cast=bool)
    scheme = "https" if minio_ssl else "http"
    AWS_S3_EXTERNAL_ENDPOINT_URL = f"{scheme}://{AWS_S3_EXTERNAL_ENDPOINT_URL}"

# ─── Email ────────────────────────────────────────────────────────────────────

EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="localhost")
EMAIL_PORT = config("EMAIL_PORT", default=1025, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@profileforge.io")
PASSWORD_RESET_TIMEOUT = config("PASSWORD_RESET_TIMEOUT", default=86400, cast=int)  # 24 hours

# ─── Field-level encryption (SEC-001) ────────────────────────────────────────
# Fernet key for encrypting sensitive DB fields (OAuth tokens, etc.).
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Store in AWS Secrets Manager; inject as FIELD_ENCRYPTION_KEY env var.
# Supports key rotation: set to comma-separated "new_key,old_key" — new key used for writes.
FIELD_ENCRYPTION_KEY = config("FIELD_ENCRYPTION_KEY", default="")

# ─── AI ───────────────────────────────────────────────────────────────────────

AI_PROVIDER = config("AI_PROVIDER", default="openai")
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
ANTHROPIC_API_KEY = config("ANTHROPIC_API_KEY", default="")
GOOGLE_AI_API_KEY = config("GOOGLE_AI_API_KEY", default="")

# ─── Career Hub — Job Providers ───────────────────────────────────────────────

ADZUNA_APP_ID = config("ADZUNA_API_ID", default="")
ADZUNA_APP_KEY = config("ADZUNA_API_KEY", default="")

# ─── Upload Limits (FINDING-003) ─────────────────────────────────────────────

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024   # 5 MB for JSON bodies
FILE_UPLOAD_MAX_MEMORY_SIZE = 1 * 1024 * 1024   # 1 MB in-memory threshold
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100              # Prevent field flooding

# ─── Static / Media ───────────────────────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ─── i18n ─────────────────────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

CELERY_BEAT_SCHEDULE = {
    "sync_jobs_daily": {
        "task": "career_hub.sync_jobs",
        "schedule": 86400.0,  # every 24 hours
    },
}

# ─── Security / Auth ─────────────────────────────────────────────────────────────

USE_I18N = True
USE_TZ = True

# ─── Frontend URL ─────────────────────────────────────────────────────────────

FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000")

# ─── API Documentation (drf-spectacular) ──────────────────────────────────────

SPECTACULAR_SETTINGS = {
    "TITLE": "ProfileForge AI API",
    "DESCRIPTION": "Enterprise-grade Resume, Cover Letter, and Portfolio generation API",
    "VERSION": "1.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]",
    "COMPONENT_SPLIT_REQUEST": True,
}

# ─── Logging ──────────────────────────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(request_id)s",
        },
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "filters": {
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
