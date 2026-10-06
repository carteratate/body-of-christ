"""release/remap.py on synthetic passages (corpus-cleanup item 0.1c). No corpus text."""
import json
import random

import pytest

from model import Document, Passage
from release import remap as R
from release import report as RP

DOC = "doc-1"
OTHER = "doc-2"


def text(seed: str, n: int = 40) -> str:
    """n distinct words, so 8-word shingles of different seeds never meet."""
    return " ".join(f"{seed}{i}" for i in range(n)) + "."


def old(pid, anchor, content, position, document_id=DOC, chapter_key="ch1",
        reference=None, unit_label=None, collection="councils"):
    return R.OldPassage(id=pid, document_id=document_id, collection=collection, anchor=anchor,
                        chapter_key=chapter_key, reference=reference or anchor,
                        position=position, content=content, unit_label=unit_label)


def new(anchor, content, position, pid=None, chapter_key="ch1", reference=None,
        unit_label=None, text_replaced=None):
    metadata = {}
    if pid:
        metadata["passage_id"] = pid          # a frozen ID, as 2.1's registry will give
    if text_replaced:
        metadata["text_replaced"] = text_replaced
    return Passage(content=content, reference=reference or anchor, anchor=anchor,
                   chapter_key=chapter_key, chapter_label=chapter_key, position=position,
                   unit_label=unit_label, metadata=metadata or None)


def doc(*passages, document_id=DOC, collection="councils"):
    return Document(id=document_id, collection=collection, title="T", passages=list(passages))


def pid(anchor, document_id=DOC):
    return R.default_passage_id(Document(id=document_id, collection="", title=""),
                                Passage("", "", anchor, "", "", 0))


def outcome(result, old_id):
    [row] = [r for r in result.rows if r.old_id == old_id]
    return row


# --------------------------------------------------------------------------- outcomes

def test_outcome_vocabulary_is_exactly_six_words():
    assert R.OUTCOMES == ("same", "moved", "split", "merged", "renumbered", "removed")
    assert R.REDIRECT_KINDS == R.OUTCOMES[1:5]
    assert R.NEW not in R.OUTCOMES


def test_same():
    a = text("a")
    result = R.remap([old(pid("s/1"), "s/1", a, 0)], [doc(new("s/1", a, 0))])
    row = outcome(result, pid("s/1"))
    assert (row.outcome, row.method, row.new_ids, row.score) == ("same", "id", (pid("s/1"),), 1.0)
    assert result.failures == [] and result.new == []


def test_moved():
    a, b = text("a"), text("b")
    result = R.remap([old("old-a", "x/1", a, 0), old(pid("s/2"), "s/2", b, 1)],
                     [doc(new("s/9", a, 0), new("s/2", b, 1))])
    row = outcome(result, "old-a")
    assert (row.outcome, row.method, row.new_ids) == ("moved", "text_hash", (pid("s/9"),))
    assert row.new_anchor == "s/9"


def test_split():
    a = text("a", 60)
    words = a.split()
    result = R.remap([old("old-a", "x/1", a, 0)],
                     [doc(new("s/1", " ".join(words[:30]), 0),
                          new("s/2", " ".join(words[30:]), 1))])
    row = outcome(result, "old-a")
    assert (row.outcome, row.method) == ("split", "union")
    assert row.new_ids == (pid("s/1"), pid("s/2"))


def test_split_primary_is_first_piece():
    a = text("a", 200)
    words = a.split()
    # The piece that holds the start of the old text comes second in the document.
    result = R.remap([old("old-a", "x/1", a, 0)],
                     [doc(new("s/0", text("z"), 0),
                          new("s/1", " ".join(words[100:]), 1),
                          new("s/2", " ".join(words[:100]), 2))])
    row = outcome(result, "old-a")
    assert row.outcome == "split"
    assert row.new_ids[0] == pid("s/2") and set(row.new_ids) == {pid("s/1"), pid("s/2")}


