"""Tests for the WEB-C USFM Bible ingestion pipeline.

All tests are fully self-contained — no filesystem or database access.
"""
import sys
import os

# Set required env vars before importing ingest.bible, which imports config at module level.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import textwrap

import pytest

import registry
from ingest.bible import (
    _clean_usfm_text,
    _format_reference,
    _parse_ref,
    BookVerses,
    Verse,
    Pericope,
    build_documents,
    check_complete,
    group_paragraphs,
    group_verses,
    load_pericopes,
    load_usfm_directory,
    load_versification,
    parse_usfm_file,
    parse_usfm_paragraph_starts,
    parse_usfm_prologue,
    parse_usfm_titles,
)


# ---------------------------------------------------------------------------
# _clean_usfm_text helpers
# ---------------------------------------------------------------------------

def test_clean_strongs_markup_removed():
    """Strong's markup \\w word|strong="H1234"\\w* → just the word."""
    raw = r'\w The|strong="H0834"\w* \w beginning|strong="H7225"\w*'
    result = _clean_usfm_text(raw)
    assert "strong" not in result
    assert "The" in result
    assert "beginning" in result


def test_clean_footnote_stripped():
    """Footnotes \\f ... \\f* are completely removed."""
    raw = r'Some text\f + \fr 1:1 \ft footnote content\f* more text'
    result = _clean_usfm_text(raw)
    assert "footnote" not in result
    assert "Some text" in result
    assert "more text" in result


def test_clean_cross_reference_stripped():
    """Cross-references \\x ... \\x* are completely removed."""
    raw = r'Verse text\x + \xo 1:1 \xt Isaiah 7:14\x* continuation'
    result = _clean_usfm_text(raw)
    assert "Isaiah" not in result
    assert "Verse text" in result
    assert "continuation" in result


def test_clean_inline_markers_stripped():
    """Generic backslash markers like \\p, \\q1, \\wj are stripped."""
    raw = r'\p plain text \q1 indented text'
    result = _clean_usfm_text(raw)
    assert "\\p" not in result
    assert "\\q1" not in result
    assert "plain text" in result
    assert "indented text" in result


def test_clean_returns_plain_text():
    """A typical verse line cleans to readable plain text."""
    raw = r'\w In|strong="H1234"\w* \w the|strong="H9999"\w* beginning'
    result = _clean_usfm_text(raw)
    assert result == "In the beginning"


# ---------------------------------------------------------------------------
# parse_usfm_file
# ---------------------------------------------------------------------------

def test_parse_usfm_strips_strongs():
    """parse_usfm_file strips Strong's markup; verse text is clean."""
    import tempfile
    usfm = textwrap.dedent(r"""
        \id MAT
        \c 1
        \v 1 \w The|strong="G2424"\w* \w book|strong="G0000"\w* of genealogy
    """).lstrip()
    with tempfile.NamedTemporaryFile(suffix=".usfm", mode="w", encoding="utf-8", delete=False) as f:
        f.write(usfm)
        path = f.name
    try:
        result = parse_usfm_file(path)
        text = result.get((1, 1), "")
        assert "strong" not in text
        assert "G2424" not in text
        assert "The" in text
        assert "book" in text
        assert "genealogy" in text
    finally:
        os.unlink(path)


def test_parse_usfm_extracts_chapters_and_verses():
    """parse_usfm_file returns correct (chapter, verse) keys."""
    import tempfile
    usfm = textwrap.dedent(r"""
        \id GEN
        \c 1
        \v 1 First verse chapter one
        \v 2 Second verse chapter one
        \c 2
        \v 1 First verse chapter two
    """).lstrip()
    with tempfile.NamedTemporaryFile(suffix=".usfm", mode="w", encoding="utf-8", delete=False) as f:
        f.write(usfm)
        path = f.name
    try:
        result = parse_usfm_file(path)
        assert (1, 1) in result
        assert (1, 2) in result
        assert (2, 1) in result
        assert result[(1, 1)] == "First verse chapter one"
        assert result[(2, 1)] == "First verse chapter two"
    finally:
        os.unlink(path)


def test_parse_usfm_handles_multiline_verses():
    """Continuation lines (no \\v / \\c) are joined to the previous verse."""
    import tempfile
    usfm = textwrap.dedent(r"""
        \id MAT
        \c 5
        \v 3 Blessed are the poor in spirit,
        for theirs is the kingdom of heaven.
    """).lstrip()
    with tempfile.NamedTemporaryFile(suffix=".usfm", mode="w", encoding="utf-8", delete=False) as f:
        f.write(usfm)
        path = f.name
    try:
        result = parse_usfm_file(path)
        text = result.get((5, 3), "")
        assert "Blessed are the poor in spirit" in text
        assert "kingdom of heaven" in text
    finally:
        os.unlink(path)


def test_parse_usfm_multiline_strongs_on_continuation():
    """Strong's markup on continuation lines is also stripped."""
    import tempfile
    usfm = textwrap.dedent(r"""
        \id JHN
        \c 3
        \v 16 For \w God|strong="G2316"\w* so loved the world,
        that \w he|strong="G3588"\w* gave his only Son.
    """).lstrip()
    with tempfile.NamedTemporaryFile(suffix=".usfm", mode="w", encoding="utf-8", delete=False) as f:
        f.write(usfm)
        path = f.name
    try:
        result = parse_usfm_file(path)
        text = result.get((3, 16), "")
        assert "strong" not in text
        assert "God" in text
        assert "gave his only Son" in text
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# _parse_ref and load_pericopes
# ---------------------------------------------------------------------------

def test_parse_ref_single_word_book():
    book, ch, v = _parse_ref("Genesis 1:1")
    assert book == "Genesis"
    assert ch == 1
    assert v == 1


def test_parse_ref_multi_word_book():
    book, ch, v = _parse_ref("1 Corinthians 13:1")
    assert book == "1 Corinthians"
    assert ch == 13
    assert v == 1


def test_parse_ref_song_of_solomon():
    book, ch, v = _parse_ref("Song of Solomon 1:1")
    assert book == "Song of Solomon"
    assert ch == 1
    assert v == 1


def test_load_pericopes_returns_correct_structure():
    """load_pericopes groups pericopes by book and extracts start/end correctly."""
    import tempfile, json
    data = [
        {
            "Pericope": "The Creation",
            "Reference Start": "Genesis 1:1",
            "Reference End": "Genesis 2:3",
            "Verses": [],
        },
        {
            "Pericope": "The Sermon on the Mount",
            "Reference Start": "Matthew 5:1",
            "Reference End": "Matthew 7:29",
            "Verses": [],
        },
        {
            "Pericope": "The Beatitudes",
            "Reference Start": "Matthew 5:3",
            "Reference End": "Matthew 5:12",
            "Verses": [],
        },
    ]
    with tempfile.NamedTemporaryFile(
        suffix=".json", mode="w", encoding="utf-8", delete=False
    ) as f:
        json.dump(data, f)
        path = f.name
    try:
        grouped = load_pericopes(path)
        assert "Genesis" in grouped
        assert "Matthew" in grouped
        assert len(grouped["Genesis"]) == 1
        assert len(grouped["Matthew"]) == 2
        gen = grouped["Genesis"][0]
        assert gen.title == "The Creation"
        assert gen.start_chapter == 1
        assert gen.start_verse == 1
        assert gen.end_chapter == 2
        assert gen.end_verse == 3
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Reference format
# ---------------------------------------------------------------------------

