"""Labels, certainty and notes for works that stay (corpus-cleanup 3.2). These read only
tracked files; tests/source_checks/test_document_facts_sources.py checks works.json and
the passage registry against a build."""
from __future__ import annotations

import os
import sys

import attributions
import document_facts
import registry
from model import Document, Passage, Work
from registry.genres import ALL_GENRES

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import document_facts_registry as facts_script  # noqa: E402

REG = registry.load_registry()
BY_WORK = {w["work_id"]: w for w in REG.works}
MARTYRDOM_OF_IGNATIUS = "church-fathers/apostolic-fathers/v.xxv"
APOSTOLIC_CANONS = ("church-fathers/third-fourth-century/ix.ix", "ix.ix.vi")


def _labels():
    """(name, labels, author key) for every document and work label."""
    out = [(k, v, "credited_as") for k, v in attributions.DOCUMENTS.items()]
    out += [(f"{k[0]}#{k[1]}", v, "author") for k, v in attributions.WORKS.items()]
    return out


# --------------------------------------------------------------------------- the tables

def test_every_label_names_a_registered_document_and_work():
    assert sorted(set(attributions.DOCUMENTS) - set(BY_WORK)) == []
    for work_id, key in list(attributions.WORKS) + list(document_facts.FATHERS_WORK_DATES) \
            + list(document_facts.FATHERS_WORK_GENRES):
        assert work_id in BY_WORK, work_id
        assert key in {x["work_key"] for x in BY_WORK[work_id]["works"]}, (work_id, key)
    for work_id, key in attributions.PASSAGE_NOTES:
        assert work_id in BY_WORK, work_id
    assert sorted(set(document_facts.FATHERS_DATES) - set(BY_WORK)) == []
    assert sorted(set(document_facts.FATHERS_GENRES) - set(BY_WORK)) == []


def test_certainty_values_and_pseudonyms():
    for name, labels, author in _labels():
        assert labels.get("certainty") in (None,) + registry.CERTAINTIES, name
        if (labels.get(author) or "").startswith("Pseudo-"):
            assert labels["certainty"] == "pseudonymous", name
        if labels.get(author) == "Anonymous":
            assert labels["certainty"] == "anonymous", name


def test_every_attribution_label_has_a_certainty():
    """The spec's table: every relabelled or noted work carries a certainty, except the
    Martyrdom of Ignatius, which keeps its author (D10). Fragment collections keep theirs
    unchanged and only gain a note on where they were preserved."""
    for name, labels, author in _labels():
        if name == MARTYRDOM_OF_IGNATIUS:
            assert labels.get("certainty") is None and not labels.get(author)
            continue
        if labels.get(author) or labels.get("attribution_note"):
            assert labels.get("certainty"), name


def test_the_apostolic_canons_are_attributed_not_anonymous():
    labels = attributions.WORKS[APOSTOLIC_CANONS]
    assert labels["author"] == "Attributed to the Apostles"
    assert labels["certainty"] == "pseudonymous"
    assert not labels["attribution_note"].startswith("Attributed")


def test_every_label_says_what_it_rests_on():
    assert [name for name, labels, _ in _labels() if not labels.get("basis")] == []


def test_the_apostle_lists_rule_c_removed_carry_no_labels():
    appendix = "church-fathers/third-century-2/iii.v"
    assert not {(appendix, "iii.v.ii"), (appendix, "iii.v.iii")} & set(attributions.WORKS)
    entries = {e["id"]: e for e in REG.removals if e.get("added_by") == "3.2"}
    assert sorted(entries) == ["rm-7001", "rm-7002", "rm-7003"]
    assert {e["reason"] for e in entries.values()} == {"rule-c"}
    for e in entries.values():
        assert e["scope"] == "passage" and not e.get("closed_by")
    rows = {r["passage_id"]: r for r in REG.passages}
    assert all(rows[e["passage_id"]]["status"] == "retired" for e in entries.values())


def test_dates_and_genres_are_well_formed():
    for key, (year, display, where) in list(document_facts.FATHERS_DATES.items()) \
            + list(document_facts.FATHERS_WORK_DATES.items()):
        assert year is None or type(year) is int, key
        assert display and where, key
        assert year is None or str(year) in display, key
    genres = list(document_facts.FATHERS_GENRES.values()) \
        + list(document_facts.FATHERS_WORK_GENRES.values())
    assert set(genres) <= set(ALL_GENRES)


# --------------------------------------------------------------------------- the registry

def test_works_json_carries_the_labels():
    for work_id, labels in attributions.DOCUMENTS.items():
        w = BY_WORK[work_id]
        if not registry.has_facts(w):
            continue
        for k in attributions.ATTRIBUTION_KEYS:
            assert w["attribution"][k] == labels.get(k), (work_id, k)
        assert w["attribution_note"] == labels.get("attribution_note"), work_id
        if labels.get("notes"):
            assert w["notes"] == labels["notes"], work_id
    for (work_id, key), labels in attributions.WORKS.items():
        row = next(x for x in BY_WORK[work_id]["works"] if x["work_key"] == key)
        for k, v in labels.items():
            assert row[k] == v, (work_id, key, k)


def test_diognetus_later_chapters_carry_their_note():
    diognetus = BY_WORK["church-fathers/apostolic-fathers/iii.ii"]["document_id"]
    noted = sorted(r["anchor"] for r in REG.passages
                   if r["document_id"] == diognetus and r.get("note"))
    assert noted and all(a.startswith(("iii.ii.xi", "iii.ii.xii")) for a in noted)


