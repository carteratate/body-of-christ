"""The Roman Catechism (5.5): its OCR units (`ocr.units.RomanCatechism`) and its adapter
(`ingest/roman_catechism.py`). The last tests read the frozen text and skip without it."""
import os
import re

import pytest

from ingest import roman_catechism as R
from ocr.furniture import Paragraph
from ocr.units import (RomanCatechism, catechism_note, roman_catechism_heading,
                       strip_catechism_calls)


def _paras(*texts, continues=()):
    return [Paragraph(t, t, [i], continues=i in continues) for i, t in enumerate(texts)]


@pytest.mark.parametrize("text", [
    "INTRODUCTORY", "ADVANTAGES OF CONFESSION", "Names of this Sacrament",
    "The Rites and ceremonies of the Mass", "“Our Father who art in heaven”",
    "Extent of this Power:", "ARTICLE IV"])
def test_the_translators_headings_are_recognized(text):
    assert roman_catechism_heading(text)


@pytest.mark.parametrize("text", [
    "But, as faith cometh by hearing, it is clear how necessary at all times.",
    "The eighth commandment forbids:", "Amen.", "It forbids false witness,"])
def test_text_is_not_a_heading(text):
    assert not roman_catechism_heading(text)


@pytest.mark.parametrize("ocr, clean", [
    ("as faith cometh by hearing,® it is clear", "as faith cometh by hearing, it is clear"),
    ("by the prophets,> and pointed", "by the prophets, and pointed"),
    ("into the world3* to corrupt", "into the world to corrupt"),
    ("in the Spirit.? Lest any", "in the Spirit. Lest any"),
    ("his eyes.2 And", "his eyes. And"),
    ("the church24 of God", "the church of God"),
    ("glory. ™ And »On the", "glory. And On the"),
])
def test_note_calls_come_off_the_text(ocr, clean):
    assert strip_catechism_calls(ocr) == clean


def test_leaked_notes_are_recognized():
    assert catechism_note("a The term “symbol” is from the Greek, “sign,” because the Creed")
    assert catechism_note("Heb. xiii. 9. * Matt. xvi. 18.")
    assert not catechism_note("The pastor should labor to impress deeply on the faithful.")


def _units(*texts, continues=()):
    return RomanCatechism().split(_paras("Title line", "INTRODUCTORY", *texts,
                                         continues=continues))


def test_units_drop_the_title_lines_notes_and_specks():
    [unit] = _units("Need of Instruction", "But faith cometh by hearing.®",
                    "a The term is Greek.", "Ir")
    assert [p.text for p in unit.paragraphs] == [
        "INTRODUCTORY", "Need of Instruction", "But faith cometh by hearing."]


def test_a_heading_split_over_two_lines_is_joined():
    [unit] = _units("INSTRUCTION SHOULD BE ACCOMMODATED TO THE CAPACITY OF THE", "HEARER",
                    "The pastor should first consider.")
    assert unit.paragraphs[1].text == ("INSTRUCTION SHOULD BE ACCOMMODATED TO THE CAPACITY OF "
                                       "THE HEARER")


def test_two_headings_in_capitals_stay_apart_when_the_first_is_complete():
    [unit] = _units("THE SACRAMENT OF BAPTISM", "IMPORTANCE OF INSTRUCTION ON BAPTISM",
                    "From what has been said.")
    assert [p.text for p in unit.paragraphs[1:3]] == [
        "THE SACRAMENT OF BAPTISM", "IMPORTANCE OF INSTRUCTION ON BAPTISM"]


def test_headings_run_into_or_onto_a_paragraph_are_split_off():
    [unit] = _units("Have we not all one Father? GOD IS CALLED “FATHER” BECAUSE HE ADOPTS "
                    "CHRISTIANS", "THROUGH GRACE", "But God, particularly in this.",
                    "IT WAS NOT A SACRAMENT How much the Sacrament excels.")
    texts = [p.text for p in unit.paragraphs]
    assert "GOD IS CALLED “FATHER” BECAUSE HE ADOPTS CHRISTIANS THROUGH GRACE" in texts
    assert texts[-2:] == ["IT WAS NOT A SACRAMENT", "How much the Sacrament excels."]


