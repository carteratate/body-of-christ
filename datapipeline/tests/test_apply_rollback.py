"""2.2w part (b): apply, switch, rollback, cleanup and the retire-only procedure, against a
real PostgreSQL and an in-memory Qdrant (docs/corpus-cleanup/P2-P3-schema-reader-policy.md,
item 2.2w, acceptance checks)."""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import replace

import asyncpg
import pytest

import reader_access
from model import Work
from publication import StageRequest
from release.staged import staged_content_sha256
from tests import pg_corpus
from tests.stage_world import DOC_A, DOC_B, DOC_S, LIVE, World, contents_tree, passage, pid
from writers import apply as A

RELEASE = "test-release"
STAGE = StageRequest(release=RELEASE, collections=("medieval",))
USER = "00000000-0000-0000-0000-0000000000aa"


@pytest.fixture(scope="module")
def cluster():
    cluster, stop = pg_corpus.start()
    yield cluster
    stop()


@pytest.fixture()
async def world(cluster, tmp_path, monkeypatch):
    # Neither test document is in the rights inventory; treat both as cleared.
    monkeypatch.setattr(reader_access, "access_for", lambda document_id: "full")
    w = World(cluster, cluster.new_database(), tmp_path)
    await w.seed()
    w.snapshots = str(tmp_path / "snapshots")
    return w


def _doc(world, document_id):
    return next(d for d in world.build if d.id == document_id)


def _removal(**entry) -> dict:
    return {"collection": "medieval", "church_act": None, "anchor": None,
            "passage_id": None, **entry}


async def _sql(world, sql, *args):
    conn = await world.connect()
    try:
        return await conn.execute(sql, *args)
    finally:
        await conn.close()


async def _stage(world, request=STAGE):
    """Stage, then record a report hash as a passing report would."""
    await world.runner().stage(request)
    conn = await world.connect()
    try:
        content = await staged_content_sha256(conn)
        await conn.execute("UPDATE corpus_publishes SET report_sha256 = $2 WHERE id = $1",
                           request.release, f"report:{content}")
    finally:
        await conn.close()


async def _apply(world, release=RELEASE, **kwargs):
    conn = await world.connect()
    try:
        return await A.apply(conn, release, root=world.snapshots, **kwargs)
    finally:
        await conn.close()


async def _switch(world, release=RELEASE):
    conn = await world.connect()
    try:
        return await A.switch(conn, world.qdrant, release, "chunks_live")
    finally:
        await conn.close()


async def _rollback(world, release=RELEASE, **kwargs):
    conn = await world.connect()
    try:
        return await A.rollback(conn, world.qdrant, release, alias="chunks_live",
                                root=world.snapshots, **kwargs)
    finally:
        await conn.close()


async def _cleanup(world, release=RELEASE):
    conn = await world.connect()
    try:
        await A.cleanup(conn, release)
    finally:
        await conn.close()


async def _user_rows(world, chunk_id):
    await _sql(world, "INSERT INTO bookmarks (user_id, chunk_id) VALUES ($1, $2)", USER, chunk_id)
    await _sql(world, "INSERT INTO retrievals (search_id, chunk_id) VALUES ($1, $2)",
               str(uuid.uuid4()), chunk_id)


async def _user_counts(world):
    return {t: (await world.fetch(f"SELECT count(*) AS n FROM {t}"))[0]["n"]
            for t in pg_corpus.USER_TABLES}


def _retire_a4(world):
    world.registry.removals.append(_removal(
        id="rm-0910", scope="passage", document_id=DOC_A, anchor="a/4",
        passage_id=pid(DOC_A, "a/4"), reason="debris", tombstone="Removed."))
    _doc(world, DOC_A).passages.pop()


class RecordingConn:
    """Wraps an asyncpg connection and records every SQL statement sent through it."""

    def __init__(self, conn):
        self._conn, self.sql = conn, []

    def __getattr__(self, name):
        attr = getattr(self._conn, name)
        if name in ("execute", "executemany", "fetch", "fetchrow", "fetchval"):
            async def recorded(sql, *args, **kwargs):
                self.sql.append(sql)
                return await attr(sql, *args, **kwargs)
            return recorded
        return attr


# --------------------------------------------------------------------------- apply

async def test_changed_text_keeps_its_id(world):
    """D1: a bookmark and a retrieval on a passage whose text changed under the same
    anchor still point at it, and it returns the new text."""
    await _user_rows(world, pid(DOC_A, "a/1"))
    _doc(world, DOC_A).passages[0].content = "Grace perfects nature, corrected."
    await _stage(world)
    await _apply(world)
    [row] = await world.fetch("SELECT content, retired_at FROM chunks WHERE id = $1::uuid",
                              pid(DOC_A, "a/1"))
    assert row == {"content": "Grace perfects nature, corrected.", "retired_at": None}
    assert (await _user_counts(world))["bookmarks"] == 1
    [b] = await world.fetch("SELECT chunk_id::text FROM bookmarks")
    assert b["chunk_id"] == pid(DOC_A, "a/1")


