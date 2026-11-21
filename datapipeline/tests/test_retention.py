"""4.1b step 13 (retention.py): the purge of retired rows nobody points at, and the
deletion of the Qdrant collection the switch left, against a real PostgreSQL with
production's user tables and an in-memory Qdrant."""
from __future__ import annotations

import asyncio
import json

import asyncpg
import pytest
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (CreateAlias, CreateAliasOperation, Distance, PointStruct,
                                  VectorParams)

import retention as R
from tests import pg_corpus

RELEASE = "rel-old"
USER = "00000000-0000-0000-0000-0000000000aa"
SEARCH = "00000000-0000-0000-0000-0000000000bb"
LIVE = "00000000-0000-0000-0000-00000000d001"    # live document
GONE = "00000000-0000-0000-0000-00000000d002"    # removed under rule A, nobody reads it
HELD = "00000000-0000-0000-0000-00000000d003"    # held for permission (ADR 0001)
READ = "00000000-0000-0000-0000-00000000d004"    # removed, someone's reading position


def p(n: int) -> str:
    return f"00000000-0000-0000-0000-0000000{n:05d}"


P_LIVE, P_HISTORY = p(1), p(2)          # current; an earlier text superseding into P_RETIRED_SUPER
P_TOMB, P_MOVED = p(10), p(11)          # removed (tombstone); moved (redirect); both deletable
P_SAVED, P_BOOKMARKED = p(12), p(13)    # in a saved search; bookmarked
P_FEEDBACK, P_GAP = p(14), p(15)        # named in feedback (set null); held council gap
P_RETIRED_SUPER = p(16)                 # retired, but a live row's superseded_by names it
P_GONE_1, P_GONE_2 = p(20), p(21)
P_HELD = p(30)
P_READ = p(40)                          # in the chapter a reading position names
DELETABLE = {P_TOMB, P_MOVED, P_GONE_1, P_GONE_2}

