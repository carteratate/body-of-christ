"""Whether a passage's unit label is worth showing a model, and why.

`unit_label` names a passage's role inside its document. For the Summa that role can
INVERT the passage's meaning — 10,517 chunks (39.3% of the collection) are objections
Aquinas states in order to REFUTE — so every model that reads a passage needs it: both
rerankers, and the explanation model that writes the prose a user actually reads.

Three call sites need the same decision, which is why it lives here rather than being
re-implemented in each: `rerank_docs` (Cohere document + listwise card),
`llm_rerank.pointwise` (the per-collection passage record), and `steps.explain`.
"""
from __future__ import annotations


def display_role(unit_label: str | None, reference: str | None) -> str | None:
    """The role worth adding to a passage header, or None to add nothing.

    Suppressed when the reference already contains the label, which is not cosmetic
    dedup. Measured against the live corpus (2026-08-20): 16,730 of the 16,829
    labelled non-Summa chunks repeat their label in the reference — "Code of Canon
    Law, Can. 33" alongside `unit_label="Can. 33"` — so emitting it would add noise to
    the one field a model reads for provenance, and would hand it a bare locator right
    after telling it that some roles invert a passage's meaning.

    The remaining 99 are Bible chunks whose label is a bare ordinal ("1") the reference
    ("Baruch 6") does not contain; those still emit, which is harmless because the
    prompts carve locators out explicitly.

    The case this exists for always passes through: 0 of 26,750 Summa references
    contain their dialectical part, because a Summa reference names the article's
    QUESTION ("Article 6 - Whether it is lawful to kill the innocent?") and never
    which side of it the passage argues.
    """
    if not unit_label:
        return None
    if reference and unit_label in reference:
        return None
    return unit_label