def test_merged():
    a, b = text("a"), text("b")
    result = R.remap([old(pid("s/1"), "s/1", a, 0), old("old-b", "x/2", b, 1)],
                     [doc(new("s/1", a + " " + b, 0))])
    assert outcome(result, pid("s/1")).outcome == "same"
    row = outcome(result, "old-b")
    assert (row.outcome, row.method, row.new_ids) == ("merged", "containment", (pid("s/1"),))


def test_two_old_passages_into_one_new_id_are_both_merged():
    a, b = text("a"), text("b")
    result = R.remap([old("old-a", "x/1", a, 0), old("old-b", "x/2", b, 1)],
                     [doc(new("s/1", a + " " + b, 0))])
    assert [outcome(result, i).outcome for i in ("old-a", "old-b")] == ["merged", "merged"]


def test_renumbered():
    a = text("a")
    redirect = {"document_id": DOC, "old_passage_id": "old-a", "old_anchor": "joel/3/1",
                "new_passage_id": pid("joel/2/28"), "new_anchor": "joel/2/28",
                "kind": "renumbered", "reason": "Nova Vulgata numbering", "added_by": "1.4b"}
    result = R.remap([old("old-a", "joel/3/1", a, 0)], [doc(new("joel/2/28", a, 0))],
                     R.Registry(redirects=[redirect]))
    row = outcome(result, "old-a")
    assert (row.outcome, row.method, row.new_ids) == ("renumbered", "redirect",
                                                      (pid("joel/2/28"),))
    assert result.failures == []


def test_removed():
    entry = {"id": "rm-0001", "scope": "passage", "collection": "councils", "document_id": DOC,
             "anchor": "x/1", "passage_id": "old-a", "reason": "rule-g-editorial"}
    result = R.remap([old("old-a", "x/1", text("a"), 0)], [doc(new("s/1", text("z"), 0))],
                     R.Registry(removals=[entry]))
    row = outcome(result, "old-a")
    assert (row.outcome, row.new_ids, row.removal) == ("removed", (), "rm-0001")
    assert result.failures == []


def test_unexplained_removal_fails():
    result = R.remap([old("old-a", "x/1", text("a"), 0)], [doc(new("s/1", text("z"), 0))])
    assert outcome(result, "old-a").outcome == "removed"
    [failure] = result.failures
    assert failure.check_id == "release.removed:councils/old-a"


def test_closed_removal_entry_no_longer_explains():
    entry = {"id": "rm-1", "scope": "passage", "document_id": DOC, "anchor": "x/1",
             "passage_id": "old-a", "closed_by": "1.8d"}
    result = R.remap([old("old-a", "x/1", text("a"), 0)], [doc(new("s/1", text("z"), 0))],
                     R.Registry(removals=[entry]))
    assert [f.check for f in result.failures] == ["removed"]


def test_document_removal_explains_every_passage():
    entry = {"id": "rm-2", "scope": "document", "document_id": OTHER, "anchor": None}
    result = R.remap([old("o1", "a", text("a"), 0, OTHER), old("o2", "b", text("b"), 1, OTHER)],
                     [doc(new("s/1", text("z"), 0))], R.Registry(removals=[entry]))
    assert {r.removal for r in result.rows} == {"rm-2"} and result.failures == []


def test_each_old_passage_has_exactly_one_outcome():
    a, b, c, d = (text(s) for s in "abcd")
    olds = [old(pid("s/1"), "s/1", a, 0), old("old-b", "x/2", b, 1),
            old("old-c", "x/3", c, 2), old("old-d", "x/4", d, 3)]
    result = R.remap(olds, [doc(new("s/1", a, 0), new("s/5", b, 1), new("s/6", c + " " + d, 2))])
    assert sorted(r.old_id for r in result.rows) == sorted(o.id for o in olds)
    assert all(r.outcome in R.OUTCOMES for r in result.rows)
    assert all(r.method in R.METHODS or r.outcome == "removed" for r in result.rows)


def test_new_passages_are_reported():
    a = text("a")
    result = R.remap([old(pid("s/1"), "s/1", a, 0)],
                     [doc(new("s/1", a, 0), new("s/2", text("restored"), 1))])
    assert [p.id for p in result.new] == [pid("s/2")]


