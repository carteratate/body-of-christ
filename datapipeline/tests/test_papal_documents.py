import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from bs4 import BeautifulSoup
from ingest.papal_documents import _tokens, build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "papal-documents")
_vendored = os.path.exists(os.path.join(_SRC, "manifest.json"))


@pytest.mark.skipif(not _vendored, reason="papal-documents not vendored")
def test_all_documents_produce_passages():
    docs = build_documents()
    assert len(docs) == 14
    for d in docs:
        assert d.passages, f"{d.title} produced no passages"


@pytest.mark.skipif(not _vendored, reason="papal-documents not vendored")
def test_collection_name():
    docs = build_documents()
    for d in docs:
        assert d.collection == "papal-documents"


@pytest.mark.skipif(not _vendored, reason="papal-documents not vendored")
def test_no_duplicate_anchors():
    for d in build_documents():
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"dup anchors in {d.title}"


def test_inline_layout():
    html = """<html><body>
    <p>Pope Boniface VIII, to all the faithful, greeting.</p>
    <p>1. We are compelled, our faith urging us, to believe and to maintain that the Church is one.</p>
    <p>2. And in this, the one and only Church, there is one body and one head.</p>
    </body></html>"""
    toks = _tokens(BeautifulSoup(html, "lxml"))
    paras = [t for t in toks if t[0] == "para"]
    assert [p[1] for p in paras] == [1, 2]
