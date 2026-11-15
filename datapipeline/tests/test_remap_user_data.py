"""4.1a: the user-data remap, against a real PostgreSQL with production's user tables and
synthetic users only (docs/corpus-cleanup/P4-P5-republish-expand.md, item 4.1a)."""
from __future__ import annotations

import inspect
import json
import os
import uuid

import pytest

import reader_access
import remap_user_data as R
from release.staged import staged_content_sha256
from publication import StageRequest
from tests import pg_corpus
from tests.stage_world import DOC_A, DOC_B, World, passage, pid
from writers import apply as A

RELEASE = "test-release"
U1, U2 = "00000000-0000-0000-0000-0000000000a1", "00000000-0000-0000-0000-0000000000a2"
A1, A2, A3, A4 = (pid(DOC_A, f"a/{n}") for n in (1, 2, 3, 4))
B1 = pid(DOC_B, "b/1")
USER_TABLES = ("bookmarks", "retrievals", "retrieval_labels", "guest_trial_retrievals",
               "reading_progress", "product_feedback", "searches", "guest_trials")


@pytest.fixture(scope="module")
def cluster():
    cluster, stop = pg_corpus.start()
    yield cluster
    stop()


@pytest.fixture()
async def world(cluster, tmp_path, monkeypatch):
    monkeypatch.setattr(reader_access, "access_for", lambda document_id: "full")
    w = World(cluster, cluster.new_database(), tmp_path)
    pg_corpus.use_production_user_tables(cluster, w.database)
    await w.seed()
    w.snapshots = str(tmp_path / "snapshots")
    w.remap = R.UserDataRemapImpl(root=w.snapshots)
    await sql(w, "INSERT INTO auth.users (id) VALUES ($1), ($2)", U1, U2)
    await sql(w, """INSERT INTO corpus_publishes (id, collections, qdrant_collection)
                    VALUES ($1, '{medieval}', 'chunks-test-release')""", RELEASE)
    return w


# --------------------------------------------------------------------------- helpers

async def sql(world, statement, *args):
    conn = await world.connect()
    try:
        return await conn.execute(statement, *args)
    finally:
        await conn.close()


async def val(world, statement, *args):
    conn = await world.connect()
    try:
        return await conn.fetchval(statement, *args)
    finally:
        await conn.close()


def moved(old, new, kind="merged", document=DOC_A, new_document=DOC_A):
    """A passage redirect and its anchor redirect, as 2.2w passes them."""
    old_anchor = next(a for a in ("a/1", "a/2", "a/3", "a/4", "b/1")
                      if pid(document, a) == old)
    new_anchor = next(a for a in ("a/1", "a/2", "a/3", "a/4", "b/1")
                      if pid(new_document, a) == new)
    return [{"entity": "passage", "old_id": old, "old_document_id": document,
             "old_anchor": old_anchor, "new_id": new, "new_document_id": new_document,
             "new_anchor": new_anchor, "kind": kind},
            {"entity": "anchor", "old_id": None, "old_document_id": document,
             "old_anchor": old_anchor, "new_id": None, "new_document_id": new_document,
             "new_anchor": new_anchor, "kind": kind}]


def chapter(old_key, new_key, document=DOC_A, new_document=DOC_A):
    return {"entity": "chapter", "old_id": None, "old_document_id": document,
            "old_anchor": old_key, "new_id": None, "new_document_id": new_document,
            "new_anchor": new_key, "kind": "moved"}


