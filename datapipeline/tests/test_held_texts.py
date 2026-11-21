"""Held texts in their place (corpus-cleanup 4.3, issue #394).

`registry/held_texts.json` lists each text a document holds back (a council's gap text,
a run of paragraphs awaiting permission) with its place and heading. The registry check
ties it to the removal registry; the build writes it into `metadata.held_texts`; the
stage carries it into staging, and the release report lists it, with no passage, point
or vector changed. Acceptance checks: docs/corpus-cleanup/P4-P5-republish-expand.md, 4.3.
"""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

import registry
from model import Document, Passage
from publication import StageRequest
from scripts import held_texts as script
from tests import pg_corpus
from tests.stage_world import DOC_A, World, pid

DOC = "dddddddd-0000-0000-0000-000000000001"
OTHER = "dddddddd-0000-0000-0000-000000000002"


def _work(document_id: str, collection: str = "councils") -> dict:
    return registry.work_entry(collection=collection, source_key=f"{collection}/{document_id}",
                               document_id=document_id, title=document_id[-1],
                               author=None, frozen_on="2026-10-30")


def _row(anchor: str, document_id: str = DOC, status: str = "retired") -> dict:
    return {"passage_id": registry.identity.passage_id(document_id, anchor),
            "document_id": document_id, "anchor": anchor, "live_anchor": anchor,
            "status": status, "frozen_on": "2026-10-30", "work_key": None}


def _removal(rid: str, anchor: str, document_id: str = DOC, collection: str = "councils",
             reason: str = "translation-in-preparation", **extra) -> dict:
    return {"id": rid, "scope": "passage", "collection": collection,
            "document_id": document_id, "anchor": anchor,
            "passage_id": registry.identity.passage_id(document_id, anchor),
            "reason": reason, "tombstone": "Not on TheoCorpus at present.",
            "detail": "Session 2, a decree (gap G9)", "church_act": None,
            "added_by": "test", "added_on": "2026-11-01", **extra}


def _held(hid: str, removal_ids: list[str], after: str | None = None, **extra) -> dict:
    return {"id": hid, "document_id": DOC, "label": "Session 2", "heading": "A decree",
            "after_anchor": after, "removal_ids": removal_ids, "url": None,
            "added_by": "4.3", "added_on": "2026-11-21", **extra}


def _registry(removals: list[dict], held: list[dict]) -> registry.WorkRegistry:
    anchors = sorted({(e["document_id"], e["anchor"]) for e in removals})
    return registry.WorkRegistry(
        works=[_work(DOC), _work(OTHER)],
        passages=[_row(a, d) for d, a in anchors] + [_row("s1/1", status="active"),
                                                      _row("s3/1", status="active")],
        removals=sorted(removals, key=lambda e: (e["collection"], e["document_id"],
                                                 e["anchor"])),
        held_texts=held)


def _problems(reg: registry.WorkRegistry) -> list[str]:
    return [p for p in registry.validate(reg) if "held" in p]


def _document() -> Document:
    """A council as the build emits it: sessions 1 and 3 published, session 2 held."""
    return Document(id=DOC, collection="councils", title="Council", author=None, passages=[
        Passage(content="one", reference="1", anchor="s1/1", chapter_key="s1",
                chapter_label="Session 1", position=0),
        Passage(content="three", reference="3", anchor="s3/1", chapter_key="s3",
                chapter_label="Session 3", position=1)])


# --------------------------------------------------------------------------- the registry

def test_the_shipped_list_covers_every_held_removal_once():
    shipped = registry.current()
    assert _problems(shipped) == []
    owned = [r for h in shipped.held_texts for r in h["removal_ids"]]
    assert len(owned) == len(set(owned))
    assert set(owned) == {e["id"] for e in shipped.removals if registry.is_held_removal(e)}


