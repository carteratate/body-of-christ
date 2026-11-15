"""Corrections to the Catechism source's heading text, in one place.

`sources/catechism/ccc.json` prints a few headings wrongly. The adapter reads them from
here for three things: matching the source's heading lines to the US edition (#279), the
chapter labels (1.6, #168) and the contents tree (#253).
"""

# Where the source's heading text is wrong. Section Two of Part One prints only its first
# sub-heading ("I. The Creeds"), which heads the section's own paragraphs (§§185–197), so
# the section's title is restored. Keyed by `toc_nodes` id.
TITLE_FIXES = {
    "toc-45": "SECTION TWO THE PROFESSION OF THE CHRISTIAN FAITH",
    "toc-207": "SECTION ONE MAN'S VOCATION: LIFE IN THE SPIRIT",
}
# Misprints inside heading text, wherever it appears (toc nodes and page lines).
TEXT_FIXES = (("AGAlN", "AGAIN"), ("THE HUMAN COMMUNION", "THE HUMAN COMMUNITY"))
# Pages holding no numbered paragraph ("The Credo"), so no passage holds them.
UNNUMBERED = {"toc-44"}
