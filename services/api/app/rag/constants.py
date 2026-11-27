# The collections (corpus cleanup 5.1b): `papal` merged the three papal collections,
# `church-law` was `canon-law` and `theologians` was `medieval` (Carter, 22 Nov 2026).
# The old keys were removed in 5.1b.4, after 5.1b.3 rewrote every stored value; the web
# still reads them from a browser's own storage (`LEGACY_COLLECTIONS` in
# apps/web/src/lib/collections.ts), so it never sends them.
#
# `roman-curia` (5.3a) is accepted before its documents are published, so a search of it
# finds nothing until then; the web lists it in `UNRELEASED_COLLECTIONS`, offering it
# only once its release PR moves it into `COLLECTIONS`.
CANONICAL_COLLECTIONS: frozenset[str] = frozenset({
    "bible",
    "catechism",
    "church-fathers",
    "papal",
    "church-law",
    "summa",
    "theologians",
    "councils",
    "roman-curia",
})

VALID_COLLECTIONS: frozenset[str] = CANONICAL_COLLECTIONS


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
    "pope-boniface-viii", "pope-martin-v", "pope-leo-x", "pope-paul-iii", "pope-benedict-xiv",
    "pope-clement-xiv", "pope-pius-vii", "pope-leo-xii", "pope-pius-viii",
    "pope-gregory-xvi", "pope-pius-ix", "pope-leo-xiii", "pope-pius-x",
    "pope-benedict-xv", "pope-pius-xi", "pope-pius-xii", "pope-john-xxiii",
    "pope-paul-vi", "pope-john-paul-ii", "pope-benedict-xvi", "pope-francis",
    "pope-leo-xiv",
)

# The Roman Curia's offices, by the slug in `documents.issuer` (5.3a): the Dicastery for
# the Doctrine of the Faith, under all three names it has printed. 5.3b adds others.
CURIA_ISSUERS: tuple[str, ...] = ("ddf",)

# Only these collections can be narrowed; a scope for any other is refused. A Roman Curia
# document's genre is its own kind (a declaration, an instruction), or `letter`.
GENRES_BY_COLLECTION: dict[str, frozenset[str]] = {
    "papal": frozenset(PAPAL_GENRES + (OTHER_GENRE,)),
    "roman-curia": frozenset(CURIA_GENRES + ("letter", OTHER_GENRE)),
}
ISSUERS_BY_COLLECTION: dict[str, frozenset[str]] = {
    "papal": frozenset(PAPAL_ISSUERS),
    "roman-curia": frozenset(CURIA_ISSUERS),
}
# The work filter: the documents a search of these collections can be narrowed to, by
# document ID (the registry's frozen `document_id`). By document, not genre, because
# the Catechism of the Catholic Church and the Roman Catechism share a genre. Another
# collection (Councils, Church Fathers) turns it on by gaining an entry here and in
# `SCOPED_COLLECTIONS` in apps/web/src/lib/collection-scopes.ts.
DOCUMENTS_BY_COLLECTION: dict[str, frozenset[str]] = {
    "catechism": frozenset({
        "9679c400-d314-5394-b916-f6fc27b50104",  # Catechism of the Catholic Church
        "800373b1-d6c8-5a26-8910-8d1485b224c2",  # Compendium of the Catechism
        "c6d78d5e-5f23-5f86-b0ca-97a741e186bf",  # Roman Catechism (Council of Trent)
    }),
}
