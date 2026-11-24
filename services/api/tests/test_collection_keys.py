"""Corpus cleanup 5.1b.1: the API accepts the new collection keys (expand).

`papal`, `church-law` and `theologians` work beside the old keys. An old key keeps
today's meaning, results come back labelled with the key the request used, and both
vocabularies work whether or not 5.1b.3 has rewritten the stored values.

The acceptance checks are docs/corpus-cleanup/P4-P5-republish-expand.md, item 5.1b.1.
"""
from __future__ import annotations

import logging
import uuid
from unittest.mock import AsyncMock, patch

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams,
)

from app.config import settings
from app.db import _init_connection
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.preferences import DEFAULT_COLLECTIONS, PreferencesResponse
from app.rag import constants, dedup, qdrant_client
from app.rag.collection_scope import CollectionScope, StoredRead, reads
from app.rag.search_plan import resolve_search_plan
from app.rag.steps import hyde_s25, retrieve_fts, retrieve_vector
from tests.pg_cluster import local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)

PAPAL_OLD = ("encyclicals", "apostolic-exhortations", "papal-documents")


# --- The vocabulary ----------------------------------------------------------------

def test_both_vocabularies_are_valid():
    assert constants.CANONICAL_COLLECTIONS >= {"papal", "church-law", "theologians"}
    assert constants.VALID_COLLECTIONS == (
        constants.CANONICAL_COLLECTIONS | set(constants.LEGACY_COLLECTIONS))
    assert len(constants.VALID_COLLECTIONS) == 13
    for old, legacy in constants.LEGACY_COLLECTIONS.items():
        assert legacy.canonical in constants.CANONICAL_COLLECTIONS, old


def test_the_old_papal_keys_split_the_papal_genres_between_them():
    """Every papal genre, and a document with none, belongs to exactly one old key."""
    vocabulary = constants.GENRES_BY_COLLECTION["papal"]
    owners = {genre: [] for genre in [*vocabulary, None]}
    for old in PAPAL_OLD:
        legacy = constants.LEGACY_COLLECTIONS[old]
        for genre in owners:
            if legacy.genres is not None:
                hit = genre in legacy.genres
            else:
                hit = genre not in legacy.without_genres
            if hit:
                owners[genre].append(old)
    assert all(len(keys) == 1 for keys in owners.values()), owners


def test_papal_takes_the_same_genre_and_issuer_filters():
    assert constants.GENRES_BY_COLLECTION["papal"] == constants.GENRES_BY_COLLECTION["encyclicals"]
    assert constants.ISSUERS_BY_COLLECTION["papal"] == constants.ISSUERS_BY_COLLECTION["encyclicals"]


@pytest.mark.parametrize("key, expected", [
    ("bible", StoredRead(("bible",))),
    ("papal", StoredRead(("papal", *PAPAL_OLD))),
    ("church-law", StoredRead(("church-law", "canon-law"))),
    ("theologians", StoredRead(("theologians", "medieval"))),
    ("canon-law", StoredRead(("canon-law", "church-law"))),
    ("medieval", StoredRead(("medieval", "theologians"))),
    ("encyclicals",
     StoredRead(("encyclicals",), ("papal", constants.LEGACY_COLLECTIONS["encyclicals"]))),
])
def test_what_each_key_reads(key, expected):
    assert reads(key) == expected


# --- Filters ------------------------------------------------------------------------

SEARCHABLE = [FieldCondition(key="searchable", match=MatchValue(value=False))]


@pytest.mark.parametrize("key", sorted(
    constants.CANONICAL_COLLECTIONS - {"papal", "church-law", "theologians"}))
@pytest.mark.parametrize("indexed", [False, True])
def test_a_key_5_1b_leaves_alone_gives_todays_filters(key, indexed):
    today = Filter(must=[FieldCondition(key="collection", match=MatchValue(value=key))],
                   must_not=SEARCHABLE)
    scope = CollectionScope(key)
    assert (scope.to_qdrant_filter(SEARCHABLE, genre_indexed=indexed).model_dump_json()
            == today.model_dump_json())
    assert scope.collection_sql("d", 4, genre_column=indexed) == ("d.collection = $1", key, [])
    assert scope.collection_sql("d", 4, genre_column=indexed)[0] == retrieve_fts.TODAYS_COLLECTION_SQL