def test_the_shipped_counts():
    """Constance's 17 held texts and the councils' 68; 23 encyclical runs; Exsurge
    Domine's opening and closing (measured against the build, 21 Nov 2026)."""
    shipped = registry.current()
    titles = {w["document_id"]: (w["collection"], w["title"]) for w in shipped.works}
    by_collection: dict[str, int] = {}
    by_title: dict[str, int] = {}
    for h in shipped.held_texts:
        collection, title = titles[h["document_id"]]
        by_collection[collection] = by_collection.get(collection, 0) + 1
        by_title[title] = by_title.get(title, 0) + 1
    assert by_collection == {"councils": 68, "encyclicals": 23, "papal-documents": 2}
    assert by_title["Council of Constance"] == 17
    assert by_title["Council of Basel-Ferrara-Florence"] == 30


def test_constance_lists_the_sentences_of_sessions_8_15_and_21():
    shipped = registry.current()
    constance = [h for h in shipped.held_texts
                 if shipped.entry_by_document[h["document_id"]]["title"] == "Council of Constance"]
    sentences = {h["label"] for h in constance if h["heading"].startswith("Sentence")}
    assert {"Session 8", "Session 15", "Session 21"} <= sentences
    assert [int(h["label"].split()[1]) for h in constance] == sorted(
        int(h["label"].split()[1]) for h in constance)


def test_a_straddling_florence_passage_counts_once():
    """rm-0741 holds the end of session 9 and all of session 10: session 9 owns it, and
    session 10, which has no passage of its own, shares it."""
    shipped = registry.current()
    owners = [h for h in shipped.held_texts if "rm-0741" in h["removal_ids"]]
    sharers = [h for h in shipped.held_texts if "rm-0741" in h.get("shared_removal_ids", [])]
    assert [h["label"] for h in owners] == ["Florence, Session 9"]
    assert [h["label"] for h in sharers] == ["Florence, Session 10"]


def test_a_valid_list_passes():
    reg = _registry([_removal("rm-1", "s2/1"), _removal("rm-2", "s2/2")],
                    [_held("ht-0001", ["rm-1", "rm-2"], after="s1/1")])
    assert _problems(reg) == []


def test_a_held_removal_in_no_entry_fails():
    reg = _registry([_removal("rm-1", "s2/1"), _removal("rm-2", "s2/2")],
                    [_held("ht-0001", ["rm-1"])])
    assert any("rm-2" in p and "no entry" in p for p in _problems(reg))


def test_a_piece_the_build_cut_needs_an_entry_like_any_other():
    """1.10c's cut pieces were never published, but their text is part of the held text."""
    cut = _removal("rm-2", "s2/1/from-e9",
                   detail="Session 2, a decree (gap G9), a piece the 1.10c build cut")
    reg = _registry([_removal("rm-1", "s2/1"), cut], [_held("ht-0001", ["rm-1"])])
    assert any("rm-2" in p for p in _problems(reg))


def test_a_removal_in_two_entries_fails():
    reg = _registry([_removal("rm-1", "s2/1")],
                    [_held("ht-0001", ["rm-1"]), _held("ht-0002", ["rm-1"])])
    assert any("already belongs to ht-0001" in p for p in _problems(reg))


def test_a_closed_removal_fails():
    """A translation found closes the removal: its held entry must go in the same PR."""
    reg = _registry([_removal("rm-1", "s2/1", closed_by="1.2x", closed_on="2026-12-01")],
                    [_held("ht-0001", ["rm-1"])])
    assert any("closed or not a held" in p for p in _problems(reg))


@pytest.mark.parametrize("removal", [
    _removal("rm-1", "s2/1", reason="rule-g-editorial"),
    _removal("rm-1", "s2/1", reason="debris"),
    # Canon law's amended canons and the Fathers' Latin chapters are out of scope.
    _removal("rm-1", "s2/1", collection="church-fathers"),
])
def test_an_out_of_scope_removal_fails(removal):
    reg = _registry([removal], [_held("ht-0001", ["rm-1"])])
    assert any("closed or not a held" in p for p in _problems(reg))


