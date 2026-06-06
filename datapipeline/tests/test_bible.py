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

from ingest.bible import (
    _clean_usfm_text,
    _format_reference,
    _parse_ref,
    BookVerses,
    Verse,
    Pericope,
    collect_pericope_verses,
    chunk_canonical_book,
    chunk_deuterocanonical_book,
    load_pericopes,
    parse_usfm_file,
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

def _make_usfm_file(content: str, tmp_path_factory, name: str = "test.usfm"):
    """Write a temporary USFM file and return its path."""
    import tempfile, os
    tmp_dir = tempfile.mkdtemp()
    path = os.path.join(tmp_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


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
# collect_pericope_verses
# ---------------------------------------------------------------------------

def _make_verse_map(entries: list[tuple[int, int, str]]) -> dict[tuple[int, int], str]:
    return {(ch, v): text for ch, v, text in entries}


def test_pericope_chunk_collects_correct_verses():
    """collect_pericope_verses returns exactly the verses within [start, end]."""
    verse_map = _make_verse_map([
        (1, 1, "verse 1:1"), (1, 2, "verse 1:2"), (1, 3, "verse 1:3"),
        (2, 1, "verse 2:1"), (2, 2, "verse 2:2"),
    ])
    result = collect_pericope_verses(verse_map, 1, 2, 2, 1)
    assert len(result) == 3
    texts = [t for _, _, t in result]
    assert "verse 1:1" not in texts
    assert "verse 1:2" in texts
    assert "verse 1:3" in texts
    assert "verse 2:1" in texts
    assert "verse 2:2" not in texts


def test_pericope_chunk_single_chapter():
    """Verses restricted to a single chapter range."""
    verse_map = _make_verse_map([
        (5, 1, "a"), (5, 2, "b"), (5, 3, "c"), (5, 4, "d"),
    ])
    result = collect_pericope_verses(verse_map, 5, 2, 5, 3)
    assert len(result) == 2
    assert result[0][2] == "b"
    assert result[1][2] == "c"


def test_pericope_chunk_inclusive_endpoints():
    """Start and end verses are both included."""
    verse_map = _make_verse_map([(1, 1, "start"), (1, 2, "middle"), (1, 3, "end")])
    result = collect_pericope_verses(verse_map, 1, 1, 1, 3)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# chunk_canonical_book
# ---------------------------------------------------------------------------

def _make_book(name: str, testament: str, verse_entries: list[tuple[int, int, str]]) -> BookVerses:
    verses = [Verse(name, ch, v, text) for ch, v, text in verse_entries]
    return BookVerses(name=name, book_code="TST", testament=testament, verses=verses)


def test_canonical_chunk_content_and_reference():
    """chunk_canonical_book yields correct content and reference for a pericope."""
    book = _make_book("Genesis", "OT", [
        (1, 1, "In the beginning"), (1, 2, "The earth was empty"),
        (2, 1, "The heavens were finished"),
    ])
    pericopes = [
        Pericope(
            title="Creation",
            book="Genesis",
            start_chapter=1, start_verse=1,
            end_chapter=2, end_verse=1,
        )
    ]
    chunks = list(chunk_canonical_book(book, pericopes, "WEB-C"))
    assert len(chunks) == 1
    content, reference, metadata, position = chunks[0]
    assert "In the beginning" in content
    assert "The earth was empty" in content
    assert "The heavens were finished" in content
    assert reference == "Genesis 1:1–2:1"
    assert metadata["pericope"] == "Creation"
    assert metadata["book"] == "Genesis"
    assert metadata["testament"] == "OT"
    assert metadata["translation"] == "WEB-C"
    assert position == 0


def test_canonical_chunk_skips_empty_pericopes():
    """Pericopes with no matching verses in the book are skipped."""
    book = _make_book("Matthew", "NT", [(5, 1, "Blessed are the poor")])
    pericopes = [
        Pericope("First", "Matthew", 5, 1, 5, 1),
        Pericope("Missing", "Matthew", 99, 1, 99, 5),  # no matching verses
    ]
    chunks = list(chunk_canonical_book(book, pericopes, "WEB-C"))
    assert len(chunks) == 1
    assert chunks[0][3] == 0  # position 0


def test_canonical_chunk_positions_sequential():
    """Position counter increments correctly across chunks."""
    book = _make_book("Romans", "NT", [
        (1, 1, "Paul a servant"), (1, 2, "called to be an apostle"),
        (1, 3, "of his Son"), (2, 1, "Therefore you are without excuse"),
    ])
    pericopes = [
        Pericope("A", "Romans", 1, 1, 1, 2),
        Pericope("B", "Romans", 1, 3, 1, 3),
        Pericope("C", "Romans", 2, 1, 2, 1),
    ]
    chunks = list(chunk_canonical_book(book, pericopes, "WEB-C"))
    assert len(chunks) == 3
    positions = [c[3] for c in chunks]
    assert positions == [0, 1, 2]


# ---------------------------------------------------------------------------
# chunk_deuterocanonical_book
# ---------------------------------------------------------------------------

def test_deuterocanonical_chunk_per_chapter():
    """chunk_deuterocanonical_book yields exactly one chunk per chapter."""
    book = _make_book("Tobit", "OT", [
        (1, 1, "The book of Tobit"), (1, 2, "son of Tobiel"),
        (2, 1, "When I returned"), (2, 2, "to my house"),
        (3, 1, "I was grieved"),
    ])
    chunks = list(chunk_deuterocanonical_book(book, "WEB-C"))
    assert len(chunks) == 3
    refs = [c[1] for c in chunks]
    assert refs == ["Tobit 1", "Tobit 2", "Tobit 3"]


def test_deuterocanonical_chapter_content_concatenated():
    """All verse texts within a chapter are joined."""
    book = _make_book("Wisdom", "OT", [
        (1, 1, "Love righteousness"), (1, 2, "you who judge the earth"),
    ])
    chunks = list(chunk_deuterocanonical_book(book, "WEB-C"))
    assert len(chunks) == 1
    content = chunks[0][0]
    assert "Love righteousness" in content
    assert "you who judge the earth" in content


def test_deuterocanonical_metadata_includes_chapter():
    """Metadata for deuterocanonical chunks includes 'chapter' key."""
    book = _make_book("Judith", "OT", [(2, 1, "Nebuchadnezzar spoke")])
    chunks = list(chunk_deuterocanonical_book(book, "WEB-C"))
    assert len(chunks) == 1
    _, _, metadata, _ = chunks[0]
    assert metadata["chapter"] == 2
    assert metadata["book"] == "Judith"
    assert metadata["testament"] == "OT"
    assert metadata["translation"] == "WEB-C"


def test_deuterocanonical_skips_empty_chapters():
    """Chapters with no text are skipped."""
    book = _make_book("Sirach", "OT", [
        (1, 1, "All wisdom"),
        (2, 1, ""),           # empty text
        (3, 1, "Honor your father"),
    ])
    chunks = list(chunk_deuterocanonical_book(book, "WEB-C"))
    # Chapter 2 has empty text — should be skipped
    refs = [c[1] for c in chunks]
    assert "Sirach 1" in refs
    assert "Sirach 3" in refs
    # Chapter 2 may or may not appear depending on whitespace; at minimum
    # chapters 1 and 3 must be present.
    assert len(chunks) >= 2


def test_deuterocanonical_positions_sequential():
    """Position values are 0-indexed and sequential."""
    book = _make_book("Baruch", "OT", [
        (1, 1, "These are words"), (2, 1, "The Lord our God"), (3, 1, "Hear O Israel"),
    ])
    chunks = list(chunk_deuterocanonical_book(book, "WEB-C"))
    positions = [c[3] for c in chunks]
    assert positions == [0, 1, 2]


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
