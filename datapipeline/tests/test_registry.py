"""The work registry (corpus-cleanup 2.1): frozen IDs, structural anchors, split pieces,
redirects, removals and the shared definitions Phase 1 adapters use."""
import copy
import json
import os
import re
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

import identity  # noqa: E402
import registry  # noqa: E402
from ingest import summa  # noqa: E402
from ingest.pieces import Segment, name_pieces  # noqa: E402
from model import Document, Passage, Work  # noqa: E402
from registry import genres  # noqa: E402
from release import remap as R  # noqa: E402

TODAY = "2026-10-30"
COLLECTION = "church-fathers"


@pytest.fixture(scope="module")
def shipped():
    return registry.load_registry()


# --------------------------------------------------------------------------- helpers

def work(source_key="church-fathers/vol.xml#ii", document_id=None, **changes):
    entry = registry.work_entry(collection=COLLECTION, source_key=source_key,
                                document_id=document_id or identity.document_id(source_key),
                                title="A Work", author="An Author", frozen_on=TODAY)
    entry.update(changes)
    return entry


def row(document_id, anchor, passage_id=None, status="active", live_anchor=None, **extra):
    out = {"passage_id": passage_id or identity.passage_id(document_id, live_anchor or anchor),
           "document_id": document_id, "anchor": anchor,
           "live_anchor": live_anchor or anchor, "status": status, "frozen_on": TODAY,
           "work_key": None}
    out.update(extra)
    return out


def removal(entry_id="rm-0001", **changes):
    w = work()
    out = {"id": entry_id, "scope": "passage", "collection": COLLECTION,
           "document_id": w["document_id"], "anchor": "ii.i",
           "passage_id": identity.passage_id(w["document_id"], "ii.i"),
           "reason": "rule-g-editorial", "detail": "An editor's note.",
           "tombstone": "This passage was an editor's note.", "church_act": None,
           "span": None, "judgment": None, "added_by": "1.8a", "added_on": TODAY}
    out.update(changes)
    return out


def valid_registry(**parts) -> registry.WorkRegistry:
    w = work()
    base = {"works": [w], "passages": [row(w["document_id"], "ii.i")], "redirects": [],
            "removals": []}
    base.update(parts)
    return registry.WorkRegistry(base["works"], base["passages"], base["redirects"],
                                 base["removals"])


def passage(anchor, content="text", position=0, **fields):
    return Passage(content=content, reference="ref", anchor=anchor, chapter_key="ii",
                   chapter_label="II", position=position, **fields)


def document(passages, document_id=None):
    return Document(id=document_id or work()["document_id"], collection=COLLECTION,
                    title="A Work", passages=passages)


def cut(unit, paragraphs, boundaries):
    """A unit of numbered paragraphs (`p1`, `p2`, ...) cut into pieces before the given
    paragraph indexes: the pieces as the adapters name them."""
    text = "\n\n".join(paragraphs)
    segments = [Segment(f"p{i + 1}", t) for i, t in enumerate(paragraphs)]
    pieces, start = [], 0
    for b in boundaries + [len(paragraphs)]:
        pieces.append("\n\n".join(paragraphs[start:b]))
        start = b
    named = name_pieces(unit, text, pieces, segments)
    return [passage(a, c, k, source_units=u) for k, (c, (a, u)) in enumerate(zip(pieces, named))]


PARAGRAPHS = [f"Paragraph {n} says something particular about the subject {n}." for n in
              ("one", "two", "three", "four", "five", "six")]


# --------------------------------------------------------------------------- the shipped files

def test_registry_has_421_entries_and_unique_ids(shipped):
    assert len(shipped.works) == 421
    assert len({w["document_id"] for w in shipped.works}) == 421
    assert len({(w["collection"], w["source_key"]) for w in shipped.works}) == 421
    assert len({w["work_id"] for w in shipped.works}) == 421


def test_registry_is_sorted_and_stable(shipped, tmp_path):
    assert registry.validate(shipped) == []
    registry.write_registry(shipped, str(tmp_path))
    for name in (registry.WORKS_FILE, registry.REDIRECTS_FILE, registry.REMOVALS_FILE):
        with open(os.path.join(registry.REGISTRY_DIR, name), encoding="utf-8") as a, \
                open(tmp_path / name, encoding="utf-8") as b:
            assert a.read() == b.read(), name


