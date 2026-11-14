"""Issue #233: keyword search's minimum-should-match mode, as a per-pipeline axis.

The default mode ("and") must be today's SQL exactly, so production does not change on
deploy. "min_match" ORs the question's lexemes, keeps passages holding at least half of
them (most first), and falls back to the passages holding the most terms when none
reaches half. It is checked against a real database under both definitions of
`search_vector`: 0004's, and 2.2c's 0045 (markers out, references in), which 4.0 applies.
"""
from __future__ import annotations

import contextlib
import dataclasses
import logging
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest

from app import corpus_schema
from app.db import _init_connection
from app.rag.compare import shared_runner
from app.rag.pipelines import runner
from app.rag.pipelines.registry import PIPELINES, RetrievalConfig
from app.rag.steps import retrieve_fts
from app.rag.steps.types import RankedChunk, RetrievalPath
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)
from tests.test_retrieve_fts_sql import ALL, TODAY_FTS

PRODUCTION = "hyde_cohere_luna_seats10t80"
ARM = "hyde_cohere_luna_seats10t80_ftsminmatch"


# --- The default is today's SQL ----------------------------------------------------

def test_the_default_mode_is_todays_sql_exactly():
    assert retrieve_fts.build_sql(corpus_schema.LEGACY, "and") == TODAY_FTS
    assert retrieve_fts.build_sql(corpus_schema.LEGACY) == TODAY_FTS
    assert retrieve_fts.build_sql(ALL, "and") == retrieve_fts.build_sql(ALL)


def test_min_match_keeps_the_searchable_filter_and_voice():
    sql = retrieve_fts.build_sql(ALL, "min_match")
    assert "AND c.searchable" in sql
    assert "AND c.retired_at IS NULL" in sql
    assert "AND d.retired_at IS NULL" in sql
    assert "c.voice" in sql
    assert "c.voice" not in retrieve_fts.build_sql(corpus_schema.LEGACY, "min_match")


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        retrieve_fts.build_sql(corpus_schema.LEGACY, "or")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        RetrievalConfig(fts_mode="or")  # type: ignore[arg-type]


# --- The axis ----------------------------------------------------------------------

def test_production_keeps_and_and_the_arm_differs_only_in_fts_mode():
    assert RetrievalConfig().fts_mode == "and"
    assert PIPELINES[PRODUCTION].retrieval.fts_mode == "and"
    arm = PIPELINES[ARM]
    assert arm.retrieval.fts_mode == "min_match"
    assert dataclasses.replace(
        arm, name=PRODUCTION,
        retrieval=dataclasses.replace(arm.retrieval, fts_mode="and"),
    ) == PIPELINES[PRODUCTION]


def _row(i: int) -> dict:
    return {
        "id": f"00000000-0000-0000-0000-{i:012d}", "content": f"chunk {i}",
        "reference": f"Ref {i}", "collection": "bible",
        "document_id": "00000000-0000-0000-0000-000000000099", "document_title": "Doc",
        "author": None, "anchor": None, "position": i, "annotation": None,
    }


async def test_capture_searches_once_per_mode_and_never_shares_a_pool_across_modes():
    """Arms that differ only in FTS mode fuse different lexical lists, so each needs
    its own keyword search and its own pool; sharing one would compare an arm with
    itself."""
    vector_ranked = [_row(i) for i in range(50)]
    by_mode = {"and": [], "min_match": [_row(i) for i in reversed(range(50))]}

    async def fts(query, collections, quota, k=None, mode="and"):
        return {"bible": by_mode[mode]} if by_mode[mode] else {}

    with (
        patch("app.rag.compare.shared_runner.embed.run", new=AsyncMock(return_value=[0.1])),
        patch("app.rag.compare.shared_runner.hyde_s25.run",
              new=AsyncMock(return_value={"bible": [[0.2]]})),
        patch("app.rag.compare.shared_runner.retrieve_vector.run",
              new=AsyncMock(return_value={"bible": [RetrievalPath("hyde", vector_ranked)]})),
        patch("app.rag.compare.shared_runner.retrieve_fts.run",
              new=AsyncMock(side_effect=fts)) as search,
        patch("app.rag.compare.shared_runner.fetch_positions.run",
              new=AsyncMock(side_effect=lambda candidates: candidates)),
    ):
        artifacts = await shared_runner.capture(
            "q", ["bible"], 4, [PIPELINES[PRODUCTION], PIPELINES[ARM]],
        )

    assert sorted(call.kwargs["mode"] for call in search.await_args_list) == [
        "and", "min_match",
    ]
    control = artifacts.candidate_pools[PRODUCTION]["bible"]
    variant = artifacts.candidate_pools[ARM]["bible"]
    assert [c.rrf_score for c in control] != [c.rrf_score for c in variant]