async def forward(world, redirects, chapters=()):
    """forward inside a transaction that has written the redirects and then marks the
    publish applied, as apply does."""
    conn = await world.connect()
    try:
        async with conn.transaction():
            for r in [*redirects, *chapters]:
                await conn.execute(
                    """INSERT INTO corpus_redirects (entity, old_id, old_document_id, old_anchor,
                         new_id, new_document_id, new_anchor, kind, publish_id)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                    r["entity"], r["old_id"], r["old_document_id"], r["old_anchor"],
                    r["new_id"], r["new_document_id"], r["new_anchor"], r["kind"], RELEASE)
            ledger = await world.remap.forward(conn, RELEASE, list(redirects), list(chapters))
            await conn.execute("UPDATE corpus_publishes SET applied_at = now() WHERE id = $1",
                               RELEASE)
        return ledger.counts
    finally:
        await conn.close()


async def reverse(world):
    conn = await world.connect()
    try:
        async with conn.transaction():
            ledger = await world.remap.reverse(conn, RELEASE)
        return ledger.counts
    finally:
        await conn.close()


async def digest(world):
    out = {}
    for t in USER_TABLES:
        out[t] = await val(world, f"SELECT coalesce(string_agg(t::text, '|' ORDER BY t::text), '') "
                                  f"FROM public.{t} t")
    return out


async def search(world, user=U1):
    return str(await val(world, "INSERT INTO searches (user_id) VALUES ($1) RETURNING id", user))


async def bookmark(world, chunk, user=U1, note=None, at="2026-01-01"):
    return str(await val(world, """INSERT INTO bookmarks (user_id, chunk_id, note, created_at)
                                   VALUES ($1, $2, $3, $4::text::timestamptz) RETURNING id""",
                         user, chunk, note, at))


async def retrieval(world, search_id, chunk, rank, explanation=None):
    return str(await val(world, """INSERT INTO retrievals (search_id, chunk_id, rank, explanation)
                                   VALUES ($1, $2, $3, $4) RETURNING id""",
                         search_id, chunk, rank, explanation))


async def rows(world, statement, *args):
    return await world.fetch(statement, *args)


def ledger_entries(world):
    with open(world.remap.ledger_path(RELEASE), encoding="utf-8") as f:
        return [json.loads(line) for line in f][1:]


# --------------------------------------------------------------------------- collision rules

async def test_bookmarks_merge_keeps_the_earliest_and_joins_differing_notes(world):
    early = await bookmark(world, A2, note="On grace.", at="2026-01-01")
    late = await bookmark(world, A1, note="Augustine's phrase.", at="2026-02-01")
    counts = await forward(world, moved(A2, A1))
    [b] = await rows(world, "SELECT id::text, chunk_id::text, note FROM bookmarks")
    assert b == {"id": early, "chunk_id": A1, "note": "On grace.\n\nAugustine's phrase."}
    assert counts == {"bookmarks.dropped": 1, "bookmarks.merged": 1, "bookmarks.notes_joined": 1}
    dropped = [e for e in ledger_entries(world) if e["action"] == "dropped"]
    assert [e["before"]["id"] for e in dropped] == [late]


async def test_bookmarks_notes_too_long_to_join_keep_the_earlier(world):
    await bookmark(world, A2, note="x" * 2000, at="2026-01-01")
    late = await bookmark(world, A1, note="y" * 1500, at="2026-02-01")
    counts = await forward(world, moved(A2, A1))
    [b] = await rows(world, "SELECT note FROM bookmarks")
    assert b["note"] == "x" * 2000
    assert counts["bookmarks.notes_kept_apart"] == 1
    [d] = [e for e in ledger_entries(world) if e["action"] == "dropped"]
    assert (d["before"]["id"], d["before"]["note"]) == (late, "y" * 1500)


async def test_bookmarks_equal_notes_are_not_doubled_and_a_lone_note_is_kept(world):
    await bookmark(world, A2, note="Same.", at="2026-01-01")
    await bookmark(world, A1, note=" Same. ", at="2026-02-01")
    await bookmark(world, A3, user=U2, note=None, at="2026-01-01")
    await bookmark(world, A1, user=U2, note="Only note.", at="2026-02-01")
    redirects = moved(A2, A1) + moved(A3, A1)
    counts = await forward(world, redirects)
    got = {r["user_id"]: r["note"] for r in await rows(
        world, "SELECT user_id::text, note FROM bookmarks")}
    assert got == {U1: "Same.", U2: "Only note."}
    assert "bookmarks.notes_joined" not in counts and counts["bookmarks.dropped"] == 2


async def test_labels_keep_the_latest(world):
    s = await search(world)
    for chunk, label, at in ((A2, "up", "2026-01-01"), (A1, "down", "2026-03-01")):
        await sql(world, """INSERT INTO retrieval_labels (user_id, chunk_id, search_id, label,
                            rank, created_at) VALUES ($1, $2, $3, $4, 1, $5::text::timestamptz)""",
                  U1, chunk, s, label, at)
    counts = await forward(world, moved(A2, A1))
    assert await rows(world, "SELECT chunk_id::text, label FROM retrieval_labels") == [
        {"chunk_id": A1, "label": "down"}]
    assert counts == {"retrieval_labels.dropped": 1, "retrieval_labels.merged": 1}


async def test_guest_results_keep_the_lowest_rank_with_its_explanation(world):
    trial = str(await val(world, "INSERT INTO guest_trials DEFAULT VALUES RETURNING id"))
    for chunk, rank, text in ((A2, 2, "second"), (A1, 5, "fifth")):
        await sql(world, """INSERT INTO guest_trial_retrievals (guest_trial_id, chunk_id, rank,
                            explanation, reranker_score) VALUES ($1, $2, $3, $4, 0.5)""",
                  trial, chunk, rank, text)
    await forward(world, moved(A2, A1))
    assert await rows(world, "SELECT chunk_id::text, rank, explanation FROM guest_trial_retrievals") == [
        {"chunk_id": A1, "rank": 2, "explanation": "second"}]


async def test_retrievals_keep_the_lowest_rank_and_leave_other_ranks(world):
    s = await search(world)
    await retrieval(world, s, A1, 1)
    await retrieval(world, s, A3, 2)
    await retrieval(world, s, A2, 3)
    other = await search(world)
    await retrieval(world, other, A2, 4)
    counts = await forward(world, moved(A2, A1))
    got = sorted((r["search_id"] == s, r["chunk_id"], r["rank"]) for r in await rows(
        world, "SELECT search_id::text, chunk_id::text, rank FROM retrievals"))
    assert got == [(False, A1, 4), (True, A1, 1), (True, A3, 2)]
    assert counts == {"retrievals.dropped": 1, "retrievals.merged": 1, "retrievals.repointed": 1}


async def test_feedback_is_repointed_without_merging(world):
    for _ in range(2):
        await sql(world, "INSERT INTO product_feedback (user_id, chunk_id) VALUES ($1, $2)", U1, A2)
    await sql(world, "INSERT INTO product_feedback (user_id, chunk_id) VALUES ($1, $2)", U1, A1)
    counts = await forward(world, moved(A2, A1))
    assert await val(world, "SELECT count(*) FROM product_feedback WHERE chunk_id = $1", A1) == 3
    assert counts == {"product_feedback.repointed": 2}


async def test_reading_position_follows_its_anchor_and_chapter(world):
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor)
                        VALUES ($1, $2, 'c1', 'a/2'), ($3, $2, 'c2', NULL)""", U1, DOC_A, U2)
    # a/2 redirects to a/3, whose chapter c2 is now c3; U2's position in c2 follows the
    # chapter redirect and has no anchor to carry.
    await sql(world, "UPDATE chunks SET chapter_key = 'c3' WHERE id = $1", A3)
    counts = await forward(world, moved(A2, A3), [chapter("c2", "c3")])
    got = {r["user_id"]: (r["chapter_key"], r["anchor"]) for r in await rows(
        world, "SELECT user_id::text, chapter_key, anchor FROM reading_progress")}
    assert got == {U1: ("c3", "a/3"), U2: ("c3", None)}
    assert counts == {"reading_progress.rewritten": 2}


