import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="imports",
    name="imports.process_import_job",
)
def process_import_job(self, import_job_id: str):
    """Parse uploaded document and extract profile data."""
    try:
        from apps.imports.models import ImportJob, ImportStatus
        from apps.imports.services import ImportService

        job = ImportJob.objects.get(id=import_job_id)
        job.status = ImportStatus.PROCESSING
        job.save(update_fields=["status"])

        ImportService.process(job)

    except Exception as exc:
        logger.error("Import job failed", exc_info=True)
        try:
            from apps.imports.models import ImportJob, ImportStatus
            ImportJob.objects.filter(id=import_job_id).update(
                status=ImportStatus.FAILED,
                error_message=str(exc)[:1000],
            )
        except Exception:
            pass
        raise self.retry(exc=exc)
