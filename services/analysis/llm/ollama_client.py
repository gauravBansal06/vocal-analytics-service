"""Ollama local LLM client."""

from __future__ import annotations

import httpx

from services.analysis.config import settings
from services.analysis.llm.base import BaseLLMClient, LLMResponse


class OllamaClient(BaseLLMClient):
    def __init__(self) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model

    async def chat(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {
                "temperature": settings.llm_temperature,
                "num_predict": 2048,
            },
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            text = data.get("message", {}).get("content", "")
            input_tokens = data.get("prompt_eval_count", 0)
            output_tokens = data.get("eval_count", 0)
            return LLMResponse(
                text=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

    def model_name(self) -> str:
        return self._model
