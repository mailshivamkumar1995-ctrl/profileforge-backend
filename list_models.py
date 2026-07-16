import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

import google.generativeai as genai
from django.conf import settings

genai.configure(api_key=getattr(settings, 'GOOGLE_AI_API_KEY', ''))
for m in genai.list_models():
    print(m.name)
