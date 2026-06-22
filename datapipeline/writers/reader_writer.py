"""Write clean documents + passages to Supabase (the reader + FTS store).

Does NOT populate content_embedding (retired — vectors live only in Qdrant).
chunks.id is the deterministic passage id so it matches the Qdrant point id.
"""
from __future__ import annotations

import json

import asyncpg

from model import Document
from identity import passage_id


async def clear_collection(pool: asyncpg.Pool, collection: str) -> None:
    """Delete a collection's chunks + documents before a clean re-ingest."""
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM chunks WHERE document_id IN "
            "(SELECT id FROM documents WHERE collection = $1)",
            collection,
        )
        await conn.execute("DELETE FROM documents WHERE collection = $1", collection)


async def write_document(pool: asyncpg.Pool, doc: Document) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO documents (id, collection, title, translation, author, year, metadata)
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::jsonb)
            ON CONFLICT (id) DO UPDATE SET
                title=EXCLUDED.title, translation=EXCLUDED.translation,
                author=EXCLUDED.author, year=EXCLUDED.year, metadata=EXCLUDED.metadata
            """,
            doc.id, doc.collection, doc.title, doc.translation or "",
            doc.author, doc.year, json.dumps(doc.metadata) if doc.metadata else None,
        )
        for p in doc.passages:
            pid = passage_id(doc.id, p.anchor)
            await conn.execute(
                """
                INSERT INTO chunks
                  (id, document_id, content, position, reference,
                   anchor, chapter_key, chapter_label, unit_label, metadata)
                VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                   content=EXCLUDED.content, position=EXCLUDED.position,
                   reference=EXCLUDED.reference, anchor=EXCLUDED.anchor,
                   chapter_key=EXCLUDED.chapter_key, chapter_label=EXCLUDED.chapter_label,
                   unit_label=EXCLUDED.unit_label, metadata=EXCLUDED.metadata
                """,
                pid, doc.id, p.content, p.position, p.reference,
                p.anchor, p.chapter_key, p.chapter_label, p.unit_label,
                json.dumps(p.metadata) if p.metadata else None,
            )
