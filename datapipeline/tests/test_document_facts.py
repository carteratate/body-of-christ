"""Document facts in the work registry (corpus-cleanup 2.3). These read only tracked files;
tests/source_checks/test_document_facts_sources.py checks them against a build."""
from __future__ import annotations

import pytest

import document_facts
import papal_genres
import registry
import rights_inventory
from model import Document
from registry.genres import ALL_GENRES

REG = registry.load_registry()
ROWS = rights_inventory.by_document_id(rights_inventory.load())
HELD = registry.removed_document_ids(REG)
FILLED = [w for w in REG.works if registry.has_facts(w)]


def entry(**facts) -> dict:
    w = registry.work_entry(collection="medieval", source_key="medieval/x",
                            document_id="dddddddd-0000-0000-0000-000000000001", title="X",
                            author="Y", frozen_on="2026-11-14")
    base = {k: None for k in registry.FACT_FIELDS}
    base.update(translation="", source_credit="Sourced via CCEL.org")
    base.update(facts)
    w.update(base)
    return w


def problems(*works, removals=()) -> list[str]:
    return registry._validate_facts(registry.WorkRegistry(list(works), [], [], list(removals)))


# --------------------------------------------------------------------------- the tracked registry

def test_every_document_not_held_has_its_facts():
    """Every registered document the build emits carries every fact field; a document
    held for permission builds nothing and carries none."""
    missing = [w["work_id"] for w in REG.works
               if w["document_id"] not in HELD and w["status"] == "active"
               and not registry.has_facts(w)]
    assert missing == [], "run scripts/document_facts_registry.py"
    assert not [w["work_id"] for w in FILLED if w["document_id"] in HELD]
    assert all(set(registry.FACT_FIELDS) <= set(w) for w in FILLED)


def test_every_document_has_a_source_credit():
    assert [w["work_id"] for w in FILLED if not w["source_credit"]] == []


def test_genres_issuers_and_years_are_valid():
    for w in FILLED:
        assert w["genre"] is None or w["genre"] in ALL_GENRES, w["work_id"]
        if w["issuer"] is not None:
            assert registry._ISSUER.match(w["issuer"]) and w["issuer_label"], w["work_id"]
        assert w["year"] is None or type(w["year"]) is int, w["work_id"]
    assert registry._validate_facts(REG) == []


def test_source_credit_is_the_rights_inventory_wording():
    """0.2's credit line, exactly; a document holding a second edition's texts names it
    after the main line (Carter, 13 Nov 2026)."""
    for w in FILLED:
        row = ROWS[w["document_id"]]
        if w["work_id"] in document_facts.COMBINED_CREDITS:
            assert row.get("also_from"), w["work_id"]
            assert w["source_credit"].startswith(row["credit_line"] + "; "), w["work_id"]
        else:
            assert w["source_credit"] == row["credit_line"], w["work_id"]


def test_documents_with_another_edition_name_it_in_their_credit():
    for w in FILLED:
        others = [a for a in ROWS[w["document_id"]].get("also_from") or []
                  if a.get("credit_line")]
        if others:
            assert w["work_id"] in document_facts.COMBINED_CREDITS, w["work_id"]


def test_translation_is_left_out_where_the_credit_names_it():
    for w in FILLED:
        if document_facts.credit_names_translation(w["source_credit"]):
            assert w["translation"] == "", w["work_id"]
        elif w["source_credit"] != "Text: papalencyclicals.net":   # translator unknown
            assert w["translation"], w["work_id"]


def test_vatican_texts_carry_the_lev_line():
    vatican = [w for w in FILLED if ROWS[w["document_id"]].get("rights_holder")
               == "Libreria Editrice Vaticana" and w["collection"] != "catechism"]
    assert len(vatican) >= 100
    for w in vatican:
        assert w["source_credit"] == document_facts.VATICAN_CREDIT, w["work_id"]
        assert w["translation"] == "Vatican English", w["work_id"]


def test_papal_genres_are_1_3b_s():
    """2.3 carries `papal_genres.csv` (1.3b) into the registry unchanged."""
    labels = papal_genres.load()
    papal = [w for w in FILLED if w["collection"] in document_facts.PAPAL_COLLECTIONS]
    assert len(papal) >= 120
    for w in papal:
        slug = w["source_key"].split("/", 1)[1]
        assert w["genre"] == labels[slug].genre, w["work_id"]