SEED = f"""
    SELECT public.drop_corpus_staging();
    INSERT INTO corpus_publishes (id, collections, qdrant_collection,
                                  previous_qdrant_collection, staged_at, applied_at,
                                  alias_switched_at, cleaned_up_at)
    VALUES ('{RELEASE}', ARRAY['medieval'], 'chunks-{RELEASE}', 'old-points',
            now() - interval '16 days', now() - interval '15 days',
            now() - interval '15 days', now() - interval '15 days');
    INSERT INTO documents (id, collection, title, author, translation, metadata, retired_at)
    VALUES ('{LIVE}', 'medieval', 'Live', 'A', '', '{{}}', NULL),
           ('{GONE}', 'medieval', 'Gone', 'B', '', '{{}}', now()),
           ('{HELD}', 'medieval', 'Held', 'C', '', '{{"url": "https://example.org/held"}}', now()),
           ('{READ}', 'medieval', 'Read', 'D', '', '{{}}', now());
    INSERT INTO document_works (document_id, work_key, ordinal, title)
    VALUES ('{GONE}', 'w1', 1, 'Gone work');
    INSERT INTO document_contents (document_id, ordinal, depth, node_key, kind, label,
                                   short_label, chapter_key)
    VALUES ('{GONE}', 1, 0, 'n1', 'chapter', 'One', 'One', 'g');
    INSERT INTO chunks (id, document_id, position, anchor, chapter_key, chapter_label,
                        content, retired_at, searchable, superseded_by)
    VALUES ('{P_LIVE}', '{LIVE}', 0, 'c1/p1', 'c1', 'One', 'live', NULL, true, NULL),
           ('{P_HISTORY}', '{LIVE}', 1, 'c1/p1/history-1990', 'c1', 'One', 'earlier',
            NULL, false, NULL),
           ('{P_TOMB}', '{LIVE}', -1000000, 'c2/p1', 'c2', 'Two',
            (SELECT string_agg(md5(i::text), ' ') FROM generate_series(1, 400) i),
            now(), true, NULL),
           ('{P_MOVED}', '{LIVE}', -1000001, 'c1/p9', 'c1', 'One', 'moved', now(), true, NULL),
           ('{P_SAVED}', '{LIVE}', -1000002, 'c3/p1', 'c3', 'Three', 'saved', now(), true, NULL),
           ('{P_BOOKMARKED}', '{LIVE}', -1000003, 'c3/p2', 'c3', 'Three', 'bm', now(), true, NULL),
           ('{P_FEEDBACK}', '{LIVE}', -1000004, 'c3/p3', 'c3', 'Three', 'fb', now(), true, NULL),
           ('{P_GAP}', '{LIVE}', -1000005, 'c4/p1', 'c4', 'Four', 'gap', now(), true, NULL),
           ('{P_RETIRED_SUPER}', '{LIVE}', -1000006, 'c5/p1', 'c5', 'Five', 'old current',
            now(), true, NULL),
           ('{P_GONE_1}', '{GONE}', -1000000, 'g1', 'g', 'G', 'gone 1', now(), true, NULL),
           ('{P_GONE_2}', '{GONE}', -1000001, 'g2', 'g', 'G', 'gone 2', now(), true, NULL),
           ('{P_HELD}', '{HELD}', -1000000, 'h1', 'h', 'H', 'held', now(), true, NULL),
           ('{P_READ}', '{READ}', -1000000, 'r1', 'r', 'R', 'read', now(), true, NULL);
    UPDATE chunks SET superseded_by = '{P_RETIRED_SUPER}' WHERE id = '{P_HISTORY}';
    SELECT public.refresh_document_outline(id) FROM documents;

    INSERT INTO corpus_tombstones (entity, id, document_id, retired_at, publish_id,
        removal_key, rule, reason_code, public_reason, snapshot)
    SELECT 'passage', c.id, c.document_id, now(), '{RELEASE}', 'rm-' || c.anchor,
           CASE WHEN c.id = '{P_GAP}' THEN 'other' ELSE 'A' END,
           CASE WHEN c.id = '{P_GAP}' THEN 'translation-in-preparation'
                WHEN c.document_id = '{HELD}' THEN 'awaiting-permission' ELSE 'rule-a' END,
           'Removed.', jsonb_build_object('reference', c.anchor)
    FROM chunks c WHERE c.retired_at IS NOT NULL AND c.id <> '{P_MOVED}';
    UPDATE corpus_tombstones SET rule = 'other' WHERE reason_code = 'awaiting-permission';
    INSERT INTO corpus_tombstones (entity, id, document_id, retired_at, publish_id,
        removal_key, rule, reason_code, public_reason, snapshot)
    VALUES ('document', '{GONE}', '{GONE}', now(), '{RELEASE}', 'rm-gone', 'A', 'rule-a',
            'Removed.', '{{}}'),
           ('document', '{HELD}', '{HELD}', now(), '{RELEASE}', 'rm-held', 'other',
            'awaiting-permission', 'Held.', '{{}}'),
           ('document', '{READ}', '{READ}', now(), '{RELEASE}', 'rm-read', 'A', 'rule-a',
            'Removed.', '{{}}');
    INSERT INTO corpus_redirects (entity, old_id, old_document_id, old_anchor, new_id,
                                  new_document_id, new_anchor, kind, publish_id)
    VALUES ('passage', '{P_MOVED}', '{LIVE}', 'c1/p9', '{P_LIVE}', '{LIVE}', 'c1/p1',
            'merged', '{RELEASE}');

    INSERT INTO auth.users (id) VALUES ('{USER}');
    INSERT INTO searches (id, user_id) VALUES ('{SEARCH}', '{USER}');
    INSERT INTO retrievals (search_id, chunk_id, rank) VALUES
        ('{SEARCH}', '{P_SAVED}', 1), ('{SEARCH}', '{P_LIVE}', 2);
    INSERT INTO bookmarks (user_id, chunk_id) VALUES ('{USER}', '{P_BOOKMARKED}');
    INSERT INTO product_feedback (user_id, chunk_id) VALUES ('{USER}', '{P_FEEDBACK}');
    INSERT INTO reading_progress (user_id, document_id, chapter_key) VALUES
        ('{USER}', '{READ}', 'r');
"""


@pytest.fixture(scope="module")
def cluster():
    cluster, stop = pg_corpus.start()
    yield cluster
    stop()


@pytest.fixture()
def db(cluster):
    name = cluster.new_database()
    pg_corpus.use_production_user_tables(cluster, name)
    cluster.psql(name, SEED, single=True)
    return cluster, name


async def _conn(db) -> asyncpg.Connection:
    cluster, name = db
    return await cluster.connect(name)


async def _ids(conn, table: str) -> set[str]:
    return {r["id"] for r in await conn.fetch(f"SELECT id::text AS id FROM {table}")}


