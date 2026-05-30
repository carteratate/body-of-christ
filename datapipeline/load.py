"""
Async database utility functions for the Body of Christ data pipeline.

Uses asyncpg directly (no ORM). Provides a module-level connection pool
singleton plus upsert helpers for documents and chunks.
"""
from __future__ import annotations

import asyncpg

from config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=1,
            max_size=5,
        )
    return _pool


async def close_pool() -> None:
    """Close the shared connection pool if it has been opened."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def upsert_document(
    pool: asyncpg.Pool,
    collection: str,
    title: str,
    author: str | None = None,
    year: int | None = None,
    metadata: dict | None = None,
) -> str:
    """
    Insert a document row or return the ID of the existing one.

    Upserts on the (collection, title) unique constraint.
    Returns the document UUID as a string.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO documents (collection, title, author, year, metadata)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (collection, title)
        DO UPDATE SET
            author   = EXCLUDED.author,
            year     = EXCLUDED.year,
            metadata = EXCLUDED.metadata
        RETURNING id
        """,
        collection,
        title,
        author,
        year,
        metadata or {},
    )
    return str(row["id"])


async def upsert_chunk(
    pool: asyncpg.Pool,
    document_id: str,
    content: str,
    position: int,
    reference: str | None = None,
) -> str:
    """
    Insert a chunk row if one does not already exist for (document_id, position).

    Does NOT populate content_embedding — that is handled by embed.py.
    Returns the chunk UUID as a string.
    """
    row = await pool.fetchrow(
        """
        INSERT INTO chunks (document_id, content, position, reference)
        VALUES ($1::uuid, $2, $3, $4)
        ON CONFLICT (document_id, position)
        DO UPDATE SET
            content   = EXCLUDED.content,
            reference = EXCLUDED.reference
        RETURNING id
        """,
        document_id,
        content,
        position,
        reference,
    )
    return str(row["id"])
