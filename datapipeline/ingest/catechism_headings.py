"""Corrections to the Catechism source's heading text, in one place.

`sources/catechism/ccc.json` prints a few headings wrongly. The adapter (#279: matching
the source's heading lines to the US edition) and the API's stopgap contents tree
(`services/api/scripts/build_catechism_contents.py`) both read them from here, and 1.6
(#168) and #253 are to use the same table rather than a copy. No imports: the API script
loads this file from the repo path.
"""

# Where the source's heading text is wrong. Section Two of Part One prints only its first
# sub-heading ("I. The Creeds"), which heads the section's own paragraphs (§§185–197); the
# section's title is restored and the sub-heading becomes a child node. Keyed by
# `toc_nodes` id.
TITLE_FIXES = {
    "toc-45": "SECTION TWO THE PROFESSION OF THE CHRISTIAN FAITH",
    "toc-207": "SECTION ONE MAN'S VOCATION: LIFE IN THE SPIRIT",
}
OWN_HEADING = {"toc-45": "I. The Creeds"}
# Misprints inside heading text, wherever it appears (toc nodes and page lines).
TEXT_FIXES = (("AGAlN", "AGAIN"),)
# Pages holding no numbered paragraph ("The Credo"), so no passage holds them.
UNNUMBERED = {"toc-44"}
