"""One-time migration: copy chunk embeddings from Supabase/pgvector to Qdrant.

DEPRECATED: superseded by the dual pipeline (datapipeline/writers/search_writer.py
writes embeddings directly to Qdrant). Kept for reference only.

Run from services/api/:
    python scripts/migrate_to_qdrant.py

Requires QDRANT_URL, QDRANT_API_KEY, and DATABASE_URL in services/api/.env.
Safe to re-run: upsert is idempotent by chunk UUID.
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, HnswConfigDiff, PayloadSchemaType, PointStruct, VectorParams

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

QDRANT_COLLECTION = "chunks"
EMBEDDING_DIMS = 1536
BATCH_SIZE = 200

# Load .env from the services/api directory
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)


def parse_pgvector(s: str) -> list[float]:
    """Parse pgvector text format '[f1,f2,...]' to list of floats."""
    return json.loads(s)


async def ensure_collection(client: AsyncQdrantClient) -> None:
    exists = await client.collection_exists(QDRANT_COLLECTION)
    if exists:
        info = await client.get_collection(QDRANT_COLLECTION)
        logger.info(
            "Collection '%s' already exists with %d points — will upsert (safe to re-run)",
            QDRANT_COLLECTION,
            info.points_count,
        )
        return

    await client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=EMBEDDING_DIMS, distance=Distance.COSINE),
        hnsw_config=HnswConfigDiff(m=16, ef_construct=64),
    )
    await client.create_payload_index(
        collection_name=QDRANT_COLLECTION,
        field_name="collection",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    logger.info("Created Qdrant collection '%s' with payload index on 'collection'", QDRANT_COLLECTION)


async def fetch_chunks(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    logger.info("Fetching chunks with embeddings from Supabase...")
    rows = await pool.fetch(
        """
        SELECT
            c.id::text          AS chunk_id,
            c.content,
            c.reference,
            c.content_embedding::text AS embedding,
            d.id::text          AS document_id,
            d.title             AS document_title,
            d.author,
            d.collection
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.content_embedding IS NOT NULL
        ORDER BY c.id
        """
    )
    logger.info("Fetched %d chunks", len(rows))
    return rows


def build_point(row: asyncpg.Record) -> PointStruct:
    vec = parse_pgvector(row["embedding"])
    return PointStruct(
        id=row["chunk_id"],
        vector=vec,
        payload={
            "collection": row["collection"],
            "document_id": row["document_id"],
            "document_title": row["document_title"],
            "author": row["author"],
            "content": row["content"],
            "reference": row["reference"],
        },
    )


async def upsert_in_batches(client: AsyncQdrantClient, rows: list[asyncpg.Record]) -> None:
    total = len(rows)
    upserted = 0
    errors = 0

    for batch_start in range(0, total, BATCH_SIZE):
        batch_rows = rows[batch_start : batch_start + BATCH_SIZE]
        points: list[PointStruct] = []
        for row in batch_rows:
            try:
                points.append(build_point(row))
            except Exception as exc:
                logger.warning("Skipping chunk %s — build_point failed: %s", row["chunk_id"], exc)
                errors += 1

        if points:
            await client.upsert(collection_name=QDRANT_COLLECTION, points=points, wait=True)
            upserted += len(points)

        logger.info(
            "Progress: %d / %d upserted (batch %d–%d)",
            upserted, total, batch_start + 1, min(batch_start + BATCH_SIZE, total),
        )

    logger.info("Migration complete: %d upserted, %d skipped due to errors", upserted, errors)


async def verify(client: AsyncQdrantClient, expected: int) -> None:
    info = await client.get_collection(QDRANT_COLLECTION)
    actual = info.points_count
    if actual >= expected:
        logger.info("Verification passed: %d points in Qdrant (expected %d)", actual, expected)
    else:
        logger.error(
            "Verification FAILED: %d points in Qdrant but expected %d — re-run to complete",
            actual, expected,
        )
        sys.exit(1)


async def main() -> None:
    qdrant_url = os.environ.get("QDRANT_URL")
    qdrant_api_key = os.environ.get("QDRANT_API_KEY")
    database_url = os.environ.get("DATABASE_URL")

    if not qdrant_url or not qdrant_api_key or not database_url:
        logger.error("Missing required env vars: QDRANT_URL, QDRANT_API_KEY, DATABASE_URL")
        sys.exit(1)

    qdrant = AsyncQdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5, statement_cache_size=0)

    try:
        await ensure_collection(qdrant)
        rows = await fetch_chunks(pool)
        if not rows:
            logger.warning("No chunks found with embeddings — nothing to migrate")
            return
        await upsert_in_batches(qdrant, rows)
        await verify(qdrant, len(rows))
    finally:
        await pool.close()
        await qdrant.close()


if __name__ == "__main__":
    asyncio.run(main())
