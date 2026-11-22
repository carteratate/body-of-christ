"""What part of one collection a search reads: its genres and issuers (item 5.1a).

A request names what to search inside a collection (`filters.scopes`), and the scope
stores the complement: the values the user turned off. Retrieval excludes only those,
by the plan's rule "filters exclude only explicit values", so a document with no genre
or no issuer is searched under every selection. A scope that excludes nothing is the
whole collection, and its filters are exactly today's.

A scope also says which stored `collection` values its key reads (`reads`, item
5.1b.1), so old and new keys both work before and after 5.1b.3 rewrites the stored
values. A key 5.1b leaves alone reads only itself, with today's filters.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.rag.constants import CANONICAL_COLLECTIONS, LEGACY_COLLECTIONS, LegacyCollection


@dataclass(frozen=True)
class StoredRead:
    """The stored values a requested key reads: `whole` entirely, and `part`, when
    set, the canonical value restricted to the old key's genres (a pair of that value
    and its `LegacyCollection`)."""
    whole: tuple[str, ...]
    part: tuple[str, LegacyCollection] | None = None


def reads(key: str) -> StoredRead:
    """What a requested key reads, before or after the stored values are rewritten.

    A new key reads its own value and every old value mapped to it. An old key reads
    its own value, and the new one whole (`canon-law`, `medieval`) or only its genres
    (the three papal keys), so after the rewrite `encyclicals` still returns only
    encyclicals; before it, the new value has no rows."""
    legacy = LEGACY_COLLECTIONS.get(key)
    if legacy is not None:
        if legacy.genres is None and legacy.without_genres is None:
            return StoredRead((key, legacy.canonical))
        return StoredRead((key,), (legacy.canonical, legacy))
    if key in CANONICAL_COLLECTIONS:
        old = tuple(k for k, v in LEGACY_COLLECTIONS.items() if v.canonical == key)
        return StoredRead((key, *old))
    return StoredRead((key,))


def requested_label(stored: str, requested) -> str:
    """The key of `requested` whose search reads `stored`, for labelling a saved
    passage as its search did; the stored value when none does. A key that reads it
    whole wins. Otherwise an old papal key reads the new value by genre, which the
    stored value alone cannot settle, so it is used only when it is the one such key
    saved; with several, the passage keeps the new value."""
    keys = [k for k in (requested if isinstance(requested, list) else ())
            if isinstance(k, str)]
    for key in keys:
        if stored in reads(key).whole:
            return key
    by_genre = [k for k in keys if (part := reads(k).part) and part[0] == stored]
    return by_genre[0] if len(by_genre) == 1 else stored


@dataclass(frozen=True)
class CollectionScope:
    collection: str
    excluded_genres: frozenset[str] = field(default_factory=frozenset)
    excluded_issuers: frozenset[str] = field(default_factory=frozenset)

    @property
    def narrowed(self) -> bool:
        return bool(self.excluded_genres or self.excluded_issuers)

    def to_qdrant_filter(self, must_not: list | None = None, *, genre_indexed: bool = False):
        """The query filter for this collection. `must_not` carries conditions every
        search applies (the `searchable` flag); with nothing excluded the filter is the
        one search built before scopes existed. A point without `genre` or `issuer`
        matches no `must_not` condition on it, so it stays searchable.

        An old papal key reads the new value's genres only when the read collection
        indexes `genre` (`genre_indexed`): strict mode refuses a filter on an unindexed
        field, and a collection without the index (the pre-republish `chunks`) holds
        no new values, so its filter is today's."""
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        excluded = [
            FieldCondition(key=key, match=MatchAny(any=sorted(values)))
            for key, values in (("genre", self.excluded_genres),
                                ("issuer", self.excluded_issuers))
            if values
        ]
        if excluded:
            must_not = [*(must_not or []), *excluded]
        read = reads(self.collection)
        whole = FieldCondition(
            key="collection",
            match=(MatchValue(value=read.whole[0]) if len(read.whole) == 1
                   else MatchAny(any=list(read.whole))),
        )
        if read.part is None or not genre_indexed:
            return Filter(must=[whole], must_not=must_not)
        value, legacy = read.part
        part_must = [FieldCondition(key="collection", match=MatchValue(value=value))]
        part_must_not = None
        if legacy.genres is not None:
            part_must.append(
                FieldCondition(key="genre", match=MatchAny(any=sorted(legacy.genres))))
        else:
            part_must_not = [
                FieldCondition(key="genre", match=MatchAny(any=sorted(legacy.without_genres)))]
        return Filter(
            should=[Filter(must=[whole]), Filter(must=part_must, must_not=part_must_not)],
            must_not=must_not,
        )

    def collection_sql(
        self, alias: str, first_param: int, *, genre_column: bool,
    ) -> tuple[str, str | list[str], list[str | list[str]]]:
        """The condition on `alias.collection`, the argument bound to `$1`, and the
        arguments numbered from `first_param`. A key 5.1b leaves alone gives today's
        `alias.collection = $1` with the key; a key reading several values binds them
        as an array. An old papal key reads the new value's genres only where the
        database has `documents.genre` (`genre_column`)."""
        read = reads(self.collection)
        if len(read.whole) == 1:
            condition, value = f"{alias}.collection = $1", read.whole[0]
        else:
            condition, value = f"{alias}.collection = ANY($1::text[])", list(read.whole)
        if read.part is None or not genre_column:
            return condition, value, []
        stored, legacy = read.part
        n = first_param
        if legacy.genres is not None:
            genre = f"{alias}.genre = ANY(${n + 1}::text[])"
            genres = sorted(legacy.genres)
        else:
            genre = f"({alias}.genre IS NULL OR {alias}.genre <> ALL(${n + 1}::text[]))"
            genres = sorted(legacy.without_genres)
        return (f"({condition} OR ({alias}.collection = ${n}::text AND {genre}))",
                value, [stored, genres])

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

