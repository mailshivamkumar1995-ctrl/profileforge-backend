import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    queue="resume",
    name="resume.rebuild_previews",
)
def rebuild_resume_previews(self, user_id: str):
    """Rebuild HTML previews for all active resumes of a user after profile update."""
    try:
        from django.contrib.auth import get_user_model
        from apps.resumes.models import Resume
        from apps.resumes.services import ResumeService

        User = get_user_model()
        user = User.objects.get(id=user_id)
        active_resumes = Resume.objects.filter(user=user, status="active")

        for resume in active_resumes:
            ResumeService.rebuild_preview(resume)
            logger.info("Rebuilt preview", extra={"resume_id": str(resume.id)})

    except Exception as exc:
        logger.error("Failed to rebuild resume previews", exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="resume",
    name="resume.generate_export",
)
def generate_resume_export(self, export_job_id: str):
    """Generate PDF or DOCX export for a resume."""
    try:
        from apps.exports.models import ExportJob, ExportStatus
        from apps.exports.services import ExportService

        job = ExportJob.objects.get(id=export_job_id)
        job.status = ExportStatus.PROCESSING
        job.save(update_fields=["status"])

        ExportService.generate(job)

    except Exception as exc:
        logger.error("Failed to generate resume export", exc_info=True)
        try:
            from apps.exports.models import ExportJob, ExportStatus
            ExportJob.objects.filter(id=export_job_id).update(
                status=ExportStatus.FAILED,
                error_message=str(exc),
            )
        except Exception:
            pass
        raise self.retry(exc=exc)
