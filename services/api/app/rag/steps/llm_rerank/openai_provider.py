"""GPT-5.6 Luna rerank provider.

Its own client instance, matching this codebase's one-client-per-step-module
convention (steps/embed.py and steps/explain.py each hold their own).
"""
from __future__ import annotations

import logging

import openai

from app.config import settings
from app.rag.steps.llm_rerank.base import ScoreResult

logger = logging.getLogger(__name__)

_client: openai.AsyncOpenAI | None = None


def init() -> None:
    global _client
    _client = openai.AsyncOpenAI(
        api_key=settings.openai_api_key, timeout=60.0, max_retries=2,
    )


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


class OpenAIProvider:
    name = "luna"

    @property
    def model_id(self) -> str:
        return settings.rerank_luna_model

    def is_ready(self) -> bool:
        return _client is not None

    async def score(self, system: str, user: str, max_tokens: int) -> ScoreResult:
        if _client is None:
            raise RuntimeError("OpenAI rerank client not initialised")
        # The system prompt goes in as a system message so the same prompt text works
        # unchanged across both providers — parsing stays identical downstream.
        response = await _client.chat.completions.create(
            model=settings.rerank_luna_model,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        usage = response.usage
        return ScoreResult(
            text=response.choices[0].message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )


PROVIDER = OpenAIProvider()
