"""The work filter: narrowing a collection to some of its documents (Catechism for now).

`filters.scopes.<collection>.documents` lists the document IDs to search, beside 5.1a's
genres and issuers. It is by document, not genre, because the Catechism of the Catholic
Church and the Roman Catechism share a genre. Only collections in
`DOCUMENTS_BY_COLLECTION` take it; validation, saving and restore are 5.1a's.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import patch

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, MatchAny, PointStruct, VectorParams,
)

from app.config import settings
from app.db import _init_connection
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.rag import constants, qdrant_client
from app.rag.collection_scope import CollectionScope
from app.rag.pipeline import _saved_search_filters
from app.rag.search_plan import SearchPlanError, resolve_search_plan
from app.rag.steps import retrieve_fts, retrieve_vector
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)

WORKS = Path(__file__).resolve().parents[3] / "datapipeline" / "registry" / "works.json"

CCC = "9679c400-d314-5394-b916-f6fc27b50104"
COMPENDIUM = "800373b1-d6c8-5a26-8910-8d1485b224c2"
ROMAN = "c6d78d5e-5f23-5f86-b0ca-97a741e186bf"
NOT_ROMAN = {"catechism": {"documents": [CCC, COMPENDIUM]}}


def test_the_catechism_lists_its_published_documents():
    works = json.loads(WORKS.read_text())
    published = {w["document_id"] for w in works
                 if w["collection"] == "catechism" and w["status"] == "active"}
    assert constants.DOCUMENTS_BY_COLLECTION == {"catechism": published}
    assert published == {CCC, COMPENDIUM, ROMAN}


# --- The plan -----------------------------------------------------------------------

def test_a_work_selection_excludes_the_other_works():
    plan = resolve_search_plan(["catechism", "bible"], 4, NOT_ROMAN)
    [scope] = plan.scopes
    assert scope == CollectionScope("catechism", excluded_documents=frozenset({ROMAN}))
    assert plan.saved_scopes() == {"catechism": {"documents": sorted([CCC, COMPENDIUM])}}


def test_every_work_is_the_whole_collection():
    plan = resolve_search_plan(["catechism"], 4, {
        "catechism": {"documents": [CCC, COMPENDIUM, ROMAN]}})
    assert plan.scopes == ()


def test_a_work_selection_does_not_count_as_a_collection_for_focused_search():
    plan = resolve_search_plan(["catechism"], 10, {"catechism": {"documents": [ROMAN]}})
    assert plan.focused and plan.collections == ("catechism",)


@pytest.mark.parametrize("scopes", [
    {"catechism": {"documents": []}},
    {"catechism": {"documents": ["00000000-0000-0000-0000-000000000000"]}},
    {"catechism": {"documents": ["not-a-uuid"]}},
    # Only the collections with a work filter take one.
    {"papal": {"documents": [CCC]}},
    {"councils": {"documents": [CCC]}},
])
def test_a_bad_work_selection_is_refused(scopes):
    with pytest.raises(SearchPlanError) as raised:
        resolve_search_plan(["catechism", "papal", "councils"], 4, scopes)
    assert raised.value.code == "invalid_document"


def test_the_catechism_takes_no_genre_filter():
    with pytest.raises(SearchPlanError) as raised:
        resolve_search_plan(["catechism"], 4, {"catechism": {"genres": ["catechism"]}})
    assert raised.value.code == "invalid_genre"


def test_a_saved_search_keeps_the_work_selection():
    plan = resolve_search_plan(["catechism"], 4, NOT_ROMAN)
    saved = _saved_search_filters(["catechism"], "CPDV", 4, None, "success", {},
                                  plan.saved_scopes())
    assert saved["scopes"] == {"catechism": {"documents": sorted([CCC, COMPENDIUM])}}


# --- Routes ------------------------------------------------------------------------

def _client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: AuthUser(user_id="u", email=None)
    return TestClient(app)


@pytest.mark.parametrize("route, path, extra", [
    ("app.routes.search", "/v1/search", {}),
    ("app.routes.guest_search", "/v1/search/guest", {"session_token": "x" * 40}),
])
def test_an_unknown_work_is_a_422_with_its_code(route, path, extra):
    import importlib

    router = importlib.import_module(route).router
    body = {"query": "grace", "quota": 4, **extra, "filters": {
        "collections": ["catechism"], "scopes": {"catechism": {"documents": ["nope"]}}}}
    response = _client(router).post(path, json=body)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_document"


# --- Retrieval: the filters each path sends -----------------------------------------

def test_the_qdrant_filter_excludes_the_unticked_documents():
    built = CollectionScope("catechism", excluded_documents=frozenset({ROMAN})).to_qdrant_filter()
    assert built.must_not == [
        FieldCondition(key="document_id", match=MatchAny(any=[ROMAN]))]


def test_the_sql_excludes_the_unticked_documents():
    sql, args = CollectionScope(
        "catechism", excluded_documents=frozenset({ROMAN})).to_sql("d", 4)
    assert sql.strip() == "AND d.id <> ALL($4::uuid[])"
    assert args == [[ROMAN]]


# --- Against a real database and an in-memory Qdrant ------------------------------

SEED = f"""
    INSERT INTO documents (id, collection, title, author, metadata, genre) VALUES
      ('{CCC}', 'catechism', 'Catechism of the Catholic Church', NULL, '{{}}', 'catechism'),
      ('{COMPENDIUM}', 'catechism', 'Compendium', NULL, '{{}}', 'compendium'),
      ('{ROMAN}', 'catechism', 'Catechism of the Council of Trent', NULL, '{{}}', 'catechism');
    INSERT INTO chunks (id, document_id, position, anchor, chapter_key, content) VALUES
      ('{CCC[:-3]}c01', '{CCC}', 0, 'p1', 'c1', 'grace and the sacraments of faith'),
      ('{COMPENDIUM[:-3]}c02', '{COMPENDIUM}', 0, 'p1', 'c1', 'grace and the sacraments of faith'),
      ('{ROMAN[:-3]}c03', '{ROMAN}', 0, 'p1', 'c1', 'grace and the sacraments of faith');
