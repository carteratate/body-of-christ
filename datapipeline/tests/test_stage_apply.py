"""The stage-then-apply writer (corpus-cleanup 2.2w) against a real PostgreSQL and an
in-memory Qdrant.

Acceptance checks: docs/corpus-cleanup/P2-P3-schema-reader-policy.md, item 2.2w. This
part covers stage, report, status and discard; the apply, switch, rollback and cleanup
checks arrive with them.
"""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

import reader_access
import registry
from identity import passage_id
from model import Document, Work
from publication import StageRequest, StageRefused
from tests import pg_corpus
from writers import reader_writer
from tests.stage_world import (DOC_A, DOC_B, DOC_S, LIVE, World, contents_tree, passage,
                               pid)

STAGE = StageRequest(release="test-release", collections=("medieval",))


@pytest.fixture(scope="module")
def cluster():
    cluster, stop = pg_corpus.start()
    yield cluster
    stop()


@pytest.fixture()
async def world(cluster, tmp_path):
    w = World(cluster, cluster.new_database(), tmp_path)
    await w.seed()
    return w


def _doc(world, document_id) -> Document:
    return next(d for d in world.build if d.id == document_id)


def _removal(**entry) -> dict:
    return {"collection": "medieval", "church_act": None, "anchor": None,
            "passage_id": None, **entry}


# --------------------------------------------------------------------------- stage

async def test_stage_writes_only_staging_and_a_new_collection(world):
    before = await world.public_digest()
    live_points = await world.qdrant.count("chunks")
    result = await world.runner().stage(STAGE)

    assert await world.public_digest() == before
    assert (await world.qdrant.count("chunks")).count == live_points.count
    [alias] = (await world.qdrant.get_aliases()).aliases
    assert (alias.alias_name, alias.collection_name) == ("chunks_live", "chunks")
    assert result.qdrant_collection == "chunks-test-release"
    staged = await world.fetch("SELECT id::text FROM staging.chunks ORDER BY id")
    assert {r["id"] for r in staged} == {pid(d, a) for d, a, _, _ in LIVE if d != DOC_S}
    [publish] = await world.fetch("SELECT * FROM corpus_publishes")
    assert publish["collections"] == ["medieval"] and publish["staged_at"] is not None
    assert publish["applied_at"] is None


async def test_rebuilt_anchor_keeps_the_frozen_id(world):
    """D1: a unit whose anchor changes from a label slug to a structural anchor keeps
    the ID the passage registry holds; only an anchor redirect is produced, no passage
    redirect and no retirement."""
    old = pid(DOC_A, "a/2")
    row = next(r for r in world.registry.passages if r["passage_id"] == old)
    row["anchor"] = "a/II"
    world.registry.__post_init__()
    _doc(world, DOC_A).passages[1].anchor = "a/II"

    result = await world.runner().stage(STAGE)
    [chunk] = await world.fetch("SELECT id::text, anchor FROM staging.chunks WHERE anchor = 'a/II'")
    assert chunk["id"] == old
    assert result.tombstones == 0
    redirects = await world.fetch("SELECT entity, old_anchor, new_anchor FROM staging.corpus_redirects")
    assert redirects == [{"entity": "anchor", "old_anchor": "a/2", "new_anchor": "a/II"}]


async def test_only_unknown_units_get_new_ids(world):
    """A restored verse gets a new ID from identity.passage_id, and the stage lists it."""
    a = _doc(world, DOC_A)
    a.passages.append(passage("a/5", "c2", "A restored line of the treatise.", 4))
    result = await world.runner().stage(STAGE)
    assert result.new_ids == [passage_id(DOC_A, "a/5")]


async def test_removed_ids_get_tombstones_from_the_registry(world):
    """A `passage` entry yields reason_code, public_reason, the rendered Church act and
    the derived rule; the live passage is no longer staged."""
    world.registry.removals.append(_removal(
        id="rm-0900", scope="passage", document_id=DOC_A, anchor="a/4",
        passage_id=pid(DOC_A, "a/4"), reason="rule-b",
        tombstone="Removed: a later forgery.",
        church_act={"issuer": "Second Council of Constantinople", "act": "anathema 11",
                    "date": "0553-05-14", "citation": "Tanner I, 120"}))
    result = await world.runner().stage(STAGE)
    assert result.tombstones == 1
    [t] = await world.fetch("SELECT * FROM staging.corpus_tombstones")
    assert (t["entity"], str(t["id"]), t["removal_key"], t["reason_code"], t["rule"],
            t["public_reason"], t["church_act"], t["publish_id"]) == (
        "passage", pid(DOC_A, "a/4"), "rm-0900", "rule-b", "B", "Removed: a later forgery.",
        "Second Council of Constantinople, anathema 11, 553", "test-release")
    assert json.loads(t["snapshot"]) == {"collection": "medieval", "title": "On Loving God",
                                         "author": "Bernard of Clairvaux",
                                         "reference": "A/4", "chapter_label": "C2"}
    assert not await world.fetch("SELECT 1 FROM staging.chunks WHERE id = $1::uuid",
                                 pid(DOC_A, "a/4"))


async def test_a_span_entry_yields_no_tombstone(world):
    world.registry.removals.append(_removal(
        id="rm-0901", scope="span", document_id=DOC_A, anchor="a/1", reason="debris",
        tombstone=None, span={"rule": "x", "count": 1}))
    assert (await world.runner().stage(STAGE)).tombstones == 0