async def test_apply_issues_no_delete(world):
    _retire_a4(world)
    await _stage(world)
    conn = RecordingConn(await world.connect())
    try:
        await A.apply(conn, RELEASE, root=world.snapshots)
    finally:
        await conn.close()
    assert not [s for s in conn.sql
                if "DELETE FROM public.chunks" in s or "DELETE FROM public.documents" in s
                or "DELETE FROM chunks" in s or "DELETE FROM documents" in s]


async def test_new_ids_are_inserted_and_removed_ids_retired_with_tombstones(world):
    await _user_rows(world, pid(DOC_A, "a/4"))
    _retire_a4(world)
    _doc(world, DOC_A).passages.append(passage("a/5", "c2", "A restored line.", 3))
    await _stage(world)
    result = await _apply(world)
    assert (result.inserted, result.retired_passages, result.tombstones) == (1, 1, 1)
    [old] = await world.fetch("SELECT retired_at IS NOT NULL AS r, position FROM chunks "
                              "WHERE id = $1::uuid", pid(DOC_A, "a/4"))
    assert old["r"] and old["position"] <= -1_000_000
    [t] = await world.fetch("SELECT reason_code, publish_id FROM corpus_tombstones")
    assert t == {"reason_code": "debris", "publish_id": RELEASE}
    assert await world.fetch("SELECT 1 FROM chunks WHERE id = $1::uuid AND retired_at IS NULL",
                             pid(DOC_A, "a/5"))
    # The user rows survive: nothing cascaded.
    assert (await _user_counts(world))["bookmarks"] == 1


async def test_outline_refreshed_in_the_same_transaction(world):
    """The outline in the committed state counts only live passages: no reader query
    after commit can see a stale chunk_count."""
    _retire_a4(world)
    await _stage(world)
    await _apply(world)
    [d] = await world.fetch("SELECT chunk_count FROM documents WHERE id = $1::uuid", DOC_A)
    assert d["chunk_count"] == 3
    chapters = await world.fetch("SELECT chapter_key FROM document_chapters "
                                 "WHERE document_id = $1::uuid ORDER BY ordinal", DOC_A)
    assert [c["chapter_key"] for c in chapters] == ["c1", "c2"]


async def test_failed_apply_leaves_live_untouched(world):
    _retire_a4(world)
    await _stage(world)
    before = await world.public_digest()

    async def boom(conn):
        raise RuntimeError("forced failure after step 4")
    with pytest.raises(RuntimeError, match="forced"):
        await _apply(world, fail_after_retire=boom)
    after = await world.public_digest()
    assert after == before
    [row] = await world.fetch("SELECT applied_at FROM corpus_publishes")
    assert row["applied_at"] is None


async def test_redirects_are_written_and_referenced_ones_refused_without_remap(world):
    a = _doc(world, DOC_A)
    a.passages[1] = passage("a/2n", "c1", a.passages[1].content, 1)
    old = pid(DOC_A, "a/2")
    world.registry.redirects.append(
        {"document_id": DOC_A, "old_passage_id": old, "old_anchor": "a/2",
         "new_passage_id": pid(DOC_A, "a/2n"), "new_anchor": "a/2n", "kind": "renumbered"})
    next(r for r in world.registry.passages if r["passage_id"] == old)["status"] = "redirected"
    world.registry.__post_init__()
    await _user_rows(world, old)
    await _stage(world)
    with pytest.raises(A.ApplyRefused, match="bookmarks 1, retrievals 1|retrievals 1, bookmarks 1"):
        await _apply(world)
    # With no user row on it, the same publish applies and writes its redirects.
    await _sql(world, "DELETE FROM bookmarks")
    await _sql(world, "DELETE FROM retrievals")
    # Feedback on the passage holds the apply too.
    await _sql(world, "INSERT INTO product_feedback (chunk_id) VALUES ($1)", uuid.UUID(old))
    with pytest.raises(A.ApplyRefused, match="product_feedback 1"):
        await _apply(world)
    await _sql(world, "DELETE FROM product_feedback")
    await _apply(world)
    rows = await world.fetch("SELECT entity, old_id::text, new_anchor FROM corpus_redirects "
                             "ORDER BY entity")
    assert rows == [{"entity": "anchor", "old_id": None, "new_anchor": "a/2n"},
                    {"entity": "passage", "old_id": old, "new_anchor": "a/2n"}]


class FakeRemap:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    async def forward(self, conn, release, redirects, chapter_remap):
        self.calls.append(("forward", conn.is_in_transaction(), release, len(redirects)))
        if self.fail:
            raise RuntimeError("remap failed")
        return A.RemapLedger({"bookmarks": 1})

    async def reverse(self, conn, release):
        live = await conn.fetchval("SELECT count(*) FROM corpus_redirects WHERE publish_id = $1",
                                   release)
        self.calls.append(("reverse", conn.is_in_transaction(), release, live))
        return A.RemapLedger({"bookmarks": 1})


