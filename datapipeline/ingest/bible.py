"""WEB-C (World English Bible — Catholic) ingestion via USFM files.

Chunking strategy (1.4a): the USFM verse list drives the build, so every verse with
text lands in exactly one passage.
  - A verse belongs to the first row of `bible_extra_pericopes.csv` that holds it, else
    to the KJV pericope (PericopeGroupedKJVVerses.json) that holds it and starts
    latest, else to the group of the verse before it in the same chapter.
  - Passages never cross a chapter; a group longer than one card is split (1.10c).
  - Books with no pericopes (the deuterocanonical books): one passage per chapter.
  - A Psalm title (\\d) opens the verse it precedes; Sirach's prologue is its own
    passage, `sirach/prologue`.

Numbering (1.4b): WEB-C follows the KJV's verse numbers. `bible_versification.csv` moves
the verses where the Nova Vulgata, which the Catechism and the Lectionary cite, numbers
them differently (Joel, Malachi and Jonah; Romans's doxology to 16:25-27). It is applied
when the USFM is loaded, so grouping, references and chapter keys all use the Nova
Vulgata's numbers; passage metadata `source_ref` keeps WEB-C's. A renumbered passage's
anchor carries the segment `nv` (`joel/nv/3/1`), so no anchor live under WEB-C's numbers
comes to name different text (D1).

USFM format notes:
  - \\id CODE ...       — book identifier (e.g. MAT)
  - \\c N               — chapter N starts
  - \\v N text          — verse N text (may wrap to continuation lines)
  - \\d text            — a Psalm title, before the verse it precedes
  - \\w word|strong="H1234"\\w*  — Strong's markup (word extracted, rest stripped)
  - \\f ... \\f*        — footnote (stripped)
  - \\x ... \\x*        — cross-reference (stripped)
  - \\wj ... \\wj*      — words of Jesus (stripped, content kept)
  - Other backslash markers (\\p, \\q1, \\q2, \\sp, etc.) are stripped.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterator

# Add datapipeline root to path so shared builder modules are importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings  # noqa: E402
from itertools import groupby  # noqa: E402
from identity import anchor as make_anchor, slugify  # noqa: E402
from model import Document, Passage  # noqa: E402
from normalize.text import clean_text  # noqa: E402
from ingest.pieces import Segment, name_pieces, pack_units, piece_reference  # noqa: E402
from registry import ANCHOR_SCHEME, anchor_slug, resolve_document_id  # noqa: E402

# ---------------------------------------------------------------------------
# Canonical book name → testament
# Full 73-book Catholic canon (deuterocanonicals included).
# ---------------------------------------------------------------------------
_BOOK_TESTAMENT: dict[str, str] = {
    # OT protocanonical
    "Genesis": "OT", "Exodus": "OT", "Leviticus": "OT", "Numbers": "OT",
    "Deuteronomy": "OT", "Joshua": "OT", "Judges": "OT", "Ruth": "OT",
    "1 Samuel": "OT", "2 Samuel": "OT", "1 Kings": "OT", "2 Kings": "OT",
    "1 Chronicles": "OT", "2 Chronicles": "OT", "Ezra": "OT", "Nehemiah": "OT",
    "Esther": "OT", "Job": "OT", "Psalms": "OT", "Proverbs": "OT",
    "Ecclesiastes": "OT", "Song of Songs": "OT", "Isaiah": "OT",
    "Jeremiah": "OT", "Lamentations": "OT", "Ezekiel": "OT", "Daniel": "OT",
    "Hosea": "OT", "Joel": "OT", "Amos": "OT", "Obadiah": "OT",
    "Jonah": "OT", "Micah": "OT", "Nahum": "OT", "Habakkuk": "OT",
    "Zephaniah": "OT", "Haggai": "OT", "Zechariah": "OT", "Malachi": "OT",
    # OT deuterocanonical
    "Tobit": "OT", "Judith": "OT", "1 Maccabees": "OT", "2 Maccabees": "OT",
    "Wisdom": "OT", "Sirach": "OT", "Baruch": "OT",
    # NT
    "Matthew": "NT", "Mark": "NT", "Luke": "NT", "John": "NT", "Acts": "NT",
    "Romans": "NT", "1 Corinthians": "NT", "2 Corinthians": "NT",
    "Galatians": "NT", "Ephesians": "NT", "Philippians": "NT",
    "Colossians": "NT", "1 Thessalonians": "NT", "2 Thessalonians": "NT",
    "1 Timothy": "NT", "2 Timothy": "NT", "Titus": "NT", "Philemon": "NT",
    "Hebrews": "NT", "James": "NT", "1 Peter": "NT", "2 Peter": "NT",
    "1 John": "NT", "2 John": "NT", "3 John": "NT", "Jude": "NT",
    "Revelation": "NT",
}

# ---------------------------------------------------------------------------
# USFM book code → canonical book name
# Covers all 73 books present in the WEB-C USFM collection.
# ---------------------------------------------------------------------------
_USFM_CODE_TO_BOOK: dict[str, str] = {
    "GEN": "Genesis", "EXO": "Exodus", "LEV": "Leviticus", "NUM": "Numbers",
    "DEU": "Deuteronomy", "JOS": "Joshua", "JDG": "Judges", "RUT": "Ruth",
    "1SA": "1 Samuel", "2SA": "2 Samuel", "1KI": "1 Kings", "2KI": "2 Kings",
    "1CH": "1 Chronicles", "2CH": "2 Chronicles", "EZR": "Ezra", "NEH": "Nehemiah",
    # WEB-C uses ESG (Greek Esther) which includes deuterocanonical additions;
    # we map it to canonical "Esther" for document title purposes.
    "ESG": "Esther",
    "JOB": "Job", "PSA": "Psalms", "PRO": "Proverbs", "ECC": "Ecclesiastes",
    "SNG": "Song of Songs",
    "ISA": "Isaiah", "JER": "Jeremiah", "LAM": "Lamentations",
    "EZK": "Ezekiel",
    # WEB-C uses DAG (Daniel with Greek additions); map to canonical "Daniel".
    "DAG": "Daniel",
    "HOS": "Hosea", "JOL": "Joel", "AMO": "Amos", "OBA": "Obadiah",
    "JON": "Jonah", "MIC": "Micah", "NAM": "Nahum", "HAB": "Habakkuk",
    "ZEP": "Zephaniah", "HAG": "Haggai", "ZEC": "Zechariah", "MAL": "Malachi",
    # Deuterocanonical
    "TOB": "Tobit", "JDT": "Judith", "1MA": "1 Maccabees", "2MA": "2 Maccabees",
    "WIS": "Wisdom", "SIR": "Sirach", "BAR": "Baruch",
    # NT
    "MAT": "Matthew", "MRK": "Mark", "LUK": "Luke", "JHN": "John",
    "ACT": "Acts", "ROM": "Romans", "1CO": "1 Corinthians", "2CO": "2 Corinthians",
    "GAL": "Galatians", "EPH": "Ephesians", "PHP": "Philippians",
    "COL": "Colossians", "1TH": "1 Thessalonians", "2TH": "2 Thessalonians",
    "1TI": "1 Timothy", "2TI": "2 Timothy", "TIT": "Titus", "PHM": "Philemon",
    "HEB": "Hebrews", "JAS": "James", "1PE": "1 Peter", "2PE": "2 Peter",
    "1JN": "1 John", "2JN": "2 John", "3JN": "3 John", "JUD": "Jude",
    "REV": "Revelation",
}

# Book titles that differ from the KJV pericope file's book names.
_PERICOPE_BOOK: dict[str, str] = {"Song of Songs": "Song of Solomon"}

# Default source paths (relative to the datapipeline root directory).
_DEFAULT_USFM_SUBDIR = os.path.join("sources", "bible", "eng-web-c_usfm")
_DEFAULT_PERICOPE_PATH = os.path.join("sources", "bible", "PericopeGroupedKJVVerses.json")
# Tracked, not vendored: WEB-C-native groups the KJV file lacks or misnumbers (1.4a).
_EXTRA_PERICOPE_PATH = "bible_extra_pericopes.csv"
# Tracked: verses WEB-C numbers differently from the Nova Vulgata (1.4b).
_VERSIFICATION_PATH = "bible_versification.csv"
# The anchor segment of a passage numbered by the Nova Vulgata where WEB-C differs.
NV_SEGMENT = "nv"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Verse:
    book: str           # canonical name e.g. "Genesis"
    chapter: int
    verse: int
    text: str


@dataclass
class BookVerses:
    name: str               # canonical book name
    book_code: str          # USFM code e.g. "GEN"
    testament: str          # "OT" | "NT"
    verses: list[Verse] = field(default_factory=list)
    usfm_path: str = ""     # absolute path to source .usfm file
    # A Psalm title (\\d) by the verse it precedes: Psalm 119's letter headings too.
    titles: dict[tuple[int, int], str] = field(default_factory=dict)
    prologue: str = ""      # Sirach's prologue (\\ip after \\is1 ... Prologue)
    # Renumbering (1.4b): each moved verse's WEB-C (chapter, verse) by its new one, and
    # the book's table entry; None for a book `bible_versification.csv` does not name.
    source_of: dict[tuple[int, int], tuple[int, int]] = field(default_factory=dict)
    versification: "BookVersification | None" = None


# ---------------------------------------------------------------------------
# USFM parsing
# ---------------------------------------------------------------------------

_FOOTNOTE_RE = re.compile(r"\\f\s.*?\\f\*", re.DOTALL)
_XREF_RE = re.compile(r"\\x\s.*?\\x\*", re.DOTALL)
# Strong's markup comes in two forms:
#   \w  word|strong="H1234"\w*   (regular)
#   \+w word|strong="G1234"\+w*  (nested, used inside \wj ... \wj*)
_STRONGS_RE = re.compile(r"\\\+?w\s+([^|\\]+?)\s*\|[^*\\]*\\\+?w\*")
_MARKER_RE = re.compile(r"\\[a-zA-Z0-9*+]+\s*")
_WS_RE = re.compile(r"\s+")


def _clean_usfm_text(raw: str) -> str:
    """Strip all USFM markup from a raw line fragment, returning plain text."""
    # Remove footnotes and cross-references (including their content).
    text = _FOOTNOTE_RE.sub("", raw)
    text = _XREF_RE.sub("", text)
    # Expand Strong's markup to just the word.
    text = _STRONGS_RE.sub(r"\1", text)
    # Strip all remaining backslash markers.
    text = _MARKER_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def parse_usfm_file(path: str) -> dict[tuple[int, int], str]:
    """Parse one USFM file and return a dict of {(chapter, verse): cleaned_text}.

    Multi-line verses are joined with a single space.
    Lines that carry no verse data (\\p, \\q1, chapter markers, etc.) are ignored
    unless they are continuation lines for the current verse.
    """
    verses: dict[tuple[int, int], str] = {}
    current_chapter: int = 0
    current_verse: int | None = None

    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n\r")

            # Chapter marker: \c N
            c_match = re.match(r"^\\c\s+(\d+)", line)
            if c_match:
                current_chapter = int(c_match.group(1))
                current_verse = None
                continue

            # Verse marker: \v N text...
            v_match = re.match(r"^\\v\s+(\d+)\s*(.*)", line)
            if v_match and current_chapter > 0:
                current_verse = int(v_match.group(1))
                rest = v_match.group(2)
                text = _clean_usfm_text(rest)
                key = (current_chapter, current_verse)
                verses[key] = text
                continue

            # Continuation line for current verse (non-empty, not a new marker block).
            # Lines starting with a backslash marker that introduce structure (\\p, \\q*)
            # may still carry text after the marker tag — we only skip if they produce
            # no text at all after cleaning.
            if current_verse is not None and current_chapter > 0:
                # Skip pure structural markers with no text payload.
                # A line is continuation if it's not a new \\c / \\v / \\id header.
                # A numbered heading (\\s1, \\ms1) is structural too: WEB-C's
                # "THE SONG OF THE THREE HOLY CHILDREN" followed Daniel 3:23 (1.4a).
                if re.match(r"^\\(id|ide|h|toc|mt|imt|ms\d*|mr|s\d*|sr|r|d|sp|b|li|lim|cls)\b",
                            line):
                    # These are always structural — reset verse context.
                    current_verse = None
                    continue
                cleaned = _clean_usfm_text(line)
                if cleaned:
                    key = (current_chapter, current_verse)
                    if key in verses:
                        verses[key] = verses[key] + " " + cleaned
                    else:
                        verses[key] = cleaned

    return verses


def parse_usfm_titles(path: str) -> dict[tuple[int, int], str]:
    """Each \\d line's cleaned text, keyed by the (chapter, verse) of the next verse."""
    titles: dict[tuple[int, int], str] = {}
    chapter, pending = 0, []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if m := re.match(r"^\\c\s+(\d+)", line):
                chapter = int(m.group(1))
            elif re.match(r"^\\d\b", line):
                pending.append(_clean_usfm_text(line[2:]))
            elif (m := re.match(r"^\\v\s+(\d+)", line)) and pending:
                titles[(chapter, int(m.group(1)))] = " ".join(t for t in pending if t)
                pending = []
    if pending:
        raise ValueError(f"{path}: a \\d title with no verse after it")
    return titles


