"""Unit tests for the 0.1a source checks (datapipeline/checks/). They run in CI: every
fixture is written here, and no vendored source is read."""
import json

import pytest

from checks import coverage as C
from checks import report
from checks import sequence as Q
from checks import source_text as S
from model import Document, Passage


def _passage(content, reference="", anchor="a", unit_label=None, position=0, chapter_key="c"):
    return Passage(content=content, reference=reference, anchor=anchor, chapter_key=chapter_key,
                   chapter_label="C", position=position, unit_label=unit_label)


def _doc(passages, title="Doc", collection="catechism", metadata=None):
    return Document(id=f"id-{title}", collection=collection, title=title,
                    metadata=metadata, passages=passages)


# --------------------------------------------------------------------------- normalize

def test_normalize_folds_case_quotes_markers_and_whitespace():
    raw = "“Grace”  and\n‘peace’[12] to you{{v:3}} [Page 45] all."
    assert C.normalize(raw) == "\"grace\" and 'peace' to you all."


def test_normalize_keeps_summa_references():
    assert C.normalize("as stated above (Q[1], A[2]; AA[3])") == "as stated above (q[1], a[2]; aa[3])"


def test_normalize_applies_nfkc():
    assert C.normalize("ﬁnal …") == "final ..."


def test_match_key_ignores_spacing_and_punctuation():
    assert C.match_key(C.normalize("Lumen Gentium , which. . .")) == \
        C.match_key(C.normalize("Lumen Gentium, which …"))


# --------------------------------------------------------------------------- sentences

def test_split_sentences_at_terminal_punctuation_before_a_capital():
    text = "The first sentence ends here. The second one? Yes! but not here."
    assert C.split_sentences(text) == ["the first sentence ends here.", "the second one?",
                                       "yes! but not here."]


def test_split_sentences_at_segment_breaks_and_blank_lines():
    text = f"Before the note{S.SEGMENT_BREAK} after the note\n\nNext paragraph"
    assert C.split_sentences(text) == ["before the note", "after the note", "next paragraph"]


# --------------------------------------------------------------------------- coverage

BODY = ("This is the first sentence of the source paragraph. "
        "This second sentence never reached any passage at all.")


def test_covered_and_uncovered_sentence():
    units = [S.SourceUnit("ccc.json", "1", BODY, "body"),
             S.SourceUnit("ccc.json", "n1", "A note sentence that leaked into a passage.", "note")]
    doc = _doc([_passage("This is the first sentence of the source paragraph. "
                         "A note sentence that leaked into a passage.")])
    result = C.coverage("catechism", [doc], units)
    f = result.files["ccc.json"]
    first, second = (len(s) for s in C.split_sentences(BODY))
    assert (f.body_chars, f.covered_chars) == (first + second, first)
    assert f.uncovered == [("1", "this second sentence never reached any passage at all.")]
    assert f.note_leakage == 1
    assert result.documents[doc.id].covered_chars == first


def test_short_sentences_are_counted_apart():
    units = [S.SourceUnit("ccc.json", "1", "Too short. Amen.", "body")]
    f = C.coverage("catechism", [_doc([])], units).files["ccc.json"]
    assert (f.body_chars, f.short_chars, f.pct) == (0, len("too short.") + len("amen."), 100.0)


def test_unit_label_counts_as_passage_text():
    units = [S.SourceUnit("summa.xml", "FP_Q1_A1",
                          "Objection 1: It seems that this sentence is long enough.", "body")]
    doc = _doc([_passage("It seems that this sentence is long enough.",
                         unit_label="Objection 1")], collection="summa")
    assert C.coverage("summa", [doc], units).files["summa.xml"].pct == 100.0


def test_large_text_uses_the_sampled_index():
    filler = " ".join(f"Sentence number {i} of the filler text." for i in range(40_000))
    needle = "The needle sentence sits deep inside a very large passage text"
    doc = _doc([_passage(filler + " " + needle + " and continues after it.")])
    index = C._PassageText([doc])
    assert len(index.text) > index._INDEX_FROM
    assert index.find(C.match_key(C.normalize(needle))) == 0
    assert index.find(C.match_key(C.normalize("A sentence that is nowhere in the text"))) is None


