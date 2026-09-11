"""Resolve a submitted search into one validated execution plan."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.config import settings
from app.rag.constants import VALID_COLLECTIONS

ALLOWED_QUOTAS: frozenset[int] = frozenset({3, 4, 5, 10})
FOCUSED_QUOTA = 10
FOCUSED_TERMINAL_CANDIDATE_BUDGET = 25
FOCUSED_MAX_PASSAGES_PER_DOCUMENT = 4
STANDARD_MAX_PASSAGES_PER_DOCUMENT = 2


class SearchPlanError(ValueError):
    """A stable validation failure that HTTP routes can translate consistently."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class SearchPlan:
    collections: tuple[str, ...]
    quota: int

    def __post_init__(self) -> None:
        if self.quota not in ALLOWED_QUOTAS:
            raise SearchPlanError("invalid_quota", "Search plan has an invalid quota.")
        if not self.collections:
            raise SearchPlanError(
                "no_valid_collections", "Search plan requires at least one collection."
            )
        if len(set(self.collections)) != len(self.collections):
            raise SearchPlanError(
                "duplicate_collections", "Search plan collections must be distinct."
            )
        if set(self.collections) - VALID_COLLECTIONS:
            raise SearchPlanError(
                "invalid_collections", "Search plan contains an invalid collection."
            )
        if self.focused and len(self.collections) != 1:
            raise SearchPlanError(
                "focused_collection_count",
                "Quota 10 requires exactly one collection.",
            )

    @property
    def focused(self) -> bool:
        return self.quota == FOCUSED_QUOTA

    @property
    def terminal_candidate_budget(self) -> int:
        return (
            FOCUSED_TERMINAL_CANDIDATE_BUDGET
            if self.focused
            else settings.llm_pool_global_cap
        )

    @property
    def max_passages_per_document(self) -> int:
        return (
            FOCUSED_MAX_PASSAGES_PER_DOCUMENT
            if self.focused
            else STANDARD_MAX_PASSAGES_PER_DOCUMENT
        )


def resolve_search_plan(collections: Iterable[str], quota: int) -> SearchPlan:
    """Normalize collections and enforce the focused-search invariant once."""
    if quota not in ALLOWED_QUOTAS:
        raise SearchPlanError(
            "invalid_quota",
            f"Quota must be one of {sorted(ALLOWED_QUOTAS)}.",
        )

    normalized = tuple(dict.fromkeys(
        collection for collection in collections if collection in VALID_COLLECTIONS
    ))
    focused = quota == FOCUSED_QUOTA
    if focused and len(normalized) != 1:
        raise SearchPlanError(
            "focused_collection_count",
            "Quota 10 requires exactly one collection.",
        )
    if not normalized:
        raise SearchPlanError(
            "no_valid_collections",
            f"No valid collections specified. Valid values: {sorted(VALID_COLLECTIONS)}",
        )

    return SearchPlan(collections=normalized, quota=quota)
