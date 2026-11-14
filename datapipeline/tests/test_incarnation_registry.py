"""1.8d's registry: Lawson's passages redirected into Robertson's sections."""
import pytest

import registry
from scripts.incarnation_registry import DOCUMENT_ID, ITEM, NEW_KEY, section_targets


def _p(pid, content):
    return {"id": pid, "content": content}


def test_section_targets():
    targets = section_targets([
        _p("a", "Creation and the Fall\n\n(1) In our former book. (2) Others."),
        _p("b", "Others take the view expressed by Plato."),       # continues §2
        _p("c", "(3) Such are the notions."),                       # lies in §3
        _p("d", "But is it, perhaps, so? (4) Then."),               # §3 into §4
    ])
    assert targets == {"a": (1, "split", True), "b": (2, "moved", False),
                       "c": (3, "moved", True), "d": (4, "split", True)}


def test_section_targets_refuses_markers_out_of_order():
    with pytest.raises(ValueError):
        section_targets([_p("a", "(2) x"), _p("b", "(1) y")])


def test_registry_redirects_every_lawson_passage():
    reg = registry.current()
    assert registry.validate(reg) == []
    work = next(w for w in reg.works if w["document_id"] == DOCUMENT_ID)
    assert work["source_key"] == NEW_KEY
    rows = [r for r in reg.passages if r["document_id"] == DOCUMENT_ID]
    lawson = {r["passage_id"] for r in rows if not r["anchor"].startswith("vii.ii.")}
    assert len(lawson) == 52 and all(r["status"] == "redirected"
                                     for r in rows if r["passage_id"] in lawson)
    open_ = {r["old_passage_id"]: r for r in registry.open_redirects(reg)
             if r["document_id"] == DOCUMENT_ID}
    assert set(open_) == lawson
    assert all(r["added_by"] == ITEM and r["new_anchor"].startswith("vii.ii.")
               for r in open_.values())
    # The one live retrieval: Lawson's "(24) There are some other possible objections".
    assert open_["3950df28-240a-5b5b-8c02-069b7ae4dd34"]["new_anchor"] == "vii.ii.xxiv"
    # No removal entry explains Lawson's IDs: the redirects do (spec).
    assert not [e for e in reg.removals if e.get("passage_id") in lawson]
