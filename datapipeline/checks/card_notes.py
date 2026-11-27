"""The notes under an opened passage are said once, each with its kind (corpus cleanup 4.4).

Run by every build and dry run (`publication.prepare`), on documents `card_notes.apply`
has written. It refuses:

- a caution without a kind: a passage note without `note_kind`, a `card_notes` entry
  shown on the card without one, or an unknown kind or place;
- an overview note tied to a work (`work_key`): the overview lists only the document's
  own notes, so it would show nowhere;
- a note naming the passage's translator, author or document title (rules 1 and 3);
- the same passage note on every passage of a document: it belongs on the document as a
  `card_notes` entry, which may still show on every card;
- a document whose card can name no translator: no `card_translator`, and an empty
  `translation` with no passage `translator` keys (an empty `card_translator` is the
  decision that the header or the notice names it, or that the work was written in
  English);
- a document without `card_version`.
"""
from __future__ import annotations

import re
from collections import Counter

import card_notes
from model import Document

# A translator's surname, the word before a year in parentheses: "H. J. Schroeder (1937)".
_SURNAME = re.compile(r"([A-Z][\w'’-]+)\s*\(\d{4}")
# Authors whose names are words a note may use about something else.
_GENERIC_AUTHORS = {"Anonymous", "Catholic Church"}


def _translator_names(*translators: str | None) -> set[str]:
    return {m for t in translators if t for m in _SURNAME.findall(t)}


def _names_in(text: str, names: set[str]) -> list[str]:
    return sorted(n for n in names if re.search(rf"\b{re.escape(n)}\b", text))


def problems(document: Document) -> list[str]:
    name = document.title
    out: list[str] = []
    metadata = document.metadata or {}
    if metadata.get("card_version") != card_notes.CARD_VERSION:
        return [f"{name}: no card_version {card_notes.CARD_VERSION}"]
    card_translator = metadata.get("card_translator")
    work_authors = {w.work_key: w.author for w in document.works if w.author}

    def named(text: str, translators: set[str], passages) -> list[str]:
        """The names `text` repeats on the passages it shows on: a translator's, the
        author each one's header shows (its work's, inside a work) and the title."""
        authors = {(work_authors.get(p.work_key or "") or document.author or "").strip()
                   for p in passages}
        found = _names_in(text, translators)
        found += sorted(a for a in authors
                        if a and a not in _GENERIC_AUTHORS and a in text)
        if document.title and document.title in text:
            found.append(document.title)
        return found

    for e in metadata.get("card_notes") or []:
        kind, show, text = e.get("kind"), e.get("show"), e.get("text") or ""
        if show not in card_notes.SHOWS:
            out.append(f"{name}: card note {text!r} has place {show!r}")
        if kind is not None and kind not in card_notes.KINDS:
            out.append(f"{name}: card note {text!r} has kind {kind!r}")
        if show == "card" and kind is None:
            out.append(f"{name}: caution without a kind: {text!r}")
        # The overview lists the document's own notes; a work's would show nowhere.
        if show == "overview" and e.get("work_key"):
            out.append(f"{name}: overview note {text!r} names work {e['work_key']}; "
                       "a work's note shows on its passages (card or record)")
        # Every translator a passage it shows on names: the card's and the passages' own.
        skip = e.get("except_work_keys") or []
        shown_on = [p for p in document.passages
                    if p.work_key == e.get("work_key")
                    or (not e.get("work_key") and p.work_key not in skip)]
        bad = named(text, _translator_names(
            card_translator, *((p.metadata or {}).get("translator") for p in shown_on)),
            shown_on)
        if bad:
            out.append(f"{name}: card note {text!r} names {', '.join(bad)}")

    notes = Counter()
    passage_translators = False
    for p in document.passages:
        pm = p.metadata or {}
        passage_translators |= bool(pm.get("translator"))
        if not p.note:
            continue
        notes[p.note] += 1
        if pm.get("note_kind") not in card_notes.KINDS:
            out.append(f"{name} {p.anchor}: passage note without a kind: {p.note!r}")
        bad = named(p.note, _translator_names(pm.get("translator") or card_translator),
                    [p])
        if bad:
            out.append(f"{name} {p.anchor}: note {p.note!r} names {', '.join(bad)}")
    for note, count in notes.items():
        if count == len(document.passages):
            out.append(f"{name}: the note {note!r} is on every passage; store it on the "
                       "document (card_notes.DOCUMENT_NOTES or FACT_NOTES)")

    if card_translator is None and not document.translation and not passage_translators:
        out.append(f"{name}: the card can name no translator (no card_translator, no "
                   "translation, no passage translator)")
    return out


def check(documents: list[Document]) -> None:
    """Raise when any document breaks a rule above."""
    found = [p for d in documents for p in problems(d)]
    if found:
        more = f" (and {len(found) - 20} more)" if len(found) > 20 else ""
        raise ValueError("REFUSING: card notes (4.4): " + "; ".join(found[:20]) + more)