def test_unplaceable_document_raises():
    # Two Catechism documents: neither a source_file, a manifest URL nor the single
    # document of the collection places them.
    with pytest.raises(ValueError):
        C.documents_by_file("catechism", [_doc([], "A"), _doc([], "B")], ["ccc.json"])


# --------------------------------------------------------------------------- extractors

HTML = """<html><head><meta charset="utf-8"></head><body><div class="entry-content">
<p><a href="#">EN</a> - <a href="#">FR</a></p>
<h2>ENCYCLICAL LETTER</h2>
<p>1. The first section opens here with enough words to measure.</p>
<p>It continues in a second paragraph with no number of its own.</p>
<ul><li>A list item inside the first section that holds body text.</li></ul>
<p>2. The second section follows<a href="#n1">[1]</a> and ends.</p>
<p>REFERENCES:</p>
<p>1. Cf. a citation that belongs to the notes.</p>
<p>Copyright © Somebody</p>
</div></body></html>"""


def test_html_units_regions_and_numbers(tmp_path):
    path = tmp_path / "doc.html"
    path.write_text(HTML, encoding="utf-8")
    units = S.html_units(str(path))
    regions = [(u.unit_id, u.region) for u in units]
    assert regions == [(None, "toc"), (None, "heading"), ("1", "body"), (None, "body"),
                       (None, "body"), ("2", "body"), (None, "heading"), ("1", "note"),
                       (None, "apparatus")]      # the site footer, even inside the notes
    first = units[2]
    assert first.text.startswith("The first section")    # the number is the id, not text


def test_html_notes_after_rule_with_bracketed_first_note(tmp_path):
    path = tmp_path / "doc.html"
    path.write_text('<div class="documento"><p>Body text that is long enough here.</p>'
                    '<hr/><p>[1] A note.</p><p>[2] Another note.</p></div>', encoding="utf-8")
    assert [u.region for u in S.html_units(str(path))] == ["body", "note", "note"]


THML = """<?xml version="1.0"?>
<ThML><ThML.head><title>T</title></ThML.head><ThML.body>
<div1 id="i" title="Contents"><p>Chapter One ........ 1</p></div1>
<div1 id="ii" title="A Work">
  <h2>A Work</h2>
  <p>Greeting before the chapters, long enough to measure here.</p>
  <div2 id="ii.i" title="Chapter I">
    <p>Body text<note n="1"><p>Note text inside the paragraph.</p></note> resumes &amp;gt; here.</p>
  </div2>
</div1>
</ThML.body></ThML>"""


def test_thml_units(tmp_path):
    path = tmp_path / "vol.xml"
    path.write_text(THML, encoding="utf-8")
    units = S.thml_units(str(path))
    assert [(u.unit_id, u.region) for u in units] == [
        ("i", "toc"), ("ii", "heading"), ("ii", "body"), ("ii.i", "body"), ("ii.i", "note")]
    body = units[3].text
    assert S.SEGMENT_BREAK in body and "Note text" not in body and body.endswith("> here.")


USFM = r"""\id DAG test
\h Daniel (Greek)
\toc2 Daniel (Greek)
\ip An editor's introduction.
\c 13
\s1 Susanna
\p
\v 1 \w There|strong="H1"\w* was a man\f + \fr 13:1 \ft A footnote.\f* in Babylon.
\q1 continued on a poetry line.
\v 2 He took a wife.
"""


def test_usfm_units(tmp_path):
    path = tmp_path / "66-DAG.usfm"
    path.write_text(USFM, encoding="utf-8")
    units = S.usfm_units(str(path))
    by_region = {}
    for u in units:
        by_region.setdefault(u.region, []).append(u)
    verses = [(u.unit_id, " ".join(u.text.replace(S.SEGMENT_BREAK, " ").split()))
              for u in by_region["body"]]
    assert verses == [("DAG/13/1", "There was a man in Babylon. continued on a poetry line."),
                      ("DAG/13/2", "He took a wife.")]
    assert [" ".join(u.text.split()) for u in by_region["note"]] == ["+ 13:1 A footnote."]
    assert "Susanna" in " ".join(u.text for u in by_region["heading"])


