"""The notes under an opened passage (corpus cleanup 4.4, issue #407)."""
import json

from app import card_notes, reader_access
from app.models.corpus import DocumentFacts
from app.rag.steps import document_facts

from tests.test_document_facts import _row

CARD = {"card_version": "1", "card_notes": None, "card_translator": None,
        "collection": "church-fathers", "title": "A Title", "document_url": None,
        "work_key": None, "note_kind": None, "translator": None}


def _card(**overrides):
    row = _row(**{**CARD, "note": None, **overrides})
    return document_facts._passage_facts(row).card


def _notes(*entries):
    return json.dumps(list(entries))


def test_a_document_from_before_4_4_gets_no_card_and_its_payload_is_unchanged():
    facts = document_facts._passage_facts(_row())
    assert facts.card is None
    assert "card" not in facts.source_fields()
    # Card columns present but no card_version: still none.
    assert _card(card_version=None) is None


def test_a_migrated_passage_with_nothing_to_say_has_an_empty_card():
    """Psalm 23: the badge names the translation, so nothing shows under the text, and
    the card's presence is what tells the client not to fall back to today's lines."""
    card = _card(collection="bible", translation="WEB-C", card_translator="",
                 source_credit="Public domain. Sourced via eBible.org")
    assert card.model_dump() == {"cautions": [], "record": [], "notice": None}
    assert document_facts._passage_facts(_row(**{**CARD, "note": None, "collection": "bible",
                                                 "card_translator": ""})
                                         ).source_fields()["card"]["record"] == []


def test_the_source_credit_never_reaches_the_card():
    card = _card(source_credit="Sourced via CCEL.org")
    assert card.notice is None
    assert "Sourced via CCEL.org" not in json.dumps(card.model_dump())


def test_a_vatican_text_carries_the_required_notice_and_the_catechism_the_usccbs():
    card = _card(collection="councils", document_url="https://www.vatican.va/x.html",
                 card_translator="The Vatican's English translation")
    assert card.notice == reader_access.VATICAN_CREDIT
    assert card.record == ["The Vatican's English translation"]
    ccc = _card(collection="catechism", title=reader_access.CATECHISM_TITLE,
                card_translator="")
    assert ccc.notice == reader_access.CATECHISM_NOTICE and ccc.record == []


def test_the_record_line_is_kind_and_form_then_survival_then_translator_then_scanned():
    card = _card(genre="apostolic-constitution", form="bull", text_source="ocr",
                 card_translator="Translation from Official Documents (Baltimore, 1855)",
                 card_notes=_notes({"text": "Preserved in a chronicle.", "show": "record"}))
    assert card.record == ["Apostolic constitution, issued as a bull",
                           "Preserved in a chronicle.",
                           "Translation from Official Documents (Baltimore, 1855)",
                           "scanned"]
    assert card.cautions == []


def test_the_translator_is_the_passages_then_the_cards_then_the_translation():
    assert _card(translator="Translated by J. A. Giles (1853)",
                 card_translator="Translated by H. J. Schroeder (1937)"
                 ).record == ["Translated by J. A. Giles (1853)"]
    assert _card(card_translator="Translated by H. J. Schroeder (1937)"
                 ).record == ["Translated by H. J. Schroeder (1937)"]
    # No card translator stored: the document's translation, as stored.
    assert _card().record == ["Ante-Nicene Fathers"]
    # Stored as empty: the card names none.
    assert _card(card_translator="").record == []


def test_an_unofficial_english_canon_names_its_translator_once_and_links_the_latin():
    card = _card(collection="church-law", text_status="unofficial_english",
                 official_latin_url="https://www.vatican.va/latin.html",
                 card_translator="The Vatican's English translation",
                 document_url="https://www.vatican.va/cic_index_en.html")
    assert card.record == []
    [caution] = card.cautions
    assert caution.kind == "wording"
    assert caution.text == ("An unofficial English translation (L’Osservatore Romano). "
                            "The Latin text is official.")
    assert caution.link.model_dump() == {"label": "The Latin text is official.",
                                         "href": "https://www.vatican.va/latin.html",
                                         "document_id": None}
    assert card.notice == reader_access.VATICAN_CREDIT


def test_cautions_come_from_the_passage_its_work_and_its_document_in_kind_order():
    card = _card(
        note="An extract.", note_kind="incomplete", work_key="w1",
        superseded_note="Superseded by a later text.", superseded_by="doc-2",
        card_notes=_notes(
            {"kind": "authorship", "text": "Not by Justin Martyr.", "show": "card"},
            {"kind": "authority", "text": "Another work's note.", "show": "card",
             "work_key": "w2"},
            {"kind": "authorship", "text": "Its own work's note.", "show": "card",
             "work_key": "w1"},
            {"kind": "incomplete", "text": "Only on the overview.", "show": "overview"}))
    assert [(c.kind, c.text) for c in card.cautions] == [
        ("incomplete", "An extract."),
        ("authorship", "Not by Justin Martyr."),
        ("authorship", "Its own work's note."),
        ("authority", "Superseded by a later text."),
    ]
    assert card.cautions[-1].link.document_id == "doc-2"


