"""Pydantic models for the three-pass enrichment (generation, classification, annotation)."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

GROUNDING_VALUES: tuple[str, ...] = ("explicit", "settled", "inferential")
KIND_VALUES: tuple[str, ...] = (
    "doctrinal", "scriptural", "typological", "philosophical",
    "moral", "historical", "devotional", "juridical",
)

Grounding = Literal["explicit", "settled", "inferential"]
Kind = Literal[
    "doctrinal", "scriptural", "typological", "philosophical",
    "moral", "historical", "devotional", "juridical",
]


class GenFacet(BaseModel):
    """Field order (text -> takeaway -> question) is intentional and matches the
    prompt's instructions: the takeaway is generated conditioned on the text.
    `text` is the working treatment, discarded downstream unless PILOT_MODE is on.
    `takeaway` is the indexed/classified artifact — everything downstream of Pass 1
    (Pass 2, Pass 3, embedding) consumes the takeaway, never `text`."""
    text: str = Field(description="2-5 sentence working treatment of the insight.")
    takeaway: str = Field(description="1-2 sentence, 30-70 word distilled claim; the indexed artifact.")
    question: str = Field(description="The single canonical question this facet's takeaway answers.")


class GenerationOutput(BaseModel):
    """Pass 1 output. No annotation — that is assembled in Pass 3 from Pass 2's labels."""
    facets: list[GenFacet]


class IdentifiedFacet(BaseModel):
    """A Pass 1 facet plus its stable, deterministic `id` (f1, f2, ...),
    assigned by `identify_facets()` from its position in Pass 1's output.
    This is the canonical representation used everywhere downstream of Pass 1
    — Pass 2 classification, Pass 3 annotation assembly, and merge — so every
    consumer joins Pass 2's returned labels back to the right facet by
    `facet_id`, never by trusting raw array position alone."""
    id: str
    text: str
    takeaway: str
    question: str


def identify_facets(facets: list[GenFacet]) -> list[IdentifiedFacet]:
    """Assigns each facet a stable, deterministic id (f1, f2, ...) from its
    position in Pass 1's output. Facet order is fixed the moment Pass 1
    succeeds and never changes afterward, so recomputing ids from position is
    safe and idempotent to call every time a `list[GenFacet]` is obtained —
    both on fresh generation output and when reconstructing facets from a
    cache row, including legacy rows written before facet ids existed (which
    simply have no `id` key at all; identify_facets() assigns them anyway)."""
    return [
        IdentifiedFacet(id=f"f{i + 1}", text=f.text, takeaway=f.takeaway, question=f.question)
        for i, f in enumerate(facets)
    ]


class Label(BaseModel):
    facet_id: str
    grounding: Grounding
    evidence: str
    kind: Kind
    kind_secondary: Kind | None = None


class ClassificationOutput(BaseModel):
    """Pass 2 output. `labels` is parallel to Pass 1's `facets`."""
    labels: list[Label]


class AnnotationOutput(BaseModel):
    """Pass 3 output."""
    annotation: str


class MergedFacet(BaseModel):
    """`text` holds Pass 1's `takeaway` (the naming convention downstream of Pass 1
    is that "facet"/"text" means the takeaway — there is no separate `takeaway`
    field here, by design, to avoid two names for one artifact).
    `working_text` is Pass 1's raw working treatment, nullable; populated only
    when PILOT_MODE is on (see stages/enrich.py), for pilot-batch review only.
    `id` is the facet's stable id (f1, f2, ...) from `identify_facets()`;
    nullable so records predating facet ids (fixtures, legacy cache rows)
    still validate — new records always populate it via merge()."""
    id: str | None = None
    grounding: Grounding
    evidence: str
    kind: Kind
    kind_secondary: Kind | None = None
    text: str
    question: str
    working_text: str | None = None


class MergedEnrichment(BaseModel):
    facets: list[MergedFacet]
    annotation: str


def generation_tool_schema() -> dict:
    return GenerationOutput.model_json_schema()


def classification_tool_schema() -> dict:
    return ClassificationOutput.model_json_schema()


def annotation_tool_schema() -> dict:
    return AnnotationOutput.model_json_schema()
