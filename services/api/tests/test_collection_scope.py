"""Corpus cleanup 5.1a: genre and issuer filters inside a collection.

A request may narrow a collection to some genres and issuers (`filters.scopes`). The
plan stores the values turned off, and retrieval excludes only those, so a document
with no genre or issuer is searched under every selection. A request without scopes
runs exactly the Qdrant filter and SQL it ran before scopes existed.

The acceptance checks are docs/corpus-cleanup/P4-P5-republish-expand.md, item 5.1a.
"""
from __future__ import annotations

import contextlib
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams,
)

from app import corpus_schema
from app.config import settings
from app.db import _init_connection
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.rag import constants, qdrant_client
from app.rag.collection_scope import CollectionScope
from app.rag.pipeline import _saved_search_filters
from app.rag.search_plan import SearchPlan, SearchPlanError, resolve_search_plan
from app.rag.steps import retrieve_fts, retrieve_vector
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)
from tests.test_retrieve_fts_sql import ALL

REPO = Path(__file__).resolve().parents[3]
REGISTRY = REPO / "datapipeline" / "registry"
# build_sql's output on master before 5.1a, for both schemas and both modes.
BEFORE = json.loads((Path(__file__).parent / "fixtures" / "fts_sql_before_scopes.json").read_text())

ONLY_ENCYCLICALS = {"encyclicals": {"genres": ["encyclical"]}}


# --- Vocabulary --------------------------------------------------------------------

def _registry_genres() -> dict[str, object]:
    # genres.py imports nothing but __future__; running it as a file keeps the API
    # free of a datapipeline import.
    namespace: dict[str, object] = {}
    exec((REGISTRY / "genres.py").read_text(), namespace)
    return namespace


def test_api_genres_match_registry_module():
    registry = _registry_genres()
    for name in ("PAPAL_GENRES", "CURIA_GENRES", "CATECHISM_AND_LAW_GENRES", "WRITER_GENRES"):
        assert getattr(constants, name) == registry[name], name
    assert constants.OTHER_GENRE == registry["OTHER"]


def test_papal_issuers_cover_the_registry():
    """Every issuer works.json gives a papal collection can be filtered on, so a new
    pope's documents cannot fall outside an "only these popes" selection unnoticed."""
    works = json.loads((REGISTRY / "works.json").read_text())
    for work in works:
        issuer = work.get("issuer")
        if issuer and work["collection"] in constants.ISSUERS_BY_COLLECTION:
            assert issuer in constants.ISSUERS_BY_COLLECTION[work["collection"]], work["work_id"]
        genre = work.get("genre")
        if genre and work["collection"] in constants.GENRES_BY_COLLECTION:
            assert genre in constants.GENRES_BY_COLLECTION[work["collection"]], work["work_id"]


# --- Without scopes, today's filters -----------------------------------------------

@pytest.mark.parametrize("must_not", [
    None, [FieldCondition(key="searchable", match=MatchValue(value=False))],
])
def test_a_whole_collection_gives_todays_qdrant_filter(must_not):
    before = Filter(
        must=[FieldCondition(key="collection", match=MatchValue(value="encyclicals"))],
        must_not=must_not,
    )
    after = CollectionScope("encyclicals").to_qdrant_filter(must_not)
    assert after.model_dump_json() == before.model_dump_json()


@pytest.mark.parametrize("key", sorted(BEFORE))
def test_a_whole_collection_gives_todays_sql(key):
    schema, mode = key.split("/")
    schema = corpus_schema.LEGACY if schema == "legacy" else ALL
    assert retrieve_fts.build_sql(schema, mode) == BEFORE[key]
    assert CollectionScope("encyclicals").to_sql("d", 4) == ("", [])


async def test_retrieval_without_scopes_sends_todays_arguments():
    """Keyword search binds only the collection, question and limit; vector search sends
    the collection filter alone."""
    conn = AsyncMock()
    conn.fetch.return_value = []
    pool = AsyncMock()
    pool.acquire.return_value = conn
    with patch("app.rag.steps.retrieve_fts.get_pool", return_value=pool), \
         patch("app.corpus_schema.current", AsyncMock(return_value=ALL)):
        await retrieve_fts.run("grace", ["encyclicals"], 4, k=9, mode="min_match")
    [call] = conn.fetch.await_args_list
    assert call.args == (BEFORE["all/min_match"], "encyclicals", "grace", 9)


