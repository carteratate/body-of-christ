"""What part of one collection a search reads: its genres and issuers (item 5.1a).

A request names what to search inside a collection (`filters.scopes`), and the scope
stores the complement: the values the user turned off. Retrieval excludes only those,
by the plan's rule "filters exclude only explicit values", so a document with no genre
or no issuer is searched under every selection. A scope that excludes nothing is the
whole collection, and its filters are exactly today's.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CollectionScope:
    collection: str
    excluded_genres: frozenset[str] = field(default_factory=frozenset)
    excluded_issuers: frozenset[str] = field(default_factory=frozenset)

    @property
    def narrowed(self) -> bool:
        return bool(self.excluded_genres or self.excluded_issuers)

    def to_qdrant_filter(self, must_not: list | None = None):
        """The query filter for this collection. `must_not` carries conditions every
        search applies (the `searchable` flag); with nothing excluded the filter is the
        one search built before scopes existed. A point without `genre` or `issuer`
        matches no `must_not` condition on it, so it stays searchable."""
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        excluded = [
            FieldCondition(key=key, match=MatchAny(any=sorted(values)))
            for key, values in (("genre", self.excluded_genres),
                                ("issuer", self.excluded_issuers))
            if values
        ]
        if excluded:
            must_not = [*(must_not or []), *excluded]
        return Filter(
            must=[FieldCondition(key="collection", match=MatchValue(value=self.collection))],
            must_not=must_not,
        )

    def to_sql(self, alias: str, first_param: int) -> tuple[str, list[list[str]]]:
        """An `AND …` clause on the documents alias, numbered from `first_param`, and
        its arguments; ("", []) when nothing is excluded. The NULL branch is required:
        `NOT (NULL = ANY(…))` is NULL, which would drop every document without a value."""
        clauses: list[str] = []
        args: list[list[str]] = []
        for column, values in (("genre", self.excluded_genres),
                               ("issuer", self.excluded_issuers)):
            if values:
                n = first_param + len(args)
                clauses.append(
                    f"\n      AND ({alias}.{column} IS NULL"
                    f" OR {alias}.{column} <> ALL(${n}::text[]))"
                )
                args.append(sorted(values))
        return "".join(clauses), args

