"""Write clean documents + passages to Supabase (the reader + FTS store).

Does NOT populate content_embedding (retired — vectors live only in Qdrant).
chunks.id is the deterministic passage id so it matches the Qdrant point id.
"""
from __future__ import annotations

import json

import asyncpg

import contents
import reader_access
from model import Document
from identity import passage_id


async def clear_collection(conn: asyncpg.Connection, collection: str) -> None:
    """Delete a collection's chunks + documents before a clean re-ingest.

    DESTRUCTIVE BEYOND THIS COLLECTION. `retrievals`, `bookmarks`, `reading_progress`,
    `retrieval_labels` and `guest_trial_retrievals` all reference `chunks.id` with ON
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


async def prune_missing_documents(conn: asyncpg.Connection, collection: str,
                                  keep_ids: set[str]) -> int:
    """Delete documents absent from a complete collection build.

    Per-document chunk pruning cannot see a document the builder stopped returning.
    Leaving it behind makes Postgres disagree with both the build and the collection-wide
    Qdrant prune. The caller must use this only after a complete, non-limited build.
    """
    deleted = await conn.fetchval(
        """
        WITH deleted AS (
            DELETE FROM documents
            WHERE collection = $1 AND NOT (id = ANY($2::uuid[]))
            RETURNING 1
        )
        SELECT count(*) FROM deleted
        """,
        collection, list(keep_ids),
    )
    return int(deleted or 0)


async def write_document(conn: asyncpg.Connection, doc: Document,
                         prune: bool = True) -> int:
    """Atomically reconcile one document and return the stale chunk count.

    Existing positions are staged below zero before the upserts. Without that step, a
    newly split chunk can claim a position still occupied by the old identity and trip
    ``UNIQUE(document_id, position)`` before the stale row is pruned.

    The document's reader outline (chapter list and chunk_count, migration 0037) is
    rebuilt last, in the same transaction, so the API never reads an outline that
    disagrees with the chunks it describes. Its contents tree (migration 0040), when
    it has one, is replaced in the same transaction too.

    `reader_access` (migration 0041) is set from the rights inventory on every write,
    so a republish cannot reopen a text whose rights are not cleared (issue #265).
    """
    contents.check(doc)  # before the transaction: a broken tree writes nothing
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO documents
              (id, collection, title, translation, author, year, metadata, reader_access)
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::jsonb, $8)
            ON CONFLICT (id) DO UPDATE SET
                title=EXCLUDED.title, translation=EXCLUDED.translation,
                author=EXCLUDED.author, year=EXCLUDED.year, metadata=EXCLUDED.metadata,
                reader_access=EXCLUDED.reader_access
            """,
            doc.id, doc.collection, doc.title, doc.translation or "",
            doc.author, doc.year, json.dumps(doc.metadata) if doc.metadata else None,
            reader_access.access_for_document(doc),
        )
        await conn.execute(
            "UPDATE chunks SET position = -position - 1 WHERE document_id = $1::uuid",
            doc.id,
        )
        pruned = await prune_missing_chunks(conn, doc) if prune else 0
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
        await conn.execute("SELECT refresh_document_outline($1::uuid)", doc.id)
        await write_contents(conn, doc)
        return pruned


async def contents_table_exists(conn: asyncpg.Connection) -> bool:
    """Whether the database has migration 0040's document_contents table."""
    return bool(await conn.fetchval(
        "SELECT to_regclass('public.document_contents') IS NOT NULL"))


async def write_contents(conn: asyncpg.Connection, doc: Document) -> None:
    """Replace the document's contents tree rows (migration 0040) with `doc.contents`.

    Always deletes first, so a document whose adapter stops emitting a tree loses the
    old one. On a database without 0040 a document with no tree writes nothing, and one
    with a tree is refused, so a tree is never silently dropped (the publication runner
    checks this before its first write; this is the backstop). Call inside the
    transaction that writes the document's chunks.
    """
    if not await contents_table_exists(conn):
        if doc.contents is not None:
            raise RuntimeError(
                f"document {doc.id} has a contents tree, but the database has no "
                "document_contents table; apply migration 0040 first")
        return
    await conn.execute("DELETE FROM document_contents WHERE document_id = $1::uuid", doc.id)
    if doc.contents is None:
        return
    # Pre-order, so each parent row exists before the rows that reference it.
    await conn.executemany(
        """
        INSERT INTO document_contents
          (document_id, ordinal, parent_ordinal, depth, node_key, kind, label,
           short_label, chapter_key, anchor, range_label)
        VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """,
        [(doc.id, r.ordinal, r.parent_ordinal, r.depth, r.node_key, r.kind, r.label,
          r.short_label, r.chapter_key, r.anchor, r.range_label)
         for r in contents.flatten(doc.contents)],
    )


async def reader_access_column_exists(conn: asyncpg.Connection) -> bool:
    """Whether the database has migration 0041's documents.reader_access column."""
    return bool(await conn.fetchval(
        """SELECT EXISTS (SELECT 1 FROM information_schema.columns
                          WHERE table_schema = 'public' AND table_name = 'documents'
                            AND column_name = 'reader_access')"""
    ))
