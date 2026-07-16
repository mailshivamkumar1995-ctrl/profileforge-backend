"""
Configuration and secrets validation for ProfileForge AI.

This module validates that all required environment variables are present
and meet minimum security requirements on application startup.

Called from Django's AppConfig.ready() or manage.py startup.
"""
import logging
import os
from typing import NamedTuple

logger = logging.getLogger(__name__)


class ConfigError(NamedTuple):
    variable: str
    message: str
    severity: str  # "critical" | "warning"


def validate_secrets() -> list[ConfigError]:
    """
    Validate all required secrets and return a list of errors.

    Critical errors should prevent application startup in production.
    Warnings should be logged but not block startup in development.
    """
    errors: list[ConfigError] = []
    from django.conf import settings

    # ── SECRET_KEY ────────────────────────────────────────────────────────────
    secret_key = getattr(settings, "SECRET_KEY", "")
    if not secret_key:
        errors.append(ConfigError("SECRET_KEY", "SECRET_KEY must be set", "critical"))
    elif len(secret_key) < 50:
        errors.append(ConfigError(
            "SECRET_KEY",
            f"SECRET_KEY is too short ({len(secret_key)} chars). Minimum: 50 chars.",
            "critical",
        ))
    elif secret_key in ("insecure-secret-key", "change-me", "django-insecure"):
        errors.append(ConfigError("SECRET_KEY", "SECRET_KEY appears to be a default/insecure value", "critical"))

    # ── Database URL ──────────────────────────────────────────────────────────
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url and not getattr(settings, "DEBUG", False):
        errors.append(ConfigError("DATABASE_URL", "DATABASE_URL must be set in production", "critical"))

    # ── JWT settings ──────────────────────────────────────────────────────────
    jwt_settings = getattr(settings, "SIMPLE_JWT", {})
    access_lifetime = jwt_settings.get("ACCESS_TOKEN_LIFETIME")
    if access_lifetime:
        minutes = access_lifetime.total_seconds() / 60
        if minutes > 60:
            errors.append(ConfigError(
                "JWT_ACCESS_TOKEN_LIFETIME_MINUTES",
                f"Access token lifetime is {int(minutes)}m. Recommended: ≤ 15m for security.",
                "warning",
            ))

    # ── AI API Keys ───────────────────────────────────────────────────────────
    ai_provider = getattr(settings, "AI_PROVIDER", "openai")
    if ai_provider == "openai":
        key = getattr(settings, "OPENAI_API_KEY", "")
        if not key:
            errors.append(ConfigError("OPENAI_API_KEY", "AI_PROVIDER=openai but OPENAI_API_KEY is not set", "warning"))
    elif ai_provider == "anthropic":
        key = getattr(settings, "ANTHROPIC_API_KEY", "")
        if not key:
            errors.append(ConfigError("ANTHROPIC_API_KEY", "AI_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set", "warning"))

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
    if "*" in cors_origins:
        errors.append(ConfigError(
            "CORS_ALLOWED_ORIGINS",
            "CORS_ALLOWED_ORIGINS contains '*' — this allows all origins. Set explicit origins.",
            "critical" if not getattr(settings, "DEBUG", False) else "warning",
        ))

    # ── ALLOWED_HOSTS ────────────────────────────────────────────────────────
    allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])
    if "*" in allowed_hosts and not getattr(settings, "DEBUG", False):
        errors.append(ConfigError(
            "ALLOWED_HOSTS",
            "ALLOWED_HOSTS contains '*' in non-debug mode. Set explicit hosts.",
            "critical",
        ))

    # ── Storage credentials ──────────────────────────────────────────────────
    storage_backend = getattr(settings, "STORAGE_BACKEND", "")
    if storage_backend in ("s3", "minio"):
        if not getattr(settings, "AWS_ACCESS_KEY_ID", ""):
            errors.append(ConfigError(
                "AWS_ACCESS_KEY_ID / MINIO_ACCESS_KEY",
                f"STORAGE_BACKEND={storage_backend} but storage access key is not set",
                "warning",
            ))

    return errors


def assert_production_config():
    """
    Run validation and raise RuntimeError for any critical errors in production.
    Logs warnings for non-critical issues.

    Call this from settings or AppConfig.ready() in production.
    """
    from django.conf import settings

    if getattr(settings, "DEBUG", False):
        logger.debug("Config validation skipped in DEBUG mode")
        return

    errors = validate_secrets()
    critical_errors = [e for e in errors if e.severity == "critical"]
    warnings = [e for e in errors if e.severity == "warning"]

    for w in warnings:
        logger.warning("Config warning [%s]: %s", w.variable, w.message)

    if critical_errors:
        messages = "\n".join(f"  [{e.variable}] {e.message}" for e in critical_errors)
        raise RuntimeError(
            f"Critical configuration errors found — application cannot start:\n{messages}"
        )