async def test_reading_position_in_a_retired_chapter_goes_to_the_first_live_chapter(world):
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor)
                        VALUES ($1, $2, 'c2', 'a/4')""", U1, DOC_A)
    await sql(world, """UPDATE chunks SET retired_at = now(), position = -1000000 - position
                        WHERE document_id = $1 AND chapter_key = 'c2'""", DOC_A)
    await sql(world, "UPDATE chunks SET chapter_key = 'c0' WHERE id = $1", A1)
    # A chapter removed outright has no successor, so no chapter redirect names it.
    counts = await forward(world, [])
    assert await rows(world, "SELECT chapter_key, anchor FROM reading_progress") == [
        {"chapter_key": "c0", "anchor": None}]
    assert counts == {"reading_progress.first_chapter": 1}


async def test_reading_position_moving_document_keeps_the_later_on_collision(world):
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor,
                        updated_at) VALUES ($1, $2, 'c2', NULL, '2026-05-01'),
                                           ($1, $3, 'k1', NULL, '2026-04-01'),
                                           ($4, $2, 'c2', NULL, '2026-01-01'),
                                           ($4, $3, 'k1', NULL, '2026-06-01')""",
              U1, DOC_A, DOC_B, U2)
    counts = await forward(world, [], [chapter("c2", "k1", new_document=DOC_B)])
    got = {r["user_id"]: (r["document_id"], r["updated_at"].month) for r in await rows(
        world, "SELECT user_id::text, document_id::text, updated_at FROM reading_progress")}
    assert got == {U1: (DOC_B, 5), U2: (DOC_B, 6)}
    assert counts == {"reading_progress.dropped": 2, "reading_progress.rewritten": 1}


