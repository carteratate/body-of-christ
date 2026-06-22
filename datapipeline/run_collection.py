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
from writers.qdrant import get_client, ensure_collection, delete_collection_points
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


async def run(collection: str, target: str, clean: bool, limit: int | None) -> None:
    docs: list[Document] = BUILDERS[collection]()
    if limit:
        docs = docs[:limit]
    print(f"{collection}: {len(docs)} documents, "
          f"{sum(len(d.passages) for d in docs)} passages")

    pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=5,
                                     statement_cache_size=0)
    qdrant = get_client()
    try:
        await ensure_collection(qdrant)
        if target in ("reader", "both"):
            await reader_writer.clear_collection(pool, collection)
            for d in docs:
                await reader_writer.write_document(pool, d)
            print(f"  reader: wrote {len(docs)} documents to Supabase")
        if target in ("search", "both"):
            if clean:
                await delete_collection_points(qdrant, collection)
                print(f"  search: deleted old '{collection}' Qdrant points")
            for d in docs:
                await search_writer.write_document(qdrant, d)
            print(f"  search: embedded + upserted points to Qdrant")
    finally:
        await pool.close()
        await qdrant.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True, choices=list(BUILDERS))
    ap.add_argument("--target", default="both", choices=["reader", "search", "both"])
    ap.add_argument("--clean", action="store_true", help="delete the collection's Qdrant points first")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    asyncio.run(run(a.collection, a.target, a.clean, a.limit))