def test_reference_format_single_verse():
    """Single verse: 'Matthew 5:3'."""
    assert _format_reference("Matthew", 5, 3, 5, 3) == "Matthew 5:3"


def test_reference_format_single_chapter():
    """Same-chapter range: 'Matthew 5:1–12'."""
    assert _format_reference("Matthew", 5, 1, 5, 12) == "Matthew 5:1–12"


def test_reference_format_cross_chapter():
    """Cross-chapter range: 'Genesis 1:1–2:3'."""
    assert _format_reference("Genesis", 1, 1, 2, 3) == "Genesis 1:1–2:3"


def test_reference_format_uses_en_dash():
    """Ranges use an en-dash (–), not a hyphen (-)."""
    ref = _format_reference("Romans", 1, 1, 1, 7)
    assert "–" in ref
    assert "-" not in ref


# ---------------------------------------------------------------------------
# 1.4a: every verse, extra pericopes, titles, prologue, Song of Songs
# ---------------------------------------------------------------------------

_HEADER = "book,start,end,title,nv_ref,lxx_ref,nab_ref\n"
_VERSIFICATION_HEADER = "book,source,target,scope,authority,evidence\n"


def _world(tmp_path, books: dict[str, str], pericopes: list[tuple], extras: str = "",
           versification: str = ""):
    """A USFM directory, a KJV pericope file, an extra-pericope CSV and a versification
    table under tmp_path. `books` maps a file name to its USFM text; `pericopes` holds
    (title, start, end)."""
    import json
    usfm = tmp_path / "usfm"
    usfm.mkdir()
    for name, text in books.items():
        (usfm / name).write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    kjv = tmp_path / "kjv.json"
    kjv.write_text(json.dumps([{"Pericope": t, "Reference Start": s, "Reference End": e,
                                "Verses": []} for t, s, e in pericopes]), encoding="utf-8")
    csv_path = tmp_path / "extra.csv"
    csv_path.write_text(_HEADER + extras, encoding="utf-8")
    table = tmp_path / "versification.csv"
    table.write_text(_VERSIFICATION_HEADER + versification, encoding="utf-8")
    return dict(usfm_dir=str(usfm), pericope_path=str(kjv), extra_path=str(csv_path),
                versification_path=str(table))


def _build(world) -> dict:
    return {d.title: d for d in build_documents(**world)}


_MARK = r"""
    \id MRK
    \c 2
    \p
    \v 1 One.
    \v 2 Two.
    \v 3 Three.
    \c 3
    \v 1 Four.
    \v 2 Five.
"""


def test_every_usfm_verse_lands_in_a_passage(tmp_path):
    # Mark 2:3 is outside every pericope: it joins the story before it (Carter,
    # 10 Nov 2026), so that passage keeps its anchor and grows by a verse.
    world = _world(tmp_path, {"71-MRK.usfm": _MARK},
                   [("Sabbath", "Mark 2:1", "Mark 2:2"), ("Healing", "Mark 3:1", "Mark 3:2")])
    mark = _build(world)["Mark"]
    assert [(p.anchor, p.reference) for p in mark.passages] == [
        ("mark/2/1", "Mark 2:1–3"), ("mark/3/1", "Mark 3:1–2")]
    assert "{{v:3}} Three." in mark.passages[0].content
    assert mark.passages[0].metadata["pericope"] == "Sabbath"


def test_overlapping_pericopes_give_the_verses_to_the_later_one(tmp_path):
    # Numbers 16:28-37 sits in two KJV pericopes; the one that opens on it keeps it.
    world = _world(tmp_path, {"71-MRK.usfm": _MARK},
                   [("Korah", "Mark 2:1", "Mark 2:3"), ("Earth", "Mark 2:2", "Mark 3:2")])
    mark = _build(world)["Mark"]
    assert [(p.anchor, p.reference, p.metadata["pericope"]) for p in mark.passages] == [
        ("mark/2/1", "Mark 2:1", "Korah"), ("mark/2/2", "Mark 2:2–3", "Earth"),
        ("mark/3/1", "Mark 3:1–2", "Earth")]


def test_a_gap_at_a_chapter_start_is_its_own_untitled_passage():
    verses = [Verse("Mark", 3, 1, "Four."), Verse("Mark", 3, 2, "Five.")]
    groups = group_verses(verses, [Pericope("Healing", "Mark", 3, 2, 3, 2)], [])
    assert [(g.title, [v for _, v, _ in g.verses]) for g in groups] == [
        (None, [1]), ("Healing", [2])]


_ESTHER = r"""
    \id ESG
    \c 4
    \p
    \v 17 Hebrew seventeen.
    \v 18 [Mordecai prays.
    \v 19 There is no one who can oppose you.
    \v 29 And queen Esther took refuge in the Lord.
    \v 30 She put on garments of distress.]
"""


def test_extra_pericope_labels_apply(tmp_path):
    extras = ("Esther,4:18,4:19,Addition C: Mordecai's prayer,Esther 4:17a–m,Esther 4:17a–i,"
              "Esther C:1–11\n"
              "Esther,4:29,4:30,Addition C: Esther's prayer,Esther 4:17n–kk,Esther 4:17k–z,"
              "Esther C:12–30\n")
    # The KJV pericope runs to 4:17 only; a row beats it even where they overlap.
    world = _world(tmp_path, {"43-ESG.usfm": _ESTHER},
                   [("Esther's Resolve", "Esther 4:17", "Esther 4:29")], extras)
    esther = _build(world)["Esther"]
    by_anchor = {p.anchor: p for p in esther.passages}
    assert list(by_anchor) == ["esther/4/17", "esther/4/18", "esther/4/29"]
    assert by_anchor["esther/4/17"].reference == "Esther 4:17"
    mordecai, queen = by_anchor["esther/4/18"], by_anchor["esther/4/29"]
    assert mordecai.reference == "Esther 4:18–19"
    assert mordecai.metadata["pericope"] == "Addition C: Mordecai's prayer"
    assert (mordecai.metadata["nv_ref"], mordecai.metadata["lxx_ref"],
            mordecai.metadata["nab_ref"]) == ("Esther 4:17a–m", "Esther 4:17a–i", "Esther C:1–11")
    assert (queen.metadata["nv_ref"], queen.metadata["lxx_ref"],
            queen.metadata["nab_ref"]) == ("Esther 4:17n–kk", "Esther 4:17k–z", "Esther C:12–30")
    assert "nv_ref" not in by_anchor["esther/4/17"].metadata