# --------------------------------------------------------------------------- untouched rows

async def test_rows_on_retired_passages_without_a_redirect_are_untouched(world):
    await sql(world, "UPDATE chunks SET retired_at = now(), position = -1000000 WHERE id = $1", A4)
    await bookmark(world, A4)
    before = await digest(world)
    assert await forward(world, moved(A2, A1)) == {}
    assert await digest(world) == before


async def test_rows_on_a_passage_whose_text_changed_are_untouched(world):
    await sql(world, "UPDATE chunks SET content = 'Corrected text.' WHERE id = $1", A3)
    await bookmark(world, A3)
    before = await digest(world)
    assert await forward(world, moved(A2, A1)) == {}
    assert await digest(world) == before


async def test_refuses_a_redirect_to_a_missing_passage(world):
    await bookmark(world, A2)
    missing = str(uuid.uuid4())
    redirect = {**moved(A2, A1)[0], "new_id": missing}
    with pytest.raises(R.RemapRefused, match="missing from chunks"):
        await forward(world, [redirect])
    assert await val(world, "SELECT chunk_id::text FROM bookmarks") == A2


async def test_forward_refuses_outside_a_transaction_and_for_an_applied_publish(world):
    conn = await world.connect()
    try:
        with pytest.raises(R.RemapRefused, match="inside 2.2w's apply"):
            await world.remap.forward(conn, RELEASE, [], [])
        await conn.execute("UPDATE corpus_publishes SET applied_at = now()")
        async with conn.transaction():
            with pytest.raises(R.RemapRefused, match="already applied"):
                await world.remap.forward(conn, RELEASE, [], [])
    finally:
        await conn.close()


# --------------------------------------------------------------------------- ledger, reverse

async def _everything(world):
    """One row of every kind forward moves, merges or drops."""
    s = await search(world)
    trial = str(await val(world, "INSERT INTO guest_trials DEFAULT VALUES RETURNING id"))
    await bookmark(world, A2, note="first", at="2026-01-01")
    await bookmark(world, A1, note="second", at="2026-02-01")
    await bookmark(world, A2, user=U2, note="alone")
    await retrieval(world, s, A1, 1)
    await retrieval(world, s, A2, 2)
    await sql(world, """INSERT INTO retrieval_labels (user_id, chunk_id, search_id, label, rank)
                        VALUES ($1, $2, $3, 'up', 2)""", U1, A2, s)
    for chunk, rank in ((A2, 1), (A1, 3)):
        await sql(world, """INSERT INTO guest_trial_retrievals (guest_trial_id, chunk_id, rank)
                            VALUES ($1, $2, $3)""", trial, chunk, rank)
    await sql(world, "INSERT INTO product_feedback (user_id, chunk_id) VALUES ($1, $2)", U1, A2)
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor,
                        updated_at) VALUES ($1, $2, 'c1', 'a/2', '2026-03-01'),
                                           ($1, $3, 'k1', NULL, '2026-01-01')""",
              U1, DOC_A, DOC_B)
    return s, trial


EVERYTHING = moved(A2, A1)
EVERYTHING_CHAPTERS = [chapter("c2", "k1", new_document=DOC_B)]


async def test_every_change_is_in_the_ledger_and_reverse_restores_exact_rows(world):
    await _everything(world)
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key)
                        VALUES ($1, $2, 'c2')""", U2, DOC_A)
    before = await digest(world)
    counts = await forward(world, EVERYTHING, EVERYTHING_CHAPTERS)
    entries = ledger_entries(world)
    changed = sum(v for k, v in counts.items()
                  if k.endswith((".repointed", ".dropped", ".rewritten", ".first_chapter")))
    merged_moves = sum(1 for e in entries if e["action"] == "moved" and e["rule"] == "merged")
    assert len(entries) == changed + merged_moves
    assert await digest(world) != before
    rcounts = await reverse(world)
    assert await digest(world) == before
    assert not [k for k in rcounts if "skipped" in k]


