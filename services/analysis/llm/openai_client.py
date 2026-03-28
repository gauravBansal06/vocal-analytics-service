"""OpenAI / Azure OpenAI API client for LLM inference."""

from __future__ import annotations

from openai import AsyncAzureOpenAI, AsyncOpenAI

from services.analysis.config import settings
from services.analysis.llm.base import BaseLLMClient, LLMResponse


class OpenAIClient(BaseLLMClient):
    def __init__(self) -> None:
        if settings.openai_azure_api_endpoint:
            # Azure OpenAI deployment
            self._client = AsyncAzureOpenAI(
                api_key=settings.openai_api_key,
                azure_endpoint=settings.openai_azure_api_endpoint,
                api_version=settings.openai_azure_api_version,
            )
        else:
            # Direct OpenAI API
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    async def chat(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=settings.llm_temperature,
            response_format={"type": "json_object"},
            max_tokens=2048,
        )
        usage = response.usage
        return LLMResponse(
            text=response.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    def model_name(self) -> str:
        return self._model