def test_a_document_note_leaves_out_the_works_it_names_in_except_work_keys():
    notes = _notes({"text": "Preserved in Eusebius, Church History", "show": "record",
                    "except_work_keys": ["mur"]})
    assert _card(card_notes=notes, card_translator="").record == [
        "Preserved in Eusebius, Church History"]
    assert _card(card_notes=notes, card_translator="", work_key="other").record == [
        "Preserved in Eusebius, Church History"]
    assert _card(card_notes=notes, card_translator="", work_key="mur").record == []


def test_a_passage_note_without_a_kind_is_still_shown_as_a_caution():
    assert [(c.kind, c.text) for c in _card(note="A note.").cautions] == [("wording", "A note.")]


def test_a_non_english_passage_is_a_wording_caution():
    [caution] = _card(language="la").cautions
    assert (caution.kind, caution.text) == (
        "wording", "This passage is in Latin; it is not included in search.")


def test_malformed_entries_are_skipped_not_fatal():
    card = _card(card_notes=_notes(
        "text", {"text": "", "show": "card", "kind": "wording"},
        {"text": "No kind on a card.", "show": "card"},
        {"text": "Bad kind.", "show": "card", "kind": "doubt"},
        {"text": "Bad place.", "show": "everywhere", "kind": "wording"},
        {"text": "Kept.", "show": "card", "kind": "wording"}))
    assert [c.text for c in card.cautions] == ["Kept."]


def test_overview_notes_are_the_documents_own_entries_whatever_their_place():
    metadata = {"card_version": 1, "card_notes": [
        {"kind": "authorship", "text": "Not by Justin Martyr.", "show": "card"},
        {"text": "Preserved in Eusebius.", "show": "record"},
        {"kind": "incomplete", "text": "Six canons are not shown.", "show": "overview"},
        {"kind": "authority", "text": "A work's.", "show": "card", "work_key": "w"}]}
    notes = card_notes.overview_notes(metadata)
    assert [(n.kind, n.text) for n in notes] == [
        ("authorship", "Not by Justin Martyr."), (None, "Preserved in Eusebius."),
        ("incomplete", "Six canons are not shown.")]
    assert card_notes.overview_notes(json.dumps(metadata)) == notes
    assert card_notes.overview_notes({"card_notes": metadata["card_notes"]}) is None
    assert card_notes.overview_notes(None) is None
    assert card_notes.overview_notes({"card_version": 1}) == []


def test_an_unknown_card_version_is_treated_as_before_4_4():
    assert _card(card_version="2") is None
    assert card_notes.card_version(True) is None
    assert card_notes.card_version(1) == card_notes.card_version("1") == 1


def test_kind_and_form_name_a_papal_kind():
    # The Papal documents badge names no kind, so every papal kind is shown.
    kf = card_notes.kind_and_form
    assert kf(DocumentFacts(genre="encyclical")) == "Encyclical"
    assert kf(DocumentFacts(genre="encyclical", form="brief")) == "Encyclical, issued as a brief"
    assert kf(DocumentFacts(genre="apostolic-exhortation")) == "Apostolic exhortation"
    assert kf(DocumentFacts(genre="apostolic-letter")) == "Apostolic letter"
    assert kf(DocumentFacts(form="brief")) == "Issued as a brief"
    assert kf(DocumentFacts(genre="treatise")) is None
    assert kf(DocumentFacts(genre="other", form="bull")) == "Issued as a bull"


def test_kind_and_form_name_a_roman_curia_kind_but_not_a_writers():
    kf = card_notes.kind_and_form
    assert kf(DocumentFacts(genre="instruction", issuer="ddf")) == "Instruction"
    assert kf(DocumentFacts(genre="doctrinal-note", issuer="ddf")) == "Doctrinal note"
    assert kf(DocumentFacts(genre="commentary", issuer="ddf")) == "Commentary"
    # A theologian's commentary, which shares the genre, shows no kind.
    assert kf(DocumentFacts(genre="commentary")) is None


def test_the_facts_query_reads_only_the_card_keys_of_either_metadata():
    sql = document_facts._sql(works=True)
    for column in ("c.metadata->>'note_kind'", "c.metadata->>'translator'",
                   "d.metadata->>'card_version'", "d.metadata->'card_notes'",
                   "d.metadata->>'card_translator'", "d.metadata->>'url'"):
        assert column in sql
    assert "d.metadata," not in sql and "c.metadata," not in sql
