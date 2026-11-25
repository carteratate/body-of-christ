"""#439: the one-off cleanup of the anchor redirects a restage wrote under the wrong old
document, against a real PostgreSQL."""
from __future__ import annotations

import json

import pytest

from scripts import delete_unreachable_redirects as U
from tests import pg_corpus
from tests.stage_world import DOC_A, DOC_B, World

USER = "00000000-0000-0000-0000-0000000000aa"


@pytest.fixture(scope="module")
def cluster():
    cluster, stop = pg_corpus.start()
    yield cluster
    stop()


@pytest.fixture()
async def world(cluster, tmp_path):
    w = World(cluster, cluster.new_database(), tmp_path)
    await w.seed()
    conn = await w.connect()
    try:
        for release in ("moved-it", "restaged"):
            await conn.execute("INSERT INTO corpus_publishes (id, collections, qdrant_collection) "
                               "VALUES ($1, '{medieval}', $2)", release, f"chunks-{release}")

        async def redirect(old_doc, old_anchor, new_doc, new_anchor, release):
            await conn.execute(
                """INSERT INTO corpus_redirects (entity, old_document_id, old_anchor,
                   new_document_id, new_anchor, kind, publish_id)
                   VALUES ('anchor', $1, $2, $3, $4, 'moved', $5)""",
                old_doc, old_anchor, new_doc, new_anchor, release)
        # The move's correct rows, from A into B.
        await redirect(DOC_A, "old/1", DOC_B, "b/1", "moved-it")
        await redirect(DOC_A, "old/2", DOC_B, "b/2", "moved-it")
        await redirect(DOC_A, "old/3", DOC_B, "b/3", "moved-it")
        # The restage's rows under B: one unreachable; one whose pair a reading position
        # names; one with no correct row beside it; and a row of another release.
        await redirect(DOC_B, "old/1", DOC_B, "b/1", "restaged")
        await redirect(DOC_B, "old/2", DOC_B, "b/2", "restaged")
        await redirect(DOC_B, "old/9", DOC_B, "b/9", "restaged")
        await redirect(DOC_B, "old/3", DOC_B, "b/3", "moved-it")
        await conn.execute("INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor) "
                           "VALUES ($1, $2, 'c1', 'old/2')", USER, DOC_B)
    finally:
        await conn.close()
    return w


async def _left(world):
    return [(r["old_document_id"] == DOC_A, r["old_anchor"], r["publish_id"]) for r in
            await world.fetch("SELECT old_document_id::text, old_anchor, publish_id "
                              "FROM corpus_redirects ORDER BY old_document_id, old_anchor")]


async def test_dry_run_counts_only_the_unreachable_row(world, capsys):
    before = await _left(world)
    assert await U.main(["--release", "restaged"], connect=world.connect) == 0
    out = capsys.readouterr().out
    assert "dry run: 1 unreachable anchor redirects from 'restaged', in 1 documents" in out
    assert await _left(world) == before


async def test_execute_deletes_only_the_unreachable_row(world, tmp_path):
    lock = tmp_path / "PUBLISH_LOCK.json"
    lock.write_text(json.dumps({"reason": "test", "approved_applies": [
        {"collection": "all", "release": "restaged", "steps": ["apply"]}]}))
    assert await U.main(["--release", "restaged", "--execute", "--expect", "1"],
                        connect=world.connect, lock_path=lock) == 0
    assert await _left(world) == [
        (True, "old/1", "moved-it"), (True, "old/2", "moved-it"), (True, "old/3", "moved-it"),
        (False, "old/2", "restaged"), (False, "old/3", "moved-it"), (False, "old/9", "restaged")]


async def test_execute_refuses_a_count_it_did_not_expect(world, tmp_path):
    lock = tmp_path / "PUBLISH_LOCK.json"
    lock.write_text(json.dumps({"reason": "test", "approved_applies": [
        {"collection": "all", "release": "restaged", "steps": ["apply"]}]}))
    before = await _left(world)
    with pytest.raises(ValueError, match="1 unreachable rows now, not the 2 expected"):
        await U.main(["--release", "restaged", "--execute", "--expect", "2"],
                     connect=world.connect, lock_path=lock)
    assert await _left(world) == before