def _renumber_a2(world):
    a = _doc(world, DOC_A)
    a.passages[1] = passage("a/2n", "c1", a.passages[1].content, 1)
    old = pid(DOC_A, "a/2")
    world.registry.redirects.append(
        {"document_id": DOC_A, "old_passage_id": old, "old_anchor": "a/2",
         "new_passage_id": pid(DOC_A, "a/2n"), "new_anchor": "a/2n", "kind": "renumbered"})
    next(r for r in world.registry.passages if r["passage_id"] == old)["status"] = "redirected"
    world.registry.__post_init__()
    return old


async def test_apply_calls_user_remap_in_the_transaction(world):
    old = _renumber_a2(world)
    await _user_rows(world, old)
    await _stage(world)
    remap = FakeRemap()
    result = await _apply(world, remap=remap)
    # The anchor redirect and the passage redirect, inside the apply's transaction.
    assert remap.calls == [("forward", True, RELEASE, 2)] and result.remap == {"bookmarks": 1}


async def test_a_failing_remap_rolls_the_apply_back(world):
    old = _renumber_a2(world)
    await _user_rows(world, old)
    await _stage(world)
    before = await world.public_digest()
    with pytest.raises(RuntimeError, match="remap failed"):
        await _apply(world, remap=FakeRemap(fail=True))
    assert await world.public_digest() == before


async def test_apply_refuses_stale_report(world):
    await _stage(world)
    await _sql(world, "UPDATE staging.chunks SET content = 'tampered' WHERE id = $1::uuid",
               pid(DOC_A, "a/1"))
    with pytest.raises(A.ApplyRefused, match="staging changed since the report"):
        await _apply(world)


async def test_apply_refuses_without_a_report(world):
    await world.runner().stage(STAGE)
    with pytest.raises(A.ApplyRefused, match="no passing report"):
        await _apply(world)


async def test_apply_rederives_reader_access_and_refuses_a_difference(world, monkeypatch):
    """Carter, 2 Nov 2026: the apply works reader_access out again from the inventory
    and refuses when it differs from the staged value."""
    await _stage(world)
    monkeypatch.setattr(reader_access, "access_for",
                        lambda document_id: "excerpt" if document_id == DOC_B else "full")
    with pytest.raises(A.ApplyRefused, match="reader access changed since the stage"):
        await _apply(world)
    assert not await world.fetch("SELECT 1 FROM corpus_publishes WHERE applied_at IS NOT NULL")


async def test_contents_tree_is_applied_with_the_chunks(world):
    _doc(world, DOC_A).contents = contents_tree()
    await _stage(world)
    await _apply(world)
    rows = await world.fetch("SELECT node_key, anchor FROM document_contents "
                             "WHERE document_id = $1::uuid ORDER BY ordinal", DOC_A)
    assert rows == [{"node_key": "book", "anchor": None}, {"node_key": "c2", "anchor": "a/3"}]


async def test_retired_positions_never_collide(world, tmp_path):
    """Two publishes that each retire passages of one document, then a third that adds
    passages, all succeed."""
    a = _doc(world, DOC_A)
    for n, (rm, anchor) in enumerate((("rm-a", "a/4"), ("rm-b", "a/3")), 1):
        world.registry.removals.append(_removal(
            id=rm, scope="passage", document_id=DOC_A, anchor=anchor,
            passage_id=pid(DOC_A, anchor), reason="debris", tombstone="Removed."))
        a.passages = [p for p in a.passages if p.anchor != anchor]
        release = f"release-{n}"
        await _stage(world, StageRequest(release=release, collections=("medieval",)))
        await _apply(world, release)
        await _cleanup(world, release)
    a.passages += [passage("a/6", "c2", "Added later.", 2), passage("a/7", "c2", "And more.", 3)]
    await _stage(world, StageRequest(release="release-3", collections=("medieval",)))
    await _apply(world, "release-3")
    positions = await world.fetch("SELECT position FROM chunks WHERE document_id = $1::uuid "
                                  "AND retired_at IS NOT NULL ORDER BY position DESC", DOC_A)
    assert [p["position"] for p in positions] == [-1_000_000, -1_000_001]


async def test_reappearing_id_is_unretired_and_loses_its_tombstone(world):
    _retire_a4(world)
    await _stage(world)
    await _apply(world)
    await _cleanup(world)
    # The removal entry is closed; the unit returns under the same ID.
    world.registry.removals[-1]["closed_by"] = "1.8d"
    world.registry.removals[-1]["closed_on"] = "2026-11-03"
    world.build = __import__("tests.stage_world", fromlist=["x"]).live_documents()
    await _stage(world, StageRequest(release="release-two", collections=("medieval",)))
    await _apply(world, "release-two")
    [row] = await world.fetch("SELECT retired_at, position FROM chunks WHERE id = $1::uuid",
                              pid(DOC_A, "a/4"))
    assert row == {"retired_at": None, "position": 3}
    assert not await world.fetch("SELECT 1 FROM corpus_tombstones")