def test_cross_document_match_is_not_attempted_without_registry():
    a = text("a")
    olds = [old("old-a", "x/1", a, 0, document_id=OTHER)]
    build = [doc(new("s/1", a, 0))]
    assert outcome(R.remap(olds, build), "old-a").outcome == "removed"
    # Once the registry says DOC supersedes OTHER, the text is found there.
    row = outcome(R.remap(olds, build, R.Registry(supersedes={OTHER: DOC})), "old-a")
    assert (row.outcome, row.new_document_id) == ("moved", DOC)


def test_declared_redirect_wins_over_computed_match():
    a, b = text("a"), text("b")
    # Computed evidence says the text moved to s/9; the redirect says s/8.
    redirect = {"document_id": DOC, "old_passage_id": "old-a", "old_anchor": "x/1",
                "new_passage_id": pid("s/8"), "new_anchor": "s/8", "kind": "moved",
                "reason": "r", "added_by": "t"}
    result = R.remap([old("old-a", "x/1", a, 0)], [doc(new("s/8", b, 0), new("s/9", a, 1))],
                     R.Registry(redirects=[redirect]))
    row = outcome(result, "old-a")
    assert (row.outcome, row.method, row.new_ids) == ("moved", "redirect", (pid("s/8"),))


def test_redirect_with_a_report_word_or_missing_target_fails():
    a = text("a")
    rows = [{"document_id": DOC, "old_passage_id": "o1", "new_passage_id": pid("s/1"),
             "kind": "same"},
            {"document_id": DOC, "old_passage_id": "o2", "new_passage_id": "nowhere",
             "kind": "moved"}]
    result = R.remap([old("o1", "x/1", a, 0), old("o2", "x/2", text("b"), 1)],
                     [doc(new("s/1", a, 0))], R.Registry(redirects=rows))
    assert sorted(f.check_id for f in result.failures) == [
        "release.bad_redirect:councils/o1", "release.bad_redirect:councils/o2"]


def test_computed_outcome_needs_a_redirect_once_registry_lands():
    a = text("a")
    result = R.remap([old("old-a", "x/1", a, 0)], [doc(new("s/9", a, 0))],
                     R.Registry(enforce_redirects=True))
    assert [f.check_id for f in result.failures] == ["release.unbacked:councils/old-a"]


def test_remap_is_deterministic(tmp_path):
    a, b, c = text("a"), text("b", 60), text("c")
    words = b.split()
    olds = [old(pid("s/1"), "s/1", a, 0), old("old-b", "x/2", b, 1), old("old-c", "x/3", c, 2)]
    build = [doc(new("s/1", a, 0), new("s/2", " ".join(words[:30]), 1),
                 new("s/3", " ".join(words[30:]), 2), new("s/4", text("n"), 3))]
    outputs = []
    for seed in (1, 2):
        shuffled = list(olds)
        random.Random(seed).shuffle(shuffled)
        result = R.remap(shuffled, build)
        path = tmp_path / f"remap-{seed}.jsonl"
        RP._write_jsonl(str(path), [r.to_json() for r in result.rows], ("councils",))
        outputs.append(path.read_bytes())
    assert outputs[0] == outputs[1]


# --------------------------------------------------------------------------- stability (D1)

def test_restored_prose_under_same_id_passes():
    a = text("a")
    result = R.remap([old(pid("s/1"), "s/1", a, 0)],
                     [doc(new("s/1", a + " " + text("restored", 200), 0))])
    assert result.failures == [] and outcome(result, pid("s/1")).score == 1.0


def test_stripped_notes_under_same_id_passes():
    a = text("a")
    result = R.remap([old(pid("s/1"), "s/1", a + " " + text("note", 80), 0)],
                     [doc(new("s/1", a, 0))])
    assert result.failures == []


def test_different_text_under_same_id_fails_without_redirect():
    result = R.remap([old(pid("s/1"), "s/1", text("a"), 0)], [doc(new("s/1", text("b"), 0))])
    [failure] = result.failures
    assert failure.check_id == f"release.stability:councils/{pid('s/1')}"
    assert failure.score < R.ANCHOR_STABILITY_THRESHOLD


