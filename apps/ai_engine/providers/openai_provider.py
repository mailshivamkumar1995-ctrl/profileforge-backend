import time
import logging
from django.conf import settings
from apps.ai_engine.providers.base import IAIProvider, AIResponse
from core.exceptions import AIProviderException

logger = logging.getLogger(__name__)

COST_PER_1K_TOKENS = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
}


class OpenAIProvider(IAIProvider):
    def __init__(self, model: str = "gpt-4o-mini"):
        from openai import OpenAI
        self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._model = model

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, prompt: str, system_prompt: str = "", max_tokens: int = 2000) -> AIResponse:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            start = time.monotonic()
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7,
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            usage = response.usage
            costs = COST_PER_1K_TOKENS.get(self._model, {})
            cost = None
            if costs:
                cost = (usage.prompt_tokens / 1000 * costs["input"]) + (
                    usage.completion_tokens / 1000 * costs["output"]
                )

            return AIResponse(
                content=response.choices[0].message.content,
                model=self._model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                cost_usd=cost,
            )
        except Exception as e:
            logger.error("OpenAI API error", exc_info=True)
            raise AIProviderException(f"OpenAI error: {str(e)}") from e

    def chat(self, messages: list[dict], system_prompt: str = "", max_tokens: int = 2000) -> AIResponse:
        openai_messages = []
        if system_prompt:
            openai_messages.append({"role": "system", "content": system_prompt})

        for m in messages:
            role = "assistant" if m.get("role") == "ai" else "user"
            openai_messages.append({"role": role, "content": m.get("content", "")})

        try:
            start = time.monotonic()
            response = self._client.chat.completions.create(
                model=self._model,
                messages=openai_messages,
                max_tokens=max_tokens,
                temperature=0.7,
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            usage = response.usage
            costs = COST_PER_1K_TOKENS.get(self._model, {})
            cost = None
            if costs:
                cost = (usage.prompt_tokens / 1000 * costs["input"]) + (
                    usage.completion_tokens / 1000 * costs["output"]
                )

            return AIResponse(
                content=response.choices[0].message.content,
                model=self._model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                cost_usd=cost,
            )
        except Exception as e:
            logger.error("OpenAI chat API error", exc_info=True)
            raise AIProviderException(f"OpenAI error: {str(e)}") from e