def test_ccc_units(tmp_path):
    data = {"page_nodes": {"toc-1": {"paragraphs": [
        {"elements": [{"type": "text", "text": "ARTICLE 1"}]},
        {"elements": [{"type": "ref-ccc", "ref_number": 1},
                      {"type": "text", "text": "The first paragraph"}, {"type": "ref", "number": 1}]},
        {"attrs": {"indent": True}, "elements": [{"type": "text", "text": "an indented quotation"}]},
        {"elements": [{"type": "text", "text": "A Heading Between"}]},
        {"elements": [{"type": "ref-ccc", "ref_number": 2}, {"type": "text", "text": "Second."}]},
    ], "footnotes": {"1": {"refs": [{"text": "A footnote."}]}}}}}
    path = tmp_path / "ccc.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    units = S.ccc_units(str(path))
    assert [(u.unit_id, u.region) for u in units] == [
        (None, "heading"), ("1", "body"), (None, "heading"), ("2", "body"), ("n1", "note")]
    assert units[1].text == "The first paragraph\nan indented quotation"


# --------------------------------------------------------------------------- sequence

def _units(*numbers):
    return [S.SourceUnit("d.html", str(n), f"Text of section {n}.", "body") for n in numbers]


def test_section_numbers_skip_list_items_and_restarts():
    units = _units(1, 2, 1, 2, 3, 4, 9, 10, 1)
    assert Q.source_section_numbers(units) == [1, 2, 3, 4, 9, 10]


def test_numbered_paragraphs_gap_duplicate_and_out_of_range():
    doc = _doc([_passage("x", "D, §1", "d/1"), _passage("x", "D, §2", "d/2/p1"),
                _passage("x", "D, §2", "d/2/p2"),                  # pieces of one unit
                _passage("x", "D, §4", "d/4"), _passage("x", "D, §4", "d/4-2"),
                _passage("x", "D, §9", "d/9-2")])
    result = Q.numbered_paragraphs(doc, _units(1, 2, 3, 4))
    assert result.missing == ["3"]
    assert result.duplicated == ["4"]
    assert result.out_of_range == ["9"]


def test_canons_missing_glued_and_cross_reference():
    passages = [_passage("Text of canon one.", anchor="can/1"),
                _passage("Text of two.Can. 3 §1. Glued text. See can. 1 and Can. 1, §2.",
                         anchor="can/2")]
    result = Q.canons([_doc(passages)])
    assert result.missing[:2] == ["3", "4"] and "1" not in result.missing
    assert result.duplicated == ["3"]


def test_ccc_paragraph_ranges_and_pieces():
    passages = [_passage("x", "CCC §1–3", "ccc/1-p1"), _passage("x", "CCC §1–3", "ccc/1-p2"),
                _passage("x", "CCC §3, §5 (part)", "ccc/3")]
    result = Q.ccc_paragraphs([_doc(passages)])
    assert result.missing[:2] == ["4", "6"]
    assert result.duplicated == ["3"]


def test_bible_verses_from_references():
    units = [S.SourceUnit("x.usfm", f"DAG/{c}/{v}", "text", "body")
             for c, v in [(12, 1), (12, 2), (13, 1), (13, 2), (14, 1)]]
    doc = _doc([_passage("x", "Daniel 12:1–2", "daniel/12/1"),
                _passage("x", "Daniel 12:2–13:1", "daniel/12/2")], title="Daniel",
               collection="bible")
    import checks.sequence as seq_module

    original = seq_module.documents_by_file
    seq_module.documents_by_file = lambda *a, **k: {"x.usfm": [doc]}
    try:
        result = Q.bible_verses([doc], units)
    finally:
        seq_module.documents_by_file = original
    assert result.missing == ["DAG/13/2", "DAG/14/1"]
    assert result.duplicated == ["DAG/12/2"]


def test_summa_articles_match_on_question_number_and_article_title():
    articles = [("FP_Q1_A1", "FIRST PART", "Question. 1 - THE NATURE [*Or, Kind] (ONE)",
                 "Article. 1 - Whether it is?"),
                ("FP_Q71", "FIRST PART", "Question. 71 - ON THE FIFTH DAY (ONE ARTICLE)", "")]
    doc = _doc([_passage("x", "Summa Theologiae, First Part, Question 1 - The Nature (ONE), "
                              "Article 1 - Whether it is?")], collection="summa")
    assert Q.summa_articles([doc], [], articles).missing == ["FP_Q71"]


