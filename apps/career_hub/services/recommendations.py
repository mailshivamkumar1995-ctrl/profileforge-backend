"""
RecommendationService — generates and persists job recommendations for a single user.

Designed for batch execution: called once per user by generate_recommendations_task,
which is enqueued by fan_out_recommendations_task on a 6-hour Celery Beat schedule.

Cold-start policy:
  - no_profile          : UserProfile does not exist for this user
  - onboarding_incomplete: profile.onboarding_complete is False
  - no_profile_data     : no skills AND no work experiences (cannot score)
Cold-start users receive a skip result and no recommendations are written.
"""
from __future__ import annotations

import dataclasses
import logging
import time
from datetime import timedelta
from decimal import Decimal
from statistics import median

from django.db.models import Q
from django.utils import timezone

from apps.career_hub.models import Job, JobRecommendation, UserJob
from apps.career_hub.services.scoring import ALGORITHM_VERSION, compute_score
from apps.profiles.models import UserProfile

logger = logging.getLogger(__name__)

TOP_N = 50
EXPIRES_HOURS = 24
CATALOG_CAP = 5_000  # max jobs scored per generation run


@dataclasses.dataclass
class RecommendationResult:
    user_id: str
    skipped: bool = False
    skip_reason: str = ""
    jobs_scored: int = 0
    recommendations_persisted: int = 0
    stale_removed: int = 0
    elapsed_ms: float = 0.0


class RecommendationService:
    """Scores catalog jobs against a user's profile and persists the top-N results."""

    def generate_for_user(self, user_id: str) -> RecommendationResult:
        start = time.monotonic()

        # ── 1. Load profile ────────────────────────────────────────────────────
        try:
            profile = (
                UserProfile.objects
                .select_related("user")
                .prefetch_related("skills", "work_experiences")
                .get(user_id=user_id)
            )
        except UserProfile.DoesNotExist:
            return RecommendationResult(
                user_id=user_id, skipped=True, skip_reason="no_profile",
            )

        if not profile.onboarding_complete:
            return RecommendationResult(
                user_id=user_id, skipped=True, skip_reason="onboarding_incomplete",
            )

        skills = list(profile.skills.all())
        work_exps = list(profile.work_experiences.all())

        if not skills and not work_exps:
            return RecommendationResult(
                user_id=user_id, skipped=True, skip_reason="no_profile_data",
            )

        # ── 2. Gather behavioral signals ───────────────────────────────────────
        user = profile.user

        saved_user_jobs = list(
            UserJob.objects
            .filter(user=user)
            .exclude(status=UserJob.Status.REJECTED)
            .select_related("job")
        )
        saved_jobs = [uj.job for uj in saved_user_jobs]

        # ── 3. Pre-compute user signal vectors (computed once, shared across jobs)
        headline = profile.headline or ""
        location_data = profile.location if isinstance(profile.location, dict) else {}
        user_city = location_data.get("city", "")

        # Prefer current role titles; fall back to most recent experience
        current_titles = [we.job_title for we in work_exps if we.is_current]
        if not current_titles and work_exps:
            sorted_exps = sorted(
                work_exps,
                key=lambda we: (we.start_date or timezone.now().date()),
                reverse=True,
            )
            current_titles = [sorted_exps[0].job_title]

        saved_job_titles = [j.title for j in saved_jobs]
        expected_salary_min, expected_salary_max = _infer_salary_expectation(saved_jobs)

        # ── 4. Load active job catalog ─────────────────────────────────────────
        jobs = list(
            Job.objects
            .filter(is_active=True, is_private=False, deleted_at__isnull=True)
            [:CATALOG_CAP]
        )

        if not jobs:
            logger.info(
                "RecommendationService: user=%s no active jobs in catalog", user_id
            )
            return RecommendationResult(
                user_id=user_id, skipped=False, jobs_scored=0,
                elapsed_ms=_elapsed_ms(start),
            )

        # ── 5. Score each job ──────────────────────────────────────────────────
        scored: list[tuple[Job, dict]] = []
        for job in jobs:
            result = compute_score(
                skills=skills,
                headline=headline,
                current_titles=current_titles,
                user_city=user_city,
                saved_job_titles=saved_job_titles,
                expected_salary_min=expected_salary_min,
                expected_salary_max=expected_salary_max,
                job=job,
            )
            scored.append((job, result))

        # ── 6. Rank — sort descending by score with deterministic tie-breaking ─
        # Tie-breaking order: total DESC, posted_at DESC, salary_max DESC, id ASC
        scored.sort(
            key=lambda x: (
                -float(x[1]["total"]),
                -(x[0].posted_at.timestamp() if x[0].posted_at else 0.0),
                -(float(x[0].salary_max) if x[0].salary_max is not None else 0.0),
                str(x[0].id),
            )
        )
        top = scored[:TOP_N]

        # ── 7. Persist recommendations (upsert preserves is_dismissed) ────────
        now = timezone.now()
        expires_at = now + timedelta(hours=EXPIRES_HOURS)
        persisted = 0

        for job, score_data in top:
            JobRecommendation.objects.update_or_create(
                user=user,
                job=job,
                defaults={
                    "score": score_data["total"],
                    "score_breakdown": score_data["breakdown"],
                    "algorithm_version": ALGORITHM_VERSION,
                    "generated_at": now,
                    "expires_at": expires_at,
                },
            )
            persisted += 1

        # ── 8. Remove stale recommendations ───────────────────────────────────
        # Non-dismissed recs not in the current top-N are pruned immediately
        # (they were superseded by higher-scoring jobs this run).
        # Dismissed recs are preserved so the UI can maintain accurate history.
        top_job_ids = {job.id for job, _ in top}
        stale_count = 0

        if top_job_ids:
            stale_deleted, _ = (
                JobRecommendation.objects
                .filter(user=user, is_dismissed=False)
                .exclude(job_id__in=top_job_ids)
                .delete()
            )
            stale_count += stale_deleted

        # Always prune recommendations for inactive or deleted jobs
        inactive_deleted, _ = (
            JobRecommendation.objects
            .filter(user=user)
            .filter(Q(job__is_active=False) | Q(job__deleted_at__isnull=False))
            .delete()
        )
        stale_count += inactive_deleted

        elapsed = _elapsed_ms(start)
        logger.info(
            "RecommendationService: user=%s scored=%d persisted=%d stale_removed=%d elapsed_ms=%.1f",
            user_id, len(scored), persisted, stale_count, elapsed,
        )

        return RecommendationResult(
            user_id=user_id,
            skipped=False,
            jobs_scored=len(scored),
            recommendations_persisted=persisted,
            stale_removed=stale_count,
            elapsed_ms=elapsed,
        )


def _infer_salary_expectation(
    saved_jobs: list[Job],
) -> tuple[Decimal | None, Decimal | None]:
    """Infer expected salary range from the median of saved jobs' salary data.

    Returns (None, None) when no saved jobs have salary information.
    """
    mins = [float(j.salary_min) for j in saved_jobs if j.salary_min is not None]
    maxs = [float(j.salary_max) for j in saved_jobs if j.salary_max is not None]

    expected_min = Decimal(str(round(median(mins), 2))) if mins else None
    expected_max = Decimal(str(round(median(maxs), 2))) if maxs else None

    return expected_min, expected_max


def _elapsed_ms(start: float) -> float:
    return (time.monotonic() - start) * 1000.0
