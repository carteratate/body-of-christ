"""
Batch embed all un-embedded chunks via OpenAI Embeddings API.

Reads chunks with NULL content_embedding from the database, sends them to
OpenAI in batches, and updates the database with the resulting vectors.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Iterator

import openai
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import settings
from load import close_pool, get_pool

_BATCH_SIZE = 100
_MAX_RETRIES = 3
_MAX_CHARS = 30000  # ~7500 tokens — safely under OpenAI's 8192-token limit


def make_batches(items: list, size: int) -> Iterator[list]:
    """Yield successive chunks of `size` from items."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def vec_to_pg(vec: list[float]) -> str:
    """Format a float list as pgvector literal: [f1,f2,...]"""
    return "[" + ",".join(str(v) for v in vec) + "]"


async def embed_batch(client: openai.AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API with retry on rate limit."""
    for attempt in range(_MAX_RETRIES):
        try:
            response = await client.embeddings.create(
                input=texts,
                model=settings.EMBEDDING_MODEL,
                dimensions=settings.EMBEDDING_DIMS,
            )
            sorted_data = sorted(response.data, key=lambda r: r.index)
            return [r.embedding for r in sorted_data]
        except openai.RateLimitError:
            if attempt == _MAX_RETRIES - 1:
                raise
            wait = 2 ** (attempt + 1)
            print(f"\n  Rate limited — waiting {wait}s...", file=sys.stderr)
            await asyncio.sleep(wait)
    raise RuntimeError("embed_batch: unreachable")


async def _embed_chunks(pool, client: openai.AsyncOpenAI, dry_run: bool = False) -> None:
    """Core embedding logic — shared by run() and run_for_main_pool()."""
    rows = await pool.fetch(
        "SELECT id, content FROM chunks WHERE content_embedding IS NULL ORDER BY id"
    )

    if dry_run:
        print(f"[dry-run] {len(rows)} chunks need embedding. Exiting.")
        return

    if not rows:
        print("All chunks already embedded.")
        return

    print(f"Embedding {len(rows)} chunks in batches of {_BATCH_SIZE}...")
    embedded = 0
    failed_ids: list[str] = []

    with tqdm(total=len(rows), unit="chunk", desc="Embed") as pbar:
        for batch in make_batches(list(rows), _BATCH_SIZE):
            texts = [r["content"][:_MAX_CHARS] for r in batch]
            try:
                vectors = await embed_batch(client, texts)
            except Exception as exc:
                ids = [str(r["id"]) for r in batch]
                print(f"\n  WARNING: Batch failed ({exc}). IDs: {ids[:3]}...", file=sys.stderr)
                failed_ids.extend(ids)
                pbar.update(len(batch))
                continue

            async with pool.acquire() as conn:
                async with conn.transaction():
                    for row, vec in zip(batch, vectors):
                        await conn.execute(
                            "UPDATE chunks SET content_embedding = $1::vector WHERE id = $2",
                            vec_to_pg(vec),
                            row["id"],
                        )
            embedded += len(batch)
            pbar.update(len(batch))

    print(f"  Done. {embedded} chunks embedded.")
    if failed_ids:
        print(f"  WARNING: {len(failed_ids)} chunks failed — re-run embed.py to retry.", file=sys.stderr)


async def run(dry_run: bool = False) -> None:
    """Standalone entry point — creates and closes its own pool."""
    pool = await get_pool()
    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        await _embed_chunks(pool, client, dry_run)
    finally:
        await client.close()
        await close_pool()


async def run_for_main_pool(pool, dry_run: bool = False) -> None:
    """Entry point for run_all.py — accepts existing pool, does not close it."""
    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        await _embed_chunks(pool, client, dry_run)
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Embed all un-embedded chunks via OpenAI.")
    parser.add_argument("--dry-run", action="store_true", help="Print count and exit without calling OpenAI.")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))
