# datapipeline/ingest/medieval.py
"""Medieval theology ingestion.

Downloads ThML XML from CCEL via httpx, parses using parse_thml_string()
from common.py, post-processes references for multi-work files, merges
short chapters, then upserts documents and chunks to the DB.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document
from ingest.common import parse_thml_string

_DELAY = 1.5       # seconds between CCEL requests
_MERGE_MIN = 450   # merge chunks shorter than this many chars
_CEILING = 3500    # hard max chunk size

# Manifest of works to ingest. Each entry:
#   url          — CCEL ThML XML direct URL
#   title        — document title to store in DB (overrides ThML metadata)
#   author       — real author name
#   year         — approximate year of composition
#   fix_author   — True when parse_thml treats work-titles as author labels
#                  (multi-work single-author files like Anselm's basic_works.xml)
#   merge_short  — True to merge consecutive short chapters (Imitation of Christ)
WORKS: list[dict] = [
    {
        "url":        "https://ccel.org/ccel/a/anselm/basic_works.xml",
        "title":      "Proslogium, Monologium, and Cur Deus Homo",
        "author":     "Anselm",
        "year":       1099,
        "fix_author": True,
        "merge_short": False,
    },
    {
        "url":        "https://ccel.org/ccel/b/boethius/consolation.xml",
        "title":      "Consolation of Philosophy",
        "author":     "Boethius",
        "year":       524,
        "fix_author": False,
        "merge_short": False,
    },
    {
        "url":        "https://ccel.org/ccel/b/bernard/loving_god.xml",
        "title":      "On Loving God",
        "author":     "Bernard of Clairvaux",
        "year":       1128,
        "fix_author": False,
        "merge_short": False,
    },
    {
        "url":        "https://ccel.org/ccel/k/kempis/imitation.xml",
        "title":      "Imitation of Christ",
        "author":     "Thomas à Kempis",
        "year":       1441,
        "fix_author": False,
        "merge_short": True,
    },
]


def fix_multi_work_refs(
    chunks: list[tuple[str, str, int, dict | None]],
    real_author: str,
) -> list[tuple[str, str, int, dict | None]]:
    """Rewrite refs produced by multi-author detection back to single-author form.

    parse_thml_string() treats Anselm's file as multi-author because it has
    multiple div1 elements with non-generic titles (Proslogium, Monologium…).
    That produces refs like "Proslogium — Chapter I". This function converts
    those to "Anselm — Proslogium, Chapter I".
    """
    fixed = []
    for content, ref, pos, meta in chunks:
        if " — " in ref and not ref.startswith(real_author):
            work_title, rest = ref.split(" — ", 1)
            new_ref = f"{real_author} — {work_title.strip()}, {rest.strip()}"
            fixed.append((content, new_ref, pos, meta))
        else:
            fixed.append((content, ref, pos, meta))
    return fixed


def merge_short_chunks(
    chunks: list[tuple[str, str, int, dict | None]],
    min_chars: int = _MERGE_MIN,
    ceiling: int = _CEILING,
) -> list[tuple[str, str, int, dict | None]]:
    """Merge adjacent short chunks so no chunk is below min_chars.

    Uses the first accumulated chunk's reference and metadata for the merged
    entry. Respects ceiling: never lets accumulated content exceed it.
    Reassigns positions sequentially starting from 0.
    """
    result: list[tuple[str, str, int, dict | None]] = []
    buf_parts: list[str] = []
    buf_ref: str = ""
    buf_meta: dict | None = None
    buf_len: int = 0
    out_pos: int = 0

    def _flush() -> None:
        nonlocal out_pos, buf_parts, buf_ref, buf_meta, buf_len
        if buf_parts:
            result.append(("\n\n".join(buf_parts), buf_ref, out_pos, buf_meta))
            out_pos += 1
            buf_parts, buf_ref, buf_meta, buf_len = [], "", None, 0

    for content, ref, _, meta in chunks:
        if len(content) >= min_chars:
            _flush()
            result.append((content, ref, out_pos, meta))
            out_pos += 1
        else:
            if buf_len + len(content) > ceiling:
                _flush()
            if not buf_parts:
                buf_ref = ref
                buf_meta = meta
            buf_parts.append(content)
            buf_len += len(content)
            if buf_len >= min_chars:
                _flush()

    _flush()
    return result


async def main(pool) -> None:
    """Download, parse, and upsert all medieval works."""
    total_chunks = 0

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        with tqdm(total=len(WORKS), unit="work", desc="Medieval") as pbar:
            for work in WORKS:
                url = work["url"]
                title = work["title"]
                author = work["author"]
                year = work["year"]

                pbar.set_postfix({"work": title[:30]})

                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    print(f"\n  WARNING: Failed to fetch {url}: {exc}", file=sys.stderr)
                    pbar.update(1)
                    time.sleep(_DELAY)
                    continue

                try:
                    doc = parse_thml_string(resp.text)
                except Exception as exc:
                    print(f"\n  WARNING: Failed to parse {title}: {exc}", file=sys.stderr)
                    pbar.update(1)
                    time.sleep(_DELAY)
                    continue

                if not doc.chunks:
                    print(f"\n  WARNING: No chunks from {title}", file=sys.stderr)
                    pbar.update(1)
                    time.sleep(_DELAY)
                    continue

                chunks = list(doc.chunks)

                if work["fix_author"]:
                    chunks = fix_multi_work_refs(chunks, author)

                if work["merge_short"]:
                    chunks = merge_short_chunks(chunks)

                doc_id = await upsert_document(
                    pool,
                    collection="medieval",
                    title=title,
                    translation="",
                    author=author,
                    year=year,
                    metadata={"source_url": url},
                )

                for content, reference, position, meta in chunks:
                    chunk_meta = (meta or {}) | {"source_url": url}
                    await upsert_chunk(pool, doc_id, content, position, reference, metadata=chunk_meta)

                total_chunks += len(chunks)
                pbar.set_postfix({"work": title[:30], "chunks": len(chunks)})
                pbar.update(1)
                time.sleep(_DELAY)

    print(f"  Done. {total_chunks} total chunks written for medieval.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