def parse_usfm_prologue(path: str) -> str:
    """The \\ip paragraphs after a \\is1 heading naming the Prologue (Sirach), joined.
    Other \\ip lines are WEB-C's own introductions and are not Scripture."""
    out, inside = [], False
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("\\is1") and "Prologue" in line:
                inside = True
            elif inside and line.startswith("\\ip"):
                out.append(_clean_usfm_text(line[3:]))
            elif inside and line.strip():
                break
    return " ".join(t for t in out if t)


def _book_code_from_usfm(path: str) -> str | None:
    """Read the \\id line from a USFM file and return the 3-letter book code."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = re.match(r"^\\id\s+([A-Z0-9]{2,3})", line)
            if m:
                return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Versification (1.4b)
# ---------------------------------------------------------------------------

_VERSIFICATION_SCOPES = ("book", "passage")


@dataclass
class BookVersification:
    """One book's rows of `bible_versification.csv`. `moves` maps each moved verse's
    WEB-C (chapter, verse) to the Nova Vulgata's. `scope` says which passages carry the
    `nv` anchor segment: `book`, every passage of the book, so it has one scheme (Joel,
    Malachi, Jonah); `passage`, only a passage holding a moved verse (Romans's doxology,
    where nothing else moves)."""
    book: str
    scope: str
    moves: dict[tuple[int, int], tuple[int, int]] = field(default_factory=dict)


def _verse_range(text: str) -> list[tuple[int, int]]:
    """'2:28-2:32' as its verses. A range stays inside one chapter."""
    start, end = text.split("-")
    (sc, sv), (ec, ev) = ((int(x) for x in part.split(":")) for part in (start, end))
    if sc != ec or ev < sv:
        raise ValueError(f"versification range {text!r} must run forward inside one chapter")
    return [(sc, v) for v in range(sv, ev + 1)]


def load_versification(path: str) -> dict[str, BookVersification]:
    """Read and check `bible_versification.csv`: each row moves a run of verses as a block,
    so its source and target ranges have the same length; no verse moves twice, no two
    verses land on one number, and a book's rows agree on their scope."""
    books: dict[str, BookVersification] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            source, target = _verse_range(row["source"]), _verse_range(row["target"])
            if len(source) != len(target):
                raise ValueError(f"{row['book']} {row['source']}: the target range "
                                 f"{row['target']} has another length")
            if row["scope"] not in _VERSIFICATION_SCOPES:
                raise ValueError(f"{row['book']} {row['source']}: scope {row['scope']!r}")
            if not row.get("authority"):
                raise ValueError(f"{row['book']} {row['source']}: no authority")
            book = books.setdefault(row["book"], BookVersification(row["book"], row["scope"]))
            if book.scope != row["scope"]:
                raise ValueError(f"{row['book']}: rows disagree on scope")
            for s, t in zip(source, target):
                if s in book.moves:
                    raise ValueError(f"{row['book']} {s[0]}:{s[1]} moves twice")
                book.moves[s] = t
    for book in books.values():
        landed = Counter(book.moves.values())
        twice = sorted(t for t, n in landed.items() if n > 1)
        if twice:
            raise ValueError(f"{book.book}: two verses land on {twice}")
    return books