def test_song_of_songs_title_keeps_frozen_id_and_anchor_slug(tmp_path):
    song = r"""
        \id SNG
        \c 1
        \p
        \v 1 The Song of songs, which is Solomon’s.
        \v 2 Let him kiss me with the kisses of his mouth.
    """
    # The KJV file still names the book "Song of Solomon".
    world = _world(tmp_path, {"22-SNG.usfm": song},
                   [("The Song", "Song of Solomon 1:1", "Song of Solomon 1:2")])
    doc = _build(world)["Song of Songs"]
    assert doc.id == "9df0b246-febf-52e3-b56f-fa7bf1c002de"
    p = doc.passages[0]
    assert (p.anchor, p.chapter_key) == ("song-of-solomon/1/1", "song-of-solomon/1")
    assert (p.reference, p.chapter_label) == ("Song of Songs 1:1–2", "Song of Songs 1")
    assert p.metadata["pericope"] == "The Song"
    frozen = registry.current().row_by_anchor[(doc.id, "song-of-solomon/1/1")]["passage_id"]
    assert registry.resolve_passage_id(doc.id, p.anchor) == frozen


_PSALMS = r"""
    \id PSA
    \c 3
    \d A Psalm by David, when he fled from Absalom his son.
    \q1
    \v 1 LORD, how my adversaries have increased!
    \v 2 Many say of my soul,
    \c 119
    \d ALEPH
    \q1
    \v 1 Blessed are those whose ways are blameless.
    \v 2 Blessed are those who keep his statutes.
    \d BETH
    \q1
    \v 3 How can a young man keep his way pure?
"""


def test_psalm_title_opens_first_passage(tmp_path):
    world = _world(tmp_path, {"20-PSA.usfm": _PSALMS},
                   [("Book 1", "Psalms 3:1", "Psalms 3:2"), ("Book 5", "Psalms 119:1", "Psalms 119:3")])
    psalms = _build(world)["Psalms"]
    first = psalms.passages[0]
    assert (first.anchor, first.reference, first.unit_label) == ("psalms/3/1", "Psalms 3:1–2", "1")
    assert first.content.startswith(
        "A Psalm by David, when he fled from Absalom his son. LORD, how my adversaries")
    # Psalm 119's letters head their stanzas: the later one opens the verse it precedes.
    assert psalms.passages[1].content.startswith("ALEPH Blessed are those")
    assert "{{v:3}} BETH How can a young man" in psalms.passages[1].content


def test_numbered_heading_is_not_read_as_verse_text(tmp_path):
    daniel = r"""
        \id DAG
        \c 3
        \p
        \v 23 These three men fell down bound.
        \s1 THE SONG OF THE THREE HOLY CHILDREN\f + \fr 3:24 \ft a note\f*
        \p
        \v 24 They walked in the midst of the fire.
    """
    path = tmp_path / "dag.usfm"
    path.write_text(textwrap.dedent(daniel).lstrip(), encoding="utf-8")
    verses = parse_usfm_file(str(path))
    assert verses[(3, 23)] == "These three men fell down bound."


_SIRACH = r"""
    \id SIR Ecclesiasticus
    \h Sirach
    \ip \bk The Wisdom of Jesus the Son of Sirach\bk* is recognized as Deuterocanonical Scripture.
    \is1 The Prologue of the Wisdom of Jesus the Son of Sirach.
    \ip WHEREAS many and great things have been delivered to us by the law.
    \c 1
    \b
    \q1
    \v 1 All wisdom comes from the Lord,
    \v 2 Who can count the sand of the seas?
"""


def test_sirach_prologue_is_its_own_passage(tmp_path):
    world = _world(tmp_path, {"46-SIR.usfm": _SIRACH}, [])
    sirach = _build(world)["Sirach"]
    prologue, chapter = sirach.passages
    assert (prologue.anchor, prologue.reference, prologue.chapter_key, prologue.chapter_label,
            prologue.position) == ("sirach/prologue", "Sirach, Prologue", "sirach/prologue",
                                   "Prologue", 0)
    assert prologue.content == "WHEREAS many and great things have been delivered to us by the law."
    # WEB-C's own introduction is not Scripture and reaches no passage.
    assert all("Deuterocanonical" not in p.content for p in sirach.passages)
    assert (chapter.anchor, chapter.reference, chapter.position) == \
        ("sirach/1/1", "Sirach 1:1–2", 1)


def test_check_complete_raises_on_a_lost_verse_or_prologue():
    book = BookVerses("Mark", "MRK", "NT", [Verse("Mark", 2, 1, "One."), Verse("Mark", 2, 2, ""),
                                           Verse("Mark", 2, 3, "Three.")])
    check_complete(book, {(2, 1), (2, 3)}, prologue_placed=False)    # 2:2 has no text
    with pytest.raises(ValueError, match="1 verses reach no passage"):
        check_complete(book, {(2, 1)}, prologue_placed=False)
    book.titles = {(2, 2): "A title"}       # a title gives an empty verse text to place
    with pytest.raises(ValueError, match="reach no passage"):
        check_complete(book, {(2, 1), (2, 3)}, prologue_placed=False)
    book.titles, book.prologue = {}, "Whereas"
    with pytest.raises(ValueError, match="prologue"):
        check_complete(book, {(2, 1), (2, 3)}, prologue_placed=False)


def test_parse_usfm_titles_and_prologue(tmp_path):
    psa, sir = tmp_path / "psa.usfm", tmp_path / "sir.usfm"
    psa.write_text(textwrap.dedent(_PSALMS).lstrip(), encoding="utf-8")
    sir.write_text(textwrap.dedent(_SIRACH).lstrip(), encoding="utf-8")
    assert parse_usfm_titles(str(psa)) == {
        (3, 1): "A Psalm by David, when he fled from Absalom his son.",
        (119, 1): "ALEPH", (119, 3): "BETH"}
    assert parse_usfm_prologue(str(psa)) == ""
    assert parse_usfm_prologue(str(sir)).startswith("WHEREAS")


# ---------------------------------------------------------------------------
# 1.4b: Nova Vulgata numbering
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Deuterocanonical paragraph passages (1.4c)
# ---------------------------------------------------------------------------

def _prose(words: int, seed: str) -> str:
    return " ".join(f"{seed}{i}" for i in range(words)) + "."


def _tobit(paragraphs_by_chapter: dict[int, list[list[int]]]) -> str:
    """Tobit USFM: each chapter's paragraphs, each paragraph a list of verse sizes in
    words (about 7 characters a word)."""
    lines = [r"\id TOB"]
    for chapter, paragraphs in paragraphs_by_chapter.items():
        lines.append(rf"\c {chapter}")
        verse = 0
        for paragraph in paragraphs:
            lines.append(r"\p")
            for words in paragraph:
                verse += 1
                lines.append(rf"\v {verse} {_prose(words, f'w{chapter}x{verse}x')}")
    return "\n".join(lines) + "\n"