def test_passage_registry_is_sorted_and_stable(shipped, tmp_path):
    registry.write_registry(shipped, str(tmp_path))
    folder = os.path.join(registry.REGISTRY_DIR, registry.PASSAGES_DIR)
    names = sorted(os.listdir(folder))
    assert names == sorted(os.listdir(tmp_path / registry.PASSAGES_DIR))
    for name in names:
        with open(os.path.join(folder, name), encoding="utf-8") as a, \
                open(tmp_path / registry.PASSAGES_DIR / name, encoding="utf-8") as b:
            assert a.read() == b.read(), name


def test_new_unit_gets_computed_id_that_collides_with_no_frozen_id(shipped):
    # A unit live never had takes its ID from its structural anchor, and that ID is no
    # other row's: a new unit never takes a live passage's ID.
    owner = {r["passage_id"]: (r["document_id"], r["anchor"]) for r in shipped.passages}
    new = [r for r in shipped.passages if r["live_anchor"] is None]
    assert new
    for r in new:
        assert r["passage_id"] == identity.passage_id(r["document_id"], r["anchor"])
        assert owner[r["passage_id"]] == (r["document_id"], r["anchor"])
    reg = valid_registry()
    rec = registry.reconcile(reg, [document([passage("ii.i"), passage("ii.ix", position=1)])],
                             item="test", today=TODAY)
    new = next(r for r in rec.rows if r["anchor"] == "ii.ix")
    assert new["passage_id"] == identity.passage_id(work()["document_id"], "ii.ix")
    assert new["passage_id"] not in reg.frozen_ids and rec.problems == []


# --------------------------------------------------------------------------- document IDs

def test_frozen_id_wins_over_label_derived_id():
    w = work()
    reg = valid_registry(works=[w])
    # The work is relabeled: its label-derived ID would change, the frozen one does not.
    got = registry.resolve_document_id(COLLECTION, w["source_key"],
                                       (COLLECTION, "A Corrected Author", "A Work"), reg)
    assert got == w["document_id"]
    assert got != identity.document_id(COLLECTION, "A Corrected Author", "A Work")


def test_unregistered_work_falls_back_to_identity_document_id():
    reg = valid_registry()
    parts = (COLLECTION, "New Author", "New Work")
    assert registry.resolve_document_id(COLLECTION, "church-fathers/new.xml#iv", parts, reg) \
        == identity.document_id(*parts)
    entry = registry.register_new_work(
        reg, Document(id=identity.document_id(*parts), collection=COLLECTION,
                      title="New Work", metadata={"source_key": "church-fathers/new.xml#iv"}),
        TODAY)
    assert entry["work_id"] == "church-fathers/new/iv"
    assert registry.frozen_document_id(COLLECTION, "church-fathers/new.xml#iv", reg) \
        == identity.document_id(*parts)


def test_two_source_keys_cannot_share_an_id():
    a = work("church-fathers/vol.xml#ii")
    b = work("church-fathers/vol.xml#iii", document_id=a["document_id"])
    problems = registry.validate(valid_registry(works=[a, b], passages=[]))
    assert any("duplicate document_id" in p for p in problems)


def test_rule_a_fields_validate():
    good = {"issuer": "Pope Cornelius's Roman synod", "date": "0251-01-01",
            "act": "excommunication", "effect": "condemn", "citation": "https://example.org"}
    w = work(rule_a={**work()["rule_a"], "applies": True, "communion_start": "0230-01-01",
                     "church_acts": [good], "decision": "exclude"})
    assert registry.validate(valid_registry(works=[w])) == []
    for bad in ({"church_acts": [{**good, "effect": "praise"}]},
                {"church_acts": [{**good, "citation": None}]},
                {"church_acts": [{**good, "date": "251"}]},
                {"communion_end": "about 235"},
                {"decision": "maybe"}):
        w = work(rule_a={**work()["rule_a"], **bad})
        assert registry.validate(valid_registry(works=[w])), bad


