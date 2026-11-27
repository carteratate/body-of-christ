"""Headings marked inside passages (issue #445): the adapter helper, the cut that carries
marks into pieces, the contract, the classifier, and the health rules H6 to H8. Runs in
CI; no vendored source is read."""
import copy

import pytest

import health
import headings
from headings import EPIGRAPH, Heading, HeadingError, MarkedText
from ingest.common import split_display_passage
from model import Document, Passage

BODY = ("Even though recent wars have wrought physical and moral havoc on our world, the "
        "devastation of battle still goes on day by day in some part of the world.")


def _spans(content, marks):
    return [content[m["at"]:m["end"]] for m in marks]


# --------------------------------------------------------------------------- helper

def test_marked_text_marks_each_heading_as_a_whole_paragraph():
    text = (MarkedText().heading("Article 1", 1, pairs_next=True)
            .heading("THE REVELATION OF GOD", 1).epigraph('"You shall not kill."')
            .paragraph(BODY))
    assert text.text == f'Article 1\n\nTHE REVELATION OF GOD\n\n"You shall not kill."\n\n{BODY}'
    assert text.marks == [
        {"at": 0, "end": 9, "level": 1, "role": "heading", "pairs_next": True},
        {"at": 11, "end": 32, "level": 1, "role": "heading"},
        {"at": 34, "end": 55, "role": "epigraph"},
    ]
    assert _spans(text.text, text.marks) == ["Article 1", "THE REVELATION OF GOD",
                                             '"You shall not kill."']
    assert headings.problems(text.text, text.marks) == []


def test_prepend_joins_held_headings_and_shifts_existing_marks():
    inner = MarkedText().paragraph(BODY).heading("The table of the word", 3).paragraph(BODY)
    content, marks = headings.prepend(
        [Heading("SECTION 1 The Avoidance of War", 2), Heading('"Blessed are"', role=EPIGRAPH)],
        "  " + inner.text, headings.shift(inner.marks, 2))
    assert content.startswith("SECTION 1 The Avoidance of War\n\n\"Blessed are\"\n\nEven")
    assert _spans(content, marks) == ["SECTION 1 The Avoidance of War", '"Blessed are"',
                                      "The table of the word"]
    assert [m.get("level") for m in marks] == [2, None, 3]
    assert headings.problems(content, marks) == []


def test_nothing_held_leaves_text_and_marks_alone():
    assert headings.prepend([], BODY) == (BODY, [])


@pytest.mark.parametrize("call", [
    lambda t: t.heading("Two\n\nparagraphs", 2),
    lambda t: t.heading("   ", 2),
    lambda t: t.heading("No level", 4),
    lambda t: t.heading("Not first tier", 2, chapter_title=True),
])
def test_the_helper_refuses_a_bad_heading(call):
    with pytest.raises(HeadingError):
        call(MarkedText())


def test_with_headings_sets_or_removes_the_key():
    assert headings.with_headings({"a": 1}, []) == {"a": 1}
    assert headings.with_headings(None, []) is None
    assert headings.with_headings({"a": 1, "headings": [{"at": 0}]}, []) == {"a": 1}
    marks = [{"at": 5, "end": 6}, {"at": 0, "end": 3}]
    assert headings.with_headings(None, marks) == {"headings": [{"at": 0, "end": 3},
                                                                {"at": 5, "end": 6}]}


# --------------------------------------------------------------------------- splitting

def _long_marked():
    text = MarkedText()
    for k in range(1, 7):
        text.heading(f"Heading number {k}", 3)
        text.paragraph(f"Paragraph {k}. " + BODY * 3)
    return text


def test_split_marks_carries_and_shifts_marks_into_pieces():
    text = _long_marked()
    pieces = split_display_passage(text.text, 900)
    assert len(pieces) > 1
    per_piece = headings.split_marks(text.text, pieces, text.marks)
    assert sum(len(m) for m in per_piece) == 6
    for piece, marks in zip(pieces, per_piece):
        for m in marks:
            assert piece[m["at"]:m["end"]].startswith("Heading number ")


def test_split_marks_refuses_a_cut_inside_a_heading():
    content = "A heading\n\n" + BODY
    with pytest.raises(HeadingError, match="inside the heading"):
        headings.split_marks(content, ["A head", "ing\n\n" + BODY],
                             [{"at": 0, "end": 9, "level": 3, "role": "heading"}])