async def _user_rows(conn) -> dict[str, int]:
    return {t: await conn.fetchval(f"SELECT count(*) FROM {t}") for t in
            ("retrievals", "bookmarks", "product_feedback", "reading_progress",
             "corpus_tombstones", "corpus_redirects")}


# --------------------------------------------------------------------------- dry run

async def test_dry_run_counts_what_goes_and_what_stays_and_writes_nothing(db):
    conn = await _conn(db)
    try:
        before = (await _ids(conn, "chunks"), await _ids(conn, "documents"),
                  await _user_rows(conn))
        plan = await R.read_plan(conn, RELEASE)
        after = (await _ids(conn, "chunks"), await _ids(conn, "documents"),
                 await _user_rows(conn))
    finally:
        await conn.close()
    assert before == after
    assert plan.refusals == []
    assert (plan.retired_passages, plan.retired_documents) == (11, 3)
    assert set(plan.passages) == DELETABLE
    assert plan.documents == [GONE]
    assert {i: set(r) for i, r in plan.kept_passages.items()} == {
        P_SAVED: {"users: public.retrievals.chunk_id (cascade)"},
        P_BOOKMARKED: {"users: public.bookmarks.chunk_id (cascade)"},
        P_FEEDBACK: {"users: public.product_feedback.chunk_id (set null)"},
        P_GAP: {"held: translation-in-preparation (ADR 0001)"},
        P_RETIRED_SUPER: {"corpus: public.chunks.superseded_by (set null)"},
        P_HELD: {"held: awaiting-permission (ADR 0001)"},
        P_READ: {"users: public.reading_progress (its chapter)"},
    }
    assert {i: set(r) for i, r in plan.kept_documents.items()} == {
        HELD: {"its passages that stay", "held: awaiting-permission (ADR 0001)"},
        READ: {"users: public.reading_progress.document_id (cascade)",
               "its passages that stay"},
    }
    w = plan.wal
    assert w.passage_rows == 4 and 1 <= w.passage_pages <= 4
    assert w.toast_pages >= 1                       # P_TOMB's 13,000 characters
    assert w.document_rows == 3                     # GONE, its work and its contents node
    assert w.purge_bytes > 0 and w.vacuum_bytes > 0
    text = "\n".join(R.describe(plan))
    assert "would delete: 4" in text and "A live run now would pass" in text


async def test_dry_run_reads_the_foreign_keys_so_a_new_table_counts(db):
    """A table added later (Studies) that points at a passage keeps it, whatever its
    ON DELETE action."""
    cluster, name = db
    cluster.psql(name, f"""
        CREATE TABLE study_blocks (id serial PRIMARY KEY,
            chunk_id uuid REFERENCES chunks(id) ON DELETE SET NULL);
        INSERT INTO study_blocks (chunk_id) VALUES ('{P_TOMB}');""")
    conn = await _conn(db)
    try:
        plan = await R.read_plan(conn, RELEASE)
    finally:
        await conn.close()
    assert P_TOMB not in plan.passages
    assert plan.kept_passages[P_TOMB] == {"users: public.study_blocks.chunk_id (set null)": 1}


async def test_dry_run_through_the_cli_prints_the_plan(db, monkeypatch, capsys):
    import publish

    async def connect():
        return await _conn(db)
    monkeypatch.setattr(publish, "_connect", connect)
    args = publish.build_parser().parse_args(["purge-retired", "--release", RELEASE])
    assert await publish.purge_retired(args) == 0
    out = capsys.readouterr().out
    assert "dry run, nothing written" in out
    assert "public.reading_progress.document_id (cascade)" in out


# --------------------------------------------------------------------------- refusals

@pytest.mark.parametrize(("sql", "reason"), [
    (f"UPDATE corpus_publishes SET applied_at = now() - interval '13 days' "
     f"WHERE id = '{RELEASE}'", "rollback window of 'rel-old' is open"),
    (f"UPDATE corpus_publishes SET rolled_back_at = now() WHERE id = '{RELEASE}'",
     "was rolled back"),
    ("INSERT INTO corpus_publishes (id, collections, qdrant_collection, staged_at) "
     "VALUES ('rel-next', ARRAY['bible'], 'chunks-rel-next', now())",
     "publish 'rel-next' is open"),
    ("INSERT INTO corpus_publishes (id, collections, qdrant_collection, staged_at, "
     "applied_at, cleaned_up_at) VALUES ('rel-new', ARRAY['bible'], 'chunks-rel-new', "
     "now(), now() - interval '2 days', now())", "'rel-new' is inside its own rollback"),
    ("SELECT public.create_corpus_staging()", "staging tables exist"),
])
async def test_a_live_run_refuses_and_deletes_nothing(db, sql, reason):
    cluster, name = db
    cluster.psql(name, sql)
    conn = await _conn(db)
    try:
        before = await _ids(conn, "chunks")
        with pytest.raises(R.RetentionRefused, match=reason):
            await R.execute(conn, RELEASE, disk_free_bytes=1 << 40)
        assert await _ids(conn, "chunks") == before
    finally:
        await conn.close()