@pytest.mark.parametrize("key", PAPAL_OLD)
def test_an_old_papal_key_gives_todays_filters_where_genre_cannot_be_read(key):
    """A Qdrant collection without the genre index (the pre-republish `chunks`, kept
    for rollback) and a database without `documents.genre` hold no new values, so the
    old key sends exactly today's filter there."""
    today = Filter(must=[FieldCondition(key="collection", match=MatchValue(value=key))],
                   must_not=SEARCHABLE)
    scope = CollectionScope(key)
    assert scope.to_qdrant_filter(SEARCHABLE).model_dump_json() == today.model_dump_json()
    assert scope.collection_sql("d", 4, genre_column=False) == ("d.collection = $1", key, [])


def test_an_old_papal_key_also_reads_its_genres_of_the_new_value():
    scope = CollectionScope("encyclicals", excluded_issuers=frozenset({"pope-pius-ix"}))
    condition, value, args = scope.collection_sql("d", 5, genre_column=True)
    assert condition == ("(d.collection = $1 OR (d.collection = $5::text"
                         " AND d.genre = ANY($6::text[])))")
    assert (value, args) == ("encyclicals", ["papal", ["encyclical"]])
    condition, _, args = CollectionScope("papal-documents").collection_sql(
        "d", 4, genre_column=True)
    assert "(d.genre IS NULL OR d.genre <> ALL($5::text[]))" in condition
    assert args == ["papal", ["apostolic-exhortation", "encyclical"]]
    query_filter = scope.to_qdrant_filter(SEARCHABLE, genre_indexed=True)
    assert query_filter.must is None and len(query_filter.should) == 2
    assert [c.key for c in query_filter.must_not] == ["searchable", "issuer"]


def test_a_renamed_key_reads_both_values_without_genre():
    for key in ("canon-law", "church-law", "medieval", "theologians", "papal"):
        condition, value, args = CollectionScope(key).collection_sql("d", 4, genre_column=True)
        assert condition == "d.collection = ANY($1::text[])" and args == []
        assert value == list(reads(key).whole)


# --- The plan -----------------------------------------------------------------------

def test_an_old_key_beside_its_new_key_is_dropped_and_logged(caplog):
    caplog.set_level(logging.INFO, logger="app.rag.search_plan")
    plan = resolve_search_plan(["encyclicals", "papal", "canon-law", "bible"], 5)
    assert plan.collections == ("papal", "canon-law", "bible")
    logged = {(r.legacy_collection_key, r.legacy_key_dropped) for r in caplog.records
              if hasattr(r, "legacy_collection_key")}
    assert logged == {("encyclicals", True), ("canon-law", False)}


def test_a_plan_of_new_keys_logs_nothing(caplog):
    caplog.set_level(logging.INFO, logger="app.rag.search_plan")
    resolve_search_plan(["papal", "church-law", "theologians"], 4)
    assert not [r for r in caplog.records if hasattr(r, "legacy_collection_key")]


def test_focused_search_counts_an_old_key_beside_its_new_key_once():
    plan = resolve_search_plan(["papal", "encyclicals"], 10)
    assert plan.focused and plan.collections == ("papal",)


def test_papal_takes_a_genre_and_issuer_scope():
    plan = resolve_search_plan(["papal"], 4, {"papal": {
        "genres": ["encyclical"], "issuers": ["pope-leo-xiii"]}})
    [scope] = plan.scopes
    assert scope.collection == "papal"
    assert plan.saved_scopes() == {"papal": {"genres": ["encyclical"],
                                             "issuers": ["pope-leo-xiii"]}}


# --- HyDE ---------------------------------------------------------------------------

@pytest.mark.parametrize("excluded, kinds", [
    (frozenset(), ["encyclicals", "apostolic-exhortations", "papal-documents"]),
    (frozenset({"encyclical"}), ["apostolic-exhortations", "papal-documents"]),
    (constants.GENRES_BY_COLLECTION["papal"] - {"encyclical"}, ["encyclicals"]),
    (constants.GENRES_BY_COLLECTION["papal"] - {"other"}, ["papal-documents"]),
    (frozenset({"apostolic-letter", "apostolic-constitution", "motu-proprio", "letter",
                "other"}), ["encyclicals", "apostolic-exhortations"]),
])
def test_papal_hyde_writes_one_passage_per_kind_the_filter_leaves_on(excluded, kinds):
    assert hyde_s25.papal_hyde_kinds(excluded) == kinds