def test_an_awaiting_permission_passage_is_held_in_any_collection():
    reg = _registry([_removal("rm-1", "s2/1", collection="encyclicals",
                              reason="awaiting-permission")],
                    [_held("ht-0001", ["rm-1"])])
    assert _problems(reg) == []


def test_another_documents_removal_fails():
    reg = _registry([_removal("rm-1", "s2/1"), _removal("rm-2", "x/1", document_id=OTHER)],
                    [_held("ht-0001", ["rm-1", "rm-2"])])
    problems = _problems(reg)
    assert any("rm-2 is another document's" in p for p in problems)


def test_a_shared_removal_must_belong_to_another_entry():
    reg = _registry([_removal("rm-1", "s2/1")],
                    [_held("ht-0001", [], shared_removal_ids=["rm-1"])])
    assert any("belongs to no other entry" in p for p in _problems(reg))
    reg.held_texts.insert(0, _held("ht-0002", ["rm-1"]))
    assert _problems(reg) == []


@pytest.mark.parametrize("change", [
    {"id": "held-1"}, {"label": ""}, {"heading": " "}, {"heading": "x" * 201},
    {"url": "papalencyclicals.net"}, {"added_on": "21 Nov"}, {"removal_ids": []},
])
def test_malformed_entries_fail(change):
    reg = _registry([_removal("rm-1", "s2/1"), _removal("rm-2", "s2/2")],
                    [_held("ht-0001", ["rm-1"]), _held("ht-0002", ["rm-2"])])
    reg.held_texts[1].update(change)
    assert _problems(reg)


# --------------------------------------------------------------------------- the build

def test_the_build_writes_the_list_into_metadata():
    reg = _registry([_removal("rm-1", "s2/1")],
                    [_held("ht-0001", ["rm-1"], after="s1/1"),
                     _held("ht-0002", ["rm-1"], after=None, label="Opening")])
    with pytest.raises(ValueError, match="before the entry above it"):
        registry.attach_held_texts(_document(), reg)
    reg.held_texts.reverse()
    doc = registry.attach_held_texts(_document(), reg)
    assert doc.metadata["held_texts"] == [
        {"key": "ht-0002", "label": "Opening", "heading": "A decree", "after_anchor": None,
         "after_chapter_key": None, "url": None},
        {"key": "ht-0001", "label": "Session 2", "heading": "A decree", "after_anchor": "s1/1",
         "after_chapter_key": "s1", "url": None}]


def test_a_document_without_entries_gets_no_key():
    doc = _document()
    doc.metadata = {"url": "https://example.org"}
    out = registry.attach_held_texts(doc, _registry([], []))
    assert out.metadata == {"url": "https://example.org"}


def test_an_after_anchor_the_build_does_not_emit_fails():
    reg = _registry([_removal("rm-1", "s2/1")], [_held("ht-0001", ["rm-1"], after="s2/9")])
    with pytest.raises(ValueError, match="does not emit"):
        registry.attach_held_texts(_document(), reg)


def test_the_build_refuses_a_stranded_list():
    """build() runs the check, dry runs included."""
    from publication import build

    reg = _registry([_removal("rm-1", "s2/1")], [_held("ht-0001", ["rm-1"], after="s2/9")])
    with pytest.raises(ValueError, match="does not emit"):
        build("councils", source_adapters={"councils": lambda: [_document()]}, registry=reg)


def test_the_build_refuses_a_held_removal_no_entry_names():
    """The coverage check runs in the build too, dry runs included; the draft generator
    alone turns it off."""
    from publication import build

    reg = _registry([_removal("rm-1", "s2/1"), _removal("rm-2", "s2/2")],
                    [_held("ht-0001", ["rm-1"], after="s1/1")])
    adapters = {"councils": lambda: [_document()]}
    with pytest.raises(ValueError, match="rm-2"):
        build("councils", source_adapters=adapters, registry=reg)
    assert build("councils", source_adapters=adapters, registry=reg, held_coverage=False)


