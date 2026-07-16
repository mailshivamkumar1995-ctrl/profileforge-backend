import logging
from django.conf import settings
from apps.ai_engine.providers.base import IAIProvider, AIResponse
from core.exceptions import AIProviderException

logger = logging.getLogger(__name__)

# Gemini 1.5 Flash pricing (per 1M tokens, prompts ≤128k)
_COST_PER_1M = {
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-flash-latest": {"input": 0.075, "output": 0.30},
}


class GeminiProvider(IAIProvider):
    def __init__(self, model: str = "gemini-pro"):
        import google.generativeai as genai
        api_key = getattr(settings, "GOOGLE_AI_API_KEY", "")
        if not api_key:
            raise AIProviderException("GOOGLE_AI_API_KEY is not configured.")
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_name = model

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model_name

    def complete(self, prompt: str, system_prompt: str = "", max_tokens: int = 2000) -> AIResponse:
        import google.generativeai as genai

        try:
            model = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=system_prompt or None,
            )
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.7,
                ),
            )

            text = response.text
            usage = response.usage_metadata
            prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
            completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
            total_tokens = getattr(usage, "total_token_count", 0) or (prompt_tokens + completion_tokens)

            costs = _COST_PER_1M.get(self._model_name, {})
            cost_usd = None
            if costs:
                cost_usd = round(
                    (prompt_tokens * costs["input"] / 1_000_000) +
                    (completion_tokens * costs["output"] / 1_000_000),
                    5
                )

            return AIResponse(
                content=text,
                model=self._model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
            )
        except Exception as e:
            logger.error("Gemini completion failed: %s", str(e))
            raise AIProviderException(f"Provider error: {str(e)}")

    def chat(self, messages: list[dict], system_prompt: str = "", max_tokens: int = 2000) -> AIResponse:
        import google.generativeai as genai

        try:
            model = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=system_prompt or None,
            )
            
            contents = []
            for m in messages:
                role = "model" if m.get("role") == "ai" else "user"
                contents.append({
                    "role": role,
                    "parts": [m.get("content", "")]
                })
                
            response = model.generate_content(
                contents,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=0.7,
                ),
            )

            text = response.text
            usage = response.usage_metadata
            prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
            completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
            total_tokens = getattr(usage, "total_token_count", 0) or (prompt_tokens + completion_tokens)

            costs = _COST_PER_1M.get(self._model_name, {})
            cost_usd = None
            if costs:
                cost_usd = round(
                    (prompt_tokens * costs["input"] / 1_000_000) +
                    (completion_tokens * costs["output"] / 1_000_000),
                    5
                )

            return AIResponse(
                content=text,
                model=self._model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
            )
        except Exception as e:
            logger.error("Gemini chat failed: %s", str(e))
            raise AIProviderException(f"Provider error: {str(e)}")
