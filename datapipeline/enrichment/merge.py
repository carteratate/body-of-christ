"""Merge Pass 1 (generation) + Pass 2 (classification) + Pass 3 (annotation) into
a final enrichment record. Validation/retry orchestration for Pass 2/3 lives in
stages/enrich.py — this stays a pure function over already-validated passes.
"""
from __future__ import annotations

from config import settings
from enrichment.schema import (
    GenerationOutput, ClassificationOutput, MergedEnrichment, MergedFacet,
)


class MergeError(Exception):
    pass


def merge(generation: GenerationOutput, classification: ClassificationOutput,
          annotation: str) -> MergedEnrichment:
    facets = generation.facets
    labels = classification.labels
    if len(facets) != len(labels):
        raise MergeError(
            f"facet/label count mismatch: {len(facets)} facets vs {len(labels)} labels")
    if not (settings.MIN_FACETS <= len(facets) <= settings.MAX_FACETS):
        raise MergeError(
            f"facet count {len(facets)} outside [{settings.MIN_FACETS}, {settings.MAX_FACETS}]")
    # Downstream of Pass 1, "facet"/"text" means the takeaway — Pass 1's raw
    # working treatment (f.text) is never what Pass 2/3 or embedding consume.
    # It's carried through as `working_text` (always, here — merge() stays pure
    # and pilot-unaware; stages/enrich.py decides whether to null it out before
    # persisting, based on settings.PILOT_MODE).
    merged = [
        MergedFacet(grounding=lab.grounding, evidence=lab.evidence, kind=lab.kind,
                    kind_secondary=lab.kind_secondary, text=f.takeaway, question=f.question,
                    working_text=f.text)
        for f, lab in zip(facets, labels)
    ]
    return MergedEnrichment(facets=merged, annotation=annotation)
