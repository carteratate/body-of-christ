"""Run one collection through both pipelines: parse → reader (Supabase) + search (Qdrant).

    cd datapipeline && python3 run_collection.py --collection church-fathers --target both --clean
"""
from __future__ import annotations

import argparse
import asyncio

import asyncpg

from config import settings
from model import Document
from writers import reader_writer
from writers import search_writer
from identity import passage_id
from writers.qdrant import (
    delete_collection_points, ensure_collection, get_client, prune_missing_points,
)
from ingest import (church_fathers, summa, bible, catechism, medieval,
                    encyclicals, councils, canon_law,
                    apostolic_exhortations, papal_documents)

BUILDERS = {
    "church-fathers": church_fathers.build_all,
    "summa": lambda: [summa.build_document()],
    "bible": bible.build_documents,
    "catechism": lambda: [catechism.build_document()],
    "medieval": medieval.build_documents,
    "encyclicals": encyclicals.build_documents,
    "apostolic-exhortations": apostolic_exhortations.build_documents,
    "papal-documents": papal_documents.build_documents,
    "councils": councils.build_documents,
    "canon-law": canon_law.build_documents,
}


# A rebuild is expected to move a few passages. Losing a large share of them means the
# build broke — a source that failed to download, an adapter that stopped matching its
# markup — and pruning to match would turn that into deleted rows and deleted vectors.
# Refuse instead, and let the operator look.
_MAX_SHRINK = 0.10


async def _refuse_if_build_collapsed(conn, collection: str, built: int, limit: int | None) -> None:
    if limit:
        return          # a deliberately partial build; the comparison is meaningless
    live = await conn.fetchval(
        """
        SELECT count(*) FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE d.collection = $1
        """,
        collection,
    ) or 0
    if live and built < live * (1 - _MAX_SHRINK):
        raise SystemExit(
            f"REFUSING: the build produced {built} passages against {live} live rows "
            f"({(1 - built / live):.0%} fewer). Pruning to match would delete the "
            f"difference from Postgres and Qdrant. Check the source files and the "
            f"adapter, or pass --limit to build a subset deliberately."
        )


async def run(collection: str, target: str, clean: bool, limit: int | None,
              wipe: bool = False) -> None:
    docs: list[Document] = BUILDERS[collection]()
    if limit:
        docs = docs[:limit]
    built = sum(len(d.passages) for d in docs)
    print(f"{collection}: {len(docs)} documents, {built} passages")

    conn = await asyncpg.connect(settings.DATABASE_URL)
    qdrant = get_client()
    try:
        await _refuse_if_build_collapsed(conn, collection, built, limit)
        await ensure_collection(qdrant)
        if target in ("reader", "both"):
            # Upsert by default. `clear_collection` cascades through retrievals,
            # bookmarks and reading_progress, so a routine re-ingest would destroy user
            # data even though the rebuild produces the same chunk ids.
            if wipe:
                print("  reader: WIPING collection (cascades to user data)")
                await reader_writer.clear_collection(conn, collection)
            pruned = 0
            for d in docs:
                await reader_writer.write_document(conn, d)
                if not wipe:
                    pruned += await reader_writer.prune_missing_chunks(conn, d)
            print(f"  reader: wrote {len(docs)} documents to Supabase"
                  + (f" ({pruned} stale chunk(s) pruned)" if pruned else ""))
        if target in ("search", "both"):
            if clean:
                await delete_collection_points(qdrant, collection)
                print(f"  search: deleted old '{collection}' Qdrant points")
            for d in docs:
                await search_writer.write_document(qdrant, d)
            # Upsert alone leaves a superseded point behind forever, still searchable,
            # while the pipeline's Postgres lookup for it returns nothing. `--clean`
            # already emptied the collection, so there is nothing stale to find.
            orphans = 0
            if not clean:
                keep = {passage_id(d.id, p.anchor) for d in docs for p in d.passages}
                orphans = await prune_missing_points(qdrant, collection, keep)
            print(f"  search: embedded + upserted points to Qdrant"
                  + (f" ({orphans} orphaned point(s) deleted)" if orphans else ""))
    finally:
        await conn.close()
        await qdrant.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True, choices=list(BUILDERS))
    ap.add_argument("--target", default="both", choices=["reader", "search", "both"])
    ap.add_argument("--clean", action="store_true", help="delete the collection's Qdrant points first")
    ap.add_argument("--wipe-reader", action="store_true",
                    help="DELETE the collection's Supabase rows before writing. Cascades "
                         "to retrievals, bookmarks and reading_progress. Omit to upsert, "
                         "which keeps chunk ids and prunes only what the build dropped.")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    asyncio.run(run(a.collection, a.target, a.clean, a.limit, a.wipe_reader))