def test_a_passage_never_ends_with_a_heading():
    words = " ".join(["word"] * 360) + "."
    units = _units("FIRST HEADING", words, "SECOND HEADING", "More text here.")
    assert all(not roman_catechism_heading(u.paragraphs[-1].text) for u in units)
    assert [p.text for p in units[-1].paragraphs][:1] == ["SECOND HEADING"]


def _text(*passages):
    return {"metadata": {"text_source": "ocr", "scan_id": R.SCAN},
            "passages": [{"id": f"{n:04d}", "pages": pages, "leaves": [], "text": t}
                         for n, (pages, t) in enumerate(passages, 1)]}


def test_sections_run_across_passages_and_headings_become_labels():
    sections = R._sections(_text(
        (["1"], "INTRODUCTORY\n\nThe Necessity of Religious Instruction\n\nBut faith."),
        (["2"], "More of it.\n\nZEAL\n\nThe pastor."))["passages"])
    assert [(s.headings, s.paragraphs) for s in sections] == [
        (["INTRODUCTORY", "The Necessity of Religious Instruction"], ["But faith.", "More of it."]),
        (["ZEAL"], ["The pastor."])]
    assert R.label(sections[0].headings) == "The Necessity of Religious Instruction"
    assert R.label(["ADVANTAGES OF CONFESSION"]) == "Advantages of Confession"
    assert R.label(["PART I", "THE CREED"]) is None


def test_a_long_section_is_cut_at_paragraphs():
    para = "x " * 1000
    pieces = R._pieces([para.strip(), para.strip(), "short."])
    assert [first for first, _ in pieces] == [0, 1]
    assert all(len(t) <= R.MAX_CHARS + 500 for _, t in pieces)


# --------------------------------------------------------------------------- frozen text

FROZEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "ocr", "texts", f"{R.WORK}.json")
needs_text = pytest.mark.skipif(not os.path.exists(FROZEN), reason="no frozen text")


@pytest.fixture(scope="module")
def document():
    return R.build_document()


@needs_text
def test_the_frozen_text_passed_its_gate():
    assert R.read_text(R.WORK)["gate"] == "pass"


@needs_text
def test_every_chapter_is_found_in_order_with_its_passages_labelled(document):
    keys = list(dict.fromkeys(p.chapter_key for p in document.passages))
    assert keys == [f"roman-catechism/{c.key}" for c in R.CHAPTERS]
    assert all(p.metadata["text_source"] == "ocr" and p.metadata["scan_id"] == R.SCAN
               for p in document.passages)
    assert len({p.anchor for p in document.passages}) == len(document.passages)


@needs_text
def test_no_note_or_heading_text_reaches_a_passage(document):
    for p in document.passages:
        assert not re.search(r"Summa Theol|[®™©]", p.content), p.anchor
        assert not any(roman_catechism_heading(q) for q in p.content.split("\n\n")), p.anchor


@needs_text
def test_no_passage_holds_a_short_unclosed_line(document):
    """A heading, a heading's broken line or OCR debris reads as a short paragraph that no
    sentence closes. Checked on the built text, not with the heading detector."""
    found = [(p.anchor, q) for p in document.passages for q in p.content.split("\n\n")
             if len(q.split()) <= 14 and not re.search(r"[.?!:;”’)]$", q.strip())]
    assert found == []
    unbalanced = [p.unit_label for p in document.passages if p.unit_label
                  and (p.unit_label.count("“") != p.unit_label.count("”")
                       or re.match(r"^\W*[a-z]", p.unit_label))]
    assert unbalanced == []