def _verses_of(p) -> list[int]:
    import re
    return [int(p.unit_label)] + [int(n) for n in re.findall(r"\{\{v:(\d+)\}\}", p.content)]


def test_parse_usfm_paragraph_starts(tmp_path):
    path = tmp_path / "41-TOB.usfm"
    path.write_text(textwrap.dedent(r"""
        \id TOB
        \c 1
        \v 1 One.
        \v 2 Two.
        \p
        \v 3 Three, a long verse whose last words
        \p open a paragraph.
        \v 4 Four.
        \v 5 Five,
        \p and a paragraph that holds most of verse five.
        \v 6 Six.
        \b
        \q1
        \v 7 Seven,
        \b
        \q1 still seven and most of it after the stanza break.
        \v 8 Eight.
        \c 2
        \p A heading-like line before the first verse.
        \v 1 One.
    """).lstrip(), encoding="utf-8")
    # A verse a break falls inside goes with the paragraph holding most of it: verse 3
    # stays before its break, so verse 4 opens; verses 5 and 7 open theirs. A chapter's
    # first verse always opens one.
    assert parse_usfm_paragraph_starts(str(path)) == {(1, 1), (1, 3), (1, 4), (1, 5), (1, 7),
                                                       (2, 1)}


def test_deutero_groups_paragraphs_within_cap(tmp_path):
    # Eight paragraphs of about 400 characters: grouped two or three to a passage, each
    # within 600 to 1,800 characters, none cut inside a paragraph, all untitled.
    world = _world(tmp_path, {"41-TOB.usfm": _tobit({1: [[30, 25]] * 8})}, [])
    tobit = _build(world)["Tobit"]
    assert len(tobit.passages) > 1
    starts = {1 + 2 * k for k in range(8)}
    verses = []
    for p in tobit.passages:
        assert 600 <= len(p.content) <= 1800, (p.reference, len(p.content))
        held = _verses_of(p)
        assert held[0] in starts and held[-1] + 1 in starts | {17}
        assert p.anchor == f"tobit/1/{held[0]}"
        assert p.reference == f"Tobit 1:{held[0]}–{held[-1]}"
        assert "pericope" not in p.metadata
        verses += held
    assert verses == list(range(1, 17))


def test_deutero_never_crosses_chapter(tmp_path):
    # Chapter 1 ends in a short paragraph and chapter 2 opens with one: each stays in its
    # own chapter, joined to its neighbour there rather than left under 300 characters.
    world = _world(tmp_path, {"41-TOB.usfm": _tobit({1: [[60, 60], [10]], 2: [[10], [60, 60]]})},
                   [])
    tobit = _build(world)["Tobit"]
    assert [(p.anchor, p.reference) for p in tobit.passages] == \
        [("tobit/1/1", "Tobit 1:1–3"), ("tobit/2/1", "Tobit 2:1–3")]
    for p in tobit.passages:
        assert p.chapter_key == f"tobit/{p.anchor.split('/')[1]}"


def test_deutero_short_paragraph_joins_a_long_one_rather_than_stand_alone():
    # A paragraph over 1,800 characters stands alone, but a paragraph under 300 beside
    # it joins it rather than be a passage of its own (Tobit 14:1-2).
    from ingest.bible import _group_content
    verses = [Verse("Tobit", 14, 1, _prose(30, "a"))] + \
        [Verse("Tobit", 14, v, _prose(80, f"b{v}")) for v in range(2, 8)] + \
        [Verse("Tobit", 14, v, _prose(80, f"c{v}")) for v in range(8, 10)]
    groups = group_paragraphs(verses, {(14, 1), (14, 2), (14, 8)})
    assert [[v for _, v, _ in g.verses] for g in groups] == [[1, 2, 3, 4, 5, 6, 7], [8, 9]]
    sizes = [len(_group_content(g.verses)) for g in groups]
    assert sizes[0] > 2200 and 600 <= sizes[1] <= 1800, sizes


_NV = "Nova Vulgata,cited so by the Catechism"


def _summary(doc):
    return [(p.anchor, p.reference, p.chapter_key, p.metadata.get("source_ref"))
            for p in doc.passages]


def test_versification_moves_joel_2_28_to_3_1(tmp_path):
    joel = r"""
        \id JOL
        \c 2
        \p
        \v 27 You will know that I am in the middle of Israel.
        \v 28 It will happen afterward, that I will pour out my Spirit on all flesh;
        \v 29 and also on the servants I will pour out my Spirit.
        \c 3
        \p
        \v 1 For, behold, in those days,
        \v 2 I will gather all nations.
    """
    world = _world(tmp_path, {"29-JOL.usfm": joel},
                   [("Restoration", "Joel 2:27", "Joel 2:27"), ("Spirit", "Joel 2:28", "Joel 2:29"),
                    ("Nations", "Joel 3:1", "Joel 3:2")],
                   versification=f"Joel,2:28-2:29,3:1-3:2,book,{_NV}\n"
                                 f"Joel,3:1-3:2,4:1-4:2,book,{_NV}\n")
    doc = _build(world)["Joel"]
    assert _summary(doc) == [
        ("joel/nv/2/27", "Joel 2:27", "joel/nv/2", "Joel 2:27"),
        ("joel/nv/3/1", "Joel 3:1–2", "joel/nv/3", "Joel 2:28–29"),
        ("joel/nv/4/1", "Joel 4:1–2", "joel/nv/4", "Joel 3:1–2")]
    spirit = doc.passages[1]
    assert (spirit.chapter_label, spirit.unit_label, spirit.metadata["pericope"]) == (
        "Joel 3", "1", "Spirit")
    assert spirit.content.startswith("It will happen afterward") and "{{v:2}} and also" in \
        spirit.content


def test_versification_moves_malachi_4_to_3_19(tmp_path):
    malachi = r"""
        \id MAL
        \c 3
        \p
        \v 18 Then you will again discern between the righteous and the wicked.
        \c 4
        \p
        \v 1 For behold, the day comes, burning like a furnace;
        \v 2 But to you who fear my name shall the sun of righteousness arise.
    """
    world = _world(tmp_path, {"39-MAL.usfm": malachi},
                   [("Remembrance", "Malachi 3:18", "Malachi 3:18"),
                    ("The Day", "Malachi 4:1", "Malachi 4:2")],
                   versification=f"Malachi,4:1-4:2,3:19-3:20,book,{_NV}\n")
    doc = _build(world)["Malachi"]
    assert _summary(doc) == [
        ("malachi/nv/3/18", "Malachi 3:18", "malachi/nv/3", "Malachi 3:18"),
        ("malachi/nv/3/19", "Malachi 3:19–20", "malachi/nv/3", "Malachi 4:1–2")]
    assert "{{v:20}} But to you" in doc.passages[1].content


