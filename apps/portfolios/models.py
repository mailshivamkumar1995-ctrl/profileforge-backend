import uuid
from django.db import models
from django.utils import timezone
from apps.authentication.models import User
from apps.profiles.models import UserProfile
from apps.templates_engine.models import Template


SECTION_DEFAULTS = {
    "hero":           {"enabled": True,  "order": 0},
    "about":          {"enabled": True,  "order": 1},
    "experience":     {"enabled": True,  "order": 2},
    "education":      {"enabled": True,  "order": 3},
    "skills":         {"enabled": True,  "order": 4},
    "projects":       {"enabled": True,  "order": 5},
    "certifications": {"enabled": True,  "order": 6},
    "achievements":   {"enabled": False, "order": 7},
    "publications":   {"enabled": False, "order": 8},
    "contact":        {"enabled": True,  "order": 9},
}


class AnalyticsProvider(models.TextChoices):
    NONE = "none", "None"
    GOOGLE_ANALYTICS = "google_analytics", "Google Analytics"
    PLAUSIBLE = "plausible", "Plausible"
    POSTHOG = "posthog", "PostHog"


class Portfolio(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="portfolio")
    profile = models.OneToOneField(
        UserProfile, on_delete=models.CASCADE, related_name="portfolio"
    )
    theme = models.ForeignKey(
        Template, on_delete=models.PROTECT, related_name="portfolios", null=True, blank=True
    )
    theme_settings = models.JSONField(default=dict, blank=True)
    section_settings = models.JSONField(default=dict, blank=True)
    custom_domain = models.CharField(max_length=255, blank=True)
    is_published = models.BooleanField(default=False)
    is_public = models.BooleanField(default=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    seo_title = models.CharField(max_length=200, blank=True)
    seo_description = models.TextField(blank=True)
    seo_keywords = models.CharField(max_length=500, blank=True)
    og_image_path = models.CharField(max_length=500, blank=True)
    analytics_provider = models.CharField(
        max_length=30, choices=AnalyticsProvider.choices, default=AnalyticsProvider.NONE
    )
    analytics_id = models.CharField(max_length=200, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    last_generated_at = models.DateTimeField(null=True, blank=True)
    static_site_path = models.CharField(max_length=500, blank=True)
    current_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "portfolios"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_published", "is_public"]),
        ]

    def __str__(self):
        return f"Portfolio of {self.user.username}"

    def get_section_settings(self) -> dict:
        merged = dict(SECTION_DEFAULTS)
        for key, val in (self.section_settings or {}).items():
            if key in merged:
                merged[key] = {**merged[key], **val}
        return merged

    def publish(self):
        self.is_published = True
        self.published_at = timezone.now()
        self.save(update_fields=["is_published", "published_at", "updated_at"])

    def unpublish(self):
        self.is_published = False
        self.save(update_fields=["is_published", "updated_at"])

    @property
    def public_url(self) -> str:
        if self.custom_domain:
            return f"https://{self.custom_domain}"
        return f"/u/{self.user.username}"


class PortfolioVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    theme_slug = models.CharField(max_length=100, blank=True)
    section_settings = models.JSONField(default=dict, blank=True)
    rendered_html = models.TextField(blank=True)
    change_summary = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="portfolio_versions_created"
    )

    class Meta:
        db_table = "portfolio_versions"
        unique_together = [("portfolio", "version_number")]
        ordering = ["-version_number"]
        indexes = [
            models.Index(fields=["portfolio", "version_number"]),
        ]

    def __str__(self):
        return f"Portfolio {self.portfolio.slug} v{self.version_number}"
