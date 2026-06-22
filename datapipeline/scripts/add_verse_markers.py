"""Add inline {{v:N}} verse markers to existing Bible chunks in Supabase.

Reads each Bible chunk's reference field (e.g. "Matthew 5:3–12") to determine
which verses it spans, looks up the clean verse texts from the local USFM files,
then rebuilds the content with {{v:N}} markers before each verse after the first.

Only updates chunks whose content actually changes (i.e. multi-verse passages).
Does NOT touch Qdrant or re-embed — run with --target reader semantics only.

    cd datapipeline && python scripts/add_verse_markers.py
    cd datapipeline && python scripts/add_verse_markers.py --dry-run
"""
from __future__ import annotations

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg
from dotenv import load_dotenv

from ingest.bible import load_usfm_directory, _clean_usfm_text
from normalize.text import clean_text

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

_USFM_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sources", "bible", "eng-web-c_usfm",
)

# Map canonical book names to {(chapter, verse): clean_text}
_BOOK_TITLE_ALIASES = {
    "Song of Solomon": "Song of Solomon",
}


def _build_verse_lookup(usfm_dir: str) -> dict[str, dict[tuple[int, int], str]]:
    """Build {book_name: {(chapter, verse): text}} from USFM files."""
    books = load_usfm_directory(usfm_dir)
    lookup: dict[str, dict[tuple[int, int], str]] = {}
    for name, bv in books.items():
        lookup[name] = {(v.chapter, v.verse): v.text for v in bv.verses}
    return lookup


# Reference parsing: "Book ch:sv–ev" or "Book ch:sv–ec:ev" or "Book ch:sv"
_REF_RE = re.compile(
    r"^(.+?)\s+(\d+):(\d+)"       # book chapter:start_verse
    r"(?:–(\d+):(\d+))?"           # optional –end_chapter:end_verse
    r"(?:–(\d+))?"                 # optional –end_verse (same chapter)
    r"$"
)


def _parse_reference(ref: str) -> tuple[str, int, int, int, int] | None:
    """Parse reference → (book, start_ch, start_v, end_ch, end_v) or None."""
    m = _REF_RE.match(ref)
    if not m:
        return None
    book = m.group(1)
    sc, sv = int(m.group(2)), int(m.group(3))
    if m.group(4) and m.group(5):
        ec, ev = int(m.group(4)), int(m.group(5))
    elif m.group(6):
        ec, ev = sc, int(m.group(6))
    else:
        ec, ev = sc, sv
    return book, sc, sv, ec, ev


def _get_verses_in_range(
    verse_map: dict[tuple[int, int], str],
    sc: int, sv: int, ec: int, ev: int,
) -> list[tuple[int, int, str]]:
    """Return sorted (chapter, verse, text) within [start, end] inclusive."""
    result = []
    for (ch, v), text in sorted(verse_map.items()):
        if (ch, v) < (sc, sv):
            continue
        if (ch, v) > (ec, ev):
            continue
        result.append((ch, v, text))
    return result


def _add_markers(verses: list[tuple[int, int, str]]) -> str:
    """Join verse texts with {{v:N}} markers for all after the first."""
    parts = []
    for i, (_ch, v, text) in enumerate(verses):
        if i == 0:
            parts.append(text)
        else:
            parts.append("{{v:%d}} %s" % (v, text))
    return " ".join(parts)


def _inject_markers_into_existing(
    content: str,
    verses: list[tuple[int, int, str]],
    unit_label: str | None,
) -> str | None:
    """Find verse boundaries within existing content via substring search and
    inject {{v:N}} markers. Returns modified content or None if no verses found.

    Used for split chunks where rebuilding from scratch doesn't match because
    the chunk only contains a portion of the full verse range.
    """
    first_verse_num = int(unit_label) if unit_label and unit_label.isdigit() else None
    result = content
    insertions: list[tuple[int, int]] = []  # (position_in_result, verse_num)

    for _ch, v, text in verses:
        if v == first_verse_num:
            continue
        cleaned = clean_text(text)
        if not cleaned or len(cleaned) < 10:
            continue
        # Use first 40 chars as search key (enough to be unique)
        search_key = cleaned[:40]
        pos = content.find(search_key)
        if pos > 0:  # must be > 0 (not at start — that's unit_label's job)
            insertions.append((pos, v))

    if not insertions:
        return None

    insertions.sort(key=lambda x: x[0])
    # Build result with markers inserted at found positions (reverse order to preserve offsets)
    result = content
    for pos, v in reversed(insertions):
        marker = "{{v:%d}} " % v
        result = result[:pos] + marker + result[pos:]
    return result