def test_the_three_point_three_omission_notes_survive():
    """3.3's note on the four Fathers works that lose Latin passages is kept."""
    from ingest.church_fathers import NON_ENGLISH_NOTE, NON_ENGLISH_OMITTED
    by_document = {w["document_id"]: w for w in REG.works}
    assert {by_document[d]["notes"] for d in NON_ENGLISH_OMITTED} == {NON_ENGLISH_NOTE}


# --------------------------------------------------------------------------- the build

def _entry(**attribution) -> dict:
    w = registry.work_entry(collection="church-fathers", source_key="church-fathers/x.xml#a",
                            document_id="dddddddd-0000-0000-0000-000000000001", title="X",
                            author="Y", frozen_on="2026-11-15", work_id="church-fathers/x/a")
    w.update({k: None for k in registry.FACT_FIELDS})
    w.update(translation="", source_credit="Sourced via CCEL.org")
    w["attribution"].update(attribution)
    return w


def test_the_build_takes_the_registry_s_author_and_work_labels():
    w = _entry(credited_as="Pseudo-Y", certainty="pseudonymous")
    w["works"] = [{"work_key": "w1", "ordinal": 1, "title": "W", "author": "Anonymous",
                   "certainty": "anonymous", "attribution_note": None, "notes": "N",
                   "date_display": "c. 200", "year": 200, "genre": "treatise",
                   "clavis_ref": None}]
    doc = Document(id=w["document_id"], collection="church-fathers", title="X", author="Y",
                   works=[Work(work_key="w1", ordinal=1, title="W", author="Y"),
                          Work(work_key="w2", ordinal=2, title="V", author="Y")])
    out = registry.apply_document_facts(doc, registry.WorkRegistry([w], [], [], []))
    assert (out.author, out.certainty) == ("Pseudo-Y", "pseudonymous")
    assert (out.works[0].author, out.works[0].certainty, out.works[0].notes,
            out.works[0].year, out.works[0].genre) == ("Anonymous", "anonymous", "N", 200,
                                                        "treatise")
    assert out.works[1] == doc.works[1], "a work the registry does not hold is unchanged"


def test_a_document_without_a_credit_keeps_the_adapter_s_author():
    w = _entry()
    doc = Document(id=w["document_id"], collection="church-fathers", title="X", author="Y")
    assert registry.apply_document_facts(doc, registry.WorkRegistry([w], [], [], [])).author \
        == "Y"


def test_the_generator_drops_labels_of_what_the_build_no_longer_emits(monkeypatch):
    w = _entry(credited_as="Pseudo-Y", certainty="pseudonymous", basis="b")
    w["works"] = [{"work_key": "w1", "ordinal": 1, "title": "W", "author": "Anonymous",
                   "certainty": "anonymous", "attribution_note": None, "notes": None,
                   "date_display": None, "year": None, "genre": None, "clavis_ref": None,
                   "basis": "b"}]
    monkeypatch.setitem(attributions.DOCUMENTS, w["work_id"],
                        {"credited_as": "Pseudo-Y", "certainty": "pseudonymous", "basis": "b"})
    monkeypatch.setitem(attributions.WORKS, (w["work_id"], "w1"),
                        {"author": "Anonymous", "certainty": "anonymous", "basis": "b"})
    reg = registry.WorkRegistry([w], [], [], [])
    [gone] = facts_script.generate(reg, [], [])
    assert {k: gone["attribution"][k] for k in attributions.ATTRIBUTION_KEYS} \
        == dict.fromkeys(attributions.ATTRIBUTION_KEYS)
    assert not registry.has_facts(gone)
    assert gone["works"][0]["work_key"] == "w1", "retired passages still name the work"
    assert all(gone["works"][0][k] is None for k in registry.WORK_LABELS)
    # Built, with one work only: the other keeps its row, unlabelled, and its ordinal.
    doc = Document(id=w["document_id"], collection="church-fathers", title="X", author="Y",
                   metadata={"source_key": w["source_key"]},
                   works=[Work(work_key="w2", ordinal=1, title="V")])
    [kept] = facts_script.generate(reg, [doc], [])
    assert kept["attribution"]["credited_as"] == "Pseudo-Y"
    assert [x["work_key"] for x in kept["works"]] == ["w1", "w2"]
    assert kept["works"][1]["ordinal"] == 2, "a new work follows the rows held"


def test_passage_rows_follow_the_build_s_work_keys_and_chapter_notes(monkeypatch):
    w = _entry()
    rows = [{"passage_id": f"p{i}", "document_id": w["document_id"], "anchor": a,
             "live_anchor": a, "status": "active", "frozen_on": "2026-11-15",
             "work_key": None} for i, a in enumerate(("c1", "c2", "c3"))]
    rows[2]["note"] = "Later."
    monkeypatch.setitem(attributions.PASSAGE_NOTES, (w["work_id"], "c2"), "Later.")
    doc = Document(id=w["document_id"], collection="church-fathers", title="X", passages=[
        Passage(content="a", reference="r", anchor=a, chapter_key=a, chapter_label="L",
                position=i, unit_label=None, metadata=None, work_key="w1")
        for i, a in enumerate(("c1", "c2", "c3"))])
    out = facts_script.generate_passages(registry.WorkRegistry([w], rows, [], []), [doc])
    assert [r["work_key"] for r in out] == ["w1"] * 3
    assert [r.get("note") for r in out] == [None, "Later.", None]
