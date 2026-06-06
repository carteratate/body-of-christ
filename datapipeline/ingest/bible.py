"""WEB-C (World English Bible — Catholic) ingestion via USFM files.

Chunking strategy:
  - 66 canonical books:  one chunk per named pericope
                         (boundaries from PericopeGroupedKJVVerses.json)
  - 7 deuterocanonical books: one chunk per chapter

Usage:
    python ingest/bible.py                            # WEB-C (default)
    python ingest/bible.py --translation WEB-C        # explicit
    python ingest/bible.py --usfm-dir /path/to/dir --translation MyTranslation

USFM format notes:
  - \\id CODE ...       — book identifier (e.g. MAT)
  - \\c N               — chapter N starts
  - \\v N text          — verse N text (may wrap to continuation lines)
  - \\w word|strong="H1234"\\w*  — Strong's markup (word extracted, rest stripped)
  - \\f ... \\f*        — footnote (stripped)
  - \\x ... \\x*        — cross-reference (stripped)
  - \\wj ... \\wj*      — words of Jesus (stripped, content kept)
  - Other backslash markers (\\p, \\q1, \\q2, \\sp, etc.) are stripped.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Iterator

from tqdm import tqdm

# Add datapipeline root to path so config/load are importable when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings  # noqa: E402
from load import close_pool, get_pool, upsert_chunk, upsert_document  # noqa: E402

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
    "Ecclesiastes": "OT", "Song of Solomon": "OT", "Isaiah": "OT",
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
    "SNG": "Song of Solomon",
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

# Deuterocanonical books chunked per-chapter (not by pericope).
_DEUTEROCANONICAL_BOOKS: frozenset[str] = frozenset({
    "Tobit", "Judith", "1 Maccabees", "2 Maccabees", "Wisdom", "Sirach", "Baruch",
})

# Default source paths (relative to the datapipeline root directory).
_DEFAULT_USFM_SUBDIR = os.path.join("sources", "bible", "eng-web-c_usfm")
_DEFAULT_PERICOPE_PATH = os.path.join("sources", "bible", "PericopeGroupedKJVVerses.json")


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
                if re.match(r"^\\(id|ide|h|toc|mt|imt|ms|mr|s|sr|r|d|sp|b|li|lim|cls)\b", line):
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


def _book_code_from_usfm(path: str) -> str | None:
    """Read the \\id line from a USFM file and return the 3-letter book code."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = re.match(r"^\\id\s+([A-Z0-9]{2,3})", line)
            if m:
                return m.group(1)
    return None