async def test_a_document_entry_retires_the_document_and_each_passage(world):
    world.registry.removals.append(_removal(
        id="rm-0902", scope="document", document_id=DOC_B, reason="awaiting-permission",
        tombstone="Held until permission is granted."))
    result = await world.runner().stage(STAGE)
    rows = await world.fetch("SELECT entity, id::text, rule FROM staging.corpus_tombstones "
                             "ORDER BY entity")
    assert rows == [{"entity": "document", "id": DOC_B, "rule": "other"},
                    {"entity": "passage", "id": pid(DOC_B, "b/1"), "rule": "other"}]
    assert result.documents == 1


async def test_unexplained_retirement_stops_the_stage(world):
    """D4: a live ID the build drops with no registry entry and no redirect stops the
    stage, names the ID, and leaves staging and Qdrant as they were."""
    a = _doc(world, DOC_A)
    a.passages = a.passages[:3]
    with pytest.raises(StageRefused, match=pid(DOC_A, "a/4")):
        await world.runner().stage(STAGE)
    assert not await world.fetch("SELECT 1 FROM staging.chunks")
    assert not await world.fetch("SELECT 1 FROM corpus_publishes")
    assert not await world.qdrant.collection_exists("chunks-test-release")


async def test_redirects_written_for_renumbered_and_split(world):
    """A declared `renumbered` redirect and a two-target `split` each yield one passage
    redirect at the primary (earliest) target, and the anchor redirect follows it."""
    a = _doc(world, DOC_A)
    a.passages = [a.passages[0],
                  passage("a/2a", "c1", "Faith seeks understanding", 1),
                  passage("a/2b", "c1", "in all things.", 2),
                  passage("a/3n", "c2", a.passages[2].content, 3),
                  replace(a.passages[3], position=4)]
    old2, old3 = pid(DOC_A, "a/2"), pid(DOC_A, "a/3")
    world.registry.redirects += [
        {"document_id": DOC_A, "old_passage_id": old2, "old_anchor": "a/2",
         "new_passage_id": pid(DOC_A, "a/2b"), "new_anchor": "a/2b", "kind": "split"},
        {"document_id": DOC_A, "old_passage_id": old2, "old_anchor": "a/2",
         "new_passage_id": pid(DOC_A, "a/2a"), "new_anchor": "a/2a", "kind": "split"},
        {"document_id": DOC_A, "old_passage_id": old3, "old_anchor": "a/3",
         "new_passage_id": pid(DOC_A, "a/3n"), "new_anchor": "a/3n", "kind": "renumbered"},
    ]
    for r in world.registry.passages:
        if r["passage_id"] in (old2, old3):
            r["status"] = "redirected"
    world.registry.__post_init__()
    await world.runner().stage(STAGE)
    rows = await world.fetch(
        "SELECT entity, old_id::text, new_id::text, old_anchor, new_anchor, kind "
        "FROM staging.corpus_redirects ORDER BY entity, old_anchor")
    assert rows == [
        {"entity": "anchor", "old_id": None, "new_id": None, "old_anchor": "a/2",
         "new_anchor": "a/2a", "kind": "moved"},
        {"entity": "anchor", "old_id": None, "new_id": None, "old_anchor": "a/3",
         "new_anchor": "a/3n", "kind": "moved"},
        {"entity": "passage", "old_id": old2, "new_id": pid(DOC_A, "a/2a"),
         "old_anchor": "a/2", "new_anchor": "a/2a", "kind": "split"},
        {"entity": "passage", "old_id": old3, "new_id": pid(DOC_A, "a/3n"),
         "old_anchor": "a/3", "new_anchor": "a/3n", "kind": "renumbered"},
    ]


async def test_chapter_redirect_for_a_moved_chapter(world):
    a = _doc(world, DOC_A)
    for p in a.passages[2:]:
        p.chapter_key, p.chapter_label = "c2-new", "Chapter Two"
    await world.runner().stage(STAGE)
    rows = await world.fetch("SELECT old_anchor, new_anchor FROM staging.corpus_redirects "
                             "WHERE entity = 'chapter'")
    assert rows == [{"old_anchor": "c2", "new_anchor": "c2-new"}]


async def test_chapter_redirect_follows_the_primary_split_target(world):
    """A split whose targets lie in two chapters redirects the old chapter where the
    passage redirect points: the earliest target, whatever order the file lists them."""
    a = _doc(world, DOC_A)
    a.passages = [passage("a/1x", "c0", "Grace perfects nature", 0),
                  passage("a/1y", "c9", "and does not destroy it.", 1)] + \
        [replace(p, position=i + 2) for i, p in enumerate(a.passages[1:])]
    old = pid(DOC_A, "a/1")
    world.registry.redirects += [
        {"document_id": DOC_A, "old_passage_id": old, "old_anchor": "a/1",
         "new_passage_id": pid(DOC_A, t), "new_anchor": t, "kind": "split"}
        for t in ("a/1y", "a/1x")]
    next(r for r in world.registry.passages if r["passage_id"] == old)["status"] = "redirected"
    world.registry.__post_init__()
    await world.runner().stage(STAGE)
    rows = await world.fetch("SELECT entity, new_anchor FROM staging.corpus_redirects "
                             "WHERE entity IN ('passage', 'anchor') ORDER BY entity")
    assert {r["new_anchor"] for r in rows} == {"a/1x"}


async def test_passage_moved_between_documents_keeps_its_id(world):
    """A live passage the build emits under another document is not a retirement: it
    keeps its ID (and moves at the apply), and only its anchor redirects."""
    a, b = _doc(world, DOC_A), _doc(world, DOC_B)
    moved = a.passages.pop()
    b.passages.append(replace(moved, position=1))
    row = next(r for r in world.registry.passages if r["passage_id"] == pid(DOC_A, "a/4"))
    row["document_id"] = DOC_B
    world.registry.__post_init__()
    result = await world.runner().stage(STAGE)
    assert result.moved == 1 and result.tombstones == 0
    [chunk] = await world.fetch("SELECT document_id::text FROM staging.chunks WHERE id = $1::uuid",
                                pid(DOC_A, "a/4"))
    assert chunk["document_id"] == DOC_B
    [r] = await world.fetch("SELECT entity, old_document_id::text, new_document_id::text "
                            "FROM staging.corpus_redirects WHERE entity = 'anchor'")
    assert (r["old_document_id"], r["new_document_id"]) == (DOC_A, DOC_B)