async def test_passage_moved_between_documents_keeps_its_id(world):
    await _user_rows(world, pid(DOC_A, "a/4"))
    a, b = _doc(world, DOC_A), _doc(world, DOC_B)
    b.passages.append(replace(a.passages.pop(), position=1))
    row = next(r for r in world.registry.passages if r["passage_id"] == pid(DOC_A, "a/4"))
    row["document_id"] = DOC_B
    world.registry.__post_init__()
    await _stage(world)
    # The move keeps the ID, so the bookmark on it needs no remap and the apply runs.
    await _apply(world)
    [moved] = await world.fetch("SELECT document_id::text, retired_at FROM chunks WHERE id = $1::uuid",
                                pid(DOC_A, "a/4"))
    assert moved == {"document_id": DOC_B, "retired_at": None}
    [b_] = await world.fetch("SELECT chunk_id::text FROM bookmarks")
    assert b_["chunk_id"] == pid(DOC_A, "a/4")


async def test_a_piece_whose_text_moved_hands_its_anchor_on(world):
    """1.10b: the anchor takes a new ID and the old ID redirects; the retired row keeps
    its anchor with a suffix, so the unique key on (document_id, anchor) holds."""
    a = _doc(world, DOC_A)
    old = pid(DOC_A, "a/3")
    new = pid(DOC_A, "a/3#moved")
    world.registry.redirects.append(
        {"document_id": DOC_A, "old_passage_id": old, "old_anchor": "a/3",
         "new_passage_id": new, "new_anchor": "a/3", "kind": "moved"})
    row = next(r for r in world.registry.passages if r["passage_id"] == old)
    row["status"], row["anchor"] = "redirected", "a/3#moved-1.10b"
    world.registry.passages.append({**row, "passage_id": new, "anchor": "a/3", "status": "active",
                                    "live_anchor": None})
    world.registry.__post_init__()
    await _stage(world)
    await _apply(world)
    rows = await world.fetch("SELECT id::text, anchor, retired_at IS NOT NULL AS retired "
                             "FROM chunks WHERE document_id = $1::uuid AND anchor LIKE 'a/3%' "
                             "ORDER BY retired", DOC_A)
    assert rows == [{"id": new, "anchor": "a/3", "retired": False},
                    {"id": old, "anchor": f"a/3#retired-{RELEASE}", "retired": True}]


# --------------------------------------------------------------------------- switch

async def test_alias_switch_is_one_call(world):
    await _stage(world)
    await _apply(world)
    calls = []
    original = world.qdrant.update_collection_aliases

    async def update(**kwargs):
        calls.append(kwargs["change_aliases_operations"])
        return await original(**kwargs)
    world.qdrant.update_collection_aliases = update
    old, new = await _switch(world)
    assert (old, new) == ("chunks", "chunks-test-release")
    [ops] = calls
    assert [type(o).__name__ for o in ops] == ["DeleteAliasOperation", "CreateAliasOperation"]
    [row] = await world.fetch("SELECT previous_qdrant_collection, alias_switched_at IS NOT NULL "
                              "AS s FROM corpus_publishes")
    assert row == {"previous_qdrant_collection": "chunks", "s": True}


# --------------------------------------------------------------------------- rollback

async def test_rollback_apply_restores_rows_alias_and_outline(world):
    """After apply, cleanup and rollback, every corpus row equals the before-snapshot
    except the rows the publish inserted, which are retired with rolled-back tombstones,
    and the alias points at the previous collection."""
    await _user_rows(world, pid(DOC_A, "a/1"))
    counts = await _user_counts(world)
    _retire_a4(world)
    a = _doc(world, DOC_A)
    a.passages[0].content = "Grace perfects nature, corrected."
    a.passages.append(passage("a/5", "c2", "A restored line.", 3))
    a.contents = contents_tree()
    await _stage(world)
    await _apply(world)
    await _switch(world)
    assert await _user_counts(world) == counts
    await _cleanup(world)
    result = await _rollback(world)
    assert result.alias == "chunks"
    [alias] = (await world.qdrant.get_aliases()).aliases
    assert alias.collection_name == "chunks"
    rows = {r["id"]: r for r in await world.fetch(
        "SELECT id::text, content, retired_at IS NOT NULL AS retired, position FROM chunks "
        "WHERE document_id = $1::uuid", DOC_A)}
    for anchor, (_, a_, _, content) in zip(range(4), [r for r in LIVE if r[0] == DOC_A]):
        assert rows[pid(DOC_A, a_)]["content"] == content
        assert rows[pid(DOC_A, a_)]["retired"] is False
    assert rows[pid(DOC_A, "a/5")]["retired"] is True
    [t] = await world.fetch("SELECT id::text, reason_code, rule, removal_key FROM corpus_tombstones")
    assert t == {"id": pid(DOC_A, "a/5"), "reason_code": "rolled-back", "rule": "other",
                 "removal_key": None}
    [d] = await world.fetch("SELECT chunk_count FROM documents WHERE id = $1::uuid", DOC_A)
    assert d["chunk_count"] == 4
    assert not await world.fetch("SELECT 1 FROM document_contents")
    assert await _user_counts(world) == counts
    # Staging holds the snapshot again, so it must be cleaned up before the next stage.
    [p] = await world.fetch("SELECT rolled_back_at IS NOT NULL AS r, cleaned_up_at FROM corpus_publishes")
    assert p == {"r": True, "cleaned_up_at": None}


