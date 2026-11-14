"""Full-text search per collection via Supabase/Postgres."""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Literal

import asyncpg

from app import corpus_schema
from app.config import settings
from app.db import POOL_ACQUIRE_TIMEOUT_SECONDS, get_pool
from app.rag.steps import degradation

logger = logging.getLogger(__name__)

_SQL_TEMPLATE = """
    SELECT c.id::text AS id, c.content, c.reference, c.anchor, c.chapter_key, c.position,
           c.annotation, c.unit_label{voice}, c.document_id::text AS document_id,
           d.title AS document_title, d.author, d.collection
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE d.collection = $1
      AND c.search_vector @@ plainto_tsquery('english', $2){searchable}
    ORDER BY ts_rank(c.search_vector, plainto_tsquery('english', $2)) DESC
    LIMIT $3
"""


# How the question becomes a full-text match (issue #233), a per-pipeline axis
# (`RetrievalConfig.fts_mode`):
#   "and"       — `plainto_tsquery`, which ANDs every lexeme. A passage must hold all of
#                 a question's terms, so most questions match nothing.
#   "min_match" — OR the same lexemes and keep passages holding at least ⌈n/2⌉ of the n
#                 distinct ones, most first. If none reaches ⌈n/2⌉, the passages
#                 holding the most terms are kept instead, down to plain OR.
FtsMode = Literal["and", "min_match"]
FTS_MODES: tuple[FtsMode, ...] = ("and", "min_match")

# Each distinct lexeme of the question becomes its own one-term tsquery, quoted for
# tsquery input so the lexeme is taken as written and not parsed or stemmed again.
# The lexemes are `to_tsvector`'s, which are `plainto_tsquery`'s without repeats: the
# two share one parser and dictionary chain.
#
# Which passages: with three or more terms the threshold is at least two, so the GIN
# index is asked only for passages holding some pair of terms (`pairs`). Without that,
# a common term ("god" alone matches 27,000 church-fathers passages) made every
# one-term passage a heap fetch, and the query took ~600 ms instead of ~150. With one
# or two terms, or when no passage holds a pair (the fallback), the plain OR runs
# instead (`singles`); `NOT EXISTS` gates it, so it costs nothing otherwise. Past 40
# terms (780 pairs; a question may run to 1,000 characters) the plain OR runs too.
#
# Terms matched: the vector's length less its length with the query's lexemes deleted,
# one pass over each candidate. Only the passages that pass the threshold are ranked:
# distinct terms matched, then today's `ts_rank` against the AND query, so a passage
# holding every term ranks exactly where "and" puts it and today's list is always this
# list's head (n <= 2 included), then `ts_rank` against the OR query, to order passages
# the AND rank scores alike. The tsqueries are InitPlan parameters, which is what lets
# the GIN index on search_vector serve the match.
_MIN_MATCH_SQL_TEMPLATE = r"""
    WITH terms AS (
        SELECT array_agg(lexeme) AS lexemes,
               array_agg(
                   ('''' || replace(replace(lexeme, '\', '\\'), '''', '''''') || '''')::tsquery
               ) AS each_term
        FROM unnest(tsvector_to_array(to_tsvector('english', $2))) AS lexeme
    ),
    query AS (
        SELECT lexemes, cardinality(lexemes) AS term_count,
               array_to_string(each_term, ' | ')::tsquery AS any_term,
               (SELECT string_agg(format('(%s & %s)', a, b), ' | ')
                FROM unnest(each_term) WITH ORDINALITY AS x(a, i)
                JOIN unnest(each_term) WITH ORDINALITY AS y(b, j) ON i < j)::tsquery
                   AS any_pair
        FROM terms
    ),
    pairs AS MATERIALIZED (
        SELECT c.id, c.search_vector
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.collection = $1
          AND (SELECT term_count FROM query) BETWEEN 3 AND 40
          AND c.search_vector @@ (SELECT any_pair FROM query){searchable}
    ),
    singles AS (
        SELECT c.id, c.search_vector
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.collection = $1
          AND NOT EXISTS (SELECT 1 FROM pairs)
          AND c.search_vector @@ (SELECT any_term FROM query){searchable}
    ),
    matched AS (
        SELECT m.id, m.search_vector, q.term_count,
               length(m.search_vector) - length(ts_delete(m.search_vector, q.lexemes))
                   AS terms_matched
        FROM (SELECT * FROM pairs UNION ALL SELECT * FROM singles) m CROSS JOIN query q
    ),
    ranked AS (
        SELECT id, terms_matched,
               ts_rank(search_vector, plainto_tsquery('english', $2)) AS all_rank,
               ts_rank(search_vector, (SELECT any_term FROM query)) AS any_rank
        FROM (SELECT *, max(terms_matched) OVER () AS most_matched FROM matched) m
        WHERE terms_matched >= LEAST(ceil(term_count / 2.0), most_matched)
        ORDER BY terms_matched DESC, all_rank DESC, any_rank DESC
        LIMIT $3
    )
    SELECT c.id::text AS id, c.content, c.reference, c.anchor, c.chapter_key, c.position,
           c.annotation, c.unit_label{voice}, c.document_id::text AS document_id,
           d.title AS document_title, d.author, d.collection
    FROM ranked r
    JOIN chunks c ON c.id = r.id
    JOIN documents d ON c.document_id = d.id
    ORDER BY r.terms_matched DESC, r.all_rank DESC, r.any_rank DESC
"""


