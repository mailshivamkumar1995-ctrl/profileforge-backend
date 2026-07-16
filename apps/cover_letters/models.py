import uuid
from django.db import models
from django.utils import timezone
from apps.authentication.models import User
from apps.profiles.models import UserProfile
from apps.resumes.models import Resume
from apps.templates_engine.models import Template


class CoverLetterTone(models.TextChoices):
    PROFESSIONAL = "professional", "Professional"
    EXECUTIVE = "executive", "Executive"
    FRIENDLY = "friendly", "Friendly"
    TECHNICAL = "technical", "Technical"
    STARTUP = "startup", "Startup"
    FORMAL = "formal", "Formal"


class CoverLetterStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class CoverLetter(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cover_letters")
    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="cover_letters"
    )
    resume = models.ForeignKey(
        Resume, on_delete=models.SET_NULL, null=True, blank=True, related_name="cover_letters"
    )
    title = models.CharField(max_length=200)
    template = models.ForeignKey(
        Template, on_delete=models.PROTECT, related_name="cover_letters", null=True, blank=True
    )
    company_name = models.CharField(max_length=200)
    job_title = models.CharField(max_length=200)
    hiring_manager_name = models.CharField(max_length=200, blank=True)
    hiring_manager_title = models.CharField(max_length=200, blank=True)
    company_address = models.JSONField(default=dict, blank=True)
    tone = models.CharField(
        max_length=20, choices=CoverLetterTone.choices, default=CoverLetterTone.PROFESSIONAL
    )
    body_content = models.TextField(blank=True)
    job_description = models.TextField(blank=True)
    ai_generated = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20, choices=CoverLetterStatus.choices, default=CoverLetterStatus.DRAFT
    )
    current_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cover_letters"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.title} for {self.company_name}"


class CoverLetterVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cover_letter = models.ForeignKey(
        CoverLetter, on_delete=models.CASCADE, related_name="versions"
    )
    version_number = models.PositiveIntegerField()
    content_snapshot = models.TextField()
    rendered_html = models.TextField(blank=True)
    change_summary = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="cover_letter_versions_created"
    )

    class Meta:
        db_table = "cover_letter_versions"
        unique_together = [("cover_letter", "version_number")]
        ordering = ["-version_number"]
        indexes = [
            models.Index(fields=["cover_letter", "version_number"]),
        ]

    def __str__(self):
        return f"{self.cover_letter.title} v{self.version_number}"