async def test_concurrent_applies_keep_the_before_snapshot(world):
    """Two applies of one release at once: the publish lock lets one apply and the other
    refuse before it writes anything, so the before-snapshot still holds the rows as they
    were and rollback restores them."""
    _retire_a4(world)
    _doc(world, DOC_A).passages[0].content = "Grace perfects nature, corrected."
    await _stage(world)
    results = await asyncio.gather(_apply(world), _apply(world), return_exceptions=True)
    assert sorted(type(r).__name__ for r in results) == ["ApplyRefused", "ApplyResult"]
    await _rollback(world)
    rows = {r["id"]: r for r in await world.fetch(
        "SELECT id::text, content, retired_at IS NOT NULL AS retired FROM chunks "
        "WHERE document_id = $1::uuid", DOC_A)}
    assert rows[pid(DOC_A, "a/1")]["content"] == LIVE[0][3]
    assert rows[pid(DOC_A, "a/4")]["retired"] is False


async def test_rollback_retry_finishes_a_failed_alias_switch(world, monkeypatch):
    """The database reversal commits before the alias moves back. When moving it fails,
    a second rollback finishes the alias instead of refusing."""
    _doc(world, DOC_A).passages.append(passage("a/5", "c2", "A restored line.", 4))
    await _stage(world)
    await _apply(world)
    await _switch(world)
    real = A.point_alias

    async def broken(*args):
        raise RuntimeError("Qdrant unavailable")
    monkeypatch.setattr(A, "point_alias", broken)
    with pytest.raises(RuntimeError, match="Qdrant unavailable"):
        await _rollback(world)
    [alias] = (await world.qdrant.get_aliases()).aliases
    assert alias.collection_name != "chunks"
    monkeypatch.setattr(A, "point_alias", real)
    result = await _rollback(world)
    assert result.alias == "chunks"
    [alias] = (await world.qdrant.get_aliases()).aliases
    assert alias.collection_name == "chunks"


async def test_rollback_refuses_under_a_later_publish(world):
    """After rollback A, cleanup A and apply B, rolling A back again must not touch the
    alias B switched (nor any row): B is in place, so A refuses."""
    _doc(world, DOC_A).passages.append(passage("a/5", "c2", "A restored line.", 4))
    await _stage(world)
    await _apply(world)
    await _switch(world)
    await _rollback(world)
    await _cleanup(world)
    later = StageRequest(release="test-later", collections=("medieval",))
    await _stage(world, later)
    await _apply(world, "test-later")
    await _switch(world, "test-later")
    [before] = (await world.qdrant.get_aliases()).aliases
    with pytest.raises(A.ApplyRefused, match="'test-later' changed live after"):
        await _rollback(world)
    [after] = (await world.qdrant.get_aliases()).aliases
    assert after.collection_name == before.collection_name != "chunks"


async def test_overlapping_rollbacks_keep_the_rolled_back_tombstones(world):
    """Two rollbacks at once: the second re-reads the publish under the lock, so it never
    deletes the first one's rolled-back tombstones."""
    _doc(world, DOC_A).passages.append(passage("a/5", "c2", "A restored line.", 4))
    await _stage(world)
    await _apply(world)
    await _switch(world)
    await asyncio.gather(_rollback(world), _rollback(world), return_exceptions=True)
    rows = await world.fetch("SELECT id::text, reason_code FROM corpus_tombstones")
    assert rows == [{"id": pid(DOC_A, "a/5"), "reason_code": "rolled-back"}]
    [alias] = (await world.qdrant.get_aliases()).aliases
    assert alias.collection_name == "chunks"


async def test_switch_retry_after_a_lost_response_keeps_the_previous_target(world):
    """The alias moves, then the reply is lost: a retried switch still records the
    collection the alias pointed at before, so rollback goes back to it."""
    await _stage(world)
    await _apply(world)
    real = world.qdrant.update_collection_aliases

    async def lost(**kwargs):
        await real(**kwargs)
        raise RuntimeError("connection reset")
    world.qdrant.update_collection_aliases = lost
    with pytest.raises(RuntimeError, match="connection reset"):
        await _switch(world)
    world.qdrant.update_collection_aliases = real
    await _switch(world)
    [row] = await world.fetch("SELECT previous_qdrant_collection AS p FROM corpus_publishes "
                              "WHERE id = $1", RELEASE)
    assert row["p"] == "chunks"


async def test_switch_refuses_a_superseded_release(world):
    """After A is applied and cleaned up and B applied and switched, switching A again
    would put B's database under A's index: it refuses."""
    await _stage(world)
    await _apply(world)
    await _switch(world)
    await _cleanup(world)
    await _stage(world, StageRequest(release="test-later", collections=("medieval",)))
    await _apply(world, "test-later")
    await _switch(world, "test-later")
    with pytest.raises(A.ApplyRefused, match="'test-later' was applied after"):
        await _switch(world)
    [alias] = (await world.qdrant.get_aliases()).aliases
    assert alias.collection_name == "chunks-test-later"