def test_versification_moves_jonah_1_17_to_2_1(tmp_path):
    # Carter, 10 Nov 2026: the fish verse opens the prayer, by a row of the extra table
    # in the published numbers; the KJV pericope alone would leave it a passage of its own.
    jonah = r"""
        \id JON
        \c 1
        \p
        \v 16 Then the men feared the LORD exceedingly.
        \v 17 The LORD prepared a huge fish to swallow up Jonah.
        \c 2
        \p
        \v 1 Then Jonah prayed to the LORD, his God, out of the fish’s belly.
        \v 2 He said, “I called because of my affliction to the LORD.
    """
    world = _world(tmp_path, {"32-JON.usfm": jonah},
                   [("Cast into the Sea", "Jonah 1:16", "Jonah 1:17"),
                    ("Prayer", "Jonah 2:1", "Jonah 2:2")],
                   extras="Jonah,2:1,2:3,Prayer,,,\n",
                   versification=f"Jonah,1:17-1:17,2:1-2:1,book,{_NV}\n"
                                 f"Jonah,2:1-2:2,2:2-2:3,book,{_NV}\n")
    doc = _build(world)["Jonah"]
    assert _summary(doc) == [
        ("jonah/nv/1/16", "Jonah 1:16", "jonah/nv/1", "Jonah 1:16"),
        ("jonah/nv/2/1", "Jonah 2:1–3", "jonah/nv/2", "Jonah 1:17–2:2")]
    assert doc.passages[1].content.startswith("The LORD prepared a huge fish")
    (tmp_path / "kjv-only").mkdir()
    without_row = _build(_world(tmp_path / "kjv-only", {"32-JON.usfm": jonah},
                                [("Cast into the Sea", "Jonah 1:16", "Jonah 1:17"),
                                 ("Prayer", "Jonah 2:1", "Jonah 2:2")],
                                versification=f"Jonah,1:17-1:17,2:1-2:1,book,{_NV}\n"
                                              f"Jonah,2:1-2:2,2:2-2:3,book,{_NV}\n"))["Jonah"]
    assert [p.reference for p in without_row.passages] == ["Jonah 1:16", "Jonah 2:1",
                                                            "Jonah 2:2–3"]


def test_passage_scope_moves_a_chapter_break_and_keeps_other_anchors(tmp_path):
    # WEB-C ends Hosea 11 with "Ephraim surrounds me with lies", which the Nova Vulgata
    # numbers 12:1 (#317). Only passages holding a moved verse take the `nv` segment, so
    # Hosea 11:11 keeps its anchor and chapter key; the moved verse opens chapter 12's
    # passage through an extra row, not a passage of its own.
    hosea = r"""
        \id HOS
        \c 11
        \p
        \v 11 They will come trembling like a bird out of Egypt.
        \v 12 Ephraim surrounds me with lies.
        \c 12
        \p
        \v 1 Ephraim feeds on wind.
        \v 2 Yahweh also has a controversy with Judah.
    """
    pericopes = [("Love", "Hosea 11:11", "Hosea 11:12"), ("Reproof", "Hosea 12:1", "Hosea 12:2")]
    table = f"Hosea,11:12-11:12,12:1-12:1,passage,{_NV}\nHosea,12:1-12:2,12:2-12:3,passage,{_NV}\n"
    doc = _build(_world(tmp_path, {"28-HOS.usfm": hosea}, pericopes,
                        extras="Hosea,12:1,12:3,Reproof,,,\n", versification=table))["Hosea"]
    assert _summary(doc) == [
        ("hosea/11/11", "Hosea 11:11", "hosea/11", None),
        ("hosea/nv/12/1", "Hosea 12:1–3", "hosea/12", "Hosea 11:12–12:2")]
    assert doc.passages[1].content.startswith("Ephraim surrounds me with lies")
    (tmp_path / "kjv-only").mkdir()
    without_row = _build(_world(tmp_path / "kjv-only", {"28-HOS.usfm": hosea}, pericopes,
                                versification=table))["Hosea"]
    assert [p.reference for p in without_row.passages] == ["Hosea 11:11", "Hosea 12:1",
                                                            "Hosea 12:2–3"]


def test_romans_doxology_is_16_25_to_27(tmp_path):
    # WEB-C prints the doxology at 14:24-26 and leaves a bare 16:25 marker; 16:24 stays.
    romans = r"""
        \id ROM
        \c 14
        \p
        \v 23 But he who doubts is condemned if he eats.
        \v 24 Now to him who is able to establish you
        \v 25 but now is revealed,
        \v 26 to the only wise God, through Jesus Christ, to whom be the glory forever! Amen.
        \c 16
        \p
        \v 23 Gaius, my host, greets you.
        \v 24 The grace of our Lord Jesus Christ be with you all! Amen.
        \v 25 \f + \fr 16:25 \ft TR places Romans 14:24-26 at the end of Romans.\f*
    """
    world = _world(tmp_path, {"75-ROM.usfm": romans},
                   [("Love", "Romans 14:23", "Romans 14:23"),
                    ("Greetings", "Romans 16:23", "Romans 16:23"),
                    ("Doxology", "Romans 16:25", "Romans 16:27")],
                   versification=f"Romans,14:24-14:26,16:25-16:27,passage,{_NV}\n")
    doc = _build(world)["Romans"]
    assert _summary(doc) == [
        ("romans/14/23", "Romans 14:23", "romans/14", None),
        ("romans/16/23", "Romans 16:23–24", "romans/16", None),
        ("romans/nv/16/25", "Romans 16:25–27", "romans/16", "Romans 14:24–26")]
    assert doc.passages[2].metadata["pericope"] == "Doxology"
    assert doc.passages[2].content.startswith("Now to him who is able")


def test_versification_table_refuses_a_bad_row(tmp_path):
    def table(rows):
        path = tmp_path / "v.csv"
        path.write_text(_VERSIFICATION_HEADER + rows, encoding="utf-8")
        return str(path)
    with pytest.raises(ValueError, match="another length"):
        load_versification(table(f"Joel,2:28-2:32,3:1-3:4,book,{_NV}\n"))
    with pytest.raises(ValueError, match="inside one chapter"):
        load_versification(table(f"Joel,2:28-3:2,3:1-3:7,book,{_NV}\n"))
    with pytest.raises(ValueError, match="two verses land"):
        load_versification(table(f"Joel,2:1-2:2,3:1-3:2,book,{_NV}\nJoel,2:3-2:3,3:2-3:2,book,{_NV}\n"))
    with pytest.raises(ValueError, match="disagree on scope"):
        load_versification(table(f"Joel,2:1-2:1,3:1-3:1,book,{_NV}\nJoel,2:2-2:2,3:2-3:2,passage,{_NV}\n"))
    # Every row says why it moves the verses (#317).
    with pytest.raises(ValueError, match="no evidence"):
        load_versification(table("Joel,2:1-2:1,3:1-3:1,book,Nova Vulgata,\n"))
    # Landing on a verse that keeps its text is refused; on an empty marker it is not.
    mark = tmp_path / "usfm"
    mark.mkdir()
    (mark / "41-MRK.usfm").write_text("\\id MRK\n\\c 1\n\\v 1 One.\n\\v 2 Two.\n",
                                      encoding="utf-8")
    with pytest.raises(ValueError, match="which has text"):
        load_usfm_directory(str(mark), load_versification(table(f"Mark,1:1-1:1,1:2-1:2,book,{_NV}\n")))
    with pytest.raises(ValueError, match="source lacks"):
        load_usfm_directory(str(mark), load_versification(table(f"Mark,1:3-1:3,1:4-1:4,book,{_NV}\n")))