def build_sql(schema: corpus_schema.CorpusSchema, mode: FtsMode = "and") -> str:
    """Today's SQL without 0042, byte for byte; with it, only searchable live rows, and
    each row's `voice` (2.4d), so a candidate found only by keyword search carries it.

    `mode` "and" is that SQL unchanged; "min_match" is the query described above."""
    voice = ", c.voice" if schema.facts else ""
    searchable = schema.searchable_sql("c", "d")
    if mode == "and":
        return _SQL_TEMPLATE.format(voice=voice, searchable=searchable)
    if mode == "min_match":
        return _MIN_MATCH_SQL_TEMPLATE.format(voice=voice, searchable=searchable)
    raise ValueError(f"unknown FTS mode {mode!r}")


_TRANSIENT_CONNECTION_ERRORS = (
    asyncpg.PostgresConnectionError,
    ConnectionError,
    TimeoutError,
)


async def _search_fts(
    collection: str, query_text: str, limit: int, mode: FtsMode = "and",
) -> list[dict]:
    """Search one collection, reacquiring once after a transient pooler failure.

    A long judge/reranker call can leave the DB pool idle long enough for Supabase's
    pooler to retire its socket, so the first fetch, or the reconnect asyncpg makes
    inside acquire, can fail. asyncpg discards a connection that failed mid-query; the
    retry therefore runs on a different one. Semantic SQL and programming errors are
    deliberately not retried.

    Waiting for a connection is bounded by POOL_ACQUIRE_TIMEOUT_SECONDS. A pool still
    exhausted after that is not retried: a second wait would only double the delay.
    The TimeoutError drops this collection's lexical path (see run()).
    """
    for attempt in range(2):
        pool = get_pool()
        if pool is None:
            degradation.record(
                "retrieve_fts", "pool_unavailable", "path_omitted",
                scope=collection,
            )
            return []
        try:
            conn = await pool.acquire(timeout=POOL_ACQUIRE_TIMEOUT_SECONDS)
        except TimeoutError:
            raise
        except _TRANSIENT_CONNECTION_ERRORS:
            if attempt:
                raise
            await asyncio.sleep(0.15 + random.random() * 0.20)
            continue
        try:
            rows = await corpus_schema.run_with_fallback(
                lambda schema: conn.fetch(
                    build_sql(schema, mode), collection, query_text, limit,
                ),
                conn,
            )
        except _TRANSIENT_CONNECTION_ERRORS:
            if attempt:
                raise
        else:
            if attempt:
                logger.info("retrieve_fts: %s recovered on fresh connection", collection)
            return [dict(r) for r in rows]
        finally:
            await pool.release(conn)
        # Small independent jitter prevents every collection from immediately
        # stampeding the pool for replacement sockets.
        await asyncio.sleep(0.15 + random.random() * 0.20)
    raise AssertionError("unreachable")


async def run(
    query: str,
    collections: list[str],
    quota: int,
    user_id: str | None = None,
    k: int | None = None,
    mode: FtsMode = "and",
) -> dict[str, list[dict]]:
    """Run FTS for all collections.

    user_id is accepted but unused (retained for caller compatibility).
    A collection with no match is left out of the output, as before, and logged, so
    how often the lexical path is empty can be read from the logs (#233).
    """
    n = k if k is not None else quota * settings.candidate_multiplier

    results = await asyncio.gather(
        *[_search_fts(col, query, n, mode) for col in collections],
        return_exceptions=True,
    )
    output: dict[str, list[dict]] = {}
    for col, result in zip(collections, results):
        if isinstance(result, BaseException):
            logger.warning("retrieve_fts: %s failed: %s", col, result)
            degradation.record(
                "retrieve_fts", type(result).__name__, "path_omitted",
                scope=col, details={"message": str(result)[:300]},
            )
        elif result:
            output[col] = result
        else:
            logger.info(
                "retrieve_fts: %s returned 0 rows", col,
                extra={"collection": col, "fts_mode": mode, "fts_rows": 0},
            )
    return output
