"""The notes under an opened passage, stored with their kind and place (corpus cleanup 4.4).

Spec: docs/corpus-cleanup/P4-P5-republish-expand.md, 4.4 (issue #407). The API builds the
card from what this writes (`services/api/app/card_notes.py`); this module decides it.

At most three slots under a passage's text: "Read with care" (a caution, opened by its
kind: incomplete, wording, authorship or authority), "About this text" (one record line:
kind and form, how the text survives, this passage's translator, "scanned") and the rights
holder's required notice. Seven rules (Carter, 20 Nov 2026): nothing repeats the header,
the role label or another line; only what is true of this passage or the unit a reader
cites, a document-wide fact going to the overview; the translator named once, for this
passage; where the digital text came from never on the card; required notices verbatim and
last; one fixed wording for each kind of note; and a check (`checks/card_notes.py`).

What this writes, in metadata keys as 2.4f did (no migration):

- every document: `metadata.card_version` (`CARD_VERSION`), `metadata.card_notes`, its own
  and its works' notes as `{kind, text, show, work_key?}` entries (`show` is `card`,
  `record` or `overview`; a `record` or `overview` entry may have no kind), and
  `metadata.card_translator`, the translator for the card (works.json's `card_translator`,
  written once by `scripts/document_facts_registry.py` from `card_translator()`; an empty
  string where the card names none because the header's badge or the notice does);
- a passage with a note: its note rewritten to the fixed wording and `metadata.note_kind`;
- a passage from a second edition (a council's; Stromata III in Chadwick's English):
  `metadata.translator`, that edition's translator, so a document translated by two
  people names each passage's own.

The stored facts (`notes`, `attribution_note`, `translation`, `source_credit`) are left as
2.3 and 3.2 set them; the reader's overview and chapter view still read the credit and the
translation. A document's notes here are read from those facts through `FACT_NOTES`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from model import Document, Passage

CARD_VERSION = 1
KINDS = ("incomplete", "wording", "authorship", "authority")
SHOWS = ("card", "record", "overview")


@dataclass(frozen=True)
class Note:
    kind: str | None
    text: str
    show: str = "card"

    def entry(self, work_key: str | None = None, except_work_keys: tuple = ()) -> dict:
        out = {"kind": self.kind, "text": self.text, "show": self.show}
        if work_key is not None:
            out["work_key"] = work_key
        if except_work_keys:
            out["except_work_keys"] = list(except_work_keys)
        return out


def caution(kind: str, text: str) -> Note:
    return Note(kind, text, "card")


def overview(text: str, kind: str | None = None) -> Note:
    return Note(kind, text, "overview")


def record(text: str) -> Note:
    return Note(None, text, "record")


# --------------------------------------------------------------------------- the wordings

# Each kind of note has one fixed wording (rule 6). They name no translator, author or
# document: the record line, the header and the overview do (rules 1 and 3).
NOT_AVAILABLE = "not available on TheoCorpus at present"
ABRIDGED = caution("incomplete", "Abridged by the translator.")
SUMMARY = caution("incomplete", "A summary by the translator, not the full text of this canon.")
EXTRACT = caution("incomplete", f"An extract; the full text is {NOT_AVAILABLE}.")
CHRONICLE = caution("wording", "Matthew Paris's version, not the council's acts.")
ANASTASIUS = caution("wording", "From Anastasius's Latin version of the acts.")
HEFELE = caution("wording", "From Hefele's account of the session, not the council's acts.")
RECENSION = caution("wording", "Translated from another recension of this canon.")
FROM_FRENCH = caution("wording", "Translated from a French translation, not from the Latin.")
PARTIAL = caution("incomplete", "This printing gives only part of this paragraph.")
# How a document's own note says it is printed only in extract (1.3d's encyclicals).
EXTRACT_DOCUMENT_OPENINGS = ("Only an extract is given:", "Only extracts are given:")
LATIN_OMITTED = overview(
    "Some passages are omitted: the translators left them in Latin and no public-domain "
    "English translation exists.", "incomplete")

# A passage's note as the adapters and the passage registry write it, to the note the card
# shows, or None where the role label or a document note already says it. Every note a
# build carries must be here: the check refuses one
# that is not, so a new note is given its kind before it ships.
PASSAGE_NOTES: dict[str, Note | None] = {
    "Abridged in Schroeder (1937).": ABRIDGED,
    "Summarised by Schroeder (1937); not the full text of this canon.": SUMMARY,
    "Extract, in R. J. Deferrari's translation of Denzinger, The Sources of Catholic Dogma "
    "(1957).": EXTRACT,
    "Matthew Paris's version, in J. A. Giles's translation (1853).": CHRONICLE,
    "Matthew Paris's version, in J. A. Giles's translation (1853). Matthew Paris dates the "
    "bull 16 July; the council's acts give 17 July.": caution(
        "wording", "Matthew Paris's version, not the council's acts. He dates the bull "
                   "16 July; the acts give 17 July."),
    "From the Latin of Anastasius, in R. J. Deferrari's translation of Denzinger (1957).":
        ANASTASIUS,
    "From Hefele's account of the session, in W. R. Clark's translation (1896).": HEFELE,
    "Translated from another recension of this canon.": RECENSION,
    # The rejected-voice label says "condemned"; the sentence's absence is the caution,
    # and the caution names the bull that states the council's verdict (5.9).
    "Articles the council condemned, not its teaching. Its sentence is not available on "
    "TheoCorpus; Martin V's Inter Cunctas (1418) states its verdict. Translated by R. J. "
    "Deferrari (1957).": caution(
        "incomplete", "The council's sentence is not available on TheoCorpus; Martin V's "
                      "Inter Cunctas (1418) states its verdict."),
    # Every passage of Exsurge Domine: the label says it, the overview says the rest.
    "Propositions of Martin Luther that the bull condemned, not its teaching. The rest of "
    "the bull is not available on TheoCorpus at present. Translated by R. J. Deferrari "
    "(1957).": None,
    **{f"Not enacted as a canon: a passage from the minutes of the fourth session, which "
       f"later Greek collections count as canon {n}.": caution(
           "authority", f"Not enacted as a canon: a passage from the minutes of the fourth "
                        f"session, which later Greek collections count as canon {n}.")
       for n in (29, 30)},
    "This canon is a later addition.": caution(
        "authorship", "This canon is a later addition."),
    PARTIAL.text: PARTIAL,
    "This printing cuts the paragraph short with “&c.”": caution(
        "incomplete", "This printing cuts the paragraph short with “&c.”"),
    "Chapters 11 and 12 are a later addition by another hand.": caution(
        "authorship", "Chapters 11 and 12 are a later addition by another hand."),
    "The Latin text ends this article with a short reply to all the objections together, "
    "which the English translation does not print.": caution(
        "incomplete", "The Latin text ends this article with a short reply to all the "
                      "objections together, which the English translation does not print."),
}
# `summa._missing_note`'s wordings, each exactly as built: a new one stops the build
# until it is added here.
for _units in ("ad 2, ad 3", "sc 2"):
    _missing = f"The English translation omits part of this article's Latin text ({_units})."
    PASSAGE_NOTES[_missing] = caution("incomplete", _missing)

# A document's or work's note in the stored facts (`attribution_note`, `notes`), to the
# notes the card and the overview show. An empty tuple drops it: the header already says
# it, with the author's label and its certainty tag (rule 1).
FACT_NOTES: dict[str, tuple[Note, ...]] = {
    # The Roman Catechism (5.5): read with care on every card; the header names the work.
    "Catechism of the Council of Trent, a historical catechism; for current teaching see "
    "the Catechism of the Catholic Church": (caution(
        "authority", "A historical catechism; for current teaching see the Catechism of the "
                     "Catholic Church."),),
    # The Code of Canon Law: excerpt-only, so its Library row shows it.
    "Canons 295, 296, 579, 695 and 700 are not shown: their current text has no "
    "English translation. The official Latin is on vatican.va.": (overview(
        "Canons 295, 296, 579, 695 and 700 are not shown: their current text has no "
        "English translation. The official Latin is on vatican.va.", "incomplete"),),
    # 5.6b's Life of St. Teresa (`ingest.theologians.LIFE_NOTE`): a document-wide fact.
    "Teresa's chapter headings, left out of the original translation, follow Benedict "
    "Zimmerman's 1904 edition.": (overview(
        "Teresa's chapter headings, left out of the original translation, follow Benedict "
        "Zimmerman's 1904 edition."),),
    # 5.6b's Story of a Soul (`ingest.theologians.THERESE_NOTE`): a document-wide fact.
    "Its Counsels and Reminiscences are her sayings as her novices recorded them.": (
        overview("Its Counsels and Reminiscences are her sayings as her novices recorded "
                 "them."),),
    # 5.6b's Autobiography of St. Ignatius (`ingest.theologians.IGNATIUS_NOTE`).
    "Ignatius dictated it to Luis Gonçalves da Câmara, whose preface opens it.": (
        overview("Ignatius dictated it to Luis Gonçalves da Câmara, whose preface opens "
                 "it."),),
    # 3.2's labels.
    # The header names the Church of Smyrna.
    "A letter of the Church of Smyrna on Polycarp's death; its writer, Evarestus, is named "
    "in chapter XX.": (overview("Its writer, Evarestus, is named in chapter XX."),),
    "A legendary account.": (caution("authority", "A legendary account."),),
    "Not by Justin Martyr.": (),
    "Not by Justin Martyr. Riedweg (1994) proposes Marcellus of Ancyra, with a question "
    "mark.": (caution("authorship", "Riedweg (1994) proposes Marcellus of Ancyra as the "
                                    "author, with a question mark."),),
    "Not by Justin Martyr; date uncertain.": (overview("Its date is uncertain."),),
    "Authorship disputed; Heimgartner (2001) assigns it to Athenagoras.": (
        caution("authorship", "Heimgartner (2001) assigns it to Athenagoras."),),
    "An account of the trial and death of Justin and his companions; its author is "
    "unknown.": (overview("An account of the trial and death of Justin and his companions."),),
    "Its attribution to Pamphilus is doubtful.": (),
    "Its attribution to Methodius is doubtful.": (),
    "Its attribution to Lactantius is doubtful.": (),
    "Not by Gregory Thaumaturgus.": (),
    "Written by Hegemonius; Archelaus is the bishop who debates Mani in it.": (
        overview("Archelaus is the bishop who debates Mani in it."),),
    "This is Jerome's revision of the commentary: he replaced Victorinus's comments on the "
    "thousand-year reign (Revelation 20 to 22) with his own.": (caution(
        "wording", "Jerome's revision of the commentary: he replaced the comments on the "
                   "thousand-year reign (Revelation 20 to 22) with his own."),),
    "An Egyptian church order, about 336 to 340.": (record("An Egyptian church order, "
                                                           "about 336 to 340"),),
    "Its view on rebaptizing heretics was not adopted by the Church.": (
        caution("authority", "Its view on rebaptizing heretics was not adopted by the "
                             "Church."),),
    "Its ruling on rebaptizing heretics was not adopted by the Church.": (
        caution("authority", "Its ruling on rebaptizing heretics was not adopted by the "
                             "Church."),),
    "Its author is unknown; the editors printed it with Caius's fragments on one scholar's "
    "guess.": (caution("authorship", "The editors printed it with Caius's fragments on one "
                                     "scholar's guess."),),
    "Compiled about 380. The Latin West received canons 1 to 50 through Dionysius "
    "Exiguus; all 85 were confirmed by the Council in Trullo (canon 2) and Nicaea II "
    "(canon 1).": (record("Compiled about 380"), caution(
        "authority", "The Latin West received canons 1 to 50 through Dionysius Exiguus; all "
                     "85 were confirmed by the Council in Trullo (canon 2) and Nicaea II "
                     "(canon 1).")),
    "Some passages are omitted: the translators left them in Latin and no public-domain "
    "English translation exists.": (LATIN_OMITTED,),
    # 3.2's fragment collections: how the text survives, on the record line.
    **{text: (record(text.rstrip(".")),) for text in (
        "Preserved in quotations by later writers, chiefly Irenaeus (Against Heresies) and "
        "Eusebius (Church History).",
        "Preserved in the Sacra Parallela, a collection of quotations attributed to John of "
        "Damascus.",
        "Preserved in quotations by later writers, among them Tatian, Irenaeus, Methodius "
        "and the Sacra Parallela attributed to John of Damascus.",
        "Preserved chiefly in Eusebius (Church History) and in catenae, medieval chains of "
        "comments on Scripture.",
        "Preserved in Eusebius, Church History.",
        "Preserved chiefly in Eusebius (Church History and Preparation for the Gospel) and "
        "Athanasius.",
        "Preserved in catenae, medieval chains of comments on Scripture.",
        "Preserved chiefly in George Syncellus's Chronography and in Eusebius.",
        "Preserved in Cyril of Jerusalem's Catechetical Lectures.",
        "Preserved in quotations by later writers.",
        "Preserved chiefly in Photius's Library and Epiphanius's Panarion.",
        "Preserved in Photius's Library and other later collections.",
        "Preserved in catenae and the Sacra Parallela.",
    )},
    # 1.3d's partial printings: what the document leaves out is document-wide (rule 2).
    "Only an extract of this encyclical is given, in R. J. Deferrari's translation of "
    "Denzinger (1957): the five teachings on usury in paragraph 3. The rest is not "
    "available on TheoCorpus at present.": (overview(
        f"Only an extract is given: the five teachings on usury in paragraph 3. The rest is "
        f"{NOT_AVAILABLE}.", "incomplete"),),
    "Only an extract of this encyclical is given, in R. J. Deferrari's translation of "
    "Denzinger (1957): paragraph 8. The rest is not available on TheoCorpus at present.": (
        overview(f"Only an extract is given: paragraph 8. The rest is {NOT_AVAILABLE}.",
                 "incomplete"),),
    "Only extracts of this encyclical are given, in R. J. Deferrari's translation of "
    "Denzinger (1957): paragraph 7, the first part of paragraph 8, and paragraph 9. The "
    "rest is not available on TheoCorpus at present.": (overview(
        f"Only extracts are given: paragraph 7, the first part of paragraph 8, and "
        f"paragraph 9. The rest is {NOT_AVAILABLE}.", "incomplete"),),
    # 5.9's Inter Cunctas: no site page, so nothing is held; the overview names the rest.
    "Only extracts of this bull are given, in R. J. Deferrari's translation of Denzinger "
    "(1957): questions 5–8 and 11–39 of those to be put to followers of Wyclif and Hus. "
    "Questions 1–4, 9 and 10, and the rest of the bull, are not available on TheoCorpus at "
    "present.": (overview(
        f"Only extracts are given: questions 5–8 and 11–39. Questions 1–4, 9 and 10, and "
        f"the rest of the bull, are {NOT_AVAILABLE}.", "incomplete"),),
    "This English printing (Interesting Letters of Clement XIV, 1777, translated from the "
    "French) omits paragraph 9; it is not available on TheoCorpus at present.": (
        FROM_FRENCH,
        overview(f"This printing omits paragraph 9; it is {NOT_AVAILABLE}.", "incomplete")),
    "This English printing (Interesting Letters of Clement XIV, 1777, translated from the "
    "French) omits paragraphs 3, 4 and 9 and shortens paragraphs 2 and 8 to \"&c.\"; what "
    "it leaves out is not available on TheoCorpus at present.": (
        FROM_FRENCH,
        overview(f"This printing omits paragraphs 3, 4 and 9 and shortens paragraphs 2 and 8 "
                 f"to \"&c.\"; what it leaves out is {NOT_AVAILABLE}.", "incomplete")),
    "This English printing (The Jesuit, Boston, 1829) is abridged: it shortens several "
    "paragraphs and omits paragraphs 2, 8, 9, 11 and 13; what it leaves out is not "
    "available on TheoCorpus at present.": (
        overview(f"This printing shortens several paragraphs, which it does not name, and "
                 f"omits paragraphs 2, 8, 9, 11 and 13; what it leaves out is "
                 f"{NOT_AVAILABLE}.", "incomplete"),),
    "This English printing (The Rambler, 1850) omits paragraphs 21–24, 26 and 31–33; they "
    "are not available on TheoCorpus at present.": (overview(
        f"This printing omits paragraphs 21–24, 26 and 31–33; they are {NOT_AVAILABLE}.",
        "incomplete"),),
    "This English printing (The Dublin Review, 1859) quotes paragraph 1 and part of "
    "paragraph 3; the address, paragraph 2 and the rest of paragraph 3 are not available "
    "on TheoCorpus at present.": (overview(
        f"This printing quotes paragraph 1 and part of paragraph 3; the address, paragraph 2 "
        f"and the rest of paragraph 3 are {NOT_AVAILABLE}.", "incomplete"),),
    "This English printing (The Rambler, 1860) quotes paragraph 6 and parts of paragraphs "
    "3, 5, 7 and 8; the address and paragraphs 1–2, 4 and 9–13 are not available on "
    "TheoCorpus at present.": (overview(
        f"This printing quotes paragraph 6 and parts of paragraphs 3, 5, 7 and 8; the "
        f"address and paragraphs 1–2, 4 and 9–13 are {NOT_AVAILABLE}.", "incomplete"),),
    "This English printing (The American Annual Cyclopaedia, 1868) quotes most of "
    "paragraph 1 and the first part of paragraph 2; the address, the rest of paragraph 2 "
    "and paragraphs 3–10 are not available on TheoCorpus at present.": (overview(
        f"This printing quotes most of paragraph 1 and the first part of paragraph 2; the "
        f"address, the rest of paragraph 2 and paragraphs 3–10 are {NOT_AVAILABLE}.",
        "incomplete"),),
}

# Notes a document gets that no stored fact holds, by works.json `work_id`: what a
# passage note on every passage said about the document (rule 2).
DOCUMENT_NOTES: dict[str, tuple[Note, ...]] = {
    # Both of its paragraphs are printed only in part.
    "encyclicals/levate": (caution("incomplete", "This printing gives only part of each "
                                                 "paragraph."),),
    "papal-documents/exsurge-domine": (overview(
        f"Only the condemned propositions and the censure are given; the rest of the bull "
        f"is {NOT_AVAILABLE}.", "incomplete"),),
}

# The translator of each scanned edition a council takes passages from (the passage's
# `metadata.scan_id`, 1.2f), for a council translated by two people (2.3's
# COMBINED_CREDITS): each passage names its own (rule 3).
SCAN_TRANSLATORS = {
    "DisciplinaryCouncils": "Translated by H. J. Schroeder (1937)",
    "sources-of-catholic-dogma-loreto-reprint":
        "Translated by Roy J. Deferrari (1957), in The Sources of Catholic Dogma",
    "matthewparisseng02pari": "Translated by J. A. Giles (1853)",
    "ahistoryofthecou05hefeuoft": "Translated by William R. Clark (1896)",
    "authoritative01chry": "Translated by James Chrystal (1895)",
    # Stromata III, which ANF left in Latin (#399).
    "alexandrianchris012826mbp": "Translated by Henry Chadwick (1954)",
}
TRANSLATOR_COLLECTIONS = ("councils", "church-fathers")


# --------------------------------------------------------------------------- translator

# The stored translation (2.3) as the card names it, where it is not a sentence already.
_TRANSLATIONS = {
    "Vatican English": "The Vatican's English translation",
    # The Bible's badge names it (rule 1), and so does the Catechism's required notice.
    "WEB-C": "",
    "United States edition (1997)": "",
    # The Devout Life's 1876 translation names no translator (5.6b; R6).
    "Anonymous translation (Rivingtons, 1876)": "Anonymous translation (Rivingtons, 1876)",
}
_TAILS = re.compile(r"(?:\.\s+(?:Sourced via|Text:).*|;.*|,\s*(?:abridged|extract)\s*)$")
_SENTENCE = re.compile(r"^(Translated by|Translation|Official English|From Hefele)")
_SERIES = ("Ante-Nicene Fathers", "Nicene and Post-Nicene Fathers")
# Translators that are a community, read with "the": "the Benedictines of Stanbrook" (5.6b).
_BODIES = ("Fathers of ", "Benedictines of ")


def card_translator(credit: str | None, translation: str | None) -> str | None:
    """The translator the card names, written once into works.json from 2.3's credit line
    or translation: the credit's translator sentence without where the text came from
    ("Sourced via …", "Text: …"), a second edition (after ";") or "abridged" (a caution
    says it); else the translation, named as a reader reads it; "" where the header's badge
    or the required notice already names it; None where nothing names one, which the
    registry's validation and the build's check refuse."""
    credit = (credit or "").strip()
    if _SENTENCE.match(credit):
        return _TAILS.sub("", credit).strip()
    value = (translation or "").strip()
    if value in _TRANSLATIONS:
        return _TRANSLATIONS[value]
    if not value:
        return None
    if value.startswith(_SERIES):
        return re.sub(r"(?<=\d)-(?=\d)", "–", value)  # a date range takes an en dash
    if value.startswith(_BODIES):
        return f"Translated by the {value}"
    return f"Translated by {value}"


# --------------------------------------------------------------------------- applying

class CardNoteError(ValueError):
    """A note the tables above do not hold. A ValueError, so a build reports it."""


def passage_note(note: str) -> Note | None:
    """The card's note for a passage note as built, or None where it goes."""
    if note in PASSAGE_NOTES:
        return PASSAGE_NOTES[note]
    raise CardNoteError(f"no card wording for the passage note {note!r}: add it to "
                        "card_notes.PASSAGE_NOTES with its kind")


