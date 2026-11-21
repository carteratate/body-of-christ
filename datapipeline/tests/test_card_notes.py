"""The notes under an opened passage, stored with their kind and place (corpus cleanup 4.4)."""
import re

import pytest

import card_notes
from checks import card_notes as check
from model import Document, Passage, Work


def _passage(n: int, note=None, metadata=None, work_key=None) -> Passage:
    return Passage(content=f"text {n}", reference=f"Ref {n}", anchor=f"a/{n}",
                   chapter_key="c", chapter_label="C", position=n, note=note,
                   metadata=metadata, work_key=work_key)


def _document(passages, **fields) -> Document:
    return Document(id="d", collection=fields.pop("collection", "councils"),
                    title=fields.pop("title", "Council of Florence"), passages=passages,
                    **fields)


# --------------------------------------------------------------------------- translator

@pytest.mark.parametrize("credit, translation, expected", [
    ("Translated by Roy J. Deferrari (1957)", "", "Translated by Roy J. Deferrari (1957)"),
    ("Translation from The Rambler (1850), abridged", "", "Translation from The Rambler (1850)"),
    ("Translation from The Rambler (1860), extract", "", "Translation from The Rambler (1860)"),
    ("Translated by J. Waterworth (1848). Text: papalencyclicals.net", "",
     "Translated by J. Waterworth (1848)"),
    ("Translated by William Harman van Allen (1909). Sourced via CCEL.org", "",
     "Translated by William Harman van Allen (1909)"),
    ("Translated by H. J. Schroeder (1937); five canons and an extract of canon 17 by Roy J. "
     "Deferrari (1957)", "", "Translated by H. J. Schroeder (1937)"),
    ("Sourced via CCEL.org", "Ante-Nicene Fathers (1885-1896)",
     "Ante-Nicene Fathers (1885–1896)"),
    ("Sourced via CCEL.org; Nestorius's second letter to Cyril translated by James Chrystal "
     "(1895)", "Nicene and Post-Nicene Fathers, Series II",
     "Nicene and Post-Nicene Fathers, Series II"),
    ("© Dicastery for Communication – Libreria Editrice Vaticana", "Vatican English",
     "The Vatican's English translation"),
    ("Public domain. Sourced via eBible.org", "WEB-C", ""),
    ("Excerpts from the English translation of the Catechism…", "United States edition (1997)", ""),
    ("Sourced via CCEL.org", "Fathers of the English Dominican Province (1920)",
     "Translated by the Fathers of the English Dominican Province (1920)"),
    ("Sourced via CCEL.org", "E. B. Pusey (1838)", "Translated by E. B. Pusey (1838)"),
])
def test_the_card_translator_is_written_once_from_the_credit_or_the_translation(
        credit, translation, expected):
    assert card_notes.card_translator(credit, translation) == expected


# --------------------------------------------------------------------------- apply

def test_a_passage_note_is_rewritten_with_its_kind_and_the_document_gets_its_keys():
    doc = card_notes.apply(_document([
        _passage(0, note="Abridged in Schroeder (1937)."), _passage(1)],
        source_credit="Translated by H. J. Schroeder (1937)"), None)
    first, second = doc.passages
    assert (first.note, first.metadata) == ("Abridged by the translator.",
                                            {"note_kind": "incomplete"})
    assert (second.note, second.metadata) == (None, None)
    assert doc.metadata == {"card_version": 1, "card_notes": [],
                            "card_translator": "Translated by H. J. Schroeder (1937)"}


def test_works_json_card_translator_wins_over_the_rule():
    doc = card_notes.apply(_document([_passage(0)], source_credit="Sourced via CCEL.org",
                                     translation="X"), {"card_translator": ""})
    assert doc.metadata["card_translator"] == ""


