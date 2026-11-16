"""Corpus cleanup 4.2: the republish check script, with no network and no paid call.

Every search assertion is driven with fixture passages that pass it and that break
each of its parts; every database expectation with fixture rows; and every check's SQL
runs on a real database migrated through 0045, where Postgres is installed.

The spec is docs/corpus-cleanup/P4-P5-republish-expand.md, item 4.2.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "republish_checks.py"
_spec = importlib.util.spec_from_file_location("republish_checks", SCRIPT)
rc = importlib.util.module_from_spec(_spec)
sys.modules["republish_checks"] = rc  # dataclasses resolve annotations through it
_spec.loader.exec_module(rc)

WORKS = Path(__file__).parents[3] / "datapipeline/registry/works.json"

# An example string for each pattern the checks match on, so a fixture passage can
# satisfy any check. A new pattern needs an example here (test_every_pattern_has_an_example).
EXAMPLES = {
    r"2267": "CCC §2263–2267",
    r"^Daniel 13:": "Daniel 13:1–28",
    r"^Daniel 14:": "Daniel 14:1–27",
    r"^John 3:": "John 3:1–21",
    r"^Psalms 23:": "Psalms 23:1–6",
    r"^Joel 3:1": "Joel 3:1–5",
    r"^Summa Theologiae I, q\. 71,": "Summa Theologiae I, q. 71, a. 1, co.: On the Work of "
                                     "the Fifth Day",
    r"^Summa Theologiae I, q\. 72,": "Summa Theologiae I, q. 72, a. 1, co.: On the Work of "
                                     "the Sixth Day",
    r"Section \d+": "On the Incarnation of the Word, Section 54",
    r"^Condemned proposition 31 of Martin Luther":
        "Condemned proposition 31 of Martin Luther (condemned by Leo X, Exsurge Domine)",
    r"^Caecilius, pagan": "Caecilius, pagan objection; answered by Octavius",
    r"^Condemned proposition \d+ \(condemned by Pius IX":
        "Condemned proposition 15 (condemned by Pius IX, Syllabus of Errors)",
    r"^Condemned articles of John Wyclif":
        "Condemned articles of John Wyclif (Council of Constance)",
    r"^Letter of Nestorius, condemned": "Letter of Nestorius, condemned by the Council of Ephesus",
    r"^Mani's teaching": "Mani's teaching, refuted by Archelaus",
    "Firmilian": "Firmilian of Caesarea",
    r"^Pseudo-Justin$": "Pseudo-Justin",
    r"^Anonymous$": "Anonymous",
    r"^Church of Smyrna$": "Church of Smyrna",
    r"^Polycarp": "Polycarp",
    r"^Cyprian": "Cyprian",
}
# Says, in words every ExplanationSays pattern accepts, that a position is rejected.
EXPLANATION = ("Leo X condemned this proposition; like Caecilius's pagan objection, it is "
               "a position the document rejects and answers.")
REMOVED_DOC = "00000000-0000-0000-0000-00000000dead"


class FakeRegistry(rc.Registry):
    """Every removal selector names one document, REMOVED_DOC."""

    def __init__(self):
        super().__init__([])

    def removed(self, added_by, reason=None, documents=()):
        return frozenset({REMOVED_DOC}), frozenset()


REGISTRY = FakeRegistry()


def hit_for(match, **extra) -> rc.Hit:
    """A passage that satisfies `match`."""
    if isinstance(match, rc.Removed):
        return rc.Hit(id="removed", document_id=REMOVED_DOC, collection="church-fathers",
                      content="removed text", **extra)
    fields = {
        "id": f"hit-{abs(hash(match)) % 10_000}",
        "document_id": match.document or "00000000-0000-0000-0000-000000000001",
        "collection": match.collection or "councils",
        "anchor": match.anchor,
        "reference": EXAMPLES[match.reference] if match.reference else "A reference",
        "unit_label": EXAMPLES[match.label] if match.label else None,
        "content": (match.text or "") + " passage text long enough to show",
        "voice": match.voice,
        "text_source": match.text_source,
        "text_status": match.text_status,
        "work_key": match.work_key,
        "author": EXAMPLES[match.author] if match.author else "An Author",
    }
    fields.update(extra)
    return rc.Hit(**fields)


OTHER = rc.Hit(id="other", document_id="00000000-0000-0000-0000-0000000000ff",
               collection="councils", anchor="other/1", reference="Elsewhere 1",
               content="an unrelated passage", author="Someone Else")


def parts(assertion) -> tuple:
    return assertion.parts if isinstance(assertion, rc.AllOf) else (assertion,)


def passing_run(check) -> rc.SearchRun:
    run = rc.SearchRun(check.question, tuple(getattr(check, "collections", ()) or
                                             (getattr(check, "collection", "x"),)))
    for part in parts(check.expect):
        if isinstance(part, (rc.Some, rc.First)):
            run.results.append(hit_for(part.match))
        elif isinstance(part, rc.ViaVector):
            run.vector.append(hit_for(part.match))
        elif isinstance(part, rc.ExplanationSays):
            hit = next((h for h in run.results if part.match.matches(h, REGISTRY)), None)
            if hit is None:
                hit = hit_for(part.match)
                run.results.append(hit)
            run.explanations[hit.id] = EXPLANATION
        elif isinstance(part, rc.Answers):
            run.results.append(dataclasses.replace(OTHER, collection=part.collection))
    # A First needs its passage first.
    firsts = [p for p in parts(check.expect) if isinstance(p, rc.First)]
    if firsts:
        top = next(h for h in run.results if firsts[0].match.matches(h, REGISTRY))
        run.results = [top] + [h for h in run.results if h is not top]
    return run


def breaking_runs(check, run: rc.SearchRun):
    """For each part of the check's assertion, a copy of the passing run it fails on."""
    for part in parts(check.expect):
        broken = rc.SearchRun(run.question, run.collections, list(run.results),
                              list(run.vector), run.outcome, list(run.degradations),
                              run.error, dict(run.explanations))
        if isinstance(part, rc.Some):
            broken.results = [h for h in broken.results if not part.match.matches(h, REGISTRY)]
        elif isinstance(part, rc.First):
            broken.results = [OTHER] + broken.results
        elif isinstance(part, rc.NoneOf):
            broken.results.append(hit_for(part.match))
        elif isinstance(part, rc.ViaVector):
            broken.vector = []
        elif isinstance(part, rc.ExplanationSays):
            broken.explanations = {k: "A passage about something." for k in broken.explanations}
        elif isinstance(part, rc.Answers):
            broken.degradations = ["cohere:" + part.collection]
        else:
            raise AssertionError(f"no breaking run for {type(part).__name__}")
        yield type(part).__name__, broken


