"""Orchestrator: runs all ingest scripts then embed.py."""
from __future__ import annotations
import argparse
import asyncio
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from load import close_pool, get_pool

from ingest import bible, catechism, canon_law, encyclicals, church_fathers
import embed as embed_mod

PIPELINE: list[tuple[str, object]] = [
    ("bible",          bible),
    ("catechism",      catechism),
    ("canon-law",      canon_law),
    ("encyclicals",    encyclicals),
    ("church-fathers", church_fathers),
]


async def run(collection: str | None = None, skip_embed: bool = False) -> None:
    # Validate before acquiring any resources
    valid_names = [n for n, _ in PIPELINE]
    if collection is not None and collection not in valid_names:
        print(f"ERROR: Unknown collection '{collection}'. "
              f"Valid: {valid_names}", file=sys.stderr)
        return

    steps = [(name, mod) for name, mod in PIPELINE
             if collection is None or name == collection]

    pool = await get_pool()
    try:

        total_start = time.time()
        for name, mod in steps:
            print(f"\n{'='*50}")
            print(f"  Running: {name}")
            print(f"{'='*50}")
            step_start = time.time()
            await mod.main(pool)
            elapsed = time.time() - step_start
            print(f"  [{name}] completed in {elapsed:.1f}s")

        if not skip_embed:
            print(f"\n{'='*50}")
            print(f"  Running: embed")
            print(f"{'='*50}")
            embed_start = time.time()
            await embed_mod.run_for_main_pool(pool, dry_run=False)
            print(f"  [embed] completed in {time.time() - embed_start:.1f}s")

        print(f"\nTotal pipeline time: {time.time() - total_start:.1f}s")
    finally:
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Body of Christ data pipeline.")
    parser.add_argument(
        "--collection",
        help="Run only this collection (bible, catechism, canon-law, encyclicals, church-fathers)"
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="Skip the embedding step."
    )
    args = parser.parse_args()
    asyncio.run(run(collection=args.collection, skip_embed=args.skip_embed))