async def test_the_runner_searches_with_the_pipelines_mode():
    chunk = RankedChunk(
        chunk_id=_row(1)["id"], content="c", reference=None, collection="bible",
        document_id=_row(1)["document_id"], document_title="Doc", author=None,
        reranker_score=0.9,
    )
    with (
        patch("app.rag.steps.embed.run", new=AsyncMock(return_value=[0.1] * 1536)),
        patch("app.rag.steps.hyde_s25.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.retrieve_vector.run", new=AsyncMock(
            return_value={"bible": [RetrievalPath("query", [_row(1)])]})),
        patch("app.rag.steps.retrieve_fts.run", new=AsyncMock(return_value={})) as fts,
        patch("app.rag.steps.fetch_positions.run",
              new=AsyncMock(side_effect=lambda candidates: candidates)),
        patch("app.rag.steps.rerank_cohere.run_per_collection",
              new=AsyncMock(return_value={"bible": [chunk]})),
        patch("app.rag.steps.llm_rerank.listwise.rerank_pool",
              new=AsyncMock(side_effect=lambda pool, *a, **k: pool)),
    ):
        await runner.run(PIPELINES[ARM], "grace", ["bible"], quota=4)
        await runner.run(PIPELINES[PRODUCTION], "grace", ["bible"], quota=4)
    assert [call.kwargs["mode"] for call in fts.await_args_list] == ["min_match", "and"]


# --- Visibility --------------------------------------------------------------------

async def test_a_collection_with_no_rows_is_logged(caplog):
    async def search(collection, query, limit, mode="and"):
        return [] if collection == "bible" else [_row(1)]

    with (
        patch("app.rag.steps.retrieve_fts._search_fts", new=AsyncMock(side_effect=search)),
        caplog.at_level(logging.INFO, logger="app.rag.steps.retrieve_fts"),
    ):
        result = await retrieve_fts.run("q", ["bible", "summa"], 4, k=50, mode="min_match")

    assert list(result) == ["summa"]
    [record] = [r for r in caplog.records if "0 rows" in r.getMessage()]
    assert (record.collection, record.fts_mode, record.fts_rows) == ("bible", "min_match", 0)


# --- Against a real database ---------------------------------------------------------

SUMMA = "00000000-0000-0000-0000-00000000b001"
FATHERS = "00000000-0000-0000-0000-00000000b002"
ALL_FOUR = "00000000-0000-0000-0000-0000000001a4"
THREE = "00000000-0000-0000-0000-0000000001a3"
TWO = "00000000-0000-0000-0000-0000000001a2"
ONE = "00000000-0000-0000-0000-0000000001a1"
NONE = "00000000-0000-0000-0000-0000000001a0"
HIDDEN = "00000000-0000-0000-0000-0000000001af"
ELSEWHERE = "00000000-0000-0000-0000-0000000001ae"

# "analogies trinity heresy grace" has four lexemes: analog, triniti, heresi, grace.
SEED = f"""
    INSERT INTO documents (id, collection, title, metadata) VALUES
      ('{SUMMA}', 'summa', 'Summa Theologiae', '{{}}'),
      ('{FATHERS}', 'church-fathers', 'On the Trinity', '{{}}');
    INSERT INTO chunks (id, document_id, position, anchor, chapter_key, content,
                        searchable) VALUES
      ('{ALL_FOUR}', '{SUMMA}', 0, 'a4', 'q1', 'Analogies for the Trinity, rightly made,
        fall into no heresy, for they are given by grace.', true),
      ('{THREE}', '{SUMMA}', 1, 'a3', 'q1', 'Some analogies of the Trinity lead to
        heresy. {{{{v:2}}}} So it was with Sabellius.', true),
      ('{TWO}', '{SUMMA}', 2, 'a2', 'q2', 'The Trinity is known by grace.', true),
      ('{ONE}', '{SUMMA}', 3, 'a1', 'q3', 'Grace, grace, and again grace: grace upon
        grace.', true),
      ('{NONE}', '{SUMMA}', 4, 'a0', 'q4', 'Of the movement of the heavens.', true),
      ('{HIDDEN}', '{SUMMA}', 5, 'af', 'q5', 'Analogies of the Trinity, heresy and
        grace, in a passage kept out of search.', false),
      ('{ELSEWHERE}', '{FATHERS}', 0, 'e1', 'b1', 'Analogies for the Trinity, heresy
        and grace, in another collection.', true);
"""

BEFORE_2_2C = (*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name,
               "0044_document_form.sql")