def fact_notes(text: str | None) -> tuple[Note, ...]:
    if not text:
        return ()
    if text not in FACT_NOTES:
        raise CardNoteError(f"no card wording for the note {text!r}: add it to "
                            "card_notes.FACT_NOTES with its kind and place")
    return FACT_NOTES[text]


def document_entries(document: Document, work_id: str | None) -> list[dict]:
    """The document's `card_notes`: its own notes, then each work's, in stored order."""
    entries = []
    for field in ("attribution_note", "notes"):
        # A work that clears the field ("", 3.2: the Muratorian Fragment's notes) is not
        # covered by the document's note: the entry leaves its passages out.
        cleared = tuple(w.work_key for w in document.works if getattr(w, field) == "")
        entries += [n.entry(except_work_keys=cleared)
                    for n in fact_notes(getattr(document, field))]
    entries += [n.entry() for n in DOCUMENT_NOTES.get(work_id or "", ())]
    for w in document.works:
        entries += [n.entry(w.work_key) for f in (w.attribution_note, w.notes)
                    for n in fact_notes(f)]
    return entries


def _passage(p: Passage, translator: str | None) -> Passage:
    metadata = dict(p.metadata or {})
    metadata.pop("note_kind", None)
    note = passage_note(p.note) if p.note else None
    if note is not None:
        metadata["note_kind"] = note.kind
    if translator:
        metadata["translator"] = translator
    else:
        metadata.pop("translator", None)
    return replace(p, note=note.text if note else None, metadata=metadata or None)