# ---------------------------------------------------------------------------
# Vendored source (skipped where the WEB-C files are not vendored)
# ---------------------------------------------------------------------------

_ROOT = os.path.join(os.path.dirname(__file__), "..")
_vendored = os.path.isdir(os.path.join(_ROOT, "sources", "bible", "eng-web-c_usfm"))


@pytest.fixture(scope="module")
def vendored_docs():
    return {d.title: d for d in build_documents()}


@pytest.mark.skipif(not _vendored, reason="WEB-C USFM not vendored")
def test_vendored_every_verse_once_and_daniel_chapters(vendored_docs):
    import re
    from collections import Counter
    from ingest.bible import load_usfm_directory
    books = load_usfm_directory(os.path.join(_ROOT, "sources", "bible", "eng-web-c_usfm"))
    assert len(books) == len(vendored_docs) == 73
    for name, book in books.items():
        seen: Counter = Counter()
        last = None
        for p in vendored_docs[name].passages:
            if p.anchor.endswith("/prologue"):
                continue
            chapter = int(p.chapter_key.rsplit("/", 1)[1])
            held = [int(p.unit_label)] + [int(n) for n in re.findall(r"\{\{v:(\d+)\}\}", p.content)]
            if (chapter, held[0]) == last:
                held = held[1:]     # a verse cut across pieces continues here (Esther 8:13)
            seen.update((chapter, v) for v in held)
            last = (chapter, held[-1]) if held else last
        # Every verse with text is in exactly one passage; a verse with none (Sirach 1:5,
        # Romans 16:25) may be left out.
        with_text = {(v.chapter, v.verse) for v in book.verses if v.text.strip()}
        assert with_text <= set(seen) <= {(v.chapter, v.verse) for v in book.verses}, name
        assert max(seen.values()) == 1, (name, [k for k, n in seen.items() if n > 1])
    daniel = Counter(v.chapter for v in books["Daniel"].verses)
    # Nova Vulgata chapter breaks (#317): 3:98-100 and 6:1 are WEB-C 4:1-3 and 5:31.
    assert [daniel[c] for c in range(1, 15)] == [21, 49, 100, 34, 30, 29, 28, 27, 27, 21, 45,
                                                13, 64, 42]


@pytest.mark.skipif(not _vendored, reason="WEB-C USFM not vendored")
def test_vendored_restored_passages(vendored_docs):
    def at(title, anchor):
        return next(p for p in vendored_docs[title].passages if p.anchor == anchor)
    assert at("Psalms", "psalms/51/1").content.startswith(
        "For the Chief Musician. A Psalm by David, when Nathan the prophet came to him")
    assert at("Daniel", "daniel/3/24").metadata["pericope"] == \
        "Prayer of Azariah and Song of the Three"
    assert at("Daniel", "daniel/3/91").reference == "Daniel 3:91–97"
    assert at("Daniel", "daniel/13/1").metadata["pericope"] == "Susanna"
    assert at("Daniel", "daniel/14/1").metadata["pericope"] == "Bel and the Dragon"
    assert "HOLY CHILDREN" not in at("Daniel", "daniel/3/19").content
    assert at("Esther", "esther/10/4").metadata["nab_ref"] == "Esther F:1–11"
    assert at("Romans", "romans/nv/16/25").reference == "Romans 16:25–27"
    assert at("Numbers", "numbers/16/28").reference == "Numbers 16:28–40"
    assert at("Mark", "mark/2/23").reference == "Mark 2:23–28"
    assert at("Sirach", "sirach/prologue").content.startswith("WHEREAS many and great things")


_RENUMBERED = ("Joel", "Malachi", "Jonah")


@pytest.mark.skipif(not _vendored, reason="WEB-C USFM not vendored")
def test_renumbered_books_use_nv_anchor_segment(vendored_docs):
    from collections import Counter
    books = load_usfm_directory(os.path.join(_ROOT, "sources", "bible", "eng-web-c_usfm"))
    def chapters(name):
        counted = Counter(v.chapter for v in books[name].verses if v.text.strip())
        return [counted[c] for c in sorted(counted)]
    assert chapters("Joel") == [20, 27, 5, 21]
    assert chapters("Malachi") == [14, 17, 24]
    assert chapters("Jonah") == [16, 11, 10, 11]
    assert chapters("Romans")[13] == 23 and chapters("Romans")[15] == 27
    for name in _RENUMBERED:
        slug = name.lower()
        for p in vendored_docs[name].passages:
            assert p.anchor.startswith(f"{slug}/nv/"), p.anchor
            assert p.chapter_key.startswith(f"{slug}/nv/"), p.chapter_key
            assert p.metadata["source_ref"].startswith(name), p.metadata
    by_anchor = {p.anchor: p for d in vendored_docs.values() for p in d.passages}
    assert by_anchor["joel/nv/3/1"].content.startswith("“It will happen afterward, that I will pour")
    assert by_anchor["malachi/nv/3/19"].metadata["source_ref"] == "Malachi 4:1–6"
    assert by_anchor["jonah/nv/2/1"].reference == "Jonah 2:1–11"
    assert by_anchor["jonah/nv/2/1"].content.startswith("The LORD prepared a huge fish")
    assert [p.anchor for p in vendored_docs["Romans"].passages if "/nv/" in p.anchor] == \
        ["romans/nv/16/25"]
    assert by_anchor["romans/16/21"].reference == "Romans 16:21–24"
    # The doxology's registry row was relabelled, never live: it keeps the ID 1.4a froze.
    rom = vendored_docs["Romans"].id
    assert registry.resolve_passage_id(rom, "romans/nv/16/25") == \
        "5410d634-8f68-5f3d-bbe5-46abb6c7e761"


