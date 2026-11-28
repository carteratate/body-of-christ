"""Corpus cleanup 5.1b: the eight collection keys.

5.1b.1 accepted `papal`, `church-law` and `theologians` beside the old keys, 5.1b.3
rewrote every stored value, and 5.1b.4 removed the old keys: the API now accepts only
the eight. The acceptance checks are docs/corpus-cleanup/P4-P5-republish-expand.md,
items 5.1b.1 and 5.1b.4.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.models.preferences import DEFAULT_COLLECTIONS, PreferencesResponse
from app.rag import constants, dedup
from app.rag.search_plan import SearchPlanError, resolve_search_plan
from app.rag.steps import hyde_s25
from tests.pg_cluster import MIGRATIONS, local_cluster
from tests.test_corpus_facts_migration import (
    EARLIER, PRODUCTION_SCHEMA, SCHEMA_MIGRATION, VALIDATE_MIGRATION,
)

OLD_KEYS = ("encyclicals", "apostolic-exhortations", "papal-documents", "canon-law",
            "medieval")


# --- The vocabulary ----------------------------------------------------------------

def test_only_the_current_keys_are_valid():
    # The eight of 5.1b, and Roman Curia (5.3a), accepted before it is offered.
    assert constants.VALID_COLLECTIONS == constants.CANONICAL_COLLECTIONS == {
        "bible", "catechism", "church-fathers", "papal", "church-law", "summa",
        "theologians", "councils", "roman-curia"}


@pytest.mark.parametrize("old", OLD_KEYS)
def test_a_plan_treats_an_old_key_as_unknown(old):
    """Dropped like any unknown key, and refused when nothing else is left."""
    assert resolve_search_plan([old, "bible"], 4).collections == ("bible",)
    with pytest.raises(SearchPlanError) as raised:
        resolve_search_plan([old], 4)
    assert raised.value.code == "no_valid_collections"


def test_papal_takes_a_genre_and_issuer_scope():
    plan = resolve_search_plan(["papal"], 4, {"papal": {
        "genres": ["encyclical"], "issuers": ["pope-leo-xiii"]}})
    [scope] = plan.scopes
    assert scope.collection == "papal"
    assert plan.saved_scopes() == {"papal": {"genres": ["encyclical"],
                                             "issuers": ["pope-leo-xiii"]}}


# --- HyDE ---------------------------------------------------------------------------

@pytest.mark.parametrize("excluded, kinds", [
    (frozenset(), ["encyclical", "apostolic-exhortation", "other"]),
    (frozenset({"encyclical"}), ["apostolic-exhortation", "other"]),
    (constants.GENRES_BY_COLLECTION["papal"] - {"encyclical"}, ["encyclical"]),
    (constants.GENRES_BY_COLLECTION["papal"] - {"other"}, ["other"]),
    (frozenset({"apostolic-letter", "apostolic-constitution", "motu-proprio", "letter",
                "other"}), ["encyclical", "apostolic-exhortation"]),
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
    kinds = hyde_s25._PAPAL_KINDS
    assert calls == [(kinds["encyclical"].prompt, 400), (kinds["other"].prompt, 300)]
    assert "papal encyclical" in kinds["encyclical"].prompt
    assert "apostolic exhortation" in kinds["apostolic-exhortation"].prompt
    assert "papal letter, constitution, or bull" in kinds["other"].prompt


def test_the_renamed_keys_take_their_prompts_and_lengths():
    prompts, tokens = hyde_s25._COLLECTION_HYDE_PROMPTS, hyde_s25._COLLECTION_MAX_TOKENS
    assert "1983 Code of Canon Law" in prompts["church-law"]
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

def test_church_law_is_chapter_keyed():
    assert "church-law" in dedup._CHAPTER_KEYED_COLLECTIONS
    assert (dedup.cosine_threshold("church-law", True),
            dedup.cosine_threshold("theologians", True)) == (0.912, 0.931)


def test_the_renamed_keys_keep_footnotes_and_source_links():
    from app import corpus_lifecycle, footnotes, reader_access

    assert footnotes.has_footnotes("theologians", None)
    assert reader_access.source_url("church-law", None) == (
        "https://www.vatican.va/archive/cod-iuris-canonici/cic_index_en.html")
    latin = {"official_latin_urls": {"can/295": "https://www.vatican.va/x"}}
    assert corpus_lifecycle.read_elsewhere_url(
        "translation-in-preparation", "church-law", False, latin, "can/295",
    ) == "https://www.vatican.va/x"


@pytest.mark.parametrize("table", [
    "_PREFIXED_THRESHOLDS", "_CHAPTER_KEYED_COLLECTIONS"])
def test_no_key_table_still_names_an_old_key(table):
    assert not set(getattr(dedup, table)) & set(OLD_KEYS)


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


# --- Migration 0048 -----------------------------------------------------------------

NARROW = "0048_drop_legacy_collection_keys.sql"
# The keys 0048 allows: the eight collections of 5.1b.
EIGHT = ("bible", "catechism", "church-fathers", "councils", "summa", "papal",
         "church-law", "theologians")


def test_0048_refuses_the_old_keys_live_and_staged():
    def insert(cluster, table, key):
        cluster.sql(f"INSERT INTO {table} (id, collection, title) "
                    f"VALUES (gen_random_uuid(), '{key}', '{table} {key}')")

    def refused(cluster, table, key):
        try:
            insert(cluster, table, key)
        except AssertionError as error:
            return "documents_collection_check" in str(error)
        return False

    with local_cluster("tc-0048-") as cluster:
        cluster.sql(PRODUCTION_SCHEMA)
        cluster.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name,
                        "0046_collection_keys.sql")
        cluster.sql("SELECT create_corpus_staging()")
        insert(cluster, "staging.documents", "canon-law")

        # A leftover old key, here only in staging, makes the whole file fail and change
        # nothing, even run outside a transaction as by hand (psql -f).
        failed = subprocess.run(
            cluster.psql_args(), input=(MIGRATIONS / NARROW).read_text(),
            capture_output=True, text=True, timeout=30)
        assert failed.returncode != 0 and "documents_collection_check" in failed.stderr
        insert(cluster, "documents", "medieval")
        insert(cluster, "staging.documents", "medieval")

        cluster.sql("DELETE FROM documents; DELETE FROM staging.documents")
        cluster.migrate(NARROW)
        for table in ("documents", "staging.documents"):
            for key in EIGHT:
                insert(cluster, table, key)
            for key in (*OLD_KEYS, "roman-curia"):
                assert refused(cluster, table, key), (table, key)


WIDEN = "0049_add_roman_curia_collection.sql"


def test_0049_adds_roman_curia_live_and_staged():
    with local_cluster("tc-0049-") as cluster:
        cluster.sql(PRODUCTION_SCHEMA)
        cluster.migrate(*EARLIER, SCHEMA_MIGRATION.name, VALIDATE_MIGRATION.name,
                        "0046_collection_keys.sql", NARROW)
        cluster.sql("SELECT create_corpus_staging()")
        cluster.migrate(WIDEN)
        for table in ("documents", "staging.documents"):
            for key in sorted(constants.VALID_COLLECTIONS):
                cluster.sql(f"INSERT INTO {table} (id, collection, title) "
                            f"VALUES (gen_random_uuid(), '{key}', '{table} {key}')")
            for key in OLD_KEYS:
                failed = subprocess.run(
                    cluster.psql_args(), capture_output=True, text=True, timeout=30,
                    input=f"INSERT INTO {table} (id, collection, title) "
                          f"VALUES (gen_random_uuid(), '{key}', 'x');")
                assert "documents_collection_check" in failed.stderr, (table, key)