async def test_the_ledger_is_private_and_its_hash_is_recorded(world):
    await bookmark(world, A2, note="private note")
    await forward(world, EVERYTHING)
    path = world.remap.ledger_path(RELEASE)
    assert os.stat(path).st_mode & 0o777 == 0o600
    hashes = json.loads(await val(world, "SELECT snapshot_sha256::text FROM corpus_publishes"))
    assert R.LEDGER_FILE in hashes
    with open(path, "a", encoding="utf-8") as f:
        f.write("{}\n")
    with pytest.raises(R.RemapFault, match="differs from the sha256"):
        await reverse(world)


async def test_reverse_without_a_ledger_moves_nothing(world):
    """A publish applied without the remap (before 4.1a) has nothing to undo."""
    await sql(world, "UPDATE corpus_publishes SET applied_at = now()")
    await bookmark(world, A1)
    before = await digest(world)
    assert await reverse(world) == {}
    assert await digest(world) == before


# --------------------------------------------------------------------------- changes in the window

async def test_deleted_surviving_bookmark_is_not_recreated(world):
    await bookmark(world, A2, note="a", at="2026-01-01")
    await bookmark(world, A1, note="b", at="2026-02-01")
    await forward(world, EVERYTHING)
    await sql(world, "DELETE FROM bookmarks")
    counts = await reverse(world)
    assert await val(world, "SELECT count(*) FROM bookmarks") == 0
    assert counts == {"bookmarks.skipped_deleted_by_user": 2}


async def test_edited_joined_note_is_kept_and_the_dropped_bookmark_not_recreated(world):
    survivor = await bookmark(world, A2, note="a", at="2026-01-01")
    await bookmark(world, A1, note="b", at="2026-02-01")
    await forward(world, EVERYTHING)
    await sql(world, "UPDATE bookmarks SET note = 'my edit' WHERE id = $1", survivor)
    counts = await reverse(world)
    assert await rows(world, "SELECT id::text, chunk_id::text, note FROM bookmarks") == [
        {"id": survivor, "chunk_id": A1, "note": "my edit"}]
    assert counts == {"bookmarks.skipped_changed_by_user": 2}


async def test_deleted_search_with_deduplicated_retrievals_is_skipped(world):
    s = await search(world)
    await retrieval(world, s, A1, 1)
    await retrieval(world, s, A2, 2)
    await forward(world, EVERYTHING)
    await sql(world, "DELETE FROM searches WHERE id = $1", s)
    counts = await reverse(world)
    assert await val(world, "SELECT count(*) FROM retrievals") == 0
    assert counts == {"retrievals.skipped_parent_deleted": 1}


async def test_deleted_account_is_skipped(world):
    await _everything(world)
    await forward(world, EVERYTHING, EVERYTHING_CHAPTERS)
    await sql(world, "DELETE FROM auth.users WHERE id = $1", U1)
    counts = await reverse(world)
    assert await val(world, "SELECT count(*) FROM bookmarks") == 1      # U2's, moved back
    assert await val(world, "SELECT chunk_id::text FROM bookmarks") == A2
    assert counts["bookmarks.skipped_parent_deleted"] == 2
    assert counts["retrievals.skipped_parent_deleted"] == 1
    assert counts["reading_progress.skipped_parent_deleted"] >= 1
    assert counts["bookmarks.restored"] == 1


async def test_claimed_guest_trial_is_not_refilled(world):
    trial = str(await val(world, "INSERT INTO guest_trials DEFAULT VALUES RETURNING id"))
    for chunk, rank in ((A2, 1), (A1, 2)):
        await sql(world, """INSERT INTO guest_trial_retrievals (guest_trial_id, chunk_id, rank)
                            VALUES ($1, $2, $3)""", trial, chunk, rank)
    await forward(world, EVERYTHING)
    await sql(world, "UPDATE guest_trials SET claimed_by = $1, claimed_at = now() WHERE id = $2",
              U1, trial)
    counts = await reverse(world)
    assert await rows(world, "SELECT chunk_id::text, rank FROM guest_trial_retrievals") == [
        {"chunk_id": A2, "rank": 1}]
    assert counts == {"guest_trial_retrievals.restored": 1,
                      "guest_trial_retrievals.skipped_guest_claimed": 1}


