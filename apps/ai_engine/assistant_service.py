import logging
from django.contrib.auth import get_user_model
from apps.ai_engine.providers.gemini_provider import GeminiProvider

logger = logging.getLogger(__name__)
User = get_user_model()


class AIAssistantService:
    def __init__(self, user=None):
        self.user = user
        self.provider = GeminiProvider()

    def _get_system_prompt(self) -> str:
        prompt = (
            "You are an expert career coach, technical recruiter, and AI Assistant for ProfileForge. "
            "Your goal is to help users with career advice, resume tailoring, interview preparation, and job search strategies. "
            "Be encouraging, professional, and highly actionable. Provide specific examples where possible."
        )

        if self.user:
            prompt += f"\n\nThe user's name is {self.user.first_name or self.user.username}."
            try:
                from apps.profiles.models import Profile
                profile = Profile.objects.get(user=self.user)
                if profile.headline:
                    prompt += f"\nTheir current professional headline is: {profile.headline}."
                if profile.summary:
                    prompt += f"\nTheir professional summary is: {profile.summary}."
            except Exception:
                pass
                
        return prompt

    def chat(self, messages: list[dict]) -> str:
        system_prompt = self._get_system_prompt()
        try:
            response = self.provider.chat(
                messages=messages,
                system_prompt=system_prompt,
                max_tokens=2500
            )
            return response.content
        except Exception as e:
            logger.error("AIAssistantService chat failed", exc_info=True)
            raise e
