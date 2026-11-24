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
    INSERT INTO documents (id, collection, title, retired_at) VALUES
      ('00000000-0000-0000-0000-0000000000d1', 'encyclicals', 'Held', now()),
      ('00000000-0000-0000-0000-0000000000d2', 'encyclicals', 'Live', NULL),
      ('00000000-0000-0000-0000-0000000000d3', 'papal', 'New', NULL);
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


# The database after the publish apply: no live document under an old key, and no
# double-encoded filters (which a write run refuses).
AFTER_APPLY = SCHEMA.replace("'encyclicals', 'Live', NULL", "'papal', 'Live', NULL").replace(
    "to_jsonb('{\"collections\": [\"encyclicals\"]}'::text)", "'{}'")


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
        assert report["tables"]["documents"] == {
            "retired_to_change": {"encyclicals": 1}, "live_still_under_old_keys": {"encyclicals": 1}}
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
        # The retired document is rekeyed; a live one is the publish's to rewrite.
        assert {str(r["id"])[-2:]: r["collection"] for r in await conn.fetch(
            "SELECT id, collection FROM documents WHERE id::text LIKE '00000000-%'")} == {"d1": "papal", "d2": "encyclicals",
                                                         "d3": "papal"}
        # A second run finds nothing to do.
        again = await R.plan(conn, VOCAB)
        assert all(not rows for rows in again["changes"].values())
    finally:
        await conn.close()


async def test_a_row_changed_after_the_read_is_never_overwritten(cluster):
    """A preference autosave between the plan and the write aborts the whole run."""
    database = cluster.new_database()
    cluster.psql(database, SCHEMA)
    conn = await cluster.connect(database)
    try:
        report = await R.plan(conn, VOCAB)
        await conn.execute("UPDATE user_preferences SET default_collections = '{bible}' "
                           "WHERE user_id = '00000000-0000-0000-0000-000000000001'")
        before = await _rows(conn)
        with pytest.raises(R.ChangedMeanwhile):
            async with conn.transaction():
                await R.apply_changes(conn, report)
        assert await _rows(conn) == before
    finally:
        await conn.close()


# --------------------------------------------------------------------------- 2.2w scope

def test_the_live_snapshot_reads_a_publish_under_either_key(tmp_path):
    """A release report reads the live rows a publish covers whichever key they are
    filed under: an old key's rows for a publish of the old key (a release staged
    before 5.1b.3 merged) and of its new key, and only those."""
    import gzip

    from checks.health import SNAPSHOT_FILE, load_snapshot

    rows = [{"id": "p1", "document_id": "unregistered-1", "collection": "medieval", "title": "T",
             "anchor": "a", "position": 0, "content": "x"},
            {"id": "p2", "document_id": "unregistered-2", "collection": "summa", "title": "S",
             "anchor": "a", "position": 0, "content": "y"}]
    with gzip.open(tmp_path / SNAPSHOT_FILE, "wt", encoding="utf-8") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)
    for published in (("medieval",), ("theologians",)):
        assert {c: [d.id for d in ds] for c, ds in load_snapshot(
            str(tmp_path), None, published=published).items()} == {"medieval": ["unregistered-1"]}
    assert load_snapshot(str(tmp_path), None, published=("papal",)) == {}


def test_malformed_saved_filters_do_not_stop_the_rewrite():
    out = R.rewrite_filters({"collections": ["encyclicals", {"x": 1}], "scopes": 7}, VOCAB)
    assert out["collections"] == ["papal", {"x": 1}]
    assert out["scopes"] == {"papal": {"genres": ["encyclical"]}}


def test_a_source_published_in_part_is_checked_whole(monkeypatch):
    """After 5.1b.3 the medieval source feeds `theologians` and Boethius `church-fathers`.
    A release staging one of them has its coverage checks see the other part as built,
    and never a document of a collection it stages, so a dropped one stays missing."""
    import publication
    from model import Document
    from release import staged

    boethius = Document(id=publication.BOETHIUS_DOCUMENT_ID, collection="medieval", title="B")
    anselm = Document(id="anselm", collection="medieval", title="A")
    monkeypatch.setitem(publication.SOURCE_BUILDS, "medieval", lambda: [boethius, anselm])
    assert staged._whole_sources(("church-fathers", "medieval"), ["church-fathers"]) == {
        "medieval": [anselm]}
    assert staged._whole_sources(("medieval",), ["theologians"]) == {"medieval": [boethius]}
    assert staged._whole_sources(("church-fathers", "medieval"),
                                 ["church-fathers", "theologians"]) == {}
    assert staged._whole_sources(("encyclicals",), ["papal"]) == {}
    assert staged._whole_sources(("medieval",), ["medieval"]) == {}


