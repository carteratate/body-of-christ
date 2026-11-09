"""The one genre vocabulary (D5, D11): lowercase and hyphenated everywhere.

1.3b and every later adapter import from here, and 2.2a seeds its `corpus_genres` table
from this module. Adding a genre is a PR that changes this module and adds the matching
`corpus_genres` row in a migration.

A papal document has two labels (Carter, 9 Nov 2026). Its genre is its kind, what it
is: the label on its card and the genre filter. Its form is how the papal chancery
issued it, a bull or a brief, and is empty where no chancery form is named (nearly every
modern document). Ineffabilis Deus is an apostolic constitution issued as a bull; Probe
Nostis is an encyclical issued as a brief. 0044 seeds `corpus_forms` from `PAPAL_FORMS`.
"""
from __future__ import annotations

PAPAL_GENRES = ("encyclical", "apostolic-exhortation", "apostolic-letter",
                "apostolic-constitution", "motu-proprio", "letter")
PAPAL_FORMS = ("bull", "brief")
CURIA_GENRES = ("declaration", "instruction", "doctrinal-note", "note", "response", "norms",
                "considerations", "commentary")
CATECHISM_AND_LAW_GENRES = ("catechism", "compendium", "code", "law")
WRITER_GENRES = ("treatise", "manual", "sermon", "commentary", "poem", "rule")
OTHER = "other"

# The ordered union, each value once (`commentary` is both a Curia and a writer genre).
ALL_GENRES = tuple(dict.fromkeys(
    PAPAL_GENRES + CURIA_GENRES + CATECHISM_AND_LAW_GENRES + WRITER_GENRES + (OTHER,)))
