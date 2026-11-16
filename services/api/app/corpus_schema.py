"""Which corpus-cleanup objects (migration 0042, and 0044's `documents.form`) the
database has (items 2.2b and 2.4a, issue #330).

The API deploys before and after 0042 is applied. Every query that reads a 0042 column
or table asks `current()` first and builds its SQL from the answer, so on a database
without 0042 the SQL is today's. `current()` is one `information_schema` query, cached
for five minutes, run once at startup and lazily after that.

A query that fails with `UndefinedColumnError` or `UndefinedTableError` (the schema
changed under the cache) calls `invalidate()` and retries once with `LEGACY`, the
answer for a database without 0042: `run_with_fallback` does both.

Under `CORPUS_READ_SCHEMA=staging` the probe looks at the schemas the session resolves
(`current_schemas`), so it describes what unqualified queries read.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import asyncpg

from app.db import get_pool

logger = logging.getLogger(__name__)

_TTL_SECONDS = 300.0


@dataclass(frozen=True)
class CorpusSchema:
    retired: bool       # chunks.retired_at and documents.retired_at exist
    searchable: bool    # chunks.searchable exists
    # documents.genre ... superseded_note, and the passage fields chunks.language,
    # note, passage_author, work_key, superseded_by and voice. All come from 0042.
    facts: bool
    works: bool         # document_works exists
    tombstones: bool    # corpus_tombstones exists
    redirects: bool     # corpus_redirects exists
    # documents.form (0044, issue #330), a papal document's chancery form. Read only
    # beside `facts`; a database without 0044 sends no form.
    form: bool = False

    def visible(self, alias: str) -> str:
        """`AND <alias>.retired_at IS NULL`, or "" without 0042."""
        return f" AND {alias}.retired_at IS NULL" if self.retired else ""

    def searchable_sql(self, chunk: str, document: str) -> str:
        """The predicates that keep a passage out of search (item 2.2b): not searchable,
        retired, or in a retired document. "" without 0042."""
        sql = f" AND {chunk}.searchable" if self.searchable else ""
        return sql + self.visible(chunk) + self.visible(document)

    @property
    def lifecycle(self) -> bool:
        """Whether retired rows can exist and be explained: anything else is current."""
        return self.retired and (self.tombstones or self.redirects)


LEGACY = CorpusSchema(retired=False, searchable=False, facts=False, works=False,
                      tombstones=False, redirects=False)

_FACT_COLUMNS = {
    "documents": ("genre", "issuer", "issuer_label", "date_display", "certainty",
                  "attribution_note", "notes", "source_credit", "superseded_by",
                  "superseded_note"),
    "chunks": ("language", "note", "passage_author", "work_key", "superseded_by",
               "voice"),
}

_PROBE_SQL = """
    SELECT table_name::text AS table_name, column_name::text AS column_name
    FROM information_schema.columns
    WHERE table_schema = ANY(current_schemas(false))
      AND table_name IN ('documents', 'chunks', 'document_works', 'corpus_tombstones',
                         'corpus_redirects')
"""

_cached: CorpusSchema | None = None
_cached_at = 0.0


def _from_columns(rows) -> CorpusSchema:
    columns: dict[str, set[str]] = {}
    for r in rows:
        columns.setdefault(r["table_name"], set()).add(r["column_name"])
    docs, chunks = columns.get("documents", set()), columns.get("chunks", set())
    return CorpusSchema(
        retired="retired_at" in docs and "retired_at" in chunks,
        searchable="searchable" in chunks,
        facts=(set(_FACT_COLUMNS["documents"]) <= docs
               and set(_FACT_COLUMNS["chunks"]) <= chunks),
        works="document_works" in columns,
        tombstones="corpus_tombstones" in columns,
        redirects="corpus_redirects" in columns,
        form="form" in docs,
    )


async def probe(conn=None) -> CorpusSchema:
    """Read the schema now and cache it. `conn` is a connection or pool."""
    global _cached, _cached_at
    conn = conn or get_pool()
    if conn is None:
        return LEGACY
    schema = _from_columns(await conn.fetch(_PROBE_SQL))
    if schema != _cached:
        logger.info("corpus schema: %s", schema)
    _cached, _cached_at = schema, time.monotonic()
    return schema


async def current(conn=None) -> CorpusSchema:
    """The cached schema, probed again after the TTL. A failed probe answers `LEGACY`
    for this call without caching it, so every query falls back to today's SQL."""
    if _cached is not None and time.monotonic() - _cached_at < _TTL_SECONDS:
        return _cached
    try:
        return await probe(conn)
    except Exception as exc:
        logger.warning("corpus schema probe failed (%s); reading as before 0042",
                       exc.__class__.__name__)
        return LEGACY


def invalidate() -> None:
    global _cached
    _cached = None


T = TypeVar("T")


async def run_with_fallback(fn: Callable[[CorpusSchema], Awaitable[T]], conn=None) -> T:
    """`fn(current schema)`; when it fails on a missing 0042 object, invalidate the
    cache and run `fn(LEGACY)` once."""
    schema = await current(conn)
    try:
        return await fn(schema)
    except (asyncpg.UndefinedColumnError, asyncpg.UndefinedTableError) as exc:
        if schema == LEGACY:
            raise
        logger.warning("corpus schema changed (%s); retrying as before 0042", exc)
        invalidate()
        return await fn(LEGACY)
