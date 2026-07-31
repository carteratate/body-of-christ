"""Provider interface for LLM-based reranking.

Both rerank shapes (pointwise per-collection, listwise global) go through this one
call, so adding a provider means implementing `score()` and registering it — no
change to prompt construction, parsing, or orchestration.

Providers return raw text rather than parsed output deliberately: the two shapes
parse differently, and keeping parsing out of the provider means a provider swap
cannot change how a response is interpreted.
"""
from __future__ import annotations

from typing import Protocol


class ScoreResult:
    """Raw provider output plus token counts for cost tracking."""

    __slots__ = ("text", "input_tokens", "output_tokens")

    def __init__(self, text: str, input_tokens: int, output_tokens: int) -> None:
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


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

    async def score(self, system: str, user: str, max_tokens: int) -> ScoreResult:
        """Single completion call. Raises on transport/API failure — callers
        decide the fallback, since the right fallback differs per shape."""
        ...