async def test_rollback_retry_refuses_after_a_later_rollback(world):
    """Apply A, apply B, roll back B, roll back A: retrying B's rollback would point the
    alias at A's undone collection, so it refuses."""
    await _stage(world)
    await _apply(world)
    await _switch(world)
    await _cleanup(world)
    later = StageRequest(release="test-later", collections=("medieval",))
    await _stage(world, later)
    await _apply(world, "test-later")
    await _switch(world, "test-later")
    await _rollback(world, "test-later")
    await _cleanup(world, "test-later")
    await _rollback(world)
    await _cleanup(world)
    with pytest.raises(A.ApplyRefused, match="changed live after 'test-later'"):
        await _rollback(world, "test-later")
    [alias] = (await world.qdrant.get_aliases()).aliases
    assert alias.collection_name == "chunks"


async def test_rollback_retry_after_a_failed_restore_under_an_older_rollback(world, monkeypatch):
    """Apply A, apply B, roll back B, then roll back A with a failing alias restore: B was
    undone before A's rollback, so retrying A finishes the alias."""
    await _stage(world)
    await _apply(world)
    await _switch(world)
    await _cleanup(world)
    later = StageRequest(release="test-later", collections=("medieval",))
    await _stage(world, later)
    await _apply(world, "test-later")
    await _switch(world, "test-later")
    await _rollback(world, "test-later")
    await _cleanup(world, "test-later")
    real = A.point_alias

    async def broken(*args):
        raise RuntimeError("Qdrant unavailable")
    monkeypatch.setattr(A, "point_alias", broken)
    with pytest.raises(RuntimeError, match="Qdrant unavailable"):
        await _rollback(world)
    monkeypatch.setattr(A, "point_alias", real)
    assert (await _rollback(world)).alias == "chunks"
    [alias] = (await world.qdrant.get_aliases()).aliases
    assert alias.collection_name == "chunks"


async def test_rollback_keeps_its_rolled_back_tombstones(world):
    _retire_a4(world)
    _renumber_a2(world)
    _doc(world, DOC_A).passages.append(passage("a/5", "c2", "A restored line.", 3))
    await _stage(world)
    await _apply(world)
    await _rollback(world)
    rows = await world.fetch("SELECT reason_code, count(*) AS n FROM corpus_tombstones GROUP BY 1")
    assert rows == [{"reason_code": "rolled-back", "n": 2}]     # a/5 and a/2n
    assert not await world.fetch("SELECT 1 FROM corpus_redirects")


async def test_rollback_calls_reverse_remap_in_the_same_transaction(world):
    old = _renumber_a2(world)
    await _user_rows(world, old)
    await _stage(world)
    remap = FakeRemap()
    await _apply(world, remap=remap)
    await _rollback(world, remap=remap)
    # Reverse runs inside the transaction while the publish's redirects still exist.
    assert remap.calls[-1] == ("reverse", True, RELEASE, 2)


async def test_rollback_restores_deleted_redirects_and_tombstones(world):
    """Publish A redirects a split piece; publish B reclaims it (deleting A's redirect)
    and un-retires another ID (deleting its tombstone); rolling B back brings both rows
    back, the piece is retired again and the user tables are as before B."""
    a = _doc(world, DOC_A)
    old = pid(DOC_A, "a/2")
    # Publish A: a/2 redirects (merged) into a/1, and a/4 is removed.
    world.registry.redirects.append(
        {"document_id": DOC_A, "old_passage_id": old, "old_anchor": "a/2",
         "new_passage_id": pid(DOC_A, "a/1"), "new_anchor": "a/1", "kind": "merged"})
    next(r for r in world.registry.passages if r["passage_id"] == old)["status"] = "redirected"
    world.registry.__post_init__()
    _retire_a4(world)
    kept = a.passages
    a.passages = [kept[0], replace(kept[2], position=1)]
    await _stage(world, StageRequest(release="publish-a", collections=("medieval",)))
    await _apply(world, "publish-a")
    await _cleanup(world, "publish-a")
    counts = await _user_counts(world)
    # Publish B: the piece reclaims its ID (its redirect closes) and a/4 returns.
    world.registry.redirects[-1]["closed_by"] = "item-b"
    world.registry.removals[-1]["closed_by"] = "item-b"
    world.registry.removals[-1]["closed_on"] = "2026-11-03"
    next(r for r in world.registry.passages if r["passage_id"] == old)["status"] = "active"
    world.registry.__post_init__()
    world.build = __import__("tests.stage_world", fromlist=["x"]).live_documents()
    await _stage(world, StageRequest(release="publish-b", collections=("medieval",)))
    await _apply(world, "publish-b")
    assert not await world.fetch("SELECT 1 FROM corpus_redirects WHERE entity = 'passage'")
    assert not await world.fetch("SELECT 1 FROM corpus_tombstones")
    await _rollback(world, "publish-b")
    [r] = await world.fetch("SELECT old_id::text, new_anchor, publish_id FROM corpus_redirects "
                            "WHERE entity = 'passage'")
    assert r == {"old_id": old, "new_anchor": "a/1", "publish_id": "publish-a"}
    [t] = await world.fetch("SELECT id::text, publish_id FROM corpus_tombstones")
    assert t == {"id": pid(DOC_A, "a/4"), "publish_id": "publish-a"}
    retired = {r["id"] for r in await world.fetch(
        "SELECT id::text FROM chunks WHERE retired_at IS NOT NULL")}
    assert retired == {old, pid(DOC_A, "a/4")}
    assert await _user_counts(world) == counts