SEARCHES = [c for c in rc.CHECKS if isinstance(c, (rc.SearchCheck, rc.KeywordCheck))]
SQL_CHECKS = [c for c in rc.CHECKS if isinstance(c, rc.SqlCheck)]
AGGREGATES = [c for c in rc.CHECKS if isinstance(c, rc.AggregateCheck)]


# --------------------------------------------------------------------------- the list

def test_check_ids_are_unique_and_every_check_says_what_it_proves():
    ids = [c.id for c in rc.CHECKS]
    assert len(ids) == len(set(ids))
    for check in rc.CHECKS:
        assert check.items and check.proves.endswith((".", ")")), check.id
        assert check.expectation(), check.id


def test_every_collection_answers_an_ordinary_and_a_reference_question():
    from app.rag.constants import VALID_COLLECTIONS

    assert set(rc.ORDINARY) == set(VALID_COLLECTIONS) == set(rc.REFERENCES)
    answers = {c.collections[0] for c in SEARCHES if isinstance(c, rc.SearchCheck)
               and isinstance(c.expect, rc.Answers)}
    vector = {c.collections[0] for c in SEARCHES if isinstance(c, rc.SearchCheck)
              and any(isinstance(p, rc.ViaVector) for p in parts(c.expect))}
    assert answers == vector == set(VALID_COLLECTIONS)


def test_searches_name_valid_collections_and_allowed_quotas():
    from app.rag.search_plan import resolve_search_plan

    for check in SEARCHES:
        if isinstance(check, rc.SearchCheck):
            resolve_search_plan(check.collections, check.quota)
        else:
            assert check.collection in rc.ORDINARY


def test_3_2_labels_are_the_registered_ones():
    """Each label a 3.2 check expects is the one 3.2 wrote to works.json: a document's
    shown author is `credited_as` (else its author), its certainty the attribution's."""
    works = {w["document_id"]: w for w in json.loads(WORKS.read_text())}
    for document_id, columns in rc.DOCUMENT_LABELS.items():
        w = works[document_id]
        registered = {
            "author": w["attribution"]["credited_as"] or w["author"],
            "certainty": w["attribution"]["certainty"],
            "attribution_note": w["attribution_note"], "notes": w["notes"],
        }
        assert {c: registered[c] for c in columns} == columns, document_id
    for key, columns in rc.WORK_LABELS.items():
        document_id, work_key = key.split(" ")
        [work] = [k for k in works[document_id]["works"] if k["work_key"] == work_key]
        assert {c: work.get(c) for c in columns} == columns, key
    preserved = {d for d, w in works.items() if (w.get("notes") or "").startswith("Preserved ")}
    assert set(rc.PRESERVED_FRAGMENTS) == preserved
    entries = [e for e in json.loads(rc.REMOVALS.read_text()) if e["added_by"] == "3.2"]
    assert {e["id"] for e in entries} == {"rm-7001", "rm-7002", "rm-7003"}


@pytest.mark.parametrize("check", [c for c in rc.CHECKS if isinstance(c, rc.SqlCheck)
                                   and isinstance(c.expect, rc.ByKey)], ids=lambda c: c.id)
def test_keyed_expectations_pass_and_fail_on_fixture_rows(check):
    good = [{"key": k, **cols} for k, cols in check.expect.expected.items()]
    assert check.expect(good).ok
    first = next(iter(check.expect.expected))
    assert not check.expect([r for r in good if r["key"] != first]).ok
    column = next(iter(check.expect.expected[first]))
    assert not check.expect([{**r, column: "something else"} if r["key"] == first else r
                             for r in good]).ok