def test_the_shipped_list_fits_the_build():
    """Every entry follows a passage the build emits, in order (the build's own check)."""
    from publication import build

    held = {h["document_id"] for h in registry.current().held_texts}
    seen = set()
    for collection in ("councils", "encyclicals", "papal-documents"):
        for d in build(collection):
            if d.id in held:
                seen.add(d.id)
                assert len(d.metadata["held_texts"]) == sum(
                    1 for h in registry.current().held_texts if h["document_id"] == d.id)
    assert seen == held


# --------------------------------------------------------------------------- the draft

def test_the_draft_groups_council_texts_and_places_them_by_session():
    removals = [_removal("rm-1", "s2/1"), _removal("rm-2", "s2/2"),
                _removal("rm-3", "s4/1", detail="Session 4, a sentence; Session 5, a bull")]
    reg = _registry(removals, [])
    doc = _document()
    doc.passages.append(Passage(content="five", reference="5", anchor="s5/1",
                                chapter_key="s5", chapter_label="Session 5", position=2))
    out = script.draft(reg, [doc], "2026-11-21")
    assert [(e["label"], e["heading"], e["after_anchor"], e["removal_ids"],
             e.get("shared_removal_ids")) for e in out] == [
        ("Session 2", "A decree", "s1/1", ["rm-1", "rm-2"], None),
        ("Session 4", "A sentence", "s3/1", ["rm-3"], None),
        ("Session 5", "A bull", "s3/1", [], ["rm-3"]),
    ]
    assert [e["id"] for e in out] == ["ht-0001", "ht-0002", "ht-0003"]


def test_the_draft_never_rewrites_an_entry_and_continues_the_ids():
    reg = _registry([_removal("rm-1", "s2/1"), _removal("rm-2", "s2/2")],
                    [_held("ht-0007", ["rm-1"])])
    before = deepcopy(reg.held_texts)
    out = script.draft(reg, [_document()], "2026-11-21")
    assert reg.held_texts == before
    assert [(e["id"], e["removal_ids"]) for e in out] == [("ht-0008", ["rm-2"])]


def test_the_draft_makes_runs_of_papal_paragraphs():
    def para(rid, n):
        detail = "The address is not in the public-domain printing" if n == 0 else \
            f"Paragraph {n} is not in the public-domain printing"
        anchor = "e/preamble" if n == 0 else f"e/{n}"
        return _removal(rid, anchor, collection="encyclicals", reason="awaiting-permission",
                        detail=detail)
    removals = [para("rm-0", 0), para("rm-1", 1), para("rm-2", 2), para("rm-5", 5)]
    doc = Document(id=DOC, collection="encyclicals", title="E", author=None, passages=[
        Passage(content=str(n), reference=str(n), anchor=f"e/{n}", chapter_key="b",
                chapter_label="E", position=i) for i, n in enumerate((3, 4, 6))])
    out = script.draft(_registry(removals, []), [doc], "2026-11-21")
    assert [(e["label"], e["after_anchor"]) for e in out] == [
        ("The address and paragraphs 1–2", None), ("Paragraph 5", "e/4")]


# --------------------------------------------------------------------------- the stage

@pytest.fixture(scope="module")
def cluster():
    cluster, stop = pg_corpus.start()
    yield cluster
    stop()


