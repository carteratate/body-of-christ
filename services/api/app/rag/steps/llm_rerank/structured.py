"""Shared schemas and strict decoding for LLM reranker responses."""
from __future__ import annotations

import json
import math
from typing import Any


class RerankContractError(ValueError):
    """Valid JSON that violates the reranker application contract."""


def score_schema(expected_count: int, *, pointwise: bool) -> dict[str, Any]:
    """Return the provider-neutral JSON Schema for one positional result per input.

    Candidate IDs deliberately stay out of model output.  Position is a cheaper and
    safer identity contract: exact array length guarantees coverage, and the caller
    maps result N back to candidate N without trusting copied database identifiers.
    """
    properties: dict[str, Any] = {
        "position": {
            "type": "integer",
            "description": "The unchanged zero-based POSITION from the input passage.",
        },
        "score": {
            "type": "number",
            "description": "Relevance score from 0.0 through 1.0 inclusive.",
        },
    }
    required = ["position", "score"]
    if pointwise:
        properties.update({
            "include": {"type": "boolean"},
            "overlap_verdict": {
                "anyOf": [
                    {"type": "string", "enum": ["redundant", "complementary"]},
                    {"type": "null"},
                ],
            },
        })
        required.extend(["include", "overlap_verdict"])

    return {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                # Keep provider grammar stable across pool sizes. Exact count is a
                # request-specific semantic invariant enforced by decode_results.
                "description": (
                    "One result per input passage, in unchanged positional order. "
                    "Do not reorder or omit entries."
                ),
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
            },
        },
        "required": ["results"],
        "additionalProperties": False,
    }


def decode_results(text: str, expected_count: int) -> list[dict[str, Any]]:
    """Strictly decode the structured payload and enforce semantic invariants."""
    payload = json.loads(text)
    if not isinstance(payload, dict) or set(payload) != {"results"}:
        raise RerankContractError(
            "Rerank response must be an object containing only 'results'"
        )
    results = payload["results"]
    if not isinstance(results, list):
        raise RerankContractError("Rerank 'results' must be an array")
    if len(results) != expected_count:
        raise RerankContractError(
            f"Rerank result count mismatch: expected {expected_count}, got {len(results)}"
        )
    if any(not isinstance(item, dict) for item in results):
        raise RerankContractError("Every rerank result must be an object")
    for expected_position, item in enumerate(results):
        position = item.get("position")
        if isinstance(position, bool) or not isinstance(position, int):
            raise RerankContractError(
                f"Rerank position must be an integer, got {position!r}"
            )
        if position != expected_position:
            raise RerankContractError(
                f"Rerank position mismatch: expected {expected_position}, got {position}"
            )
    return results


def strict_score(item: dict[str, Any]) -> float:
    """Accept JSON numbers only; reject booleans, strings, NaN, and out-of-range."""
    value = item.get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RerankContractError(
            f"Rerank score must be a JSON number, got {value!r}"
        )
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise RerankContractError(
            f"Rerank score must be finite and within [0, 1], got {value!r}"
        )
    return score
