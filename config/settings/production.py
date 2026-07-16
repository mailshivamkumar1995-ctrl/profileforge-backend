from .base import *  # noqa
from decouple import config

DEBUG = False

# FINDING-012: assert DEBUG is never accidentally True in production
assert not DEBUG, "DEBUG must be False in production"

# Security headers
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SESSION_COOKIE_SAMESITE = "Strict"  # FINDING-009
CSRF_COOKIE_SAMESITE = "Strict"

# ─── Content Security Policy (SEC-004) ────────────────────────────────────────
# django-csp reads these settings and adds a Content-Security-Policy header
# to every response via csp.middleware.CSPMiddleware (wired in base.py).
#
# 'unsafe-inline' is removed from style-src; use inline nonces where needed.
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'",)          # no 'unsafe-inline' — use nonces for inline styles
CSP_IMG_SRC = ("'self'", "data:", "https:")
CSP_FONT_SRC = ("'self'", "https://fonts.gstatic.com")
CSP_CONNECT_SRC = ("'self'",)
CSP_OBJECT_SRC = ("'none'",)         # disallow Flash, plugins
CSP_FRAME_ANCESTORS = ("'none'",)    # reinforces X-Frame-Options: DENY
CSP_BASE_URI = ("'self'",)
CSP_FORM_ACTION = ("'self'",)
CSP_REPORT_URI = config("CSP_REPORT_URI", default="")   # optional: pipe to sentry/report-uri

# Sentry
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment="production",
    )

# Production logging: structured JSON
LOGGING["handlers"]["console"]["formatter"] = "json"
