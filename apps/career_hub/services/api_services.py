from decimal import Decimal, InvalidOperation
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.career_hub.models import Job, JobRecommendation, ResumeMatchScore, UserJob


# --- JOB SERVICES ---

def get_job_by_id(job_id: str) -> Job:
    try:
        return Job.objects.select_related("source").get(
            pk=job_id, is_active=True, is_private=False, deleted_at__isnull=True
        )
    except Job.DoesNotExist:
        raise NotFound("Job not found.")


# --- USER JOB (SAVED JOB) SERVICES ---

def save_user_job(user, job_id: str) -> tuple[UserJob, bool]:
    job = get_job_by_id(job_id)
    user_job, created = UserJob.objects.get_or_create(
        user=user,
        job=job,
        defaults={"status": UserJob.Status.SAVED},
    )
    user_job.job = job
    return user_job, created


def unsave_user_job(user, job_id: str) -> None:
    deleted_count, _ = UserJob.objects.filter(
        user=user, job_id=job_id
    ).delete()
    if deleted_count == 0:
        raise NotFound("Saved job not found.")


def get_saved_jobs_for_user(user):
    return (
        UserJob.objects.filter(user=user)
        .select_related("job__source")
        .order_by("-created_at")
    )


# --- RECOMMENDATION SERVICES ---

def get_user_recommendations(user, show_dismissed: bool):
    now = timezone.now()
    qs = (
        JobRecommendation.objects
        .filter(user=user)
        .filter(Q(expires_at__gte=now) | Q(expires_at__isnull=True))
    )
    if not show_dismissed:
        qs = qs.filter(is_dismissed=False)
    return qs.select_related("job__source").order_by("-score", "-generated_at")


def get_recommendation_by_id(user, rec_id: str) -> JobRecommendation:
    try:
        return JobRecommendation.objects.select_related("job__source").get(
            pk=rec_id, user=user
        )
    except JobRecommendation.DoesNotExist:
        raise NotFound("Recommendation not found.")


def dismiss_recommendation(user, rec_id: str) -> JobRecommendation:
    try:
        rec = JobRecommendation.objects.get(pk=rec_id, user=user)
    except JobRecommendation.DoesNotExist:
        raise NotFound("Recommendation not found.")
    rec.is_dismissed = True
    rec.save(update_fields=["is_dismissed"])
    return rec


# --- MATCH SCORE SERVICES ---

def get_match_scores_for_user(user, min_score: str = None):
    qs = (
        ResumeMatchScore.objects
        .filter(user=user)
        .select_related("job__source")
        .order_by("-overall_score", "-created_at")
    )

    if min_score is not None:
        try:
            qs = qs.filter(overall_score__gte=Decimal(min_score))
        except (InvalidOperation, ValueError):
            raise ValidationError({"min_score": "Must be a valid decimal value."})
    return qs


def get_match_score_by_id(user, score_id: str) -> ResumeMatchScore:
    try:
        return ResumeMatchScore.objects.select_related("job__source").get(
            pk=score_id, user=user
        )
    except ResumeMatchScore.DoesNotExist:
        raise NotFound("Match score not found.")


def get_match_score_for_job(user, job_id: str) -> ResumeMatchScore:
    try:
        return ResumeMatchScore.objects.select_related("job__source").get(
            job_id=job_id, user=user
        )
    except ResumeMatchScore.DoesNotExist:
        raise NotFound("No match score found for this job.")
