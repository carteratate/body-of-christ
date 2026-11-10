"""Corpus cleanup 2.2b: search skips passages that are not searchable or retired.

Without 0042 the full-text, stitch and position SQL is today's, byte for byte. With it,
full-text search, Summa stitching and the position lookup leave out a passage marked
`searchable = false`, a retired passage and a passage of a retired document, checked
against a real database migrated through 0043.

The acceptance checks are docs/corpus-cleanup/P2-P3-schema-reader-policy.md, item 2.2b.
"""
import contextlib
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from app import corpus_schema
from app.db import _init_connection
from app.rag.pipelines import runner
from app.rag.pipelines.registry import PIPELINES
from app.rag.steps import fetch_context, fetch_positions, retrieve_fts, stitch
from app.rag.steps.types import RankedChunk
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)

ALL = corpus_schema.CorpusSchema(True, True, True, True, True, True)

# The SQL before 2.2b, copied from master at 613075b.
TODAY_FTS = """
    SELECT c.id::text AS id, c.content, c.reference, c.anchor, c.chapter_key, c.position,
           c.annotation, c.unit_label, c.document_id::text AS document_id,
           d.title AS document_title, d.author, d.collection
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE d.collection = $1
      AND c.search_vector @@ plainto_tsquery('english', $2)
    ORDER BY ts_rank(c.search_vector, plainto_tsquery('english', $2)) DESC
    LIMIT $3
"""
TODAY_STITCH = """
    SELECT c.id::text AS chunk_id, c.content, c.reference, c.anchor, c.chapter_key,
           c.position, c.unit_label, c.document_id::text AS document_id,
           d.title AS document_title, d.author, d.collection
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.chapter_key = ANY($1::text[])
      AND d.collection = 'summa'
    ORDER BY c.document_id, c.chapter_key, c.position
"""
TODAY_POSITIONS = (
    "SELECT id::text, position, annotation, chapter_key, unit_label "
    "FROM chunks WHERE id = ANY($1::uuid[])"
)


def test_without_0042_the_sql_is_todays():
    assert retrieve_fts.build_sql(corpus_schema.LEGACY) == TODAY_FTS
    assert fetch_context.build_sql(corpus_schema.LEGACY) == TODAY_STITCH
    assert fetch_positions.build_sql(corpus_schema.LEGACY) == TODAY_POSITIONS


def test_with_0042_the_sql_skips_unsearchable_and_retired_rows():
    for sql in (retrieve_fts.build_sql(ALL), fetch_context.build_sql(ALL)):
        assert "AND c.searchable" in sql
        assert "AND c.retired_at IS NULL" in sql
        assert "AND d.retired_at IS NULL" in sql
    positions = fetch_positions.build_sql(ALL)
    assert ("NOT (TRUE AND c.searchable AND c.retired_at IS NULL AND d.retired_at IS NULL)"
            " AS hidden") in positions
    # The lookup still returns hidden rows, so they are told apart from orphans.
    assert "WHERE c.id = ANY($1::uuid[])" in positions


DOC = "00000000-0000-0000-0000-00000000e001"
GONE_DOC = "00000000-0000-0000-0000-00000000e002"
SUMMA = "00000000-0000-0000-0000-00000000e003"
SHOWN = "00000000-0000-0000-0000-0000000000f1"
UNSEARCHABLE = "00000000-0000-0000-0000-0000000000f2"
RETIRED = "00000000-0000-0000-0000-0000000000f3"
IN_RETIRED_DOC = "00000000-0000-0000-0000-0000000000f4"
# Three Summa articles, each an objection and its determination: hidden as not
# searchable (a1), retired (a2), and shown (a3, the control).
OBJ_A1 = "00000000-0000-0000-0000-0000000000a1"
DET_A1 = "00000000-0000-0000-0000-0000000000d1"
OBJ_A2 = "00000000-0000-0000-0000-0000000000a2"
DET_A2 = "00000000-0000-0000-0000-0000000000d2"
OBJ_A3 = "00000000-0000-0000-0000-0000000000a3"
DET_A3 = "00000000-0000-0000-0000-0000000000d3"

SEED = f"""
    INSERT INTO documents (id, collection, title, author, metadata) VALUES
      ('{DOC}', 'church-fathers', 'On Grace', 'Augustine', '{{}}'),
      ('{GONE_DOC}', 'church-fathers', 'Retired Work', 'Someone', '{{}}'),
      ('{SUMMA}', 'summa', 'Summa Theologiae', 'Thomas Aquinas', '{{}}');
    INSERT INTO chunks (id, document_id, position, anchor, chapter_key, content,
                        searchable, retired_at) VALUES
      ('{SHOWN}', '{DOC}', 0, 'p1', 'c1', 'grace abounds', true, NULL),
      ('{UNSEARCHABLE}', '{DOC}', 1, 'p2', 'c1', 'grace in Latin', false, NULL),
      ('{RETIRED}', '{DOC}', -1000000, 'p3', 'c1', 'grace withdrawn', true, now()),
      ('{IN_RETIRED_DOC}', '{GONE_DOC}', 0, 'q1', 'k1', 'grace elsewhere', true, NULL),
      ('{OBJ_A1}', '{SUMMA}', 0, 'a1/o1', 'a1', 'objection one', true, NULL),
      ('{DET_A1}', '{SUMMA}', 1, 'a1/d', 'a1', 'answer one', false, NULL),
      ('{OBJ_A2}', '{SUMMA}', 2, 'a2/o1', 'a2', 'objection two', true, NULL),
      ('{DET_A2}', '{SUMMA}', -1000001, 'a2/d', 'a2', 'answer two', true, now()),
      ('{OBJ_A3}', '{SUMMA}', 3, 'a3/o1', 'a3', 'objection three', true, NULL),
      ('{DET_A3}', '{SUMMA}', 4, 'a3/d', 'a3', 'answer three', true, NULL);
    UPDATE chunks SET unit_label = CASE WHEN anchor LIKE '%/o1' THEN 'Objection 1'
                                        ELSE 'I answer that' END
    WHERE document_id = '{SUMMA}';
    UPDATE documents SET retired_at = now() WHERE id = '{GONE_DOC}';
"""