def test_attribution_fields_validate():
    judgment = {"source_file": "anf01.xml", "element_id": "ii.iv-p1",
                "quote": "Its genuineness is doubtful.", "verdict": "dubious",
                "overridden_by_plan": False}
    w = work(attribution={**work()["attribution"], "certainty": "pseudonymous",
                          "editorial_judgments": [judgment]})
    assert registry.validate(valid_registry(works=[w])) == []
    for bad in ({"certainty": "probable"},
                {"editorial_judgments": [{**judgment, "verdict": "forged"}]},
                {"editorial_judgments": [{**judgment, "element_id": None}]}):
        w = work(attribution={**work()["attribution"], **bad})
        assert registry.validate(valid_registry(works=[w])), bad


# --------------------------------------------------------------------------- passage IDs

def test_frozen_passage_id_survives_anchor_change():
    w = work()
    frozen = row(w["document_id"], "ii.i", live_anchor="some-work/chapter-1")
    reg = valid_registry(passages=[frozen])
    # The unit's anchor is rebuilt from structure: the registry still names its ID.
    assert registry.resolve_passage_id(w["document_id"], "ii.i", reg) == \
        identity.passage_id(w["document_id"], "some-work/chapter-1")
    # A later label fix edits the row's anchor and keeps the ID; no redirect is needed.
    frozen["anchor"] = "ii.i.a"
    reg = valid_registry(passages=[frozen])
    assert registry.resolve_passage_id(w["document_id"], "ii.i.a", reg) == frozen["passage_id"]


def test_registry_override_wins_over_adapter_fields():
    w = work()
    reg = valid_registry(passages=[row(w["document_id"], "ii.i", searchable=False,
                                       language="la", passage_author="Chrysostom",
                                       unit_label="Condemned proposition 10",
                                       note="A reader note.")])
    got = registry.apply_overrides(document([passage("ii.i", searchable=True)]), reg)
    p = got.passages[0]
    assert (p.searchable, p.language, p.passage_author, p.unit_label) == \
        (False, "la", "Chrysostom", "Condemned proposition 10")
    assert p.metadata["note"] == "A reader note."


def test_voice_values_validate():
    w = work()
    assert registry.validate(valid_registry(
        passages=[row(w["document_id"], "ii.i", voice="rejected")])) == []
    assert registry.validate(valid_registry(
        passages=[row(w["document_id"], "ii.i", voice="objection")]))
    assert registry.VOICES == ("rejected",)


def test_registry_voice_override_wins():
    w = work()
    reg = valid_registry(passages=[row(w["document_id"], "ii.i", voice="rejected")])
    assert registry.apply_overrides(document([passage("ii.i")]), reg).passages[0].voice \
        == "rejected"


def test_history_passage_shape():
    current = passage("can/295")
    history = passage("can/295/history-1983", position=1, searchable=False,
                      superseded_by_anchor="can/295")
    assert registry.history_problems(document([current, history])) == []
    for bad in (passage("can/295/history-1983", searchable=True, superseded_by_anchor="can/295"),
                passage("can/295/old", searchable=False, superseded_by_anchor="can/295"),
                passage("can/296/history-1983", searchable=False,
                        superseded_by_anchor="can/296"),
                passage("can/295/history-1983", searchable=False)):
        assert registry.history_problems(document([current, bad])), bad.anchor


# --------------------------------------------------------------------------- the work model

def test_genre_values_are_lowercase_hyphenated_and_unique():
    assert len(genres.ALL_GENRES) == len(set(genres.ALL_GENRES))
    assert all(re.fullmatch(r"[a-z]+(-[a-z]+)*", g) for g in genres.ALL_GENRES)
    assert genres.ALL_GENRES.count("commentary") == 1
    assert genres.OTHER in genres.ALL_GENRES
    for group in (genres.PAPAL_GENRES, genres.CURIA_GENRES,
                  genres.CATECHISM_AND_LAW_GENRES, genres.WRITER_GENRES):
        assert set(group) <= set(genres.ALL_GENRES)


def _container():
    w = work(works=[{"work_key": "letter-1", "ordinal": 1, "title": "Letter 1",
                     "author": "Firmilian", "certainty": "genuine", "attribution_note": None,
                     "notes": None, "date_display": None, "year": None, "genre": "letter",
                     "clavis_ref": None}])
    return w


def test_passage_work_key_names_a_work_of_its_document():
    w = _container()
    assert registry.validate(valid_registry(
        works=[w], passages=[row(w["document_id"], "ii.i", work_key="letter-1")])) == []
    assert any("names no work" in p for p in registry.validate(valid_registry(
        works=[w], passages=[row(w["document_id"], "ii.i", work_key="letter-2")])))
    assert Work(work_key="letter-1", ordinal=1, title="Letter 1").genre is None


