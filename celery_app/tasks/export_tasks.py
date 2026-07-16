import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="resume",
    name="exports.generate",
)
def generate_export(self, export_job_id: str):
    """Generate a PDF or DOCX export and upload to storage."""
    try:
        from apps.exports.models import ExportJob, ExportStatus
        from apps.exports.services import ExportService

        job = ExportJob.objects.get(id=export_job_id)
        ExportService.generate(job)

    except Exception as exc:
        logger.error("Export generation failed", exc_info=True)
        raise self.retry(exc=exc)