@pytest.fixture(scope="module")
def cluster():
    with local_cluster("tc-search-visibility-") as running:
        running.sql(PRODUCTION_SCHEMA)
        running.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
        running.sql(SEED)
        yield running


@contextlib.asynccontextmanager
async def _pool_on(cluster):
    pool = await asyncpg.create_pool(
        host=str(cluster.socket), user="postgres", database="postgres",
        min_size=1, max_size=3, statement_cache_size=0, init=_init_connection,
    )
    try:
        with (
            patch("app.rag.steps.retrieve_fts.get_pool", return_value=pool),
            patch("app.rag.steps.fetch_context.get_pool", return_value=pool),
            patch("app.rag.steps.fetch_positions.get_pool", return_value=pool),
            patch("app.corpus_schema.get_pool", return_value=pool),
        ):
            yield pool
    finally:
        await pool.close()


@pytest.mark.real_corpus_schema
async def test_full_text_search_returns_only_searchable_live_rows(cluster):
    async with _pool_on(cluster):
        assert await corpus_schema.current() == ALL
        result = await retrieve_fts.run("grace", ["church-fathers"], quota=5, k=10)
    assert [row["id"] for row in result["church-fathers"]] == [SHOWN]


async def test_without_0042_full_text_search_still_runs_against_0042(cluster):
    """The legacy SQL (the autouse fixture pins LEGACY) is valid on a migrated database
    and, with nothing hidden, would return every match: the predicates are what hide."""
    async with _pool_on(cluster):
        result = await retrieve_fts.run("grace", ["church-fathers"], quota=5, k=10)
    assert {row["id"] for row in result["church-fathers"]} == {
        SHOWN, UNSEARCHABLE, RETIRED, IN_RETIRED_DOC,
    }


async def _stitched(cluster, objection: str, chapter_key: str):
    async with _pool_on(cluster):
        articles = await fetch_context.articles({chapter_key})
    result = next(c for c in articles.get((SUMMA, chapter_key), [])
                  if c.chunk_id == objection)
    [card] = stitch.assemble([result], articles)
    return card


@pytest.mark.real_corpus_schema
async def test_unsearchable_parts_are_not_attached(cluster):
    card = await _stitched(cluster, OBJ_A1, "a1")
    assert card.parts == []
    control = await _stitched(cluster, OBJ_A3, "a3")
    assert [p.chunk_id for p in control.parts] == [DET_A3]


@pytest.mark.real_corpus_schema
async def test_retired_parts_are_not_attached(cluster):
    card = await _stitched(cluster, OBJ_A2, "a2")
    assert card.parts == []


def _vector_hit(chunk_id: str) -> dict:
    return {
        "id": chunk_id, "content": "grace", "reference": None,
        "collection": "church-fathers", "document_id": DOC, "document_title": "On Grace",
        "author": None, "anchor": None, "chapter_key": None, "unit_label": None,
        "position": None, "annotation": None,
    }


@pytest.mark.real_corpus_schema
async def test_runner_drops_a_vector_hit_whose_row_is_hidden(cluster):
    """Defense in depth for a Qdrant point that disagrees with Postgres: a vector hit
    whose row is retired, unsearchable, in a retired document or missing never reaches
    the reranker."""
    from app.rag.steps.types import RetrievalPath

    orphan = "00000000-0000-0000-0000-0000000000ff"
    hits = [_vector_hit(i) for i in (SHOWN, UNSEARCHABLE, RETIRED, IN_RETIRED_DOC, orphan)]
    seen: dict[str, list[str]] = {}

    async def rerank(pools, *args, **kwargs):
        seen.update({col: [c.chunk_id for c in cands] for col, cands in pools.items()})
        chunk = RankedChunk(
            chunk_id=SHOWN, content="grace", reference=None, collection="church-fathers",
            document_id=DOC, document_title="On Grace", author=None, reranker_score=0.9,
        )
        return {"church-fathers": [chunk]}

    async with _pool_on(cluster):
        with (
            patch("app.rag.steps.embed.run", new=AsyncMock(return_value=[0.1] * 1536)),
            patch("app.rag.steps.hyde_s25.run", new=AsyncMock(return_value={})),
            patch("app.rag.steps.retrieve_vector.run", new=AsyncMock(
                return_value={"church-fathers": [RetrievalPath("query", hits)]})),
            patch("app.rag.steps.retrieve_fts.run", new=AsyncMock(return_value={})),
            patch("app.rag.steps.rerank_cohere.run_per_collection", new=rerank),
            patch("app.rag.steps.llm_rerank.listwise.rerank_pool",
                  new=AsyncMock(side_effect=lambda pool, *a, **k: pool)),
        ):
            await runner.run(PIPELINES["hyde_cohere_haiku"], "grace",
                             ["church-fathers"], quota=4)
    assert seen == {"church-fathers": [SHOWN]}
