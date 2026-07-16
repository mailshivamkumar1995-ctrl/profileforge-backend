import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List

from django.db import transaction
from django.utils import timezone

from apps.career_hub.models import Job, JobSource
from apps.career_hub.providers.base import JobProvider, NormalizedJob

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    provider: str
    query: str
    city: str
    pages_fetched: int
    jobs_seen: int
    created: int
    updated: int
    reactivated: int
    deactivated: int
    errors: int
    duration_seconds: float
    sweep_skipped: bool


class JobSyncService:
    """
    Orchestrates job synchronization from a JobProvider into the Job catalog.

    All business logic lives here. The Celery task is a thin wrapper.
    """

    def __init__(self, provider: JobProvider) -> None:
        self.provider = provider

    def sync(self, query: str, city: str, max_pages: int = 5) -> SyncResult:
        start = time.monotonic()
        pages_fetched = 0
        jobs_seen = 0
        created = 0
        updated = 0
        reactivated = 0
        deactivated = 0
        errors = 0

        source = self._resolve_source()
        sync_start = timezone.now()

        for page in range(1, max_pages + 1):
            try:
                jobs = self.provider.fetch_jobs(query, city, page)
            except Exception as exc:
                logger.error(
                    "JobSyncService: unexpected provider error on page %d: %s",
                    page, exc,
                )
                errors += 1
                break

            if not jobs:
                break

            pages_fetched += 1
            jobs_seen += len(jobs)

            try:
                b_created, b_updated, b_reactivated = self._upsert_batch(jobs, source)
                created += b_created
                updated += b_updated
                reactivated += b_reactivated
            except Exception as exc:
                logger.error(
                    "JobSyncService: upsert failed for page %d: %s", page, exc
                )
                errors += 1

        # COND-01: skip stale sweep when no jobs were successfully ingested
        # COND-02: skip stale sweep if this is a targeted search (query or city provided)
        is_targeted_search = bool(query) or bool(city)
        sweep_eligible = pages_fetched >= 1 and jobs_seen >= 1 and not is_targeted_search
        sweep_skipped = not sweep_eligible

        if sweep_skipped:
            logger.error(
                "JobSyncService: stale sweep skipped — pages_fetched=%d jobs_seen=%d "
                "(provider=%s query=%r city=%r). Catalog preserved.",
                pages_fetched, jobs_seen, self.provider.source_name, query, city,
            )
        else:
            try:
                deactivated = self._mark_stale_inactive(source, sync_start)
            except Exception as exc:
                logger.error("JobSyncService: stale sweep failed: %s", exc)
                errors += 1
                sweep_skipped = True

        result = SyncResult(
            provider=self.provider.source_name,
            query=query,
            city=city,
            pages_fetched=pages_fetched,
            jobs_seen=jobs_seen,
            created=created,
            updated=updated,
            reactivated=reactivated,
            deactivated=deactivated,
            errors=errors,
            duration_seconds=round(time.monotonic() - start, 3),
            sweep_skipped=sweep_skipped,
        )

        logger.info("JobSyncService: complete — %s", result)
        return result

    def _resolve_source(self) -> JobSource:
        source, created = JobSource.objects.get_or_create(
            slug=self.provider.source_name,
            defaults={
                "name": self.provider.source_name.title(),
                "is_active": True,
            },
        )
        if created:
            logger.info("JobSyncService: created JobSource slug=%r", source.slug)
        return source

    def _upsert_batch(
        self, jobs: List[NormalizedJob], source: JobSource
    ) -> tuple[int, int, int]:
        """Upsert a list of jobs. Returns (created, updated, reactivated)."""
        if not jobs:
            return 0, 0, 0

        created = 0
        updated = 0
        reactivated = 0

        with transaction.atomic():
            # Single query to identify which existing records are currently inactive.
            # This lets us distinguish reactivation from a normal update.
            inactive_eids = set(
                Job.objects.filter(
                    source=source,
                    external_id__in=[j.external_id for j in jobs],
                    is_active=False,
                ).values_list("external_id", flat=True)
            )

            for job in jobs:
                _, was_created = Job.objects.update_or_create(
                    source=source,
                    external_id=job.external_id,
                    defaults={
                        "title": job.title,
                        "company": job.company,
                        "description": job.description,
                        "apply_url": job.apply_url,
                        "city": job.city or "",
                        "work_type": job.work_type,
                        "salary_min": job.salary_min,
                        "salary_max": job.salary_max,
                        "salary_currency": job.salary_currency,
                        "posted_at": job.posted_at,
                        "is_active": True,
                        "is_private": job.is_private,
                        "deleted_at": None,
                        "fetched_at": timezone.now(),
                    },
                )
                if was_created:
                    created += 1
                elif job.external_id in inactive_eids:
                    reactivated += 1
                else:
                    updated += 1

        return created, updated, reactivated

    def _mark_stale_inactive(self, source: JobSource, sync_start: datetime) -> int:
        """Deactivate jobs not seen since sync_start. Returns count deactivated."""
        with transaction.atomic():
            return Job.objects.filter(
                source=source,
                is_active=True,
                deleted_at__isnull=True,
                fetched_at__lt=sync_start,
            ).update(
                is_active=False,
                deleted_at=timezone.now(),
            )
