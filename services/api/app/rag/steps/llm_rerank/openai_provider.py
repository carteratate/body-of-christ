"""GPT-5.6 Luna rerank provider.

Its own client instance, matching this codebase's one-client-per-step-module
convention (steps/embed.py and steps/explain.py each hold their own).
"""
from __future__ import annotations

import logging
from typing import Any

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

    async def score(
        self, system: str, user: str, max_tokens: int,
        output_schema: dict[str, Any] | None = None,
    ) -> ScoreResult:
        if _client is None:
            raise RuntimeError("OpenAI rerank client not initialised")
        # The system prompt goes in as a system message so the same prompt text works
        # unchanged across both providers — parsing stays identical downstream.
        response_format = (
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "rerank_scores",
                    "strict": True,
                    "schema": output_schema,
                },
            }
            if output_schema is not None else openai.NOT_GIVEN
        )
        response = await _client.chat.completions.create(
            model=settings.rerank_luna_model,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=response_format,
        )
        choice = response.choices[0]
        completion_error = None
        completion_reason = None
        if choice.finish_reason != "stop":
            completion_error = f"OpenAI rerank incomplete: finish_reason={choice.finish_reason}"
            completion_reason = (
                "completion_truncated" if choice.finish_reason == "length"
                else "completion_incomplete"
            )
        if getattr(choice.message, "refusal", None):
            completion_error = "OpenAI rerank refused the structured-output request"
            completion_reason = "completion_refused"
        usage = response.usage
        return ScoreResult(
            text=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            completion_error=completion_error,
            completion_reason=completion_reason,
        )


PROVIDER = OpenAIProvider()
