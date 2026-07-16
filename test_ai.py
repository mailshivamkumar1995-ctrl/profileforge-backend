import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from apps.ai_engine.providers.gemini_provider import GeminiProvider

p = GeminiProvider()
try:
    res = p.complete('Reply with OK')
    print('RESULT:', res.content)
except Exception as e:
    print('ERROR:', str(e))