EARLY = "Carter, 21 Nov 2026 (#192)"


async def test_close_window_early_lifts_only_the_window_refusal(db, capsys):
    """--close-window-early: inside the window the purge runs, and says so; another
    refusal (an open publish) still stops it."""
    cluster, name = db
    cluster.psql(name, f"UPDATE corpus_publishes SET applied_at = now() - interval '1 day' "
                       f"WHERE id = '{RELEASE}'")
    conn = await _conn(db)
    try:
        plan = await R.read_plan(conn, RELEASE)
        assert any("rollback window of 'rel-old' is open" in r for r in plan.refusals)
        early = await R.read_plan(conn, RELEASE, EARLY)
        assert early.refusals == []
        assert early.early_close.startswith("EARLY CLOSE: the rollback window of 'rel-old'")
        assert EARLY in early.early_close and early.early_close in R.describe(early)

        cluster.psql(name, "INSERT INTO corpus_publishes (id, collections, qdrant_collection, "
                           "staged_at) VALUES ('rel-next', ARRAY['bible'], 'x', now())")
        with pytest.raises(R.RetentionRefused, match="publish 'rel-next' is open"):
            await R.execute(conn, RELEASE, disk_free_bytes=1 << 40, early_close=EARLY)
        cluster.psql(name, "DELETE FROM corpus_publishes WHERE id = 'rel-next'")

        lines = []
        result = await R.execute(conn, RELEASE, disk_free_bytes=1 << 40, early_close=EARLY,
                                 progress=lines.append)
        assert result.passages == 4 and lines[0] == early.early_close
    finally:
        await conn.close()


async def test_close_window_early_needs_a_named_decision():
    import publish

    with pytest.raises(SystemExit):
        publish.build_parser().parse_args(
            ["purge-retired", "--release", RELEASE, "--close-window-early", "yes"])


async def test_close_window_early_is_not_mentioned_once_the_window_has_closed(db):
    conn = await _conn(db)
    try:
        assert (await R.read_plan(conn, RELEASE, EARLY)).early_close is None
    finally:
        await conn.close()


async def test_a_live_run_refuses_without_enough_disk(db):
    conn = await _conn(db)
    try:
        before = await _ids(conn, "chunks")
        for free in (None, 1 << 30):
            with pytest.raises(R.RetentionRefused, match="free on the database disk"):
                await R.execute(conn, RELEASE, disk_free_bytes=free)
        assert await _ids(conn, "chunks") == before
    finally:
        await conn.close()


async def test_the_cli_asks_the_lock_for_apply_before_any_write(db, monkeypatch, tmp_path):
    import publish
    import publish_lock

    monkeypatch.setattr(publish_lock, "settings_targets", lambda: publish_lock.WriteTargets(
        "postgresql://u:p@db.example.supabase.co/postgres", "https://q.example.qdrant.io"))

    async def connect():
        return await _conn(db)
    monkeypatch.setattr(publish, "_connect", connect)
    lock = tmp_path / "PUBLISH_LOCK.json"
    args = publish.build_parser().parse_args(
        ["purge-retired", "--release", RELEASE, "--execute", "--disk-free-gb", "100"])
    # Another step for every collection, or apply for the release's one collection only:
    # the purge is corpus-wide, so neither approves it.
    for entry in ({"collection": "all", "release": RELEASE, "steps": ["rollback"]},
                  {"collection": "medieval", "release": RELEASE, "steps": ["apply"]}):
        lock.write_text(json.dumps({"reason": "test", "approved_applies": [entry]}))
        with pytest.raises(ValueError, match="step 'apply', collection 'all'"):
            await publish.purge_retired(args, lock)
    conn = await _conn(db)
    try:
        assert DELETABLE <= await _ids(conn, "chunks")
    finally:
        await conn.close()


# --------------------------------------------------------------------------- execute

