import os

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")

import logging

from config import settings
from enrichment.schema import Label
from enrichment.telemetry import EnrichmentTelemetry


def _label(facet_id="f1", grounding="explicit", kind="doctrinal", kind_secondary=None):
    return Label(facet_id=facet_id, grounding=grounding, evidence="e", kind=kind,
                 kind_secondary=kind_secondary)


def test_record_labels_tallies_by_primary_kind_and_secondary():
    t = EnrichmentTelemetry(collection="bible")
    labels = [
        _label(kind="doctrinal", kind_secondary="scriptural"),
        _label(kind="doctrinal", kind_secondary=None),
        _label(kind="moral", kind_secondary=None),
    ]
    t.record_labels(labels, evidence_warnings=[])
    assert t.labels_by_primary_kind["doctrinal"] == 2
    assert t.labels_by_primary_kind["moral"] == 1
    assert t.secondary_by_primary_kind["doctrinal"] == 1
    assert t.secondary_by_primary_kind.get("moral", 0) == 0


def test_record_labels_matches_warnings_back_to_grounding_by_index():
    t = EnrichmentTelemetry(collection="bible")
    labels = [
        _label(facet_id="f1", grounding="settled"),
        _label(facet_id="f2", grounding="inferential"),
    ]
    # warning references label[0] (settled) only
    t.record_labels(labels, evidence_warnings=["label[0] settled_consistency: ..."])
    assert t.labels_by_grounding["settled"] == 1
    assert t.labels_by_grounding["inferential"] == 1
    assert t.warned_labels_by_grounding["settled"] == 1
    assert t.warned_labels_by_grounding.get("inferential", 0) == 0


def test_record_annotation_appends_ratio():
    t = EnrichmentTelemetry(collection="bible")
    t.record_annotation(token_count=150, target=100)
    assert t.annotation_expansion_ratios == [1.5]


def test_record_annotation_ignores_zero_target():
    t = EnrichmentTelemetry(collection="bible")
    t.record_annotation(token_count=150, target=0)
    assert t.annotation_expansion_ratios == []


def test_log_summary_warns_when_batch_secondary_rate_exceeds_threshold(caplog):
    t = EnrichmentTelemetry(collection="bible")
    # 3 of 4 labels carry a secondary kind -> 75%, above the default 60% threshold.
    labels = [
        _label(facet_id="f1", kind="doctrinal", kind_secondary="scriptural"),
        _label(facet_id="f2", kind="doctrinal", kind_secondary="scriptural"),
        _label(facet_id="f3", kind="doctrinal", kind_secondary="scriptural"),
        _label(facet_id="f4", kind="doctrinal", kind_secondary=None),
    ]
    t.record_labels(labels, evidence_warnings=[])
    with caplog.at_level(logging.WARNING):
        t.log_summary()
    assert any("secondary-kind rate" in r.message for r in caplog.records)


def test_log_summary_no_warning_when_batch_secondary_rate_at_or_below_threshold():
    t = EnrichmentTelemetry(collection="bible")
    # 1 of 4 -> 25%, comfortably under the default 60% threshold.
    labels = [
        _label(facet_id="f1", kind="doctrinal", kind_secondary="scriptural"),
        _label(facet_id="f2", kind="doctrinal", kind_secondary=None),
        _label(facet_id="f3", kind="doctrinal", kind_secondary=None),
        _label(facet_id="f4", kind="doctrinal", kind_secondary=None),
    ]
    t.record_labels(labels, evidence_warnings=[])
    import logging as _logging
    logger = _logging.getLogger("enrichment.telemetry")
    records = []
    handler = _logging.Handler()
    handler.emit = lambda record: records.append(record)
    logger.addHandler(handler)
    try:
        t.log_summary()
    finally:
        logger.removeHandler(handler)
    assert not any("secondary-kind rate" in r.getMessage() for r in records)


def test_log_summary_never_raises_with_no_data():
    EnrichmentTelemetry(collection="bible").log_summary()


def test_default_saturation_threshold_is_sixty_percent():
    assert settings.SECONDARY_KIND_SATURATION_WARN_THRESHOLD == 0.60