def moves_by_code(path: str | None = None) -> dict[str, dict[tuple[int, int], tuple[int, int]]]:
    """The tracked table's moves keyed by USFM book code (`JOL`), for checks that read
    the USFM's own verse numbers (0.1a)."""
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                _VERSIFICATION_PATH)
    by_name = {name: code for code, name in _USFM_CODE_TO_BOOK.items()}
    return {by_name[name]: t.moves for name, t in load_versification(path).items()}


def renumber(name: str, verse_map: dict[tuple[int, int], str],
             titles: dict[tuple[int, int], str], table: BookVersification
             ) -> tuple[dict[tuple[int, int], str], dict[tuple[int, int], str],
                        dict[tuple[int, int], tuple[int, int]]]:
    """The book's verses and titles under the table's numbers, and each moved verse's
    WEB-C number by its new one. A moved verse may land on a number the source leaves
    empty (WEB-C's bare Romans 16:25 marker), never on a verse with text that stays."""
    missing = sorted(set(table.moves) - set(verse_map))
    if missing:
        raise ValueError(f"{name}: the versification table moves verses the source "
                         f"lacks: {missing}")
    out = {k: v for k, v in verse_map.items() if k not in table.moves}
    source_of: dict[tuple[int, int], tuple[int, int]] = {}
    for s, t in table.moves.items():
        if out.get(t, "").strip():
            raise ValueError(f"{name}: {s[0]}:{s[1]} would land on {t[0]}:{t[1]}, "
                             "which has text")
        out[t] = verse_map[s]
        source_of[t] = s
    moved_titles = {table.moves.get(k, k): v for k, v in titles.items()}
    return out, moved_titles, source_of


