"""Universi Dominici Gregis and its history in Church law (corpus-cleanup 5.4, #203)."""
import os
import re
import sys

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("QDRANT_URL", "http://localhost")
os.environ.setdefault("QDRANT_API_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import headings
import registry
import rights_inventory
from ingest import universal_law as U

_vendored = all(os.path.exists(os.path.join(U.SRC, e.file)) for e in U.EDITIONS)
needs_sources = pytest.mark.skipif(not _vendored, reason="sources/church-law not vendored")


@pytest.fixture(scope="module")
def built():
    current, original, normas = U.build_documents()
    return current, original, normas


def _norm(text: str) -> str:
    """Text compared across the two editions: quotes and spacing as each prints them."""
    text = re.sub(r"[“”\"]", "", text)
    return " ".join(re.sub(r"[‘’]", "'", text).split())


def _amended() -> set[int]:
    return {int(n.split(",")[0]) for n in U.AMENDED}


# --------------------------------------------------------------------------- units

def _blocks(*items):
    return [U._Block(kind, text) for kind, text in items]


def test_constitution_units_hold_headings_for_the_number_they_open(monkeypatch):
    monkeypatch.setattr(U, "NUMBERS", 2)
    blocks = _blocks(("para", "The Shepherd of the Lord's whole flock."),
                     ("part", "PART ONE"), ("part-title", "THE VACANCY"),
                     ("chapter", "CHAPTER I"), ("chapter-title", "THE POWERS"),
                     ("para", "1. During the vacancy."), ("para", "It runs on."),
                     ("para", "2. Second."),
                     ("promulgation", "PROMULGATION"), ("para", "Wherefore."),
                     ("para", "Given in Rome, in the year 1996."),
                     ("para", "IOANNES PAULUS PP. II"))
    units = U.constitution_units(blocks, U.CURRENT)
    assert [u.anchor for u in units] == ["preamble/1", "no/1", "no/2", "promulgation/1"]
    one = units[1]
    assert (one.chapter_key, one.chapter_label, one.unit_label) == (
        "part-1/chapter-1", "Part One, Chapter I: The Powers", "No. 1")
    assert [h.text for h in one.held] == ["PART ONE", "THE VACANCY", "CHAPTER I", "THE POWERS"]
    assert one.paragraphs == ["During the vacancy.", "It runs on."]
    # The dating line and the signature close the last promulgation paragraph.
    assert units[-1].paragraphs == ["Wherefore.", "Given in Rome, in the year 1996.",
                                    "IOANNES PAULUS PP. II"]


def test_constitution_units_refuse_a_missing_number(monkeypatch):
    monkeypatch.setattr(U, "NUMBERS", 3)
    with pytest.raises(ValueError, match="2 numbers, expected 3"):
        U.constitution_units(_blocks(("part", "PART ONE"), ("part-title", "THE VACANCY"),
                                     ("chapter", "CHAPTER I"), ("chapter-title", "POWERS"),
                                     ("para", "1. One."), ("para", "2. Two.")), U.CURRENT)


def test_normas_units_one_per_norm():
    texts = ["With the Apostolic Letter De Aliquibus Mutationibus.", "Given the importance.",
             'No. 46 § 1. "In order to meet."', "There must also be available.",
             'No. 62. "Since the forms."', "All that I have laid down.",
             "Given in Rome.", "BENEDICTUS PP. XVI"]
    units = U.normas_units(texts)
    assert [(u.anchor, u.unit_label) for u in units] == [
        ("preamble/1", None), ("preamble/2", None), ("no/46-1", "No. 46 § 1"),
        ("no/62", "No. 62"), ("closing", None)]
    assert units[2].paragraphs[1] == "There must also be available."
    assert units[-1].paragraphs[-1] == "BENEDICTUS PP. XVI"
    assert units[0].reference == "Normas Nonnullas, Preamble (part 1 of 2)"


def test_line_end_hyphens_join_except_in_compounds():
    assert U._held_joined("the pre­ scrutiny and the ballot­paper") == \
        "the pre-scrutiny and the ballotpaper"
    assert U._held_joined("the above­mentioned oath") == "the above-mentioned oath"


def test_broken_words_are_mended():
    assert U._clean("abso- lutely and men-tioned and newly- elected") == \
        "absolutely and mentioned and newly-elected"


# --------------------------------------------------------------------------- the build

@needs_sources
def test_three_documents_one_searchable(built):
    current, original, normas = built
    assert [d.title for d in built] == [U.CURRENT.title, U.ORIGINAL.title, U.NORMAS.title]
    assert {d.collection for d in built} == {"church-law"}
    assert (len(current.passages), len(original.passages), len(normas.passages)) == \
        (108, 108, 18)
    assert all(p.searchable for p in current.passages)
    # Superseded text kept as history: never searchable (rule F, D5).
    assert not any(p.searchable for d in (original, normas) for p in d.passages)
    for d in built:
        assert [p.position for p in d.passages] == list(range(len(d.passages)))
        assert len({p.anchor for p in d.passages}) == len(d.passages)
        assert all(p.chapter_key for p in d.passages)    # dedup's per-chapter cap


@needs_sources
def test_both_editions_hold_every_number_under_the_same_chapters(built):
    current, original, _ = built
    for d in (current, original):
        numbers = [p.anchor for p in d.passages if p.anchor.startswith("no/")]
        assert numbers == [f"no/{n}" for n in range(1, U.NUMBERS + 1)]
    chapters = lambda d: {p.anchor: p.chapter_key for p in d.passages}  # noqa: E731
    assert chapters(current) == chapters(original)
    assert len({p.chapter_key for p in current.passages}) == 14   # preamble, 12, promulgation


@needs_sources
def test_editions_read_the_same_outside_the_amended_numbers(built):
    # The 1996 PDF and the consolidated page are read by different readers; every number
    # Normas Nonnullas left alone must come out the same, paragraph breaks included.
    current, original, _ = built
    old = {p.anchor: p for p in original.passages}
    for p in current.passages:
        n = int(p.anchor.split("/")[1]) if p.anchor.startswith("no/") else None
        if n in _amended():
            continue
        q = old[p.anchor]
        if p.anchor == "promulgation/2":
            # Only the page prints the signature.
            assert p.content.endswith("\n\nIOANNES PAULUS PP. II")
            assert _norm(q.content) == _norm(p.content[:-len("\n\nIOANNES PAULUS PP. II")])
            continue
        assert _norm(p.content) == _norm(q.content), p.anchor
        assert p.content.count("\n\n") == q.content.count("\n\n"), p.anchor


@needs_sources
def test_the_amended_numbers_read_as_normas_nonnullas_gives_them(built):
    current, original, normas = built
    now = {p.anchor: p for p in current.passages}
    then = {p.anchor: p for p in original.passages}
    norms = [p for p in normas.passages if p.anchor.startswith("no/")]
    assert len(norms) == len(U.AMENDED)
    for p in norms:
        n = p.anchor.split("/")[1].split("-")[0]
        given = _norm(re.sub(r"^No\. \d+(?:\s*§\s*\d)?\.\s*", "", p.content))
        assert given in _norm(now[f"no/{n}"].content), p.anchor
        assert _norm(now[f"no/{n}"].content) != _norm(then[f"no/{n}"].content), p.anchor


@needs_sources
def test_number_75_two_thirds_now_absolute_majority_then(built):
    current, original, _ = built
    now = next(p for p in current.passages if p.anchor == "no/75").content
    then = next(p for p in original.passages if p.anchor == "no/75").content
    assert "two thirds of the votes of the Cardinals present and voting" in now
    assert "absolute majority" not in now
    assert "absolute majority" in then


@needs_sources
def test_misprint_and_marks_are_not_in_the_text(built):
    current, _, normas = built
    text = "\n".join(p.content for p in current.passages)
    assert "Since Since" not in text
    assert not re.search(r"\[\d+\]", text)                 # note callers
    assert not re.search(r"^n ", text, re.M)               # the amendment mark
    assert "NOTE:" not in text and "Original Version" not in text
    # Normas Nonnullas' markup closes No. 48's oath early; its last words are kept.
    oath = next(p for p in normas.passages if p.anchor == "no/48").content
    assert "(‘latae sententiae’) excommunication reserved to the Apostolic See." in oath


@needs_sources
def test_headings_are_marked_and_valid(built):
    current, original, _ = built
    for d in (current, original):
        for p in d.passages:
            assert headings.problems(p.content, (p.metadata or {}).get("headings")) == [], \
                p.anchor
        first = next(p for p in d.passages if p.anchor == "no/1")
        marks = first.metadata["headings"]
        assert [first.content[m["at"]:m["end"]] for m in marks] == [
            "PART ONE", "THE VACANCY OF THE APOSTOLIC SEE", "CHAPTER I",
            "THE POWERS OF THE COLLEGE OF CARDINALS DURING THE VACANCY OF THE APOSTOLIC SEE"]
        assert [(m["level"], m.get("pairs_next", False)) for m in marks] == [
            (1, True), (1, False), (2, True), (2, False)]


@needs_sources
def test_the_page_lists_what_was_amended():
    assert U.amendment_note() == list(U.AMENDED)


# --------------------------------------------------------------------------- registry

@needs_sources
def test_history_documents_point_at_the_current_text(built):
    current, original, normas = built
    reg = registry.current()
    for d in (original, normas):
        entry = reg.entry_by_document[d.id]
        assert entry["superseded_by"] == current.id
        assert entry["superseded_note"].startswith("Superseded text, kept as history:")
    assert reg.entry_by_document[current.id]["superseded_by"] is None
    assert reg.entry_by_document[current.id]["issuer"] == "pope-john-paul-ii"
    assert reg.entry_by_document[normas.id]["genre"] == "motu-proprio"


def test_rights_rows_for_the_built_and_the_excluded():
    rows = rights_inventory.load()
    by_path = {r["source_path"]: r for r in rows}
    for e in U.EDITIONS:
        row = by_path[f"church-law/{e.file}"]
        assert (row["work"], row["planned_for"]) == (e.title, None)
        assert row["document_id"]
    # Rule E (revised 29 Oct 2026): neither is added, so neither has a row (Carter,
    # 23 Nov 2026).
    assert "church-law/de-aliquibus-mutationibus.html" not in by_path
    assert "apostolic-exhortations/a-new-hope-for-lebanon.html" not in by_path