async def test_execute_deletes_only_what_nobody_points_at(db):
    conn = await _conn(db)
    try:
        users_before = await _user_rows(conn)
        lines = []
        result = await R.execute(conn, RELEASE, disk_free_bytes=1 << 40, batch_size=2,
                                 progress=lines.append)
        assert (result.passages, result.documents, result.newly_kept) == (4, 1, 0)
        assert result.batches == len(lines) == 3        # 2 of passages, 1 of documents
        assert not DELETABLE & await _ids(conn, "chunks")
        assert await _ids(conn, "documents") == {LIVE, HELD, READ}
        # Nothing a user made is gone, and every notice and redirect is kept.
        assert await _user_rows(conn) == users_before
        assert await conn.fetchval(
            f"SELECT superseded_by::text FROM chunks WHERE id = '{P_HISTORY}'") == P_RETIRED_SUPER
        # The document's own parts went with it.
        for table in ("document_works", "document_contents", "document_chapters"):
            assert not await conn.fetchval(
                f"SELECT count(*) FROM {table} WHERE document_id = '{GONE}'")
        # Outlines were refreshed after 0037's trigger cleared them.
        assert await conn.fetchval(
            f"SELECT chunk_count FROM documents WHERE id = '{LIVE}'") == 2
        # A deleted passage's tombstone keeps its location for old reader links.
        snapshot = await conn.fetchval(
            f"SELECT snapshot FROM corpus_tombstones WHERE id = '{P_TOMB}'")
        assert json.loads(snapshot) == {"reference": "c2/p1", "anchor": "c2/p1",
                                        "chapter_key": "c2"}
        # A second run finds nothing more.
        again = await R.read_plan(conn, RELEASE)
        assert (again.passages, again.documents) == ([], [])
    finally:
        await conn.close()


async def test_each_batch_commits_on_its_own(db):
    """A batch that cannot take its rows' locks within lock_timeout rolls back alone; the
    batches before it stay committed, and a rerun picks up what is left."""
    conn = await _conn(db)
    holder = await _conn(db)
    plan = await R.read_plan(conn, RELEASE)
    second = plan.passages[2:4]
    try:
        async def hold_second_batch(number):
            if number == 1:
                await holder.execute("BEGIN")
                await holder.execute(
                    "SELECT 1 FROM chunks WHERE id = ANY($1::uuid[]) FOR UPDATE", second)

        with pytest.raises(asyncpg.LockNotAvailableError):
            await R.execute(conn, RELEASE, disk_free_bytes=1 << 40, batch_size=2,
                            progress=lambda line: None, after_batch=hold_second_batch)
        await holder.execute("ROLLBACK")
        left = await _ids(conn, "chunks")
        assert not set(plan.passages[:2]) & left        # batch 1 committed
        assert set(plan.passages[2:]) <= left           # batch 2 rolled back, 3 never ran
        result = await R.execute(conn, RELEASE, disk_free_bytes=1 << 40, batch_size=2,
                                 progress=lambda line: None)
        assert (result.passages, result.documents) == (2, 1)
    finally:
        await holder.close()
        await conn.close()


async def test_a_row_someone_points_at_after_the_plan_stays(db):
    """The batch checks again under its row locks: a bookmark made between the plan and
    the batch keeps its passage, and is not cascaded away."""
    conn = await _conn(db)
    plan = await R.read_plan(conn, RELEASE)
    late = plan.passages[1]                         # in the live document, batch 2
    assert late in {P_TOMB, P_MOVED}
    try:
        async def bookmark(number):
            if number == 1:
                await conn.execute("INSERT INTO bookmarks (user_id, chunk_id) VALUES ($1, $2)",
                                   USER, late)

        result = await R.execute(conn, RELEASE, disk_free_bytes=1 << 40, batch_size=1,
                                 progress=lambda line: None, after_batch=bookmark)
        assert (result.newly_kept, result.passages, result.documents) == (1, 3, 1)
        assert late in await _ids(conn, "chunks")
        assert await conn.fetchval("SELECT count(*) FROM bookmarks WHERE chunk_id = $1",
                                   late) == 1
    finally:
        await conn.close()