def test_document_ids_name_the_works_they_claim():
    works = {w["document_id"]: w["title"] for w in json.loads(WORKS.read_text())}
    named = {
        rc.CATECHISM: "Catechism of the Catholic Church",
        rc.CANON_LAW: "Code of Canon Law (1983)",
        rc.SUMMA: "Summa Theologiae",
        rc.PSALMS: "Psalms",
        rc.NOSTRA_AETATE: "Nostra Aetate",
        rc.LUMEN_GENTIUM: "Lumen Gentium",
        rc.TRENT: "Council of Trent",
        rc.VATICAN_I: "First Vatican Council",
        rc.CHALCEDON: "Council of Chalcedon",
        rc.EPHESUS: "Council of Ephesus",
        rc.LATERAN_IV: "Fourth Lateran Council",
        rc.CONSTANCE: "Council of Constance",
        rc.EXSURGE_DOMINE: "Exsurge Domine",
        rc.SYLLABUS: "Syllabus of Errors",
        rc.INEFFABILIS_DEUS: "Ineffabilis Deus",
        rc.QUANTA_CURA_1864: "Quanta Cura (1864)",
        rc.MIRARI_VOS: "Mirari Vos",
        rc.UBI_LUTETIAM: "Ubi Lutetiam",
        rc.RERUM_NOVARUM: "Rerum Novarum",
        rc.FAMILIARIS_CONSORTIO: "Familiaris Consortio",
        rc.ORDINATIO_SACERDOTALIS: "Ordinatio Sacerdotalis",
        rc.CONFESSIONS: "The Confessions of Saint Augustine",
        rc.INCARNATION: "On the Incarnation of the Word",
        rc.OCTAVIUS: "The Octavius of Minucius Felix.",
        rc.ARCHELAUS: "The Acts of the Disputation with the Heresiarch Manes.",
        rc.CYPRIAN_EPISTLES: "The Epistles of Cyprian.",
        rc.TO_HIS_WIFE: "To His Wife.",
        rc.APPAREL_OF_WOMEN: "On the Apparel of Women.",
        rc.STROMATA: "The Stromata, or Miscellanies",
        rc.INSTRUCTOR: "The Instructor",
        rc.DIVINE_INSTITUTES: "The Divine Institutes",
        rc.WORKMANSHIP_OF_GOD: "On the Workmanship of God, or the Formation of Man",
        rc.PROSLOGIUM: "Proslogium",
        rc.CUR_DEUS_HOMO: "Cur Deus Homo",
        rc.BOOK_VIII: "Book VIII. Concerning Gifts, and Ordinations, and the "
                      "Ecclesiastical Canons",
    }
    for document_id, title in named.items():
        assert works.get(document_id) == title, document_id
    vatican_ii = {w["document_id"] for w in json.loads(WORKS.read_text())
                  if w["source_key"].startswith("councils/vat2-")}
    assert set(rc.VATICAN_II) == vatican_ii
    ignatius = {w["document_id"][:8] for w in json.loads(WORKS.read_text())
                if w["title"].endswith(": Shorter and Longer Versions")}
    assert set(rc.IGNATIUS_SHORTER_AND_LONGER) == ignatius
    for group in (rc.ORIGEN, rc.TERTULLIAN_SEVEN, rc.NOVATIAN_WORKS, rc.TATIAN, rc.ARNOBIUS,
                  rc.ALEXANDER_OF_LYCOPOLIS, rc.HIPPOLYTUS, rc.GREGORY_THAUMATURGUS,
                  rc.LACTANTIUS_FRAGMENTS, rc.APOSTOLIC_CONSTITUTIONS, rc.FORGED_IGNATIUS,
                  rc.SECTIONAL_CONFESSION, rc.PFAFF_FRAGMENTS, rc.MEDIEVAL_IGNATIUS):
        assert all(d in works for d in group), group


def test_3_1_targets_are_its_removal_entries():
    """Once 3.1 (#386) has merged, every document its checks name carries a 3.1 entry
    and every 3.1 entry sits on a document a check names."""
    entries = [e for e in json.loads(rc.REMOVALS.read_text()) if e["added_by"] == "3.1"]
    if not entries:
        pytest.skip("3.1 (#386) has not merged")
    named = set().union(
        rc.ORIGEN, rc.TERTULLIAN_SEVEN, rc.NOVATIAN_WORKS, rc.TATIAN, rc.ARNOBIUS,
        rc.ALEXANDER_OF_LYCOPOLIS, rc.HIPPOLYTUS, rc.GREGORY_THAUMATURGUS,
        rc.LACTANTIUS_FRAGMENTS, rc.APOSTOLIC_CONSTITUTIONS, rc.FORGED_IGNATIUS,
        rc.SECTIONAL_CONFESSION, rc.PFAFF_FRAGMENTS, rc.MEDIEVAL_IGNATIUS,
        {rc.CYPRIAN_EPISTLES},
    )
    assert {e["document_id"] for e in entries} == named