async def test_advanced_reading_position_is_kept(world):
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor)
                        VALUES ($1, $2, 'c1', 'a/2')""", U1, DOC_A)
    await forward(world, EVERYTHING)
    await sql(world, """UPDATE reading_progress SET chapter_key = 'c2', anchor = 'a/4',
                        updated_at = now()""")
    counts = await reverse(world)
    assert await rows(world, "SELECT chapter_key, anchor FROM reading_progress") == [
        {"chapter_key": "c2", "anchor": "a/4"}]
    assert counts == {"reading_progress.skipped_changed_by_user": 1}


async def test_bookmark_made_on_a_target_after_the_apply_is_not_moved(world):
    """A1 existed before the apply. U2 bookmarks it afterwards; reverse moves only what
    forward moved, and counts U2's row."""
    await bookmark(world, A2)
    await forward(world, EVERYTHING)
    late = await bookmark(world, A1, user=U2, at="2099-01-01")
    counts = await reverse(world)
    got = {r["id"]: r["chunk_id"] for r in await rows(world, "SELECT id::text, chunk_id::text FROM bookmarks")}
    assert got[late] == A1 and A2 in got.values()
    assert counts == {"bookmarks.restored": 1, "bookmarks.untouched_made_after_apply": 1}


async def test_a_row_already_on_the_target_before_the_apply_is_never_moved(world):
    resident = await bookmark(world, A1, user=U2)
    await bookmark(world, A2)
    await forward(world, EVERYTHING)
    await reverse(world)
    assert await val(world, "SELECT chunk_id::text FROM bookmarks WHERE id = $1", resident) == A1


async def test_unique_key_taken_is_skipped(world):
    await bookmark(world, A2, note="mine")
    await forward(world, EVERYTHING)
    # A new bookmark on the old passage (say through an old link) holds its key.
    await bookmark(world, A2, at="2099-01-01")
    counts = await reverse(world)
    assert counts == {"bookmarks.skipped_unique_key_taken": 1}


async def test_reverse_skip_never_aborts(world):
    """Every skip condition at once: reverse completes and the transaction commits."""
    s, trial = await _everything(world)
    await bookmark(world, A1, user=U2, note="u2 a", at="2026-03-01")
    u3 = "00000000-0000-0000-0000-0000000000a3"
    await sql(world, "INSERT INTO auth.users (id) VALUES ($1)", u3)
    await bookmark(world, A2, user=u3)
    await forward(world, EVERYTHING, EVERYTHING_CHAPTERS)
    await sql(world, "DELETE FROM product_feedback")
    await bookmark(world, A2, user=u3, at="2099-01-01")
    await sql(world, "DELETE FROM searches WHERE id = $1", s)
    await sql(world, "UPDATE guest_trials SET claimed_at = now() WHERE id = $1", trial)
    await sql(world, "UPDATE bookmarks SET note = 'edited' WHERE user_id = $1", U1)
    await sql(world, "UPDATE reading_progress SET updated_at = now()")
    await sql(world, "DELETE FROM auth.users WHERE id = $1", U2)
    conn = await world.connect()
    try:
        tr = conn.transaction()
        await tr.start()
        counts = (await world.remap.reverse(conn, RELEASE)).counts
        await tr.commit()
    finally:
        await conn.close()
    assert counts == {
        "bookmarks.skipped_changed_by_user": 2,      # U1 edited the joined note
        "bookmarks.skipped_parent_deleted": 2,       # U2 deleted their account
        "bookmarks.skipped_unique_key_taken": 1,     # u3 bookmarked the old passage again
        "guest_trial_retrievals.restored": 1,
        "guest_trial_retrievals.skipped_guest_claimed": 1,
        "product_feedback.skipped_deleted_by_user": 1,
        "reading_progress.skipped_changed_by_user": 1,
        "reading_progress.untouched_made_after_apply": 1,   # U1's other position, touched
        "retrieval_labels.skipped_parent_deleted": 1,   # the search was deleted
        "retrievals.skipped_parent_deleted": 1,
    }



# --------------------------------------------------------------------------- 2.2w and the CLI