def test_coverage_checks_judge_the_staged_documents_and_build_only_the_rest():
    from model import Document
    from release.report import with_supplement

    staged = Document(id="boethius", collection="medieval", title="Staged copy")
    rebuilt = Document(id="boethius", collection="medieval", title="Rebuilt copy")
    anselm = Document(id="anselm", collection="medieval", title="Proslogium")
    out = with_supplement({"medieval": [staged]}, {"medieval": [rebuilt, anselm]})
    assert [d.title for d in out["medieval"]] == ["Staged copy", "Proslogium"]
    assert with_supplement({"summa": []}, {}) == {"summa": []}


def test_a_malformed_outcome_takes_part_in_no_merge():
    assert R.canonical_outcomes({"encyclicals": "results", "papal-documents": ["x"]}) == {
        "papal": "results"}
    assert R.canonical_outcomes({"encyclicals": ["x"], "papal-documents": ["y"]}) == {"papal": ["x"]}


async def test_the_write_run_locks_and_completes(cluster):
    database = cluster.new_database()
    cluster.psql(database, AFTER_APPLY)
    conn = await cluster.connect(database)
    try:
        assert await R._run(conn, True, VOCAB) == 0
        assert await R._run(conn, False, VOCAB) == 0
    finally:
        await conn.close()


def test_a_release_of_all_old_keys_asks_for_the_all_entry(monkeypatch):
    import publication
    import publish

    asked = []
    monkeypatch.setattr(publication, "publish_lock_guard",
                        lambda step, lock_path=None: lambda c, r: asked.append(c))
    # The ten keys an `all` release staged before 5.1b.3 records (republish-2026-10's),
    # written out: the sources have grown since (5.4's church-law).
    old_all = ["apostolic-exhortations", "bible", "canon-law", "catechism",
               "church-fathers", "councils", "encyclicals", "medieval", "papal-documents",
               "summa"]
    publish.guard_publish("rollback", old_all, "old-all")
    publish.guard_publish("rollback", sorted(publication.SOURCE_BUILDS), "sources-all")
    publish.guard_publish("rollback", sorted(publication.SOURCE_ADAPTERS), "new-all")
    publish.guard_publish("rollback", ["papal"], "one")
    assert asked == ["all", "all", "all", "papal"]


async def test_a_guest_claim_during_the_run_is_waited_for_not_deadlocked(cluster):
    """A claim locks its trial, then inserts the search; the run locks the trials first,
    so it waits for the claim and then rewrites the search the claim wrote."""
    import asyncio

    database = cluster.new_database()
    cluster.psql(database, AFTER_APPLY)
    claim = await cluster.connect(database)
    run = await cluster.connect(database)
    try:
        tx = claim.transaction()
        await tx.start()
        await claim.execute("SELECT 1 FROM guest_trials WHERE id = $1::uuid FOR UPDATE",
                            "00000000-0000-0000-0000-0000000000b1")
        repair = asyncio.create_task(R._run(run, True, VOCAB))
        await asyncio.sleep(0.5)
        assert not repair.done()
        await claim.execute("""INSERT INTO searches VALUES ('00000000-0000-0000-0000-0000000000a9',
                               '{"collections": ["canon-law"], "quota": 3}')""")
        await claim.execute("UPDATE guest_trials SET filters = filters WHERE id = $1::uuid",
                            "00000000-0000-0000-0000-0000000000b1")
        await tx.commit()
        assert await asyncio.wait_for(repair, 10) == 0
        claimed = await run.fetchval(
            "SELECT filters::text FROM searches WHERE id = '00000000-0000-0000-0000-0000000000a9'")
        assert json.loads(claimed)["collections"] == ["church-law"]
    finally:
        await claim.close()
        await run.close()


async def test_apply_refuses_while_live_documents_carry_old_keys(cluster):
    """The script runs after the publish apply; before it, a live document still under
    an old key means the order is wrong."""
    database = cluster.new_database()
    cluster.psql(database, SCHEMA.replace(
        "to_jsonb('{\"collections\": [\"encyclicals\"]}'::text)", "'{}'"))
    conn = await cluster.connect(database)
    try:
        assert await R._run(conn, True, VOCAB) == 1
        assert await conn.fetchval(
            "SELECT collection FROM documents WHERE id = '00000000-0000-0000-0000-0000000000d1'") == "encyclicals"
    finally:
        await conn.close()