def test_every_pattern_has_an_example():
    for check in SEARCHES:
        for part in parts(check.expect):
            match = getattr(part, "match", None)
            if isinstance(match, rc.Match):
                for value in (match.reference, match.label, match.author):
                    if value:
                        assert value in EXAMPLES, (check.id, value)
                        assert re.search(value, EXAMPLES[value])


def test_list_runs_without_settings_or_calls():
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--list"], capture_output=True, text=True,
        timeout=60, env=env, cwd="/",
    )
    assert result.returncode == 0, result.stderr
    for check in rc.CHECKS:
        assert f"] {check.id} " in result.stdout
    assert f"{len(rc.CHECKS)} checks" in result.stdout


# --------------------------------------------------------------------------- search assertions

@pytest.mark.parametrize("check", SEARCHES, ids=[c.id for c in SEARCHES])
def test_search_assertions_pass_and_fail_on_fixtures(check):
    run = passing_run(check)
    verdict = check.expect(run, REGISTRY)
    assert verdict.ok, verdict.detail
    for name, broken in breaking_runs(check, run):
        assert not check.expect(broken, REGISTRY).ok, name


def test_match_reads_a_unit_with_its_pieces_but_not_a_longer_number():
    match = rc.Match(anchor="nostra-aetate/4")
    assert match.matches(rc.Hit("a", "d", "councils", anchor="nostra-aetate/4"))
    assert match.matches(rc.Hit("b", "d", "councils", anchor="nostra-aetate/4/from-e18"))
    assert not match.matches(rc.Hit("c", "d", "councils", anchor="nostra-aetate/40"))


def test_answers_fails_on_an_error_outcome_and_on_no_result_from_its_collection():
    check = rc.Answers("bible")
    good = rc.SearchRun("q", ("bible",), [dataclasses.replace(OTHER, collection="bible")])
    assert check(good, REGISTRY).ok
    assert not check(rc.SearchRun("q", ("bible",), [OTHER]), REGISTRY).ok
    assert not check(rc.SearchRun("q", ("bible",), [dataclasses.replace(
        OTHER, collection="bible")], outcome="degraded_success"), REGISTRY).ok


def test_some_within_looks_only_at_the_first_results():
    target = rc.Match(anchor="can/1055")
    run = rc.SearchRun("q", ("canon-law",), [OTHER, hit_for(target)])
    assert rc.Some(target, within=2)(run, REGISTRY).ok
    assert not rc.Some(target, within=1)(run, REGISTRY).ok


def test_explanation_that_presents_an_objection_as_teaching_fails():
    check = next(c for c in rc.CHECKS if c.id == "2.4d.summa-objection")
    run = passing_run(check)
    hit = next(h for h in run.results if h.voice == "rejected")
    run.explanations[hit.id] = ("Aquinas argues that evil disproves God's existence, and "
                                "teaches this conclusion; he answers the question directly.")
    assert not check.expect(run, REGISTRY).ok


def test_returned_fields_are_judged_as_returned():
    """A stale payload is judged as the search returned it, not as the corpus stores
    it; the corpus adds only the card's facts and visibility."""
    stored = rc.Hit("p", "d", "catechism", reference="CCC §2263–2267", content="inadmissible",
                    voice="rejected", author="Catholic Church", searchable=False)
    returned = {"id": "p", "document_id": "d", "collection": "catechism",
                "reference": "CCC §2266–2267 (part)", "content": "practically non-existent",
                "voice": None, "anchor": "ccc/2266", "unit_label": None}
    hit = rc.as_returned(returned, stored)
    assert (hit.reference, hit.content, hit.voice, hit.anchor) == (
        "CCC §2266–2267 (part)", "practically non-existent", None, "ccc/2266")
    assert (hit.author, hit.searchable, hit.found) == ("Catholic Church", False, True)
    missing = rc.as_returned(returned, None)
    assert (missing.found, missing.content) == (False, "practically non-existent")


def test_deuterocanonical_check_needs_every_book_cited_by_verse():
    good = [{"key": b, "n": n, "miscited": 0}
            for b, n in rc.DEUTEROCANONICAL_PASSAGES.items()]
    assert rc.deuterocanonical_pericopes(good).ok
    assert not rc.deuterocanonical_pericopes(good[1:]).ok
    assert not rc.deuterocanonical_pericopes(
        [{**r, "n": 0} if r["key"] == "Baruch" else r for r in good]).ok
    assert not rc.deuterocanonical_pericopes(
        [{**r, "miscited": 1} if r["key"] == "Tobit" else r for r in good]).ok


def test_indulgence_check_needs_the_definition_not_just_the_anchor():
    """C-03: the card for §1471 must hold the definition itself."""
    check = next(c for c in rc.CHECKS if c.id == "4.2.indulgence")
    without = rc.Hit("p", rc.CATECHISM, "catechism", anchor="ccc/1471",
                     content="§1471 The doctrine and practice of indulgences in the Church "
                             "are closely linked to the effects of the sacrament of Penance.")
    assert not check.expect(rc.SearchRun("q", ("catechism",), [without]), REGISTRY).ok
    with_it = dataclasses.replace(without, content=without.content + ' "An indulgence is a '
                                  'remission before God of the temporal punishment due to sins '
                                  'whose guilt has already been forgiven."')
    assert check.expect(rc.SearchRun("q", ("catechism",), [with_it]), REGISTRY).ok