def test_impl_satisfies_2_2w_protocol():
    impl: A.UserDataRemap = R.UserDataRemapImpl()
    for name in ("forward", "reverse"):
        theirs = inspect.signature(getattr(A.UserDataRemap, name))
        ours = inspect.signature(getattr(type(impl), name))
        assert list(ours.parameters) == list(theirs.parameters)
        assert inspect.iscoroutinefunction(getattr(type(impl), name))


async def test_dry_run_never_writes_and_prints_the_counts(world, tmp_path, capsys):
    await bookmark(world, A2)
    path = tmp_path / "redirects.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in EVERYTHING))
    before = await digest(world)
    conn = await world.connect()
    try:
        plan = await R.dry_run(conn, str(path), rows=True)
    finally:
        await conn.close()
    assert await digest(world) == before
    assert not os.path.exists(world.remap.ledger_path(RELEASE))
    out = capsys.readouterr().out
    assert "bookmarks.repointed: 1" in out and dict(plan.counts) == {"bookmarks.repointed": 1}


def test_cli_requires_dry_run():
    with pytest.raises(SystemExit):
        R.build_parser().parse_args([])


async def _stage_and_report(world, request):
    await world.runner().stage(request)
    conn = await world.connect()
    try:
        content = await staged_content_sha256(conn)
        await conn.execute("UPDATE corpus_publishes SET report_sha256 = $2 WHERE id = $1",
                           request.release, f"report:{content}")
    finally:
        await conn.close()


async def test_full_apply_and_rollback_move_user_rows_and_back(world):
    """Through 2.2w: a/2 is renumbered a/2n; apply moves the rows on a/2 inside its
    transaction, and rollback puts them back exactly."""
    release = "remap-flow"
    await sql(world, "DELETE FROM corpus_publishes")
    a = next(d for d in world.build if d.id == DOC_A)
    a.passages[1] = passage("a/2n", "c1", a.passages[1].content, 1)
    new = pid(DOC_A, "a/2n")
    world.registry.redirects.append(
        {"document_id": DOC_A, "old_passage_id": A2, "old_anchor": "a/2",
         "new_passage_id": new, "new_anchor": "a/2n", "kind": "renumbered"})
    next(r for r in world.registry.passages if r["passage_id"] == A2)["status"] = "redirected"
    world.registry.__post_init__()
    s = await search(world)
    await bookmark(world, A2, note="kept")
    await retrieval(world, s, A2, 1)
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor)
                        VALUES ($1, $2, 'c1', 'a/2')""", U1, DOC_A)
    before = await digest(world)
    await _stage_and_report(world, StageRequest(release=release, collections=("medieval",)))

    conn = await world.connect()
    try:
        result = await A.apply(conn, release, root=world.snapshots, remap=world.remap)
    finally:
        await conn.close()
    assert result.remap == {"bookmarks.repointed": 1, "reading_progress.rewritten": 1,
                            "retrievals.repointed": 1}
    assert await val(world, "SELECT chunk_id::text FROM bookmarks") == new
    assert await rows(world, "SELECT anchor FROM reading_progress") == [{"anchor": "a/2n"}]

    conn = await world.connect()
    try:
        back = await A.rollback(conn, world.qdrant, release, alias="chunks_live",
                                root=world.snapshots, remap=world.remap)
    finally:
        await conn.close()
    assert back.remap == {"bookmarks.restored": 1, "reading_progress.restored": 1,
                          "retrievals.restored": 1}
    assert await digest(world) == before


def _rename_a2(world, chapter_key="c1"):
    """a/2 becomes a/2n (in `chapter_key`), with the registry's redirect."""
    a = next(d for d in world.build if d.id == DOC_A)
    a.passages[1] = passage("a/2n", chapter_key, a.passages[1].content, 1)
    world.registry.redirects.append(
        {"document_id": DOC_A, "old_passage_id": A2, "old_anchor": "a/2",
         "new_passage_id": pid(DOC_A, "a/2n"), "new_anchor": "a/2n", "kind": "renumbered"})
    next(r for r in world.registry.passages if r["passage_id"] == A2)["status"] = "redirected"