def test_every_work_has_a_passage():
    w = _container()
    assert any("has no passage" in p for p in registry.validate(valid_registry(
        works=[w], passages=[row(w["document_id"], "ii.i")])))


# --------------------------------------------------------------------------- redirects and removals

def test_redirect_kinds_are_remap_words():
    assert registry.REDIRECT_KINDS == R.REDIRECT_KINDS
    w = work()
    redirect = {"document_id": w["document_id"], "old_passage_id": "a", "old_anchor": "ii.x",
                "new_passage_id": "b", "new_anchor": "ii.i", "kind": "merged",
                "reason": "test", "added_by": "test"}
    rows = [row(w["document_id"], "ii.i"),
            row(w["document_id"], "ii.x", passage_id="a", status="redirected")]
    assert registry.validate(valid_registry(passages=rows, redirects=[redirect])) == []
    assert registry.validate(valid_registry(passages=rows,
                                            redirects=[{**redirect, "kind": "same"}]))


def test_removal_entries_validate():
    w = work()
    rows = [row(w["document_id"], "ii.i", status="retired")]
    assert registry.validate(valid_registry(passages=rows, removals=[removal()])) == []
    for bad in ({"scope": "chapter"}, {"reason": "heresy"}, {"tombstone": None},
                {"tombstone": "x" * registry.TOMBSTONE_MAX},
                {"scope": "span", "span": {"sha1": "0", "excerpt": "x"}},
                {"reason": "rule-a", "church_act": None},
                {"passage_id": identity.passage_id(w["document_id"], "ii.ix")}):
        assert registry.validate(valid_registry(passages=rows,
                                                removals=[removal(**bad)])), bad
    document_scope = removal(scope="document", anchor=None, passage_id=None)
    assert registry.validate(valid_registry(removals=[document_scope])) == []


def test_removal_entry_needs_anchor_not_position():
    w = work()
    entry = removal(anchor=None)
    entry["position"] = 3
    problems = registry.validate(valid_registry(
        passages=[row(w["document_id"], "ii.i", status="retired")], removals=[entry]))
    assert any("never a position" in p for p in problems)
    assert any("needs an anchor" in p for p in problems)


def test_no_anchor_is_both_retired_and_a_redirect_target():
    w = work()
    rows = [row(w["document_id"], "ii.i", status="retired"),
            row(w["document_id"], "ii.x", passage_id="a", status="redirected")]
    redirect = {"document_id": w["document_id"], "old_passage_id": "a", "old_anchor": "ii.x",
                "new_passage_id": rows[0]["passage_id"], "new_anchor": "ii.i",
                "kind": "merged", "reason": "test", "added_by": "test"}
    problems = registry.validate(valid_registry(passages=rows, redirects=[redirect],
                                                removals=[removal()]))
    assert any("also a redirect target" in p for p in problems)


def test_rolled_back_reason_is_rejected_in_removals_file():
    w = work()
    problems = registry.validate(valid_registry(
        passages=[row(w["document_id"], "ii.i", status="retired")],
        removals=[removal(reason=registry.ROLLED_BACK)]))
    assert any("only by rollback" in p for p in problems)


def test_closed_entry_is_kept_and_ignored_by_writer():
    w = work()
    closed = removal(closed_by="1.8d", closed_on=TODAY)
    reg = valid_registry(passages=[row(w["document_id"], "ii.i")], removals=[closed])
    assert registry.validate(reg) == []
    assert reg.removals == [closed] and registry.open_removals(reg) == []
    # The release report applies only open entries: the passage, still built, is fine.
    old = [R.OldPassage(closed["passage_id"], w["document_id"], COLLECTION, "ii.i", "ii", "r",
                        0, "text")]
    result = R.remap(old, [document([passage("ii.i")])],
                     R.Registry(removals=reg.removals))
    assert not [f for f in result.failures if f.check == "bad_removal"]


# --------------------------------------------------------------------------- split pieces

def test_first_piece_takes_the_unit_anchor():
    pieces = cut("ii.i", PARAGRAPHS, [2, 4])
    assert [p.anchor for p in pieces] == ["ii.i", "ii.i/from-p3", "ii.i/from-p5"]
    assert pieces[1].source_units == (("p3", 0), ("p4", len(PARAGRAPHS[2]) + 2))