async def test_rollback_rederives_reader_access(world, monkeypatch):
    """Carter, 2 Nov 2026: a permission withdrawn during the window is not reopened by a
    rollback; reader_access comes from the inventory as it stands at the rollback."""
    await _stage(world)
    await _apply(world)
    monkeypatch.setattr(reader_access, "access_for",
                        lambda document_id: "excerpt" if document_id == DOC_A else "full")
    await _rollback(world)
    [row] = await world.fetch("SELECT reader_access FROM documents WHERE id = $1::uuid", DOC_A)
    assert row["reader_access"] == "excerpt"


async def test_rollback_restores_the_snapshot_works(world):
    """A work the publish added goes with the rollback, even though the passage that names
    it stays as a retired row (4.1b rehearsal rerun, 20 Nov 2026: eight documents kept the
    new corpus's work list over the old text)."""
    await _sql(world, """INSERT INTO document_works (document_id, work_key, ordinal, title)
                         VALUES ($1::uuid, 'w-old', 1, 'Kept')""", DOC_A)
    a = _doc(world, DOC_A)
    a.works = [Work(work_key="w-old", ordinal=1, title="Kept"),
               Work(work_key="w-new", ordinal=2, title="Added")]
    a.passages.append(passage("a/5", "c2", "A restored line.", 4, work_key="w-new"))
    await _stage(world)
    await _apply(world)
    keys = lambda rows: sorted(r["work_key"] for r in rows)
    assert keys(await world.fetch("SELECT work_key FROM document_works")) == ["w-new", "w-old"]
    await _rollback(world)
    assert keys(await world.fetch("SELECT work_key FROM document_works")) == ["w-old"]
    [row] = await world.fetch("SELECT retired_at IS NOT NULL AS r FROM chunks WHERE id = $1::uuid",
                              pid(DOC_A, "a/5"))
    assert row["r"] is True


async def test_rollback_never_opens_beyond_the_snapshot(world):
    """Carter, 6 Nov 2026: the inventory describes the published edition, and a re-sourced
    work keeps its ID, so a rollback to an excerpt-only snapshot stays excerpt-only."""
    await _sql(world, "UPDATE documents SET reader_access = 'excerpt' WHERE id = $1::uuid", DOC_A)
    await _stage(world)
    await _apply(world)
    [row] = await world.fetch("SELECT reader_access FROM documents WHERE id = $1::uuid", DOC_A)
    assert row["reader_access"] == "full"
    await _rollback(world)
    [row] = await world.fetch("SELECT reader_access FROM documents WHERE id = $1::uuid", DOC_A)
    assert row["reader_access"] == "excerpt"


async def test_sync_decides_and_writes_on_locked_rows(world):
    """A rollback that restores an older edition cannot slip between the sync's check and
    its write: the sync holds the rows, so the rollback waits for it."""
    await _sql(world, """UPDATE documents SET metadata = '{"url": "https://old"}'::jsonb
                         WHERE id = $1::uuid""", DOC_A)
    table, urls = {DOC_A: "full"}, {DOC_A: "https://new"}
    conn = await world.connect()
    other = await world.connect()
    try:
        async with conn.transaction():
            result = await reader_access.plan(conn, table, urls, lock=True)
            assert [c.document_id for c in result.held] == [DOC_A]
            await other.execute("SET lock_timeout = '200ms'")
            with pytest.raises(asyncpg.exceptions.LockNotAvailableError):
                await other.execute(
                    "UPDATE documents SET metadata = '{}'::jsonb WHERE id = $1::uuid", DOC_A)
        result = await reader_access.sync(conn, table, apply=True, allow_unmatched=True,
                                           urls=urls)
        assert [c.document_id for c in result.held] == [DOC_A]
        [row] = await conn.fetch("SELECT reader_access FROM documents WHERE id = $1::uuid", DOC_A)
        assert row["reader_access"] == "excerpt"
    finally:
        await other.close()
        await conn.close()


# --------------------------------------------------------------------------- cleanup

async def test_cleanup_drops_staging_only(world):
    await _stage(world)
    await _apply(world)
    before = await world.public_digest()
    await _cleanup(world)
    assert await world.public_digest() == before
    [row] = await world.fetch("SELECT to_regclass('staging.chunks') IS NULL AS gone")
    assert row["gone"]
    # The next stage recreates staging.
    await world.runner().stage(StageRequest(release="next-release", collections=("medieval",)))
    assert await world.fetch("SELECT 1 FROM staging.chunks LIMIT 1")


# --------------------------------------------------------------------------- retire only