async def test_papal_hyde_uses_each_kinds_prompt_and_length():
    calls = []

    async def single(client, system, query, max_tokens, **kwargs):
        calls.append((system, max_tokens))
        return "passage"

    with patch.object(hyde_s25, "_generate_single", side_effect=single):
        passages = await hyde_s25.generate_hyde_passages(
            "grace", "papal", object(), AsyncMock(), passage_provider="luna",
            excluded_genres=frozenset({"apostolic-exhortation"}),
        )
    assert passages == ["passage", "passage"]
    prompts = hyde_s25._COLLECTION_HYDE_PROMPTS
    assert calls == [(prompts["encyclicals"], 400), (prompts["papal-documents"], 300)]


def test_the_renamed_keys_take_their_prompts_and_lengths():
    prompts, tokens = hyde_s25._COLLECTION_HYDE_PROMPTS, hyde_s25._COLLECTION_MAX_TOKENS
    assert prompts["church-law"] == prompts["canon-law"]
    assert "medieval schoolmen and mystics" in prompts["theologians"]
    assert (tokens["church-law"], tokens["theologians"]) == (350, 350)
    assert "papal" not in prompts


async def test_the_runner_hands_the_plan_scopes_to_hyde():
    from app.rag.pipelines import runner
    from app.rag.pipelines.registry import PIPELINES

    plan = resolve_search_plan(["papal"], 4, {"papal": {"genres": ["encyclical"]}})
    hyde = AsyncMock(return_value={})
    with (
        patch("app.rag.steps.embed.run", new=AsyncMock(return_value=[0.1])),
        patch("app.rag.steps.hyde_s25.run", new=hyde),
        patch("app.rag.steps.retrieve_vector.run", new=AsyncMock(return_value={})),
        patch("app.rag.steps.retrieve_fts.run", new=AsyncMock(return_value={})),
    ):
        await runner.run(PIPELINES["hyde_cohere_luna_seats10t80_ftsminmatch"], "grace",
                         ["papal"], 4, search_plan=plan)
    assert hyde.await_args.kwargs["scopes"] == {"papal": plan.scopes[0]}


# --- Other key tables ---------------------------------------------------------------

def test_church_law_is_chapter_keyed_like_canon_law():
    assert "church-law" in dedup._CHAPTER_KEYED_COLLECTIONS
    for new, old in (("church-law", "canon-law"), ("theologians", "medieval")):
        assert dedup.cosine_threshold(new, True) == dedup.cosine_threshold(old, True)


def test_the_renamed_keys_keep_footnotes_and_source_links():
    from app import corpus_lifecycle, footnotes, reader_access

    assert footnotes.has_footnotes("theologians", None)
    assert reader_access.source_url("church-law", None) == reader_access.source_url(
        "canon-law", None)
    latin = {"official_latin_urls": {"can/295": "https://www.vatican.va/x"}}
    for key in ("canon-law", "church-law"):
        assert corpus_lifecycle.read_elsewhere_url(
            "translation-in-preparation", key, False, latin, "can/295",
        ) == "https://www.vatican.va/x"


# --- Preferences --------------------------------------------------------------------

def _row(collections, quota=4, standard=4):
    return {"preferred_translation": "CPDV", "default_collections": collections,
            "default_quota": quota, "last_standard_quota": standard, "theme": "dark"}


def _preferences_client():
    from app.routes.preferences import router

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    app.dependency_overrides[get_current_user] = lambda: AuthUser(user_id="u", email=None)
    return TestClient(app)


@pytest.mark.parametrize("stored, collections, quota", [
    (["bible", "saints", "papal"], ["bible", "papal"], 4),
    (["bible", "saints", None], ["bible"], 4),
    (["saints"], DEFAULT_COLLECTIONS, 4),
    (["saints", "summa"], ["summa"], 10),
])
def test_get_preferences_drops_a_stored_key_it_does_not_know(stored, collections, quota):
    pool = AsyncMock()
    pool.fetchrow.return_value = _row(stored, quota=10 if quota == 10 else 4)
    with patch("app.routes.preferences.get_pool", return_value=pool):
        response = _preferences_client().get("/v1/preferences")
    assert response.status_code == 200
    assert response.json()["default_collections"] == collections
    assert response.json()["default_quota"] == quota


