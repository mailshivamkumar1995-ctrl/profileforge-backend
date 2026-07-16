"""
Test settings — fast, isolated, no external services required.
SQLite :memory: database; local memory cache; synchronous Celery.
"""
from .base import *  # noqa

# ─── Database ─────────────────────────────────────────────────────────────────
# In-process SQLite — zero setup, zero cleanup, never touches Neon
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# ─── Cache ────────────────────────────────────────────────────────────────────
# DummyCache: never stores anything — effectively disables throttle counters
# AND avoids any Redis dependency in tests.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# Sessions can't use cached_db with locmem in the same way; use plain db
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# ─── Celery ───────────────────────────────────────────────────────────────────
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
# memory:// doesn't use SSL — disable the SSL dicts set in base.py
CELERY_BROKER_USE_SSL = None
CELERY_REDIS_BACKEND_USE_SSL = None

# ─── Auth ─────────────────────────────────────────────────────────────────────
# Fast hashing — tests don't need security-grade KDF
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# ─── API ──────────────────────────────────────────────────────────────────────
# No throttling in tests
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []

# ─── Email ────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ─── Encryption ───────────────────────────────────────────────────────────────
# Stable test key — safe to commit (test-only, not a production key)
FIELD_ENCRYPTION_KEY = "kPF3eqbIk0bJqNH1WJ_gu75MTlPdJa00CWwmqQNMuWo="

# ─── Logging ──────────────────────────────────────────────────────────────────
# Silence noisy loggers during test runs
LOGGING["root"]["level"] = "ERROR"

DEBUG = True
SECRET_KEY = "test-secret-key-not-for-production-use-only"
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True

# ─── Career Hub — Job Providers ───────────────────────────────────────────────
# Dummy values — all provider HTTP calls are mocked in tests
ADZUNA_APP_ID = "test-app-id"
ADZUNA_APP_KEY = "test-app-key"
