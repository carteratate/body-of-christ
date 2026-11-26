"""Resolve a submitted search into one validated execution plan."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from app.config import settings
from app.rag.collection_scope import CollectionScope
from app.rag.constants import (
    DOCUMENTS_BY_COLLECTION, GENRES_BY_COLLECTION, ISSUERS_BY_COLLECTION, VALID_COLLECTIONS,
)

ALLOWED_QUOTAS: frozenset[int] = frozenset({3, 4, 5, 10})
FOCUSED_QUOTA = 10
FOCUSED_TERMINAL_CANDIDATE_BUDGET = 25
FOCUSED_MAX_PASSAGES_PER_SOURCE = 4
STANDARD_MAX_PASSAGES_PER_SOURCE = 2


class SearchPlanError(ValueError):
    """A stable validation failure that HTTP routes can translate consistently."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


# Codes added by 5.1a. Their HTTP detail is `{"code", "message"}`, so a client can tell
# them apart; the older codes keep their plain-string detail.
SCOPE_ERROR_CODES: frozenset[str] = frozenset({
    "invalid_genre", "invalid_issuer", "invalid_document"})


def http_detail(exc: SearchPlanError) -> str | dict[str, str]:
    if exc.code in SCOPE_ERROR_CODES:
        return {"code": exc.code, "message": exc.detail}
    return exc.detail


@dataclass(frozen=True)
class SearchPlan:
    collections: tuple[str, ...]
    quota: int
    # Only collections the user narrowed (5.1a); every other collection is searched
    # whole. A genre or issuer selection never counts as a collection, so it changes
    # nothing about focused search.
    scopes: tuple[CollectionScope, ...] = ()

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
        scoped = [scope.collection for scope in self.scopes]
        if len(set(scoped)) != len(scoped) or set(scoped) - set(self.collections):
            raise SearchPlanError(
                "invalid_scopes", "Search plan scopes must name its collections once each."
            )

    def saved_scopes(self) -> dict[str, dict[str, list[str]]]:
        """The selection as a request sends it, for `searches.filters`: per narrowed
        collection, the genres and issuers searched. Empty when nothing is narrowed."""
        saved: dict[str, dict[str, list[str]]] = {}
        for scope in self.scopes:
            entry: dict[str, list[str]] = {}
            if scope.excluded_genres:
                entry["genres"] = sorted(
                    GENRES_BY_COLLECTION[scope.collection] - scope.excluded_genres)
            if scope.excluded_issuers:
                entry["issuers"] = sorted(
                    ISSUERS_BY_COLLECTION[scope.collection] - scope.excluded_issuers)
            if scope.excluded_documents:
                entry["documents"] = sorted(
                    DOCUMENTS_BY_COLLECTION[scope.collection] - scope.excluded_documents)
            saved[scope.collection] = entry
        return saved

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
    def max_passages_per_source(self) -> int:
        return (
            FOCUSED_MAX_PASSAGES_PER_SOURCE
            if self.focused
            else STANDARD_MAX_PASSAGES_PER_SOURCE
        )


def _excluded(
    collection: str,
    selected: Iterable[str] | None,
    vocabulary: Mapping[str, frozenset[str]],
    code: str,
    noun: str,
) -> frozenset[str]:
    """The values of `collection` the selection leaves out. None (absent) is all."""
    if selected is None:
        return frozenset()
    chosen = set(selected)
    allowed = vocabulary.get(collection)
    if allowed is None:
        raise SearchPlanError(code, f"{collection} cannot be narrowed by {noun}.")
    if not chosen:
        raise SearchPlanError(code, f"Choose at least one {noun} for {collection}.")
    if chosen - allowed:
        raise SearchPlanError(
            code, f"Unknown {noun} for {collection}: {sorted(chosen - allowed)}",
        )
    return allowed - chosen


def resolve_scopes(
    collections: tuple[str, ...],
    scope_filters: Mapping[str, Mapping[str, Iterable[str] | None]] | None,
) -> tuple[CollectionScope, ...]:
    """Validate `filters.scopes` against the genre, issuer and document vocabularies.

    Every scope sent is validated, so a bad value is refused whichever collections are
    selected; only the scopes of collections the search includes apply. A selection of
    every value is the whole collection, so it adds no filter."""
    resolved: dict[str, CollectionScope] = {}
    for collection, selection in (scope_filters or {}).items():
        if not selection:
            continue
        resolved[collection] = CollectionScope(
            collection,
            excluded_genres=_excluded(
                collection, selection.get("genres"), GENRES_BY_COLLECTION,
                "invalid_genre", "genre",
            ),
            excluded_issuers=_excluded(
                collection, selection.get("issuers"), ISSUERS_BY_COLLECTION,
                "invalid_issuer", "issuer",
            ),
            excluded_documents=_excluded(
                collection, selection.get("documents"), DOCUMENTS_BY_COLLECTION,
                "invalid_document", "work",
            ),
        )
    scopes = [resolved[c] for c in collections if c in resolved and resolved[c].narrowed]
    return tuple(scopes)


def resolve_search_plan(
    collections: Iterable[str],
    quota: int,
    scope_filters: Mapping[str, Mapping[str, Iterable[str] | None]] | None = None,
) -> SearchPlan:
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

    return SearchPlan(
        collections=normalized, quota=quota,
        scopes=resolve_scopes(normalized, scope_filters),
    )