def load_usfm_directory(usfm_dir: str, versification: dict[str, BookVersification] | None = None
                        ) -> dict[str, BookVerses]:
    """Load all USFM files in a directory.

    Returns a dict of {canonical_book_name: BookVerses}.
    Files that do not map to a known canonical name are skipped. A book `versification`
    names is renumbered by it (1.4b); None reads the tracked table.
    """
    if versification is None:
        versification = load_versification(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         _VERSIFICATION_PATH))
    unknown = sorted(set(versification) - set(_USFM_CODE_TO_BOOK.values()))
    if unknown:
        raise ValueError(f"versification table names unknown books: {unknown}")
    books: dict[str, BookVerses] = {}
    for fname in sorted(os.listdir(usfm_dir)):
        if not fname.endswith(".usfm"):
            continue
        path = os.path.join(usfm_dir, fname)
        code = _book_code_from_usfm(path)
        if code is None:
            continue
        canonical = _USFM_CODE_TO_BOOK.get(code)
        if canonical is None:
            continue
        testament = _BOOK_TESTAMENT.get(canonical, "OT")
        verse_map = parse_usfm_file(path)
        titles = parse_usfm_titles(path)
        table = versification.get(canonical)
        source_of: dict[tuple[int, int], tuple[int, int]] = {}
        if table is not None:
            verse_map, titles, source_of = renumber(canonical, verse_map, titles, table)
        verse_list = [
            Verse(canonical, ch, v, text)
            for (ch, v), text in sorted(verse_map.items())
        ]
        books[canonical] = BookVerses(
            name=canonical,
            book_code=code,
            testament=testament,
            verses=verse_list,
            usfm_path=path,
            titles=titles,
            prologue=parse_usfm_prologue(path),
            source_of=source_of,
            versification=table,
        )
    return books


