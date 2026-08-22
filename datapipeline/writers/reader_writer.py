"""Write clean documents + passages to Supabase (the reader + FTS store).

Does NOT populate content_embedding (retired — vectors live only in Qdrant).
chunks.id is the deterministic passage id so it matches the Qdrant point id.
"""
from __future__ import annotations

import json

import asyncpg

from model import Document
from identity import passage_id


async def clear_collection(conn: asyncpg.Connection, collection: str) -> None:
    """Delete a collection's chunks + documents before a clean re-ingest.

    DESTRUCTIVE BEYOND THIS COLLECTION. `retrievals`, `bookmarks`, `reading_progress`,
    `chunk_feedback` and `guest_trial_retrievals` all reference `chunks.id` with ON
    DELETE CASCADE, so this removes user data that the re-insert never restores — even
    when the rebuild produces byte-identical chunk ids, which for a deterministic
    re-ingest it usually does.

    Prefer `prune_missing_chunks` after `write_document`: the upsert path keeps ids
    stable and touches only rows the new build no longer produces.
    """
    await conn.execute(
        "DELETE FROM chunks WHERE document_id IN "
        "(SELECT id FROM documents WHERE collection = $1)",
        collection,
    )
    await conn.execute("DELETE FROM documents WHERE collection = $1", collection)


async def prune_missing_chunks(conn: asyncpg.Connection, doc: Document) -> int:
    """Delete only this document's chunks that the current build no longer produces.

    The non-destructive counterpart to `clear_collection`. Everything the rebuild still
    emits keeps its id — and therefore its bookmarks, retrievals and reading progress —
    because `write_document` upserts on `chunks.id`. Only genuinely orphaned rows are
    removed, and those cascade because the passage they point at no longer exists.

    Returns the number of rows deleted, so a caller can refuse to proceed when a build
    unexpectedly drops a large share of a document.
    """
    keep = [passage_id(doc.id, p.anchor) for p in doc.passages]
    deleted = await conn.fetchval(
        """
        WITH deleted AS (
            DELETE FROM chunks
            WHERE document_id = $1::uuid AND NOT (id = ANY($2::uuid[]))
            RETURNING 1
        )
        SELECT count(*) FROM deleted
        """,
        doc.id, keep,
    )
    return int(deleted or 0)


async def write_document(conn: asyncpg.Connection, doc: Document) -> None:
    async with conn.transaction():
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
