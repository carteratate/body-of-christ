import os
from ingest.summa import build_document

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "sources", "church-fathers", "summa.xml")


def test_summa_builds_one_document_with_clean_refs():
    doc = build_document(_SRC)
    assert doc.collection == "summa"
    assert doc.title.startswith("Summa")
    # Articles split into parts → many passages, none gigantic.
    assert all(len(p.content) <= 4000 for p in doc.passages)
    # Apparatus expanded in references (no Q[..]/A[..] bracket scheme).
    sample = doc.passages[0].reference
    assert "Q[" not in sample and "A[" not in sample


def test_summa_unit_labels_mark_article_parts():
    doc = build_document(_SRC)
    labels = {p.unit_label for p in doc.passages if p.unit_label}
    assert any(l and l.startswith("Objection") for l in labels) or "I answer that" in labels
