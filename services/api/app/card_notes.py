"""The notes under an opened passage (corpus cleanup 4.4, issue #407).

At most three slots under the text, each its own voice:

1. Read with care (`cautions`): TheoCorpus's caution about this passage, one sentence
   each, opened by its kind (incomplete, wording, authorship, authority).
2. About this text (`record`): one line, kind and form · how the text survives · this
   passage's translator · "scanned".
3. The required notice (`notice`): the USCCB's or the Vatican's line, verbatim
   (`reader_access.source_credit`). Where the digital text came from ("Sourced via
   CCEL.org") is never on the card: the reader and the Sources page show it.

The datapipeline stores each note with its kind and place (4.4 PR (b)): a document's,
and its works', as `documents.metadata.card_notes` entries `{kind, text, show, work_key?}`
(`show` is `card`, `record` or `overview`; a `record` or `overview` entry may have no
kind); a passage's own note in `chunks.note` with its kind in `chunks.metadata.note_kind`;
the translator for the card in `documents.metadata.card_translator` (an empty string
means the card names none, because the header or the notice already does), or a
passage's own in `chunks.metadata.translator`. Every document such a publish writes
carries `metadata.card_version`, and only those passages get a card, so a migrated
passage with nothing to say (a psalm) is told apart from one not yet migrated.
"""
from __future__ import annotations

import json
from typing import Any

from app.models.corpus import (CardCaution, CardLink, DocumentFacts, OverviewNote,
                               PassageCard)

CARD_VERSION = 1
CAUTION_KINDS = ("incomplete", "wording", "authorship", "authority")
SHOWS = ("card", "record", "overview")

# Wordings the API itself writes, from fields the earlier items already send.
SCANNED = "scanned"
UNOFFICIAL_ENGLISH = "An unofficial English translation (L’Osservatore Romano)."
OFFICIAL_LATIN = "The Latin text is official."
READ_CURRENT_TEXT = "Read the current text"

_LANGUAGE_NAMES = {
    "la": "Latin", "el": "Greek", "grc": "Greek", "it": "Italian", "fr": "French",
    "de": "German", "es": "Spanish", "pt": "Portuguese", "syr": "Syriac",
}
_FORMS = {"bull": "a bull", "brief": "a brief"}


def _json(value: Any) -> Any:
    """A jsonb value as Python: the API's pool decodes jsonb itself (`app/db.py`), a bare
    connection hands back text."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def card_version(value: Any) -> int | None:
    """The `metadata.card_version` a 4.4 publish wrote (an int, or its text from
    `metadata->>'card_version'`), or None for a document from before it, or one this API
    does not know how to read."""
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value)
    return value if isinstance(value, int) and not isinstance(value, bool) \
        and 1 <= value <= CARD_VERSION else None


def entries(value: Any) -> list[dict]:
    """The well-formed `metadata.card_notes` entries, in stored order. A malformed one is
    skipped rather than failing the passage; the build's check refuses it first."""
    value = _json(value)
    if not isinstance(value, list):
        return []
    out = []
    for e in value:
        if not isinstance(e, dict):
            continue
        text, show, kind = _text(e.get("text")), e.get("show"), e.get("kind")
        if not text or show not in SHOWS or (kind is not None and kind not in CAUTION_KINDS):
            continue
        if show == "card" and kind is None:
            continue
        work_key = e.get("work_key")
        out.append({"kind": kind, "text": text, "show": show,
                    "work_key": work_key if isinstance(work_key, str) else None})
    return out


def overview_notes(metadata: Any) -> list[OverviewNote] | None:
    """The notes a document's overview (and an excerpt-only document's Library row)
    shows: its own entries, whatever their place, since a note on every card is also
    true of the document. Works' entries stay on their works' passages. None for a
    document from before 4.4, whose overview shows its facts as before."""
    metadata = _json(metadata)
    if not isinstance(metadata, dict) or card_version(metadata.get("card_version")) is None:
        return None
    return [OverviewNote(kind=e["kind"], text=e["text"])
            for e in entries(metadata.get("card_notes")) if e["work_key"] is None]


def language_name(code: str | None) -> str | None:
    if not code or code == "en":
        return None
    return _LANGUAGE_NAMES.get(code, code)


