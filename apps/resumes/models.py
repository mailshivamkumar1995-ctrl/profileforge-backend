import uuid
from django.db import models
from django.utils import timezone
from apps.authentication.models import User
from apps.profiles.models import UserProfile
from apps.templates_engine.models import Template


class ResumeStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class Resume(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="resumes")
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="resumes")
    title = models.CharField(max_length=200)
    template = models.ForeignKey(
        Template, on_delete=models.PROTECT, related_name="resumes", null=True, blank=True
    )
    template_settings = models.JSONField(default=dict, blank=True)
    custom_sections = models.JSONField(default=list, blank=True)
    is_primary = models.BooleanField(default=False)
    target_role = models.CharField(max_length=200, blank=True)
    target_company = models.CharField(max_length=200, blank=True)
    ats_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ats_analysis = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20, choices=ResumeStatus.choices, default=ResumeStatus.DRAFT
    )
    current_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "resumes"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.user.email})"

    def save(self, *args, **kwargs):
        # Ensure only one primary resume per user
        if self.is_primary:
            Resume.objects.filter(user=self.user, is_primary=True).exclude(pk=self.pk).update(
                is_primary=False
            )
        super().save(*args, **kwargs)


class ResumeVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resume = models.ForeignKey(Resume, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    change_summary = models.TextField(blank=True)
    rendered_html = models.TextField(blank=True)
    export_pdf_path = models.CharField(max_length=500, blank=True)
    export_docx_path = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="resume_versions_created"
    )

    class Meta:
        db_table = "resume_versions"
        unique_together = [("resume", "version_number")]
        ordering = ["-version_number"]
        indexes = [
            models.Index(fields=["resume", "version_number"]),
        ]

    def __str__(self):
        return f"Resume {self.resume.title} v{self.version_number}"