def _passage_translator(document: Document, p: Passage, card: str) -> str | None:
    if document.collection not in TRANSLATOR_COLLECTIONS:
        return None
    named = SCAN_TRANSLATORS.get((p.metadata or {}).get("scan_id") or "")
    return named if named and named != card else None


def apply(document: Document, entry: dict | None) -> Document:
    """The document with its card notes stored (4.4). `entry` is its works.json entry,
    which holds `card_translator` and `work_id`."""
    entry = entry or {}
    card = entry.get("card_translator")
    if card is None:
        card = card_translator(document.source_credit, document.translation)
    passages = [_passage(p, _passage_translator(document, p, card)) for p in document.passages]
    entries = document_entries(document, entry.get("work_id"))
    passages = _without_document_wide(passages, entries)
    metadata = {**(document.metadata or {}), "card_version": CARD_VERSION,
                "card_notes": entries, "card_translator": card}
    return replace(document, passages=passages, metadata=metadata)


def _without_document_wide(passages: list[Passage], entries: list[dict]) -> list[Passage]:
    """The passages without the extract note when the document says, in its own extract
    note, which part is given (rule 2): an encyclical printed only in extract. A passage
    printed only in part keeps its own caution. Any other note stays, and the check
    refuses one on every passage, so a repeated caution is never dropped unseen."""
    if not any(e["text"].startswith(EXTRACT_DOCUMENT_OPENINGS) and "work_key" not in e
               for e in entries):
        return passages
    out = []
    for p in passages:
        if p.note == EXTRACT.text:
            metadata = {k: v for k, v in (p.metadata or {}).items() if k != "note_kind"}
            p = replace(p, note=None, metadata=metadata or None)
        out.append(p)
    return out
