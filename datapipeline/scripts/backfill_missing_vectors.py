"""Embed and upsert the Postgres chunks that have no Qdrant point.

    cd datapipeline
    python3 scripts/backfill_missing_vectors.py --collection all            # dry run
    python3 scripts/backfill_missing_vectors.py --collection encyclicals --apply

Live gap as of 2026-08-20: 280 passages (encyclicals 169, apostolic-exhortations 102,
papal-documents 9) exist in `chunks` with no vector. They can only be found when a
user's literal keywords match — invisible to vector search and to HyDE, silently, with
no error surfaced anywhere.

DRY RUN IS THE DEFAULT. `--apply` is required to write.

WHY THIS EXISTS RATHER THAN A PIPELINE RUN
`run_collection.py --target search` would re-embed the whole collection with the
CURRENT writer, which emits 3072-dimension NAMED vectors. The live collection is
1536-dimension and unnamed, so that run either fails or forces a full corpus rebuild —
to repair 280 points. This is the narrow additive alternative: it writes only the
missing ids, reproduces the embedding input the live vectors were built with, and
touches no existing point.

It also never deletes. A Qdrant point with no `chunks` row is an orphan needing a
targeted delete, which is a different operation with different risks — this tool
reports that direction and refuses to act on it, the same way the payload reconcile
does.

SAFE TO RE-RUN. The set of missing ids is recomputed from both stores every time, so a
completed backfill reports nothing to do, and an interrupted one resumes.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backfill_vectors import (  # noqa: E402
    LIVE_EMBEDDING_DIMS, LIVE_EMBEDDING_MODEL, PassageRow, build_payload,
    legacy_prefix, missing_chunk_ids, to_passages,
)

# `config`, `openai`, `writers.*` are imported lazily inside the functions that use
# them so this module can be imported — and its argument handling tested — without
# production credentials.

# Every passage of the affected documents, in position order. The FULL document is
# required, not just the missing rows: `build_embedding_input` splices neighbour text,
# so a passage embedded without its neighbours present would get a different input than
# the one beside it that was written correctly.
_SQL = """
    SELECT c.id::text AS chunk_id, c.document_id::text AS document_id,
           d.title AS document_title, d.author, d.collection,
           c.content, c.reference, c.anchor, c.chapter_key, c.chapter_label,
           c.unit_label, c.position
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE d.collection = $1
    ORDER BY c.document_id, c.position
"""


async def qdrant_point_ids(client, collection: str) -> set[str]:
    from writers.qdrant import QDRANT_COLLECTION, collection_filter

    ids: set[str] = set()
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=collection_filter(collection),
            limit=1000, offset=offset,
            with_payload=False, with_vectors=False,
        )
        ids.update(str(point.id) for point in points)
        if offset is None:
            return ids


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed with the LIVE collection's dimensionality, explicitly.

    `dimensions=` is passed on purpose. The current pipeline omits it and takes
    text-embedding-3-large's native 3072; the live collection is 1536. Omitting it here
    would produce vectors Qdrant rejects — or worse, silently accepts into a differently
    shaped index if the collection is ever recreated.

    Retries the transient transport failures too, not just rate limits: a repair run
    against prod should not abort a collection because one request timed out.
    """
    import openai

    from config import settings

    client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    transient = (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError,
                 openai.InternalServerError)
    try:
        for attempt in range(4):
            try:
                response = await client.embeddings.create(
                    input=texts, model=LIVE_EMBEDDING_MODEL,
                    dimensions=LIVE_EMBEDDING_DIMS,
                )
                break
            except transient:
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)
        else:  # pragma: no cover - the loop always breaks or raises
            raise RuntimeError("unreachable")

        vectors = [r.embedding for r in sorted(response.data, key=lambda r: r.index)]
        # Vectors are matched to rows BY POSITION downstream, so a short response would
        # not merely drop the tail — it would shift every later vector onto the wrong
        # passage, writing plausible-looking points that are silently mispaired.
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"embedding response returned {len(vectors)} vectors for {len(texts)} "
                f"inputs; refusing to write positionally mismatched points"
            )
        return vectors
    finally:
        await client.close()


def plan(rows: list[PassageRow], missing: set[str]) -> list[tuple[PassageRow, str]]:
    """(row, embedding_input) for each missing chunk, with full-document context.

    Groups by document so each passage is embedded against its real neighbours, then
    emits only the missing ones.
    """
    from config import settings
    from writers.search_writer import build_embedding_input

    by_document: dict[str, list[PassageRow]] = {}
    for row in rows:
        by_document.setdefault(row.document_id, []).append(row)

    out: list[tuple[PassageRow, str]] = []
    for doc_rows in by_document.values():
        # Only documents we are actually writing into: an unrelated gap elsewhere in the
        # collection must not abort a repair we can safely make.
        if not any(row.chunk_id in missing for row in doc_rows):
            continue
        # `build_embedding_input` is called with the LIST INDEX, which is only the
        # passage's true position when positions are contiguous from 0. That holds for
        # every document today (verified: 0 gaps, 0 duplicates, 0 non-zero starts across
        # all 54,027 rows) but only by luck of the data — one deleted chunks row would
        # shift the neighbour window by one and produce a wrong-but-plausible embedding
        # input, the exact failure this module exists to avoid. Assert rather than trust.
        positions = [row.position for row in doc_rows]
        if positions != list(range(len(doc_rows))):
            raise RuntimeError(
                f"document {doc_rows[0].document_id} has non-contiguous positions "
                f"(first mismatch at index "
                f"{next(i for i, p in enumerate(positions) if i != p)}); "
                f"neighbour context cannot be reconstructed safely"
            )
        passages = to_passages(doc_rows)
        k_prev, k_next = settings.overlap_for(doc_rows[0].collection)
        for index, row in enumerate(doc_rows):
            if row.chunk_id not in missing:
                continue
            out.append((row, build_embedding_input(
                passages, index, k_prev, k_next, legacy_prefix(row))))
    return out


