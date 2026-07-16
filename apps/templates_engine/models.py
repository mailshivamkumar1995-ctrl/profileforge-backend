import uuid
from django.db import models
from django.utils import timezone


class TemplateType(models.TextChoices):
    RESUME = "resume", "Resume"
    COVER_LETTER = "cover_letter", "Cover Letter"
    PORTFOLIO = "portfolio", "Portfolio"


class TemplateCategory(models.TextChoices):
    ATS = "ats", "ATS"
    EXECUTIVE = "executive", "Executive"
    PROFESSIONAL = "professional", "Professional"
    TECHNICAL = "technical", "Technical"
    CORPORATE = "corporate", "Corporate"
    ACADEMIC = "academic", "Academic"
    ENGINEERING = "engineering", "Engineering"
    MANAGEMENT = "management", "Management"
    CREATIVE = "creative", "Creative"
    GENERAL = "general", "General"
    MINIMAL = "minimal", "Minimal"
    MODERN = "modern", "Modern"
    TERMINAL = "terminal", "Terminal"


class Template(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=TemplateType.choices)
    category = models.CharField(max_length=20, choices=TemplateCategory.choices)
    version = models.CharField(max_length=20, default="1.0")
    is_ats_optimized = models.BooleanField(default=False)
    is_single_page = models.BooleanField(default=True)
    is_premium = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    thumbnail_path = models.CharField(max_length=500, blank=True)
    description = models.TextField(blank=True)
    preview_data = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "templates"
        indexes = [
            models.Index(fields=["type", "is_active"]),
            models.Index(fields=["slug"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.type})"
