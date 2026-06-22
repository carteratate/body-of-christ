import os, sys, re
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from bs4 import BeautifulSoup
from ingest.encyclicals import _tokens, build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "encyclicals")
_vendored = os.path.exists(os.path.join(_SRC, "manifest.json"))

INLINE = """<html><body>
<p>To Our Venerable Brethren, greeting and Apostolic Blessing.</p>
<p>1. That the spirit of revolutionary change which has long been disturbing the nations of the world.</p>
<p>2. Therefore venerable brethren as on former occasions when it seemed opportune to refute false teaching.</p>
</body></html>"""

HEADING_BODY = """<html><body>
<p>Venerable Brothers greetings and the Apostolic Blessing.</p>
<p>I. INHERITANCE</p>
<p><b>1. At the close of the second Millennium</b></p>
<p>THE REDEEMER OF MAN Jesus Christ is the centre of the universe and of history and to him go my thoughts.</p>
<p>more body of section one continuing the thought with additional substance for the paragraph.</p>
<p><b>2. The first words</b></p>
<p>The first words body text that belongs to paragraph two of this encyclical document here.</p>
</body></html>"""


def _kinds(toks):
    return [t[0] for t in toks]


def test_inline_layout_two_paras_after_preamble():
    toks = _tokens(BeautifulSoup(INLINE, "lxml"))
    assert _kinds(toks).count("preamble") == 1
    paras = [t for t in toks if t[0] == "para"]
    assert [p[1] for p in paras] == [1, 2]
    assert "revolutionary change" in paras[0][2]


def test_heading_body_absorbs_following_paragraphs():
    toks = _tokens(BeautifulSoup(HEADING_BODY, "lxml"))
    paras = [t for t in toks if t[0] == "para"]
    assert [p[1] for p in paras] == [1, 2]
    assert "THE REDEEMER OF MAN" in paras[0][2]
    assert "more body of section one" in paras[0][2]
    assert any(t[0] == "section" for t in toks)


def test_pre_first_number_header_not_a_section():
    html = """<html><body><p><b>RERUM NOVARUM</b></p>
    <p>1. The spirit of revolutionary change disturbing nations across the whole world today.</p></body></html>"""
    toks = _tokens(BeautifulSoup(html, "lxml"))
    assert not any(t[0] == "section" for t in toks)


@pytest.mark.skipif(not _vendored, reason="encyclicals not vendored")
def test_all_eighteen_documents_produce_passages():
    docs = build_documents()
    assert len(docs) == 18
    for d in docs:
        assert d.passages, f"{d.title} produced no passages"


@pytest.mark.skipif(not _vendored, reason="encyclicals not vendored")
def test_layout_b_documents_recovered():
    docs = {d.title: d for d in build_documents()}
    for title in ("Redemptor Hominis", "Laborem Exercens"):
        units = [p.unit_label for p in docs[title].passages if p.unit_label]
        assert len(units) >= 15, f"{title} only {len(units)} numbered passages"


@pytest.mark.skipif(not _vendored, reason="encyclicals not vendored")
def test_clean_anchored_no_footnote_markers():
    for d in build_documents():
        anchors = [p.anchor for p in d.passages]
        assert len(anchors) == len(set(anchors)), f"dup anchors in {d.title}"
        for p in d.passages:
            assert p.chapter_key and p.chapter_label
            assert not p.content.lstrip().startswith("[")
            assert not re.search(r"\[\d+\]", p.content), f"footnote marker left in {d.title}"
