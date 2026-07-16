import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="ai",
    name="ai.analyze_ats",
)
def analyze_ats_score(self, resume_id: str, user_id: str, job_description: str = ""):
    """Compute ATS score for a resume asynchronously."""
    try:
        from apps.resumes.models import Resume
        from apps.resumes.services import ResumeService
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.get(id=user_id)
        resume = Resume.objects.get(id=resume_id, user=user)
        ResumeService.compute_ats_score(resume, user, job_description)

    except Exception as exc:
        logger.error("ATS analysis failed", exc_info=True)
        raise self.retry(exc=exc)