async def backfill_collection(client, conn, collection: str, apply: bool,
                              batch_size: int) -> tuple[int, int]:
    """Returns (missing_count, written_count)."""
    from qdrant_client.models import PointStruct

    from writers.qdrant import upsert_points

    rows = [PassageRow(**dict(r)) for r in await conn.fetch(_SQL, collection)]
    pg_ids = {row.chunk_id for row in rows}
    q_ids = await qdrant_point_ids(client, collection)

    missing = set(missing_chunk_ids(pg_ids, q_ids))
    orphaned = q_ids - pg_ids
    print(f"{collection:24} pg={len(pg_ids):>6} qdrant={len(q_ids):>6} "
          f"missing={len(missing):>4} orphaned={len(orphaned):>4}")
    if orphaned:
        print(f"    ⚠️  {len(orphaned)} Qdrant point(s) with no chunks row — NOT touched. "
              f"Those need a targeted delete by point id.")
    if not missing:
        print("    nothing to do")
        return 0, 0
    # Built before the dry-run return so a dry run exercises the whole construction
    # path — position guard included. It costs nothing: plan() makes no API call.
    work = plan(rows, missing)
    if not apply:
        print(f"    DRY RUN — {len(work)} point(s) would be embedded and upserted. "
              f"Re-run with --apply to write.")
        return len(missing), 0

    written = 0
    for start in range(0, len(work), batch_size):
        window = work[start:start + batch_size]
        vectors = await embed_texts([text for _, text in window])
        # Guarded HERE as well as inside embed_texts, because this is where vectors are
        # PAIRED TO ROWS BY POSITION: `zip` would silently truncate, shifting every
        # later vector onto the wrong passage and writing plausible mispaired points.
        # The check belongs at the pairing, not only at the fetch.
        if len(vectors) != len(window):
            raise RuntimeError(
                f"got {len(vectors)} vectors for {len(window)} passages; refusing to "
                f"write positionally mismatched points"
            )
        # Via writers.qdrant.upsert_points, not client.upsert directly: that helper
        # retries transient failures 4x with backoff, and it is the same one the writer
        # being replayed here uses. Bypassing it would be a gratuitous regression.
        await upsert_points(client, [
            # Unnamed vector and the deterministic passage id already in `chunks`
            # (verified equal to passage_id(document_id, anchor) for all 54,027 rows),
            # so a re-run overwrites rather than duplicating.
            PointStruct(id=row.chunk_id, vector=vector, payload=build_payload(row))
            for (row, _), vector in zip(window, vectors)
        ])
        written += len(window)
        print(f"      … {written}/{len(work)}", flush=True)
    return len(missing), written


async def main(collections: list[str], apply: bool, batch_size: int) -> int:
    from config import settings
    from writers.qdrant import get_client

    conn = await asyncpg.connect(settings.DATABASE_URL, statement_cache_size=0)
    exit_code = 0
    try:
        client = get_client()
        try:
            for collection in collections:
                try:
                    await backfill_collection(client, conn, collection, apply, batch_size)
                except Exception as exc:
                    print(f"    ✗ FAILED: {exc}")
                    print(f"      Re-run to resume — missing ids are recomputed from "
                          f"both stores, so written points are skipped.")
                    exit_code = 1
        finally:
            await client.close()
    finally:
        await conn.close()
    return exit_code


class ArgError(ValueError):
    """A rejected argument combination, raised so validation is testable."""


def resolve_args(collection: str, batch_size: int,
                 valid_collections: set[str]) -> list[str]:
    if batch_size < 1:
        raise ArgError(f"--batch-size must be >= 1 (got {batch_size}); a non-positive "
                       f"value silently writes nothing and reports success")
    if collection == "all":
        return sorted(valid_collections)
    if collection in valid_collections:
        return [collection]
    raise ArgError(f"unknown collection {collection!r}. "
                   f"Valid: {', '.join(sorted(valid_collections))}, or 'all'")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collection", required=True, help="collection name, or 'all'")
    ap.add_argument("--apply", action="store_true",
                    help="actually embed and write; omit for a dry run")
    ap.add_argument("--batch-size", type=int, default=100,
                    help="passages per embedding call (default 100)")
    args = ap.parse_args()

    from publication import SOURCE_ADAPTERS  # noqa: E402

    try:
        names = resolve_args(
            args.collection, args.batch_size, set(SOURCE_ADAPTERS)
        )
    except ArgError as exc:
        ap.error(str(exc))

    raise SystemExit(asyncio.run(main(names, args.apply, args.batch_size)))
