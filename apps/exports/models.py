import uuid
from django.db import models
from django.utils import timezone
from apps.authentication.models import User
from apps.templates_engine.models import Template


class ExportResourceType(models.TextChoices):
    RESUME = "resume", "Resume"
    COVER_LETTER = "cover_letter", "Cover Letter"
    PORTFOLIO = "portfolio", "Portfolio"


class ExportFormat(models.TextChoices):
    PDF = "pdf", "PDF"
    DOCX = "docx", "DOCX"


class ExportStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class ExportJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="export_jobs")
    resource_type = models.CharField(max_length=20, choices=ExportResourceType.choices)
    resource_id = models.UUIDField()
    format = models.CharField(max_length=10, choices=ExportFormat.choices)
    template = models.ForeignKey(
        Template, on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(
        max_length=20, choices=ExportStatus.choices, default=ExportStatus.QUEUED
    )
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    download_url = models.TextField(blank=True)
    url_expires_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "export_jobs"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["resource_type", "resource_id"]),
        ]

    def __str__(self):
        return f"Export {self.resource_type} {self.resource_id} as {self.format}"
