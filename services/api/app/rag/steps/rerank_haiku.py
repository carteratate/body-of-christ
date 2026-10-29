"""The Claude Haiku client and the Haiku reranker provider.

This module owns the one Anthropic client that Haiku calls share: the listwise
reranker reaches it through `PROVIDER`, and `routes/evaluate.py` (Discover) reads
`_client` directly. `init_rerank` / `close_rerank` are wired into `main.py`.

`_HaikuClientProvider.score` reads the module-level `_client` at call time (rather
than capturing it), so patching `rerank_haiku._client` still intercepts the model
call — that is what the existing tests do.
"""
from __future__ import annotations

import logging
from typing import Any

import anthropic

from app.config import settings
from app.rag.steps.llm_rerank.base import ScoreResult

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def init_rerank() -> None:
    global _client
    # timeout bounds a hung rerank call (has an RRF fallback on failure).
    _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=45.0)


async def close_rerank() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


class _HaikuClientProvider:
    """The Haiku rerank provider, bound to this module's `_client` global.

    The Anthropic client lives here rather than in `llm_rerank/` because this
    module is already its owner: `init_rerank`/`close_rerank` are wired into
    `main.py`'s lifespan, and `routes/evaluate.py` reads `rerank_haiku._client`
    directly. A second `AsyncAnthropic` inside `llm_rerank/` would mean two
    connection pools to one API and two things to remember to initialise — and an
    uninitialised provider fails *silently*, since `is_ready()` returning False
    makes every rerank fall back to RRF order rather than raising.

    `score` reads `_client` at call time rather than capturing it, so patching
    `rerank_haiku._client` intercepts the model call.
    """

    name = "haiku"

    @property
    def model_id(self) -> str:
        return settings.rerank_model

    def is_ready(self) -> bool:
        return _client is not None

    async def score(
        self, system: str, user: str, max_tokens: int,
        output_schema: dict[str, Any] | None = None,
    ) -> ScoreResult:
        output_config = (
            {
                "format": {
                    "type": "json_schema",
                    "schema": anthropic.transform_schema(output_schema),
                },
            }
            if output_schema is not None else anthropic.omit
        )
        response = await _client.messages.create(
            model=settings.rerank_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            # The transformer strips unsupported grammar constraints while our
            # shared decoder enforces request-specific invariants locally.
            output_config=output_config,
        )
        text_blocks = [block.text for block in response.content if block.type == "text"]
        completion_error = None
        completion_reason = None
        if response.stop_reason != "end_turn":
            completion_error = (
                f"Anthropic rerank incomplete: stop_reason={response.stop_reason}"
            )
            if response.stop_reason == "max_tokens":
                completion_reason = "completion_truncated"
            elif response.stop_reason == "refusal":
                completion_reason = "completion_refused"
            else:
                completion_reason = "completion_incomplete"
        elif len(text_blocks) != 1:
            completion_error = (
                f"Anthropic rerank expected one text block, got {len(text_blocks)}"
            )
            completion_reason = "completion_content_invalid"
        return ScoreResult(
            text=text_blocks[0] if len(text_blocks) == 1 else "",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            completion_error=completion_error,
            completion_reason=completion_reason,
        )


# The single Haiku rerank provider instance, consumed by steps/rerank.py.
PROVIDER = _HaikuClientProvider()