async def test_retire_only_and_its_rollback(world):
    """The On the Incarnation procedure: retire one document and its passages with
    tombstones from the registry entry, mark their points not searchable, switch no
    alias; rollback restores them and makes the points searchable again."""
    await _user_rows(world, pid(DOC_B, "b/1"))
    world.registry.removals.append(_removal(
        id="rm-0920", scope="document", document_id=DOC_B,
        reason="translation-in-preparation", tombstone="Being replaced."))
    conn = await world.connect()
    try:
        done = await A.retire_only(conn, world.qdrant, "incarnation-withdraw", "medieval",
                                   alias="chunks_live", registry=world.registry,
                                   root=world.snapshots)
    finally:
        await conn.close()
    assert done == {"documents": 1, "passages": 1, "collection": "chunks"}
    rows = await world.fetch("SELECT entity, rule, reason_code FROM corpus_tombstones ORDER BY entity")
    assert rows == [{"entity": "document", "rule": "other", "reason_code": "translation-in-preparation"},
                    {"entity": "passage", "rule": "other", "reason_code": "translation-in-preparation"}]
    [point] = await world.qdrant.retrieve("chunks", ids=[pid(DOC_B, "b/1")])
    assert point.payload["searchable"] is False
    [alias] = (await world.qdrant.get_aliases()).aliases
    assert alias.collection_name == "chunks"
    assert (await _user_counts(world))["bookmarks"] == 1

    await _rollback(world, "incarnation-withdraw")
    [d] = await world.fetch("SELECT retired_at FROM documents WHERE id = $1::uuid", DOC_B)
    [c] = await world.fetch("SELECT retired_at, position FROM chunks WHERE id = $1::uuid",
                            pid(DOC_B, "b/1"))
    assert d["retired_at"] is None and c == {"retired_at": None, "position": 0}
    assert not await world.fetch("SELECT 1 FROM corpus_tombstones")
    [point] = await world.qdrant.retrieve("chunks", ids=[pid(DOC_B, "b/1")])
    assert point.payload["searchable"] is True
    # Other documents of the collection were never touched.
    [a_] = await world.fetch("SELECT count(*) AS n FROM chunks WHERE document_id = $1::uuid "
                             "AND retired_at IS NULL", DOC_A)
    assert a_["n"] == 4


async def test_retire_only_leaves_an_unsearchable_point_unsearchable(world):
    """A point already marked not searchable is neither flipped nor recorded, so the
    rollback does not make it searchable."""
    world.registry.removals.append(_removal(
        id="rm-0921", scope="document", document_id=DOC_B,
        reason="translation-in-preparation", tombstone="Being replaced."))
    await world.qdrant.set_payload("chunks", payload={"searchable": False},
                                   points=[pid(DOC_B, "b/1")], wait=True)
    conn = await world.connect()
    try:
        await A.retire_only(conn, world.qdrant, "incarnation-withdraw", "medieval",
                            alias="chunks_live", registry=world.registry, root=world.snapshots)
    finally:
        await conn.close()
    with open(f"{A.snapshot_dir('incarnation-withdraw', world.snapshots)}/{A.FLIPPED_POINTS}") as f:
        assert json.load(f) == []
    await _rollback(world, "incarnation-withdraw")
    [point] = await world.qdrant.retrieve("chunks", ids=[pid(DOC_B, "b/1")])
    assert point.payload["searchable"] is False


# --------------------------------------------------------------------------- CLI

def _remote(monkeypatch):
    import asyncpg
    import publish_lock
    import writers.qdrant

    monkeypatch.setattr(publish_lock, "settings_targets", lambda: publish_lock.WriteTargets(
        "postgresql://u:p@db.example.supabase.co/postgres", "https://q.example.qdrant.io"))

    def no_network(*args, **kwargs):
        raise AssertionError("the lock must refuse before any write")
    monkeypatch.setattr(writers.qdrant, "get_client", lambda: _NoClient())
    return asyncpg


class _NoClient:
    async def close(self):
        return None


@pytest.mark.parametrize(("command", "step"), [
    ("apply", "apply"), ("switch", "apply"), ("cleanup", "apply"), ("rollback", "rollback")])
async def test_each_subcommand_asks_for_its_step(world, monkeypatch, command, step):
    """test_apply_refuses_without_lock_match and test_each_subcommand_asks_for_its_step:
    with remote targets and a lock entry for another step, each command refuses before
    it changes anything."""
    import publish

    _remote(monkeypatch)
    await _stage(world)

    async def connect():
        return await world.connect()
    monkeypatch.setattr(publish, "_connect", connect)
    lock = world.tmp_path / "PUBLISH_LOCK.json"
    other = "rollback" if step != "rollback" else "apply"
    lock.write_text(json.dumps({"reason": "test", "approved_applies": [
        {"collection": "medieval", "release": RELEASE, "steps": [other]}]}))
    before = await world.public_digest()
    args = publish.build_parser().parse_args([command, "--release", RELEASE])
    with pytest.raises(ValueError, match=f"step '{step}'"):
        await publish.COMMANDS[command](args, lock)
    assert await world.public_digest() == before


async def test_retire_only_needs_its_collection(world):
    import publish

    args = publish.build_parser().parse_args(["apply", "--retire-only", "--release", "x-1"])
    with pytest.raises(ValueError, match="--retire-only needs --collection"):
        await publish.apply(args)