@pytest.mark.skipif(not _vendored, reason="WEB-C USFM not vendored")
def test_every_old_joel_malachi_and_jonah_passage_has_a_redirect(vendored_docs):
    """Each WEB-C-numbered row redirects to the Nova Vulgata passage now holding its
    first verse, and no WEB-C anchor is built again (D1)."""
    import re
    reg = registry.current()
    table = load_versification(os.path.join(_ROOT, "bible_versification.csv"))
    open_from = {r["old_passage_id"]: r for r in registry.open_redirects(reg)}
    for name in _RENUMBERED:
        doc = vendored_docs[name]
        built = {p.anchor: p for p in doc.passages}
        old = [r for r in reg.passages if r["document_id"] == doc.id and "/nv/" not in r["anchor"]]
        assert len(old) == {"Joel": 9, "Malachi": 9, "Jonah": 8}[name]
        for row in old:
            assert row["status"] == "redirected" and row["anchor"] not in built
            redirect = open_from[row["passage_id"]]
            assert redirect["kind"] in ("renumbered", "split", "merged")
            target = built[redirect["new_anchor"]]
            _, c, v = row["anchor"].split("/")
            nc, nv = table[name].moves.get((int(c), int(v)), (int(c), int(v)))
            held = {int(target.unit_label)} | {int(x) for x in
                                               re.findall(r"\{\{v:(\d+)\}\}", target.content)}
            assert target.chapter_key.endswith(f"/{nc}") and nv in held, (row["anchor"], target.anchor)
    kinds = {r["old_anchor"]: r["kind"] for r in open_from.values()
             if r["old_anchor"] in ("joel/2/28", "jonah/1/11", "jonah/2/1")}
    assert kinds == {"joel/2/28": "renumbered", "jonah/1/11": "split", "jonah/2/1": "merged"}


# #317: Nova Vulgata chapter breaks in Daniel and Hosea (Carter, 12 Nov 2026). Old row
# anchor -> (new anchor, kind); every other passage of the two books keeps its anchor and ID.
_NV_PASSAGE_MOVES = {
    "daniel/4/1": ("daniel/nv/3/98", "renumbered"),
    "daniel/4/4": ("daniel/nv/4/1", "renumbered"),
    "daniel/4/19": ("daniel/nv/4/16", "renumbered"),
    "daniel/4/28": ("daniel/nv/4/25", "renumbered"),
    "daniel/4/34": ("daniel/nv/4/31", "renumbered"),
    "daniel/6/1": ("daniel/nv/6/1", "merged"),
    "daniel/6/10": ("daniel/nv/6/11", "renumbered"),
    "daniel/6/25": ("daniel/nv/6/26", "renumbered"),
    "hosea/2/1": ("hosea/nv/2/3", "renumbered"),
    "hosea/2/14": ("hosea/nv/2/16", "renumbered"),
    "hosea/12/1": ("hosea/nv/12/1", "merged"),
    "hosea/14/1": ("hosea/nv/14/2", "renumbered"),
    "hosea/14/4": ("hosea/nv/14/5", "renumbered"),
}


@pytest.mark.skipif(not _vendored, reason="WEB-C USFM not vendored")
def test_daniel_and_hosea_use_nova_vulgata_chapter_breaks(vendored_docs):
    from collections import Counter
    books = load_usfm_directory(os.path.join(_ROOT, "sources", "bible", "eng-web-c_usfm"))
    def chapters(name):
        counted = Counter(v.chapter for v in books[name].verses if v.text.strip())
        return [counted[c] for c in sorted(counted)]
    # Checked against the Nova Vulgata on vatican.va (12 Nov 2026). NV divides WEB-C's
    # Hosea 2:23 into 2:25-26; verse divisions inside a chapter stay WEB-C's (1.4b).
    assert chapters("Daniel")[2:6] == [100, 34, 30, 29]
    assert chapters("Hosea") == [9, 25, 5, 19, 15, 11, 16, 14, 17, 15, 11, 15, 15, 10]
    by_anchor = {p.anchor: p for name in ("Daniel", "Hosea") for p in vendored_docs[name].passages}
    def at(anchor):
        p = by_anchor[anchor]
        return p.reference, p.chapter_key, p.metadata.get("source_ref")
    assert at("daniel/nv/3/98") == ("Daniel 3:98–100", "daniel/3", "Daniel 4:1–3")
    assert at("daniel/nv/4/1") == ("Daniel 4:1–15", "daniel/4", "Daniel 4:4–18")
    assert at("daniel/5/13") == ("Daniel 5:13–30", "daniel/5", None)
    assert at("daniel/nv/6/1") == ("Daniel 6:1–10", "daniel/6", "Daniel 5:31–6:9")
    assert at("daniel/nv/6/11") == ("Daniel 6:11–25", "daniel/6", "Daniel 6:10–24")
    assert at("hosea/1/1") == ("Hosea 1:1–9", "hosea/1", None)
    assert at("hosea/nv/2/1") == ("Hosea 2:1–2", "hosea/2", "Hosea 1:10–11")
    assert at("hosea/nv/2/16") == ("Hosea 2:16–25", "hosea/2", "Hosea 2:14–23")
    assert at("hosea/11/8") == ("Hosea 11:8–11", "hosea/11", None)
    assert at("hosea/nv/12/1") == ("Hosea 12:1–15", "hosea/12", "Hosea 11:12–12:14")
    assert at("hosea/13/15") == ("Hosea 13:15", "hosea/13", None)
    assert at("hosea/nv/14/1") == ("Hosea 14:1", "hosea/14", "Hosea 13:16")
    assert at("hosea/nv/14/2") == ("Hosea 14:2–4", "hosea/14", "Hosea 14:1–3")
    assert by_anchor["daniel/nv/4/1"].content.startswith("I, Nebuchadnezzar, was at rest")
    assert by_anchor["daniel/nv/6/1"].content.startswith("Darius the Mede received")
    assert by_anchor["hosea/nv/2/1"].content.startswith("Yet the number of the children")
    assert by_anchor["hosea/nv/14/2"].content.startswith("Israel, return to")
    # A passage holding no moved verse keeps its anchor; one holding a moved verse has `nv`.
    for name in ("Daniel", "Hosea"):
        book = books[name]
        for p in vendored_docs[name].passages:
            moved = any(k in book.source_of for k in _held(p))
            assert ("/nv/" in p.anchor) == moved, p.anchor
            assert "/nv/" not in p.chapter_key and ("source_ref" in p.metadata) == moved


@pytest.mark.skipif(not _vendored, reason="WEB-C USFM not vendored")
def test_every_old_daniel_and_hosea_passage_has_a_redirect(vendored_docs):
    """Each row whose verses #317 renumbers redirects to the passage now holding its first
    verse; every other row of the two books is still built, with its frozen ID (D1)."""
    reg = registry.current()
    table = load_versification(os.path.join(_ROOT, "bible_versification.csv"))
    open_from = {r["old_passage_id"]: r for r in registry.open_redirects(reg)
                 if r.get("added_by") == "1.4b-2"}
    seen = set()
    for name in ("Daniel", "Hosea"):
        doc = vendored_docs[name]
        built = {p.anchor: p for p in doc.passages}
        for row in (r for r in reg.passages if r["document_id"] == doc.id):
            if row["anchor"] not in _NV_PASSAGE_MOVES:
                assert row["status"] == "redirected" or row["anchor"] in built, row["anchor"]
                assert row["passage_id"] not in open_from, row["anchor"]
                continue
            seen.add(row["anchor"])
            new_anchor, kind = _NV_PASSAGE_MOVES[row["anchor"]]
            redirect = open_from[row["passage_id"]]
            assert row["status"] == "redirected" and row["anchor"] not in built
            assert (redirect["new_anchor"], redirect["kind"]) == (new_anchor, kind)
            assert redirect["new_passage_id"] == registry.resolve_passage_id(doc.id, new_anchor)
            _, c, v = row["anchor"].split("/")
            assert table[name].moves[(int(c), int(v))] in _held(built[new_anchor])
    assert seen == set(_NV_PASSAGE_MOVES) and len(open_from) == len(_NV_PASSAGE_MOVES)