def test_explanation_check_fails_without_its_passage():
    check = rc.ExplanationSays(rc.Match(voice="rejected"), ("reject",))
    assert not check(rc.SearchRun("q", ("summa",), [OTHER]), REGISTRY).ok


# --------------------------------------------------------------------------- registry

def _entry(**fields):
    base = {"id": "rm-1", "added_by": "3.1", "scope": "passage", "reason": "rule-a",
            "document_id": "doc-a", "passage_id": "p-1", "closed_by": None}
    return {**base, **fields}


def test_registry_reads_open_document_and_passage_entries_only():
    registry = rc.Registry([
        _entry(scope="document", passage_id=None),
        _entry(passage_id="p-2", document_id="doc-b"),
        _entry(passage_id="p-3", document_id="doc-b", closed_by="1.2e-3"),
        _entry(scope="span", passage_id=None, document_id="doc-c"),
        _entry(passage_id="p-4", document_id="doc-d", added_by="1.3d",
               reason="awaiting-permission"),
    ])
    assert registry.removed("3.1") == ({"doc-a"}, {"p-2"})
    assert registry.removed("3.1", documents=("doc-b",)) == (frozenset(), {"p-2"})
    assert registry.removed(("3.1", "1.3d")) == ({"doc-a"}, {"p-2", "p-4"})
    assert registry.removed("1.3d", reason="awaiting-permission") == (frozenset(), {"p-4"})
    with pytest.raises(LookupError, match="has that item merged"):
        registry.removed("3.2")
    with pytest.raises(LookupError):
        registry.removed("3.1", documents=("doc-c",))


def test_removed_matches_a_document_or_a_passage_the_registry_names():
    registry = rc.Registry([_entry(scope="document", passage_id=None),
                            _entry(passage_id="p-9", document_id="doc-z")])
    removed = rc.Removed("3.1")
    assert removed.matches(rc.Hit("x", "doc-a", "church-fathers"), registry)
    assert removed.matches(rc.Hit("p-9", "doc-z", "church-fathers"), registry)
    assert not removed.matches(rc.Hit("p-8", "doc-z", "church-fathers"), registry)


def test_the_real_registry_resolves_every_merged_items_removals():
    registry = rc.Registry.load()
    has_3_1 = any(e["added_by"] == "3.1" for e in json.loads(rc.REMOVALS.read_text()))
    for check in SQL_CHECKS:
        if check.id.startswith("3.1.") and not has_3_1:
            continue
        check.args(registry)  # raises LookupError for a selector that names nothing


# --------------------------------------------------------------------------- SQL expectations

def _value_for(want):
    return want.n if isinstance(want, rc.AtLeast) else want


def _off_by_one(want):
    return want.n - 1 if isinstance(want, rc.AtLeast) else want + 1


@pytest.mark.parametrize("check", [c for c in SQL_CHECKS if isinstance(c.expect, rc.Row)],
                         ids=lambda c: c.id)
def test_row_expectations_pass_and_fail_on_fixture_rows(check):
    good = {column: _value_for(want) for column, want in check.expect.expected.items()}
    assert check.expect([good]).ok
    for column, want in check.expect.expected.items():
        assert not check.expect([{**good, column: _off_by_one(want)}]).ok, column
    assert not check.expect([]).ok
    assert not check.expect([good, good]).ok


@pytest.mark.parametrize("check", [c for c in SQL_CHECKS if isinstance(c.expect, rc.CountsBy)],
                         ids=lambda c: c.id)
def test_count_expectations_pass_and_fail_on_fixture_rows(check):
    counts = {**check.expect.exact, **check.expect.at_least}
    good = [{"key": key, "n": n} for key, n in counts.items()]
    assert check.expect(good).ok
    for key, n in counts.items():
        assert not check.expect([r if r["key"] != key else {"key": key, "n": n - 1}
                                 for r in good]).ok, key
    assert not check.expect(good + [{"key": "something-else", "n": 1}]).ok


def test_summa_citations_agree_with_their_articles():
    agree = [
        {"reference": "Summa Theologiae I, q. 2, a. 3, obj. 1: Whether God exists?",
         "article": "FP_Q2_A3"},
        {"reference": "Summa Theologiae I, q. 71, a. 1, co.: On the Work of the Fifth Day",
         "article": "FP_Q71"},
        {"reference": "Summa Theologiae I-II, q. 1, a. 1, obj. 1: Whether …",
         "article": "FS_Q1_A1"},
        {"reference": "Summa Theologiae Suppl., App. 2, q. 1, a. 1, obj. 1: Whether …",
         "article": "AP2_Q1_A1"},
        {"reference": "Summa Theologiae I, q. 2, prologue", "article": None},
    ]
    assert rc.summa_citations_agree(agree).ok
    assert not rc.summa_citations_agree(agree + [
        {"reference": "Summa Theologiae I, q. 2, a. 2, ad 1: Whether …", "article": "FP_Q2_A3"},
    ]).ok
    assert not rc.summa_citations_agree(agree + [
        {"reference": "Summa Theologiae II-II, q. 2, a. 3, co.", "article": "FP_Q2_A3"},
    ]).ok
    assert not rc.summa_citations_agree([{"reference": "x", "article": None}]).ok


