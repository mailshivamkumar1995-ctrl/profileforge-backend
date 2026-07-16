import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("profileforge")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks([
    "celery_app.tasks.resume_tasks",
    "celery_app.tasks.portfolio_tasks",
    "celery_app.tasks.import_tasks",
    "celery_app.tasks.export_tasks",
    "celery_app.tasks.ai_tasks",
])
