"""Rejected-voice ranges (corpus-cleanup 3.4): the tracked ranges file, the registry rows it
generates, and the `roles.rejected_voice` check, on made-up documents. The check on the
real build is in tests/source_checks/test_rejected_voice_sources.py."""
import re

import pytest

import registry
from checks import content
from model import Document, Passage
from registry import rejected_voice as rv
from scripts import rejected_voice_rows as rows_script

DOC = "doc-1"


def _p(anchor, unit_label=None, voice=None):
    return Passage(content="Some words.", reference=anchor, anchor=anchor, chapter_key="ch",
                   chapter_label="Chapter", position=0, unit_label=unit_label, voice=voice)


def _doc(*passages, collection="encyclicals", doc_id=DOC):
    for i, p in enumerate(passages):
        p.position = i
    return Document(id=doc_id, collection=collection, title="A Document",
                    passages=list(passages))


def _range(first, last, label="Condemned proposition {n} (A List)", collection="encyclicals",
           doc_id=DOC):
    return rv.Range(collection=collection, document_id=doc_id, title="A Document",
                    first_anchor=first, last_anchor=last, label=label, basis="An act.")


@pytest.fixture(scope="module")
def shipped():
    return registry.load_registry()


@pytest.fixture(scope="module")
def ranges():
    return rv.load_ranges()


# --------------------------------------------------------------------------- tracked files

def test_ranges_file_is_valid(ranges, shipped):
    assert rv.validate(ranges, shipped.works) == []


def test_registry_still_validates(shipped):
    assert registry.validate(shipped) == []


def test_every_rejected_row_sits_in_a_listed_document_under_its_label(ranges, shipped):
    """Every registry row with the role is in a document the ranges list, and its label is
    one of that document's label patterns (the Summa's objections take the role from the
    adapter, not from a row)."""
    patterns = {}
    for r in ranges:
        text = re.escape(r.label).replace(re.escape("{n}"), r"\d+")
        patterns.setdefault(r.document_id, []).append(re.compile(f"^{text}$"))
    wrong = [(row["document_id"], row["anchor"], row.get("unit_label"))
             for row in shipped.passages if row.get("voice") == rv.VOICE
             and not any(p.match(row.get("unit_label") or "")
                         for p in patterns.get(row["document_id"], []))]
    assert wrong == []


def test_each_range_ends_on_rows_that_carry_the_role(ranges, shipped):
    for r in ranges:
        for anchor in (r.first_anchor, r.last_anchor):
            row = shipped.row_by_anchor.get((r.document_id, anchor))
            assert row is not None and row["status"] == "active", anchor
            assert row.get("voice") == rv.VOICE, anchor


def test_the_document_keeps_its_own_notes_out_of_the_syllabus_ranges(ranges, shipped):
    """The Syllabus's N.B. notes and section IV's heading are Pius IX's own words."""
    syllabus = next(r.document_id for r in ranges if r.title == "Syllabus of Errors")
    for anchor in ("text-2", "text-4", "text-8", "text-9"):
        row = shipped.row_by_anchor[(syllabus, f"syllabus-of-errors/{anchor}")]
        assert "voice" not in row and "unit_label" not in row


# --------------------------------------------------------------------------- ranges

def test_label_takes_the_number_ending_the_unit_anchor():
    r = _range("list/1", "list/9")
    assert r.label_for(_p("list/10")) == "Condemned proposition 10 (A List)"
    assert r.label_for(_p("list/10/from-p2")) == "Condemned proposition 10 (A List)"
    assert _range("a", "b", label="Plain").label_for(_p("x")) == "Plain"
    with pytest.raises(ValueError):
        r.label_for(_p("list/intro"))


def test_validate_names_each_problem():
    works = [{"document_id": DOC, "collection": "encyclicals"}]
    assert rv.validate([_range("a", "b")], works) == []
    assert rv.validate([_range("a", "b", collection="councils")], works) \
        == [f"A Document a: document {DOC} is not in councils"]
    assert rv.validate([_range("a", "b", label="Article {k}")], works) \
        == ["A Document a: label 'Article {k}' holds a placeholder other than {n}"]
    assert rv.validate([rv.Range("encyclicals", DOC, "A Document", "a", "b", "L", "")],
                       works) == ["A Document a: no basis"]
    unsorted = [_range("a", "b", doc_id="z"), _range("a", "b")]
    assert "not sorted" in rv.validate(unsorted, works + [
        {"document_id": "z", "collection": "encyclicals"}])[0]


