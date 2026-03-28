"""LLM client factory."""

from __future__ import annotations

from services.analysis.config import settings
from services.analysis.llm.base import BaseLLMClient


def get_llm_client() -> BaseLLMClient:
    """Return the configured LLM client instance."""
    if settings.llm_provider == "openai":
        from services.analysis.llm.openai_client import OpenAIClient
        return OpenAIClient()
    if settings.llm_provider == "ollama":
        from services.analysis.llm.ollama_client import OllamaClient
        return OllamaClient()
    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")