def test_a_plan_without_scopes_saves_todays_filters():
    plan = resolve_search_plan(["encyclicals", "bible"], 4)
    assert plan.scopes == () and plan.saved_scopes() == {}
    saved = _saved_search_filters(["encyclicals"], "CPDV", 4, None, "success", {},
                                  plan.saved_scopes())
    assert "scopes" not in saved


# --- The scope's filters -----------------------------------------------------------

def test_excluded_values_become_must_not_and_null_safe_sql():
    scope = CollectionScope("encyclicals", frozenset({"other", "apostolic-letter"}),
                            frozenset({"pope-pius-ix"}))
    must_not = scope.to_qdrant_filter(None).must_not
    assert [(c.key, c.match.any) for c in must_not] == [
        ("genre", ["apostolic-letter", "other"]), ("issuer", ["pope-pius-ix"])]
    sql, args = scope.to_sql("d", 4)
    assert "(d.genre IS NULL OR d.genre <> ALL($4::text[]))" in sql
    assert "(d.issuer IS NULL OR d.issuer <> ALL($5::text[]))" in sql
    assert args == [["apostolic-letter", "other"], ["pope-pius-ix"]]


def test_an_issuer_alone_takes_the_first_free_parameter():
    sql, args = CollectionScope("encyclicals", excluded_issuers=frozenset({"pope-leo-xiii"})
                                ).to_sql("d", 4)
    assert "$4::text[]" in sql and "$5" not in sql and args == [["pope-leo-xiii"]]


def test_the_searchable_condition_is_kept_beside_the_scope():
    searchable = [FieldCondition(key="searchable", match=MatchValue(value=False))]
    scope = CollectionScope("encyclicals", frozenset({"other"}))
    assert [c.key for c in scope.to_qdrant_filter(searchable).must_not] == ["searchable", "genre"]


# --- The plan ----------------------------------------------------------------------

def test_a_selection_is_stored_as_the_values_turned_off():
    plan = resolve_search_plan(["encyclicals"], 4, ONLY_ENCYCLICALS)
    [scope] = plan.scopes
    assert scope.excluded_genres == constants.GENRES_BY_COLLECTION["encyclicals"] - {"encyclical"}
    assert scope.excluded_issuers == frozenset()
    assert plan.saved_scopes() == ONLY_ENCYCLICALS


def test_selecting_everything_is_the_whole_collection():
    every = sorted(constants.GENRES_BY_COLLECTION["encyclicals"])
    plan = resolve_search_plan(["encyclicals"], 4, {"encyclicals": {"genres": every,
                                                                    "issuers": None}})
    assert plan.scopes == ()


def test_several_genres_and_issuers():
    plan = resolve_search_plan(["encyclicals", "papal-documents"], 5, {
        "encyclicals": {"genres": ["encyclical", "apostolic-letter"]},
        "papal-documents": {"issuers": ["pope-francis", "pope-john-paul-ii"]},
    })
    assert plan.saved_scopes() == {
        "encyclicals": {"genres": ["apostolic-letter", "encyclical"]},
        "papal-documents": {"issuers": ["pope-francis", "pope-john-paul-ii"]},
    }
    assert plan.scope("bible") == CollectionScope("bible")


@pytest.mark.parametrize("scopes, code", [
    ({"encyclicals": {"genres": ["sermon-ish"]}}, "invalid_genre"),
    ({"encyclicals": {"genres": []}}, "invalid_genre"),
    ({"bible": {"genres": ["encyclical"]}}, "invalid_genre"),
    ({"encyclicals": {"issuers": ["pope-peter-ii"]}}, "invalid_issuer"),
    ({"encyclicals": {"issuers": []}}, "invalid_issuer"),
])
def test_invalid_values_are_refused(scopes, code):
    with pytest.raises(SearchPlanError) as raised:
        resolve_search_plan(["encyclicals", "bible"], 4, scopes)
    assert raised.value.code == code


def test_a_scope_for_a_collection_not_searched_is_ignored():
    assert resolve_search_plan(["bible"], 4, ONLY_ENCYCLICALS).scopes == ()


def test_a_genre_selection_does_not_count_as_a_collection_for_focused_search():
    plan = resolve_search_plan(["encyclicals"], 10, {
        "encyclicals": {"genres": ["encyclical", "apostolic-letter"]}})
    assert plan.focused and plan.collections == ("encyclicals",)
    with pytest.raises(SearchPlanError) as raised:
        resolve_search_plan(["encyclicals", "bible"], 10, ONLY_ENCYCLICALS)
    assert raised.value.code == "focused_collection_count"