def test_hold_headings_moves_a_trailing_heading_stack_to_the_next_piece():
    content = (MarkedText().paragraph(BODY).heading("Part Two", 1, pairs_next=True)
               .heading("THE SACRAMENTS", 1).paragraph(BODY))
    pieces = [BODY + "\n\nPart Two\n\nTHE SACRAMENTS", BODY]   # a splitter cut after them
    held = headings.hold_headings(content.text, pieces, content.marks)
    assert held == [BODY, "Part Two\n\nTHE SACRAMENTS\n\n" + BODY]
    per_piece = headings.split_marks(content.text, held, content.marks)
    assert per_piece[0] == []
    assert _spans(held[1], per_piece[1]) == ["Part Two", "THE SACRAMENTS"]
    for piece, marks in zip(held, per_piece):
        assert headings.problems(piece, marks) == []


def test_hold_headings_joins_a_piece_of_only_a_title_to_the_next():
    content = MarkedText().heading("Chapter 2.—On Twins.", 3).paragraph(BODY).paragraph(BODY)
    pieces = ["Chapter 2.—On Twins.", BODY, BODY]
    assert headings.hold_headings(content.text, pieces, content.marks) == [
        "Chapter 2.—On Twins.\n\n" + BODY, BODY]


def test_hold_headings_leaves_unmarked_cuts_and_the_last_piece():
    content = MarkedText().paragraph(BODY).paragraph(BODY).heading("Trailing", 3)
    pieces = [BODY, BODY + "\n\nTrailing"]
    assert headings.hold_headings(content.text, pieces, content.marks) == pieces
    assert headings.hold_headings("x y", ["x", "y"], []) == ["x", "y"]


# --------------------------------------------------------------------------- the contract

def _h(at, end, level=3, **flags):
    return {"at": at, "end": end, "level": level, "role": "heading", **flags}


@pytest.mark.parametrize("content,marks,expected", [
    ("Title\n\n" + BODY, [_h(0, 4)], "not one whole paragraph"),
    ("Title\n\n" + BODY, [_h(0, 5, level=5)], "level"),
    ("Title\n\n" + BODY, [{"at": 0, "end": 5, "role": "caption"}], "role"),
    ("Title\n\n" + BODY, [_h(0, 5, colour="red")], "unknown keys"),
    ("Title\n\n" + BODY, [_h(0, 5), _h(0, 5)], "two marks"),
    ("Title", [_h(0, 5)], "only headings"),
    (BODY + "\n\nTitle", [_h(len(BODY) + 2, len(BODY) + 7)], "ends on a heading"),
    ("One\n\nThree\n\n" + BODY, [_h(0, 3, level=1), _h(5, 10, level=3)], "skips a level"),
    ("Article 1\n\n" + BODY, [_h(0, 9, level=1, pairs_next=True)], "pairs_next"),
    ("Title\n\n" + BODY, "nope", "not a list"),
])
def test_problems_names_each_broken_rule(content, marks, expected):
    found = headings.problems(content, marks)
    assert any(expected in f for f in found), found


def test_levels_may_rise_and_a_stack_may_restart():
    content = "One\n\nTwo\n\n" + BODY + "\n\nThree\n\n" + BODY
    marks = [_h(0, 3, level=1), _h(5, 8, level=2), _h(len(BODY) + 12, len(BODY) + 17, level=3)]
    assert headings.problems(content, marks) == []
    assert headings.problems(BODY, None) == []


# --------------------------------------------------------------------------- the classifier

@pytest.mark.parametrize("line", [
    "SECTION 1 The Avoidance of War", "Legitimate defense", "IN BRIEF",
    "I. GOD REVEALS HIS \"PLAN OF LOVING GOODNESS\"", "CHAPTER ONE: WHAT IS HAPPENING",
    "Chapter 26.—That in Certain Peculiar Cases the Examples of the Saints are Not to Be Followed.",
    "In the person of Christ the Head …",
])
def test_heading_like_lines(line):
    assert headings.looks_like_heading(line)


