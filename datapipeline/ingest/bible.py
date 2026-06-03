"""Catholic Bible ingestion: CPDV (local JSON) and Douay-Rheims (Project Gutenberg).

Usage:
    python ingest/bible.py                       # both translations
    python ingest/bible.py --translation CPDV
    python ingest/bible.py --translation douay-rheims

Project Gutenberg #8300 format notes:
  - Chapter headers: "BookName Chapter N"  (e.g. "Genesis Chapter 1")
  - Verse lines:     "chapter:verse. Text" (e.g. "1:1. In the beginning...")
  - Verse text may wrap across continuation lines until a blank line.
  - Annotation/footnote lines (prose not starting with "N:N.") are skipped.

CPDV source:
  - Local file: datapipeline/sources/bible/cpdv.json
  - Format: {"charset": "UTF-8", "Genesis": {"1": {"1": "text", ...}, ...}, ...}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Iterator

import httpx
from tqdm import tqdm

# Add datapipeline root to path so config/load are importable when run directly.
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings  # noqa: E402
from load import close_pool, get_pool, upsert_chunk, upsert_document  # noqa: E402

# ---------------------------------------------------------------------------
# Canonical book name → testament
# Includes full 73-book Catholic canon (deuterocanonicals included).
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
# Douay-Rheims (PG #8300) book name mapping
#
# PG #8300 uses "BookName Chapter N" headers. The "BookName" portion uses
# Douay-Rheims Latinised spellings (Josue, Isaias, Tobias, etc.).
# Map to canonical names used in the documents table.
# ---------------------------------------------------------------------------
DR_PG_BOOK_NAME_MAP: dict[str, str] = {
    "Genesis": "Genesis",
    "Exodus": "Exodus",
    "Leviticus": "Leviticus",
    "Numbers": "Numbers",
    "Deuteronomy": "Deuteronomy",
    "Josue": "Joshua",
    "Judges": "Judges",
    "Ruth": "Ruth",
    "1 Kings": "1 Samuel",
    "2 Kings": "2 Samuel",
    "3 Kings": "1 Kings",
    "4 Kings": "2 Kings",
    "1 Paralipomenon": "1 Chronicles",
    "2 Paralipomenon": "2 Chronicles",
    "1 Esdras": "Ezra",
    "2 Esdras": "Nehemiah",
    "Tobias": "Tobit",
    "Judith": "Judith",
    "Esther": "Esther",
    "1 Machabees": "1 Maccabees",
    "2 Machabees": "2 Maccabees",
    "Job": "Job",
    "Psalms": "Psalms",
    "Proverbs": "Proverbs",
    "Ecclesiastes": "Ecclesiastes",
    "Canticle of Canticles": "Song of Solomon",
    "Wisdom": "Wisdom",
    "Ecclesiasticus": "Sirach",
    "Isaias": "Isaiah",
    "Jeremias": "Jeremiah",
    "Lamentations": "Lamentations",
    "Baruch": "Baruch",
    "Ezechiel": "Ezekiel",
    "Daniel": "Daniel",
    "Osee": "Hosea",
    "Joel": "Joel",
    "Amos": "Amos",
    "Abdias": "Obadiah",
    "Jonas": "Jonah",
    "Micheas": "Micah",
    "Nahum": "Nahum",
    "Habacuc": "Habakkuk",
    "Sophonias": "Zephaniah",
    "Aggeus": "Haggai",
    "Zacharias": "Zechariah",
    "Malachias": "Malachi",
    # New Testament (same spelling as canonical)
    "Matthew": "Matthew",
    "Mark": "Mark",
    "Luke": "Luke",
    "John": "John",
    "Acts": "Acts",
    "Romans": "Romans",
    "1 Corinthians": "1 Corinthians",
    "2 Corinthians": "2 Corinthians",
    "Galatians": "Galatians",
    "Ephesians": "Ephesians",
    "Philippians": "Philippians",
    "Colossians": "Colossians",
    "1 Thessalonians": "1 Thessalonians",
    "2 Thessalonians": "2 Thessalonians",
    "1 Timothy": "1 Timothy",
    "2 Timothy": "2 Timothy",
    "Titus": "Titus",
    "Philemon": "Philemon",
    "Hebrews": "Hebrews",
    "James": "James",
    "1 Peter": "1 Peter",
    "2 Peter": "2 Peter",
    "1 John": "1 John",
    "2 John": "2 John",
    "3 John": "3 John",
    "Jude": "Jude",
    "Apocalypse": "Revelation",
}


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
    book_code: str          # USFM code (empty for DR/CPDV JSON)
    testament: str          # "OT" | "NT"
    verses: list[Verse] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CPDV JSON parser
# ---------------------------------------------------------------------------

def parse_cpdv_json(data: dict) -> list[BookVerses]:
    """Parse the CPDV JSON structure {book: {chapter: {verse: text}}} into BookVerses."""
    books: list[BookVerses] = []
    for book_name, chapters in data.items():
        if book_name == "charset":
            continue
        testament = _BOOK_TESTAMENT.get(book_name)
        if testament is None:
            continue
        verses: list[Verse] = []
        for ch_str, verse_dict in chapters.items():
            ch = int(ch_str)
            for v_str, text in verse_dict.items():
                verses.append(Verse(book_name, ch, int(v_str), text))
        books.append(BookVerses(name=book_name, book_code="", testament=testament, verses=verses))
    return books


# ---------------------------------------------------------------------------
# Project Gutenberg Douay-Rheims (#8300) parser
# ---------------------------------------------------------------------------
#
# File format:
#   - Chapter headers: "BookName Chapter N"
#   - Verse lines:     "chapter:verse. Text that may wrap..."
#   - Continuation:    non-blank lines following a verse (before next blank/verse)
#   - Annotations:     prose lines that look like continuations but are chapter
#                      summaries — we skip them by only collecting continuation
#                      lines that come right after a confirmed verse line.
#
# Verse line regex: starts with digits:digits followed by a period and space.
# -------------------------------------------------------------------------

_DR_CHAPTER_HDR_RE = re.compile(r"^(.+?)\s+Chapter\s+\d+\s*$")
_DR_VERSE_LINE_RE = re.compile(r"^(\d+):(\d+)\.\s+(.+)$")


def parse_douay_rheims(text: str) -> list[BookVerses]:
    """
    Parse the Project Gutenberg plain-text Douay-Rheims Bible (#8300).

    Returns a list of BookVerses, one per canonical book name.
    Books with the same canonical name (e.g. because multiple PG book names
    map to the same canonical) have their verses merged in order.
    """
    lines = text.splitlines()

    # Skip Gutenberg preamble.
    start_idx = 0
    for i, line in enumerate(lines):
        if "*** START OF" in line or "***START OF" in line:
            start_idx = i + 1
            break

    # We accumulate verses per canonical book name to handle cases where
    # the same book appears across multiple chapter-header entries.
    book_order: list[str] = []          # insertion order of canonical names
    book_verses: dict[str, BookVerses] = {}

    current_canonical: str | None = None
    last_was_verse = False              # True after a verse line, False after blank/header

    for line in lines[start_idx:]:
        raw = line.rstrip()

        # End of Project Gutenberg content
        if "*** END OF" in raw or "***END OF" in raw:
            break

        stripped = raw.strip()

        if not stripped:
            last_was_verse = False
            continue

        # Try verse line first (most common content line)
        m = _DR_VERSE_LINE_RE.match(stripped)
        if m and current_canonical is not None:
            ch = int(m.group(1))
            v = int(m.group(2))
            verse_text = m.group(3).strip()
            book_verses[current_canonical].verses.append(
                Verse(current_canonical, ch, v, verse_text)
            )
            last_was_verse = True
            continue

        # Try chapter header: "BookName Chapter N"
        hm = _DR_CHAPTER_HDR_RE.match(stripped)
        if hm:
            pg_book_name = hm.group(1).strip()
            canonical = DR_PG_BOOK_NAME_MAP.get(pg_book_name)
            if canonical is not None:
                current_canonical = canonical
                if canonical not in book_verses:
                    testament = _BOOK_TESTAMENT.get(canonical, "OT")
                    book_verses[canonical] = BookVerses(
                        name=canonical,
                        book_code="",
                        testament=testament,
                    )
                    book_order.append(canonical)
                last_was_verse = False
                continue

        # Continuation line — append to the last verse if we're in a verse block.
        # We only treat it as continuation if:
        #   1. last_was_verse is True (we are still inside a verse paragraph)
        #   2. current_canonical is set
        #   3. the line doesn't look like a chapter summary (hard to distinguish
        #      perfectly, but verse continuations come right after a verse line
        #      with no blank line in between)
        if last_was_verse and current_canonical and book_verses[current_canonical].verses:
            book_verses[current_canonical].verses[-1].text += " " + stripped
            # last_was_verse remains True until we hit a blank line

    # Return books in insertion order, skipping empty ones
    result = [book_verses[name] for name in book_order if book_verses[name].verses]
    return result


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------

def _make_reference(book: str, verses: list[Verse]) -> str:
    """Build a human-readable reference string, e.g. 'John 3:14-17'."""
    if not verses:
        return ""
    first = verses[0]
    last = verses[-1]
    if first.chapter == last.chapter:
        if first.verse == last.verse:
            return f"{book} {first.chapter}:{first.verse}"
        return f"{book} {first.chapter}:{first.verse}-{last.verse}"
    # Spans chapters
    return f"{book} {first.chapter}:{first.verse} – {last.chapter}:{last.verse}"


def chunk_book(book_verses: BookVerses, group_size: int, min_length: int) -> Iterator[tuple[str, str, int]]:
    """
    Yield (content, reference, position) tuples for each chunk.

    Verses are grouped `group_size` at a time; chunks never span chapters.
    """
    position = 0
    # Group by chapter to avoid cross-chapter chunks
    chapters: dict[int, list[Verse]] = {}
    for v in book_verses.verses:
        chapters.setdefault(v.chapter, []).append(v)

    for ch_num in sorted(chapters.keys()):
        ch_verses = chapters[ch_num]
        for i in range(0, len(ch_verses), group_size):
            group = ch_verses[i : i + group_size]
            content = " ".join(v.text for v in group)
            if len(content) < min_length:
                continue
            reference = _make_reference(book_verses.name, group)
            yield content, reference, position
            position += 1


# ---------------------------------------------------------------------------
# Download helper (used by Douay-Rheims)
# ---------------------------------------------------------------------------

def _download(url: str, description: str) -> bytes:
    """Download a URL synchronously with progress indication. Exits on failure."""
    print(f"Downloading {description}...")
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.content
    except httpx.HTTPError as exc:
        print(f"ERROR: Failed to download {description}: {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Ingest functions
# ---------------------------------------------------------------------------

DOUAY_RHEIMS_URL = "https://www.gutenberg.org/cache/epub/8300/pg8300.txt"


async def ingest_cpdv(pool) -> None:
    """Read CPDV from sources/bible/cpdv.json and ingest."""
    src = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "bible", "cpdv.json")
    print(f"Reading CPDV from {src}...")
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    books = parse_cpdv_json(data)
    print(f"  Found {len(books)} books in CPDV JSON.")
    _verify_deuterocanonicals(books, "CPDV")
    await _ingest_books(pool, books, translation="CPDV")


async def ingest_douay_rheims(pool) -> None:
    """Download and ingest the Douay-Rheims (Challoner) from Project Gutenberg."""
    raw = _download(DOUAY_RHEIMS_URL, "Douay-Rheims Bible from Project Gutenberg (#8300)")

    print("Parsing Douay-Rheims plain text...")
    text = raw.decode("utf-8", errors="replace")
    books = parse_douay_rheims(text)
    print(f"  Found {len(books)} books in Douay-Rheims text.")

    if len(books) < 60:
        print(
            f"  WARNING: Expected ~73 books but only found {len(books)}. "
            "The PG file structure may have changed.",
            file=sys.stderr,
        )

    _verify_deuterocanonicals(books, "Douay-Rheims")

    await _ingest_books(pool, books, translation="douay-rheims")


def _verify_deuterocanonicals(books: list[BookVerses], label: str) -> None:
    """Warn if any deuterocanonical books are missing."""
    deuterocanonicals = {"Tobit", "Judith", "1 Maccabees", "2 Maccabees", "Wisdom", "Sirach", "Baruch"}
    found_names = {b.name for b in books}
    missing = deuterocanonicals - found_names
    if missing:
        print(
            f"  WARNING: Deuterocanonical books missing from {label}: {sorted(missing)}",
            file=sys.stderr,
        )
    else:
        present = sorted(deuterocanonicals & found_names)
        print(f"  Deuterocanonical books confirmed present in {label}: {present}")


async def _ingest_books(pool, books: list[BookVerses], translation: str) -> None:
    """Write all books and their chunks to the database."""
    total_chunks = 0
    total_verses = sum(len(b.verses) for b in books)
    print(f"  Ingesting {len(books)} books / ~{total_verses} verses [{translation}]...")

    with tqdm(total=len(books), unit="book", desc=f"Ingesting {translation}") as pbar:
        for book in books:
            doc_id = await upsert_document(
                pool,
                collection="bible",
                title=book.name,
                translation=translation,
                author=None,
                year=None,
                metadata={
                    "translation": translation,
                    "book_code": book.book_code,
                    "testament": book.testament,
                },
            )

            chunks = list(
                chunk_book(book, settings.BIBLE_VERSE_GROUP_SIZE, settings.MIN_CHUNK_LENGTH)
            )

            for content, reference, position in chunks:
                await upsert_chunk(
                    pool,
                    document_id=doc_id,
                    content=content,
                    position=position,
                    reference=reference,
                )
                total_chunks += 1

            pbar.set_postfix({"book": book.name, "chunks": len(chunks)})
            pbar.update(1)

    print(f"  Done. {total_chunks} chunks written for {translation}.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Catholic Bible translations into the Body of Christ RAG database."
    )
    parser.add_argument(
        "--translation",
        choices=["CPDV", "douay-rheims"],
        default=None,
        help="Which translation to ingest. Omit to ingest both.",
    )
    args = parser.parse_args()

    pool = await get_pool()
    try:
        if args.translation in (None, "CPDV"):
            await ingest_cpdv(pool)
        if args.translation in (None, "douay-rheims"):
            await ingest_douay_rheims(pool)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