def test_later_piece_anchor_names_its_first_source_unit():
    w = work()
    first = cut("ii.i", PARAGRAPHS, [2, 4])
    reg = valid_registry(passages=[row(w["document_id"], p.anchor) for p in first])
    ids = {p.anchor: registry.resolve_passage_id(w["document_id"], p.anchor, reg) for p in first}
    # Cut differently: p3 no longer opens a piece, p5 still does.
    rec = registry.reconcile(reg, [document(cut("ii.i", PARAGRAPHS, [1, 4]))],
                             item="test", today=TODAY)
    rows = {r["anchor"]: r for r in rec.rows}
    assert rows["ii.i/from-p5"]["passage_id"] == ids["ii.i/from-p5"]
    assert rows["ii.i/from-p5"]["status"] == "active"
    assert rows["ii.i/from-p3"]["status"] == "redirected"
    [redirect] = rec.redirects
    assert (redirect["old_passage_id"], redirect["new_anchor"], redirect["kind"]) == \
        (ids["ii.i/from-p3"], "ii.i/from-p2", "merged")
    assert rec.problems == []


def test_first_piece_of_newly_split_unit_keeps_unit_id():
    w = work()
    reg = valid_registry(passages=[row(w["document_id"], "ii.i")])
    rec = registry.reconcile(reg, [document(cut("ii.i", PARAGRAPHS, [3]))],
                             item="test", today=TODAY)
    rows = {r["anchor"]: r for r in rec.rows}
    assert rows["ii.i"]["passage_id"] == identity.passage_id(w["document_id"], "ii.i")
    assert rows["ii.i/from-p4"]["passage_id"] == \
        identity.passage_id(w["document_id"], "ii.i/from-p4")
    assert rec.redirects == [] and rec.problems == []


def test_piece_cut_inside_a_long_paragraph_adds_k():
    long = " ".join(f"Sentence {k} of a long paragraph." for k in range(60))
    paragraphs = ["A short opening paragraph.", long]
    text = "\n\n".join(paragraphs)
    third = len(long) // 3
    i = text.index(". ", len(paragraphs[0]) + third) + 2
    j = text.index(". ", len(paragraphs[0]) + 2 * third) + 2
    pieces = [text[:i].strip(), text[i:j].strip(), text[j:].strip()]
    named = name_pieces("ii.i", text, pieces, [Segment("p1", paragraphs[0]),
                                                Segment("p2", long)])
    assert [a for a, _ in named] == ["ii.i", "ii.i/from-p2-2", "ii.i/from-p2-3"]
    assert named[1][1][0] == ("p2", 0)


def test_piece_created_redirected_and_reappearing_reclaims_its_id():
    w = work()
    start = valid_registry(passages=[row(w["document_id"], "ii.i")])
    created = registry.reconcile(start, [document(cut("ii.i", PARAGRAPHS, [3]))],
                                 item="1.10b", today=TODAY)
    piece_id = next(r["passage_id"] for r in created.rows if r["anchor"] == "ii.i/from-p4")
    reg = registry.WorkRegistry(start.works, created.rows, created.redirects, [])
    redirected = registry.reconcile(reg, [document(cut("ii.i", PARAGRAPHS, [2]))],
                                    item="1.8a", today=TODAY)
    reg = registry.WorkRegistry(start.works, redirected.rows, redirected.redirects, [])
    assert next(r for r in reg.passages if r["passage_id"] == piece_id)["status"] == "redirected"
    assert registry.validate(reg) == []
    reopened = registry.reconcile(reg, [document(cut("ii.i", PARAGRAPHS, [3]))],
                                  item="1.10c", today=TODAY)
    reg = registry.WorkRegistry(start.works, reopened.rows, reopened.redirects, [])
    again = next(r for r in reg.passages if r["anchor"] == "ii.i/from-p4")
    assert (again["passage_id"], again["status"]) == (piece_id, "active")
    closed = next(r for r in reg.redirects if r["old_passage_id"] == piece_id)
    assert (closed["closed_by"], closed["closed_on"]) == ("1.10c", TODAY)
    assert registry.validate(reg) == []
    assert registry.resolve_passage_id(w["document_id"], "ii.i/from-p4", reg) == piece_id
    # The release report ignores the closed redirect, so reusing the anchor is no failure.
    old = [R.OldPassage(piece_id, w["document_id"], COLLECTION, "ii.i/from-p4", "ii", "ref",
                        1, "\n\n".join(PARAGRAPHS[3:]))]
    built = document(cut("ii.i", PARAGRAPHS, [3]))
    open_only = [r for r in reg.redirects if not r.get("closed_by")]
    result = R.remap(old, [built], R.Registry(redirects=open_only),
                     passage_id=lambda d, p: registry.resolve_passage_id(d.id, p.anchor, reg))
    assert result.rows[0].outcome == "same"
    assert not [f for f in result.failures if f.check in ("anchor_reuse", "bad_redirect")]