# ---------------------------------------------------------------------------
# Pericope loading
# ---------------------------------------------------------------------------

@dataclass
class Pericope:
    title: str
    book: str       # canonical book name extracted from "Reference Start"
    start_chapter: int
    start_verse: int
    end_chapter: int
    end_verse: int


def _parse_ref(ref: str) -> tuple[str, int, int]:
    """Parse 'BookName Chapter:Verse' into (book_name, chapter, verse).

    Handles multi-word book names like '1 Corinthians 13:1'.
    """
    # The reference ends with 'N:N' — split on the last space to separate book + cv.
    parts = ref.rsplit(" ", 1)
    if len(parts) != 2:
        raise ValueError(f"Cannot parse reference: {ref!r}")
    book = parts[0].strip()
    cv = parts[1].strip()
    if ":" not in cv:
        raise ValueError(f"No chapter:verse in reference: {ref!r}")
    ch_str, v_str = cv.split(":", 1)
    return book, int(ch_str), int(v_str)


def load_pericopes(pericope_path: str) -> dict[str, list[Pericope]]:
    """Load pericope boundaries and group by canonical book name.

    Returns {canonical_book_name: [Pericope, ...]}.
    """
    with open(pericope_path, encoding="utf-8") as fh:
        raw = json.load(fh)

    grouped: dict[str, list[Pericope]] = {}
    for item in raw:
        book, sc, sv = _parse_ref(item["Reference Start"])
        _, ec, ev = _parse_ref(item["Reference End"])
        p = Pericope(
            title=item["Pericope"],
            book=book,
            start_chapter=sc,
            start_verse=sv,
            end_chapter=ec,
            end_verse=ev,
        )
        grouped.setdefault(book, []).append(p)
    return grouped


# ---------------------------------------------------------------------------
# Reference formatting
# ---------------------------------------------------------------------------

def _format_reference(book: str, sc: int, sv: int, ec: int, ev: int) -> str:
    """Build a human-readable reference string using an en-dash for ranges.

    Single verse:      'Matthew 5:3'
    Same chapter:      'Matthew 5:1–4'
    Cross-chapter:     'Genesis 1:1–2:3'
    """
    if sc == ec and sv == ev:
        return f"{book} {sc}:{sv}"
    if sc == ec:
        return f"{book} {sc}:{sv}–{ev}"
    return f"{book} {sc}:{sv}–{ec}:{ev}"


# ---------------------------------------------------------------------------
# Grouping verses into pericopes (1.4a)
# ---------------------------------------------------------------------------