@pytest.mark.parametrize("line", [
    "And Pindar:—", "\"Gather, uphold, spur on", "§1. Universal or particular customs",
    "- the use of arms must not", "(1) What is a vow?", BODY, "Two\nlines", "1983",
    "This suffices for the Reply to the First Objection.",
])
def test_text_lines(line):
    assert not headings.looks_like_heading(line)


# --------------------------------------------------------------------------- health rules

def _passage(content, marks=None, anchor="a", position=0, chapter_key="ch-1",
             chapter_label="Chapter 1"):
    return Passage(content=content, reference=anchor, anchor=anchor, chapter_key=chapter_key,
                   chapter_label=chapter_label, position=position,
                   metadata={"headings": marks} if marks is not None else None)


def _doc(*passages, collection="encyclicals"):
    return Document(id="doc-1", collection=collection, title="A Document",
                    passages=list(passages))


def _rules(document):
    return [v.rule for v in health.check_documents(document.collection, [document])
            if v.severity == "block"]


@pytest.fixture
def opted_in(monkeypatch):
    patterns = copy.deepcopy(health.load_patterns())
    patterns["H7_unmarked_heading"]["collections"] = ["encyclicals"]
    monkeypatch.setattr(health, "load_patterns", lambda path=None: patterns)
    return patterns


def test_unmarked_collections_are_untouched_by_h7_and_h8():
    doc = _doc(_passage("Chapter 1\n\nLegitimate defense\n\n" + BODY))
    assert _rules(doc) == []


def test_h6_blocks_a_malformed_mark_in_any_collection():
    doc = _doc(_passage(BODY + "\n\nTrailing", [_h(len(BODY) + 2, len(BODY) + 10)]),
               collection="bible")
    assert _rules(doc) == ["H6_heading_marks"]


def test_h7_blocks_an_unmarked_heading_once_opted_in(opted_in):
    content = "Legitimate defense\n\n" + BODY
    assert _rules(_doc(_passage(content))) == ["H7_unmarked_heading"]
    assert _rules(_doc(_passage(content, [_h(0, 18)]))) == []
    # A one-paragraph passage is its own text, never a heading.
    assert _rules(_doc(_passage("Legitimate defense"))) == []


def test_h7_accepts_a_listed_paragraph_that_is_not_a_heading(opted_in):
    opted_in["H7_unmarked_heading"]["not_headings"] = {
        "doc-1": [{"text": "JOHN PAUL II", "reason": "signature"}]}
    assert _rules(_doc(_passage(BODY + "\n\nJohn Paul II"))) == []


def test_h8_wants_chapter_title_on_an_opening_repeat(opted_in):
    content = "CHAPTER ONE: WHAT IS HAPPENING TO OUR COMMON HOME\n\n" + BODY
    end = content.index("\n\n")
    label = "Chapter One - What is happening to our common home"
    plain = _passage(content, [_h(0, end, level=1)], chapter_label=label)
    flagged = _passage(content, [_h(0, end, level=1, chapter_title=True)], chapter_label=label)
    assert _rules(_doc(plain)) == ["H8_chapter_title"]
    assert _rules(_doc(flagged)) == []
    # Only where the passage opens its chapter.
    later = _passage(content, [_h(0, end, level=1)], anchor="b", position=1, chapter_label=label)
    assert _rules(_doc(flagged, later)) == []


def test_h8_reads_a_pair_as_one_heading(opted_in):
    content = "Article 1\n\nTHE REVELATION OF GOD\n\n" + BODY
    marks = [_h(0, 9, level=1, pairs_next=True), _h(11, 32, level=1)]
    doc = _doc(_passage(content, marks, chapter_label="The Revelation of God"))
    assert _rules(doc) == ["H8_chapter_title"]
    marks[0]["chapter_title"] = True
    assert _rules(doc) == []


# --------------------------------------------------------------------------- review fixes

def test_hold_headings_moves_a_heading_a_splitter_cut_inside():
    content = MarkedText().paragraph(BODY).heading("III. THE DIFFERENT KINDS OF SINS", 2) \
        .paragraph(BODY)
    cut = content.text.index("KINDS") - 1
    pieces = [content.text[:cut], content.text[cut + 1:]]
    held = headings.hold_headings(content.text, pieces, content.marks)
    assert held == [BODY, "III. THE DIFFERENT KINDS OF SINS\n\n" + BODY]
    assert headings.split_marks(content.text, held, content.marks)[1][0]["at"] == 0