def test_expand_follows_reading_order_not_anchor_order():
    d = _doc(_p("x/2"), _p("x/10"), _p("x/note"), _p("x/3"))
    assert [p.anchor for p in rv.expand(d, _range("x/10", "x/3"))] == ["x/10", "x/note", "x/3"]
    with pytest.raises(ValueError, match="comes before"):
        rv.expand(d, _range("x/3", "x/10"))
    with pytest.raises(ValueError, match="not in the build"):
        rv.expand(d, _range("x/1", "x/3"))


def test_two_ranges_may_not_share_a_passage():
    d = _doc(_p("x/1"), _p("x/2"), _p("x/3"))
    with pytest.raises(ValueError, match="two ranges"):
        rv.labels([d], [_range("x/1", "x/2"), _range("x/2", "x/3")])


# --------------------------------------------------------------------------- the check

def test_check_passes_a_marked_range_and_a_summa_objection():
    label = "Condemned proposition {n} (A List)"
    d = _doc(_p("x/1", "Condemned proposition 1 (A List)", "rejected"),
             _p("x/2", "Condemned proposition 2 (A List)", "rejected"), _p("x/note"))
    assert rv.check("encyclicals", [d], [_range("x/1", "x/2", label)]) == {}
    summa = _doc(_p("q/1/p1", "Objection 1", "rejected"), _p("q/1/p2", "On the contrary"),
                 collection="summa")
    assert rv.check("summa", [summa], []) == {}


def test_check_fails_each_wrong_passage():
    d = _doc(_p("x/1", "Condemned proposition 1 (A List)"),
             _p("x/2", "§2", "rejected"),
             _p("x/note", None, "rejected"))
    units = rv.check("encyclicals", [d], [_range("x/1", "x/2")])["roles.rejected_voice:encyclicals"]
    assert units == [f"{DOC}#x/1: no rejected voice",
                     f"{DOC}#x/2: label '§2', not 'Condemned proposition 2 (A List)'",
                     f"{DOC}#x/note: rejected voice outside every range"]


def test_check_fails_a_range_that_does_not_resolve():
    d = _doc(_p("x/1"))
    assert rv.check("encyclicals", [d], [_range("x/1", "x/9")]) == {
        "roles.rejected_voice:encyclicals": ["A Document: anchor x/9 is not in the build"]}
    assert rv.check("encyclicals", [], [_range("x/1", "x/9")]) == {
        "roles.rejected_voice:encyclicals": [f"{DOC}: A Document is not in the build"]}
    assert rv.check("councils", [], [_range("x/1", "x/9")]) == {}


def test_a_non_summa_objection_label_is_not_excused():
    d = _doc(_p("x/1", "Objection 1", "rejected"), collection="church-fathers")
    assert rv.check("church-fathers", [d], []) == {
        "roles.rejected_voice:church-fathers": [f"{DOC}#x/1: rejected voice outside every range"]}


def test_content_run_applies_the_registry_overrides(monkeypatch):
    """The check reads the documents as the stage writes them: a row's role and label
    reach a passage the adapter left bare."""
    r = _range("x/1", "x/1", label="Plain")
    bare = _doc(_p("x/1"))
    assert content.rejected_voice("encyclicals", [bare], [r]) != {}
    marked = registry.WorkRegistry(passages=[{"document_id": DOC, "anchor": "x/1",
                                              "passage_id": "p", "voice": "rejected",
                                              "unit_label": "Plain"}])
    previous = registry.activate(marked)
    try:
        assert content.rejected_voice("encyclicals", [bare], [r]) == {}
    finally:
        registry.activate(previous)


# --------------------------------------------------------------------------- generator

def _row(anchor, **extra):
    return {"passage_id": anchor, "document_id": DOC, "anchor": anchor, "status": "active",
            **extra}


def test_generator_sets_role_and_label_and_counts_changes():
    rows = [_row("x/1"), _row("x/2", voice="rejected", note="A note."), _row("x/3"),
            _row("x/4", voice="rejected", unit_label="L2")]
    wanted = {(DOC, "x/1"): "L1", (DOC, "x/2"): "L2", (DOC, "x/4"): "L2"}
    out, changed = rows_script.updated_rows(rows, wanted, {DOC})
    assert changed == 2
    assert out[0] == _row("x/1", voice="rejected", unit_label="L1")
    assert out[1] == _row("x/2", voice="rejected", note="A note.", unit_label="L2")
    assert out[2] == _row("x/3")


def test_generator_refuses_a_missing_row_and_a_stray_role():
    with pytest.raises(ValueError, match="no registry row"):
        rows_script.updated_rows([_row("x/1")], {(DOC, "x/2"): "L"}, {DOC})
    with pytest.raises(ValueError, match="outside every range"):
        rows_script.updated_rows([_row("x/1", voice="rejected")], {}, {DOC})
    out, changed = rows_script.updated_rows([_row("x/1", voice="rejected")], {}, {"other"})
    assert changed == 0
