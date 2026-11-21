"""Stromata III in Henry Chadwick's English (#399): the OCR units, the alignment to ANF's
passages, the build and the registry."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import registry
import rights_inventory
from checks.language import latin_runs
from ingest import stromata_chadwick as sc
from ocr.furniture import Paragraph
from ocr.units import ChadwickSections
from scripts import stromata_chadwick_registry as scr

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "church-fathers")
vendored = pytest.mark.skipif(not os.path.isdir(_SRC), reason="sources not vendored")


def _paras(*texts):
    return [Paragraph(t, t, [1]) for t in texts]


WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve")


def _book(n_sections: int, extra: dict[int, str] | None = None) -> list[str]:
    """Title lines, then chapter I holding sections 1..n, each a paragraph, the odd ones
    ending on a note call."""
    extra = extra or {}
    return ["On Marriage", "Miscellanies, Book III", "THE TEXT", "CHAPTER I"] + [
        extra.get(n, f"{n}. Section {WORDS[n - 1]} says this." + (" 7" if n % 2 else ""))
        for n in range(1, n_sections + 1)]


@pytest.fixture
def units(monkeypatch):
    u = ChadwickSections()
    monkeypatch.setattr(u, "SECTIONS", 4)
    return u


def test_units_are_sections_without_numbers_notes_or_headings(units):
    out = units.split(_paras(*_book(4)))
    assert [u.id for u in out] == ["ch01/s001", "ch01/s002", "ch01/s003", "ch01/s004"]
    assert [p.text for u in out for p in u.paragraphs] == [
        f"Section {w} says this." for w in WORDS[:4]]


def test_a_section_may_open_inside_a_paragraph_after_a_note_call(units):
    texts = _book(4, {2: '2. He wrote: "Man is weak." 35 3. Moreover he said so.'})
    del texts[-2]                              # section 3 is inside section 2's paragraph
    out = units.split(_paras(*texts))
    assert [p.text for u in out for p in u.paragraphs] == [
        "Section one says this.", 'He wrote: "Man is weak."', "Moreover he said so.",
        "Section four says this."]


def test_split_and_misread_numbers_are_found(monkeypatch):
    u = ChadwickSections()
    monkeypatch.setattr(u, "SECTIONS", 12)
    texts = _book(12, {1: "i. The first.", 10: "1 0. The tenth.", 11: "1 1 . The eleventh."})
    out = u.split(_paras(*texts))
    assert [x.id for x in out][-3:] == ["ch01/s010", "ch01/s011", "ch01/s012"]
    assert out[0].paragraphs[0].text == "The first."
    assert out[10].paragraphs[0].text == "The eleventh."


def test_chapter_headings_set_the_chapter_and_a_missing_section_raises(units):
    texts = _book(4)
    texts.insert(6, "CHAPTER II")
    assert [u.id for u in units.split(_paras(*texts))] == [
        "ch01/s001", "ch01/s002", "ch02/s003", "ch02/s004"]
    with pytest.raises(ValueError, match="section 4 is not where expected"):
        units.split(_paras(*_book(3)))


def test_a_verse_line_continues_its_paragraph(units):
    texts = _book(4, {2: '2. Empedocles says: "When I saw the place, I wept and'})
    texts.insert(6, 'wailed."')
    out = units.split(_paras(*texts))
    assert [p.continues for p in out[1].paragraphs] == [False, True]


# ── The frozen text and its alignment ───────────────────────────────────────

def test_frozen_text_passed_its_gate_and_holds_the_110_sections():
    frozen = sc.read_text(sc.WORK)
    assert frozen["gate"] == "pass"
    assert frozen["metadata"] == {"text_source": "ocr", "scan_id": "alexandrianchris012826mbp"}
    assert sorted(sc.sections(frozen)) == list(range(1, 111))


def test_the_pieces_cover_the_book_once_in_order():
    texts = sc.english()
    assert list(texts) == [a for a, _, _ in sc.PIECES] and len(texts) == 33
    joined = " ".join(" ".join(t.split()) for t in texts.values())
    whole = " ".join(" ".join(t.split()) for t in sc.sections().values())
    assert joined == whole
    for (anchor, _, opening), text in zip(sc.PIECES, texts.values()):
        assert text.replace("“", '"').lstrip('"').startswith(
            opening.replace("“", '"')), anchor
    assert texts[sc.BOOK].endswith("If you burn, marry.")
    assert texts[f"{sc.BOOK}/from-p246-2"].endswith("in accordance with the true philosophy.")


def test_an_opening_must_start_a_sentence():
    assert sc._find("He said. If, as they say, so.", "If, as they say") == 9
    assert sc._find("he wished if, as they say, so.", "if, as they say") is None
    assert sc._find('"Thou shalt not covet," he said.', "Thou shalt not covet") == 0


def test_no_latin_reaches_the_english():
    for anchor, text in sc.english().items():
        assert latin_runs(text) == [], anchor


# ── The build ───────────────────────────────────────────────────────────────

@vendored
@pytest.mark.sources
def test_build_restores_book_iii_in_english_with_its_ids():
    import card_notes
    from ingest.church_fathers import build_all
    reg = registry.current()
    built = next(d for d in build_all() if d.id == sc.STROMATA)
    # As `publication.prepare` stores the card's notes (4.4).
    doc = card_notes.apply(built, reg.entry_by_document[sc.STROMATA])
    assert doc.metadata["card_translator"] == "Ante-Nicene Fathers (1885–1896)"
    book = [p for p in doc.passages if p.anchor.split("/")[0] == sc.BOOK]
    assert [p.anchor for p in book] == [a for a, _, _ in sc.PIECES]
    assert not any((p.metadata or {}).get("translator") for p in doc.passages
                   if p.anchor.split("/")[0] != sc.BOOK)
    for p in book:
        assert p.note is None and p.metadata["text_replaced"] == sc.TEXT_REPLACED
        assert p.metadata["translator"] == "Translated by Henry Chadwick (1954)"
        assert p.chapter_key == sc.BOOK and p.chapter_label == "Book III"
        assert "footnotes" not in p.metadata and "editor_note_count" not in p.metadata
        row = reg.row_by_anchor[(sc.STROMATA, p.anchor)]
        assert row["status"] == "active"
    assert doc.notes is None


# ── The registry and the rights row ─────────────────────────────────────────

def test_registry_closes_3_3s_stromata_entries():
    reg = registry.current()
    entries = {e["id"]: e for e in reg.removals}
    assert all(entries[n]["closed_by"] == "#399" for n in scr.REMOVALS)
    rows = {r["passage_id"]: r for r in reg.passages}
    assert rows[scr.MERGED]["status"] == "redirected"
    (redirect,) = [r for r in reg.redirects
                   if r["old_passage_id"] == scr.MERGED and not r.get("closed_by")]
    assert redirect["new_anchor"] == scr.MERGED_INTO and redirect["added_by"] == "#399"


def test_registry_rerun_changes_nothing():
    import json
    reg = registry.current()
    copy = registry.WorkRegistry(*(json.loads(json.dumps(x)) for x in (
        reg.works, reg.passages, reg.redirects, reg.removals, reg.kept_text)))
    scr.apply(copy, "2099-01-01")
    assert (copy.removals, copy.passages, copy.redirects) == \
        (reg.removals, reg.passages, reg.redirects)


def test_rights_row_names_chadwick_for_book_iii():
    row = rights_inventory.by_document_id(rights_inventory.load())[sc.STROMATA]
    (edition,) = row["also_from"]
    assert edition["translator"] == "Henry Chadwick" and edition["first_published"] == 1954
    assert edition["status"] == "pd-us-non-renewal"
    assert edition["checked_by"] == "Carter" and edition["checked_on"] == "2026-11-16"
    assert edition["source_url"] == sc.SCAN_URL