@pytest.mark.parametrize("stored, saved, label", [
    ("encyclicals", ["papal", "bible"], "papal"),
    ("papal", ["papal"], "papal"),
    ("canon-law", ["church-law"], "church-law"),
    ("church-law", ["canon-law"], "canon-law"),
    ("encyclicals", ["encyclicals"], "encyclicals"),
    ("papal", ["encyclicals", "bible"], "encyclicals"),
    ("summa", None, "summa"),
])
def test_a_restored_passage_takes_the_saved_requests_key(stored, saved, label):
    from app.rag.collection_scope import requested_label

    assert requested_label(stored, saved) == label


@pytest.mark.parametrize("genre, label", [
    ("encyclical", "encyclicals"),
    ("apostolic-letter", "papal-documents"),
    (None, "papal-documents"),
    ("apostolic-exhortation", "papal"),
])
def test_the_genre_settles_which_old_papal_key_a_rewritten_passage_restores_as(genre, label):
    from app.rag.collection_scope import requested_label

    assert requested_label("papal", ["encyclicals", "papal-documents"], genre) == label
    assert requested_label("papal", ["encyclicals", "papal-documents"]) == "papal"


def test_a_focused_preference_left_without_one_collection_returns_to_standard():
    prefs = PreferencesResponse.from_stored(_row(["saints"], quota=10, standard=3))
    assert prefs.default_collections == DEFAULT_COLLECTIONS and prefs.default_quota == 3


def test_put_still_refuses_an_unknown_key():
    response = _preferences_client().put(
        "/v1/preferences", json={"default_collections": ["saints"]})
    assert response.status_code == 422


def test_put_accepts_new_keys():
    from app.models.preferences import PreferencesUpdate

    body = PreferencesUpdate(default_collections=["papal", "church-law", "theologians"])
    assert body.default_collections == ["papal", "church-law", "theologians"]


def test_a_put_replacing_a_focused_unknown_key_keeps_focused():
    from app.models.preferences import PreferencesUpdate
    from app.routes.preferences import _merge_preferences

    merged = _merge_preferences(PreferencesUpdate(default_collections=["summa"]),
                                _row(["saints"], quota=10, standard=3))
    assert merged.default_collections == ["summa"] and merged.default_quota == 10


def test_a_put_merges_over_a_stored_key_it_does_not_know():
    from app.models.preferences import PreferencesUpdate
    from app.routes.preferences import _merge_preferences

    merged = _merge_preferences(PreferencesUpdate(theme="light"), _row(["saints", "bible"]))
    assert merged.default_collections == ["bible"] and merged.theme == "light"


# --- Against a real database and Qdrant, before and after the rewrite -----------------

def _ids(prefix: int, n: int) -> list[str]:
    return [str(uuid.UUID(int=prefix * 100 + i)) for i in range(n)]


ENC, EXH, LETTER, NO_GENRE, CANON, EG = _ids(51, 6)
TITLES = {ENC: "Rerum Novarum", EXH: "Amoris Laetitia", LETTER: "Ad Tuendam Fidem",
          NO_GENRE: "Unsorted", CANON: "Code of Canon Law", EG: "Evangelii Gaudium"}
GENRES = {ENC: "encyclical", EXH: "apostolic-exhortation", LETTER: "apostolic-letter",
          NO_GENRE: None, CANON: "code", EG: "apostolic-exhortation"}
# Evangelii Gaudium is stored under `encyclicals` today with genre apostolic-exhortation
# (works.json), like seven other searchable papal documents. A rewrite moves it to the
# old key its genre names; 5.1b.3 decides whether that stands.
BEFORE = {ENC: "encyclicals", EXH: "apostolic-exhortations", LETTER: "papal-documents",
          NO_GENRE: "papal-documents", CANON: "canon-law", EG: "encyclicals"}
AFTER = {ENC: "papal", EXH: "papal", LETTER: "papal", NO_GENRE: "papal",
         CANON: "church-law", EG: "papal"}