@pytest.mark.parametrize("check", AGGREGATES, ids=lambda c: c.id)
def test_aggregates_pass_and_fail_on_fixture_searches(check):
    clean = rc.Hit("a", rc.SUMMA, "summa", content="A passage of ordinary length.",
                   reference="Summa Theologiae I, q. 2, a. 3, obj. 1: Whether God exists?",
                   article="FP_Q2_A3")
    assert check.expect([rc.SearchRun("q", ("bible",), [clean])]).ok
    assert not check.expect([]).ok
    bad = {
        "4.2.no-short-results": dataclasses.replace(clean, content="§12"),
        "4.2.results-searchable": dataclasses.replace(clean, searchable=False),
        "4.2.summa-results-cite-their-article": dataclasses.replace(
            clean, reference="Summa Theologiae I, q. 2, a. 2, ad 1: Whether …"),
        "4.2.vatican-ii-results-not-notes": dataclasses.replace(
            clean, document_id=rc.NOSTRA_AETATE, content="Cf. Rom. 11:28."),
    }[check.id]
    assert not check.expect([rc.SearchRun("q", ("bible",), [clean, bad])]).ok
    if check.id == "4.2.results-searchable":
        for hidden in (dataclasses.replace(clean, retired=True),
                       dataclasses.replace(clean, found=False)):
            assert not check.expect([rc.SearchRun("q", ("bible",), [hidden])]).ok


# --------------------------------------------------------------------------- running

def _context(search=None, explain=None, rows=None, keyword_ids=(), hits=None):
    async def fetch(sql, args):
        return rows if rows is not None else [{"visible": 0, "live_documents": 0}]

    async def hydrate(ids):
        return {i: hits[i] for i in ids if i in (hits or {})}

    async def keyword(question, collection, limit):
        return list(keyword_ids)

    return rc.Context(fetch, hydrate, keyword, search, explain, REGISTRY)


async def test_paid_checks_are_not_run_without_spend():
    search = next(c for c in rc.CHECKS if isinstance(c, rc.SearchCheck))
    aggregate = AGGREGATES[0]
    outcomes = await rc.run_checks([aggregate, search], _context())
    assert [(o.check.id, o.status) for o in outcomes] == [
        (search.id, "NOT RUN"), (aggregate.id, "NOT RUN")]


async def test_a_run_explains_only_its_target_and_adds_the_cost():
    check = next(c for c in rc.CHECKS if c.id == "2.4d.exsurge-domine-31")
    target = hit_for(check.explain_targets()[0])
    asked = []

    async def search(c):
        return rc.SearchRun(c.question, c.collections,
                            [OTHER, dataclasses.replace(target, voice="rejected",
                                                        unit_label=EXAMPLES[
                                                            r"^Condemned proposition 31 of Martin Luther"])],
                            cost=0.01, explain_inputs={target.id: "objection [answered:] reply"})

    async def explain(hit, question, content):
        asked.append((hit.id, content))
        return EXPLANATION, 0.002

    [outcome] = await rc.run_checks([check], _context(search, explain))
    assert outcome.status == "PASS", outcome.detail
    assert asked == [(target.id, "objection [answered:] reply")]
    assert rc.summarise([outcome])["cost_usd"] == 0.012


@pytest.mark.parametrize("outcome,degradations", [
    ("retrieval_failed", []), ("ranking_failed", []), ("degraded_success", ["cohere:bible"]),
    ("success", ["rerank_listwise_luna:parse_failed"]),
])
async def test_a_search_that_did_not_run_cleanly_is_an_error(outcome, degradations):
    """An empty result from a failed search must not pass a "never returns" check."""
    check = next(c for c in rc.CHECKS if c.id == "3.1.search-flight-in-persecution")

    async def search(c):
        return rc.SearchRun(c.question, c.collections, outcome=outcome,
                            degradations=degradations)

    [result] = await rc.run_checks([check], _context(search))
    assert result.status == "ERROR", result.detail


async def test_a_healthy_search_with_no_candidates_can_pass_a_removal_check():
    check = next(c for c in rc.CHECKS if c.id == "3.1.search-flight-in-persecution")

    async def search(c):
        return rc.SearchRun(c.question, c.collections, outcome="no_candidates")

    [result] = await rc.run_checks([check], _context(search))
    assert result.status == "PASS", result.detail


@pytest.mark.parametrize("check_id", [
    "3.1.search-flight-in-persecution", "1.3d.search-held",
])
async def test_an_empty_search_still_needs_its_removal_targets(check_id):
    """A healthy empty search must not pass a removal check whose item has not merged."""
    check = next(c for c in rc.CHECKS if c.id == check_id)

    async def search(c):
        return rc.SearchRun(c.question, c.collections, outcome="no_candidates")

    ctx = _context(search)
    ctx.registry = rc.Registry([])
    [result] = await rc.run_checks([check], ctx)
    assert result.status == "ERROR" and "has that item merged" in result.detail