SUMMA_ARTICLES = [
    ("FP_Q2_A3", "FIRST PART", "Question. 2 - THE EXISTENCE OF GOD", "Article. 3 - Whether God exists?"),
    ("FP_Q8_A1", "FIRST PART", "Question. 8 - THE EXISTENCE OF GOD IN THINGS",
     "Article. 1 - Whether God exists in all things?"),
]


def _summa_ref(q, article):
    return f"Summa Theologiae, First Part, Question {q} - Topic, {article}"


def test_summa_article_pieces_count_once_and_longest_title_wins():
    # Objection, answer and a split piece share the article's chapter_key; the Q8 article's
    # title contains the Q2 title, but the question number keeps them apart.
    a3, a1 = _summa_ref(2, "Article 3 - Whether God exists?"), \
        _summa_ref(8, "Article 1 - Whether God exists in all things?")
    doc = _doc([_passage("x", a3, "q2/a3/0", "Objection 1", chapter_key="q2/a3"),
                _passage("x", a3, "q2/a3/1", "I answer that", chapter_key="q2/a3"),
                _passage("x", a3, "q2/a3/2", "I answer that", chapter_key="q2/a3"),
                _passage("x", a1, "q8/a1/0", "Objection 1", chapter_key="q8/a1")],
               collection="summa")
    assert Q.summa_articles([doc], [], SUMMA_ARTICLES).ok


def test_summa_article_built_twice_and_invented_article():
    a3 = _summa_ref(2, "Article 3 - Whether God exists?")
    doc = _doc([_passage("x", a3, "q2/a3/0", chapter_key="q2/a3"),
                _passage("x", a3, "q2/a3--2/0", chapter_key="q2/a3--2"),
                _passage("x", _summa_ref(8, "Article 1 - Whether God exists in all things?"),
                         "q8/a1/0", chapter_key="q8/a1"),
                _passage("x", _summa_ref(9999, "Article 1 - Whether this was invented?"),
                         "q9999/a1/0", chapter_key="q9999/a1")], collection="summa")
    result = Q.summa_articles([doc], [], SUMMA_ARTICLES)
    assert (result.missing, result.duplicated, result.out_of_range) == (
        [], ["FP_Q2_A3"], ["q9999/a1"])


def test_thml_chapter_needs_half_its_characters():
    long_text = " ".join(f"Sentence number {i} of a long dropped work." for i in range(20))
    units = [S.SourceUnit("v.xml", "ii.i", long_text, "body"),
             S.SourceUnit("v.xml", "ii.ii", "One sentence of this chapter does reach a passage.",
                          "body"),
             S.SourceUnit("v.xml", "ii.iii", "Too short.", "body")]
    # A single shared sentence is not enough to call a long div represented.
    doc = _doc([_passage("Sentence number 3 of a long dropped work. "
                         "One sentence of this chapter does reach a passage.")])
    assert Q.thml_chapters([doc], units).missing == ["ii.i"]


def test_check_ids_granularity():
    result = Q.SequenceResult(missing=["DAG/13/1", "DAG/13/2"], duplicated=[], out_of_range=[])
    assert Q.check_ids("bible_verses", "bible", result) == {
        "sequence.bible_verses.missing:DAG/13": ["DAG/13/1", "DAG/13/2"]}
    assert list(Q.check_ids("canons", "canon-law", Q.SequenceResult(missing=["266"]))) == [
        "sequence.canons.missing:266"]
    assert list(Q.check_ids("thml_chapters", "church-fathers/v.xml",
                            Q.SequenceResult(missing=["ii.i"]))) == [
        "sequence.thml_chapters.missing:church-fathers/v.xml#ii.i"]


# --------------------------------------------------------------------------- bookkeeping

KNOWN = {"sequence.canons.missing:266": {"fixed_by": "1.5a", "description": "d"},
         "coverage.councils.vat2-nostra-aetate.html": {"fixed_by": "1.1", "description": "d"}}


def test_known_defect_that_now_passes_is_reported_fixed():
    assert report.known_defect_status("sequence.canons.missing:266", set(), KNOWN) == \
        "fixed, remove entry"