@pytest.mark.parametrize("entry", [
    {"level": True}, {"level": 2.0}, {"level": 2, "pairs_next": "yes"},
    {"level": 1, "chapter_title": 1},
])
def test_problems_refuses_non_integer_levels_and_non_boolean_flags(entry):
    content = "Title\n\n" + BODY
    assert headings.problems(content, [{"at": 0, "end": 5, "role": "heading", **entry}])


def test_h7_blocks_a_piece_that_holds_only_an_unmarked_title(opted_in):
    assert _rules(_doc(_passage("Chapter 2.—On the Difference in the Health of Twins."))) \
        == ["H7_unmarked_heading"]


def test_h8_strips_only_a_division_prefix():
    assert headings.repeats_label("CHAPTER ONE: WHAT IS HAPPENING", "What is happening")
    assert headings.repeats_label("Article 1 THE REVELATION OF GOD", "The Revelation of God")
    assert not headings.repeats_label("Introduction", "A Historical Introduction")


def test_hold_headings_reads_a_cut_that_keeps_its_whitespace():
    content = MarkedText().heading("Title", 3).paragraph(BODY)
    assert headings.hold_headings(content.text, ["Title\n\n", BODY], content.marks) == [
        "Title\n\n" + BODY]
    plain = MarkedText().paragraph(BODY).paragraph(BODY)
    assert headings.hold_headings(plain.text, [BODY + "\n\n", BODY], [{"at": 0, "end": 1}]) \
        == [BODY + "\n\n", BODY]


def test_two_numbers_never_repeat_each_other():
    assert not headings.repeats_label("Article 1 The Church", "Article 2 The Church")


def test_a_sentence_opening_with_a_division_is_not_a_title():
    assert not headings.looks_like_division(
        "Article 1 of the Constitution sets out the rights of the faithful in detail.")
    assert not headings.looks_like_division("Article 1 of the Constitution sets out…")
    assert headings.looks_like_division("CHAPTER ONE: WHAT IS HAPPENING TO OUR COMMON HOME")


@pytest.mark.parametrize("line", [
    "I. WHY DID THE WORD BECOME FLESH?", "2. The diocesan curia and commissions",
    "A) General norms",
])
def test_numbered_section_heads_are_heading_like(line):
    assert headings.looks_like_heading(line)


@pytest.mark.parametrize("line", [
    "1. Let a bishop be ordained by two or three bishops.", "2. See above;",
])
def test_numbered_sentences_are_not(line):
    assert not headings.looks_like_heading(line)


def test_a_pair_matches_the_last_division_of_a_breadcrumb_label():
    label = "Part Three, Section Two, Chapter Two, Article 5, The Fifth Commandment"
    assert headings.repeats_label("Article 5 The Fifth Commandment", label)
    assert not headings.repeats_label("Article 4 The Fifth Commandment", label)


def test_a_pairs_title_cannot_open_another_pair():
    content = "Article 1\n\nTitle\n\nMore\n\n" + BODY
    marks = [_h(0, 9, level=1, pairs_next=True), _h(11, 16, level=1, pairs_next=True),
             _h(18, 22, level=1)]
    assert any("cannot open another pair" in f for f in headings.problems(content, marks))


def test_a_document_can_opt_in_before_its_collection(monkeypatch):
    """5.6b's works join H7 and H8 one document at a time: a listed document is checked,
    the rest of its collection is not."""
    patterns = copy.deepcopy(health.load_patterns())
    patterns["H7_unmarked_heading"]["documents"] = ["doc-1"]
    monkeypatch.setattr(health, "load_patterns", lambda path=None: patterns)
    content = "Chapter 1\n\nLegitimate defense\n\n" + BODY
    assert _rules(_doc(_passage(content), collection="medieval")) == ["H7_unmarked_heading"]
    other = Document(id="doc-2", collection="medieval", title="Another",
                     passages=[_passage(content)])
    assert _rules(other) == []


def test_a_bare_section_number_may_be_dropped_but_not_a_word():
    assert headings.repeats_label("Christian Education", "2. Christian Education")
    assert not headings.repeats_label("Society", "Civil Society")
