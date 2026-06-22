import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from ingest.medieval import build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "medieval")
pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(_SRC, "manifest.json")),
    reason="medieval sources not vendored; run scripts/vendor_sources.py")


def test_anselm_three_works_single_author():
    docs = build_documents()
    anselm = [d for d in docs if d.author == "Anselm"]
    titles = [d.title for d in anselm]
    label = " | ".join(titles)
    # Exactly the three works — no front-matter pseudo-works (Title Page,
    # Introduction, Appendix, Indexes).
    assert len(anselm) == 3, label
    assert any("Proslogium" in t for t in titles), label
    assert any("Monologium" in t for t in titles), label
    assert any("Cur Deus Homo" in t for t in titles), label
    assert not any(t in ("Introduction", "Appendix", "Title Page", "Indexes")
                   for t in titles), label
    assert all(d.author == "Anselm" for d in anselm)


def test_single_works_present_with_year():
    docs = build_documents()
    boeth = [d for d in docs if d.author == "Boethius"]
    assert len(boeth) == 1
    assert boeth[0].year == 524
    assert boeth[0].collection == "medieval"


def test_content_is_clean_and_anchored():
    for d in build_documents():
        assert d.passages, d.title
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"dup anchors in {d.title}"
        for p in d.passages:
            assert p.chapter_key and p.chapter_label
            assert not p.content.lstrip().startswith("[")


def test_document_ids_unique():
    ids = [d.id for d in build_documents()]
    assert len(ids) == len(set(ids))