def test_known_and_unexpected_failures():
    failing = {"sequence.canons.missing:266", "sequence.canons.missing:267"}
    assert report.known_defect_status("sequence.canons.missing:266", failing, KNOWN) == \
        "known defect, fixed by 1.5a"
    assert report.known_defect_status("sequence.canons.missing:267", failing, KNOWN) == \
        "unexpected failure"
    assert report.known_defect_status("sequence.canons.missing:268", failing, KNOWN) == "pass"


def test_coverage_regression_and_expected_direction_down():
    cov = C.CoverageResult("councils", {
        "a.html": C.FileCoverage("a.html", [], body_chars=100, covered_chars=90),
        "b.html": C.FileCoverage("b.html", [], body_chars=100, covered_chars=50)}, {})
    run = report.RunResult(["councils"], {"councils": cov})
    baseline = {"files": {"councils/a.html": {"pct": 90.4}, "councils/b.html": {"pct": 80.0}}}
    assert report.coverage_regressions(run, baseline, {}) == ["councils/b.html: 50.0 < baseline 80.0"]
    down = {"coverage.councils.b.html": {"fixed_by": "1.8a", "description": "d",
                                         "expected_direction": "down"}}
    assert report.coverage_regressions(run, baseline, down) == []


def test_known_defects_file_is_well_formed():
    known = report.load_known()
    allowed = {"fixed_by", "description", "expected_direction", "units"}
    for check_id, entry in known.items():
        assert set(entry) <= allowed and entry["fixed_by"] and entry["description"], check_id
        assert entry.get("expected_direction", "down") == "down", check_id
        assert report.check_scope(check_id) in report.COLLECTIONS, check_id
        # Grouped check ids list their units, so a new unit is not hidden by the entry.
        grouped = check_id.startswith(("sequence.bible_verses.", "sequence.numbered_paragraphs."))
        assert ("units" in entry) == grouped, check_id


def test_editorial_div_is_apparatus_and_flagged_if_published(tmp_path, monkeypatch):
    listing = tmp_path / "editorial_divs.json"
    listing.write_text(json.dumps([{"collection": "church-fathers", "file": "vol.xml",
                                    "div": "ii.i", "title": "Chapter I", "item": "1.8a"}]))
    monkeypatch.setattr(S, "EDITORIAL_DIVS_PATH", str(listing))
    monkeypatch.setattr(S, "editorial_divs",
                        lambda f, path=str(listing): {"ii.i"} if f == "vol.xml" else set())
    path = tmp_path / "vol.xml"
    path.write_text(THML, encoding="utf-8")
    units = S.thml_units(str(path))
    assert [u.region for u in units if u.unit_id == "ii.i"] == ["apparatus", "note"]
    # An editorial div that reaches a passage is reported; a body div that does not is missing.
    editorial_text = next(u.text for u in units if u.unit_id == "ii.i" and u.region == "apparatus")
    doc = _doc([_passage(editorial_text.replace(S.SEGMENT_BREAK, " "))])
    long_editorial = [S.SourceUnit("vol.xml", "ed", "An editor wrote this long sentence here. " * 4,
                                   "apparatus")]
    published = _doc([_passage("An editor wrote this long sentence here. " * 4)])
    assert Q.thml_chapters([published], long_editorial, {"ed"}).out_of_range == ["ed"]
    assert Q.thml_chapters([doc], long_editorial, {"ed"}).out_of_range == []


def test_coverage_entry_reported_fixed_at_threshold():
    cov = C.CoverageResult("councils", {
        "a.html": C.FileCoverage("a.html", [], body_chars=100, covered_chars=96),
        "b.html": C.FileCoverage("b.html", [], body_chars=100, covered_chars=50)}, {})
    run = report.RunResult(["councils"], {"councils": cov})
    failing = report.coverage_failing(run)
    known = {"coverage.councils.a.html": {"fixed_by": "1.1", "description": "d"},
             "coverage.councils.b.html": {"fixed_by": "1.1", "description": "d"}}
    assert report.known_defect_status("coverage.councils.a.html", failing, known) == \
        "fixed, remove entry"
    assert report.known_defect_status("coverage.councils.b.html", failing, known) == \
        "known defect, fixed by 1.1"


