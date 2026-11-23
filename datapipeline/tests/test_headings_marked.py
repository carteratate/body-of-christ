"""Headings marked by the Catechism and Vatican II adapters (issue #445, part 2): the
rules that set their levels, and, on the vendored sources, what two passages carry and
that both collections pass H6 to H8 with only marks added."""
import os

import pytest

import health
import headings
from ingest import catechism, councils
from ingest.catechism import _DEFAULT_SRC
from ingest.councils import _SRC as COUNCILS_SRC


def _h(at, end, level):
    return {"at": at, "end": end, "level": level, "role": "heading"}


def test_a_heading_straight_under_another_is_at_most_one_level_below_it():
    clean = "Article 1\n\nTITLE\n\nA sub-head\n\nBody.\n\nAnother\n\nBody."
    marks = [_h(0, 9, 1), _h(11, 16, 1), _h(18, 28, 3), _h(37, 44, 3)]
    assert [m["level"] for m in catechism._no_skipped_levels(marks, clean)] == [1, 1, 2, 3]


def test_a_chapter_opening_pair_that_repeats_its_label_is_marked_chapter_title():
    clean = "Article 5\n\nTHE FIFTH COMMANDMENT\n\n§2258 Text."
    marks = [{**_h(0, 9, 1), "pairs_next": True}, _h(11, 32, 1)]
    label = "Part Three, Section Two, Chapter Two, Article 5, The Fifth Commandment"
    assert catechism._chapter_title(marks, clean, label)[0]["chapter_title"] is True
    assert catechism._chapter_title(marks, clean, "Article 4, The Fourth")[0].get(
        "chapter_title") is None


@pytest.mark.parametrize("text,level", [
    ("SECTION 1 The Avoidance of War", 2), ("ARTICLE 1: Christian Witness", 2),
    ("I. Diocesan Bishops", 2), ("A) General norms", 3),
    ("2. The diocesan curia and commissions", 3),
    ("1. The Nature of the Sacred Liturgy and Its Importance in the Church's Life", 3),
])
def test_vatican2_levels(text, level):
    assert councils._v2_level("Christus Dominus", text) == level


def test_vatican2_level_fix():
    assert councils._v2_level(
        "Sacrosanctum Concilium",
        "1. The Nature of the Sacred Liturgy and Its Importance in the Church's Life") == 2


# --------------------------------------------------------------------------- sources

def _marked(passage):
    return [(passage.content[m["at"]:m["end"]], m.get("level") or m["role"])
            for m in passage.metadata.get("headings", [])]


@pytest.mark.sources
@pytest.mark.skipif(not os.path.exists(_DEFAULT_SRC), reason="catechism sources not vendored")
def test_catechism_marks():
    doc = catechism.build_document()
    by = {p.anchor: p for p in doc.passages}
    assert _marked(by["ccc/2263"]) == [("Legitimate defense", 3)]
    assert _marked(by["ccc/2258"])[:3] == [
        ("Article 5", 1), ("THE FIFTH COMMANDMENT", 1), ("You shall not kill.", "epigraph")]
    assert by["ccc/2258"].metadata["headings"][0]["chapter_title"] is True
    assert health.check_documents("catechism", [doc], report=False) == []


@pytest.mark.sources
@pytest.mark.skipif(not os.path.exists(COUNCILS_SRC), reason="councils sources not vendored")
def test_vatican2_marks_and_only_vatican2():
    docs = councils.build_documents()
    gs = next(d for d in docs if d.title == "Gaudium et Spes")
    gs79 = next(p for p in gs.passages if p.anchor == "gaudium-et-spes/79")
    assert _marked(gs79) == [("SECTION 1 The Avoidance of War", 2)]
    marked = {d.author for d in docs for p in d.passages if (p.metadata or {}).get("headings")}
    assert marked == {"Second Vatican Council"}
    assert health.check_documents("councils", docs, report=False) == []


def test_vatican2_marks_the_heading_paragraph_not_earlier_words(monkeypatch):
    builder = councils._Builder(clean=lambda text: text.strip())
    body = "These are the General norms we follow.\n\nGeneral norms\n\nText."
    from ingest.pieces import Segment
    segments = [Segment("e1", "These are the General norms we follow."),
                Segment("e2", "General norms"), Segment("e3", "Text.")]
    builder.add(body=body, ref="SC 22", base_anchor="sc/22", ckey="c", clabel="C", unit="§22",
                meta={}, segments=segments, heads={"e2": {"level": 3}})
    (passage,) = builder.passages
    (mark,) = passage.metadata["headings"]
    assert passage.content[mark["at"]:mark["end"]] == "General norms" and mark["at"] > 0


def test_every_title_of_an_opening_stack_that_repeats_the_label_is_flagged():
    clean = ("CHAPTER ONE\n\nTHE PASCHAL MYSTERY\n\nArticle 1\n\nTHE LITURGY - WORK OF THE "
             "HOLY TRINITY\n\n§1077 Text.")
    marks = [{**_h(0, 11, 1), "pairs_next": True}, _h(13, 32, 1),
             {**_h(34, 43, 1), "pairs_next": True}, _h(45, 83, 1)]
    label = "Part Two, Section One, Chapter One, Article 1, The Liturgy - Work of the Holy Trinity"
    out = catechism._chapter_title(marks, clean, label)
    assert [bool(m.get("chapter_title")) for m in out] == [False, False, True, False]


def test_vatican2_marks_the_heading_paragraph_not_an_identical_earlier_one():
    from ingest.pieces import Segment
    builder = councils._Builder(clean=lambda text: text.strip())
    segments = [Segment("e1", "General norms"), Segment("e2", "Text one."),
                Segment("e3", "General norms"), Segment("e4", "Text two.")]
    builder.add(body="\n\n".join(s.text for s in segments), ref="SC 22",
                base_anchor="sc/22", ckey="c", clabel="C", unit="§22", meta={},
                segments=segments, heads={"e3": {"level": 3}})
    (passage,) = builder.passages
    assert [m["at"] for m in passage.metadata["headings"]] == [passage.content.index(
        "General norms\n\nText two.")]


def test_a_bare_number_counts_only_at_the_start():
    assert not headings.repeats_label("The Church", "History 2: The Church")
