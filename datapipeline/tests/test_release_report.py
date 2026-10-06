"""release/report.py on a synthetic snapshot and build (corpus-cleanup item 0.1c)."""
import json
import os

import pytest

from checks import report as checks_report
from model import Document, Passage
from release import remap as R
from release import report as RP
from scripts import export_live_snapshot as E

DOC = "doc-1"
SECRET = "Quodcumque ligaveris super terram erit ligatum et in caelis"   # passage text


def words(seed, n=40):
    return " ".join(f"{seed}{i}" for i in range(n)) + "."


def pid(anchor):
    return R.default_passage_id(Document(id=DOC, collection="", title=""),
                                Passage("", "", anchor, "", "", 0))


def live_row(anchor, content, position, chapter_key="q1", collection="councils"):
    return {"id": pid(anchor), "document_id": DOC, "collection": collection, "title": "T",
            "author": "A", "anchor": anchor, "chapter_key": chapter_key,
            "chapter_label": chapter_key, "reference": anchor, "unit_label": None,
            "position": position, "content": content}


def write_snapshot(tmp_path, rows, references, date="2026-10-05"):
    data = {"passages": rows, "references": references, "tables": {"chunks": len(rows)},
            "documents": [{"id": DOC, "collection": rows[0]["collection"], "title": "T"}]}
    index = tmp_path / "snapshots.json"
    return E.write_snapshot(data, str(tmp_path / "snapshots"), date, "t", str(index)), str(index)


def build(*passages, collection="councils"):
    return {collection: [Document(id=DOC, collection=collection, title="T",
                                  passages=list(passages))]}


def passage(anchor, content, position, chapter_key="q1"):
    return Passage(content=content, reference=anchor, anchor=anchor, chapter_key=chapter_key,
                   chapter_label=chapter_key, position=position)


@pytest.fixture()
def no_known(monkeypatch):
    known: dict = {}
    monkeypatch.setattr(checks_report, "load_known", lambda *a, **k: known)
    return known


def scenario(tmp_path):
    """Live: q1/a kept, q1/b gone with no successor, q1/c moved to q2/c. Build adds q2/d."""
    rows = [live_row("q1/a", words("a") + " " + SECRET, 0), live_row("q1/b", words("b"), 1),
            live_row("q1/c", words("c"), 2)]
    references = {
        "passages": {pid("q1/a"): {"retrievals": 5, "bookmarks": 1,
                                   "guest_trial_retrievals": 0, "retrieval_labels": 0},
                     pid("q1/b"): {"retrievals": 3, "bookmarks": 0,
                                   "guest_trial_retrievals": 2, "retrieval_labels": 1},
                     pid("q1/c"): {"retrievals": 1, "bookmarks": 1,
                                   "guest_trial_retrievals": 0, "retrieval_labels": 0}},
        "documents": {DOC: {"reading_progress": 4, "positions": [
            {"chapter_key": "q1", "anchor": "q1/a", "rows": 1},     # unchanged
            {"chapter_key": "q1", "anchor": "q1/c", "rows": 2},     # anchor and chapter move
            {"chapter_key": "q1", "anchor": None, "rows": 1}]}}}    # chapter stays q1
    snapshot, index = write_snapshot(tmp_path, rows, references)
    new = build(passage("q1/a", words("a") + " " + SECRET, 0),
                passage("q2/c", words("c"), 1, chapter_key="q2"),
                passage("q2/d", words("d"), 2, chapter_key="q2"))
    return snapshot, index, new


def run(tmp_path, snapshot, index, new, out="out", public=True, collections=("councils",)):
    return RP.run(snapshot, collections, str(tmp_path / out), public, registry=R.Registry(),
                  build=new, run_checks=False, index_path=index)


def test_user_impact_sums_on_synthetic_references(tmp_path, no_known):
    snapshot, index, new = scenario(tmp_path)
    no_known["release.removed:councils/" + pid("q1/b")] = {"fixed_by": "t", "description": "d"}
    assert run(tmp_path, snapshot, index, new) == 0
    data = json.load(open(tmp_path / "out" / "report.json"))
    impact = data["collections"]["councils"]["user_impact"]
    assert impact == {
        "moved": {"passages": 1, "retrievals": 1, "bookmarks": 1, "guest_trial_retrievals": 0,
                  "retrieval_labels": 0, "reading_progress": 2},
        "removed": {"passages": 1, "retrievals": 3, "bookmarks": 0, "guest_trial_retrievals": 2,
                    "retrieval_labels": 1, "reading_progress": 0}}
    outcomes = data["collections"]["councils"]["outcomes"]
    assert (outcomes["same"], outcomes["moved"], outcomes["removed"]) == (1, 1, 1)
    assert data["collections"]["councils"]["new"] == 1


