"""`ChapterPlan.headings` in `ingest.thml_doc.make_doc` (5.6b, #445): a paragraph the work
prints as its own heading stays in the text, is marked, and stays with what follows it."""
import os, sys
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import defusedxml.ElementTree as ET
import pytest

import headings
from config import settings
from ingest.thml_doc import ChapterPlan, make_doc


def _chapter(*paragraphs):
    body = "".join(f'<p id="c1-p{k}">{t}</p>' for k, t in enumerate(paragraphs, 1))
    return ET.fromstring(f'<div2 id="c1" title="Chapter I. Of Love">{body}</div2>')


def _build(div, plan):
    return make_doc(collection="medieval", filename="f.xml", author="A", title="T",
                    chapters=[(None, div, plan)], source_key="theologians/f.xml")


def test_a_marked_title_stays_in_the_text_with_its_first_paragraph():
    long = "Word " * (settings.MAX_PASSAGE_CHARS // 5)
    div = _chapter("OF LOVE.", long.strip() + ".", "A second paragraph of the chapter.")
    doc = _build(div, ChapterPlan(label="Chapter I. Of Love", headings=(("c1-p1", 1, True),)))
    first = doc.passages[0]
    assert first.content.startswith("OF LOVE.\n\nWord Word")
    assert first.metadata["headings"] == [
        {"at": 0, "end": 8, "level": 1, "role": "heading", "chapter_title": True}]
    assert all(headings.problems(p.content, (p.metadata or {}).get("headings")) == []
               for p in doc.passages)
    # Without the plan the packer would leave the title alone in a piece.
    bare = _build(_chapter("OF LOVE.", long.strip() + ".", "A second paragraph."),
                  ChapterPlan(label="Chapter I. Of Love"))
    assert bare.passages[0].content == "OF LOVE."


def test_headings_inside_a_chapter_are_marked_at_their_levels():
    div = _chapter("Of Creation.", "Preparation.",
                   "1. Place yourself in the Presence of God, and ask Him to inspire you.",
                   "Considerations.", "1. Consider that but a few years since you were not.")
    doc = _build(div, ChapterPlan(label="Chapter IX. First Meditation", headings=(
        ("c1-p1", 2, False), ("c1-p2", 3, False), ("c1-p4", 3, False))))
    (p,) = doc.passages
    marked = [(p.content[m["at"]:m["end"]], m["level"]) for m in p.metadata["headings"]]
    assert marked == [("Of Creation.", 2), ("Preparation.", 3), ("Considerations.", 3)]


def test_a_heading_printed_before_the_chapter_opens_its_text():
    div = _chapter("OF LOVE.", "Text of the chapter, long enough to keep: " * 4)
    doc = _build(div, ChapterPlan(label="Book I · Chapter I. Of Love",
                                  headings=(("c1-p1", 1, True),),
                                  lead=(("BOOK I. OF THE WILL.", 1),)))
    (p,) = doc.passages
    assert p.content.startswith("BOOK I. OF THE WILL.\n\nOF LOVE.\n\nText")
    assert [(p.content[m["at"]:m["end"]], m.get("chapter_title", False))
            for m in p.metadata["headings"]] == [("BOOK I. OF THE WILL.", False),
                                                 ("OF LOVE.", True)]
    assert p.anchor == "c1"


def test_a_heading_id_is_read_without_its_own_div_prefix_only():
    div = ET.fromstring('<div2 id="c1"><p id="c1-p1-a">HEAD</p><p id="c1-p2">'
                        + "Body text of the chapter, long enough. " * 4 + '</p></div2>')
    doc = _build(div, ChapterPlan(label="C", headings=(("c1-p1-a", 2, False),)))
    assert doc.passages[0].metadata["headings"][0]["end"] == 4


def test_a_heading_that_is_no_paragraph_read_is_refused():
    with pytest.raises(ValueError, match="not paragraphs read"):
        _build(_chapter("Of Love.", "Text of the chapter, long enough to keep: " * 4),
               ChapterPlan(label="Chapter I", headings=(("c1-p9", 2, False),)))


def test_a_heading_without_a_level_is_an_epigraph():
    # 5.6a: Cyril's Scripture reading under a lecture's title.
    elem = _chapter("Romans vi. 3, 4", "Know ye not that so many of us " * 4,
                    "1. These daily introductions into the Mysteries are profitable. " * 3)
    plan = ChapterPlan(label="Lecture XX", headings=(("c1-p1", None, False),
                                                       ("c1-p2", None, False)))
    doc = make_doc(collection="church-fathers", filename="t.xml", author="A", title="T",
                   chapters=[(None, elem, plan)], source_key="church-fathers/t.xml")
    marks = doc.passages[0].metadata["headings"]
    assert [m["role"] for m in marks] == ["epigraph", "epigraph"]
    assert all("level" not in m for m in marks)