def test_editorial_divs_file_is_well_formed():
    with open(S.EDITORIAL_DIVS_PATH, encoding="utf-8") as f:
        rows = json.load(f)
    keys = [(r["collection"], r["file"], r["div"]) for r in rows]
    assert len(keys) == len(set(keys))
    for r in rows:
        assert set(r) == {"collection", "file", "div", "title", "item"}
        assert r["item"] in ("1.8a", "1.8b", "1.9"), r


def test_thml_verse_lines_are_body(tmp_path):
    path = tmp_path / "vol.xml"
    path.write_text("""<?xml version="1.0"?><ThML><ThML.body><div1 id="i" title="A Work">
<p>A paragraph before the hymn, long enough to measure.</p>
<verse><l>To thee a garland I present,</l><l>Woven of words</l></verse>
</div1></ThML.body></ThML>""", encoding="utf-8")
    units = S.thml_units(str(path))
    assert [u.region for u in units] == ["body", "body"]
    assert " ".join(units[1].text.split()) == "To thee a garland I present, Woven of words"


def test_summa_notes_are_notes_and_references_are_spelled_out(tmp_path):
    path = tmp_path / "summa.xml"
    path.write_text("""<?xml version="1.0"?><ThML><ThML.body><div1 id="FS" title="Part">
<div4 id="FS_Q1_A1" title="Article 1"><p>As Augustine says (De Lib. Arb. ii, 19 [*Cf. FP, Q[12]]), it is
so, as stated above (FS, Q[24], A[3], OBJ[2]; SS, QQ[1]-[4]).</p></div4>
</div1></ThML.body></ThML>""", encoding="utf-8")
    units = S.summa_units(str(path))
    assert [u.region for u in units] == ["note", "body"]
    assert units[0].text == "[*Cf. FP, Q[12]]"
    assert " ".join(units[1].text.split()) == (
        "As Augustine says (De Lib. Arb. ii, 19), it is so, as stated above (First Part of "
        "the Second Part, Q. 24, A. 3, Objection 2; Second Part of the Second Part, Qq. 1–4).")


def test_sentence_without_letters_is_not_measured():
    units = [S.SourceUnit("ccc.json", "1", "* * * * * * * * * * * * * * * * * *", "body")]
    f = C.coverage("catechism", [_doc([_passage("Anything at all.")])], units).files["ccc.json"]
    assert (f.body_chars, f.covered_chars) == (0, 0) and f.short_chars > 0


def test_stale_baseline_after_a_fix_or_a_source_change():
    cov = C.CoverageResult("councils", {
        "a.html": C.FileCoverage("a.html", [], body_chars=100, covered_chars=90),
        "b.html": C.FileCoverage("b.html", [], body_chars=100, covered_chars=95),
        "c.html": C.FileCoverage("c.html", [], body_chars=200, covered_chars=100),
        "d.html": C.FileCoverage("d.html", [], body_chars=100, covered_chars=100)}, {})
    run = report.RunResult(["councils"], {"councils": cov})
    baseline = {"files": {"councils/a.html": {"pct": 90.0, "body_chars": 100},
                          "councils/b.html": {"pct": 40.0, "body_chars": 100},
                          "councils/c.html": {"pct": 50.0, "body_chars": 100}}}
    assert report.stale_baseline(run, baseline) == [
        "councils/b.html: 95.0 > baseline 40.0",
        "councils/c.html: body 200 characters, baseline 100",
        "councils/d.html: not in the baseline"]


def test_grown_defect_lists_only_new_units():
    known = {"sequence.numbered_paragraphs.missing:councils/a.html":
             {"fixed_by": "1.1", "description": "d", "units": ["3", "4"]},
             "sequence.canons.missing:266": {"fixed_by": "1.5a", "description": "d"}}
    failing = {"sequence.numbered_paragraphs.missing:councils/a.html": ["3", "7"],
               "sequence.canons.missing:266": ["266"]}
    assert report.grown_defects(failing, known) == {
        "sequence.numbered_paragraphs.missing:councils/a.html": ["7"]}


def _coverage_run(collection, name, covered, documents=None):
    cov = C.CoverageResult(collection, {
        name: C.FileCoverage(name, [], body_chars=100, covered_chars=covered)}, documents or {})
    return report.RunResult([collection], {collection: cov})


