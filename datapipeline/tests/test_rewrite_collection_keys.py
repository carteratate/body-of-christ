"""Corpus cleanup 5.1b.3: the keys stored in user rows (`scripts/rewrite_collection_keys.py`).

The rules are the web's restore rules (apps/web `canonicalSearchFilters`, tested in
`restoreScopes.test.ts`), so a restored search reads the same before and after."""
from __future__ import annotations

import json

import pytest

from scripts import rewrite_collection_keys as R
from tests import pg_corpus

VOCAB = ["encyclical", "apostolic-exhortation", "apostolic-letter", "apostolic-constitution",
         "motu-proprio", "other"]


def test_the_papal_vocabulary_is_the_webs():
    """The web generates its list from works.json the same way (collection-scopes.json)."""
    import registry

    web = json.load(open(pg_corpus.MIGRATIONS.parents[1] / "apps/web/src/lib/collection-scopes.json"))
    assert R.papal_genres(registry.current().works) == [g["value"] for g in web["papal"]["genres"]]


def test_keys_are_mapped_and_deduplicated_keeping_the_first():
    assert R.canonical_keys(["encyclicals", "bible", "papal-documents", "canon-law", "saints"]) == [
        "papal", "bible", "church-law", "saints"]


@pytest.mark.parametrize("keys, scopes, papal", [
    (["encyclicals", "bible"], {}, {"genres": ["encyclical"]}),
    (["encyclicals", "apostolic-exhortations"], {}, {"genres": ["encyclical", "apostolic-exhortation"]}),
    (["papal-documents"], {}, {"genres": ["apostolic-letter", "apostolic-constitution", "motu-proprio", "other"]}),
    (["encyclicals", "apostolic-exhortations", "papal-documents"], {}, None),
    (["encyclicals"], {"encyclicals": {"genres": ["encyclical", "apostolic-letter"], "issuers": ["pope-leo-xiii"]}},
     {"genres": ["encyclical", "apostolic-letter"], "issuers": ["pope-leo-xiii"]}),
    (["encyclicals", "papal-documents"], {"encyclicals": {"issuers": ["pope-leo-xiii"]}},
     {"genres": [g for g in VOCAB if g != "apostolic-exhortation"]}),
])
def test_old_papal_keys_become_a_papal_selection(keys, scopes, papal):
    filters = {"collections": keys, "quota": 4, "scopes": scopes} if scopes else {"collections": keys, "quota": 4}
    out = R.rewrite_filters(filters, VOCAB)
    assert out["collections"][0] == "papal" and "encyclicals" not in out["collections"]
    assert (out.get("scopes") or {}).get("papal") == papal
    assert not set(out.get("scopes") or {}) & set(R.RENAMES)
    assert out["quota"] == 4


def test_a_search_already_in_new_keys_is_left_as_it_is():
    filters = {"collections": ["papal", "bible"], "scopes": {"papal": {"genres": ["encyclical"]}},
               "collection_outcomes": {"papal": "results"}}
    assert R.rewrite_filters(filters, VOCAB) == filters


def test_merged_outcomes_follow_the_web():
    assert R.canonical_outcomes({"encyclicals": "results", "papal-documents": "no_candidates",
                                 "canon-law": "below_threshold", "bible": "results"}) == {
        "papal": "results", "church-law": "below_threshold", "bible": "results"}
    assert R.canonical_outcomes({"encyclicals": "results", "apostolic-exhortations": "retrieval_failed"}) == {
        "papal": "results_degraded"}
    assert R.canonical_outcomes({"encyclicals": "no_candidates", "papal-documents": "below_threshold"}) == {
        "papal": "below_threshold"}


# --------------------------------------------------------------------------- database

SCHEMA = """
    CREATE TABLE user_preferences (user_id uuid PRIMARY KEY, default_collections text[],
                                   default_quota int NOT NULL DEFAULT 4);
    CREATE TABLE searches (id uuid PRIMARY KEY, filters jsonb);
    CREATE TABLE guest_trials (id uuid PRIMARY KEY, filters jsonb);
    INSERT INTO user_preferences VALUES
      ('00000000-0000-0000-0000-000000000001', '{bible,encyclicals,papal-documents,canon-law}', 4),
      ('00000000-0000-0000-0000-000000000002', '{medieval}', 10),
      ('00000000-0000-0000-0000-000000000003', '{bible,papal}', 4);
    INSERT INTO searches VALUES
      ('00000000-0000-0000-0000-0000000000a1',
       '{"collections": ["encyclicals", "saints"], "quota": 4,
         "collection_outcomes": {"encyclicals": "results"}}'),
      ('00000000-0000-0000-0000-0000000000a2', '{"collections": ["bible"], "quota": 4}'),
      ('00000000-0000-0000-0000-0000000000a3', to_jsonb('{"collections": ["encyclicals"]}'::text));
    INSERT INTO guest_trials VALUES
      ('00000000-0000-0000-0000-0000000000b1', '{"collections": ["canon-law"], "quota": 3}');
"""


@pytest.fixture(scope="module")
def cluster():
    cluster, stop = pg_corpus.start()
    yield cluster
    stop()


async def _rows(conn):
    prefs = {str(r["user_id"])[-1]: list(r["default_collections"]) for r in await conn.fetch(
        "SELECT user_id, default_collections FROM user_preferences")}
    searches = {str(r["id"])[-2:]: r["filters"] for r in await conn.fetch(
        "SELECT id, filters::text AS filters FROM searches")}
    trials = {str(r["id"])[-2:]: r["filters"] for r in await conn.fetch(
        "SELECT id, filters::text AS filters FROM guest_trials")}
    return prefs, searches, trials


async def test_the_dry_run_writes_nothing_and_counts_without_content(cluster):
    database = cluster.new_database()
    cluster.psql(database, SCHEMA)
    conn = await cluster.connect(database)
    try:
        before = await _rows(conn)
        async with conn.transaction(readonly=True):
            report = await R.plan(conn, VOCAB)
        assert await _rows(conn) == before
        assert report["tables"]["user_preferences"] == {
            "rows": 3, "to_change": 2,
            "old_keys": {"canon-law": 1, "encyclicals": 1, "medieval": 1, "papal-documents": 1}}
        assert report["tables"]["searches"]["to_change"] == 1
        assert report["tables"]["searches"]["double_encoded_filters"] == 1
        assert report["tables"]["guest_trials"]["to_change"] == 1
        assert "grace" not in R.summary(report)
    finally:
        await conn.close()


async def test_apply_rewrites_in_place_and_leaves_unknown_and_encoded_rows(cluster):
    database = cluster.new_database()
    cluster.psql(database, SCHEMA)
    conn = await cluster.connect(database)
    try:
        async with conn.transaction():
            await R.apply_changes(conn, await R.plan(conn, VOCAB))
        prefs, searches, trials = await _rows(conn)
        assert prefs == {"1": ["bible", "papal", "church-law"], "2": ["theologians"],
                         "3": ["bible", "papal"]}
        assert json.loads(searches["a1"]) == {
            "collections": ["papal", "saints"], "quota": 4,
            "collection_outcomes": {"papal": "results"},
            "scopes": {"papal": {"genres": ["encyclical"]}}}
        assert json.loads(searches["a2"]) == {"collections": ["bible"], "quota": 4}
        assert json.loads(json.loads(searches["a3"])) == {"collections": ["encyclicals"]}
        assert json.loads(trials["b1"]) == {"collections": ["church-law"], "quota": 3}
        # A second run finds nothing to do.
        again = await R.plan(conn, VOCAB)
        assert all(not rows for rows in again["changes"].values())
    finally:
        await conn.close()