def load_usfm_directory(usfm_dir: str) -> dict[str, BookVerses]:
    """Load all USFM files in a directory.

    Returns a dict of {canonical_book_name: BookVerses}.
    Files that do not map to a known canonical name are skipped.
    """
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
        verse_list = [
            Verse(canonical, ch, v, text)
            for (ch, v), text in sorted(verse_map.items())
        ]
        books[canonical] = BookVerses(
            name=canonical,
            book_code=code,
            testament=testament,
            verses=verse_list,
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
# Chunking
# ---------------------------------------------------------------------------

def collect_pericope_verses(
    verse_map: dict[tuple[int, int], str],
    start_chapter: int,
    start_verse: int,
    end_chapter: int,
    end_verse: int,
) -> list[tuple[int, int, str]]:
    """Return (chapter, verse, text) tuples within [start, end] inclusive."""
    result = []
    for (ch, v), text in sorted(verse_map.items()):
        if (ch, v) < (start_chapter, start_verse):
            continue
        if (ch, v) > (end_chapter, end_verse):
            continue
        result.append((ch, v, text))
    return result


def chunk_canonical_book(
    book: BookVerses,
    pericopes: list[Pericope],
    translation: str,
) -> Iterator[tuple[str, str, dict, int]]:
    """Yield (content, reference, metadata, position) for a canonical book.

    One chunk per pericope. Empty chunks are skipped.
    """
    verse_map: dict[tuple[int, int], str] = {
        (v.chapter, v.verse): v.text for v in book.verses
    }
    position = 0
    for p in pericopes:
        verses = collect_pericope_verses(
            verse_map, p.start_chapter, p.start_verse, p.end_chapter, p.end_verse
        )
        if not verses:
            continue
        content = " ".join(text for _, _, text in verses)
        if not content.strip():
            continue
        reference = _format_reference(
            book.name, p.start_chapter, p.start_verse, p.end_chapter, p.end_verse
        )
        metadata = {
            "pericope": p.title,
            "book": book.name,
            "testament": book.testament,
            "translation": translation,
        }
        yield content, reference, metadata, position
        position += 1


def chunk_deuterocanonical_book(
    book: BookVerses,
    translation: str,
) -> Iterator[tuple[str, str, dict, int]]:
    """Yield (content, reference, metadata, position) for a deuterocanonical book.

    One chunk per chapter. Empty chapters are skipped.
    """
    chapters: dict[int, list[str]] = {}
    for v in book.verses:
        chapters.setdefault(v.chapter, []).append(v.text)

    position = 0
    for ch in sorted(chapters):
        texts = chapters[ch]
        content = " ".join(texts)
        if not content.strip():
            continue
        reference = f"{book.name} {ch}"
        metadata = {
            "book": book.name,
            "chapter": ch,
            "testament": book.testament,
            "translation": translation,
        }
        yield content, reference, metadata, position
        position += 1


# ---------------------------------------------------------------------------
# Ingest functions
# ---------------------------------------------------------------------------

async def ingest_webc(
    pool,
    usfm_dir: str | None = None,
    translation: str = "WEB-C",
) -> None:
    """Ingest WEB-C Bible from USFM files into the database.

    Args:
        pool:        asyncpg connection pool.
        usfm_dir:    Path to directory containing *.usfm files.
                     Defaults to sources/bible/eng-web-c_usfm/ relative to datapipeline root.
        translation: Label stored in the database; default "WEB-C".
    """
    datapipeline_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if usfm_dir is None:
        usfm_dir = os.path.join(datapipeline_root, _DEFAULT_USFM_SUBDIR)
    pericope_path = os.path.join(datapipeline_root, _DEFAULT_PERICOPE_PATH)

    print(f"Loading WEB-C USFM files from: {usfm_dir}")
    all_books = load_usfm_directory(usfm_dir)
    print(f"  Loaded {len(all_books)} books from USFM.")

    print(f"Loading pericopes from: {pericope_path}")
    pericope_map = load_pericopes(pericope_path)
    print(f"  Loaded pericopes for {len(pericope_map)} books.")

    canonical_books = {
        name: bv for name, bv in all_books.items()
        if name not in _DEUTEROCANONICAL_BOOKS
    }
    deutero_books = {
        name: bv for name, bv in all_books.items()
        if name in _DEUTEROCANONICAL_BOOKS
    }

    print(
        f"  {len(canonical_books)} canonical books (pericope chunking), "
        f"{len(deutero_books)} deuterocanonical books (chapter chunking)."
    )

    total_chunks = 0

    with tqdm(total=len(all_books), unit="book", desc=f"Ingesting {translation}") as pbar:
        # --- Canonical books ---
        for book_name, book in sorted(canonical_books.items()):
            testament = book.testament
            doc_id = await upsert_document(
                pool,
                collection="bible",
                title=book_name,
                translation=translation,
                author=None,
                year=None,
                metadata={"testament": testament},
            )
            pericopes = pericope_map.get(book_name, [])
            if not pericopes:
                pbar.set_postfix({"book": book_name, "chunks": 0, "note": "no pericopes"})
                pbar.update(1)
                continue

            book_chunks = 0
            for content, reference, metadata, position in chunk_canonical_book(
                book, pericopes, translation
            ):
                await upsert_chunk(
                    pool,
                    document_id=doc_id,
                    content=content,
                    position=position,
                    reference=reference,
                    metadata=metadata,
                )
                total_chunks += 1
                book_chunks += 1

            pbar.set_postfix({"book": book_name, "chunks": book_chunks})
            pbar.update(1)

        # --- Deuterocanonical books ---
        for book_name, book in sorted(deutero_books.items()):
            testament = book.testament
            doc_id = await upsert_document(
                pool,
                collection="bible",
                title=book_name,
                translation=translation,
                author=None,
                year=None,
                metadata={"testament": testament},
            )

            book_chunks = 0
            for content, reference, metadata, position in chunk_deuterocanonical_book(
                book, translation
            ):
                await upsert_chunk(
                    pool,
                    document_id=doc_id,
                    content=content,
                    position=position,
                    reference=reference,
                    metadata=metadata,
                )
                total_chunks += 1
                book_chunks += 1

            pbar.set_postfix({"book": book_name, "chunks": book_chunks})
            pbar.update(1)

    print(f"  Done. {total_chunks} chunks written for {translation}.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def main(pool=None, usfm_dir: str | None = None, translation: str = "WEB-C") -> None:
    """Ingest WEB-C Bible. Accepts an external pool (from run_all.py)
    or creates its own when run standalone."""
    _own_pool = pool is None
    if _own_pool:
        pool = await get_pool()
    try:
        await ingest_webc(pool, usfm_dir=usfm_dir, translation=translation)
    finally:
        if _own_pool:
            await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest WEB-C Bible (USFM) into the Body of Christ RAG database."
    )
    parser.add_argument(
        "--translation",
        default="WEB-C",
        help="Translation label stored in the database (default: WEB-C).",
    )
    parser.add_argument(
        "--usfm-dir",
        default=None,
        dest="usfm_dir",
        help="Path to directory of *.usfm files. Defaults to sources/bible/eng-web-c_usfm/.",
    )
    args = parser.parse_args()

    asyncio.run(main(usfm_dir=args.usfm_dir, translation=args.translation))
