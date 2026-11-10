"""Tests for the WEB-C USFM Bible ingestion pipeline.

All tests are fully self-contained — no filesystem or database access.
"""
import sys
import os

# Set required env vars before importing ingest.bible, which imports config at module level.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import textwrap
import unittest.mock as mock

import pytest

import registry
from ingest.bible import (
    _clean_usfm_text,
    _format_reference,
    _parse_ref,
    BookVerses,
    ExtraPericope,
    Verse,
    Pericope,
    build_documents,
    check_complete,
    group_verses,
    load_pericopes,
    parse_usfm_file,
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


def _world(tmp_path, books: dict[str, str], pericopes: list[tuple], extras: str = ""):
    """A USFM directory, a KJV pericope file and an extra-pericope CSV under tmp_path.
    `books` maps a file name to its USFM text; `pericopes` holds (title, start, end)."""
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
    return dict(usfm_dir=str(usfm), pericope_path=str(kjv), extra_path=str(csv_path))


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
    assert (chapter.anchor, chapter.reference, chapter.position) == ("sirach/1/1", "Sirach 1", 1)


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
    assert [daniel[c] for c in range(1, 15)] == [21, 49, 97, 37, 31, 28, 28, 27, 27, 21, 45,
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
    assert at("Romans", "romans/14/24").reference == "Romans 14:24–26"
    assert at("Numbers", "numbers/16/28").reference == "Numbers 16:28–40"
    assert at("Mark", "mark/2/23").reference == "Mark 2:23–28"
    assert at("Sirach", "sirach/prologue").content.startswith("WHEREAS many and great things")
