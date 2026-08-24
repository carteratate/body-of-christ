"""Re-embed Qdrant points whose stored vector was built from different text.

    cd datapipeline
    python3 scripts/reembed_drifted_vectors.py --collection all              # dry run
    python3 scripts/reembed_drifted_vectors.py --collection all --apply      # write

DRY RUN IS THE DEFAULT. `--apply` is required to write.

⚠️  RUN THIS BEFORE `reconcile_qdrant_payloads.py --fields content`. That sync
overwrites Qdrant `content` with the signal this tool classifies on. Simulated live:
54 points would become permanently undetectable (25 content_unrelated, including 17
Gaudete in Domino; all 29 minor_text) — and the run would still report `selected=296`
rather than "nothing to do", because the remaining points also carry a drifted
`chapter_label`, which the reconcile does not sync. A healthy-looking number hiding a
silent loss.

WHY A PAYLOAD SYNC IS NOT ENOUGH
`reconcile_qdrant_payloads.py` fixes the TEXT a point displays. It cannot fix the
VECTOR — `set_payload` writes payload only — so a point embedded from text that is no
longer its row stays retrievable by words the user never sees. `Gaudete in Domino` is
the worst case: all 78 of its points hold footnote fragments ("2 Cor. 11:28.", median
14 characters) and their vectors were built from those footnotes, so the document is
findable by its citations and not by its content.

WHAT THIS DELIBERATELY REFUSES TO DO
Re-embedding "wherever the stores disagree" would rewrite 26,931 points, 26,581 of them
Summa passages whose Qdrant copy merely retains the inline "Objection N" prefix — a
known, deliberate transformation from commit 16f6d27, same passage either way.

Their repair would be exactly as marginal as the `label_drift` points this DOES select
(median reproduction cosine 0.977 vs 0.988) for 113x the writes. The refusal is a
decision about blast radius, NOT a claim that their vectors are better than the ones
being fixed — see `reembed.py` for the measured distribution. Passing `--categories
all` overrides it; there is no good reason to today.

Live scope (2026-08-21): 350 points — content_unrelated 86, label_drift 235,
minor_text 29. A further 21 Summa points have a blank Postgres passage and are refused
under every selection: there is nothing to rebuild a vector from.

SAFE TO RE-RUN. Drift is recomputed from both stores every time, so a completed run
reports nothing to do and an interrupted one resumes. Point ids are the deterministic
`chunks.id`, so writes overwrite in place and never duplicate.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backfill_missing_vectors import ArgError, embed_texts, plan  # noqa: E402
from backfill_vectors import PassageRow, build_payload  # noqa: E402
from reembed import (  # noqa: E402
    BLANK_SOURCE, CONTENT_UNRELATED, DEFAULT_CATEGORIES, IN_SYNC, LABEL_DRIFT,
    MARKER_PREFIX, MINOR_TEXT, classify, needs_reembed,
)

CATEGORY_SETS: dict[str, frozenset[str]] = {
    "default": DEFAULT_CATEGORIES,
    "unrelated": frozenset({CONTENT_UNRELATED}),
    "all": frozenset({CONTENT_UNRELATED, LABEL_DRIFT, MINOR_TEXT, MARKER_PREFIX}),
}

_REPORT_ORDER = (CONTENT_UNRELATED, LABEL_DRIFT, MINOR_TEXT, MARKER_PREFIX,
                 BLANK_SOURCE)

# The full document in position order — the same requirement `plan()` documents. The
# neighbour text spliced into an embedding input comes from the passages either side,
# so a drifted point must be embedded with its whole document present, not alone.
_SQL = """
    SELECT c.id::text AS chunk_id, c.document_id::text AS document_id,
           d.title AS document_title, d.author, d.collection,
           c.content, c.reference, c.anchor, c.chapter_key, c.chapter_label,
           c.unit_label, c.position
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE d.collection = $1
    ORDER BY c.document_id, c.position