def test_short_passages_compare_word_by_word():
    # Under 16 words: a dropped word keeps most of the text; a different verse does not.
    result = R.remap([old(pid("v/1"), "v/1", "Jesus wept bitterly.", 0),
                      old(pid("v/2"), "v/2", "Rejoice in the Lord always.", 1)],
                     [doc(new("v/1", "Jesus wept.", 0), new("v/2", "Pray without ceasing.", 1))])
    assert outcome(result, pid("v/1")).score == 1.0
    assert [f.passage_id for f in result.failures] == [pid("v/2")]


def test_declared_text_replacement_passes_and_is_listed():
    result = R.remap([old(pid("s/1"), "s/1", text("a"), 0)],
                     [doc(new("s/1", text("b"), 0,
                              text_replaced="Percival translation replaces Tanner"))])
    assert result.failures == []
    [listed] = result.replacements
    assert (listed["anchor"], listed["reason"]) == ("s/1", "Percival translation replaces Tanner")
    assert listed["score"] < R.ANCHOR_STABILITY_THRESHOLD


def test_pieces_compared_as_one_unit():
    # A unit printed as three pieces is re-split at different points. Piece by piece, p2
    # keeps under half its text; joined, the unit is the same text.
    words = text("a", 120).split()
    cut = lambda i, j: " ".join(words[i:j])
    olds = [old(pid(f"s/1/p{k + 1}"), f"s/1/p{k + 1}", cut(i, j), k, reference="§1")
            for k, (i, j) in enumerate(((0, 40), (40, 80), (80, 120)))]
    build = [doc(*(new(f"s/1/p{k + 1}", cut(i, j), k, reference="§1")
                   for k, (i, j) in enumerate(((0, 60), (60, 100), (100, 120)))))]
    assert R.similarity(olds[1].content, build[0].passages[1].content) < 0.5   # p2 alone
    result = R.remap(olds, build)
    assert result.failures == []
    assert {r.outcome for r in result.rows} == {"same"}


def test_summa_parts_are_not_joined_into_one_unit():
    # Objection 1's second piece takes the running number Objection 2 had; a unit label
    # keeps the two objections apart, so the shift is caught.
    o1, o2 = text("obja", 30), text("objb", 30)
    olds = [old(pid("a/0"), "a/0", o1, 0, reference="A1", unit_label="Objection 1"),
            old(pid("a/1"), "a/1", o2, 1, reference="A1", unit_label="Objection 2")]
    build = [doc(new("a/0", " ".join(o1.split()[:15]), 0, reference="A1", unit_label="Objection 1"),
                 new("a/1", " ".join(o1.split()[15:]), 1, reference="A1", unit_label="Objection 1"),
                 new("a/2", o2, 2, reference="A1", unit_label="Objection 2"))]
    result = R.remap(olds, build)
    assert [f.passage_id for f in result.failures] == [pid("a/1")]


def test_anchor_string_change_with_frozen_id_is_same():
    a = text("a")
    result = R.remap([old("frozen-1", "chapter-ii-the-vanity-of-idols", a, 0)],
                     [doc(new("ii.ii", a, 0, pid="frozen-1"))])
    row = outcome(result, "frozen-1")
    assert (row.outcome, row.old_anchor, row.new_anchor) == (
        "same", "chapter-ii-the-vanity-of-idols", "ii.ii")
    assert result.failures == []


def test_live_anchor_reused_for_other_unit_fails():
    a, b = text("a"), text("b")
    # The live anchor "s/2" named unit B; the build gives that string to a new unit.
    result = R.remap([old("frozen-a", "s/1", a, 0), old("frozen-b", "s/2", b, 1)],
                     [doc(new("s/1", a, 0, pid="frozen-a"), new("s/3", b, 1, pid="frozen-b"),
                          new("s/2", text("c"), 2, pid="brand-new"))])
    assert [f.check_id for f in result.failures] == ["release.anchor_reuse:councils/frozen-b"]


