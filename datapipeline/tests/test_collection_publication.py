"""The build and preparation steps a stage runs before it opens any store (2.2w).

The stage itself runs against a local PostgreSQL and an in-memory Qdrant in
test_stage_apply.py.
"""
from pathlib import Path
import sys

import pytest

import registry
from identity import passage_id
from model import Document, Passage, Work
from publication import (SOURCE_ADAPTERS, WORK_ORDINAL_LIMIT, StageRequest, StageRunner,
                         build, prepare, validate_documents)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))
from services.api.app.rag.constants import VALID_COLLECTIONS

DOC = "11111111-1111-1111-1111-111111111111"


def _document(*anchors: str) -> Document:
    return Document(
        id=DOC,
        collection="medieval",
        title="On Loving God",
        author="Bernard of Clairvaux",
        passages=[
            Passage(
                content=f"Passage {anchor}",
                reference=anchor,
                anchor=anchor,
                chapter_key="chapter-1",
                chapter_label="Chapter 1",
                position=position,
            )
            for position, anchor in enumerate(anchors)
        ],
    )


def _registry(passages=(), removals=()) -> registry.WorkRegistry:
    work = registry.work_entry(collection="medieval", source_key="medieval/x", document_id=DOC,
                               title="On Loving God", author=None, frozen_on="2026-10-30")
    return registry.WorkRegistry(works=[work], passages=list(passages),
                                 removals=list(removals))


def _row(anchor, pid, **extra):
    return {"passage_id": pid, "document_id": DOC, "anchor": anchor, "live_anchor": anchor,
            "status": "active", "frozen_on": "2026-10-30", "work_key": None, **extra}


def test_source_adapter_registry_exactly_matches_production_collections():
    assert set(SOURCE_ADAPTERS) == VALID_COLLECTIONS == {
        "apostolic-exhortations",
        "bible",
        "canon-law",
        "catechism",
        "church-fathers",
        "councils",
        "encyclicals",
        "medieval",
        "papal-documents",
        "summa",
    }
    assert all(callable(adapter) for adapter in SOURCE_ADAPTERS.values())


def test_prepared_ids_come_from_the_registry_and_new_units_from_identity():
    """D1: a unit the registry holds keeps its frozen ID whatever its anchor computes
    to; only a unit the registry does not know gets `identity.passage_id`."""
    frozen = "22222222-2222-2222-2222-222222222222"
    reg = _registry(passages=[_row("a/1", frozen)])
    [document], new = prepare([_document("a/1", "a/2")], reg)
    assert [p.id for p in document.passages] == [frozen, passage_id(DOC, "a/2")]
    assert new == [passage_id(DOC, "a/2")]


def test_registry_override_beats_adapter_searchable():
    reg = _registry(passages=[_row("a/1", passage_id(DOC, "a/1"), searchable=False,
                                   note="Translated from another recension of this canon.")])
    [document], _ = prepare([_document("a/1", "a/2")], reg)
    assert document.passages[0].searchable is False
    # The registry's note, stored with its kind (4.4).
    assert document.passages[0].note == "Translated from another recension of this canon."
    assert document.passages[0].metadata["note_kind"] == "wording"


def test_history_passage_must_name_a_passage_of_its_document():
    document = _document("c/1", "c/1/history-1983")
    document.passages[1].superseded_by_anchor = "c/9"
    with pytest.raises(ValueError, match="not a passage of the same document"):
        prepare([document], _registry())


def test_the_build_drops_what_the_removal_registry_retires():
    removal = {"id": "rm-9", "scope": "passage", "collection": "medieval", "document_id": DOC,
               "anchor": "a/2", "passage_id": passage_id(DOC, "a/2"), "reason": "debris",
               "tombstone": "Removed.", "church_act": None}
    reg = _registry(passages=[_row("a/2", passage_id(DOC, "a/2"))], removals=[removal])
    [document] = build("medieval",
                       source_adapters={"medieval": lambda: [_document("a/1", "a/2", "a/3")]},
                       registry=reg)
    # An interior removal: the kept passages are renumbered, so the build's position
    # check (health H3) passes.
    assert [(p.anchor, p.position) for p in document.passages] == [("a/1", 0), ("a/3", 1)]
    whole = {**removal, "id": "rm-10", "scope": "document", "anchor": None, "passage_id": None}
    assert build("medieval", source_adapters={"medieval": lambda: [_document("a/1")]},
                 registry=_registry(removals=[whole])) == []


def test_a_work_ordinal_at_the_apply_offset_refuses_the_build():
    """The apply parks live works at ordinal + 1,000,000, so a built ordinal stays below."""
    document = _document("a/1")
    document.works = [Work(work_key="w", ordinal=WORK_ORDINAL_LIMIT - 1, title="W")]
    validate_documents("medieval", [document])
    document.works = [Work(work_key="w", ordinal=WORK_ORDINAL_LIMIT, title="W")]
    with pytest.raises(ValueError, match="work ordinal outside 1 to 999999"):
        validate_documents("medieval", [document])


async def test_write_guard_runs_before_adapters_and_store_acquisition():
    events = []

    def guard(collection, release):
        events.append(("guard", collection, release))
        raise ValueError("locked")

    def adapter():
        events.append("adapter")
        return []

    async def connect():
        events.append("connect")

    runner = StageRunner(connect=connect, qdrant=lambda: events.append("qdrant"),
                         cache=lambda: None, write_guard=guard,
                         source_adapters={"medieval": adapter})
    with pytest.raises(ValueError, match="locked"):
        await runner.stage(StageRequest(release="r-1", collections=("medieval",)))
    assert events == [("guard", "medieval", "r-1")]