@dataclass
class ExtraPericope:
    """A row of `bible_extra_pericopes.csv`: a group the KJV file lacks (Susanna, the
    Esther additions) or misnumbers (Daniel 3). A row wins over the KJV pericopes for
    every verse it holds, and bounds its own group. Rows use the published numbers: WEB-C's,
    or the Nova Vulgata's where `bible_versification.csv` moves a verse (Jonah 2:1-11)."""
    book: str
    start_chapter: int
    start_verse: int
    end_chapter: int
    end_verse: int
    title: str
    # Whole-addition ranges in other numberings (Esther only; R3, Decision log).
    refs: dict[str, str] = field(default_factory=dict)


_REF_COLUMNS = ("nv_ref", "lxx_ref", "nab_ref")


def load_extra_pericopes(path: str) -> dict[str, list[ExtraPericope]]:
    grouped: dict[str, list[ExtraPericope]] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            sc, sv = (int(x) for x in row["start"].split(":"))
            ec, ev = (int(x) for x in row["end"].split(":"))
            grouped.setdefault(row["book"], []).append(ExtraPericope(
                row["book"], sc, sv, ec, ev, row["title"],
                {k: row[k] for k in _REF_COLUMNS if row.get(k)}))
    return grouped


def renumber_pericope(p: Pericope, table: BookVersification | None) -> Pericope:
    """A KJV pericope with its ends moved by the versification table. The KJV file numbers
    verses as WEB-C does wherever the table moves one (Joel, Malachi, Jonah), except that it
    has no verse at WEB-C's Romans 14:24: its "Doxology" already sits at 16:25-27, which no
    row moves. A pericope moved across a chapter is cut there like any other."""
    if table is None:
        return p
    sc, sv = table.moves.get((p.start_chapter, p.start_verse), (p.start_chapter, p.start_verse))
    ec, ev = table.moves.get((p.end_chapter, p.end_verse), (p.end_chapter, p.end_verse))
    return Pericope(p.title, p.book, sc, sv, ec, ev)


def _holds(p, chapter: int, verse: int) -> bool:
    return (p.start_chapter, p.start_verse) <= (chapter, verse) <= (p.end_chapter, p.end_verse)


@dataclass
class VerseGroup:
    """Consecutive verses of one chapter that make one passage (before splitting)."""
    chapter: int
    verses: list[tuple[int, int, str]]
    title: str | None
    refs: dict[str, str] = field(default_factory=dict)


def group_verses(verses: list[Verse], pericopes: list[Pericope],
                 extras: list[ExtraPericope]) -> list[VerseGroup]:
    """Every verse in order, each in exactly one group. A verse belongs to the first
    extra row that holds it; else to the KJV pericope that holds it and starts latest,
    so an overlap goes to the pericope that opens on it (Numbers 16:28-37); else to the
    group of the verse before it in the same chapter, the story the KJV file cut short
    (Mark 2:28). Carter, 10 Nov 2026."""
    groups: list[VerseGroup] = []
    last_key = None
    for v in verses:
        extra = next((i for i, e in enumerate(extras) if _holds(e, v.chapter, v.verse)), None)
        if extra is not None:
            key = ("extra", extra)
        else:
            held = [i for i, p in enumerate(pericopes) if _holds(p, v.chapter, v.verse)]
            if held:
                latest = max(held, key=lambda i: ((pericopes[i].start_chapter,
                                                   pericopes[i].start_verse), -i))
                key = ("kjv", latest)
            elif groups and groups[-1].chapter == v.chapter:
                key = last_key
            else:
                key = ("none", v.chapter, v.verse)
        if key != last_key or groups[-1].chapter != v.chapter:
            kind, idx = key[0], key[1]
            source = extras[idx] if kind == "extra" else pericopes[idx] if kind == "kjv" else None
            groups.append(VerseGroup(v.chapter, [], source.title if source else None,
                                     dict(source.refs) if kind == "extra" else {}))
        groups[-1].verses.append((v.chapter, v.verse, v.text))
        last_key = key
    return groups


# ---------------------------------------------------------------------------
# Canonical passage builder — passage = pericope clamped to chapter
# ---------------------------------------------------------------------------

def _join_with_verse_markers(verse_tuples: list[tuple[int, int, str]]) -> str:
    """Join verse texts, prepending {{v:N}} markers for all verses after the first.

    The first verse relies on the passage's unit_label field instead.
    """
    parts = []
    for i, (_ch, v, text) in enumerate(verse_tuples):
        if i == 0:
            parts.append(text)
        else:
            parts.append("{{v:%d}} %s" % (v, text))
    return " ".join(parts)


