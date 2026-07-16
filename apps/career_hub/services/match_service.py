"""
Resume match score service — P7-1B persistence and orchestration layer.

Bridges the pure scoring engine (match_scoring.py) and the Django ORM.
All ORM operations live here; the engine remains side-effect-free.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction

from apps.career_hub.models import Job, ResumeMatchScore
from apps.career_hub.services.match_scoring import (
    MATCH_ALGORITHM_VERSION,
    compute_resume_match_score,
)
from apps.profiles.models import UserProfile


def _build_scoring_inputs(profile: UserProfile) -> dict:
    """Extract profile data into keyword arguments for compute_resume_match_score().

    Uses pre-fetched querysets — callers must prefetch skills, work_experiences,
    educations, certifications, and projects before passing the profile.
    """
    return dict(
        skills=list(profile.skills.all()),
        work_experiences=list(profile.work_experiences.all()),
        educations=list(profile.educations.all()),
        certifications=list(profile.certifications.all()),
        projects=list(profile.projects.all()),
        headline=profile.headline or "",
        professional_summary=profile.professional_summary or "",
        ats_keywords=profile.ats_keywords or [],
        target_role=getattr(profile, "target_role", "") or "",
        custom_section_texts=[],
        user_city=(profile.location or {}).get("city", "") or "",
        expected_salary_min=None,
        expected_salary_max=None,
    )


def _fetch_profile(user) -> UserProfile:
    """Fetch the user's profile with all scoring-related relations prefetched."""
    return (
        UserProfile.objects
        .prefetch_related(
            "skills",
            "work_experiences",
            "educations",
            "certifications",
            "projects",
        )
        .get(user=user)
    )


def _explanation_to_defaults(explanation) -> dict:
    """Convert a MatchExplanation into model field values."""
    bd = explanation.breakdown
    return {
        "overall_score": explanation.total,
        "skill_score": Decimal(str(bd["skill"])),
        "experience_score": Decimal(str(bd["experience"])),
        "keyword_score": Decimal(str(bd["keyword"])),
        "title_score": Decimal(str(bd["title"])),
        "education_score": Decimal(str(bd["education"])),
        "certification_score": Decimal(str(bd["certification"])),
        "location_score": Decimal(str(bd["location"])),
        "salary_score": Decimal(str(bd["salary"])),
        "skill_gaps": explanation.skill_gaps,
        "scoring_version": MATCH_ALGORITHM_VERSION,
    }


def generate_match_score(user, job: Job) -> ResumeMatchScore:
    """Compute and persist a match score for a single (user, job) pair.

    Idempotent: a second call refreshes the existing score rather than
    creating a duplicate. Raises UserProfile.DoesNotExist when the user
    has no profile. The returned instance has `job` pre-attached to avoid
    an extra DB query in serializers.
    """
    profile = _fetch_profile(user)
    inputs = _build_scoring_inputs(profile)
    explanation = compute_resume_match_score(**inputs, job=job, today=date.today())

    score, _ = ResumeMatchScore.objects.update_or_create(
        user=user,
        job=job,
        defaults=_explanation_to_defaults(explanation),
    )
    score.job = job
    return score


def bulk_generate_match_scores(user, job_ids: list[str]) -> list[ResumeMatchScore]:
    """Compute and persist match scores for multiple jobs in a single transaction.

    Jobs that do not exist or are inactive are silently skipped — the caller
    receives only the scores that were successfully generated. Idempotent:
    existing scores for included jobs are refreshed. Complexity: O(n) engine
    calls, O(n) DB upserts, 1 profile fetch.
    """
    if not job_ids:
        return []

    profile = _fetch_profile(user)
    inputs = _build_scoring_inputs(profile)

    jobs = list(
        Job.objects.filter(
            pk__in=job_ids,
            is_active=True,
            deleted_at__isnull=True,
        )
    )

    scores: list[ResumeMatchScore] = []
    with transaction.atomic():
        for job in jobs:
            explanation = compute_resume_match_score(
                **inputs, job=job, today=date.today()
            )
            score, _ = ResumeMatchScore.objects.update_or_create(
                user=user,
                job=job,
                defaults=_explanation_to_defaults(explanation),
            )
            score.job = job
            scores.append(score)

    return scores