"""


@pytest.fixture(scope="module")
def cluster():
    with local_cluster("tc-work-filter-") as running:
        running.sql(PRODUCTION_SCHEMA)
        running.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
        running.sql(SEED)
        yield running


@pytest.mark.real_corpus_schema
@pytest.mark.parametrize("mode", ["and", "min_match"])
async def test_keyword_search_reads_only_the_ticked_works(cluster, mode):
    pool = await asyncpg.create_pool(
        host=str(cluster.socket), user="postgres", database="postgres",
        min_size=1, max_size=2, statement_cache_size=0, init=_init_connection,
    )

    async def found(scope):
        with patch("app.rag.steps.retrieve_fts.get_pool", return_value=pool), \
             patch("app.corpus_schema.get_pool", return_value=pool):
            rows = await retrieve_fts.run(
                "grace sacraments", ["catechism"], 4, k=10, mode=mode,
                scopes={"catechism": scope} if scope else None)
        return {row["document_id"] for row in rows.get("catechism", [])}

    try:
        assert await found(None) == {CCC, COMPENDIUM, ROMAN}
        assert await found(CollectionScope(
            "catechism", excluded_documents=frozenset({ROMAN}))) == {CCC, COMPENDIUM}
        assert await found(CollectionScope(
            "catechism", excluded_documents=frozenset({CCC, COMPENDIUM}))) == {ROMAN}
    finally:
        await pool.close()


async def test_vector_search_reads_only_the_ticked_works(monkeypatch):
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection("chunks", vectors_config=VectorParams(
        size=4, distance=Distance.COSINE))
    await client.upsert("chunks", points=[
        PointStruct(id=str(uuid.UUID(int=n)), vector=[1.0, 0.0, 0.0, 0.0], payload={
            "collection": "catechism", "document_id": doc, "document_title": doc,
            "content": f"passage {n}"})
        for n, doc in enumerate((CCC, COMPENDIUM, ROMAN), start=1)
    ], wait=True)
    monkeypatch.setattr(settings, "qdrant_read_collection", "chunks")
    monkeypatch.setattr(qdrant_client, "_searchable_indexed", False)
    monkeypatch.setattr(qdrant_client, "_searchable_checked_at", float("inf"))

    async def found(scope):
        rows = await retrieve_vector._search_vector(scope, [1.0, 0.0, 0.0, 0.0], 10, "query")
        return {row["document_id"] for row in rows}

    try:
        with patch.object(retrieve_vector, "get_qdrant_client", return_value=client):
            assert await found(CollectionScope("catechism")) == {CCC, COMPENDIUM, ROMAN}
            assert await found(CollectionScope(
                "catechism", excluded_documents=frozenset({ROMAN}))) == {CCC, COMPENDIUM}
    finally:
        await client.close()
