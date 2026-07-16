from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class AIResponse:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: Optional[float] = None


class IAIProvider(ABC):
    """All AI provider implementations must satisfy this interface."""

    @abstractmethod
    def complete(self, prompt: str, system_prompt: str = "", max_tokens: int = 2000) -> AIResponse:
        """Send a completion request and return a structured response."""
        ...

    @abstractmethod
    def chat(self, messages: list[dict], system_prompt: str = "", max_tokens: int = 2000) -> AIResponse:
        """Send a chat history request and return a structured response.
        Messages should be of the format: [{"role": "user"|"ai", "content": "..."}]
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...
