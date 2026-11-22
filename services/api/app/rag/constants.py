VALID_COLLECTIONS: frozenset[str] = frozenset({
    "bible",
    "catechism",
    "church-fathers",
    "encyclicals",
    "apostolic-exhortations",
    "papal-documents",
    "canon-law",
    "summa",
    "medieval",
    "councils",
})

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

_PAPAL_COLLECTIONS = ("encyclicals", "apostolic-exhortations", "papal-documents")

# Only these collections can be narrowed; a scope for any other is refused.
GENRES_BY_COLLECTION: dict[str, frozenset[str]] = {
    collection: frozenset(PAPAL_GENRES + (OTHER_GENRE,)) for collection in _PAPAL_COLLECTIONS
}
ISSUERS_BY_COLLECTION: dict[str, frozenset[str]] = {
    collection: frozenset(PAPAL_ISSUERS) for collection in _PAPAL_COLLECTIONS
}