async def test_history_passage_gets_superseded_by(world):
    a = _doc(world, DOC_A)
    a.passages.append(passage("a/4/history-1983", "c2", "The earlier wording.", 4,
                              searchable=False, superseded_by_anchor="a/4"))
    await world.runner().stage(STAGE)
    [row] = await world.fetch("SELECT superseded_by::text, searchable FROM staging.chunks "
                              "WHERE anchor = 'a/4/history-1983'")
    assert row == {"superseded_by": pid(DOC_A, "a/4"), "searchable": False}


async def test_voice_reaches_staging_and_payload(world):
    a = _doc(world, DOC_A)
    a.passages[0].voice = "rejected"
    a.passages[0].unit_label = "Objection 1"
    await world.runner().stage(STAGE)
    [row] = await world.fetch("SELECT voice FROM staging.chunks WHERE id = $1::uuid",
                              pid(DOC_A, "a/1"))
    assert row["voice"] == "rejected"
    [point] = await world.qdrant.retrieve("chunks-test-release", ids=[pid(DOC_A, "a/1")])
    assert point.payload["voice"] == "rejected"


async def test_document_facts_and_works_reach_staging(world):
    a = _doc(world, DOC_A)
    a.genre, a.issuer, a.issuer_label = "treatise", "bernard-of-clairvaux", "Bernard"
    a.form = "brief"
    a.works = [Work(work_key="w1", ordinal=1, title="Book One", author="Bernard")]
    a.passages[0].work_key = "w1"
    await world.runner().stage(STAGE)
    [doc] = await world.fetch("SELECT genre, form, issuer, issuer_label FROM staging.documents "
                              "WHERE id = $1::uuid", DOC_A)
    assert doc == {"genre": "treatise", "form": "brief", "issuer": "bernard-of-clairvaux",
                   "issuer_label": "Bernard"}
    assert await world.fetch("SELECT work_key, title FROM staging.document_works") == \
        [{"work_key": "w1", "title": "Book One"}]


async def test_document_facts_reach_staging_and_live_after_apply(world, monkeypatch, tmp_path):
    """2.3: the registry's facts win over the adapter's, reach staging, and reach live in
    the apply, with certainty and clavis_ref from the entry's attribution."""
    from release.staged import staged_content_sha256
    from writers import apply as A

    monkeypatch.setattr(reader_access, "access_for", lambda document_id: "full")
    entry = world.registry.entry_by_document[DOC_A]
    entry.update({k: None for k in registry.FACT_FIELDS})
    entry.update(genre="treatise", form="bull", year=1128, date_display="c. 1128",
                 translation="William Harman van Allen (1909)",
                 source_credit="Sourced via CCEL.org",
                 notes="Preserved in Eusebius, Church History.",
                 card_translator="Translated by William Harman van Allen (1909)")
    entry["attribution"].update(certainty="genuine", clavis="PL 182")
    a = _doc(world, DOC_A)
    a.year, a.translation, a.genre = 1099, "adapter", "sermon"

    await world.runner().stage(STAGE)
    columns = ("genre, form, year, date_display, translation, source_credit, notes, "
               "certainty, clavis_ref, issuer")
    want = {"genre": "treatise", "form": "bull", "year": 1128, "date_display": "c. 1128",
            "translation": "William Harman van Allen (1909)",
            "source_credit": "Sourced via CCEL.org",
            "notes": "Preserved in Eusebius, Church History.",
            "certainty": "genuine", "clavis_ref": "PL 182", "issuer": None}
    query = f"SELECT {columns} FROM {{}}.documents WHERE id = $1::uuid"
    assert await world.fetch(query.format("staging"), DOC_A) == [want]
    # 4.4: the card's keys ride in the document's metadata.
    card = ("SELECT metadata->>'card_version' AS v, metadata->>'card_translator' AS t, "
            "metadata->'card_notes' AS notes FROM {}.documents WHERE id = $1::uuid")
    card_want = {"v": "1", "t": "Translated by William Harman van Allen (1909)",
                 "notes": [{"kind": None, "text": "Preserved in Eusebius, Church History",
                            "show": "record"}]}

    def decoded(rows):
        return [{**r, "notes": json.loads(r["notes"]) if isinstance(r["notes"], str)
                 else r["notes"]} for r in rows]

    assert decoded(await world.fetch(card.format("staging"), DOC_A)) == [card_want]

    conn = await world.connect()
    try:
        content = await staged_content_sha256(conn)
        await conn.execute("UPDATE corpus_publishes SET report_sha256 = $2 WHERE id = $1",
                           STAGE.release, f"report:{content}")
        await A.apply(conn, STAGE.release, root=str(tmp_path / "snapshots"))
    finally:
        await conn.close()
    assert await world.fetch(query.format("public"), DOC_A) == [want]
    assert decoded(await world.fetch(card.format("public"), DOC_A)) == [card_want]


async def test_a_stage_refuses_a_database_without_0044(world):
    """Issue #330: the writer stages documents.form, so a database without migration
    0044 is refused by name before anything is written, not halfway through."""
    conn = await world.connect()
    try:
        await conn.execute("ALTER TABLE documents DROP COLUMN form")
    finally:
        await conn.close()
    before = await world.public_digest()
    with pytest.raises(ValueError, match="live documents has no form.*0044"):
        await world.runner().stage(STAGE)
    assert await world.public_digest() == before


