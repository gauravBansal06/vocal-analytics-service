"""Abstract base class for LLM clients."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class BaseLLMClient(ABC):
    """Interface for LLM providers."""

    @abstractmethod
    async def chat(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send a chat completion request and return response with token usage."""
        ...

    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier string."""
        ...