"""


async def _qdrant_payloads(client, collection: str) -> dict[str, dict]:
    from writers.qdrant import QDRANT_COLLECTION, collection_filter

    payloads: dict[str, dict] = {}
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=collection_filter(collection),
            limit=1000, offset=offset,
            with_payload=["content", "chapter_label"], with_vectors=False,
        )
        for point in points:
            payloads[str(point.id)] = point.payload or {}
        if offset is None:
            return payloads


def classify_rows(rows: list[PassageRow], payloads: dict[str, dict]) -> dict[str, str]:
    """chunk_id -> drift category, for every row that has a Qdrant point.

    Rows with no point are skipped rather than reported: that is the backfill's job
    (`backfill_missing_vectors.py`), and a tool that both creates and overwrites points
    would make an interrupted run much harder to reason about.
    """
    out: dict[str, str] = {}
    for row in rows:
        payload = payloads.get(row.chunk_id)
        if payload is None:
            continue
        out[row.chunk_id] = classify(
            row.content or "", payload.get("content") or "",
            row.chapter_label, payload.get("chapter_label"),
        )
    return out


async def reembed_collection(client, conn, collection: str, categories: frozenset[str],
                             apply: bool, batch_size: int) -> tuple[int, int]:
    """Returns (selected_count, written_count)."""
    from qdrant_client.models import PointStruct

    from writers.qdrant import upsert_points

    rows = [PassageRow(**dict(r)) for r in await conn.fetch(_SQL, collection)]
    payloads = await _qdrant_payloads(client, collection)
    categorised = classify_rows(rows, payloads)

    counts = {category: 0 for category in _REPORT_ORDER}
    selected: set[str] = set()
    for chunk_id, category in categorised.items():
        if category == IN_SYNC:
            continue
        counts[category] = counts.get(category, 0) + 1
        if needs_reembed(category, categories):
            selected.add(chunk_id)

    drifted = sum(counts.values())
    summary = "  ".join(f"{name}={counts[name]}" for name in _REPORT_ORDER if counts[name])
    print(f"{collection:24} points={len(categorised):>6} drifted={drifted:>6} "
          f"selected={len(selected):>5}   {summary}")

    refused = counts.get(MARKER_PREFIX, 0)
    if refused and MARKER_PREFIX not in categories:
        print(f"    {refused} marker_prefix point(s) NOT re-embedded — same passage "
              f"(a retained dialectical marker), so the repair would be no larger than "
              f"that of the categories this tool does select, for ~76x the writes. "
              f"Use --categories all to override.")
    blank = counts.get(BLANK_SOURCE, 0)
    if blank:
        print(f"    ⚠️  {blank} point(s) have a BLANK Postgres passage — never "
              f"re-embedded under any selection, since there is nothing to rebuild a "
              f"vector from. This is an ingest defect to fix upstream.")
    if not selected:
        print("    nothing to do")
        return 0, 0

    work = [item for item in plan(rows, selected)]
    if not apply:
        print(f"    DRY RUN — {len(work)} point(s) would be re-embedded and overwritten. "
              f"Re-run with --apply to write.")
        return len(selected), 0

    written = 0
    for start in range(0, len(work), batch_size):
        window = work[start:start + batch_size]
        vectors = await embed_texts([text for _, text in window])
        # Same guard, same reason as the backfill: vectors are paired to rows BY
        # POSITION, so a short response shifts every later vector onto the wrong
        # passage rather than merely dropping a tail.
        if len(vectors) != len(window):
            raise RuntimeError(
                f"got {len(vectors)} vectors for {len(window)} passages; refusing to "
                f"write positionally mismatched points"
            )
        await upsert_points(client, [
            PointStruct(id=row.chunk_id, vector=vector, payload=build_payload(row))
            for (row, _), vector in zip(window, vectors)
        ])
        written += len(window)
        print(f"      … {written}/{len(work)}", flush=True)
    return len(selected), written


async def main(collections: list[str], categories: frozenset[str],
               apply: bool, batch_size: int) -> int:
    from config import settings
    from writers.qdrant import get_client

    conn = await asyncpg.connect(settings.DATABASE_URL, statement_cache_size=0)
    exit_code = 0
    try:
        client = get_client()
        try:
            for collection in collections:
                try:
                    await reembed_collection(client, conn, collection, categories,
                                             apply, batch_size)
                except Exception as exc:
                    print(f"    ✗ FAILED: {exc}")
                    print(f"      Re-run to resume — drift is recomputed from both "
                          f"stores, so points already rewritten fall out of scope.")
                    exit_code = 1
        finally:
            await client.close()
    finally:
        await conn.close()
    return exit_code


def resolve_args(collection: str, category_set: str, batch_size: int,
                 valid_collections: set[str]) -> tuple[list[str], frozenset[str]]:
    """Validate an argument combination; return (collection names, categories)."""
    if collection == "all":
        names = sorted(valid_collections)
    elif collection in valid_collections:
        names = [collection]
    else:
        raise ArgError(f"unknown collection {collection!r}. "
                       f"Valid: {', '.join(sorted(valid_collections))}, or 'all'")

    if batch_size < 1:
        raise ArgError(f"--batch-size must be >= 1 (got {batch_size}); a non-positive "
                       f"value silently writes nothing and reports success")

    if category_set not in CATEGORY_SETS:
        raise ArgError(f"unknown category set {category_set!r}. "
                       f"Valid: {', '.join(sorted(CATEGORY_SETS))}")

    return names, CATEGORY_SETS[category_set]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collection", required=True, help="collection name, or 'all'")
    ap.add_argument("--categories", choices=sorted(CATEGORY_SETS), default="default",
                    help="default = content_unrelated + label_drift + minor_text (350 "
                         "points); unrelated = only the 86 whose vector was built from "
                         "another passage; all = also the 26,581 summa marker-prefix "
                         "points, for 26,931 total — a full-collection rewrite whose "
                         "per-point gain is no larger than the default selection's. "
                         "No selection ever includes blank_source.")
    ap.add_argument("--apply", action="store_true",
                    help="actually re-embed and overwrite; omit for a dry run")
    ap.add_argument("--batch-size", type=int, default=100)
    args = ap.parse_args()

    from publication import SOURCE_ADAPTERS  # noqa: E402

    try:
        names, categories = resolve_args(
            args.collection,
            args.categories,
            args.batch_size,
            set(SOURCE_ADAPTERS),
        )
    except ArgError as exc:
        ap.error(str(exc))

    raise SystemExit(asyncio.run(main(names, categories, args.apply, args.batch_size)))
