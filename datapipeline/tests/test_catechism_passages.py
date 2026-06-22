from ingest.catechism import build_document, _DEFAULT_SRC


def test_no_tiny_toc_fragments():
    doc = build_document(_DEFAULT_SRC)
    # The old pipeline emitted 9-char "Article 2" / "PART TWO:" passages; drop them.
    tiny = [p for p in doc.passages if len(p.content) < 30]
    assert tiny == [], tiny[:5]


def test_unit_label_is_ccc_number_and_text_clean():
    doc = build_document(_DEFAULT_SRC)
    numbered = [p for p in doc.passages if p.unit_label]
    assert numbered
    assert all(". . ." not in p.content for p in doc.passages)  # ellipses normalized


def test_anchors_unique_per_document():
    doc = build_document(_DEFAULT_SRC)
    anchors = [p.anchor for p in doc.passages]
    assert len(anchors) == len(set(anchors))
