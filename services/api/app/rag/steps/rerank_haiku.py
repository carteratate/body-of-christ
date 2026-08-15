"""Per-collection pointwise re-ranking using Claude Haiku (parallel across collections).

The prompt and parsing now live in `llm_rerank/pointwise.py` so Haiku and Luna can
share them. This module stays as the Haiku-bound entry point: it owns the `_client`
global and keeps `run` / `_rerank_single_collection` / `init_rerank` / `close_rerank`
at their historical import paths, which `app/main.py` and `tests/test_rerank.py`
depend on.

`_HaikuClientProvider.score` reads the module-level `_client` at call time (rather
than capturing it), so patching `rerank_haiku._client` still intercepts the model
call — that is what the existing tests do.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid as _uuid_mod
from typing import Any

import anthropic

from app.config import settings
from app.rag.steps import degradation
from app.rag.steps.cost_tracker import CostTracker
from app.rag.steps.llm_rerank import pointwise
from app.rag.steps.llm_rerank.base import ScoreResult
from app.rag.steps.types import ChunkCandidate, RankedChunk

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

# Re-exported for tests and callers that reference them at this path.
_RERANK_SYSTEM = pointwise._RERANK_SYSTEM
_format_passages = pointwise._format_passages
_fallback_ranked = pointwise.fallback_ranked


# Compatibility shims for external evaluation harnesses that imported the former
# private helpers. Production parsing uses llm_rerank.structured instead.
def _is_valid_uuid(value: str) -> bool:
    try:
        _uuid_mod.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _extract_json_array(text: str) -> list[dict]:
    start = text.find("[")
    if start < 0:
        raise ValueError("No JSON array found in response")
    value, end = json.JSONDecoder().raw_decode(text, start)
    if not isinstance(value, list) or text[end:].strip() not in ("", "```"):
        raise ValueError("Invalid legacy JSON array response")
    return value


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
            temperature=0,
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


async def _rerank_single_collection(
    candidates: list[ChunkCandidate],
    query: str,
    quota: int,
    cost_tracker: CostTracker,
) -> list[RankedChunk]:
    """Score and filter one collection's candidates using Claude Haiku."""
    return await pointwise.rerank_collection(
        candidates, query, quota, cost_tracker, PROVIDER, step="rerank_haiku",
    )


async def run(
    candidates: dict[str, list[ChunkCandidate]],
    query: str,
    quota: int,
    cost_tracker: CostTracker,
) -> list[RankedChunk]:
    """Rerank all collections in parallel, return globally sorted list."""
    max_per_col = quota * settings.candidate_multiplier
    results = await asyncio.gather(
        *[_rerank_single_collection(col_cands[:max_per_col], query, quota, cost_tracker)
          for col_cands in candidates.values()],
        return_exceptions=True,
    )
    all_ranked: list[RankedChunk] = []
    for collection, result in zip(candidates, results):
        if isinstance(result, BaseException):
            logger.warning("rerank_haiku: collection failed: %s", result)
            degradation.record(
                "rerank_haiku", type(result).__name__, "collection_omitted",
                scope=collection, details={"message": str(result)[:300]},
            )
        else:
            all_ranked.extend(result)
    all_ranked.sort(key=lambda r: r.reranker_score, reverse=True)
    return all_ranked