_PARAGRAPH_BOOK_TITLES = ("Tobit", "Judith", "Wisdom", "Sirach", "Baruch", "1 Maccabees",
                          "2 Maccabees")


def _held(p) -> list[tuple[int, int]]:
    import re
    chapter = int(p.chapter_key.rsplit("/", 1)[1])
    return [(chapter, int(p.unit_label))] + \
        [(chapter, int(v)) for v in re.findall(r"\{\{v:(\d+)\}\}", p.content)]


@pytest.mark.skipif(not _vendored, reason="WEB-C USFM not vendored")
def test_vendored_deutero_passage_sizes(vendored_docs):
    """Every passage of the seven books is 300 to 2,200 characters, except one holding a
    paragraph longer than that. Wisdom 15:7-19 can meet neither bound (297 characters
    after a paragraph of 2,022): Carter approved joining them as one passage of 2,329
    characters (11 Nov 2026, NEEDS-CARTER.md)."""
    from ingest.bible import PARAGRAPH_CEILING, _group_content
    approved_exceptions = {"Wisdom 15:7–19": 2329}
    books = load_usfm_directory(os.path.join(_ROOT, "sources", "bible", "eng-web-c_usfm"))
    for name in _PARAGRAPH_BOOK_TITLES:
        book = books[name]
        paragraph_of, sizes, current = {}, [], []
        for v in book.verses:
            if (v.chapter, v.verse) in book.paragraph_starts or not current \
                    or current[-1][0] != v.chapter:
                if current:
                    sizes.append(len(_group_content(current)))
                current = []
            current.append((v.chapter, v.verse, v.text))
            paragraph_of[(v.chapter, v.verse)] = len(sizes)
        sizes.append(len(_group_content(current)))
        for p in vendored_docs[name].passages:
            if p.anchor.endswith("/prologue"):
                continue
            assert p.anchor == f"{p.chapter_key}/{p.unit_label}" or "/from-" in p.anchor
            assert "pericope" not in p.metadata and p.reference.startswith(f"{name} ")
            longest = max(sizes[paragraph_of[k]] for k in _held(p))
            assert 300 <= len(p.content) <= 2200 or longest > PARAGRAPH_CEILING \
                or approved_exceptions.get(p.reference) == len(p.content), \
                (p.reference, len(p.content))
        assert len(vendored_docs[name].passages) > \
            {"Tobit": 16, "Judith": 25, "Wisdom": 25, "Sirach": 60, "Baruch": 12,
             "1 Maccabees": 47, "2 Maccabees": 37}[name]


@pytest.mark.skipif(not _vendored, reason="WEB-C USFM not vendored")
def test_every_old_deutero_passage_redirects_to_its_first_verse(vendored_docs):
    """Each chapter's first passage keeps its anchor and the ID frozen for it; every other
    row of the seven books that is not built is redirected (`split` or `merged`) to the
    passage holding its first verse. A row never published opens where its anchor says;
    a live one is checked against its live text (the next test)."""
    reg = registry.current()
    open_from = {r["old_passage_id"]: r for r in registry.open_redirects(reg)}
    for name in _PARAGRAPH_BOOK_TITLES:
        doc = vendored_docs[name]
        built = {p.anchor: p for p in doc.passages}
        rows = [r for r in reg.passages if r["document_id"] == doc.id]
        chapters = {p.chapter_key for p in doc.passages if not p.anchor.endswith("/prologue")}
        for key in chapters:
            first = next(r for r in rows if r["anchor"] == f"{key}/1")
            assert first["status"] == "active" and first["frozen_on"] == "2026-10-30", key
        for row in rows:
            if row["anchor"] in built:
                assert row["status"] == "active", row["anchor"]
                continue
            assert row["status"] == "redirected", row["anchor"]
            redirect = open_from[row["passage_id"]]
            target = built[redirect["new_anchor"]]
            if redirect.get("added_by") == "1.4c":
                assert redirect["kind"] in ("split", "merged")
                if row["frozen_on"] != "2026-10-30":
                    parts = row["anchor"].split("/")
                    c, v = (parts[3].split("-")[1:3] if len(parts) > 3 else parts[1:3])
                    assert (int(c), int(v)) in _held(target), (row["anchor"], target.anchor)


_SNAPSHOT = os.path.join(_ROOT, "releases", "snapshots", "2026-10-31", "passages.jsonl.gz")


@pytest.mark.skipif(not (_vendored and os.path.exists(_SNAPSHOT)),
                    reason="WEB-C USFM or the 31 Oct 2026 snapshot not here")
def test_live_deutero_passages_redirect_to_their_live_opening_verse(vendored_docs):
    """Every open redirect from a live passage of the seven books lands on the passage
    holding the first verse of the text users saw. A live piece (`tobit/1/1-2`) carries
    the chapter's unit_label; it opens on its first verse marker, or, opening inside a
    verse, continues the last verse of the live passage before it (Tobit 1:22)."""
    import gzip
    import json
    import re
    ids = {vendored_docs[name].id: name for name in _PARAGRAPH_BOOK_TITLES}
    live: dict[str, list[dict]] = {}
    with gzip.open(_SNAPSHOT, "rt", encoding="utf-8") as fh:
        for line in fh:
            p = json.loads(line)
            if p["document_id"] in ids:
                live.setdefault(p["document_id"], []).append(p)
    opening: dict[str, tuple[int, int]] = {}
    for passages in live.values():
        last = None
        for p in sorted(passages, key=lambda p: p["position"]):
            chapter = int(p["chapter_key"].rsplit("/", 1)[1])
            markers = [int(n) for n in re.findall(r"\{\{v:(\d+)\}\}", p["content"])]
            piece = "-" in p["anchor"].rsplit("/", 1)[1] and not p["anchor"].endswith("-1")
            if p["content"].startswith("{{v:"):
                first = markers[0]
            elif piece:
                first = last[1]
            else:
                first = int(p["unit_label"])
            opening[p["id"]] = (chapter, first)
            last = (chapter, (markers or [first])[-1])
    checked = 0
    for r in registry.open_redirects(registry.current()):
        if r["document_id"] in ids and r["old_passage_id"] in opening:
            target = next(p for p in vendored_docs[ids[r["document_id"]]].passages
                          if p.anchor == r["new_anchor"])
            assert opening[r["old_passage_id"]] in _held(target), (r["old_anchor"], target.anchor)
            checked += 1
    assert checked == 73
