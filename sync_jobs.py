import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from apps.career_hub.providers.adzuna import AdzunaProvider
from apps.career_hub.services.sync import JobSyncService

provider = AdzunaProvider()
service = JobSyncService(provider)
result = service.sync(query=" devops,
