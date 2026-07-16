import time
import logging
from django.conf import settings
from apps.ai_engine.providers.base import IAIProvider, AIResponse
from core.exceptions import AIProviderException

logger = logging.getLogger(__name__)


class AnthropicProvider(IAIProvider):
    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        import anthropic
        self._client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self._model = model

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, prompt: str, system_prompt: str = "", max_tokens: int = 2000) -> AIResponse:
        kwargs = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        try:
            response = self._client.messages.create(**kwargs)
            usage = response.usage
            return AIResponse(
                content=response.content[0].text,
                model=self._model,
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                total_tokens=usage.input_tokens + usage.output_tokens,
            )
        except Exception as e:
            logger.error("Anthropic API error", exc_info=True)
            raise AIProviderException(f"Anthropic error: {str(e)}") from e