def test_user_impact_counts_rows_on_a_drifted_same_passage():
    rows = [R.RemapRow("p1", "same", "id", ("p1",), 0.2, DOC, DOC, "a", "a", "q1", "q1", "summa"),
            R.RemapRow("p2", "same", "id", ("p2",), 0.9, DOC, DOC, "b", "b", "q1", "q1", "summa")]
    refs = {"passages": {"p1": {"retrievals": 2}, "p2": {"retrievals": 7}}, "documents": {}}
    impact = R.user_impact(rows, [], refs)
    assert impact == {"summa": {R.BELOW_THRESHOLD: {
        "passages": 1, "retrievals": 2, "bookmarks": 0, "guest_trial_retrievals": 0,
        "retrieval_labels": 0, "reading_progress": 0}}}


def test_markdown_has_no_passage_content_when_public(tmp_path, no_known):
    snapshot, index, new = scenario(tmp_path)
    run(tmp_path, snapshot, index, new)
    out = tmp_path / "out"
    for name in ("report.md", "health.md", "report.json", "remap.jsonl", "chapter_remap.jsonl"):
        text = (out / name).read_text()
        assert "a0 a1" not in text and "c0 c1" not in text and SECRET not in text, name
    # --no-public is for local reading and does quote passages.
    run(tmp_path, snapshot, index, new, out="local", public=False)
    assert "c0 c1" in (tmp_path / "local" / "report.md").read_text()


def test_report_fails_on_unexpected_and_on_stale_known_defects(tmp_path, no_known):
    snapshot, index, new = scenario(tmp_path)
    removed = "release.removed:councils/" + pid("q1/b")
    assert run(tmp_path, snapshot, index, new) == 1                   # unlisted failure
    no_known[removed] = {"fixed_by": "2.1", "description": "d"}
    assert run(tmp_path, snapshot, index, new) == 0                   # listed: accepted
    no_known["release.stability:councils/" + pid("q1/a")] = {"fixed_by": "t", "description": "d"}
    assert run(tmp_path, snapshot, index, new) == 1                   # listed but passes
    md = (tmp_path / "out" / "report.md").read_text()
    assert "Fixed, remove entry:" in md and "release.stability" in md


def test_snapshot_hash_mismatch_refuses_before_writing(tmp_path, no_known):
    snapshot, index, new = scenario(tmp_path)
    with open(os.path.join(snapshot, E.REFERENCES_FILE), "a") as f:
        f.write(" ")
    assert run(tmp_path, snapshot, index, new) == 1
    assert not (tmp_path / "out").exists()


def test_index_entry_must_match_snapshot(tmp_path, no_known):
    snapshot, index, new = scenario(tmp_path)
    data = json.load(open(index))
    data["snapshots"][0]["files"][E.PASSAGES_FILE] = "0" * 64
    json.dump(data, open(index, "w"))
    assert run(tmp_path, snapshot, index, new) == 1
    assert not (tmp_path / "out").exists()


def test_a_run_keeps_other_collections_rows_in_out(tmp_path, no_known):
    snapshot, index, new = scenario(tmp_path)
    run(tmp_path, snapshot, index, new)
    # A second snapshot of another collection, into the same --out.
    (tmp_path / "b").mkdir()
    other_rows = [live_row("v/1", words("v"), 0, collection="bible")]
    other, other_index = write_snapshot(tmp_path / "b", other_rows,
                                        {"passages": {}, "documents": {}}, "2026-10-06")
    run(tmp_path, other, other_index, build(passage("v/1", words("v"), 0), collection="bible"),
        collections=("bible",))
    out = tmp_path / "out"
    collections = {json.loads(line)["collection"] for line in open(out / "remap.jsonl")}
    assert collections == {"councils", "bible"}
    assert set(json.load(open(out / "report.json"))["collections"]) == {"councils", "bible"}
    health = json.load(open(out / "health.json"))
    assert set(health["build"]) == set(health["snapshot"]) == {"councils", "bible"}


def test_missing_registry_files_count_as_empty(tmp_path):
    registry = RP.load_registry(str(tmp_path))
    assert (registry.redirects, registry.removals, registry.supersedes,
            registry.enforce_redirects) == ([], [], {}, False)
    (tmp_path / "redirects.json").write_text("[]")
    (tmp_path / "works.json").write_text(json.dumps(
        [{"document_id": "new-doc", "supersedes": ["old-doc"]}]))
    registry = RP.load_registry(str(tmp_path))
    assert registry.enforce_redirects and registry.supersedes == {"old-doc": "new-doc"}


def test_release_check_ids_have_their_own_scope():
    assert checks_report.check_scope("release.stability:summa/abc") == "summa"
    assert checks_report.check_scope("release.removed:canon-law/abc") == "canon-law"
    # 0.1a judges only the prefixes it computes.
    assert not "release.removed:summa/x".startswith(checks_report.REPORT_PREFIXES)
