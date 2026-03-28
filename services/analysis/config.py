"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load .env from project root (resolves regardless of cwd)
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)


class Settings(BaseSettings):
    # LLM provider
    llm_provider: Literal["openai", "ollama"] = "openai"

    # OpenAI / Azure OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_azure_api_endpoint: str = ""   # e.g. https://your-resource.openai.azure.com
    openai_azure_api_version: str = "2024-12-01-preview"

    # Ollama (local — no key needed)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Whisper
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # File upload limits
    max_file_size_mb: int = 50
    max_transcript_chars: int = 100_000
    max_audio_duration_seconds: int = 1800  # 30 minutes

    # Analysis
    min_transcript_words: int = 5
    short_transcript_threshold: int = 50  # words
    max_llm_retries: int = 1
    llm_temperature: float = 0.1

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def active_llm_model(self) -> str:
        if self.llm_provider == "openai":
            return self.openai_model
        return self.ollama_model


settings = Settings()