async def migrate(dry_run: bool = False) -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    print(f"Loading USFM files from: {_USFM_DIR}")
    verse_lookup = _build_verse_lookup(_USFM_DIR)
    print(f"  Loaded {len(verse_lookup)} books")

    pool = await asyncpg.create_pool(
        db_url, min_size=1, max_size=3, statement_cache_size=0,
    )

    try:
        rows = await pool.fetch(
            """SELECT c.id, c.reference, c.unit_label, c.content, d.title as book_title
               FROM chunks c
               JOIN documents d ON c.document_id = d.id
               WHERE d.collection = 'bible'
               ORDER BY d.title, c.position"""
        )
        print(f"  Found {len(rows)} Bible chunks")

        updated = 0
        skipped_no_ref = 0
        skipped_no_parse = 0
        skipped_no_book = 0
        skipped_single = 0
        skipped_no_match = 0

        for row in rows:
            chunk_id = row["id"]
            ref = row["reference"]
            content = row["content"]
            book_title = row["book_title"]

            if not ref:
                skipped_no_ref += 1
                continue

            parsed = _parse_reference(ref)
            if not parsed:
                # Chapter-only refs like "Psalms 1" — try treating as full chapter
                m = re.match(r"^(.+?)\s+(\d+)$", ref)
                if m:
                    book_name = m.group(1)
                    ch = int(m.group(2))
                    vmap = verse_lookup.get(book_name)
                    if vmap:
                        chapter_verses = sorted(
                            [(c, v, t) for (c, v), t in vmap.items() if c == ch]
                        )
                        if len(chapter_verses) <= 1:
                            skipped_single += 1
                            continue
                        new_content = clean_text(_add_markers(chapter_verses))
                        if new_content != content and len(new_content) > 0:
                            if not dry_run:
                                await pool.execute(
                                    "UPDATE chunks SET content = $1 WHERE id = $2",
                                    new_content, chunk_id,
                                )
                            updated += 1
                            if updated <= 3:
                                print(f"  [sample] {ref}: added markers")
                                print(f"    old: {content[:100]}...")
                                print(f"    new: {new_content[:100]}...")
                        continue
                skipped_no_parse += 1
                continue

            book, sc, sv, ec, ev = parsed
            vmap = verse_lookup.get(book)
            if not vmap:
                skipped_no_book += 1
                continue

            verses = _get_verses_in_range(vmap, sc, sv, ec, ev)
            if len(verses) <= 1:
                skipped_single += 1
                continue

            new_content = clean_text(_add_markers(verses))

            # Verify the new content (without markers) roughly matches old content
            stripped = re.sub(r"\{\{v:\d+\}\}\s*", "", new_content)
            if len(stripped) == 0:
                skipped_no_match += 1
                continue

            # Check similarity — allow some variance from text normalization
            min_len = min(len(stripped), len(content))
            use_inject = False
            if min_len > 0:
                old_start = content[:80].lower().strip()
                new_start = stripped[:80].lower().strip()
                if old_start[:40] != new_start[:40]:
                    # Content doesn't match — this is a split chunk.
                    # Fall back to in-place marker injection.
                    use_inject = True

            if use_inject:
                injected = _inject_markers_into_existing(
                    content, verses, row["unit_label"],
                )
                if injected is None or injected == content:
                    skipped_no_match += 1
                    continue
                final_content = injected
            else:
                final_content = new_content

            if not dry_run:
                await pool.execute(
                    "UPDATE chunks SET content = $1 WHERE id = $2",
                    final_content, chunk_id,
                )
            updated += 1
            if updated <= 5:
                print(f"  [sample] {ref}: added markers")
                print(f"    old: {content[:120]}...")
                print(f"    new: {final_content[:120]}...")

        print(f"\nResults:")
        print(f"  Updated:          {updated}")
        print(f"  Single-verse:     {skipped_single} (no markers needed)")
        print(f"  No reference:     {skipped_no_ref}")
        print(f"  Unparsed ref:     {skipped_no_parse}")
        print(f"  Book not found:   {skipped_no_book}")
        print(f"  Content mismatch: {skipped_no_match}")
        if dry_run:
            print("  (DRY RUN — no changes written)")

    finally:
        await pool.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(migrate(dry_run=dry_run))
