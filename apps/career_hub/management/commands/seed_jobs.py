import logging
from django.core.management.base import BaseCommand
from apps.career_hub.models import Job

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Seeds initial jobs into the database from Adzuna if none exist."

    def handle(self, *args, **options):
        if Job.objects.exists():
            self.stdout.write(self.style.SUCCESS("Jobs already exist. Skipping seed."))
            return

        self.stdout.write(self.style.WARNING("No jobs found. Starting initial sync..."))
        from apps.career_hub.providers.adzuna import AdzunaProvider
        from apps.career_hub.services.sync import JobSyncService
        try:
            provider = AdzunaProvider()
            service = JobSyncService(provider)
            result = service.sync(query="Software Engineer", city="Bangalore")
            self.stdout.write(self.style.SUCCESS(f"Successfully seeded jobs: {result}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to seed jobs: {str(e)}"))
