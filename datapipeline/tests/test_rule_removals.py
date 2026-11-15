"""Removals under rules A to C (corpus-cleanup 3.1): the removal registry's entries, as
`scripts/rule_removals.py` writes them from R1's file and Carter's 15 Nov 2026 answers.
Reads only the registry files, so it runs without the vendored sources;
`tests/test_church_fathers.py` checks the build."""
import json

import pytest

import registry
from scripts import rule_removals

ITEM = "3.1"
CYPRIAN_EPISTLES = "aaf1a0e4-9bf5-5e26-9eaf-8f4f38ff60fe"
TREATISES_ATTRIBUTED = "5d75dc92-df2c-5421-904f-4249590ff48a"


@pytest.fixture(scope="module")
def reg():
    return registry.load_registry()


@pytest.fixture(scope="module")
def r1():
    with open(rule_removals.R1_FILE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def mine(reg):
    return [e for e in reg.removals if e.get("added_by") == ITEM]


def _rows_in(reg, document_id, divs):
    return [r for r in reg.passages if r["document_id"] == document_id
            and rule_removals._inside(r["anchor"], divs)]


def _retired(reg):
    return {e["passage_id"] for e in registry.open_removals(reg) if e["scope"] == "passage"}


def test_registry_is_what_the_generator_writes(reg, r1, mine):
    planned = rule_removals.plan(reg, r1, "today")
    strip = lambda es: [{k: v for k, v in e.items() if k != "added_on"} for e in es]
    assert sorted(strip(planned), key=lambda e: e["id"]) == \
        sorted(strip(mine), key=lambda e: e["id"])


def test_ids_stay_in_the_block(mine):
    numbers = sorted(int(e["id"].split("-")[1]) for e in mine)
    assert numbers == list(range(5001, 5001 + len(mine)))
    assert numbers[-1] <= 6999
    assert registry.validate(registry.load_registry()) == []


def test_every_rule_a_exclusion_has_its_entries(r1, mine):
    """R1's file decides rule A: each work it excludes has 3.1's rule-A entries, and none
    it includes has one (rule B or C may still remove it)."""
    reg = registry.load_registry()
    documents = {e["document_id"] for e in mine
                 if e["reason"] == "rule-a" and e["scope"] == "document"}
    passages = {e["passage_id"] for e in mine
                if e["reason"] == "rule-a" and e["scope"] == "passage"}
    for e in r1:
        if "document_id" not in e:
            continue                                  # a planned candidate work
        doc, div, decision = e["document_id"], e.get("div_id"), e["rule_a"]["decision"]
        if div is None:
            assert (doc in documents) == (decision == "exclude"), e["title"]
            continue
        rows = {r["passage_id"] for r in _rows_in(reg, doc, (div,))}
        assert rows, e["title"]
        if decision == "exclude":
            assert rows - passages <= _retired(reg), e["title"]
            assert rows & passages, e["title"]
        else:
            assert not rows & passages, e["title"]


def test_no_novatian_passage_stays_active(reg):
    """Novatian, condemned by name in 251: his two works whole, his two treatises among
    Cyprian's, and Epistles XXV, XXIX and XXX among Cyprian's letters (C-02)."""
    removed = registry.removed_document_ids(reg)
    novatian = [w["document_id"] for w in reg.works if (w["author"] or "").startswith("Novatian")]
    assert len(novatian) == 2 and set(novatian) <= removed
    retired = _retired(reg)
    for doc, divs in ((TREATISES_ATTRIBUTED, ("iv.vii.ii", "iv.vii.iv")),
                      (CYPRIAN_EPISTLES, ("iv.iv.xxv", "iv.iv.xxix", "iv.iv.xxx"))):
        rows = _rows_in(reg, doc, divs)
        assert rows and not [r["anchor"] for r in rows if r["passage_id"] not in retired
                             and r["status"] != "redirected"]


def test_what_stays(reg):
    """Carter, 15 Nov 2026: Tertullian's To His Wife and On the Apparel of Women and
    Firmilian's letter stay; so do Hippolytus's two datable works, Treatises II and IV
    among Cyprian's, and the Apostolic Canons at the end of Book VIII."""
    removed = registry.removed_document_ids(reg)
    retired = _retired(reg)
    by_prefix = {w["document_id"][:8]: w["document_id"] for w in reg.works}
    assert not {by_prefix["3717ce05"], by_prefix["e73bb326"]} & removed
    for prefix, divs in (("aaf1a0e4", ("iv.iv.lxxiv", "iv.iv.ii", "iv.iv.xlix")),
                         ("506ebe31", ("iii.iv.i.x", "iii.iv.ii.i")),
                         ("5d75dc92", ("iv.vii.iii", "iv.vii.v")),
                         ("10d8d7c6", ("ix.ix.vi",)),
                         ("0066869a", ("ix.viii.xxxv", "ix.viii.xl"))):
        rows = _rows_in(reg, by_prefix[prefix], divs)
        assert rows and not [r["anchor"] for r in rows if r["passage_id"] in retired], prefix


def test_counts(mine):
    scopes = {s: sum(e["scope"] == s for e in mine) for s in ("document", "passage")}
    assert scopes == {"document": 33, "passage": 285}
    by_reason = {}
    for e in mine:
        if e["scope"] == "document":
            by_reason[e["reason"]] = by_reason.get(e["reason"], 0) + 1
    assert by_reason == {"rule-a": 16, "rule-b": 13, "rule-c": 4}


def test_tombstones_are_the_approved_sentences(mine):
    approved = {
        rule_removals._condemned("Origen"), rule_removals._condemned("Novatian"),
        rule_removals.T_NOVATIAN_LETTER, rule_removals._broke("Tertullian"),
        rule_removals._broke("Tatian"), rule_removals.T_HIPPOLYTUS,
        rule_removals.T_ARNOBIUS, rule_removals.T_NOT_CHRISTIAN, rule_removals.T_PANEGYRIC,
        rule_removals.T_PHOENIX, rule_removals.T_CONSTITUTIONS,
        rule_removals.T_IGNATIUS_FORGED, rule_removals.T_SECTIONAL, rule_removals.T_PFAFF,
        rule_removals.T_IGNATIUS_LATIN}
    assert {e["tombstone"] for e in mine} == approved
    assert rule_removals._condemned("Origen") == (
        "Removed because the Church condemned Origen by name, and TheoCorpus leaves out "
        "every work of an author it has condemned by name.")


def test_church_acts(mine):
    """Origen and Novatian cite their acts, the Apostolic Constitutions the Council in
    Trullo; every other rule-A or rule-B entry states its basis instead (Carter, 11 and
    15 Nov 2026), and the notice then shows no "Church act:" line."""
    import retirements

    acts = {retirements.render_church_act(e["church_act"]) for e in mine}
    assert acts == {"Second Council of Constantinople, anathema 11, 553",
                    "Roman synod under Pope Cornelius, excommunication of Novatian, 251",
                    "Council in Trullo, canon 2, confirmed by the Second Council of Nicaea, "
                    "canon 1, 692", None}
    for e in mine:
        if e["church_act"] is None and e["reason"] == "rule-a":
            assert "Origen" not in e["tombstone"] and "Novatian" not in e["tombstone"]
