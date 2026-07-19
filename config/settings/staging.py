from .base import *  # noqa
from decouple import config

DEBUG = False

# FINDING: allow Prometheus's Pod-IP-based scrape requests to /metrics without
# permanently widening ALLOWED_HOSTS — each Pod learns its own IP via the
# Kubernetes Downward API and allows exactly that one value.
POD_IP = config("POD_IP", default="")
if POD_IP:
    ALLOWED_HOSTS = ALLOWED_HOSTS + [POD_IP]

# Slightly relaxed security for staging (no HSTS preload)
SECURE_HSTS_SECONDS = 3600
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REDIRECT_EXEMPT = [r"^metrics/?$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# Sentry (staging environment)
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.5,
        send_default_pii=False,
        environment="staging",
    )