@pytest.fixture(scope="module", params=["0004", "0045"])
def cluster(request):
    """Both definitions of search_vector: today's, and 2.2c's (applied in 4.0)."""
    with local_cluster("tc-fts-min-") as running:
        running.sql(PRODUCTION_SCHEMA)
        running.migrate(*BEFORE_2_2C)
        if request.param == "0045":
            running.migrate("0045_search_vector_markers_and_reference.sql")
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
            patch("app.corpus_schema.get_pool", return_value=pool),
        ):
            yield pool
    finally:
        await pool.close()


async def _ids(cluster, query: str, mode: str, collection: str = "summa") -> list[str]:
    async with _pool_on(cluster):
        result = await retrieve_fts.run(query, [collection], quota=4, k=50, mode=mode)
    return [row["id"] for row in result.get(collection, [])]


@pytest.mark.real_corpus_schema
async def test_min_match_keeps_half_the_terms_or_more_most_first(cluster):
    """Four terms: at least two must match. The passage that only repeats one term,
    however often, is left out; the unsearchable passage and the other collection's
    are too."""
    query = "analogies for the trinity heresy grace"
    assert await _ids(cluster, query, "min_match") == [ALL_FOUR, THREE, TWO]
    # Today's AND finds only the passage holding all four.
    assert await _ids(cluster, query, "and") == [ALL_FOUR]


@pytest.mark.real_corpus_schema
async def test_when_no_passage_reaches_half_it_falls_back_to_the_most_matched(cluster):
    """Four terms, but no passage holds two: the passages holding one are kept."""
    found = await _ids(cluster, "trinity zebra quokka wombat", "min_match")
    assert set(found) == {ALL_FOUR, THREE, TWO}
    assert await _ids(cluster, "trinity zebra quokka wombat", "and") == []


@pytest.mark.real_corpus_schema
async def test_short_of_half_it_keeps_the_most_matched_not_every_one_term_match(cluster):
    """Six terms (half is three), and the best passages hold two: those are kept, and
    the passages holding one are not."""
    found = await _ids(cluster, "trinity grace zebra quokka wombat koala", "min_match")
    assert set(found) == {ALL_FOUR, TWO}


@pytest.mark.real_corpus_schema
async def test_a_question_of_the_longest_allowed_length_runs(cluster):
    """1,000 characters, past the 40 terms the pair filter is used for."""
    words = " ".join(f"word{chr(97 + i % 26)}{chr(97 + i // 26)}" for i in range(140))
    query = (words + " trinity grace")[-1000:]
    assert len(query) <= 1000
    assert set(await _ids(cluster, query, "min_match")) == {ALL_FOUR, TWO}


@pytest.mark.real_corpus_schema
@pytest.mark.parametrize("query", [
    "trinity",                                 # n = 1: the same as AND
    "trinity grace",                           # n = 2
    "analogies trinity heresy",                # n = 3
    "analogies for the trinity heresy grace",  # n = 4
])
async def test_todays_results_are_always_the_head_of_min_match(cluster, query):
    """A passage holding every term ranks exactly where AND puts it, so min-match
    loses nothing today's search finds, for short queries included."""
    today = await _ids(cluster, query, "and")
    new = await _ids(cluster, query, "min_match")
    assert today
    assert new[:len(today)] == today
    if len(query.split()) == 1:
        assert new == today


@pytest.mark.real_corpus_schema
async def test_two_terms_add_the_one_term_matches_after_todays(cluster):
    today = await _ids(cluster, "trinity grace", "and")
    assert set(today) == {ALL_FOUR, TWO}
    new = await _ids(cluster, "trinity grace", "min_match")
    assert new[:2] == today
    assert set(new[2:]) == {THREE, ONE}


@pytest.mark.real_corpus_schema
@pytest.mark.parametrize("query", ["the of and", "", "O'Brien's C:\\path \\ 'x'"])
async def test_awkward_queries_do_not_fail(cluster, query):
    assert await _ids(cluster, query, "min_match") == []


@pytest.mark.real_corpus_schema
async def test_the_limit_applies_after_ordering(cluster):
    async with _pool_on(cluster):
        result = await retrieve_fts.run(
            "analogies for the trinity heresy grace", ["summa"], quota=4, k=2,
            mode="min_match",
        )
    assert [row["id"] for row in result["summa"]] == [ALL_FOUR, THREE]


async def test_min_match_runs_on_the_legacy_sql_too(cluster):
    """Without 0042 (the autouse fixture pins LEGACY) nothing is filtered by
    `searchable`, so the hidden passage comes back: the predicates are what hide."""
    found = await _ids(cluster, "analogies for the trinity heresy grace", "min_match")
    assert set(found) == {ALL_FOUR, THREE, TWO, HIDDEN}
