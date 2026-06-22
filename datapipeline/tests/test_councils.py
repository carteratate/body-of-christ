import os, sys, re
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from bs4 import BeautifulSoup
from ingest.councils import build_ecumenical, build_vatican2, build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "councils")
_vendored = os.path.exists(os.path.join(_SRC, "manifest.json"))

CANON_HTML = """<html><body>
<h2>Canons</h2>
<p>Canon 1. If anyone says that the world was not created, let him be anathema and rejected.</p>
<p>Canon 2. If anyone denies the divine nature, let him be condemned by the holy synod here.</p>
</body></html>"""

VAT2_HTML = """<html><body>
<p><strong>CHAPTER I</strong></p>
<p>1. In His goodness and wisdom God chose to reveal Himself and to make known the mystery of His will.</p>
<p>2. By this revelation the invisible God out of the abundance of His love speaks to men as friends.</p>
</body></html>"""


def test_ecumenical_canon_passages_have_unit_and_anchor():
    entry = {"council": "Council of Trent", "document": "Council of Trent", "year": 1563,
             "group": "ecumenical-1-20", "file": "x.html", "url": "http://example"}
    passages = build_ecumenical(entry, BeautifulSoup(CANON_HTML, "lxml")).passages
    assert [p.unit_label for p in passages] == ["Canon 1", "Canon 2"]
    assert passages[0].anchor.startswith("council-of-trent/canon/1")
    assert not passages[0].content.lstrip().startswith("[")


def test_vatican2_numbered_paragraphs_under_chapter():
    entry = {"council": "Second Vatican Council", "document": "Dei Verbum",
             "document_type": "constitution", "year": 1965, "group": "vatican-ii",
             "file": "x.html", "url": "http://example"}
    d = build_vatican2(entry, BeautifulSoup(VAT2_HTML, "lxml"))
    assert d.title == "Dei Verbum"
    assert d.metadata["council"] == "Second Vatican Council"
    assert [p.unit_label for p in d.passages] == ["§1", "§2"]
    assert any("Chapter" in p.chapter_label for p in d.passages)


# Bug 1+4: chapters marked with <b>, a trailing table-of-contents copy, and a
# <p><b> double-hit must all be handled — content split onto the real chapters,
# trailing TOC ignored, no phantom/duplicated chapters.
VAT2_BOLD_HTML = """<html><body>
<p><b>CHAPTER I</b></p>
<p>1. In His goodness God chose to reveal Himself and to make known the mystery of His will to men.</p>
<p>2. By this revelation the invisible God speaks to men as friends and lives among them in friendship.</p>
<b>CHAPTER II</b>
<p>3. In His gracious goodness God has seen to it that what He had revealed for salvation would abide.</p>
<p>Chapter I</p>
<p>Chapter II</p>
</body></html>"""


def test_vatican2_detects_bold_chapters_ignores_trailing_toc():
    entry = {"council": "Second Vatican Council", "document": "Dei Verbum",
             "document_type": "constitution", "year": 1965, "group": "vatican-ii",
             "file": "x.html", "url": "http://example"}
    d = build_vatican2(entry, BeautifulSoup(VAT2_BOLD_HTML, "lxml"))
    labels = [p.chapter_label for p in d.passages]
    assert [p.unit_label for p in d.passages] == ["§1", "§2", "§3"]
    # §1,§2 under Chapter I; §3 under Chapter II — two distinct real chapters.
    assert labels[0] == labels[1] == "Chapter I"
    assert labels[2] == "Chapter II"
    # exactly two chapters (no phantom from the <p><b> double-hit or trailing TOC)
    assert len({p.chapter_key for p in d.passages}) == 2


VAT2_FLAT_HTML = """<html><body>
""" + "\n".join(
    f"<p>{i}. This is numbered paragraph {i} of a declaration with no chapter headings at all here.</p>"
    for i in range(1, 26)
) + """
</body></html>"""


def test_vatican2_headerless_falls_back_to_paragraph_buckets():
    entry = {"council": "Second Vatican Council", "document": "Dignitatis Humanae",
             "document_type": "declaration", "year": 1965, "group": "vatican-ii",
             "file": "x.html", "url": "http://example"}
    d = build_vatican2(entry, BeautifulSoup(VAT2_FLAT_HTML, "lxml"))
    assert len(d.passages) == 25
    labels = {p.chapter_label for p in d.passages}
    # 25 paragraphs in buckets of 20 → "Paragraphs 1–20" and "Paragraphs 21–40"
    assert labels == {"Paragraphs 1–20", "Paragraphs 21–40"}
    assert all(p.anchor and p.chapter_key for p in d.passages)


@pytest.mark.skipif(not _vendored, reason="councils not vendored")
def test_all_documents_build_and_are_clean():
    docs = build_documents()
    assert len(docs) == 36          # 20 ecumenical + 16 Vatican II
    for d in docs:
        assert d.passages, d.title
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"dup anchors in {d.title}"
        for p in d.passages:
            assert p.chapter_key and p.chapter_label
            assert not p.content.lstrip().startswith("[")
            assert not re.search(r"\[\d+\]", p.content)


@pytest.mark.skipif(not _vendored, reason="councils not vendored")
def test_document_ids_unique():
    ids = [d.id for d in build_documents()]
    assert len(ids) == len(set(ids))