async def test_aggregates_run_last_over_every_search():
    short = rc.Hit("s", "d", "bible", content="§1")
    check = next(c for c in rc.CHECKS if c.id == "4.2.susanna")

    async def search(c):
        return rc.SearchRun(c.question, c.collections, [short])

    aggregate = next(c for c in AGGREGATES if c.id == "4.2.no-short-results")
    outcomes = await rc.run_checks([aggregate, check], _context(search))
    assert [o.check.id for o in outcomes] == [check.id, aggregate.id]
    assert outcomes[1].status == "FAIL"


async def test_a_failing_search_or_query_is_an_error_not_a_crash():
    check = next(c for c in rc.CHECKS if c.id == "4.2.susanna")

    async def search(c):
        return rc.SearchRun(c.question, c.collections, error="PipelineExecutionError: rerank")

    async def broken_fetch(sql, args):
        raise RuntimeError("connection reset")

    ctx = _context(search)
    ctx.fetch = broken_fetch
    sql = next(c for c in SQL_CHECKS if c.id == "4.2.no-short-passages")
    outcomes = await rc.run_checks([check, sql], ctx)
    assert [o.status for o in outcomes] == ["ERROR", "ERROR"]
    assert "connection reset" in outcomes[1].detail


async def test_keyword_checks_read_their_hits_in_order():
    check = next(c for c in rc.CHECKS if c.id == "2.2c.keyword-canon-1055")
    first = rc.Hit("c1055", rc.CANON_LAW, "canon-law", anchor="can/1055")
    second = rc.Hit("c382", rc.CANON_LAW, "canon-law", anchor="can/382")
    [ok] = await rc.run_checks([check], _context(keyword_ids=["c1055", "c382"],
                                                  hits={"c1055": first, "c382": second}))
    [wrong] = await rc.run_checks([check], _context(keyword_ids=["c382", "c1055"],
                                                     hits={"c1055": first, "c382": second}))
    assert (ok.status, wrong.status) == ("PASS", "FAIL")


async def test_vector_paths_are_recorded_and_the_step_restored():
    from app.rag.steps import retrieve_vector
    from app.rag.steps.types import RetrievalPath

    original = retrieve_vector.run

    async def fake(*args, **kwargs):
        return {"bible": [RetrievalPath("hyde", [{"id": "v1"}]),
                          RetrievalPath("query", [{"id": "v2"}])]}

    retrieve_vector.run = fake
    try:
        captured: list[dict] = []
        with rc._recording_vector_paths(captured):
            await retrieve_vector.run([], {}, ["bible"], 5)
        assert captured == [{"id": "v1"}, {"id": "v2"}]
        assert retrieve_vector.run is fake
    finally:
        retrieve_vector.run = original


def test_select_by_id_or_prefix():
    assert {c.id for c in rc.select(rc.CHECKS, ["3.1"])} == {
        c.id for c in rc.CHECKS if c.id.startswith("3.1.")}
    assert [c.id for c in rc.select(rc.CHECKS, ["4.2.ccc-2267"])] == ["4.2.ccc-2267"]
    with pytest.raises(SystemExit):
        rc.select(rc.CHECKS, ["no-such-check"])


async def test_spending_on_staging_refuses_the_live_vector_collection(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "corpus_read_schema", "staging")
    monkeypatch.setattr(settings, "qdrant_read_collection", "chunks_live")
    with pytest.raises(SystemExit, match="vector search would read the live corpus"):
        await rc.main(["--spend"])


def test_outcome_record_holds_corpus_data_only():
    check = next(c for c in rc.CHECKS if c.id == "4.2.susanna")
    run = rc.SearchRun(check.question, check.collections,
                       [rc.Hit("h", "d", "bible", anchor="daniel/13/1",
                               reference="Daniel 13:1–28", content="text")], cost=0.01)
    record = rc.outcome_record(rc.Outcome(check, "PASS", "found", run))
    assert set(record) == {"id", "items", "kind", "status", "detail", "expects", "question",
                           "results", "explanations", "cost_usd", "seconds",
                           "vector_seconds"}
    assert record["results"] == [{"reference": "Daniel 13:1–28", "anchor": "daniel/13/1",
                                  "collection": "bible"}]


def test_summary_reports_cost_and_search_timings():
    check = next(c for c in rc.CHECKS if c.id == "4.2.susanna")
    outcomes = [rc.Outcome(check, "PASS", "", rc.SearchRun("q", ("bible",), cost=0.006,
                                                          seconds=s, vector_seconds=v))
                for s, v in ((3.0, 0.2), (5.0, 0.9), (4.0, 0.4))]
    summary = rc.summarise(outcomes + [rc.Outcome(check, "NOT RUN", "")])
    assert summary["counts"] == {"PASS": 3, "NOT RUN": 1}
    assert summary["cost_usd"] == 0.018
    assert summary["search_timing"] == {"median_s": 4.0, "max_s": 5.0}
    assert summary["vector_search_timing"] == {"median_s": 0.4, "max_s": 0.9}
    assert rc.summarise([])["search_timing"] is None