async def test_each_batch_reads_the_foreign_keys_again(db):
    """A table that starts pointing at passages between batches keeps its passage."""
    conn = await _conn(db)
    plan = await R.read_plan(conn, RELEASE)
    late = plan.passages[1]
    try:
        async def add_table(number):
            if number == 1:
                await conn.execute(f"""
                    CREATE TABLE study_blocks (id serial PRIMARY KEY,
                        chunk_id uuid REFERENCES chunks(id) ON DELETE SET NULL);
                    INSERT INTO study_blocks (chunk_id) VALUES ('{late}')""")

        result = await R.execute(conn, RELEASE, disk_free_bytes=1 << 40, batch_size=1,
                                 progress=lambda line: None, after_batch=add_table)
        assert result.newly_kept == 1
        assert await conn.fetchval("SELECT chunk_id::text FROM study_blocks") == late
    finally:
        await conn.close()


async def test_a_user_row_inserted_during_a_batch_waits_and_then_fails(db):
    """While a batch holds its rows, a new user row pointing at one waits for the commit,
    then fails on its foreign key: it can never be cascaded away unseen."""
    conn = await _conn(db)
    other = await _conn(db)
    try:
        target = (await R.read_plan(conn, RELEASE)).passages[0]
        await conn.execute("BEGIN")
        await conn.execute("SELECT 1 FROM chunks WHERE id = $1 FOR UPDATE", target)
        insert = asyncio.create_task(other.execute(
            "INSERT INTO bookmarks (user_id, chunk_id) VALUES ($1, $2)", USER, target))
        await asyncio.sleep(0.3)
        assert not insert.done()
        await conn.execute("DELETE FROM chunks WHERE id = $1", target)
        await conn.execute("COMMIT")
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await insert
    finally:
        await other.close()
        await conn.close()


# --------------------------------------------------------------------------- Qdrant

async def _qdrant(alias_on: str = "chunks-rel-old") -> AsyncQdrantClient:
    q = AsyncQdrantClient(location=":memory:")
    for name in ("old-points", "chunks-rel-old"):
        await q.create_collection(name, vectors_config=VectorParams(size=2,
                                                                    distance=Distance.COSINE))
        await q.upsert(name, points=[PointStruct(id=P_LIVE, vector=[1.0, 0.0])])
    await q.update_collection_aliases(change_aliases_operations=[CreateAliasOperation(
        create_alias=CreateAlias(collection_name=alias_on, alias_name="live"))])
    return q


async def test_the_old_collection_is_deleted_only_when_named_and_unused(db):
    q = await _qdrant()
    conn = await _conn(db)
    try:
        old = await R.old_collection(conn, q, RELEASE, "live")
        assert (old.name, old.points, old.problems) == ("old-points", 1, [])
        with pytest.raises(R.RetentionRefused, match="--confirm must name"):
            await R.drop_old_collection(conn, q, RELEASE, "live", "chunks-rel-old")
        assert await q.collection_exists("old-points")
        assert await R.drop_old_collection(conn, q, RELEASE, "live", "old-points") == (
            "old-points", True)
        assert not await q.collection_exists("old-points")
        assert await q.collection_exists("chunks-rel-old")
        # A retry (the first response lost) finds it gone and succeeds.
        assert await R.drop_old_collection(conn, q, RELEASE, "live", "old-points") == (
            "old-points", False)
    finally:
        await conn.close()
        await q.close()


async def test_the_old_collection_can_go_early_by_decision(db):
    cluster, name = db
    cluster.psql(name, f"UPDATE corpus_publishes SET applied_at = now() - interval '1 day' "
                       f"WHERE id = '{RELEASE}'")
    q = await _qdrant()
    conn = await _conn(db)
    try:
        with pytest.raises(R.RetentionRefused, match="rollback window"):
            await R.drop_old_collection(conn, q, RELEASE, "live", "old-points")
        assert await R.drop_old_collection(conn, q, RELEASE, "live", "old-points",
                                           EARLY) == ("old-points", True)
    finally:
        await conn.close()
        await q.close()


async def test_the_old_collection_stays_while_the_alias_or_a_publish_uses_it(db):
    cluster, name = db
    q = await _qdrant(alias_on="old-points")
    conn = await _conn(db)
    try:
        old = await R.old_collection(conn, q, RELEASE, "live")
        assert "alias 'live' points at 'old-points'" in old.problems
        cluster.psql(name, f"UPDATE corpus_publishes SET applied_at = now() "
                           f"WHERE id = '{RELEASE}'")
        with pytest.raises(R.RetentionRefused, match="rollback window"):
            await R.drop_old_collection(conn, q, RELEASE, "live", "old-points")
        assert await q.collection_exists("old-points")
    finally:
        await conn.close()
        await q.close()