def test_reused_retired_anchor_fails():
    entry = {"id": "rm-0002", "scope": "passage", "document_id": DOC, "anchor": "s/7",
             "passage_id": "retired-1", "reason": "duplicate"}
    result = R.remap([old("retired-1", "s/7", text("a"), 0)],
                     [doc(new("s/7", text("b"), 0, pid="another"))], R.Registry(removals=[entry]))
    assert outcome(result, "retired-1").outcome == "removed"
    assert [f.check_id for f in result.failures] == ["release.anchor_reuse:councils/retired-1"]


# --------------------------------------------------------------------------- chapters

def test_chapter_remap_majority_and_reading_progress_anchors():
    a, b, c, d = (text(s) for s in "abcd")
    olds = [old(pid("q1/0"), "q1/0", a, 0, chapter_key="q1"),
            old("old-b", "q1/1", b, 1, chapter_key="q1"),
            old("old-c", "q1/2", c, 2, chapter_key="q1"),
            old("old-d", "q2/0", d, 3, chapter_key="q2")]
    # q1's first passage keeps its ID in q1; two of its passages moved to q1b; q2 is gone.
    build = [doc(new("q1/0", a, 0, chapter_key="q1"), new("q1b/0", b, 1, chapter_key="q1b"),
                 new("q1b/1", c, 2, chapter_key="q1b"))]
    references = {"documents": {DOC: {"reading_progress": 4, "positions": [
        {"chapter_key": "q1", "anchor": "q1/1", "rows": 2},
        {"chapter_key": "q1", "anchor": None, "rows": 1},
        {"chapter_key": "q2", "anchor": "q2/0", "rows": 1}]}}}
    result = R.remap(olds, build)
    chapters = {c["old_chapter_key"]: c for c in R.chapter_remap(olds, result.rows, references)}
    assert (chapters["q1"]["new_chapter_key"], chapters["q1"]["share"]) == ("q1b", round(2 / 3, 4))
    assert chapters["q1"]["reading_progress_anchors"] == ["q1/1"]
    assert chapters["q1"]["reading_progress_rows"] == 3
    assert (chapters["q2"]["new_chapter_key"], chapters["q2"]["share"]) == (None, 0.0)
    json.dumps(list(chapters.values()))       # serializable as chapter_remap.jsonl


def test_unit_key_strips_piece_numbers_only():
    p = lambda anchor, label=None: old("x", anchor, "", 0, reference="R", unit_label=label)
    assert R.unit_key(p("s/1/p2"))[3] == R.unit_key(p("s/1/p1"))[3] == "s/1"
    assert R.unit_key(p("ccc/185-p2"))[3] == "ccc/185"
    assert R.unit_key(p("genesis/1/1-2"))[3] == "genesis/1/1"
    # The Summa's running number inside one labelled part is a piece number...
    assert R.unit_key(p("summa/q1/a1/3", "Objection 2")) == R.unit_key(p("summa/q1/a1/4", "Objection 2"))
    # ...but unlabelled numbered paragraphs sharing a reference are separate units.
    assert R.unit_key(p("council/sec-4/3")) != R.unit_key(p("council/sec-4/4"))


def test_unlabelled_paragraphs_sharing_a_reference_are_checked_one_by_one():
    a, b, c = text("a"), text("b"), text("c")
    olds = [old(pid(f"sec-4/{i}"), f"sec-4/{i}", t, i, reference="Letter")
            for i, t in enumerate((a, b, c))]
    build = [doc(*(new(f"sec-4/{i}", t, i, reference="Letter")
                   for i, t in enumerate((a, text("replaced"), c))))]
    assert [f.passage_id for f in R.remap(olds, build).failures] == [pid("sec-4/1")]


@pytest.mark.parametrize("a,b,expected", [("", "", 1.0), ("x", "", 0.0),
                                         ("Same text.", "same  TEXT", 1.0)])
def test_similarity_edges(a, b, expected):
    assert R.similarity(a, b) == expected


# --------------------------------------------------------------------------- review findings