def _seed(stored: dict[str, str]) -> str:
    rows = []
    for doc, collection in stored.items():
        genre = f"'{GENRES[doc]}'" if GENRES[doc] else "NULL"
        rows.append(f"INSERT INTO documents (id, collection, title, metadata, genre)"
                    f" VALUES ('{doc}', '{collection}', '{TITLES[doc]}', '{{}}', {genre});")
        rows.append(f"INSERT INTO chunks (document_id, position, anchor, chapter_key, content)"
                    f" VALUES ('{doc}', 0, 'p1', 'c1', 'grace and labour of workers');")
    return "\n".join(rows)


@pytest.fixture(scope="module", params=["before", "after"])
def stored(request):
    """The corpus as stored before 5.1b.3 (old values) and after it (new values; the
    rewrite also widens the constraint, which this fixture drops)."""
    values = BEFORE if request.param == "before" else AFTER
    with local_cluster("tc-collection-keys-") as running:
        running.sql(PRODUCTION_SCHEMA)
        running.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name)
        running.sql("ALTER TABLE documents DROP CONSTRAINT documents_collection_check;")
        running.sql(_seed(values))
        yield request.param, running


async def _keyword(cluster, key: str, scope: CollectionScope | None = None) -> list[dict]:
    pool = await asyncpg.create_pool(
        host=str(cluster.socket), user="postgres", database="postgres",
        min_size=1, max_size=2, statement_cache_size=0, init=_init_connection,
    )
    try:
        with patch("app.rag.steps.retrieve_fts.get_pool", return_value=pool), \
             patch("app.corpus_schema.get_pool", return_value=pool):
            found = await retrieve_fts.run("grace labour workers", [key], 4, k=10,
                                           mode="min_match", scopes={key: scope} if scope else None)
    finally:
        await pool.close()
    return found.get(key, [])


# What each key returns, the same before and after the rewrite except for a document
# stored under one old key whose genre belongs to another (`MOVES`).
EXPECTED = {
    "papal": {ENC, EXH, LETTER, NO_GENRE, EG},
    "encyclicals": {ENC},
    "apostolic-exhortations": {EXH},
    "papal-documents": {LETTER, NO_GENRE},
    "canon-law": {CANON},
    "church-law": {CANON},
}
MOVES = {"before": {"encyclicals": {EG}}, "after": {"apostolic-exhortations": {EG}}}


def _expected(when: str, key: str) -> set[str]:
    return EXPECTED[key] | MOVES[when].get(key, set())


@pytest.mark.real_corpus_schema
@pytest.mark.parametrize("key", sorted(EXPECTED))
async def test_keyword_search_reads_both_vocabularies(stored, key):
    when, cluster = stored
    rows = await _keyword(cluster, key)
    assert {row["document_id"] for row in rows} == _expected(when, key)
    assert {row["collection"] for row in rows} == {key}


@pytest.mark.real_corpus_schema
async def test_keyword_search_narrows_papal_by_genre(stored):
    _, cluster = stored
    scope = CollectionScope("papal", constants.GENRES_BY_COLLECTION["papal"] - {"encyclical"})
    assert {row["document_id"] for row in await _keyword(cluster, "papal", scope)} == {
        ENC, NO_GENRE}  # EG: an exhortation, whatever its stored value


@pytest.fixture(params=["before", "after"])
async def qdrant(request, monkeypatch):
    values = BEFORE if request.param == "before" else AFTER
    client = AsyncQdrantClient(location=":memory:")
    await client.create_collection("chunks", vectors_config=VectorParams(
        size=4, distance=Distance.COSINE))
    await client.upsert("chunks", points=[
        PointStruct(id=doc, vector=[1.0, 0.0, 0.0, 0.0], payload={
            "collection": values[doc], "document_id": doc, "document_title": TITLES[doc],
            "content": "passage", **({"genre": GENRES[doc]} if GENRES[doc] else {})})
        for doc in values
    ], wait=True)
    monkeypatch.setattr(settings, "qdrant_read_collection", "chunks")
    monkeypatch.setattr(qdrant_client, "_searchable_indexed", False)
    monkeypatch.setattr(qdrant_client, "_genre_indexed", True)
    monkeypatch.setattr(qdrant_client, "_searchable_checked_at", float("inf"))
    with patch.object(retrieve_vector, "get_qdrant_client", return_value=client):
        yield request.param
    await client.close()