# A papal document's kind (1.3b's genres). A Father's writer genre (treatise, letter) is
# not shown on the card, as the approved design shows none.
PAPAL_GENRES = ("encyclical", "apostolic-exhortation", "apostolic-letter",
                "apostolic-constitution", "motu-proprio", "letter")
# The kind a collection's badge already names (rule 1: the record does not repeat it).
_BADGE_KINDS = {"encyclicals": "encyclical", "apostolic-exhortations": "apostolic-exhortation"}


def kind_and_form(facts: DocumentFacts, collection: str = "") -> str | None:
    """"Apostolic constitution, issued as a bull"; "Apostolic exhortation" for Evangelii
    Gaudium under the Encyclicals badge. A kind the badge already names shows only with
    its form ("Encyclical, issued as a brief"), and a writer's genre not at all."""
    form = _FORMS.get(facts.form or "")
    genre = facts.genre if facts.genre in PAPAL_GENRES else None
    if genre and not form and genre == _BADGE_KINDS.get(collection):
        genre = None
    if not genre:
        return f"Issued as {form}" if form else None
    words = genre.replace("-", " ")
    kind = f"{words[:1].upper()}{words[1:]}"
    return f"{kind}, issued as {form}" if form else kind


def build(*, card_version_value: Any, card_notes: Any, card_translator: Any,
          facts: DocumentFacts, collection: str = "", work_key: str | None, note: str | None,
          note_kind: str | None, translator: str | None, language: str | None,
          text_labels: dict, notice: str | None) -> PassageCard | None:
    """One passage's card, or None when its document has no `card_version`.

    `card_translator` is `metadata->>'card_translator'`: None when the document has
    none, "" when the card names no translator. `facts` are the passage's document facts with its
    work's values applied, as the card's header reads them."""
    if card_version(card_version_value) is None:
        return None
    notes = [e for e in entries(card_notes)
             if e["work_key"] is None or e["work_key"] == work_key]
    cautions: list[CardCaution] = []
    unofficial = text_labels.get("text_status") == "unofficial_english"

    lang = language_name(language)
    if lang:
        cautions.append(CardCaution(
            kind="wording", text=f"This passage is in {lang}; it is not included in search."))
    if unofficial:
        latin = text_labels.get("official_latin_url")
        cautions.append(CardCaution(
            kind="wording", text=f"{UNOFFICIAL_ENGLISH} {OFFICIAL_LATIN}",
            link=CardLink(label=OFFICIAL_LATIN, href=latin) if latin else None))
    cautions += [CardCaution(kind=e["kind"], text=e["text"])
                 for e in notes if e["show"] == "card"]
    own = _text(note)
    if own:
        # A note the build stored without a kind is still the passage's caution about
        # itself; the build's check (`checks/card_notes.py`) refuses one, so this is a
        # fallback, never the design.
        kind = note_kind if note_kind in CAUTION_KINDS else "wording"
        cautions.append(CardCaution(kind=kind, text=own))
    superseded = _text(facts.superseded_note)
    if superseded:
        cautions.append(CardCaution(
            kind="authority", text=superseded,
            link=CardLink(label=READ_CURRENT_TEXT, document_id=facts.superseded_by)
            if facts.superseded_by else None))
    # In the order the four kinds are named, keeping stored order within a kind.
    cautions.sort(key=lambda c: CAUTION_KINDS.index(c.kind))
    seen: set[str] = set()
    cautions = [c for c in cautions if not (c.text in seen or seen.add(c.text))]

    record: list[str] = []
    kind = kind_and_form(facts, collection)
    if kind:
        record.append(kind)
    record += [e["text"] for e in notes if e["show"] == "record"]
    if not unofficial:
        # The unofficial-English caution already names its translator (canon 112).
        named = _text(translator)
        if named is None:
            named = (_text(card_translator) if isinstance(card_translator, str)
                     else _text(facts.translation))
        if named:
            record.append(named)
    if text_labels.get("text_source") == "ocr":
        record.append(SCANNED)
    return PassageCard(cautions=cautions, record=list(dict.fromkeys(record)),
                       notice=_text(notice))