def slugify_book(name: str) -> str:
    return slugify(name)


def _verse_segments(verse_tuples: list[tuple[int, int, str]]) -> list[Segment]:
    """Each verse as `_join_with_verse_markers` writes it, named `<chapter>-<verse>`."""
    return [Segment(f"{ch}-{v}", text if i == 0 else "{{v:%d}} %s" % (v, text))
            for i, (ch, v, text) in enumerate(verse_tuples)]


_MARKER = re.compile(r"\{\{v:(\d+)\}\}")
_LEADING_MARKER = re.compile(r"^\{\{v:\d+\}\}\s*")


def _verse_units(content: str, chapter: int, first_v: int) -> list[tuple[str, str]]:
    """`content` cut before each verse marker: (`chapter:verse`, slice), each slice keeping
    the space after it, so the slices join back to `content`."""
    cuts = [(first_v, 0)] + [(int(m.group(1)), m.start()) for m in _MARKER.finditer(content)]
    ends = [at for _, at in cuts[1:]] + [len(content)]
    return [(f"{chapter}:{v}", content[at:end]) for (v, at), end in zip(cuts, ends)]


def _last_with_text(units: list[tuple[str, str]], piece) -> int:
    """The last verse of `piece` with text: the source has empty verses (Sirach 23:28 is a
    bare marker), which a reference does not cite."""
    k = piece.last
    while k > piece.first and not _LEADING_MARKER.sub("", units[k][1]).strip():
        k -= 1
    return k


def _pieces(book: str, chapter: int, verses: list[tuple[int, int, str]], content: str,
            base_anchor: str, whole_reference: str | None = None
            ) -> list[tuple[str, str, str, str, tuple, tuple[str, str]]]:
    """(content, reference, unit_label, anchor, source_units, (first, last)) for each piece of one
    pericope part or chapter (1.10c). Pieces hold whole verses and cite the verses whose
    text they hold; a later piece opens on its first verse, which its `unit_label`
    carries in place of a marker. Only a verse longer than one card is cut (Esther 8:13,
    Greek addition E, 1.4a); pieces that would then cite the same verses add "(part j of
    m)" among themselves. `whole_reference` cites a unit that is not split (a chapter
    cited as "Tobit 3"). `(first, last)` are the `chapter:verse` labels it cites."""
    units = _verse_units(content, chapter, verses[0][1])
    packed = pack_units(units, settings.MAX_PASSAGE_CHARS, sep="")
    texts = [p.text for p in packed]
    named = name_pieces(base_anchor, content, texts, _verse_segments(verses))
    if len(packed) == 1 and whole_reference:
        refs = [whole_reference]
    else:
        refs = [piece_reference(book, units[p.first][0], units[_last_with_text(units, p)][0],
                                1, 1) for p in packed]
    shared = Counter(refs)
    seen: Counter = Counter()
    out = []
    for p, ref, (anchor, held) in zip(packed, refs, named):
        cited = (units[p.first][0], units[_last_with_text(units, p)][0])
        if shared[ref] > 1:
            seen[ref] += 1
            ref = piece_reference(ref, None, None, seen[ref], shared[ref])
        text = p.text
        lead = _LEADING_MARKER.match(text)
        if p is not packed[0] and lead:
            text = text[lead.end():]
            held = tuple((loc, max(0, at - lead.end())) for loc, at in held)
        out.append((text, ref, units[p.first][0].split(":")[1], anchor, held, cited))
    return out


def _with_titles(book: BookVerses) -> list[Verse]:
    """The book's verses, a Psalm title opening the verse it precedes (C-11, Carter
    9 Oct 2026): no marker or number of its own."""
    return [Verse(v.book, v.chapter, v.verse,
                  f"{book.titles[(v.chapter, v.verse)]} {v.text}".strip()
                  if (v.chapter, v.verse) in book.titles else v.text)
            for v in book.verses]


def check_complete(book: BookVerses, placed: set[tuple[int, int]],
                   prologue_placed: bool) -> None:
    """Raise unless every verse with text, every title and the prologue reached a
    passage. A verse with no text (Sirach 1:5) is excused."""
    verses = {(v.chapter, v.verse) for v in book.verses}
    stray = sorted(set(book.titles) - verses)
    if stray:
        raise ValueError(f"{book.name}: titles before no verse: {stray}")
    expected = {(v.chapter, v.verse) for v in _with_titles(book) if v.text.strip()}
    missing = sorted(expected - placed)
    if missing:
        raise ValueError(f"{book.name}: {len(missing)} verses reach no passage, "
                         f"first {missing[:5]}")
    if book.prologue and not prologue_placed:
        raise ValueError(f"{book.name}: the prologue reaches no passage")