@pytest.mark.parametrize("key", sorted(EXPECTED))
async def test_vector_search_reads_both_vocabularies(qdrant, key):
    rows = await retrieve_vector._search_vector(
        CollectionScope(key), [1.0, 0.0, 0.0, 0.0], 10, "query")
    assert {row["document_id"] for row in rows} == _expected(qdrant, key)
    assert {row["collection"] for row in rows} == {key}


async def test_vector_search_without_the_genre_index_reads_only_the_old_value(
        qdrant, monkeypatch):
    monkeypatch.setattr(qdrant_client, "_genre_indexed", False)
    rows = await retrieve_vector._search_vector(
        CollectionScope("encyclicals"), [1.0, 0.0, 0.0, 0.0], 10, "query")
    assert {row["document_id"] for row in rows} == (
        {ENC, EG} if qdrant == "before" else set())


async def test_a_refused_genre_filter_falls_back_to_todays(qdrant, monkeypatch):
    """After a rollback to a collection without the genre index, the cached answer is
    stale for up to five minutes; the refused query is rerun with today's filter."""
    client = retrieve_vector.get_qdrant_client()
    real = client.query_points
    filters = []

    async def strict(**kwargs):
        filters.append(kwargs["query_filter"])
        if kwargs["query_filter"].should:
            raise UnexpectedResponse(
                status_code=400, reason_phrase="Bad Request", headers=httpx.Headers(),
                content=b'{"status":{"error":"Bad request: Index required but not found'
                        b' for \\"genre\\""}}')
        return await real(**kwargs)

    monkeypatch.setattr(client, "query_points", strict)
    rows = await retrieve_vector._search_vector(
        CollectionScope("encyclicals"), [1.0, 0.0, 0.0, 0.0], 10, "query")
    assert [bool(f.should) for f in filters] == [True, False]
    assert qdrant_client._genre_indexed is None
    assert {row["document_id"] for row in rows} == (
        {ENC, EG} if qdrant == "before" else set())


async def test_another_failure_is_not_retried_without_the_new_value(qdrant, monkeypatch):
    """A timeout is not a missing index: rerunning without the genre branch would
    silently drop every rewritten papal passage."""
    client = retrieve_vector.get_qdrant_client()

    async def timeout(**kwargs):
        raise TimeoutError

    monkeypatch.setattr(client, "query_points", timeout)
    with pytest.raises(TimeoutError):
        await retrieve_vector._search_vector(
            CollectionScope("encyclicals"), [1.0, 0.0, 0.0, 0.0], 10, "query")
    assert qdrant_client._genre_indexed is True


async def test_another_bad_request_naming_genre_is_not_retried(qdrant, monkeypatch):
    client = retrieve_vector.get_qdrant_client()

    async def bad(**kwargs):
        raise UnexpectedResponse(status_code=400, reason_phrase="Bad Request",
                                 headers=httpx.Headers(), content=b'{"genre": "wrong type"}')

    monkeypatch.setattr(client, "query_points", bad)
    with pytest.raises(UnexpectedResponse):
        await retrieve_vector._search_vector(
            CollectionScope("encyclicals"), [1.0, 0.0, 0.0, 0.0], 10, "query")


def test_a_passage_read_by_two_old_keys_mid_rewrite_is_kept_once():
    """Between 5.1b.3's database apply and its alias switch, Evangelii Gaudium can come
    back from Qdrant as `encyclicals` and from Postgres as `apostolic-exhortations`."""
    from app.rag.steps import rrf
    from app.rag.steps.types import RetrievalPath

    def row(collection):
        return {"id": "eg", "content": "joy of the gospel", "collection": collection,
                "document_id": EG, "document_title": "Evangelii Gaudium"}

    other = {"id": "rn", "content": "workers", "collection": "encyclicals",
             "document_id": ENC, "document_title": "Rerum Novarum"}
    merged = rrf.run(
        {"encyclicals": [RetrievalPath(family="query", rows=[other, row("encyclicals")])]},
        {"apostolic-exhortations": [row("apostolic-exhortations")]}, 4, k=20,
    )
    assert [c.chunk_id for c in merged["apostolic-exhortations"]] == ["eg"]
    assert [c.chunk_id for c in merged["encyclicals"]] == ["rn"]