@pytest.fixture()
async def world(cluster, tmp_path):
    w = World(cluster, cluster.new_database(), tmp_path)
    await w.seed()
    # A held passage no publish carried (like 1.10c's cut pieces): the list is the only
    # change a stage of the unchanged build makes.
    w.registry.removals.append(
        {"id": "rm-9001", "scope": "passage", "collection": "medieval", "document_id": DOC_A,
         "anchor": "a/held", "passage_id": pid(DOC_A, "a/held"), "reason": "awaiting-permission",
         "tombstone": "Held until we have permission.", "detail": "Paragraph 3 is held",
         "church_act": None, "added_by": "test", "added_on": "2026-11-21"})
    w.registry.held_texts = [
        {"id": "ht-0001", "document_id": DOC_A, "label": "Chapter 1",
         "heading": "A held letter", "after_anchor": "a/2", "removal_ids": ["rm-9001"],
         "url": None, "added_by": "4.3", "added_on": "2026-11-21"}]
    return w


STAGE = StageRequest(release="test-release", collections=("medieval",))


async def test_stage_writes_held_texts_into_metadata(world):
    await world.runner().stage(STAGE)
    rows = {r["id"]: r["metadata"] for r in await world.fetch(
        "SELECT id::text AS id, metadata FROM staging.documents")}
    assert json.loads(rows[DOC_A])["held_texts"] == [
        {"key": "ht-0001", "label": "Chapter 1", "heading": "A held letter",
         "after_anchor": "a/2", "after_chapter_key": "c1", "url": None}]
    assert rows[next(d for d in rows if d != DOC_A)] is None
    # No document metadata reaches a point.
    points, _ = await world.qdrant.scroll("chunks-test-release", limit=20)
    assert all("held_texts" not in json.dumps(p.payload) for p in points)


async def test_held_texts_publish_changes_no_passage_or_point(world, tmp_path):
    """A stage whose only change is the list: no ID kept, retired, redirected or new
    beyond today's, no point or embedding input changed, and the report lists it."""
    from tests.test_stage_apply import _report

    async def inputs() -> dict:
        points, _ = await world.qdrant.scroll("chunks-test-release", limit=20)
        return {p.id: p.payload.get("embed_sha256") for p in points}

    from qdrant_schema import create_chunks_collection
    from writers.apply import point_alias
    from writers.qdrant import copy_points

    held, world.registry.held_texts = world.registry.held_texts, []
    removal = world.registry.removals.pop()
    await world.runner().stage(STAGE)
    without, calls = await inputs(), len(world.embedded)
    # Live is now that stage's corpus, as after its apply and switch.
    await create_chunks_collection(world.qdrant, "chunks-before")
    for collection in ("medieval", "summa"):
        await copy_points(world.qdrant, "chunks-test-release", "chunks-before", collection)
    await point_alias(world.qdrant, "chunks_live", "chunks-before")
    world.registry.held_texts = held
    world.registry.removals.append(removal)
    await world.runner().stage(STAGE)
    assert await inputs() == without       # every embedding input unchanged
    assert len(world.embedded) == calls    # so every vector is reused: no call
    code, data = await _report(world, tmp_path)
    assert code == 0, data["failures"]
    assert (data["ids"]["kept"], data["ids"]["retired"], data["ids"]["redirected"],
            data["ids"]["new"]) == (5, 0, 0, [])
    assert data["points"]["mismatches"] == [] and data["points"]["hash_failures"] == []
    assert data["live_points"]["medieval"] == {"compared": 5, "payload_changed": 0,
                                               "embed_sha256_changed": 0, "fields": []}
    [diff] = data["held_texts_diff"]
    assert (diff["id"], [h["key"] for h in diff["added"]], diff["removed"],
            diff["changed"]) == (DOC_A, ["ht-0001"], [], [])
    assert all(d["changed"].keys() <= {"reader_access"} for d in data["facts_diff"])
    section = (tmp_path / "report" / "report.md").read_text().split("## Held texts (4.3)")[1]
    assert "+ ht-0001 Chapter 1 · A held letter (after a/2)" in section
    # The point a held text sits beside is untouched.
    [point] = await world.qdrant.retrieve("chunks-test-release", [pid(DOC_A, "a/2")],
                                          with_payload=True)
    assert "held_texts" not in point.payload
