from typing import NamedTuple

# The collections after corpus cleanup 5.1b, and the only keys the web will send once
# 5.1b.2 ships. `papal` merges the three papal collections; `church-law` is `canon-law`
# and `theologians` is `medieval`, renamed (Carter confirmed the keys and labels,
# 22 Nov 2026).
CANONICAL_COLLECTIONS: frozenset[str] = frozenset({
    "bible",
    "catechism",
    "church-fathers",
    "papal",
    "church-law",
    "summa",
    "theologians",
    "councils",
})


class LegacyCollection(NamedTuple):
    """What an old key means in the new vocabulary: its canonical collection, read
    whole, or only some of that collection's genres. `genres` reads those genres;
    `without_genres` reads every other genre and documents with none."""
    canonical: str
    genres: frozenset[str] | None = None
    without_genres: frozenset[str] | None = None


# The old keys (5.1b.1 to 5.1b.4). The API accepts them with today's meaning until
# 5.1b.4 removes them, whether or not 5.1b.3 has rewritten the stored values
# (`collection_scope.reads`). `papal-documents` takes the papal documents that are
# neither encyclicals nor exhortations, so the three old keys still split the merged
# collection between them.
_ENCYCLICAL = frozenset({"encyclical"})
_EXHORTATION = frozenset({"apostolic-exhortation"})
LEGACY_COLLECTIONS: dict[str, LegacyCollection] = {
    "encyclicals": LegacyCollection("papal", genres=_ENCYCLICAL),
    "apostolic-exhortations": LegacyCollection("papal", genres=_EXHORTATION),
    "papal-documents": LegacyCollection("papal", without_genres=_ENCYCLICAL | _EXHORTATION),
    "canon-law": LegacyCollection("church-law"),
    "medieval": LegacyCollection("theologians"),
}

VALID_COLLECTIONS: frozenset[str] = CANONICAL_COLLECTIONS | frozenset(LEGACY_COLLECTIONS)


# Genre and issuer filters (corpus cleanup 5.1a). The genre values are a copy of the
# datapipeline's one vocabulary, `datapipeline/registry/genres.py`, which the API cannot
# import; `test_api_genres_match_registry_module` fails on any difference. Issuers are
# the slugs in `documents.issuer` (the pope, for a papal document); every issuer
# `datapipeline/registry/works.json` gives a papal collection must be listed here
# (`test_papal_issuers_cover_the_registry`). Ordered by pontificate.
PAPAL_GENRES: tuple[str, ...] = (
    "encyclical", "apostolic-exhortation", "apostolic-letter",
    "apostolic-constitution", "motu-proprio", "letter",
)
CURIA_GENRES: tuple[str, ...] = (
    "declaration", "instruction", "doctrinal-note", "note", "response", "norms",
    "considerations", "commentary",
)
CATECHISM_AND_LAW_GENRES: tuple[str, ...] = ("catechism", "compendium", "code", "law")
WRITER_GENRES: tuple[str, ...] = ("treatise", "manual", "sermon", "commentary", "poem", "rule")
OTHER_GENRE = "other"

PAPAL_ISSUERS: tuple[str, ...] = (
    "pope-boniface-viii", "pope-leo-x", "pope-paul-iii", "pope-benedict-xiv",
    "pope-clement-xiv", "pope-pius-vii", "pope-leo-xii", "pope-pius-viii",
    "pope-gregory-xvi", "pope-pius-ix", "pope-leo-xiii", "pope-pius-x",
    "pope-benedict-xv", "pope-pius-xi", "pope-pius-xii", "pope-john-xxiii",
    "pope-paul-vi", "pope-john-paul-ii", "pope-benedict-xvi", "pope-francis",
    "pope-leo-xiv",
)

_PAPAL_COLLECTIONS = ("papal", "encyclicals", "apostolic-exhortations", "papal-documents")

# Only these collections can be narrowed; a scope for any other is refused.
GENRES_BY_COLLECTION: dict[str, frozenset[str]] = {
    collection: frozenset(PAPAL_GENRES + (OTHER_GENRE,)) for collection in _PAPAL_COLLECTIONS
}
ISSUERS_BY_COLLECTION: dict[str, frozenset[str]] = {
    collection: frozenset(PAPAL_ISSUERS) for collection in _PAPAL_COLLECTIONS
}
