"""Provider interface for LLM-based reranking.

Both rerank shapes (pointwise per-collection, listwise global) go through this one
call, so adding a provider means implementing `score()` and registering it — no
change to prompt construction, parsing, or orchestration.

Providers return raw text rather than parsed output deliberately: the two shapes
parse differently, and keeping parsing out of the provider means a provider swap
cannot change how a response is interpreted.
"""
from __future__ import annotations

import inspect
from typing import Any, Protocol


class ScoreResult:
    """Raw provider output plus token counts for cost tracking."""

    __slots__ = (
        "text", "input_tokens", "output_tokens", "completion_error",
        "completion_reason",
    )

    def __init__(
        self, text: str, input_tokens: int, output_tokens: int,
        completion_error: str | None = None,
        completion_reason: str | None = None,
    ) -> None:
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        # Providers return billed incomplete/refusal responses so the caller can
        # record usage before rejecting them transactionally.
        self.completion_error = completion_error
        self.completion_reason = completion_reason


class RerankProvider(Protocol):
    """A model backend usable for reranking."""

    name: str

    @property
    def model_id(self) -> str:
        """Model identifier, used as the cost-tracking key."""
        ...

    def is_ready(self) -> bool:
        """False when the client was never initialised (missing credentials)."""
        ...

    async def score(
        self,
        system: str,
        user: str,
        max_tokens: int,
        output_schema: dict[str, Any] | None = None,
    ) -> ScoreResult:
        """Single completion call. Raises on transport/API failure — callers
        decide the fallback, since the right fallback differs per shape."""
        ...


async def call_provider(
    provider: RerankProvider,
    system: str,
    user: str,
    max_tokens: int,
    output_schema: dict[str, Any],
) -> ScoreResult:
    """Call new providers with a schema while retaining legacy stub compatibility.

    Pre-structured-output evaluation harnesses implemented the three-argument
    ``score`` method. Signature inspection avoids misclassifying a TypeError raised
    *inside* a provider as an old interface and provides a clean migration bridge.
    """
    parameters = inspect.signature(provider.score).parameters
    if "output_schema" in parameters or len(parameters) >= 4:
        return await provider.score(system, user, max_tokens, output_schema)
    return await provider.score(system, user, max_tokens)  # type: ignore[call-arg]