def test_issuers():
    by_key = {w["source_key"]: w for w in FILLED}
    assert (by_key["catechism"]["issuer"], by_key["canon-law"]["issuer_label"]) \
        == ("holy-see", "Holy See")
    lumen = by_key["councils/vat2-lumen-gentium"]
    assert (lumen["issuer"], lumen["issuer_label"]) \
        == ("second-vatican-council", "Second Vatican Council")
    trent = by_key["councils/ecum-19-council-of-trent"]
    assert (trent["issuer"], trent["issuer_label"]) == ("council-of-trent", "Council of Trent")
    rerum = by_key["encyclicals/rerum-novarum"]
    assert (rerum["issuer"], rerum["issuer_label"]) == ("pope-leo-xiii", "Pope Leo XIII")
    assert {w["issuer"] for w in FILLED if w["collection"] in
            ("church-fathers", "medieval", "summa", "bible")} == {None}


def test_corrected_years():
    by_key = {w["source_key"]: w for w in FILLED}
    assert by_key["encyclicals/cum-sancta-mater-ecclesia"]["year"] == 1859
    assert by_key["encyclicals/salutis-nostrae"]["year"] == 1774
    assert (by_key["summa"]["year"], by_key["summa"]["date_display"]) == (1265, "1265 to 1274")


# --------------------------------------------------------------------------- validation

def test_a_valid_entry_passes():
    assert problems(entry(genre="treatise", issuer="holy-see", issuer_label="Holy See",
                          year=1100)) == []


@pytest.mark.parametrize("facts, message", [
    ({"genre": "bull"}, "genre"),
    ({"issuer": "Pope Leo XIII", "issuer_label": "Pope Leo XIII"}, "slug"),
    ({"issuer": "pope-leo-xiii"}, "no issuer_label"),
    ({"issuer_label": "Pope Leo XIII"}, "without an issuer"),
    ({"year": "1859"}, "not an integer"),
    ({"year": True}, "not an integer"),
    ({"source_credit": None}, "no source_credit"),
    ({"superseded_by": "eeeeeeee-0000-0000-0000-000000000009"}, "superseded_by"),
])
def test_bad_facts_are_refused(facts, message):
    assert any(message in p for p in problems(entry(**facts))), facts


def test_partial_facts_are_refused():
    w = entry()
    del w["notes"]
    assert any("facts lack notes" in p for p in problems(w))


def test_a_held_document_needs_no_credit():
    w = entry(source_credit=None)
    held = {"scope": "document", "document_id": w["document_id"], "collection": "medieval"}
    assert problems(w, removals=[held]) == []


def test_superseded_by_names_another_registered_document():
    old, new = entry(), entry()
    new.update(document_id="dddddddd-0000-0000-0000-000000000002", work_id="medieval/y",
               source_key="medieval/y")
    old["superseded_by"] = new["document_id"]
    assert problems(old, new) == []
    old["superseded_by"] = old["document_id"]
    assert problems(old, new)


# --------------------------------------------------------------------------- the build

def test_registry_facts_win_over_the_adapter():
    w = entry(genre="treatise", year=1100, translation="T (1900)", notes="N")
    w["attribution"]["certainty"], w["attribution"]["clavis"] = "disputed", "CPL 1"
    reg = registry.WorkRegistry([w], [], [], [])
    doc = Document(id=w["document_id"], collection="medieval", title="X", year=1, notes="old",
                   translation="adapter")
    out = registry.apply_document_facts(doc, reg)
    assert (out.genre, out.year, out.translation, out.notes, out.source_credit) \
        == ("treatise", 1100, "T (1900)", "N", "Sourced via CCEL.org")
    assert (out.certainty, out.clavis_ref) == ("disputed", "CPL 1")


def test_an_entry_without_facts_leaves_the_adapter_s_values():
    w = registry.work_entry(collection="medieval", source_key="medieval/x",
                            document_id="dddddddd-0000-0000-0000-000000000001", title="X",
                            author="Y", frozen_on="2026-11-14")
    doc = Document(id=w["document_id"], collection="medieval", title="X", year=7,
                   translation="adapter", date_display="c. 7")
    assert registry.apply_document_facts(doc, registry.WorkRegistry([w], [], [], [])) == doc


def test_derive_keeps_hand_set_supersession():
    w = entry(superseded_by="dddddddd-0000-0000-0000-000000000002", superseded_note="See Y")
    doc = Document(id=w["document_id"], collection="medieval", title="X")
    facts = document_facts.derive(doc, {"credit_line": "Sourced via CCEL.org"}, w)
    assert (facts["superseded_by"], facts["superseded_note"]) == (w["superseded_by"], "See Y")
    assert list(facts) == list(registry.FACT_FIELDS)