async def test_the_contents_tree_is_staged_with_the_chunks(world):
    """Carter, 2 Nov 2026: the contents tree travels with the passages."""
    _doc(world, DOC_A).contents = contents_tree()
    await world.runner().stage(STAGE)
    rows = await world.fetch("SELECT ordinal, parent_ordinal, node_key, chapter_key, anchor "
                             "FROM staging.document_contents ORDER BY ordinal")
    assert [(r["node_key"], r["parent_ordinal"], r["anchor"]) for r in rows] == \
        [("book", None, None), ("c2", rows[0]["ordinal"], "a/3")]
    # A stage that drops the tree drops its staged rows too.
    _doc(world, DOC_A).contents = None
    await world.runner().stage(STAGE)
    assert not await world.fetch("SELECT 1 FROM staging.document_contents")


async def test_reader_access_is_staged_from_the_rights_inventory(world, monkeypatch):
    """D12, Carter 2 Nov 2026: stage writes each document's reader_access from the
    inventory, so the report and the staging eval see it."""
    monkeypatch.setattr(reader_access, "access_for",
                        lambda document_id: "full" if document_id == DOC_A else "excerpt")
    await world.runner().stage(STAGE)
    rows = await world.fetch("SELECT id::text, reader_access FROM staging.documents ORDER BY id")
    assert rows == [{"id": DOC_A, "reader_access": "full"},
                    {"id": DOC_B, "reader_access": "excerpt"}]


async def test_staged_outline_and_full_text_index_exist(world):
    await world.runner().stage(STAGE)
    chapters = await world.fetch("SELECT document_id::text, chapter_key FROM "
                                 "staging.document_chapters ORDER BY document_id, ordinal")
    assert chapters == [{"document_id": DOC_A, "chapter_key": "c1"},
                        {"document_id": DOC_A, "chapter_key": "c2"},
                        {"document_id": DOC_B, "chapter_key": "k1"}]
    [count] = await world.fetch("SELECT chunk_count FROM staging.documents WHERE id = $1::uuid", DOC_A)
    assert count["chunk_count"] == 4
    hits = await world.fetch("SELECT id::text FROM staging.chunks "
                             "WHERE search_vector @@ to_tsquery('english', 'charity')")
    assert hits == [{"id": pid(DOC_A, "a/4")}]


async def test_metadata_passes_through_unchanged(world):
    """1.10b's per-piece footnotes, 1.10c's piece references and 1.2f's OCR source
    reach staging exactly as built."""
    metadata = {"footnotes": [{"n": 1, "text": "Cf. Augustine."}], "text_source": "ocr",
                "piece": {"index": 2, "of": 3}, "editor_note_count": 4}
    a = _doc(world, DOC_A)
    a.passages[0].metadata = metadata
    a.passages[0].reference = "A/1 (part 2 of 3)"
    a.metadata = {"text_source": "ocr", "source_key": "medieval/On Loving God"}
    await world.runner().stage(STAGE)
    [row] = await world.fetch("SELECT metadata, reference FROM staging.chunks WHERE id = $1::uuid",
                              pid(DOC_A, "a/1"))
    assert json.loads(row["metadata"]) == metadata
    assert row["reference"] == "A/1 (part 2 of 3)"
    [doc] = await world.fetch("SELECT metadata FROM staging.documents WHERE id = $1::uuid", DOC_A)
    assert json.loads(doc["metadata"])["text_source"] == "ocr"


async def test_live_annotations_are_copied_into_staging(world):
    conn = await world.connect()
    await conn.execute("UPDATE chunks SET annotation = '{\"a\": 1}' WHERE id = $1::uuid",
                       pid(DOC_A, "a/1"))
    await conn.close()
    await world.runner().stage(STAGE)
    [row] = await world.fetch("SELECT annotation FROM staging.chunks WHERE id = $1::uuid",
                              pid(DOC_A, "a/1"))
    assert json.loads(row["annotation"]) == {"a": 1}


# --------------------------------------------------------------------------- Qdrant

async def test_every_passage_is_a_point_with_payload_facts(world):
    a = _doc(world, DOC_A)
    a.genre, a.issuer = "treatise", "bernard-of-clairvaux"
    a.passages[3].searchable = False
    await world.runner().stage(STAGE)
    points, _ = await world.qdrant.scroll("chunks-test-release", limit=100, with_payload=True)
    medieval = {str(p.id): p.payload for p in points if p.payload["collection"] == "medieval"}
    assert set(medieval) == {pid(d, a_) for d, a_, _, _ in LIVE if d != DOC_S}
    facts = medieval[pid(DOC_A, "a/4")]
    assert (facts["genre"], facts["issuer"], facts["searchable"]) == \
        ("treatise", "bernard-of-clairvaux", False)
    assert medieval[pid(DOC_B, "b/1")]["genre"] is None


async def test_publish_records_embedding_model(world):
    from config import settings

    await world.runner().stage(STAGE)
    [row] = await world.fetch("SELECT embed_model, embed_dimensions FROM corpus_publishes")
    assert row == {"embed_model": settings.EMBEDDING_MODEL, "embed_dimensions": 1536}
    [point] = await world.qdrant.retrieve("chunks-test-release", ids=[pid(DOC_A, "a/1")])
    assert point.payload["embed_model"] == settings.EMBEDDING_MODEL
    assert len(point.payload["embed_sha256"]) == 64


async def test_a_second_stage_of_the_same_build_makes_no_embedding_call(world):
    await world.runner().stage(STAGE)
    first = len(world.embedded)
    assert first == 5
    await world.runner().stage(STAGE)
    assert len(world.embedded) == first


