import dataclasses
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    queue="career_hub",
    name="career_hub.sync_jobs",
    max_retries=3,
    default_retry_delay=300,
)
def sync_jobs_task(query="software engineer", city="Bangalore"):
    """Fetch jobs from all active providers and upsert into the catalog."""
    from apps.career_hub.providers.adzuna import AdzunaProvider
    from apps.career_hub.services.sync import JobSyncService

    provider = AdzunaProvider()
    service = JobSyncService(provider)
    result = service.sync(query=query, city=city, max_pages=1)

    if result.sweep_skipped:
        logger.error(
            "sync_jobs_task: sweep_skipped=True pages_fetched=%d jobs_seen=%d",
            result.pages_fetched, result.jobs_seen,
        )
    else:
        logger.info("sync_jobs_task: complete %s", result)

    return dataclasses.asdict(result)


@shared_task(queue="career_hub", name="career_hub.generate_recommendations")
def generate_recommendations_task(user_id: str) -> dict:
    """Score catalog jobs against a user profile and write top-N recommendations.

    Thin-task pattern: business logic lives in RecommendationService.
    Returns a dict representation of RecommendationResult.
    """
    from apps.career_hub.services.recommendations import RecommendationService

    service = RecommendationService()
    result = service.generate_for_user(user_id)

    if result.skipped:
        logger.info(
            "generate_recommendations_task: user=%s skipped reason=%s",
            user_id, result.skip_reason,
        )
    else:
        logger.info(
            "generate_recommendations_task: user=%s scored=%d persisted=%d elapsed_ms=%.1f",
            user_id, result.jobs_scored, result.recommendations_persisted, result.elapsed_ms,
        )

    return dataclasses.asdict(result)


@shared_task(queue="career_hub", name="career_hub.fan_out_recommendations")
def fan_out_recommendations_task() -> dict:
    """Enqueue one generate_recommendations_task per eligible user.

    Eligible users: those with onboarding_complete=True, ordered by user_id for
    deterministic batching. Fan-out design supports future horizontal scaling by
    splitting the user_id range across multiple workers.
    """
    from apps.profiles.models import UserProfile

    user_ids = list(
        UserProfile.objects
        .filter(onboarding_complete=True)
        .values_list("user_id", flat=True)
        .order_by("user_id")
    )

    for uid in user_ids:
        generate_recommendations_task.delay(str(uid))

    logger.info("fan_out_recommendations_task: enqueued %d users", len(user_ids))
    return {"enqueued": len(user_ids)}