async def test_removed_chapter_through_stage_and_apply_goes_to_the_first_chapter(world):
    """Chapter c2 (a/3, a/4) is removed with no successor: 2.2w writes tombstones and no
    chapter redirect, and the reading position in it still moves (step 2)."""
    await sql(world, "DELETE FROM corpus_publishes")
    a = next(d for d in world.build if d.id == DOC_A)
    for anchor in ("a/3", "a/4"):
        world.registry.removals.append(
            {"collection": "medieval", "church_act": None, "id": f"rm-{anchor}",
             "scope": "passage", "document_id": DOC_A, "anchor": anchor,
             "passage_id": pid(DOC_A, anchor), "reason": "debris", "tombstone": "Removed."})
    a.passages = a.passages[:2]
    world.registry.__post_init__()
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor)
                        VALUES ($1, $2, 'c2', 'a/3')""", U1, DOC_A)
    before = await digest(world)
    await _stage_and_report(world, StageRequest(release="removed-chapter", collections=("medieval",)))
    assert await val(world, "SELECT count(*) FROM staging.corpus_redirects WHERE entity = 'chapter'") == 0
    conn = await world.connect()
    try:
        result = await A.apply(conn, "removed-chapter", root=world.snapshots, remap=world.remap)
        assert result.remap == {"reading_progress.first_chapter": 1}
        assert await rows(world, "SELECT chapter_key, anchor FROM reading_progress") == [
            {"chapter_key": "c1", "anchor": None}]
        await A.rollback(conn, world.qdrant, "removed-chapter", alias="chunks_live",
                         root=world.snapshots, remap=world.remap)
    finally:
        await conn.close()
    assert await digest(world) == before


async def test_dry_run_plans_what_forward_then_does(world):
    """The dry run reads the staged corpus: a/2n is only in staging and sits in a new
    chapter, and the plan for the reading position equals what the apply writes."""
    await sql(world, "DELETE FROM corpus_publishes")
    _rename_a2(world, chapter_key="c1b")
    world.registry.__post_init__()
    await bookmark(world, A2)
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor)
                        VALUES ($1, $2, 'c1', 'a/2')""", U1, DOC_A)
    await _stage_and_report(world, StageRequest(release="dry-run", collections=("medieval",)))
    conn = await world.connect()
    try:
        plan = await R.dry_run(conn)
        result = await A.apply(conn, "dry-run", root=world.snapshots, remap=world.remap)
    finally:
        await conn.close()
    assert dict(plan.counts) == result.remap == {"bookmarks.repointed": 1,
                                                 "reading_progress.rewritten": 1}
    planned = [e["after"] for e in plan.entries if e["table"] == "reading_progress"]
    assert [{k: p[k] for k in ("chapter_key", "anchor")} for p in planned] == [
        {"chapter_key": "c1b", "anchor": "a/2n"}]
    assert await rows(world, "SELECT chapter_key, anchor FROM reading_progress") == [
        {"chapter_key": "c1b", "anchor": "a/2n"}]


async def test_reading_positions_swapping_documents_round_trip(world):
    """Chapters move A to B and B to A: both of a user's positions move, and reverse puts
    both back, though each one's old key is the other's new key."""
    await sql(world, "UPDATE chunks SET chapter_key = 'k1' WHERE id = $1", A3)
    await sql(world, "UPDATE chunks SET chapter_key = 'c2' WHERE id = $1", B1)
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key)
                        VALUES ($1, $2, 'c1'), ($1, $3, 'k9')""", U1, DOC_A, DOC_B)
    before = await digest(world)
    counts = await forward(world, [], [chapter("c1", "c2", new_document=DOC_B),
                                       chapter("k9", "k1", document=DOC_B, new_document=DOC_A)])
    assert counts == {"reading_progress.rewritten": 2}
    assert await reverse(world) == {"reading_progress.restored": 2}
    assert await digest(world) == before


async def test_reading_position_saved_after_the_apply_is_counted(world):
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key, anchor)
                        VALUES ($1, $2, 'c1', 'a/2')""", U1, DOC_A)
    await forward(world, EVERYTHING)
    await sql(world, """INSERT INTO reading_progress (user_id, document_id, chapter_key, updated_at)
                        VALUES ($1, $2, 'c1', '2099-01-01')""", U2, DOC_A)
    counts = await reverse(world)
    assert counts == {"reading_progress.restored": 1,
                      "reading_progress.untouched_made_after_apply": 1}
