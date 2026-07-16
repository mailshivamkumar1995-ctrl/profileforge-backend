import uuid

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils import timezone

from apps.authentication.models import User


class JobSource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "career_hub_job_source"

    def __str__(self):
        return self.name


class WorkType(models.TextChoices):
    REMOTE = "remote", "Remote"
    HYBRID = "hybrid", "Hybrid"
    ONSITE = "onsite", "Onsite"


class Job(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(JobSource, on_delete=models.PROTECT, related_name="jobs")
    external_id = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    company = models.CharField(max_length=200)
    description = models.CharField(max_length=2000)
    description_tsv = SearchVectorField(null=True)
    apply_url = models.URLField(max_length=500)
    city = models.CharField(max_length=100, blank=True)
    work_type = models.CharField(max_length=20, choices=WorkType.choices, default=WorkType.HYBRID)
    salary_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_currency = models.CharField(max_length=3, default="INR")
    posted_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_private = models.BooleanField(default=False)
    fetched_at = models.DateTimeField(default=timezone.now)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "career_hub_job"
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="uq_job_source_external",
            ),
        ]
        indexes = [
            GinIndex(fields=["description_tsv"], name="ch_job_tsv_gin_idx"),
            models.Index(fields=["city", "work_type", "is_active"], name="ch_job_city_wt_active_idx"),
            models.Index(fields=["posted_at", "is_active"], name="ch_job_posted_active_idx"),
        ]

    def __str__(self):
        return f"{self.title} at {self.company}"


class UserJob(models.Model):
    class Status(models.TextChoices):
        SAVED = "saved", "Saved"
        APPLIED = "applied", "Applied"
        REJECTED = "rejected", "Rejected"
        INTERVIEW = "interview", "Interview"
        OFFER = "offer", "Offer"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_jobs")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="user_jobs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SAVED)
    notes = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "career_hub_user_job"
        constraints = [
            models.UniqueConstraint(fields=["user", "job"], name="uq_user_job"),
        ]
        indexes = [
            models.Index(fields=["user", "status"], name="ch_userjob_status_idx"),
            models.Index(fields=["user", "created_at"], name="ch_userjob_created_idx"),
        ]

    def __str__(self):
        return f"{self.user_id} — {self.job_id} ({self.status})"


class Draft(models.Model):
    class DraftType(models.TextChoices):
        RESUME = "resume", "Resume"
        COVER_LETTER = "cover_letter", "Cover Letter"
        GENERAL = "general", "General"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="drafts")
    title = models.CharField(max_length=200)
    draft_type = models.CharField(max_length=20, choices=DraftType.choices, default=DraftType.RESUME)
    target_job = models.ForeignKey(
        Job, null=True, blank=True, on_delete=models.SET_NULL, related_name="targeted_drafts"
    )
    content = models.JSONField(default=dict, blank=True)
    profile_snapshot_hash = models.CharField(max_length=64, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "career_hub_draft"
        indexes = [
            models.Index(fields=["user", "deleted_at"], name="ch_draft_user_del_idx"),
            models.Index(fields=["user", "draft_type", "deleted_at"], name="ch_draft_user_type_del_idx"),
        ]

    def __str__(self):
        return f"{self.title} ({self.draft_type})"


class JobRecommendation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="job_recommendations")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="recommendations")
    score = models.DecimalField(max_digits=4, decimal_places=3)
    algorithm_version = models.CharField(max_length=20)
    generated_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_dismissed = models.BooleanField(default=False)
    score_breakdown = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "career_hub_job_recommendation"
        constraints = [
            models.UniqueConstraint(fields=["user", "job"], name="uq_recommendation_user_job"),
            models.CheckConstraint(
                check=models.Q(score__gte=0) & models.Q(score__lte=1),
                name="chk_recommendation_score_range",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_dismissed", "generated_at"], name="ch_rec_dismissed_idx"),
            models.Index(fields=["expires_at"], name="career_hub_rec_expires_idx"),
        ]

    def __str__(self):
        return f"Rec {self.user_id}:{self.job_id} score={self.score}"


class ResumeMatchScore(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="match_scores")
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="match_scores")
    overall_score = models.DecimalField(max_digits=4, decimal_places=3)
    skill_score = models.DecimalField(max_digits=5, decimal_places=4)
    experience_score = models.DecimalField(max_digits=5, decimal_places=4)
    keyword_score = models.DecimalField(max_digits=5, decimal_places=4)
    title_score = models.DecimalField(max_digits=5, decimal_places=4)
    education_score = models.DecimalField(max_digits=5, decimal_places=4)
    certification_score = models.DecimalField(max_digits=5, decimal_places=4)
    location_score = models.DecimalField(max_digits=5, decimal_places=4)
    salary_score = models.DecimalField(max_digits=5, decimal_places=4)
    skill_gaps = models.JSONField(default=dict)
    scoring_version = models.CharField(max_length=20)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "career_hub_resume_match_score"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "job"],
                name="uq_match_score_user_job",
            ),
            models.CheckConstraint(
                check=models.Q(overall_score__gte=0) & models.Q(overall_score__lte=1),
                name="chk_match_score_overall_range",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "overall_score"],
                name="ch_match_score_user_score_idx",
            ),
            models.Index(
                fields=["job", "overall_score"],
                name="ch_match_score_job_score_idx",
            ),
        ]

    def __str__(self):
        return f"MatchScore {self.user_id}:{self.job_id} score={self.overall_score}"
