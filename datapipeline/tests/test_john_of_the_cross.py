"""John of the Cross in Lewis's translation (5.6c): the adapter, `ingest/john_of_the_cross.py`.
The last tests read the frozen texts and skip without them."""
import os
import re

import pytest

from ingest import john_of_the_cross as J

ASCENT = J.TREATISES[0]


@pytest.mark.parametrize("ocr, clean", [
    ("is foolishness with God.’* He, therefore", "is foolishness with God.’ He, therefore"),
    ("cannot be a disciple’ f of Christ.", "cannot be a disciple’ of Christ."),
    ("in the presence of God.t By that action", "in the presence of God. By that action"),
    ("defiled with it.’1 He, then,", "defiled with it.’ He, then,"),
    ("‘Who will give us flesh to eat?’{ They", "‘Who will give us flesh to eat?’ They"),
    ("the wisdom~of this world", "the wisdom of this world"),
    ("the wind of his love,’+ and again", "the wind of his love,’ and again"),
    ("descend with him.’ ††‘Be not afraid", "descend with him.’ ‘Be not afraid"),
    ("all that the ___ imagination may", "all that the imagination may"),
])
def test_note_calls_and_specks_come_off(ocr, clean):
    assert J.strip_calls(ocr) == clean


def test_words_that_look_like_calls_stay():
    text = "He left the house of his father, and at the foot of the mount."
    assert J.strip_calls(text) == text


def test_roman_numerals():
    assert [J.roman(n) for n in ("I", "IV", "IX", "XIV", "XL", "XLIV")] == [1, 4, 9, 14, 40, 44]


def _text(*paragraphs, continues=()):
    return [{"id": f"{k:04d}", "pages": [str(k)], "text": t, "continues": k in continues}
            for k, t in enumerate(paragraphs, 1)]


SMALL = J.Treatise("w", "scan", "work", "A Work", 1585, 2, (2, 1))


def test_chapters_take_their_title_and_run_in_order_within_each_book():
    chapters = J.chapters(SMALL, _text(
        "THE\n\nA WORK OF GOD.\n\nARGUMENT.\n\nThe argument.\n\nSTANZAS\n\nI\n\nIn an obscure night.",
        "PROLOGUE.\n\nThe prologue.\n\nBOOK I.\n\nTHE TITLE OF THE FIRST BOOK.\n\nCHAPTER I.\n\n"
        "The first title.\n\nThe first text.",
        "runs on.\n\nCHAPTER II.\n\nThe second title.\n\nSTANZA I.\n\nThe second text.",
        "BOOK II.\n\nCHAPTER I.\n\nSTANZA II.\n\nThe third text.", continues=(3,)))
    assert [(c.key, c.label, c.paragraphs) for c in chapters] == [
        ("argument", "Argument", ["The argument.", "In an obscure night."]),
        ("prologue", "Prologue", ["The prologue."]),
        ("book-1/chapter-1", "Book I, Chapter I. The first title", ["The first text. runs on."]),
        ("book-1/chapter-2", "Book I, Chapter II. The second title", ["The second text."]),
        ("book-2/chapter-1", "Book II, Chapter I", ["The third text."])]


def test_a_chapter_out_of_order_or_a_missing_one_fails():
    with pytest.raises(ValueError, match="after chapter 1"):
        J.chapters(SMALL, _text("BOOK I.\n\nCHAPTER I.\n\nT.\n\nText.\n\nCHAPTER III.\n\nT.\n\nText."))
    with pytest.raises(ValueError, match="chapters per book"):
        J.chapters(SMALL, _text("BOOK I.\n\nCHAPTER I.\n\nT.\n\nText.\n\nBOOK II.\n\nCHAPTER I.\n\nT.\n\nText."))


def test_text_outside_a_chapter_fails():
    with pytest.raises(ValueError, match="outside a chapter"):
        J.chapters(SMALL, _text("Some text before any heading."))


# --------------------------------------------------------------------------- frozen text

FROZEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "ocr", "texts", f"{ASCENT.work}.json")
needs_text = pytest.mark.skipif(not os.path.exists(FROZEN), reason="no frozen text")


@pytest.fixture(scope="module")
def document():
    return J.build_document(ASCENT)


@needs_text
def test_the_frozen_text_passed_its_gate():
    from ocr.fixes import read_text
    assert read_text(ASCENT.work)["gate"] == "pass"


@needs_text
def test_every_chapter_is_found_in_order(document):
    keys = list(dict.fromkeys(p.chapter_key for p in document.passages))
    chapters = [f"book-{b}/chapter-{n}" for b, count in enumerate(ASCENT.chapters, 1)
                for n in range(1, count + 1)]
    assert [k.split("/", 1)[1] for k in keys] == (
        ["argument", "prologue"] + chapters[:47] + ["book-3/argument"] + chapters[47:])
    assert all(p.metadata["text_source"] == "ocr" for p in document.passages)
    assert len({p.anchor for p in document.passages}) == len(document.passages)


@needs_text
def test_no_heading_mark_or_broken_paragraph_reaches_a_passage(document):
    for p in document.passages:
        assert not re.search(r"\bCHAPTER\b|\bBOOK [IVX]+\.|\bSTANZA\b|[*†‡§¶|{}¢®©~_+%€]",
                             p.content), p.anchor
    short = [(p.anchor, q) for p in document.passages for q in p.content.split("\n\n")
             if len(q.split()) <= 14 and not re.search(r"[.?!:;”’)'\"]$", q.strip())]
    assert short == []
    labels = {p.chapter_label for p in document.passages}
    shape = re.compile(r"^(Argument|Prologue|Book (I|II|III), (Argument|Chapter [IVXL]+(\. .+)?))$")
    assert sorted(label for label in labels if not shape.match(label)
                  or re.search(r"\. .*[A-Z]{4}|[.,]$", label)) == []
    assert "Book II, Chapter I" in labels


@needs_text
def test_a_clipped_label_leaves_the_whole_title_as_the_chapters_heading(document):
    first = {}
    for p in document.passages:
        first.setdefault(p.chapter_key, p)
    clipped = 0
    for p in first.values():
        assert len(p.chapter_label) <= 140, p.chapter_label
        marks = (p.metadata or {}).get("headings") or []
        title = p.chapter_label.split(". ", 1)[1] if ". " in p.chapter_label else ""
        if marks:
            clipped += 1
            heading = p.content[marks[0]["at"]:marks[0]["end"]]
            assert marks[0]["at"] == 0 and marks[0]["level"] == 1
            assert heading.startswith(title) and len(heading) > len(title), p.anchor
    assert clipped == 23
    assert not any((p.metadata or {}).get("headings") for p in document.passages
                   if p is not first[p.chapter_key])
