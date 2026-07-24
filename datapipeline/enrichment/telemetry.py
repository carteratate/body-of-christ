"""Non-blocking batch telemetry for enrichment runs.

Nothing here ever raises or changes what gets written — it only counts and,
at the end of a collection's run, logs warnings when a rate crosses a
configured threshold. Three independent concerns are tracked, one counter
family each:

- secondary-kind saturation (item 4): what fraction of facets carry a
  secondary kind, overall and broken down by primary kind, since an
  "exceptional only" prompt rule (enrichment/prompts/classification.py rule
  8) is only as good as our ability to notice when the model drifts back
  toward decorative secondary kinds at scale.
- evidence-warning rate by grounding (item 6): what fraction of settled/
  inferential labels trip a validate_evidence_style() warning, broken down
  by grounding tier.
- annotation length expansion (item 5): the distribution of
  token_count / target ratios across a collection's annotations, so a
  systematic drift toward the soft margin is visible in aggregate even when
  no single annotation crosses it.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentTelemetry:
    collection: str
    labels_by_primary_kind: Counter = field(default_factory=Counter)
    secondary_by_primary_kind: Counter = field(default_factory=Counter)
    labels_by_grounding: Counter = field(default_factory=Counter)
    warned_labels_by_grounding: Counter = field(default_factory=Counter)
    annotation_expansion_ratios: list[float] = field(default_factory=list)

    def record_labels(self, labels, evidence_warnings: list[str]) -> None:
        """Call once per chunk with its resolved Pass 2 labels and the
        (possibly empty) warnings list `validate_evidence_style` returned for
        them. Warnings are matched back to labels by the `label[i]` index
        every validate_evidence_style warning string is prefixed with."""
        warned_indices: set[int] = set()
        for w in evidence_warnings:
            # every warning starts "label[<i>] ..." — see validate_evidence_style
            try:
                idx = int(w.split("label[", 1)[1].split("]", 1)[0])
                warned_indices.add(idx)
            except (IndexError, ValueError):
                continue
        for i, lab in enumerate(labels):
            self.labels_by_primary_kind[lab.kind] += 1
            if lab.kind_secondary:
                self.secondary_by_primary_kind[lab.kind] += 1
            self.labels_by_grounding[lab.grounding] += 1
            if i in warned_indices:
                self.warned_labels_by_grounding[lab.grounding] += 1

    def record_annotation(self, token_count: int, target: int) -> None:
        if target > 0:
            self.annotation_expansion_ratios.append(token_count / target)

    def log_summary(self) -> None:
        """Logs one warning per bucket whose secondary-kind rate crosses the
        configured saturation threshold, plus informational summaries for the
        other two counter families. Never raises."""
        total_labels = sum(self.labels_by_primary_kind.values())
        total_secondary = sum(self.secondary_by_primary_kind.values())
        threshold = settings.SECONDARY_KIND_SATURATION_WARN_THRESHOLD

        if total_labels:
            batch_rate = total_secondary / total_labels
            if batch_rate > threshold:
                logger.warning(
                    "enrich telemetry: collection %s secondary-kind rate %.0f%% "
                    "of %d labels exceeds the %.0f%% saturation threshold",
                    self.collection, batch_rate * 100, total_labels, threshold * 100)
            for kind, count in self.labels_by_primary_kind.items():
                secondary = self.secondary_by_primary_kind.get(kind, 0)
                rate = secondary / count if count else 0.0
                if rate > threshold:
                    logger.warning(
                        "enrich telemetry: collection %s primary kind '%s' secondary-kind "
                        "rate %.0f%% of %d labels exceeds the %.0f%% saturation threshold",
                        self.collection, kind, rate * 100, count, threshold * 100)

        for grounding, count in self.labels_by_grounding.items():
            warned = self.warned_labels_by_grounding.get(grounding, 0)
            if count:
                logger.info(
                    "enrich telemetry: collection %s grounding '%s' evidence-warning "
                    "rate %.0f%% (%d/%d labels)",
                    self.collection, grounding, 100 * warned / count, warned, count)

        if self.annotation_expansion_ratios:
            ratios = self.annotation_expansion_ratios
            avg = sum(ratios) / len(ratios)
            logger.info(
                "enrich telemetry: collection %s annotation length ratio "
                "(actual/target) avg=%.2f max=%.2f over %d annotation(s)",
                self.collection, avg, max(ratios), len(ratios))