def test_a_council_passage_from_a_second_edition_names_its_own_translator():
    doc = card_notes.apply(_document([
        _passage(0, metadata={"text_source": "ocr", "scan_id": "DisciplinaryCouncils"}),
        _passage(1, note="Extract, in R. J. Deferrari's translation of Denzinger, The Sources "
                         "of Catholic Dogma (1957).",
                 metadata={"text_source": "ocr",
                           "scan_id": "sources-of-catholic-dogma-loreto-reprint"}),
    ], source_credit="Translated by H. J. Schroeder (1937); the extracts of three decrees by "
                     "Roy J. Deferrari (1957)"), None)
    schroeder, deferrari = doc.passages
    assert "translator" not in schroeder.metadata
    assert deferrari.metadata["translator"] == (
        "Translated by Roy J. Deferrari (1957), in The Sources of Catholic Dogma")
    assert deferrari.note == "An extract; the full text is not available on TheoCorpus at present."
    # Only councils hold two translators' passages in one document.
    encyclical = card_notes.apply(_document(
        [_passage(0, metadata={"scan_id": "sources-of-catholic-dogma-loreto-reprint"})],
        collection="encyclicals", source_credit="Translated by Roy J. Deferrari (1957)"), None)
    assert "translator" not in encyclical.passages[0].metadata


def test_document_and_work_notes_become_entries_and_header_repeats_go():
    doc = card_notes.apply(_document(
        [_passage(0, work_key="w")], collection="church-fathers", title="Fragments of Caius",
        notes="Preserved in Eusebius, Church History.",
        works=[Work("w", 1, "The Muratorian Fragment", author="Anonymous",
                    attribution_note="Its author is unknown; the editors printed it with "
                                     "Caius's fragments on one scholar's guess.")]), None)
    assert doc.metadata["card_notes"] == [
        {"kind": None, "text": "Preserved in Eusebius, Church History", "show": "record"},
        {"kind": "authorship", "show": "card", "work_key": "w",
         "text": "The editors printed it with Caius's fragments on one scholar's guess."},
    ]
    pseudo = card_notes.apply(_document([_passage(0)], collection="church-fathers",
                                        attribution_note="Not by Justin Martyr."), None)
    assert pseudo.metadata["card_notes"] == []


def test_exsurge_domines_note_leaves_its_passages_for_the_overview():
    note = ("Propositions of Martin Luther that the bull condemned, not its teaching. The rest "
            "of the bull is not available on TheoCorpus at present. Translated by R. J. "
            "Deferrari (1957).")
    doc = card_notes.apply(_document([_passage(0, note=note), _passage(1, note=note)],
                                     collection="papal-documents", title="Exsurge Domine"),
                           {"work_id": "papal-documents/exsurge-domine"})
    assert all(p.note is None for p in doc.passages)
    assert doc.metadata["card_notes"] == [{
        "kind": "incomplete", "show": "overview",
        "text": "Only the condemned propositions are given; the rest of the bull is not "
                "available on TheoCorpus at present."}]
    assert check.problems(doc) == []


def test_a_note_on_every_passage_goes_when_the_document_says_it():
    extract = ("Extract, in R. J. Deferrari's translation of Denzinger, The Sources of Catholic "
               "Dogma (1957).")
    vix = ("Only an extract of this encyclical is given, in R. J. Deferrari's translation of "
           "Denzinger (1957): the five teachings on usury in paragraph 3. The rest is not "
           "available on TheoCorpus at present.")
    doc = card_notes.apply(_document([_passage(0, note=extract), _passage(1, note=extract)],
                                     collection="encyclicals", title="Vix Pervenit", notes=vix),
                           None)
    assert [p.note for p in doc.passages] == [None, None]
    assert check.problems(doc) == []
    # Without the document's note it stays, and the check refuses it.
    alone = card_notes.apply(_document([_passage(0, note=extract)], collection="encyclicals",
                                       title="Singulari Nos"), None)
    assert alone.passages[0].note is not None
    assert any("on every passage" in p for p in check.problems(alone))