def test_duplicate_build_id_fails():
    a = text("a")
    result = R.remap([old(pid("a"), "a", a, 0)], [doc(new("a", a, 0), new("a", text("z"), 1))])
    assert [f.check_id for f in result.failures] == [f"release.duplicate_id:councils/{pid('a')}"]


def test_split_bridges_a_piece_too_short_for_shingles():
    words = text("a", 60).split()
    result = R.remap([old("old-a", "x/1", " ".join(words), 0)],
                     [doc(new("s/1", " ".join(words[:28]), 0), new("s/2", " ".join(words[28:32]), 1),
                          new("s/3", " ".join(words[32:]), 2))])
    row = outcome(result, "old-a")
    assert row.outcome == "split" and set(row.new_ids) == {pid("s/1"), pid("s/2"), pid("s/3")}
    assert result.failures == []


def test_removal_entry_with_an_id_does_not_explain_another_passage_at_its_anchor():
    entry = {"id": "rm", "scope": "passage", "document_id": DOC, "anchor": "x",
             "passage_id": "P-retired"}
    result = R.remap([old("P-other", "x", text("a"), 0)], [doc(new("s/1", text("z"), 0))],
                     R.Registry(removals=[entry]))
    assert outcome(result, "P-other").removal is None
    assert [f.check for f in result.failures] == ["removed"]


def test_null_position_sorts_last_without_crashing():
    a, b = text("a"), text("b")
    result = R.remap([old(pid("s/1"), "s/1", a, None), old(pid("s/2"), "s/2", b, 0)],
                     [doc(new("s/1", a, None), new("s/2", b, 0))])
    assert [r.old_id for r in result.rows] == [pid("s/2"), pid("s/1")]


def test_text_inside_a_split_piece_is_merged_not_moved():
    a, b = text("a", 200), text("b")
    words = a.split()
    # A splits into s/1 and s/2; B's text is also inside s/2.
    result = R.remap([old("old-a", "x/1", a, 0), old("old-b", "x/2", b, 1)],
                     [doc(new("s/1", " ".join(words[:100]), 0),
                          new("s/2", " ".join(words[100:]) + " " + b, 1))])
    assert outcome(result, "old-a").outcome == "split"
    assert outcome(result, "old-b").outcome == "merged"


def test_text_landing_on_a_drifted_id_is_moved_not_merged():
    # Live a/1 = X, a/2 = Y; the build drops X, so a/1 now holds Y. a/1 keeps its ID but
    # none of its text, so a/2's text is the only old text there: moved, not merged.
    p, x, y = text("p"), text("x"), text("y")
    result = R.remap([old(pid("a/0"), "a/0", p, 0), old(pid("a/1"), "a/1", x, 1),
                      old(pid("a/2"), "a/2", y, 2)],
                     [doc(new("a/0", p, 0), new("a/1", y, 1))])
    assert outcome(result, pid("a/2")).outcome == "moved"
    assert [f.check for f in result.failures] == ["stability"]


def test_removal_entry_for_a_built_passage_or_document_fails():
    a = text("a")
    entries = [{"id": "rm-1", "scope": "passage", "document_id": DOC, "anchor": "z",
                "passage_id": pid("s/1")},
               {"id": "rm-2", "scope": "document", "document_id": DOC, "anchor": None}]
    result = R.remap([old(pid("s/1"), "s/1", a, 0)], [doc(new("s/1", a, 0))],
                     R.Registry(removals=entries))
    assert [f.check for f in result.failures] == ["bad_removal", "bad_removal"]


def test_split_redirect_primary_is_first_by_build_position():
    a = text("a")
    rows = [{"document_id": DOC, "old_passage_id": "o", "new_passage_id": pid(f"s/{i}"),
             "kind": "split"} for i in (2, 1)]
    result = R.remap([old("o", "x", a, 0)], [doc(new("s/1", a, 0), new("s/2", text("b"), 1))],
                     R.Registry(redirects=rows))
    assert outcome(result, "o").new_ids == (pid("s/1"), pid("s/2"))
