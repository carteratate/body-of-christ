"""Rule G for the ANF volumes (corpus-cleanup 1.8a): `ingest/editorial.py`, its use in the
Church Fathers adapter, and the removal registry entries generated from a build."""
import os

import pytest

import identity
import registry
from ingest import editorial
from ingest.church_fathers import build_documents
from ingest.common import direct_blocks_text
from scripts import editorial_removals

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "thml_editorial.xml")
FIXTURE_DIR = os.path.dirname(FIXTURE)
BANQUET_KEY = "church-fathers/thml_editorial.xml#ii.ii"
_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "church-fathers")


@pytest.fixture
def built(monkeypatch):
    """The fixture volume built with rule G, the Banquet stand-in taking its chapter
    titles into labels; the documents and what each chapter lost."""
    monkeypatch.setattr(editorial, "CHAPTER_TITLE_WORKS",
                        editorial.CHAPTER_TITLE_WORKS | {BANQUET_KEY})
    with editorial.recording() as log:
        documents = build_documents(FIXTURE)
    return documents, log


def _letter(documents):
    letters = next(d for d in documents if d.title == "The Epistles of Testius")
    return letters, next(p for p in letters.passages if p.chapter_key == "ii.i.i")


def test_elucidation_divs_skipped_at_any_depth(built):
    documents, log = built
    letters, _ = _letter(documents)
    assert [p.chapter_key for p in letters.passages] == ["ii.i.i"]
    assert ("church-fathers/thml_editorial.xml#ii.i", "ii.i.ii", "Elucidations.") in log
    assert editorial.editorial_div("Elucidations.")
    assert editorial.editorial_div("Note by the American Editor")
    assert editorial.editorial_div("Translator’s Biographical Notice.")
    assert not editorial.editorial_div("Contents.", "iii.iii.i.i", "third-century-2.xml")
    assert editorial.editorial_div("Contents.", "v.ii", "confessions.xml")


def test_translator_credit_line_dropped(built):
    _, letter = _letter(built[0])
    assert "Translated by" not in letter.content
    assert editorial.strip_editorial_lines(
        ["[Translated by the Rev. S. Thelwall.]", "We do not indeed forbid the union."]
    ) == ["We do not indeed forbid the union."]


def test_translation_brackets_kept(built):
    _, letter = _letter(built[0])
    assert "the Lord [of God] that it has come" in letter.content


def test_editor_bracket_removed(built):
    _, letter = _letter(built[0])
    assert "Elucidation" not in letter.content
    assert "the antiquity of error and nothing more" in letter.content
    assert editorial.strip_editor_brackets("error [See Elucidation VI.] and more", None) \
        == "error and more"


def test_reviewed_bracket_hash_removed(monkeypatch):
    span = "[This concluding chapter is of itself a masterpiece.]"
    monkeypatch.setattr(editorial, "_reviewed", frozenset({editorial.span_sha1(span)}))
    assert editorial.strip_editor_brackets(f"to each. {span} End.") == "to each. End."
    assert editorial.strip_editor_brackets("to each [weal] alike.") == "to each [weal] alike."


def test_argument_paragraph_dropped(built):
    _, letter = _letter(built[0])
    assert "Argument" not in letter.content
    assert "Vehemence" not in letter.content


def test_letter_title_line_dropped_greeting_kept(built):
    _, letter = _letter(built[0])
    assert letter.content.startswith("1. Firmilian to Testius, his brother in the Lord, greeting.")
    assert "Against the Letter of Stephen" not in letter.content
    edit = next(e for _, div, e in built[1] if div == "ii.i.i")
    assert [(r.block, r.kind) for r in edit.removed if r.kind not in ("bracket", "section")] == [
        ("p1", "heading"), ("p2", "heading"), ("p3", "heading"), ("p5", "letter-title"),
        ("p6", "argument"), ("p7", "credit"), ("p10", "provenance")]


def test_editor_section_under_a_heading_dropped(built):
    _, letter = _letter(built[0])
    assert letter.content.endswith("in all the churches that are of one mind.")
    assert "bishops of Rome" not in letter.content
    edit = next(e for _, div, e in built[1] if div == "ii.i.i")
    assert [(r.block, r.kind) for r in edit.removed if r.kind == "section"] == [("p12", "section")]


def test_chapter_title_moves_to_label(built):
    banquet = next(d for d in built[0] if d.metadata["source_key"] == BANQUET_KEY)
    [chapter] = banquet.passages
    assert chapter.chapter_label == "Chapter I: Virginity a Plant from Heaven, Introduced Late"
    assert chapter.content.startswith("For truly by a great stretch of power")
    edit = next(e for _, div, e in built[1] if div == "ii.ii.i")
    assert edit.removed == []      # a line that becomes the label is not a removal


def test_chapter_title_line_stays_outside_the_named_works():
    lines = ["Chapter II.—The Tenets of the Esseni Continued.", "The Essenes hold that"]
    assert editorial.strip_editorial_lines(lines) == lines


def test_provenance_line_dropped(built):
    _, letter = _letter(built[0])
    assert "Script. vet." not in letter.content
    assert "3. Therefore let each keep the truth" in letter.content


def test_heading_lines_only_at_the_top():
    lines = ["Book I.", "————————", "A long opening paragraph " * 10, "II.", "Hymn line."]
    assert editorial.strip_editorial_lines(lines) == lines[2:]