def test_a_plan_cannot_carry_a_scope_outside_its_collections():
    with pytest.raises(SearchPlanError):
        SearchPlan(("bible",), 4, (CollectionScope("encyclicals", frozenset({"other"})),))


# --- Routes ------------------------------------------------------------------------

def _client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: AuthUser(user_id="u", email=None)
    return TestClient(app)


def test_an_invalid_genre_is_a_422_with_its_code():
    from app.routes.search import router

    body = {"query": "grace", "quota": 4, "filters": {
        "collections": ["encyclicals"], "scopes": {"encyclicals": {"genres": ["nope"]}}}}
    response = _client(router).post("/v1/search", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_genre"


def test_an_invalid_issuer_is_a_422_with_its_code_for_guests():
    from app.routes.guest_search import router

    body = {"query": "grace", "quota": 4, "session_token": "x" * 40, "filters": {
        "collections": ["encyclicals"], "scopes": {"encyclicals": {"issuers": ["nope"]}}}}
    response = _client(router).post("/v1/search/guest", json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_issuer"


def test_the_older_codes_keep_their_plain_detail():
    from app.routes.search import router

    body = {"query": "grace", "quota": 10, "filters": {"collections": ["bible", "summa"]}}
    response = _client(router).post("/v1/search", json=body)
    assert response.status_code == 422
    assert response.json()["detail"] == "Quota 10 requires exactly one collection."


def test_a_restore_returns_the_stored_selection():
    from app.routes.search import router

    search_id = "00000000-0000-0000-0000-0000000005a1"
    filters = {"collections": ["encyclicals"], "translation": "CPDV", "quota": 4,
               "scopes": ONLY_ENCYCLICALS}
    pool = AsyncMock()
    pool.fetchrow.return_value = {"id": search_id, "query": "grace", "filters": filters,
                                  "result_count": 0}
    pool.fetch.return_value = []
    with patch("app.routes.search.get_pool", return_value=pool):
        body = _client(router).get(f"/v1/searches/{search_id}/results").json()
    assert body["filters"]["scopes"] == ONLY_ENCYCLICALS


async def test_the_guest_trial_saves_the_selection():
    from app.routes import guest_search

    conn = AsyncMock()
    conn.transaction = lambda: contextlib.nullcontext()

    @contextlib.asynccontextmanager
    async def acquire():
        yield conn

    pool = AsyncMock()
    pool.acquire = acquire

    class _Tx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *exc):
            return False

    conn.transaction = lambda: _Tx()
    with patch("app.routes.guest_search.get_pool", return_value=pool):
        await guest_search._persist_guest_results(
            uuid.uuid4(), "grace", ["encyclicals"], "CPDV", 4, [], {},
            scopes=ONLY_ENCYCLICALS,
        )
    filters = conn.execute.await_args_list[0].args[3]
    assert filters["scopes"] == ONLY_ENCYCLICALS


# --- Against a real database and a real Qdrant -------------------------------------

ENC = "00000000-0000-0000-0000-0000000005e1"
LETTER = "00000000-0000-0000-0000-0000000005e2"
NO_GENRE = "00000000-0000-0000-0000-0000000005e3"
SEED = f"""
    INSERT INTO documents (id, collection, title, author, metadata, genre, issuer) VALUES
      ('{ENC}', 'encyclicals', 'Rerum Novarum', 'Leo XIII', '{{}}', 'encyclical', 'pope-leo-xiii'),
      ('{LETTER}', 'encyclicals', 'A Letter', 'Pius IX', '{{}}', 'apostolic-letter', 'pope-pius-ix'),
      ('{NO_GENRE}', 'encyclicals', 'Unsorted', 'Someone', '{{}}', NULL, NULL);
    INSERT INTO chunks (id, document_id, position, anchor, chapter_key, content) VALUES
      ('{ENC[:-3]}c01', '{ENC}', 0, 'p1', 'c1', 'grace and labour'),
      ('{LETTER[:-3]}c02', '{LETTER}', 0, 'p1', 'c1', 'grace and labour'),
      ('{NO_GENRE[:-3]}c03', '{NO_GENRE}', 0, 'p1', 'c1', 'grace and labour');
"""


@pytest.fixture(scope="module")
def cluster():
    with local_cluster("tc-collection-scope-") as running:
        running.sql(PRODUCTION_SCHEMA)
        running.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
        running.sql(SEED)
        yield running


async def _keyword(cluster, scope: CollectionScope | None, mode: str) -> set[str]:
    pool = await asyncpg.create_pool(
        host=str(cluster.socket), user="postgres", database="postgres",
        min_size=1, max_size=2, statement_cache_size=0, init=_init_connection,
    )
    try:
        with patch("app.rag.steps.retrieve_fts.get_pool", return_value=pool), \
             patch("app.corpus_schema.get_pool", return_value=pool):
            found = await retrieve_fts.run(
                "grace labour", ["encyclicals"], 4, k=10, mode=mode,
                scopes={"encyclicals": scope} if scope else None,
            )
    finally:
        await pool.close()
    return {row["document_id"] for row in found.get("encyclicals", [])}


@pytest.mark.real_corpus_schema
@pytest.mark.parametrize("mode", ["and", "min_match"])
async def test_keyword_search_keeps_a_document_without_genre_under_every_selection(
        cluster, mode):
    assert await _keyword(cluster, None, mode) == {ENC, LETTER, NO_GENRE}
    only_letters = CollectionScope(
        "encyclicals", constants.GENRES_BY_COLLECTION["encyclicals"] - {"apostolic-letter"})
    assert await _keyword(cluster, only_letters, mode) == {LETTER, NO_GENRE}
    no_letters = CollectionScope("encyclicals", frozenset({"apostolic-letter"}))
    assert await _keyword(cluster, no_letters, mode) == {ENC, NO_GENRE}
    only_leo = CollectionScope(
        "encyclicals", excluded_issuers=frozenset(constants.PAPAL_ISSUERS) - {"pope-leo-xiii"})
    assert await _keyword(cluster, only_leo, mode) == {ENC, NO_GENRE}


@pytest.fixture()
async def qdrant(monkeypatch):
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection("chunks", vectors_config=VectorParams(
        size=4, distance=Distance.COSINE))

    def point(n: int, **extra) -> PointStruct:
        return PointStruct(id=str(uuid.UUID(int=n)), vector=[1.0, 0.0, 0.0, 0.0], payload={
            "collection": "encyclicals", "document_id": f"d{n}", "document_title": f"T{n}",
            "content": f"passage {n}", **extra})

    await client.upsert("chunks", points=[
        point(1, genre="encyclical", issuer="pope-leo-xiii"),
        point(2, genre="apostolic-letter", issuer="pope-pius-ix"),
        point(3),
    ], wait=True)
    monkeypatch.setattr(settings, "qdrant_read_collection", "chunks")
    monkeypatch.setattr(qdrant_client, "_searchable_indexed", False)
    monkeypatch.setattr(qdrant_client, "_searchable_checked_at", float("inf"))
    with patch.object(retrieve_vector, "get_qdrant_client", return_value=client):
        yield client
    await client.close()


async def _vector(scope: CollectionScope) -> set[str]:
    rows = await retrieve_vector._search_vector(scope, [1.0, 0.0, 0.0, 0.0], 10, "query")
    return {row["document_id"] for row in rows}


async def test_vector_search_keeps_a_point_without_genre_under_every_selection(qdrant):
    assert await _vector(CollectionScope("encyclicals")) == {"d1", "d2", "d3"}
    only_letters = CollectionScope(
        "encyclicals", constants.GENRES_BY_COLLECTION["encyclicals"] - {"apostolic-letter"})
    assert await _vector(only_letters) == {"d2", "d3"}
    only_pius = CollectionScope(
        "encyclicals", excluded_issuers=frozenset(constants.PAPAL_ISSUERS) - {"pope-pius-ix"})
    assert await _vector(only_pius) == {"d2", "d3"}


async def test_the_runner_hands_the_plan_scopes_to_both_paths():
    from app.rag.pipelines import runner
    from app.rag.pipelines.registry import PIPELINES

    plan = resolve_search_plan(["encyclicals"], 4, ONLY_ENCYCLICALS)
    vector = AsyncMock(return_value={})
    fts = AsyncMock(return_value={})
    with (
        patch("app.rag.steps.embed.run", new=AsyncMock(return_value=[0.1])),
        patch("app.rag.steps.hyde_s25.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.retrieve_vector.run", new=vector),
        patch("app.rag.steps.retrieve_fts.run", new=fts),
    ):
        await runner.run(PIPELINES["hyde_cohere_luna_seats10t80_ftsminmatch"], "grace",
                         ["encyclicals"], 4, search_plan=plan)
    expected = {"encyclicals": plan.scope("encyclicals")}
    assert vector.await_args.kwargs["scopes"] == expected
    assert fts.await_args.kwargs["scopes"] == expected
