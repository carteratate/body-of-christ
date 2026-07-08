"""Merge Call 1 (generation) + Call 2 (classification) into a final enrichment."""
from __future__ import annotations

from config import settings
from enrichment.schema import (
    GenerationOutput, ClassificationOutput, MergedEnrichment, MergedFacet,
)


class MergeError(Exception):
    pass


def merge(generation: GenerationOutput, classification: ClassificationOutput) -> MergedEnrichment:
    facets = generation.facets
    labels = classification.labels
    if len(facets) != len(labels):
        raise MergeError(
            f"facet/label count mismatch: {len(facets)} facets vs {len(labels)} labels")
    if not (settings.MIN_FACETS <= len(facets) <= settings.MAX_FACETS):
        raise MergeError(
            f"facet count {len(facets)} outside [{settings.MIN_FACETS}, {settings.MAX_FACETS}]")
    merged = [
        MergedFacet(confidence=lab.confidence, kind=lab.kind, text=f.text, question=f.question)
        for f, lab in zip(facets, labels)
    ]
    return MergedEnrichment(facets=merged, annotation=generation.annotation)