def test_write_baseline_for_one_collection_keeps_the_others(tmp_path, monkeypatch):
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({
        "measured_on": "master abc1234",
        "files": {"bible/a.usfm": {"body_chars": 100, "covered_chars": 90, "pct": 90.0},
                  "catechism/ccc.json": {"body_chars": 100, "covered_chars": 50, "pct": 50.0}},
        "documents": {"d-bible": {"collection": "bible", "source_file": "a.usfm",
                                  "body_chars": 100, "covered_chars": 90, "pct": 90.0},
                      "d-ccc": {"collection": "catechism", "source_file": "ccc.json",
                                "body_chars": 100, "covered_chars": 50, "pct": 50.0}}}))
    run = _coverage_run("catechism", "ccc.json", 97, {
        "d-ccc": C.DocumentCoverage("d-ccc", "CCC", "ccc.json", body_chars=100, covered_chars=97)})
    monkeypatch.setattr(report, "run", lambda collections: run)
    monkeypatch.setattr(report, "_git_head", lambda: "feat/x def5678")
    assert report.main(["--collection", "catechism", "--baseline", str(path),
                        "--write-baseline", str(path), "--out", str(tmp_path / "out")]) == 0
    written = json.loads(path.read_text())
    assert written["measured_on"] == {"bible": "master abc1234", "catechism": "feat/x def5678"}
    assert written["files"]["bible/a.usfm"]["pct"] == 90.0
    assert written["files"]["catechism/ccc.json"]["pct"] == 97.0
    assert set(written["documents"]) == {"d-bible", "d-ccc"}
    assert written["documents"]["d-ccc"]["covered_chars"] == 97


def test_one_editorial_sentence_in_a_passage_is_a_leak():
    editorial = [S.SourceUnit("v.xml", "ed", "The editor wrote this first long sentence here. "
                              "The editor added a second long sentence too. "
                              "The editor closed with a third long sentence.", "apparatus"),
                 S.SourceUnit("v.xml", "ed.i", "A nested editor's paragraph of decent length.",
                              "apparatus")]
    leaked = _doc([_passage("The author's text. The editor added a second long sentence too.")])
    assert Q.thml_chapters([leaked], editorial, {"ed"}).out_of_range == ["ed"]
    nested = _doc([_passage("A nested editor's paragraph of decent length.")])
    assert Q.thml_chapters([nested], editorial, {"ed"}).out_of_range == ["ed"]


def test_editorial_sentence_the_file_also_holds_elsewhere_is_not_a_leak():
    units = [S.SourceUnit("v.xml", "ed", "I believe in God the Father Almighty, maker of all.",
                          "apparatus"),
             S.SourceUnit("v.xml", "ii.i", "He taught them to say: I believe in God the Father "
                          "Almighty, maker of all.", "body"),
             S.SourceUnit("v.xml", "ed", "Boethius's first wife was Elpis, daughter of Festus.",
                          "apparatus"),
             S.SourceUnit("v.xml", "iii", "Boethius's first wife was Elpis, daughter of Festus.",
                          "note")]
    doc = _doc([_passage("He taught them to say: I believe in God the Father Almighty, maker of "
                         "all. Boethius's first wife was Elpis, daughter of Festus.")])
    assert Q.thml_chapters([doc], units, {"ed"}).out_of_range == []


def test_numbered_paragraph_invented_inside_a_source_gap():
    doc = _doc([_passage("x", f"D, §{n}", f"d/{n}") for n in (1, 2, 3, 4)])
    result = Q.numbered_paragraphs(doc, _units(1, 2, 4))
    assert (result.missing, result.duplicated, result.out_of_range) == ([], [], ["3"])


def test_paragraph_number_without_a_space_after_it(tmp_path):
    path = tmp_path / "doc.html"
    path.write_text('<div class="documento"><p>131.Later, his director helped him further.</p>'
                    '<p>1.5 metres is not a paragraph number at all here.</p></div>',
                    encoding="utf-8")
    units = S.html_units(str(path))
    assert [(u.unit_id, u.text) for u in units] == [
        ("131", "Later, his director helped him further."),
        (None, "1.5 metres is not a paragraph number at all here.")]
