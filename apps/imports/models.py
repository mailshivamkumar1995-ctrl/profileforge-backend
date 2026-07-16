import uuid
from django.db import models
from django.utils import timezone
from apps.authentication.models import User


class ImportFileType(models.TextChoices):
    PDF = "pdf", "PDF"
    DOCX = "docx", "DOCX"
    TXT = "txt", "TXT"
    MD = "md", "Markdown"


class ImportStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    REVIEW_REQUIRED = "review_required", "Review Required"
    APPLIED = "applied", "Applied"
    FAILED = "failed", "Failed"


class ImportJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="import_jobs")
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10, choices=ImportFileType.choices)
    file_path = models.CharField(max_length=500)
    file_size = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=ImportStatus.choices, default=ImportStatus.PENDING
    )
    parsed_data = models.JSONField(default=dict, blank=True)
    mapping_review = models.JSONField(default=dict, blank=True)
    confidence_scores = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "import_jobs"
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Import: {self.original_filename} ({self.status})"
