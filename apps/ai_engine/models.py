import uuid
from django.db import models
from django.utils import timezone
from apps.authentication.models import User


class AIProvider(models.TextChoices):
    OPENAI = "openai", "OpenAI"
    ANTHROPIC = "anthropic", "Anthropic"
    GEMINI = "gemini", "Google Gemini"


class AIFeature(models.TextChoices):
    BULLET_ENHANCE = "bullet_enhance", "Bullet Enhancement"
    SUMMARY_GENERATE = "summary_generate", "Summary Generation"
    COVER_LETTER_GENERATE = "cover_letter_generate", "Cover Letter Generation"
    COVER_LETTER_REWRITE = "cover_letter_rewrite", "Cover Letter Rewrite"
    COVER_LETTER_IMPROVE_TONE = "cover_letter_improve_tone", "Cover Letter Tone Improvement"
    COVER_LETTER_IMPROVE_ATS = "cover_letter_improve_ats", "Cover Letter ATS Improvement"
    ATS_ANALYZE = "ats_analyze", "ATS Analysis"
    CONTENT_REWRITE = "content_rewrite", "Content Rewrite"
    JOB_MATCH = "job_match", "Job Description Matching"
    RESUME_BULLET_REWRITE = "resume_bullet_rewrite", "Resume Bullet Rewrite"
    RESUME_SUMMARY_OPTIMIZE = "resume_summary_optimize", "Resume Summary Optimization"


class AIUsageLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ai_usage_logs")
    feature = models.CharField(max_length=30, choices=AIFeature.choices)
    provider = models.CharField(max_length=20, choices=AIProvider.choices)
    model_name = models.CharField(max_length=100)
    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    success = models.BooleanField(default=True)
    error_code = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ai_usage_logs"
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["created_at"]),
        ]
