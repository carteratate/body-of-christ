"""The one genre vocabulary (D5, D11): lowercase and hyphenated everywhere.

1.3b and every later adapter import from here, and 2.2a seeds its `corpus_genres` table
from this module. Adding a genre is a PR that changes this module and adds the matching
`corpus_genres` row in a migration.
"""
from __future__ import annotations

PAPAL_GENRES = ("encyclical", "apostolic-exhortation", "apostolic-letter",
                "apostolic-constitution", "motu-proprio", "bull", "letter")
CURIA_GENRES = ("declaration", "instruction", "doctrinal-note", "note", "response", "norms",
                "considerations", "commentary")
CATECHISM_AND_LAW_GENRES = ("catechism", "compendium", "code", "law")
WRITER_GENRES = ("treatise", "manual", "sermon", "commentary", "poem", "rule")
OTHER = "other"

# The ordered union, each value once (`commentary` is both a Curia and a writer genre).
ALL_GENRES = tuple(dict.fromkeys(
    PAPAL_GENRES + CURIA_GENRES + CATECHISM_AND_LAW_GENRES + WRITER_GENRES + (OTHER,)))