async def test_single_collection_publish_copies_other_collections(world):
    result = await world.runner().stage(STAGE)
    assert result.copied == {"summa": 1}
    [point] = await world.qdrant.retrieve("chunks-test-release", ids=[pid(DOC_S, "s/1")],
                                          with_vectors=True)
    [live] = await world.qdrant.retrieve("chunks", ids=[pid(DOC_S, "s/1")], with_vectors=True)
    assert point.payload == live.payload and point.vector == live.vector


async def test_point_count_check_includes_copied_collections(world, monkeypatch):
    from writers import qdrant as qd

    async def copy_nothing(client, source, target, collection):
        return 0
    monkeypatch.setattr(qd, "copy_points", copy_nothing)
    with pytest.raises(StageRefused, match="summa: 0 points, 1 in the collection users search"):
        await world.runner().stage(STAGE)


async def test_a_renamed_collection_stages_its_old_key_live_rows(world):
    """5.1b.3: staging `theologians` reads the live rows filed under `medieval`, its old
    key, by ID: nothing is retired, the documents stage under the new key, no point is
    copied under the old one, and every other collection is copied as it is stored."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    renamed = {"theologians": lambda: [replace(d, collection="theologians") for d in world.build],
               "summa": lambda: []}
    live_summa = (await world.qdrant.count("chunks", count_filter=Filter(must=[
        FieldCondition(key="collection", match=MatchValue(value="summa"))]))).count
    result = await world.runner(source_adapters=renamed).stage(
        StageRequest(release="test-release", collections=("theologians",)))

    assert result.tombstones == 0 and result.redirects == {}
    assert {r["collection"] for r in await world.fetch(
        "SELECT collection FROM staging.documents")} == {"theologians"}
    assert result.copied == {"summa": live_summa}
    old_key = Filter(must=[FieldCondition(key="collection", match=MatchValue(value="medieval"))])
    assert (await world.qdrant.count("chunks-test-release", count_filter=old_key)).count == 0
    staged = sum(len(d.passages) for d in world.build)
    assert (await world.qdrant.count("chunks-test-release")).count == staged + live_summa


async def test_restaging_a_renamed_collection_clears_its_old_key_points(world):
    """A release whose Qdrant collection holds the renamed collection's points under the
    old key (copied by an earlier stage of the release that did not cover it) has them
    cleared when the new key is staged, so the point counts agree and none is left."""
    import uuid

    from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct

    renamed = {"theologians": lambda: [replace(d, collection="theologians") for d in world.build],
               "summa": lambda: []}
    request = StageRequest(release="test-release", collections=("theologians",))
    await world.runner(source_adapters=renamed).stage(request)
    [live] = (await world.qdrant.scroll("chunks", limit=1, with_vectors=True, scroll_filter=Filter(
        must=[FieldCondition(key="collection", match=MatchValue(value="medieval"))])))[0]
    await world.qdrant.upsert("chunks-test-release", points=[PointStruct(
        id=str(uuid.uuid4()), vector=live.vector, payload=live.payload)], wait=True)
    await world.runner(source_adapters=renamed).stage(request)
    old_key = Filter(must=[FieldCondition(key="collection", match=MatchValue(value="medieval"))])
    assert (await world.qdrant.count("chunks-test-release", count_filter=old_key)).count == 0


async def test_a_release_staged_under_an_old_key_is_not_copied_over(world):
    """A release staged under `medieval` (before 5.1b.3 merged) keeps its staged points
    when the adapters also know `theologians`: the old key is staged, so it is not
    copied from live as part of the unstaged new key."""
    adapters = {"medieval": lambda: world.build, "theologians": lambda: [],
                "summa": lambda: []}
    result = await world.runner(source_adapters=adapters).stage(STAGE)
    assert "medieval" not in result.copied


async def test_boethius_moves_only_when_both_collections_stage(world, monkeypatch):
    """Before 5.1b.3's apply, a Fathers-only stage leaves him where live has him (his
    points copied as stored), a stage of `theologians` alone refuses, and a stage of
    both moves him."""
    import publication

    monkeypatch.setattr(publication, "BOETHIUS_DOCUMENT_ID", DOC_B)
    adapters = {"church-fathers": lambda: [replace(_doc(world, DOC_B), collection="church-fathers")],
                "theologians": lambda: [replace(_doc(world, DOC_A), collection="theologians")],
                "summa": lambda: []}
    fathers = await world.runner(source_adapters=adapters).stage(
        StageRequest(release="fathers-only", collections=("church-fathers",)))
    assert fathers.documents == 0 and fathers.tombstones == 0
    assert "medieval" in fathers.copied
    conn = await world.connect()
    try:
        await conn.execute("UPDATE corpus_publishes SET discarded_at = now()")
        await reader_writer.clear_staged_collections(conn, ["church-fathers", "medieval",
                                                            "theologians", "summa"])
    finally:
        await conn.close()
    with pytest.raises(StageRefused, match="stage theologians with church-fathers"):
        await world.runner(source_adapters=adapters).stage(
            StageRequest(release="theologians-only", collections=("theologians",)))
    both = await world.runner(source_adapters=adapters).stage(
        StageRequest(release="both", collections=("church-fathers", "theologians")))
    assert both.tombstones == 0
    assert {r["id"]: r["collection"] for r in await world.fetch(
        "SELECT id::text, collection FROM staging.documents")} == {
        DOC_B: "church-fathers", DOC_A: "theologians"}


async def test_restaging_the_fathers_keeps_a_release_s_boethius_move(world, monkeypatch):
    """A release that staged both keys keeps moving him when only `church-fathers` is
    restaged: its earlier collections count."""
    import publication

    monkeypatch.setattr(publication, "BOETHIUS_DOCUMENT_ID", DOC_B)
    adapters = {"church-fathers": lambda: [replace(_doc(world, DOC_B), collection="church-fathers")],
                "theologians": lambda: [replace(_doc(world, DOC_A), collection="theologians")],
                "summa": lambda: []}
    runner = world.runner(source_adapters=adapters)
    await runner.stage(StageRequest(release="both", collections=("church-fathers", "theologians")))
    again = await runner.stage(StageRequest(release="both", collections=("church-fathers",)))
    assert again.documents == 1
    assert {r["id"]: r["collection"] for r in await world.fetch(
        "SELECT id::text, collection FROM staging.documents")} == {
        DOC_B: "church-fathers", DOC_A: "theologians"}


async def test_stage_refuses_a_document_moving_from_a_collection_it_does_not_cover(world):
    """A build may not take a live document from a collection the stage leaves alone
    (5.1b.3's Boethius: stage `church-fathers` with `theologians` until it is applied)."""
    moved = {"summa": lambda: [replace(d, collection="summa") for d in world.build],
             "medieval": lambda: []}
    with pytest.raises(StageRefused, match="stage theologians with it|stage medieval with it"):
        await world.runner(source_adapters=moved).stage(
            StageRequest(release="test-release", collections=("summa",)))
    assert not await world.fetch("SELECT 1 FROM corpus_publishes")


async def test_stage_refuses_without_the_live_alias(world):
    from qdrant_client.models import DeleteAlias, DeleteAliasOperation

    await world.qdrant.update_collection_aliases(change_aliases_operations=[
        DeleteAliasOperation(delete_alias=DeleteAlias(alias_name="chunks_live"))])
    with pytest.raises(StageRefused, match="no Qdrant alias 'chunks_live'"):
        await world.runner().stage(STAGE)
    assert not await world.fetch("SELECT 1 FROM corpus_publishes")


async def test_stage_refuses_while_staging_holds_another_publish(world):
    await world.runner().stage(STAGE)
    with pytest.raises(StageRefused, match="staging holds publish 'test-release'"):
        await world.runner().stage(StageRequest(release="other-release",
                                                collections=("medieval",)))


async def test_stage_refuses_staging_made_before_a_generated_column_changed(world):
    """2.2c: the search_vector migration rewrites live only. Staging made earlier keeps
    the old expression, so the stage refuses until 4.0's window recreates it."""
    world.cluster.psql(world.database, (pg_corpus.MIGRATIONS /
                       "0045_search_vector_markers_and_reference.sql").read_text(), single=True)
    conn = await world.connect()
    try:
        problems = await reader_writer.staging_shape_problems(conn)
    finally:
        await conn.close()
    # Before Postgres 17 the column also moves to the end, so later columns differ too.
    [vector] = [p for p in problems if p.startswith("staging.chunks.search_vector is")]
    assert "to_tsvector('english'::regconfig, content)" in vector
    with pytest.raises(ValueError, match="the staging tables differ from live"):
        await world.runner().stage(STAGE)

    world.cluster.psql(world.database,
                       "SELECT drop_corpus_staging(); SELECT create_corpus_staging();")
    await world.runner().stage(STAGE)


async def test_a_refused_stage_leaves_no_ownership_for_a_retry(world):
    """A Qdrant collection of the publish's name that no earlier stage made is refused,
    and the refusal writes no publish row, so a retry is refused too and the
    collection's points are untouched."""
    from qdrant_client.models import Distance, PointStruct, VectorParams

    await world.qdrant.create_collection("chunks-test-release", vectors_config=VectorParams(
        size=1536, distance=Distance.COSINE))
    await world.qdrant.upsert("chunks-test-release", points=[PointStruct(
        id=pid(DOC_A, "a/1"), vector=[0.5] * 1536, payload={"collection": "medieval"})])
    for _ in range(2):
        with pytest.raises(StageRefused, match="belongs to no earlier stage"):
            await world.runner().stage(STAGE)
    assert not await world.fetch("SELECT 1 FROM corpus_publishes")
    assert (await world.qdrant.count("chunks-test-release")).count == 1


async def test_restaging_recopies_untouched_collections(world):
    """A live change that keeps the point count still reaches the publish's copy."""
    await world.runner().stage(STAGE)
    await world.qdrant.set_payload("chunks", payload={"content": "Changed in live."},
                                   points=[pid(DOC_S, "s/1")])
    await world.runner().stage(STAGE)
    [point] = await world.qdrant.retrieve("chunks-test-release", ids=[pid(DOC_S, "s/1")])
    assert point.payload["content"] == "Changed in live."


async def test_concurrent_releases_cannot_both_claim_staging(world):
    """The ownership check and the claim are serialized: a second release waits for
    the first's transaction, then sees it holds staging and refuses."""
    import asyncio

    from publication import begin_publish

    first, second = await world.connect(), await world.connect()
    try:
        tx = first.transaction()
        await tx.start()
        await begin_publish(first, "release-one", ["medieval"], "chunks-release-one")

        async def claim():
            async with second.transaction():
                await begin_publish(second, "release-two", ["summa"], "chunks-release-two")
        waiting = asyncio.ensure_future(claim())
        await asyncio.sleep(0.3)
        assert not waiting.done()          # blocked on the lock, not past the check
        await tx.commit()
        with pytest.raises(StageRefused, match="staging holds publish 'release-one'"):
            await waiting
    finally:
        await first.close()
        await second.close()
    assert [r["id"] for r in await world.fetch("SELECT id FROM corpus_publishes")] == \
        ["release-one"]


async def test_restaging_replaces_the_collection_rows(world):
    await world.runner().stage(STAGE)
    _doc(world, DOC_A).passages[0].content = "Grace perfects nature, revised."
    await world.runner().stage(STAGE)
    [row] = await world.fetch("SELECT content FROM staging.chunks WHERE id = $1::uuid",
                              pid(DOC_A, "a/1"))
    assert row["content"] == "Grace perfects nature, revised."
    assert (await world.qdrant.count("chunks-test-release")).count == 6


# --------------------------------------------------------------------------- report

async def _report(world, tmp_path, recorded=None):
    from release import staged

    conn = await world.connect()
    try:
        async def record(value):
            recorded.append(value)
            await conn.execute("UPDATE corpus_publishes SET report_sha256 = $2 WHERE id = $1",
                               "test-release", value)
        code = await staged.run(conn, world.qdrant, "test-release", str(tmp_path / "report"),
                                record=record if recorded is not None else None,
                                registry=world.registry, run_checks=False)
    finally:
        await conn.close()
    with open(tmp_path / "report" / "publish.json") as f:
        return code, json.load(f)


async def test_report_passes_and_records_the_hashes(world, tmp_path):
    from release import staged

    world.registry.removals.append(_removal(
        id="rm-0903", scope="passage", document_id=DOC_A, anchor="a/4",
        passage_id=pid(DOC_A, "a/4"), reason="debris", tombstone="Removed."))
    _doc(world, DOC_A).passages.pop()
    await world.runner().stage(STAGE)
    recorded = []
    code, data = await _report(world, tmp_path, recorded)
    assert code == 0, data["failures"]
    assert (data["ids"]["kept"], data["ids"]["retired"], data["ids"]["redirected"]) == (4, 1, 0)
    assert data["points"]["mismatches"] == [] and data["points"]["hash_failures"] == []
    assert data["user_impact"]["retired"]["bookmarks"] == 0
    [stored] = recorded
    conn = await world.connect()
    try:
        assert stored.split(":")[1] == await staged.staged_content_sha256(conn)
    finally:
        await conn.close()
    with open(tmp_path / "report" / "report.md") as f:
        assert "## Publish checks (2.2w)" in f.read()


async def test_every_live_id_is_kept_or_explained(world, tmp_path):
    """A staged corpus that drops a live ID with no tombstone or redirect fails the
    report, and so does one that re-keys a known unit."""
    await world.runner().stage(STAGE)
    conn = await world.connect()
    await conn.execute("UPDATE staging.chunks SET id = gen_random_uuid() WHERE id = $1::uuid",
                       pid(DOC_A, "a/2"))
    await conn.close()
    code, data = await _report(world, tmp_path, [])
    assert code == 1
    assert data["ids"]["unexplained"] == [pid(DOC_A, "a/2")]
    assert len(data["ids"]["new"]) == 1
    # A failing report records nothing, so apply cannot run on it.
    [row] = await world.fetch("SELECT report_sha256 FROM corpus_publishes")
    assert row["report_sha256"] is None


async def test_report_checks_payload_facts_and_input_hashes(world, tmp_path):
    await world.runner().stage(STAGE)
    await world.qdrant.set_payload("chunks-test-release", payload={"searchable": False,
                                                                   "embed_sha256": "x"},
                                   points=[pid(DOC_A, "a/1")])
    code, data = await _report(world, tmp_path)
    assert code == 1
    assert data["points"]["hash_failures"] == [pid(DOC_A, "a/1")]
    assert any("searchable" in m for m in data["points"]["mismatches"])


async def test_report_lists_the_document_facts_diff(world, tmp_path):
    _doc(world, DOC_A).genre = "treatise"
    _doc(world, DOC_A).form = "bull"
    _doc(world, DOC_B).author = "Bernard"
    await world.runner().stage(STAGE)
    _, data = await _report(world, tmp_path)
    diffs = {d["id"]: d["changed"] for d in data["facts_diff"]}
    assert diffs[DOC_A]["genre"] == {"live": None, "staged": "treatise"}
    assert diffs[DOC_A]["form"] == {"live": None, "staged": "bull"}
    # 2.3: the report's "Document facts" section counts each field per collection and
    # lists the author changes.
    report = (tmp_path / "report" / "report.md").read_text()
    section = report.split("## Document facts (2.3)")[1]
    assert "| Field | medieval |" in section
    assert "| genre | 1 |" in section and "| reader_access | 2 |" in section
    assert "| form | 1 |" in section
    assert "Author changes: 1." in section
    assert f"`{DOC_B}`: 'Bernard of Clairvaux' → 'Bernard'" in section
    del diffs[DOC_B]["author"]
    # Neither test document is in the rights inventory, so staging makes both excerpt-only
    # (D12) and the diff says so.
    assert diffs[DOC_B] == {"reader_access": {"live": "full", "staged": "excerpt"}}


async def test_report_lists_the_works_diff(world, tmp_path):
    """3.2: a work inside a document (D6) that is new or whose labels change is in the
    report, so a work-only label change is visible."""
    from model import Work
    doc = _doc(world, DOC_A)
    doc.works = [Work(work_key="w1", ordinal=1, title="A work", author="Anonymous",
                      certainty="anonymous")]
    for p in doc.passages:
        p.work_key = "w1"
    await world.runner().stage(STAGE)
    _, data = await _report(world, tmp_path)
    assert [(d["document_id"], d["work_key"], d["new_work"]) for d in data["works_diff"]] \
        == [(DOC_A, "w1", True)]
    section = (tmp_path / "report" / "report.md").read_text() \
        .split("## Works inside documents (3.2)")[1]
    assert "| (new works) | 1 |" in section
    # A new work's labels are listed, so a reviewer sees them before the apply.
    assert f"`{DOC_A}` w1: new: title 'A work'; author 'Anonymous'; certainty 'anonymous'" \
        in section
    assert data["works_diff"][0]["changed"]["author"] == {"live": None, "staged": "Anonymous"}


def test_works_md_lists_each_changed_label():
    from release import staged

    diff = [{"document_id": "d", "work_key": "w", "collection": "summa", "new_work": False,
             "changed": {"attribution_note": {"live": None, "staged": "Compiled after"},
                         "author": {"live": "Y", "staged": "Pseudo-Y"}}}]
    md = "\n".join(staged.works_md(diff))
    assert "| author | 1 |" in md and "| attribution_note | 1 |" in md
    assert "- summa `d` w: attribution_note None → 'Compiled after'; author 'Y' → 'Pseudo-Y'" \
        in md
    assert "No work differs from live." in "\n".join(staged.works_md([]))


def test_report_dedup_collision_rate():
    from release import staged

    v = [1.0, 0.0, 0.0]
    vectors = {"p1": v, "p2": [0.99, 0.1, 0.0], "p3": [0.0, 1.0, 0.0], "p4": [0.0, 0.0, 1.0]}
    hits, pairs = staged.collision_rate(vectors, ["p1", "p2", "p3", "p4"])
    # Pairs within two positions: (1,2) (2,3) (3,4) (1,3) (2,4); only (1,2) exceeds 0.9.
    assert (hits, pairs) == (1, 5)
    assert staged.collision_rate({"p1": v}, ["p1"]) == (0, 0)


# --------------------------------------------------------------------------- CLI

def _remote(monkeypatch):
    import asyncpg
    import publish_lock
    import writers.qdrant

    monkeypatch.setattr(publish_lock, "settings_targets", lambda: publish_lock.WriteTargets(
        "postgresql://u:p@db.example.supabase.co/postgres", "https://q.example.qdrant.io"))

    def no_network(*args, **kwargs):
        raise AssertionError("the lock must refuse before any network call")
    monkeypatch.setattr(asyncpg, "connect", no_network)
    monkeypatch.setattr(writers.qdrant, "get_client", no_network)


def test_stage_asks_the_lock_for_its_step(tmp_path, monkeypatch, capsys):
    import publish

    _remote(monkeypatch)
    lock = tmp_path / "PUBLISH_LOCK.json"
    lock.write_text(json.dumps({"reason": "test", "approved_applies": [
        {"collection": "theologians", "release": "test-release", "steps": ["apply"]}]}))
    with pytest.raises(SystemExit) as raised:
        publish.main(["stage", "--collection", "theologians", "--release", "test-release"],
                     lock_path=lock)
    assert raised.value.code == 2
    assert "step 'stage'" in capsys.readouterr().err


async def test_discard_asks_for_stage_and_drops_staging(world, monkeypatch, capsys):
    import publish
    import publish_lock

    await world.runner().stage(STAGE)

    async def connect():
        return await world.connect()
    monkeypatch.setattr(publish, "_connect", connect)
    asked = []

    def guard(action, collection, release, step, lock=None, targets=None):
        asked.append((collection, release, step))
    monkeypatch.setattr(publish_lock, "assert_live_write_allowed", guard)
    args = publish.build_parser().parse_args(["discard", "--release", "test-release"])
    assert await publish.discard(args) == 0
    assert asked == [("medieval", "test-release", "stage")]
    [row] = await world.fetch("SELECT to_regclass('staging.chunks') IS NULL AS gone, "
                              "(SELECT discarded_at IS NOT NULL FROM corpus_publishes) AS d")
    assert row == {"gone": True, "d": True}
    assert "chunks-test-release" in capsys.readouterr().out
    # A discarded publish no longer holds staging: the next stage recreates it.
    await world.runner().stage(StageRequest(release="next-release", collections=("medieval",)))
    assert await world.fetch("SELECT 1 FROM staging.chunks LIMIT 1")


async def test_a_delayed_discard_never_drops_another_release(world, monkeypatch):
    """Discard validates its release under the lock. Here, between its first read and
    its transaction, the release is discarded and another one stages; the delayed
    discard refuses, and the other release's staging survives."""
    import publish
    import publish_lock

    await world.runner().stage(STAGE)

    async def connect():
        return await world.connect()
    monkeypatch.setattr(publish, "_connect", connect)
    monkeypatch.setattr(publish_lock, "assert_live_write_allowed", lambda *a, **k: None)
    read = publish._publish_row
    calls = []

    async def read_then_interleave(conn, release):
        row = await read(conn, release)
        calls.append(release)
        if len(calls) == 1:            # the stale, unlocked read
            other = await world.connect()
            try:
                await other.execute("SELECT public.drop_corpus_staging()")
                await other.execute("UPDATE corpus_publishes SET discarded_at = now() "
                                    "WHERE id = 'test-release'")
            finally:
                await other.close()
            await world.runner().stage(StageRequest(release="next-release",
                                                    collections=("medieval",)))
        return row
    monkeypatch.setattr(publish, "_publish_row", read_then_interleave)
    args = publish.build_parser().parse_args(["discard", "--release", "test-release"])
    with pytest.raises(ValueError, match="was discarded"):
        await publish.discard(args)
    assert await world.fetch("SELECT 1 FROM staging.chunks LIMIT 1")


def test_release_names_follow_the_publish_id_rule(capsys):
    import publish

    with pytest.raises(SystemExit):
        publish.build_parser().parse_args(["status", "--release", "Bad_Name"])
    args = publish.build_parser().parse_args(["stage", "--collection", "all",
                                              "--release", "2026-11-republish"])
    assert args.collection == ["all"]


def test_stage_takes_collections_a_document_moves_between_in_one_call():
    """5.1b.3: Boethius moves from `theologians` to `church-fathers`, so both stage at once."""
    import publish

    args = publish.build_parser().parse_args([
        "stage", "--collection", "church-fathers", "--collection", "theologians",
        "--release", "collection-keys"])
    assert args.collection == ["church-fathers", "theologians"]