def test_the_supplements_generated_note_keeps_its_parts():
    note = card_notes.passage_note(
        "The English translation omits part of this article's Latin text (ad 2, ad 3).")
    assert (note.kind, note.text) == (
        "incomplete", "The English translation omits part of this article's Latin text (ad 2, ad 3).")


def test_an_unknown_note_stops_the_build_until_it_has_a_kind():
    with pytest.raises(card_notes.CardNoteError, match="PASSAGE_NOTES"):
        card_notes.apply(_document([_passage(0, note="A new note.")]), None)
    with pytest.raises(card_notes.CardNoteError, match="FACT_NOTES"):
        card_notes.apply(_document([_passage(0)], notes="A new document note."), None)


# --------------------------------------------------------------------------- the tables

ALL_NOTES = [n for n in card_notes.PASSAGE_NOTES.values() if n is not None] + [
    n for notes in (*card_notes.FACT_NOTES.values(), *card_notes.DOCUMENT_NOTES.values())
    for n in notes]


def test_every_card_note_has_a_kind_and_a_place():
    for note in ALL_NOTES:
        assert note.show in card_notes.SHOWS, note
        assert note.kind is None or note.kind in card_notes.KINDS, note
        if note.show == "card":
            assert note.kind is not None, note


def test_no_wording_names_a_translator():
    names = {"Schroeder", "Deferrari", "Giles", "Clark", "Chrystal", "Denzinger"}
    for note in ALL_NOTES:
        assert not any(re.search(rf"\b{n}\b", note.text) for n in names), note


# --------------------------------------------------------------------------- the check

def _checked(**overrides):
    doc = _document([_passage(0), _passage(1)], source_credit="Translated by H. J. "
                                                              "Schroeder (1937)")
    doc = card_notes.apply(doc, None)
    for key, value in overrides.items():
        if key == "passages":
            doc.passages = value
        else:
            doc.metadata = {**doc.metadata, key: value}
    return check.problems(doc)


def test_the_check_passes_a_written_document():
    assert _checked() == []


def test_the_check_refuses_a_caution_without_a_kind():
    assert any("without a kind" in p for p in _checked(
        card_notes=[{"kind": None, "text": "A caution.", "show": "card"}]))
    assert any("without a kind" in p for p in _checked(
        passages=[_passage(0, note="A note."), _passage(1)]))
    assert any("has kind" in p for p in _checked(
        card_notes=[{"kind": "doubt", "text": "A caution.", "show": "card"}]))


def test_the_check_refuses_a_note_naming_the_translator_author_or_title():
    assert any("names Schroeder" in p for p in _checked(
        card_notes=[{"kind": "incomplete", "text": "Abridged by Schroeder.", "show": "card"}]))
    assert any("names Council of Florence" in p for p in _checked(
        card_notes=[{"kind": None, "text": "Part of the Council of Florence.", "show": "record"}]))
    named = card_notes.apply(_document([_passage(0), _passage(1)], collection="church-fathers",
                                       title="T", author="Justin Martyr"), None)
    named.metadata["card_notes"] = [{"kind": "authorship", "text": "Not by Justin Martyr.",
                                     "show": "card"}]
    assert any("names Justin Martyr" in p for p in check.problems(named))


def test_the_check_refuses_a_document_without_its_card_keys():
    doc = _document([_passage(0)])
    assert check.problems(doc) == ["Council of Florence: no card_version 1"]
    doc = card_notes.apply(doc, None)
    del doc.metadata["card_translator"]
    assert any("can name no translator" in p for p in check.problems(doc))


def test_the_check_raises_for_a_build():
    doc = card_notes.apply(_document([_passage(0)]), None)
    doc.metadata["card_notes"] = [{"kind": None, "text": "A caution.", "show": "card"}]
    with pytest.raises(ValueError, match="REFUSING: card notes"):
        check.check([doc])