# --------------------------------------------------------------------------- Summa anchors

_ARTICLE = """<ThML><ThML.body><div1 title="FIRST PART" id="FP">
<div3 title="QUESTION 1" id="FP_Q1"><div4 title="Whether it is so?" id="FP_Q1_A1">
<p id="FP_Q1_A1-p1"><b>Objection 1:</b> It seems that it is not so, for the reason given.</p>
<p id="FP_Q1_A1-p2"><b>{second}:</b> Further, another reason is given for the opposite view.</p>
<p id="FP_Q1_A1-p3"><b>On the contrary,</b> Augustine says that it is so.</p>
<p id="FP_Q1_A1-p4"><b>I answer that,</b> It is so, as the argument shows at some length.</p>
<p id="FP_Q1_A1-p5"><b>Reply to Objection 1:</b> The reason does not follow.</p>
</div4></div3></div1></ThML.body></ThML>"""


def _summa(tmp_path, second):
    path = tmp_path / f"summa-{second.replace(' ', '')}.xml"
    path.write_text(_ARTICLE.format(second=second), encoding="utf-8")
    return summa.build_document(str(path))


def test_summa_anchor_is_source_paragraph_id(tmp_path):
    right = _summa(tmp_path, "Objection 2")
    wrong = _summa(tmp_path, "Reply to Objection 3")      # a wrong bold label (C-04)
    assert [p.anchor for p in right.passages] == [
        "summa/FP_Q1_A1/p1", "summa/FP_Q1_A1/p2", "summa/FP_Q1_A1/p3", "summa/FP_Q1_A1/p4",
        "summa/FP_Q1_A1/p5"]
    assert [p.anchor for p in wrong.passages] == [p.anchor for p in right.passages]
    assert [p.unit_label for p in wrong.passages] != [p.unit_label for p in right.passages]
    assert right.metadata["source_key"] == "summa"


def test_summa_adapter_builds_no_anchor_from_a_label():
    with open(summa.__file__, encoding="utf-8") as f:
        source = f.read()
    assert not re.search(r"anchor\s*=\s*[^\n]*(unit_label|label|a_title)", source)


def test_second_summa_part_in_one_paragraph_takes_2(tmp_path):
    text = _ARTICLE.format(second="Objection 2").replace(
        '</p>\n<p id="FP_Q1_A1-p3"><b>On the contrary,</b>', " On the contrary,")
    path = tmp_path / "summa-merged.xml"
    path.write_text(text, encoding="utf-8")
    anchors = [p.anchor for p in summa.build_document(str(path)).passages]
    assert anchors[1:3] == ["summa/FP_Q1_A1/p2", "summa/FP_Q1_A1/p2-2"]


def test_shipped_registry_counts_every_snapshot_document(shipped):
    index = json.load(open(os.path.join(os.path.dirname(registry.REGISTRY_DIR), "releases",
                                        "snapshots.json"), encoding="utf-8"))
    latest = max(index["snapshots"], key=lambda s: s["date"])
    assert latest["tables"]["documents"] == len(shipped.works)
    live = [r for r in shipped.passages if r["live_anchor"] is not None]
    assert len(live) == latest["tables"]["chunks"]


def test_work_registry_is_independent_copy():
    reg = valid_registry()
    snapshot = copy.deepcopy(reg.passages)
    registry.reconcile(reg, [document([passage("ii.i"), passage("ii.ix", position=1)])],
                       item="test", today=TODAY)
    assert reg.passages == snapshot