def test_judgments_found_in_removed_text():
    text = ("This golden letter, doubtless genuine, was attended with consequences. "
            "We forgive them. The homilies are doubtful works.")
    assert editorial.judgments(text) == [
        "This golden letter, doubtless genuine, was attended with consequences.",
        "We forgive them.", "The homilies are doubtful works."]


def test_removed_units_logged_with_judgment(built, monkeypatch):
    documents, log = built
    letters, letter = _letter(documents)
    elucidation = "ii.i.ii.i"
    pid = identity.passage_id(letters.id, elucidation)
    rows = [{"passage_id": p.id or identity.passage_id(d.id, p.anchor), "document_id": d.id,
             "anchor": p.anchor, "live_anchor": p.anchor, "status": "active",
             "frozen_on": "2026-10-30", "work_key": None}
            for d in documents for p in d.passages]
    rows.append({"passage_id": pid, "document_id": letters.id, "anchor": elucidation,
                 "live_anchor": elucidation, "status": "active", "frozen_on": "2026-10-30",
                 "work_key": None})
    works = [registry.work_entry(collection="church-fathers",
                                 source_key=d.metadata["source_key"], document_id=d.id,
                                 title=d.title, author=d.author, frozen_on="2026-10-30")
             for d in documents]
    reg = registry.WorkRegistry(works, rows, [], [{"id": "rm-0001", "scope": "class",
                                                  "collection": "church-fathers",
                                                  "document_id": letters.id, "anchor": None,
                                                  "added_by": "1.10b", "span": {}}], [])
    live = {pid: editorial_removals.div_text("thml_editorial.xml", elucidation, FIXTURE_DIR)}
    entries, found, problems = editorial_removals.generate(
        reg, documents, log, live, "2026-11-10", source_dir=FIXTURE_DIR)
    assert problems == []
    [retired] = [e for e in entries if e["scope"] == "passage"]
    assert (retired["anchor"], retired["passage_id"]) == (elucidation, pid)
    assert retired["tombstone"] and retired["reason"] == "rule-g-editorial"
    assert retired["judgment"].startswith("This letter is thought spurious by some")
    spans = {e["detail"]: e for e in entries if e["scope"] == "span"}
    assert {e["anchor"] for e in spans.values()} == {letter.anchor}
    assert all(len(e["span"]["excerpt"]) <= 120 and len(e["span"]["sha1"]) == 40
               for e in spans.values())
    assert [e["span"]["count"] for e in entries if e["scope"] == "class"] == [3]

    _, unreviewed = editorial_removals.plan(reg, entries, found)
    assert unreviewed, "a judgment nobody has read is not copied"
    quote = retired["judgment"]
    note = next(e for e in entries if e["detail"] == editorial_removals.DETAIL["section"])
    assert note["judgment"].startswith("This letter shows how little")
    monkeypatch.setattr(editorial_removals, "VERDICTS", {
        editorial_removals.sentence_key(quote): ("spurious", False),
        editorial_removals.sentence_key(note["judgment"]): ("genuine", False)})
    updated, unreviewed = editorial_removals.plan(reg, entries, found)
    assert unreviewed == []
    work = next(w for w in updated.works if w["document_id"] == letters.id)
    assert work["attribution"]["editorial_judgments"] == [
        {"source_file": "thml_editorial.xml", "element_id": "ii.i.ii", "quote": quote,
         "verdict": "spurious", "overridden_by_plan": False},
        {"source_file": "thml_editorial.xml", "element_id": "ii.i.i-p12",
         "quote": note["judgment"], "verdict": "genuine", "overridden_by_plan": False}]
    assert next(r for r in updated.passages if r["passage_id"] == pid)["status"] == "retired"
    assert {e["id"] for e in updated.removals if e["added_by"] == "1.8a"} == {
        f"rm-{n:04d}" for n in range(2, 2 + len(entries))}


def test_unexplained_changes_catches_lost_author_words():
    before = "Epistle I.\n\n1. Cyprian to Cornelius, greeting. We read [of God] your letter."
    after = "1. Cyprian to Cornelius, greeting. We read your letter."
    assert editorial.unexplained_changes(before, after, ["Epistle I.", "[of God]"]) == []
    assert editorial.unexplained_changes(before, after, ["Epistle I."])
    assert editorial.unexplained_changes(before, after.replace("read", "saw"),
                                         ["Epistle I.", "[of God]"])


@pytest.mark.sources
@pytest.mark.skipif(not os.path.isdir(_SRC), reason="church-fathers sources not vendored")
def test_author_text_unchanged():
    """Every chapter of the vendored ANF volumes loses only what its record lists: the
    author's words are unchanged (1.8a, coverage check)."""
    from ingest.church_fathers import build_all

    with editorial.recording() as log:
        build_all()
    failing = {}
    for key, div, edit in log:
        if isinstance(edit, str):
            continue
        before = direct_blocks_text(edit.elem)[0]
        after = direct_blocks_text(edit.elem, edit.again().edit)[0]
        removed = [r.text for r in edit.removed] + [edit.label_line or ""]
        problems = editorial.unexplained_changes(before, after, removed)
        if problems:
            failing[f"{key}#{div}"] = problems
    assert failing == {}
