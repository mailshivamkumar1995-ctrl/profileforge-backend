from django.contrib import admin
from django.conf import settings
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),

    # API v1
    path("api/v1/", include([
        path("auth/", include("apps.authentication.urls")),
        path("profiles/", include("apps.profiles.urls")),
        path("resumes/", include("apps.resumes.urls")),
        path("cover-letters/", include("apps.cover_letters.urls")),
        path("portfolios/", include("apps.portfolios.urls")),
        path("templates/", include("apps.templates_engine.urls")),
        path("imports/", include("apps.imports.urls")),
        path("exports/", include("apps.exports.urls")),
        path("ai/", include("apps.ai_engine.urls")),
        path("public/", include("apps.portfolios.public_urls")),
        path("career-hub/", include("apps.career_hub.urls")),
    ])),

    # Health checks
    path("health/", include("core.health_urls")),

    # Metrics (Prometheus)
    path("", include("django_prometheus.urls")),
]

# API documentation — never expose in production; opt-in via SHOW_API_DOCS=True for staging
if settings.DEBUG or getattr(settings, "SHOW_API_DOCS", False):
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    ]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls)),
    ]