def _source_label(book: BookVerses, label: str) -> str:
    """A `chapter:verse` label in WEB-C's numbers."""
    ch, v = (int(x) for x in label.split(":"))
    sc, sv = book.source_of.get((ch, v), (ch, v))
    return f"{sc}:{sv}"


def build_documents(usfm_dir: str | None = None, translation: str = "WEB-C",
                    pericope_path: str | None = None,
                    extra_path: str | None = None,
                    versification_path: str | None = None) -> list[Document]:
    """Build one Document per book; passages = verse groups (`group_verses`), each split
    to fit a card. Raises when a verse, a title or the prologue reaches no passage."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    usfm_dir = usfm_dir or os.path.join(root_dir, _DEFAULT_USFM_SUBDIR)
    pericope_map = load_pericopes(pericope_path or os.path.join(root_dir, _DEFAULT_PERICOPE_PATH))
    extra_map = load_extra_pericopes(extra_path or os.path.join(root_dir, _EXTRA_PERICOPE_PATH))
    books = load_usfm_directory(usfm_dir, load_versification(
        versification_path or os.path.join(root_dir, _VERSIFICATION_PATH)))

    docs: list[Document] = []
    for name, book in sorted(books.items()):
        source_key = f"bible/{book.book_code}"
        did = resolve_document_id("bible", source_key, ("bible", translation, name))
        # The registry keeps a renamed book's old slug, so no anchor changes (1.4a).
        book_slug = anchor_slug("bible", source_key) or slugify_book(name)
        passages: list[Passage] = []
        placed: set[tuple[int, int]] = set()

        if book.prologue:
            passages.append(Passage(
                content=clean_text(book.prologue), reference=f"{name}, Prologue",
                anchor=make_anchor(book_slug, "prologue"),
                chapter_key=make_anchor(book_slug, "prologue"), chapter_label="Prologue",
                position=0,
                metadata={"testament": book.testament, "translation": translation}))

        pericopes = [renumber_pericope(p, book.versification)
                     for p in pericope_map.get(_PERICOPE_BOOK.get(name, name), [])]
        whole_book_nv = book.versification is not None and book.versification.scope == "book"
        extras = extra_map.get(name, [])
        verses = _with_titles(book)
        if pericopes or extras:
            groups = group_verses(verses, pericopes, extras)
        else:
            # Books without pericopes (deuterocanonical): one group per chapter.
            groups = [VerseGroup(ch, [(v.chapter, v.verse, v.text) for v in vs], None)
                      for ch, vs in groupby(verses, key=lambda v: v.chapter)]

        for g in groups:
            content = clean_text(_join_with_verse_markers(g.verses))
            if not content:
                continue
            # Nova Vulgata numbers get their own anchors (1.4b): every passage of a book
            # renumbered whole, else a passage holding a moved verse (Romans 16:25-27).
            nv = whole_book_nv or any((ch, v) in book.source_of for ch, v, _ in g.verses)
            scheme = (book_slug, NV_SEGMENT) if nv else (book_slug,)
            base_anchor = make_anchor(*scheme, g.chapter, g.verses[0][1])
            chapter_key = make_anchor(*(scheme if whole_book_nv else (book_slug,)), g.chapter)
            whole = None if pericopes or extras else f"{name} {g.chapter}"
            metadata = {"testament": book.testament, "translation": translation}
            if g.title:
                metadata = {"pericope": g.title, **metadata, **g.refs}
            for piece, ref, label, anchor, units, (first, last) in _pieces(
                    name, g.chapter, g.verses, content, base_anchor, whole_reference=whole):
                extra = {"source_ref": piece_reference(
                    name, _source_label(book, first), _source_label(book, last), 1, 1)} \
                    if nv else {}
                passages.append(Passage(
                    content=piece, reference=ref, anchor=anchor,
                    chapter_key=chapter_key,
                    chapter_label=f"{name} {g.chapter}", position=len(passages),
                    unit_label=label, metadata={**metadata, **extra}, source_units=units,
                ))
            placed.update((ch, v) for ch, v, _ in g.verses)

        check_complete(book, placed, prologue_placed=bool(book.prologue))
        docs.append(Document(id=did, collection="bible", title=name, translation=translation,
                             metadata={"testament": book.testament,
                                       "source_key": source_key,
                                       "anchor_scheme": ANCHOR_SCHEME},
                             passages=passages))
    return docs