# --------------------------------------------------------------------------- the SQL itself

@pytest.fixture(scope="module")
def migrated():
    from tests.pg_cluster import local_cluster
    from tests.test_corpus_facts_migration import EARLIER, PRODUCTION_SCHEMA

    with local_cluster("tc-republish-checks-") as cluster:
        cluster.sql(PRODUCTION_SCHEMA)
        cluster.migrate(*EARLIER, "0042_corpus_facts_retirement_staging.sql",
                        "0043_validate_corpus_facts.sql", "0044_document_form.sql",
                        "0045_search_vector_markers_and_reference.sql")
        cluster.sql(f"""
            INSERT INTO documents (id, collection, title, metadata) VALUES
              ('{rc.CANON_LAW}', 'canon-law', 'Code of Canon Law (1983)',
               '{{"official_latin_urls": {{"can/295": "https://www.vatican.va/x"}}}}'),
              ('{rc.SUMMA}', 'summa', 'Summa Theologiae', '{{}}');
            INSERT INTO chunks (document_id, position, anchor, reference, content, metadata)
            VALUES ('{rc.CANON_LAW}', 0, 'can/1055', 'Code of Canon Law, Can. 1055',
                    'The matrimonial covenant', '{{}}'),
                   ('{rc.SUMMA}', 0, 'summa/FP_Q2_A3/p2',
                    'Summa Theologiae I, q. 2, a. 3, obj. 1: Whether God exists?',
                    'It seems that God does not exist', '{{"article": "FP_Q2_A3"}}');
        """)
        yield cluster


@pytest.mark.parametrize("check", SQL_CHECKS, ids=lambda c: c.id)
async def test_every_sql_check_runs_on_a_migrated_database(migrated, check):
    import asyncpg

    from app.db import _init_connection

    conn = await asyncpg.connect(host=str(migrated.socket), user="postgres",
                                 database="postgres")
    await _init_connection(conn)
    try:
        rows = [dict(r) for r in await conn.fetch(check.sql, *check.args(REGISTRY))]
    finally:
        await conn.close()
    expect = check.expect
    if isinstance(expect, rc.Row):
        assert len(rows) == 1 and set(expect.expected) <= set(rows[0])
    elif isinstance(expect, rc.CountsBy):
        assert all(set(r) == {"key", "n"} for r in rows)
    elif isinstance(expect, rc.ByKey):
        assert all({"key", *cols} <= set(r) for r in rows for cols in expect.expected.values())
    elif expect is rc.deuterocanonical_pericopes:
        assert {r["key"] for r in rows} == set(rc.DEUTEROCANONICAL_PASSAGES)
        assert all(set(r) == {"key", "n", "miscited"} for r in rows)
    else:
        assert all({"reference", "article"} <= set(r) for r in rows)
    expect(rows)  # an expectation reads what the query returns without raising


async def test_keyword_hydration_reads_a_passage_back(migrated):
    import asyncpg

    from app.db import _init_connection

    conn = await asyncpg.connect(host=str(migrated.socket), user="postgres",
                                 database="postgres")
    await _init_connection(conn)
    try:
        ids = [r["id"] for r in await conn.fetch(
            "SELECT id::text FROM chunks WHERE anchor = 'can/1055'")]
        hits = rc._hits(dict(r) for r in await conn.fetch(rc._HYDRATE_SQL, ids))
    finally:
        await conn.close()
    [hit] = hits.values()
    assert (hit.anchor, hit.collection, hit.searchable, hit.retired) == (
        "can/1055", "canon-law", True, False)


async def test_deuterocanonical_sql_counts_a_missing_citation_as_miscited(migrated):
    import asyncpg

    from app.db import _init_connection

    check = next(c for c in SQL_CHECKS if c.id == "1.4c.deuterocanonical-pericopes")
    tobit = "00000000-0000-0000-0000-00000000b0b1"
    migrated(f"""
        INSERT INTO documents (id, collection, title) VALUES ('{tobit}', 'bible', 'Tobit');
        INSERT INTO chunks (document_id, position, anchor, reference, content) VALUES
          ('{tobit}', 0, 'tobit/1/1', 'Tobit 1:1–22', 'The book of the words of Tobit'),
          ('{tobit}', 1, 'tobit/2/1', NULL, 'Now when I had come home again'),
          ('{tobit}', 2, 'tobit/3/1', 'Tobit 3', 'Then being grieved');
    """)
    conn = await asyncpg.connect(host=str(migrated.socket), user="postgres",
                                 database="postgres")
    await _init_connection(conn)
    try:
        rows = [dict(r) for r in await conn.fetch(check.sql, *check.args(REGISTRY))]
    finally:
        await conn.close()
        migrated(f"DELETE FROM documents WHERE id = '{tobit}'")
    assert next(r for r in rows if r["key"] == "Tobit") == {"key": "Tobit", "n": 3,
                                                             "miscited": 2}
