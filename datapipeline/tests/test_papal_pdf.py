"""A papal document published only as a PDF: Amoris Laetitia (corpus-cleanup 5.4, #203).

The source checks' sentence coverage does not measure it (`checks.source_text`); these
tests check the reading instead, against the booklet's own index and its run of numbers.
"""
import json
import os
import re
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import headings
from ingest import papal_common, papal_pdf

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources",
                    "apostolic-exhortations")
_PDF = os.path.join(_SRC, "amoris-laetitia.pdf")
needs_pdf = pytest.mark.skipif(not os.path.exists(_PDF), reason="the PDF is not vendored")

# The chapters' opening paragraphs, as the booklet's index prints them ("[8]", "[31]" …).
CHAPTER_OPENINGS = [8, 31, 58, 89, 165, 199, 259, 291, 313]


@pytest.fixture(scope="module")
def blocks():
    return papal_pdf.blocks(_PDF, papal_pdf.AMORIS_LAETITIA)


@pytest.fixture(scope="module")
def text():
    """The text as the parser reads it, line-end hyphens decided."""
    from bs4 import BeautifulSoup

    html = papal_pdf.html_text(_PDF, papal_pdf.AMORIS_LAETITIA)
    return "\n".join(el.get_text() for el in BeautifulSoup(html, "lxml").find_all(True)
                     if el.name in ("p", "h2", "h3", "h4"))


@pytest.fixture(scope="module")
def document():
    with open(os.path.join(_SRC, "manifest.json"), encoding="utf-8") as f:
        entry = next(e for e in json.load(f) if e["slug"] == "amoris-laetitia")
    return papal_common.build_document(entry, "apostolic-exhortations", _SRC)


def _index_headings() -> list[str]:
    """The section headings the booklet's index lists after its text, without their
    paragraph ranges and page numbers."""
    lines = papal_pdf.read_lines(_PDF, papal_pdf.AMORIS_LAETITIA.first_page)
    start = next(i for i, ln in enumerate(lines) if ln.text.strip() == "INDEX")
    entries, current = [], ""
    for ln in lines[start + 1:]:
        text = papal_pdf._joined(ln.text.strip(), papal_pdf.AMORIS_LAETITIA)
        if re.fullmatch(r"\d+", text):
            continue                       # a page number
        current = f"{current} {text}".strip()
        if re.search(r"\[\d+(?:-\d+)?\]", current):
            entries.append(re.sub(r"^Chapter \w+ ", "", re.sub(r"\s*\[.*$", "", current)))
            current = ""
    return entries


@needs_pdf
def test_every_numbered_paragraph_in_order(blocks):
    numbers = [int(m[1]) for b in blocks if b.tag == "p"
               if (m := re.match(r"(\d+)\. ", b.text()))]
    assert numbers == list(range(1, 326))


@needs_pdf
def test_headings_are_the_index(blocks):
    # The index lists the introduction ("The Joy of Love"), each chapter's title and every
    # heading inside a chapter, in order.
    index = [h.replace("VOCA-TION", "VOCATION") for h in _index_headings()]
    read = []
    for b in blocks:
        if b.tag == "h2" and not b.text().startswith("CHAPTER "):
            read.append(b.text())
        elif b.tag in ("h3", "h4"):
            read.append(b.text())
    assert index[0] == "The Joy of Love"           # §§1-7 have no heading in the text
    assert [h.casefold() for h in index[1:]] == [h.casefold() for h in read]
    assert sum(b.tag == "h2" and b.text().startswith("CHAPTER ") for b in blocks) == 9


@needs_pdf
def test_no_note_page_number_or_caller_reaches_the_text(text):
    assert "AAS" not in text and "Ibid." not in text       # the notes at a page's foot
    # A caller left after a word or its punctuation (a verse is "Jn 16:13").
    assert not re.search(r"[a-z”’.,;]\d{1,3}\b", text)
    assert "INDEX" not in text and "VATICAN PRESS" not in text


@needs_pdf
def test_line_end_hyphens(text):
    for compound in papal_pdf.AMORIS_LAETITIA.compounds:
        assert compound in text
    assert "deepest mystery" in text and "deep-est" not in text
    assert "­" not in text and "￾" not in text
    assert "kerygma" in text and "almsgiving" in text


@needs_pdf
def test_the_document(document):
    assert (document.title, document.year, document.metadata["genre"]) == (
        "Amoris Laetitia", 2016, "apostolic-exhortation")
    paragraphs = [p for p in document.passages if p.unit_label]
    assert [p.unit_label for p in paragraphs] == [f"§{n}" for n in range(1, 326)]
    chapters = {}
    for p in document.passages:
        chapters.setdefault(p.chapter_key, p)
    assert [p.unit_label for p in chapters.values()] == \
        ["§1"] + [f"§{n}" for n in CHAPTER_OPENINGS] + [None]
    assert document.passages[-1].chapter_label == "Prayer to the Holy Family"
    assert document.passages[-1].content.endswith("the fourth of my Pontificate.")


@needs_pdf
def test_headings_marked(document):
    for p in document.passages:
        assert headings.problems(p.content, (p.metadata or {}).get("headings")) == [], p.anchor
    by = {p.unit_label: p for p in document.passages}
    marks = by["§8"].metadata["headings"]
    assert marks == [{"at": 0, "end": 37, "level": 1, "role": "heading",
                      "chapter_title": True}]
    assert by["§9"].metadata["headings"][0]["level"] == 2     # "You and your wife"
    assert by["§91"].metadata["headings"][0]["level"] == 3    # "Love is patient"


def test_a_pdf_with_no_layout_stops_the_build(tmp_path):
    with pytest.raises(ValueError, match="needs its layout"):
        papal_pdf.soup(str(tmp_path / "x.pdf"), "evangelii-gaudium")


def test_unmarked_documents_keep_their_metadata():
    # Only 5.4's two additions mark headings; the rest of the papal collection waits for
    # #445 (`papal_common._MARKED_HEADINGS`).
    assert papal_common._MARKED_HEADINGS == {"amoris-laetitia", "ubicumque-et-semper"}
