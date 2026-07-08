"""Shared building blocks for the per-collection generation system prompt."""
from __future__ import annotations

_FACET_INSTRUCTIONS = """\
Produce between 2 and 12 FACETS for this passage. A short article may warrant 2;
a rich passage may warrant 10-12. Each facet:
- Is written as an ASSERTION, not a question. 2-4 purposeful sentences.
- Covers exactly ONE interpretive angle. Every sentence adds a distinct semantic anchor.
- Must differ from the other facets: each facet has at least one angle none of the others have.
- Carries exactly one QUESTION: the single most likely question this specific facet is the
  canonical answer to — not a generic question the whole passage could answer.

EPISTEMIC CONSTRAINT: Typological and inferred readings must NOT be written as declarative
teaching claims. A facet about typology reads as traditional interpretation, not defined doctrine.
"""

_ANNOTATION_INSTRUCTIONS = """\
Also produce an ANNOTATION: one global summary plus one labeled segment per facet.
Hard cap ~400-600 tokens. Format exactly:

SUMMARY: <1-2 sentences: primary content and overall doctrinal scope>

[<KIND> | <confidence>]: <1-2 tight sentences>
[<KIND> | <confidence>]: <1-2 tight sentences>
...

Where <KIND> is one of DOCTRINAL, SCRIPTURAL, TYPOLOGICAL, PHILOSOPHICAL, MORAL, HISTORICAL,
DEVOTIONAL and <confidence> is one of explicit, traditional, inferential (your best judgment of
each facet's character — final labels are assigned separately).

TWO INVARIANTS:
1. The annotation must cover EVERY facet angle — each facet appears in its own labeled segment.
2. The annotation must NOT convert implied or typological readings into declarative teaching claims.
"""

_OUTPUT_CONTRACT = """\
Return your result ONLY by calling the provided tool with `facets` (each having `text` and
`question`) and `annotation`. Do not assign confidence or kind labels — that is a separate step.
"""


def compose_generation_system(guidance: str) -> str:
    return (
        "You are a Catholic theologian and librarian enriching a passage for a theology "
        "search engine. Your output powers semantic retrieval, so every facet must add "
        "distinct, searchable meaning.\n\n"
        f"COLLECTION GUIDANCE:\n{guidance}\n\n"
        f"{_FACET_INSTRUCTIONS}\n{_ANNOTATION_INSTRUCTIONS}\n{_OUTPUT_CONTRACT}"
    )
