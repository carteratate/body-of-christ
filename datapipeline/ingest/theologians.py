"""Theologians and spiritual writers from CCEL ThML (corpus-cleanup 5.6b, issue #207).

Each work is one vendored ThML file under `sources/theologians/` and one entry in
`WORKS`: its labels, its dates and translation, and which of the file's divs are the
author's. The file's other divs (title page, editors' introductions and prefaces, annals,
indexes) are never read, so an editor's essay cannot reach a passage by default. Inside a
chapter, rule G drops the editors' paragraphs (`_WorkEditor`), and their notes leave
the text as everywhere (`ingest.thml_doc`).

The works' own headings are chapter labels, and a heading the work prints longer than
its label stays in the text, marked through `headings.py` (#445; Carter, 23 Nov 2026):
each chapter of the Interior Castle opens with Teresa's "This chapter treats of…", her
arguments of the Life's chapters (printed together before the book) each open their
chapter, and a book's, part's or mansion's own heading opens its first chapter. Levels:
1 for a division the label names, 2 below it, 3 deeper (`headings.py`).

The documents are built under the source key `COLLECTION` (`ingest.keys.THEOLOGIANS`,
`medieval`), which `publication.py` publishes as the `theologians` collection since 5.1b.3.
The files are in `sources/theologians/`, and each document's source key is its file's
path there.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable

from xml.etree.ElementTree import Element      # builds an element, parses nothing

import defusedxml.ElementTree as ET

import headings
from model import Document
from normalize.caps import smart_title_case
from ingest import gutenberg_text
from ingest.common import _block_text, _build_parent_map
from ingest.keys import THEOLOGIANS
from ingest.editorial import PLAIN_CALLERS, ChapterEdit, Editor, Removed
from ingest.thml_doc import LABEL_MAX_CHARS, ChapterPlan, _clip, make_doc

# The source key these works are built under (published as `theologians`).
COLLECTION = THEOLOGIANS
SOURCE_DIR = "theologians"
_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", SOURCE_DIR)

CCEL_CREDIT = "Sourced via CCEL.org"
# The Devout Life's translation as the card names it (`card_notes._TRANSLATIONS`).
ANONYMOUS_1876 = "Anonymous translation (Rivingtons, 1876)"
# Teresa's headings of the Life's chapters are not Lewis's: he left them out, following
# Bouix, and Zimmerman's introduction to the 1904 edition prints them before the book.
# The Counsels and Reminiscences are her words as others set them down.
LAWRENCE_NOTE = ("Its Conversations are attributed to Joseph de Beaufort; the close of the "
                 "Fourth draws on other accounts.")
ANONYMOUS_1852 = "Anonymous translation (Dunigan, 1852)"
ANONYMOUS_1895 = "Anonymous translation (Revell, about 1895)"
IGNATIUS_NOTE = ("Ignatius dictated it to Luis Gonçalves da Câmara, whose preface "
                 "opens it.")
THERESE_NOTE = ("Its Counsels and Reminiscences are her sayings as her novices recorded "
                "them.")
LIFE_NOTE = ("Teresa's chapter headings, left out of the original translation, follow "
             "Benedict Zimmerman's 1904 edition.")


@dataclass(frozen=True)
class ThmlWork:
    file: str                  # under sources/theologians/
    url: str                   # where CCEL serves it (the rights row's source_url)
    title: str
    author: str
    year: int                  # when the author finished it
    translation: str           # as the card reads it after "Translated by", or whole
    chapters: Callable         # root -> [(book, div, ChapterPlan)]
    genre: str                 # D5's writer value, or `other` (registry.genres)
    # Paragraph classes the work prints its own headings in (a chapter's title, Teresa's
    # chapter headings): kept in the text though they repeat a title line, and set as
    # printed (no opening-capitals change); the chapter plans mark them.
    title_classes: frozenset[str] = frozenset()
    notes: str | None = None   # the document's note (2.3's `notes`)
    # A Project Gutenberg text (`ingest.gutenberg_text`): its eBook number, recorded as
    # provenance, and the heading its notes stand under.
    ebook: int | None = None
    notes_heading: str | None = None

    @property
    def source_key(self) -> str:
        return f"{SOURCE_DIR}/{self.file}"


def _read_root(path: str):
    with open(path, encoding="utf-8") as f:
        xml = f.read()
    xml = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)
    return ET.fromstring(xml)


def _div(root, div_id: str):
    for d in root.iter():
        if isinstance(d.tag, str) and d.tag.startswith("div") and d.get("id") == div_id:
            return d
    raise ValueError(f"no div {div_id!r}")


def _text(elem) -> str:
    return " ".join(_block_text(elem).split())


# --------------------------------------------------------------------------- Teresa

# The Interior Castle (Stanbrook, 1921): Teresa's preface, the seven mansions' chapters
# and her epilogue. Left out: the title page (i), Zimmerman's note on the edition (ii),
# his introduction (iii), his introductory note to VI, ch. iii (x.iii), the subject
# index (xiii) and CCEL's indexes (xiv).
_CASTLE_MANSIONS = ("v", "vi", "vii", "viii", "ix", "x", "xi")
_CASTLE_EDITOR_DIVS = frozenset({"x.iii"})
# "Chapter II. The Human Soul." -> "Chapter II. The Human Soul"
_CHAPTER_TITLE = re.compile(r"^Chapter ([IVXLC]+)\.\s+(.+?)\.?$")


def _castle_chapters(root):
    preface = _div(root, "iv")
    out = [(None, preface, ChapterPlan(label="Preface", headings=_castle_heading(preface)))]
    for mansion_id in _CASTLE_MANSIONS:
        mansion = _div(root, mansion_id)
        book = (mansion.get("title") or "").strip()
        # The mansion's own heading ("THE FIRST MANSIONS", `<h1>`) opens its first chapter.
        lead = ((_text(mansion.find("h1")), 1),)
        first = True
        for ch in mansion:
            if not (isinstance(ch.tag, str) and ch.tag == "div2"):
                continue
            if ch.get("id") in _CASTLE_EDITOR_DIVS:
                continue
            m = _CHAPTER_TITLE.match((ch.get("title") or "").strip())
            if not m:
                raise ValueError(f"teresa-castle2.xml: unexpected chapter title "
                                 f"{ch.get('title')!r}")
            out.append((book, ch, ChapterPlan(label=f"Chapter {m.group(1)}. {m.group(2)}",
                                              headings=_castle_heading(ch),
                                              lead=lead if first else ())))
            first = False
    out.append((None, _div(root, "xii"), ChapterPlan(label="Epilogue")))
    return out


def _castle_heading(chapter) -> tuple[tuple[str, int, bool], ...]:
    """Teresa's heading of a Castle chapter ("THIS CHAPTER TREATS OF…"), or her title
    line over the preface, printed in capitals as the div's first `Centered` paragraph:
    level 2, under the chapter's label."""
    for block in chapter:
        if block.tag != "p" or not _text(block):
            continue          # an empty paragraph stands before it in VI ch. ii and IV
        return ((block.get("id"), 2, False),) if block.get("class") == "Centered" else ()
    return ()


# The Life (Lewis, 1904): Teresa's prologue and forty chapters, then the Relations she
# wrote for her confessors, which Lewis prints after them. Left out: the frontispiece and
# title page (i, ii), the contents (iii), Zimmerman's introduction (iv), Teresa's
# arguments of the chapters gathered before the book (v; each opens its chapter, level 2),
# Lewis's preface (vi), the annals (vii), the index (x) and CCEL's indexes (xi).
# A sentence's end in an argument line; "St." is not one.
_FIRST_SENTENCE = re.compile(r"(?<!\bSt)\.\s+")
_LIFE_ARGUMENT = re.compile(r"^(?:J\.H\.S\.\s*)?Chapter ([IVXLC]+)\.\s*[—-]+\s*(.+)$")


def _life_chapters(root):
    headings = _life_headings(_div(root, "v"))
    life, relations = _div(root, "viii"), _div(root, "ix")
    out = []
    for ch in life:
        if not (isinstance(ch.tag, str) and ch.tag == "div2"):
            continue
        kind = (ch.get("type") or "").lower()
        if kind == "prologue":
            out.append((None, ch, ChapterPlan(label="Prologue")))
            continue
        if kind != "chapter":
            raise ValueError(f"teresa-life.xml: unexpected div {ch.get('id')!r} in the Life")
        n = (ch.get("n") or "").strip()
        argument = ch.find("argument")
        if argument is None or not n:
            raise ValueError(f"teresa-life.xml: chapter {ch.get('id')!r} has no number "
                             f"or argument")
        # The label takes the first sentence of the edition's argument line, which is
        # Lewis's; Teresa's own heading opens the chapter's text, level 2.
        subject = _FIRST_SENTENCE.split(_text(argument), 1)[0].rstrip(".")
        out.append((None, ch, ChapterPlan(label=f"Chapter {n}. {subject}",
                                          lead=((headings[n], 2),))))
    # "The Relations." (`<h2>`) opens the first of them, level 1.
    lead = ((_text(relations.find("h2")), 1),)
    for rel in relations:
        if not (isinstance(rel.tag, str) and rel.tag == "div2"):
            continue
        if (rel.get("type") or "").lower() != "relation" or not rel.get("n"):
            raise ValueError(f"teresa-life.xml: unexpected div {rel.get('id')!r} in the "
                             f"Relations")
        out.append(("The Relations", rel, ChapterPlan(label=f"Relation {rel.get('n')}",
                                                      lead=lead)))
        lead = ()
    return out


def _life_headings(arguments) -> dict[str, str]:
    """Teresa's own heading of each chapter of the Life, by its Roman number, from "St.
    Teresa's Arguments of the Chapters" (div v), notes left out."""
    out = {}
    for block in arguments:
        if block.tag != "p":
            continue
        m = _LIFE_ARGUMENT.match(_text(block))
        if m:
            out[m.group(1)] = m.group(2).strip()
    if len(out) != 40:
        raise ValueError(f"teresa-life.xml: {len(out)} chapter arguments, not 40")
    return out


# What is no passage text though it stands in the author's chapters, by file: paragraphs
# by class (an editor's), which the editor drops; and divs whose own paragraphs are the
# author's headings (the Life's arguments, which open their chapters through `lead`; a
# Treatise book's title; the Devout Life's contents), which the build never reads. The
# checks' extractor (`checks.source_text.thml_units`) reads both so.
NOT_BODY_CLASSES = {"teresa-castle2.xml": {"Outline": "apparatus"},
                    # O'Conor's chapter summaries, which name the labels.
                    "ignatius-autobiography.xml": {"chapterHead": "apparatus"}}
HEADING_DIVS = {"teresa-life.xml": frozenset({"v"}),
                "desales-devout_life.xml": frozenset({"ii"}),
                # The Treatise's twelve book divs, ii to xiii (`_LOVE_BOOKS`).
                "desales-love.xml": frozenset({"ii", "iii", "iv", "v", "vi", "vii", "viii",
                                               "ix", "x", "xi", "xii", "xiii"})}
# Single paragraphs by id: in the Life, Báñez's signed note on the manuscript after
# Teresa's last line (ch. xl) and the transcriber's page marker "{p. 479}" (Relation XI);
# in the Castle, the printers' colophon.
NOT_BODY_PARAGRAPHS = {"teresa-life.xml": {"viii.xli-p58": "apparatus",
                                           "ix.xi-p12": "apparatus"},
                       # The printers' colophon after the Castle's last "Amen" ("HERE ENDS
                       # THE INTERIOR CASTLE … PRINTED BY THE BENEDICTINES OF STANBROOK").
                       "teresa-castle2.xml": {"xii-p3": "apparatus"},
                       # "THE END." after the Treatise's last chapter: the printer's.
                       "desales-love.xml": {"xiii.xiii-p17": "apparatus"},
                       # The Story of a Soul: the editors' opening of the Counsels, their
                       # captions over letters and prayers ("(Written during her retreat
                       # …)", "Written for a Novice"), one bracketed account of the
                       # circumstances, and "END OF THE AUTOBIOGRAPHY".
                       "therese-autobio.xml": {pid: "apparatus" for pid in (
                           "xxi-p1", "xxiii.i-p1", "xxiii.ii-p1", "xxiii.iv-p1",
                           "xxiii.viii-p1", "xxix.i-p1", "xxix.iii-p1", "xxix.viii-p1",
                           "xix-p56")},
                       # O'Conor's caption over da Câmara's preface ("Preface of Father
                       # Louis Gonzalez, S.J., to the 'Acts of St. Ignatius,' …").
                       "ignatius-autobiography.xml": {"iv-p2": "apparatus"},
                       # Mullan's cross-reference in the Annotations, only his page numbers
                       # ("Consolation and desolation are spoken of on p. 170; the
                       # Additions on p. 22.").
                       "ignatius-exercises.xml": {"ix-p23": "apparatus"}}


def not_body(source_file: str) -> tuple[dict[str, str], frozenset[str], dict[str, str]]:
    """`NOT_BODY_CLASSES`, `HEADING_DIVS` and `NOT_BODY_PARAGRAPHS` for a source file
    named as the checks name it (`../theologians/<file>`); empty for any other file."""
    prefix = f"../{SOURCE_DIR}/"
    if not source_file.startswith(prefix):
        return {}, frozenset(), {}
    name = source_file[len(prefix):]
    return (NOT_BODY_CLASSES.get(name, {}), HEADING_DIVS.get(name, frozenset()),
            NOT_BODY_PARAGRAPHS.get(name, {}))


class _WorkEditor(Editor):
    """Rule G for these files, beyond the editors' lines `Editor` finds. The Castle's
    chapters open with Zimmerman's outline of the chapter's numbered paragraphs
    (`Outline`, "1. Plan of this book. 2. …"), which goes; Teresa's heading in capitals
    before it (`Centered`) stays, marked. In the Life, two single paragraphs go by id
    (`NOT_BODY_PARAGRAPHS`).

    The Castle also prints the first word of a chapter's first paragraph in capitals
    ("1. WHILE I was begging"), a printer's opening, which is set in normal case ("1.
    While I was begging"; "1. I HAVE known" to "1. I have known"). Two of the Life's notes are called by a bracketed number,
    which leaves with them. No paragraph of either file opens with a word that is
    capitals of its own. A caller printed as a plain digit is read without it
    (`ingest.editorial.PLAIN_CALLERS`)."""

    def __init__(self, *args, title_classes: frozenset[str] = frozenset(), **kwargs):
        super().__init__(*args, **kwargs)
        self.title_classes = title_classes

    def chapter(self, elem, label: str) -> ChapterEdit:
        edit = super().chapter(elem, label)
        for block in elem:
            # A title the work prints as the chapter's first paragraph is marked, not
            # dropped, though it repeats the label `Editor` would drop it for.
            if block.tag == "p" and edit.dropped.get(id(block)) == "heading" and (
                    block.get("class") in self.title_classes
                    or self.source_file in _LETTER_FILES
                    and _YEAR_LINE.fullmatch(_text(block))):
                del edit.dropped[id(block)]
                edit.removed = [x for x in edit.removed
                                if x.block != edit.locators[id(block)]]
        for block in elem:
            if block.tag != "p":
                continue
            if self.source_file in _SEPARATOR_FILES and _SEPARATOR.fullmatch(_text(block)):
                kind = "heading"                  # a printer's rule or omission mark
                edit.dropped[id(block)] = kind
                edit.removed.append(Removed(edit.locators[id(block)], kind, _block_text(block)))
                continue
            kind = (NOT_BODY_PARAGRAPHS.get(self.source_file, {}).get(block.get("id"))
                    or NOT_BODY_CLASSES.get(self.source_file, {}).get(block.get("class")))
            kind = {"apparatus": "summary"}.get(kind, kind)
            if kind and id(block) not in edit.dropped:
                edit.dropped[id(block)] = kind
                edit.removed.append(Removed(edit.locators[id(block)], kind, _block_text(block)))
        inner = edit.edit

        callers = f"../{SOURCE_DIR}/{self.source_file}"

        def opened(block, marked, notes):
            marked, notes = inner(block, marked, notes)
            marked = _NOTE_CALL.sub("", marked)
            marked = _GLUED_STEP.sub(r"\1 \2", marked)
            for printed, without in PLAIN_CALLERS.get((callers, block.get("id")), ()):
                marked = marked.replace(printed, without)
            for printed, read in TEXT_FIXES.get((self.source_file, block.get("id")), ()):
                marked = marked.replace(printed, read)
            marked = without_page_refs(callers, marked)
            if block.get("class") in self.title_classes:
                return marked, notes          # a title in capitals throughout stays so
            if self.source_file.endswith(".txt"):
                return marked, notes          # a Gutenberg text, as its edition prints it
            if self.source_file in _LETTER_FILES and _SALUTATION.match(marked):
                return _SALUTATION.sub(lambda m: _title(m.group(1)) + ",—", marked,
                                       count=1), notes
            return _OPENING_CAPS.sub(_opening, marked, count=1), notes

        edit.edit = opened
        return edit


# A paragraph that is only a printer's rule or an omission mark ("* * * * * *", ". . . .
# . ."), in the files that print them between items: never text.
_SEPARATOR = re.compile(r"[*.\s]+")
_SEPARATOR_FILES = frozenset({"therese-autobio.xml"})
# A note's number printed in brackets just before the note (the Life, ch. xxvi and xxix):
# "vision.[8]" with note 8 after it. The note leaves; so does its call.
_NOTE_CALL = re.compile(r"\[\d+\](?=\u2063)")
# Words a file mistranscribes, by (file, paragraph id), each with the evidence: (as the
# file reads, as it should read). The Ninth Meditation's subject reads "upon to you"; the
# same file's contents, from the same edition, prints "open to you".
TEXT_FIXES = {("desales-devout_life.xml", "iii.xvii-p2"): (("upon to you", "open to you"),),
              # Letter V to Céline is dated 12 March 1889 (Carmel of Lisieux, LT 85); the
              # file prints 1899, two years after her death.
              ("therese-autobio.xml", "xxii.v-p1"): (("March 12, 1899.", "March 12, 1889."),),
              # The next paragraph opens with an omission mark, ". . . I must", which
              # cleaning would fold into the date's full stop across the paragraph break.
              ("therese-autobio.xml", "xxii.v-p2"): ((". . . I must", "… I must"),),
              # A Mystery's source line, as its neighbours print it ("Ibidem" with an l).
              ("ignatius-exercises.xml", "xviii.xxxvii-p1"): (("lbidem.", "Ibidem."),),
              # Part I ch. III § 2's title; the edition's contents prints "Mary, the hope
              # of sinners".
              ("pg72411.txt", "p287"): (("HAST THE HOPE OF SINNERS.",
                                          "MARY, THE HOPE OF SINNERS."),),
              # The Little Rosary of the Immaculate Mary's versicle and response print the
              # Latin after the English: the English stays (rule E).
              # Part I ch. II § 3's incipit prints its Latin before the English, as the
              # other incipits print it on a line of its own: the English stays (rule E).
              ("pg72411.txt", "p249"): (("Dulcedo:—Sweetness.", "Sweetness."),),
              ("pg72411.txt", "p1241"): ((": Ora pro nobis, Virgo immaculata;", ";"),),
              ("pg72411.txt", "p1242"): ((": Ut digni officiamur promissionibus Christi.",
                                          "."),)}
# Mullan's references to pages of his edition, in the files that print them: the
# edition's, not the text. In brackets ("They sent the Angel … (p. 133)."; "(P. 154)";
# "(p. 152); and it contains"), or after a comma ("the Particular Examen, p. 21, and";
# "Sins, pp. 37, 38; then"; "etc., p. 125. Let him").
_PAGE_REF = re.compile(r"\s*\([Pp]\. \d+\)(?:;\s*)?")
# One after a sentence's full stop, with a stop of its own ("different spirits. (P. 177).").
_PAGE_REF_AFTER_STOP = re.compile(r"(?<=[.!?])\s*\([Pp]\. \d+\)\.")
_PAGE_REF_AFTER_COMMA = re.compile(r",\s*pp?\. \d+(?:,\s*\d+)*(?=[.,;])")
_PAGE_REF_FILES = frozenset({"ignatius-exercises.xml"})


def without_page_refs(source_file: str, text: str) -> str:
    """`text` without the edition's page references, for a file that prints them (named
    as the checks name it, `../theologians/<file>`): "(p. 152); and it" reads "and it",
    "inclusive (p. 155); and in" reads "inclusive; and in", "Examen, p. 21, and" reads
    "Examen, and", "etc., p. 125. Let" reads "etc. Let"."""
    if source_file.removeprefix(f"../{SOURCE_DIR}/") not in _PAGE_REF_FILES:
        return text
    text = _PAGE_REF_AFTER_STOP.sub("", text)
    text = _PAGE_REF.sub(lambda m: "; " if m.start() and ";" in m.group() else "", text)
    text = _PAGE_REF_AFTER_COMMA.sub("", text)
    return text.replace("etc..", "etc.")


# A numbered step run on to the sentence before it with no space ("in the Presence of
# God.2. Humble yourself", the Devout Life's meditations VII to X): the space restored.
_GLUED_STEP = re.compile(r"([a-z][.!?”])(\d{1,2}\. [A-Z])")
# The files whose letters print their salutations in capitals and date a letter by a line
# holding only its year ("1889."), which `Editor` takes for a section number.
_LETTER_FILES = frozenset({"therese-autobio.xml"})
_YEAR_LINE = re.compile(r"\d{4}\.?")
# A letter's salutation printed in capitals up to its ",—" ("MY DEAR LITTLE CÉLINE,—"):
# set in title case as a whole.
_SALUTATION = re.compile(r"^([A-ZÀ-ÖØ-Þ’'][A-ZÀ-ÖØ-Þ’' ]*[A-ZÀ-ÖØ-Þ]),—")
# A printer's opening: the paragraph's first word (after its number) in capitals, or the
# word after an opening "I" ("1. I HAVE known", III ch. ii).
_OPENING_CAPS = re.compile(r"^(\s*(?:\d+\.\s+)?)(I\s+)?([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ’']+)(?![a-zß-ÿ])")


def _opening(m: re.Match) -> str:
    word = m.group(3).lower() if m.group(2) else m.group(3).capitalize()
    return m.group(1) + (m.group(2) or "") + word



# --------------------------------------------------------------------------- de Sales

# Introduction to the Devout Life (Rivingtons, 1876): the author's preface (i.i) and the
# chapters of Parts I to V (iii to vii). Left out: the title page (i), the contents (ii),
# the subject index (viii) and CCEL's indexes (ix). The chapter titles are `<h2>` lines,
# not paragraphs, so they are labels only.
_DEVOUT_PARTS = ("iii", "iv", "v", "vi", "vii")
_PART = re.compile(r"^PART ([IVX]+)\.")
_CHAPTER = re.compile(r"^(?:CHAPTER|Chapter)\s+([IVXLC]+)\.?\s*(.*?)[\s.]*$")


def _devout_chapters(root):
    out = [(None, _div(root, "i.i"), ChapterPlan(label="Preface"))]
    for part_id in _DEVOUT_PARTS:
        part = _div(root, part_id)
        book = f"Part {_PART.match(part.get('title') or '').group(1)}"
        # The part's own heading ("PART I. COUNSELS AND PRACTICES SUITABLE…", `<h1>`)
        # opens its first chapter, level 1.
        lead = ((_text(part.find("h1")).rstrip(), 1),)
        for k, ch in enumerate(_div2s(part)):
            m = _CHAPTER.match(" ".join((ch.get("title") or "").split()))
            if not m:
                raise ValueError(f"desales-devout_life.xml: unexpected chapter title "
                                 f"{ch.get('title')!r}")
            out.append((book, ch, ChapterPlan(label=f"Chapter {m.group(1)}. {m.group(2)}",
                                              headings=_meditation_headings(ch),
                                              lead=lead if k == 0 else ())))
    return out


def _meditation_headings(chapter) -> tuple[tuple[str, int, bool], ...]:
    """The headings of one of Part I's ten meditations (chapters ix to xviii): its subject
    ("Of Creation.") as the chapter's first paragraph, level 2 under the label ("First
    Meditation"), and its parts ("Preparation.", "Considerations.", "Affections and
    Resolutions.", "Conclusion.", "The Choice."), each a paragraph in italics only, level
    3. No other chapter prints a paragraph in italics only."""
    paras = [b for b in chapter if b.tag == "p" and _text(b)]
    parts = [b for b in paras if _italic_only(b)]
    if not parts:
        return ()
    subject = paras[0]
    if _italic_only(subject) or len(_text(subject)) > 80:
        raise ValueError(f"desales-devout_life.xml: meditation {chapter.get('id')!r} opens "
                         f"with no subject line")
    return ((subject.get("id"), 2, False),) + tuple((b.get("id"), 3, False) for b in parts)


def _italic_only(block) -> bool:
    kids = list(block)
    return (len(kids) == 1 and kids[0].tag == "i" and not (block.text or "").strip()
            and not (kids[0].tail or "").strip())


# Treatise on the Love of God (Mackey, about 1884; the TAN reprint of 1997): the author's
# dedicatory prayer (i.vii), his preface (i.viii) and the chapters of Books I to XII (ii
# to xiii). Left out: the cover, frontispiece, title page and TAN's dedication page (i.i to
# i.iv), Mackey's introduction (i.v), the contents (i.vi), TAN's list of its books
# (xiii.xiv), CCEL's indexes (xiv), and "THE END." after Book XII. A book's own text is
# its title only. Each chapter prints "CHAPTER N." (`<h3>`) and then its title as its
# first paragraph, which stays in the text as a marked heading.
_LOVE_BOOKS = ("ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii")
_LOVE_EDITOR_DIVS = frozenset({"xiii.xiv"})
_LOVE_TITLES = frozenset({"subhead", "subhead1", "smallhead"})
_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")


def _love_chapters(root):
    out = [(None, _div(root, "i.vii"), ChapterPlan(label="Dedicatory Prayer")),
           (None, _div(root, "i.viii"), ChapterPlan(label="Preface"))]
    for k, book_id in enumerate(_LOVE_BOOKS):
        book_div = _div(root, book_id)
        book = f"Book {_ROMAN[k]}"
        lead = ((_book_heading(book_div), 1),)
        for j, ch in enumerate(_div2s(book_div)):
            if ch.get("id") in _LOVE_EDITOR_DIVS:
                continue
            number = ch.find("h3")
            m = _CHAPTER.match(_text(number)) if number is not None else None
            first = next((b for b in ch if b.tag == "p" and _text(b)), None)
            if not m or first is None or first.get("class") not in _LOVE_TITLES:
                raise ValueError(f"desales-love.xml: chapter {ch.get('id')!r} prints no "
                                 f"number or title")
            # The label is the printed title (CCEL's typed div titles have slips: "Died by
            # and", "Signfied"); it repeats the title only when it holds it whole.
            title = smart_title_case(_text(first).upper()).rstrip(". ")
            full = f"Chapter {m.group(1)}. {title}"
            label = _clip(full)
            out.append((book, ch, ChapterPlan(label=label,
                                              headings=((first.get("id"), 1, label == full),),
                                              lead=lead if j == 0 else ())))
    return out


def _book_heading(book) -> str:
    """A Treatise book's own heading as printed over its first chapter, one line: "BOOK I.
    CONTAINING A PREPARATION FOR THE WHOLE TREATISE." The running title "THE LOVE OF
    GOD." over Book I is not part of it."""
    lines = [_text(c) for c in book if c.tag in ("h1", "h2", "h3", "p") and _text(c)]
    lines = [t for t in lines if t != "THE LOVE OF GOD."]
    return " ".join(lines)


def _div2s(parent):
    return [d for d in parent if isinstance(d.tag, str) and d.tag == "div2"]


# --------------------------------------------------------------------------- Julian

# Revelations of Divine Love (Warrack, 1901): the 86 chapters, the first three before the
# sixteen Revelations (i), each Revelation a div (ii to xviii, with "Anent certain points
# in the foregoing fourteen Revelations", xvi). Left out: the scribe's postscript (xix,
# not Julian's) and CCEL's indexes (xx). Each chapter's number is its label; the quoted
# subtitle under it (`<h3>`, "I saw . . . as it were in the time of His Passion") is
# Warrack's choice of Julian's words, standing in for the Sloane MS's chapter titles, so
# it is neither label nor text. A Revelation's heading names the label's book.
# Chapter numbers the file misprints, by div id, with the evidence: LXXXII is typed
# "LXXII" in its title and heading; it stands between LXXXI and LXXXIII.
_JULIAN_NUMBER_FIXES = {"xviii.xvi": "LXXXII"}
_JULIAN_PARTS = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii",
                 "xiii", "xiv", "xv", "xvi", "xvii", "xviii")


def _julian_chapters(root):
    out = []
    for part_id in _JULIAN_PARTS:
        part = _div(root, part_id)
        title = " ".join((part.get("title") or "").split())
        book = None if part_id == "i" else smart_title_case(title)
        for ch in _div2s(part):
            m = _CHAPTER.match(" ".join((ch.get("title") or "").split()))
            if not m:
                raise ValueError(f"julian-revelations.xml: unexpected chapter title "
                                 f"{ch.get('title')!r}")
            number = _JULIAN_NUMBER_FIXES.get(ch.get("id"), m.group(1))
            out.append((book, ch, ChapterPlan(label=f"Chapter {number}")))
    return out


# --------------------------------------------------------------------------- Thérèse

# The Story of a Soul (Taylor, 1912): the eleven chapters of the autobiography (ix to
# xix), the Counsels and Reminiscences (xxi; her sayings as her novices recorded them),
# her letters (xxii to xxviii) and her prayers (xxix). Left out: the electronic edition's
# note, title pages, contents and dedication (i to v, viii), Cardinal Bourne's preface
# (vi), the editors' prologue and epilogue on her family and death (vii, xx), the motto
# (xxx, a line of St John of the Cross), the table of her "days of grace" (xxxi), the
# poems (xxxii: Susan L. Emery's translation, not Taylor's, which the rights row does not
# cover) and CCEL's indexes. Chapter and letter titles are the edition's (`<h1>`-`<h3>`),
# so they are labels; each prayer's own title ("PRAYER TO OBTAIN HUMILITY") also opens
# its text, as printed, marked level 1 (not "VARIOUS PRAYERS", a group's).
_STORY = ("ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix")
_LETTERS = ("xxii", "xxiii", "xxiv", "xxv", "xxvi", "xxvii", "xxviii")
# The quotations she set over two of her Various Prayers (John 16:23, and words of Sister
# Mary of St Peter): epigraphs, marked, each kept with the prayer it opens.
_THERESE_EPIGRAPHS = {"xxix.iv": (("xxix.iv-p1", None, False), ("xxix.iv-p3", None, False)),
                      # The Joan of Arc prayer's title runs on under "PRAYER" in italics,
                      # as in the French ("Inspired by the sight of a statue …").
                      "xxix.vii": (("xxix.vii-p1", 2, False),)}
# "VARIOUS PRAYERS" names a group of two prayers, not a prayer: a label only.
_PRAYER_GROUPS = frozenset({"xxix.iv"})
# "CHAPTER I - EARLIEST MEMORIES"
_STORY_CHAPTER = re.compile(r"^CHAPTER ([IVXL]+) - (.+)$")
# A letter div's title: its number, then perhaps a caption and a date ("II (Written
# during her retreat before receiving the habit.) January 8, 1889.").
_LETTER_TITLE = re.compile(r"^([IVXL]+)\b\s*(?:\([^)]*\)\s*)?(.*?)\.?$")


def _therese_chapters(root):
    out = []
    for cid in _STORY:
        ch = _div(root, cid)
        m = _STORY_CHAPTER.match(" ".join((ch.get("title") or "").split()))
        if not m:
            raise ValueError(f"therese-autobio.xml: unexpected chapter title "
                             f"{ch.get('title')!r}")
        out.append((None, ch, ChapterPlan(
            label=f"Chapter {m.group(1)}. {_title(m.group(2))}")))
    out.append((None, _div(root, "xxi"), ChapterPlan(label="Counsels and Reminiscences")))
    for lid in _LETTERS:
        section = _div(root, lid)
        heads = [_text(h) for h in section if h.tag in ("h1", "h2", "h3") and _text(h)]
        book = _title(_letters_heading(heads, section.get("title")))
        letters = _div2s(section)
        if not letters:                       # one letter, the section itself
            out.append((None, section, ChapterPlan(label=book)))
            continue
        for letter in letters:
            # The printed heading ("I February 21, 1888."), which carries the date the
            # div's title leaves out.
            head = letter.find("h2")
            m = _LETTER_TITLE.match(_text(head) if head is not None else
                                    " ".join((letter.get("title") or "").split()))
            date = m.group(2).strip(" .")
            out.append((book, letter, ChapterPlan(
                label=f"Letter {m.group(1)}" + (f", {date}" if date else ""))))
    for prayer in _div2s(_div(root, "xxix")):
        title = " ".join((prayer.get("title") or "").split())
        out.append(("Prayers", prayer, ChapterPlan(
            label=_title(title), headings=_THERESE_EPIGRAPHS.get(prayer.get("id"), ()),
            lead=() if prayer.get("id") in _PRAYER_GROUPS
            else ((_text(prayer.find("h2")), 1, True),))))
    return out


def _title(text: str) -> str:
    """A heading printed in capitals, or partly so ("GUÉRIN (MADAME LA NÉELE)"), in title
    case, a word after "(" capitalized."""
    out = smart_title_case(text.upper())
    return re.sub(r"\((\w)", lambda m: "(" + m.group(1).upper(), out)


def _letters_heading(heads: list[str], title: str | None) -> str:
    """A letter section's name: its own heading line naming the recipient ("LETTERS OF
    SOEUR THÉRÈSE TO HER SISTER CÉLINE"), shortened to "Letters to …", else the div's
    title."""
    named = [h for h in heads if " TO " in h.upper()] or [title or ""]
    text = named[-1]
    i = text.upper().find(" TO ")
    return "Letters" + text[i:] if text.upper().startswith("LETTERS") else text


# --------------------------------------------------------------------------- Ignatius

# The Spiritual Exercises (Mullan, 1914): the Annotations (ix), the work's own title over
# its Presupposition (x, xi), the four Weeks (xii to xv), the Contemplation to Gain Love
# (xvi), the Three Methods of Prayer (xvii), the Mysteries of the Life of Christ (xviii)
# and the Rules (xix). Left out: the title pages (i, viii), the approbations of the Latin
# texts and Paul III's brief (ii, iii), Mullan's preface and general note (iv, vi), the
# contents (v), Father Diertins's prayer (vii), the general index (xx) and CCEL's indexes.
# The headlines are the Manuscript's (Mullan supplied the few it lacks, his general note
# says), so each stays in the text, marked: a section's ("FIRST WEEK") over its first
# chapter and a chapter's own at level 1, one inside a chapter at level 2. The file sets
# one printed heading over several `<h2>`/`<h3>` lines ("THE FIRST DAY AND FIRST
# CONTEMPLATION / IT IS ON / THE INCARNATION / …"), so each run of heading lines is one
# heading; a title line with smaller lines under it ("FIRST EXERCISE" over "IT IS A
# MEDITATION …") is a title and a level-2 subtitle.
_EXERCISES = ("ix", "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii", "xviii", "xix")
_EXERCISES_TITLE = "x"                    # the work's title, over the Presupposition
_HEAD_TAGS = ("h1", "h2", "h3", "h4")
# The class of the paragraph a run of heading lines becomes; with the file's subtitle
# paragraphs ("IT IS A MEDITATION ON THE SINS …"), titles printed in capitals.
_HEAD_CLASS = "heading-run"
_EXERCISES_TITLES = frozenset({_HEAD_CLASS, "subtitle"})
# Labels the div titles cut short ("THE SAME FOURTH DAY LET MEDITATION BE MADE ON").
_EXERCISES_LABELS = {"xiii.v": "The Fourth Day. Two Standards",
                     "xiii.vi": "The Fourth Day. Three Pairs of Men",
                     # The Ninth Apparition is printed inside the Eighth's div.
                     "xviii.xlv": "Of the Eighth and Ninth Apparitions"}
# A subtitle paragraph that is no heading: a Mystery's source line ("Ibidem.").
_EXERCISES_NOT_SUBTITLES = frozenset({"xviii.xxxvii-p1"})


def _heading_runs(div) -> list[tuple[Element, int, bool]]:
    """Replace each run of the div's own heading lines (`<h1>`-`<h4>`, the empty
    paragraphs between them passed over) with one paragraph of class `_HEAD_CLASS`, and
    return those paragraphs as (paragraph, level, opens the chapter): a run before any
    text opens it, level 1; a run after text is level 2. An opening run whose title line
    (`<h1>`, `<h2>`) has smaller lines under it is split there, the rest a subtitle."""
    out, seen_text, k = [], False, 0
    while k < len(div):
        kid = div[k]
        if kid.tag not in _HEAD_TAGS:
            seen_text = seen_text or (kid.tag == "p" and bool(_text(kid)))
            k += 1
            continue
        j = k
        while j < len(div) and (div[j].tag in _HEAD_TAGS
                                or div[j].tag == "p" and not _text(div[j])):
            j += 1
        run = [h for h in div[k:j] if h.tag in _HEAD_TAGS and _text(h)]
        groups = [run] if run else []
        if not seen_text and len(run) > 1 and run[0].tag in ("h1", "h2") \
                and run[1].tag not in ("h1", "h2"):
            groups = [run[:1], run[1:]]
        for h in [h for h in div[k:j] if h.tag in _HEAD_TAGS]:
            div.remove(h)
        for n, group in enumerate(groups):
            para = Element("p", {"id": group[0].get("id"), "class": _HEAD_CLASS})
            para.text = " ".join(_text(h) for h in group)
            div.insert(k + n, para)
            out.append((para, 2 if seen_text or n else 1, not seen_text))
        k += len(groups)
    return out


def _exercises_chapters(root):
    out, pending = [], []
    title = _div(root, _EXERCISES_TITLE)
    for part_id in _EXERCISES:
        if part_id == "xi":
            pending.append((" ".join(_text(h) for h in title
                                     if h.tag in _HEAD_TAGS and _text(h)), 1))
        _ignatius_walk(_div(root, part_id), None, None, out, pending)
    return out


def _ignatius_walk(div, book: str | None, prefix: str | None, out: list,
                   pending: list) -> None:
    """Add `div` as a chapter if it holds text of its own, then its child divs. A
    top-level div names its children's book ("First Week"); a div below a book prefixes
    its children's labels ("First Method. I. The Ten Commandments"). A div holding only
    headings passes them, as leads, to the first chapter after it."""
    runs = _heading_runs(div)
    title = " ".join((div.get("title") or "").split())
    label = _EXERCISES_LABELS.get(div.get("id")) or (
        _MINOR_WORDS.sub(lambda m: m.group().lower(), _title(title)) if title.isupper()
        else title)                                         # "I. The Ten Commandments"
    if prefix:
        label = f"{prefix}. {label}"
    own = [p for p in div if p.tag == "p" and p.get("class") != _HEAD_CLASS and _text(p)]
    if own:
        heads = [(p.get("id"), level, opens and level == 1
                  and headings.normalized(_text(p)) == headings.normalized(label))
                 for p, level, opens in runs]
        heads += [(p.get("id"), 2, False) for p in own if p.get("class") == "subtitle"
                  and p.get("id") not in _EXERCISES_NOT_SUBTITLES]
        order = {p.get("id"): n for n, p in enumerate(div) if p.tag == "p"}
        out.append((book, div, ChapterPlan(
            label=label, headings=tuple(sorted(heads, key=lambda h: order[h[0]])),
            lead=tuple(pending))))
        pending.clear()
    else:
        pending.extend((_text(p), level) for p, level, _ in runs)
    for child in div:
        if isinstance(child.tag, str) and child.tag.startswith("div"):
            if book is None:
                _ignatius_walk(child, label, None, out, pending)
            else:
                _ignatius_walk(child, book, label, out, pending)


# The Autobiography (O'Conor, 1900): the account Ignatius dictated to Luis Gonçalves da
# Câmara ("Father Louis Gonzalez"), with da Câmara's own preface (iv, "Preface of the
# Writer"). Left out: the title page and images (i, ii), O'Conor's preface (iii) and
# appendix on Jesuit education (xiii), his caption over da Câmara's preface, and CCEL's
# indexes. The eight chapters and their summaries ("HIS MILITARY LIFE—HE IS WOUNDED …",
# `chapterHead`) are O'Conor's division of a text that has none, so they are labels only,
# as are his titles over the first chapter.
_AUTOBIOGRAPHY = ("v", "vi", "vii", "viii", "ix", "x", "xi", "xii")
_CHAPTER_NUMBER = re.compile(r"^CHAPTER ([IVXL]+)$")
# Short words the title case capitalizes inside a summary ("Wounded At the Siege").
_MINOR_WORDS = re.compile(r"(?<=\s)(?:At|As|Into)(?=\s)")


def _autobiography_chapters(root):
    out = [(None, _div(root, "iv"), ChapterPlan(label="Preface of the Writer"))]
    for cid in _AUTOBIOGRAPHY:
        ch = _div(root, cid)
        number = next((m.group(1) for h in ch if h.tag == "h2"
                       for m in [_CHAPTER_NUMBER.match(_text(h))] if m), None)
        summary = next((_text(p) for p in ch if p.get("class") == "chapterHead"), None)
        if not number or not summary:
            raise ValueError(f"ignatius-autobiography.xml: chapter {cid!r} has no number "
                             f"or summary")
        # As many of the summary's phrases as fit a label, whole (as the Life's label
        # takes its argument's first sentence).
        label = f"Chapter {number}."
        for k, part in enumerate(summary.rstrip(". ").split("—")):
            phrase = _MINOR_WORDS.sub(lambda m: m.group().lower(), _title(part))
            longer = label + (" " if k == 0 else "—") + phrase
            if k and len(longer) > LABEL_MAX_CHARS:
                break
            label = longer
        out.append((None, ch, ChapterPlan(label=label)))
    return out

# --------------------------------------------------------------------------- Gutenberg text

# A Gutenberg work is one div of paragraphs (`ingest.gutenberg_text`), which its plan
# cuts into chapter divs at the work's own headings. A heading paragraph (printed in
# capitals, set in italics throughout, or a title line `headings.looks_like_heading`
# takes for one) stays in the text, marked: before the chapter's first text, the
# chapter's own title and any line in capitals at level 1 (with `chapter_title` where
# the label repeats it); otherwise level 2.
_ORDINALS = ("FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH", "EIGHTH",
             "NINTH", "TENTH", "ELEVENTH", "TWELFTH", "THIRTEENTH", "FOURTEENTH",
             "FIFTEENTH")
_ORDINAL = "|".join(_ORDINALS)
_HEADING_CLASS = "heading"
_TITLE_LINE_MAX = 80
# A prayer's title line ("Prayer of St. Ephrem."), a heading though it ends in a stop.
_TITLE_LINE = re.compile(rf"^Prayer (?:of|to) .{{3,{_TITLE_LINE_MAX - 10}}}$")


# Paragraphs of a Gutenberg text that are the edition's, not the work's, as ranges by the
# paragraphs that open and end them (end not included): the title page, approbation and
# publishers' preface before the work's first line, and the Glories' contents. The plans
# and the checks' extractor (`checks.source_text.gutenberg_units`) both read them.
TEXT_APPARATUS = {
    "pg72411.txt": ((None, "PROTEST OF THE AUTHOR."),
                    ("CONTENTS.", "PETITION OF THE AUTHOR TO JESUS AND MARY.")),
    "pg13871.txt": ((None, "CONVERSATIONS."),),
}


def text_apparatus(file: str, texts: list[str]) -> set[int]:
    """The indices of `texts` (a Gutenberg text's paragraphs) in `TEXT_APPARATUS`."""
    out: set[int] = set()
    for start, end in TEXT_APPARATUS.get(file, ()):
        a = 0 if start is None else texts.index(start)
        out.update(range(a, texts.index(end)))
    return out


def _caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


@dataclass
class _Unit:
    book: str | None
    label: str
    keep: int = 0              # text paragraphs it may hold and still take the next's
    shown: bool = True         # whether the paragraph that opens it stays in the text
    paras: list = field(default_factory=list)
    heads: list = field(default_factory=list)       # (paragraph, level, text as read)
    body: int = 0              # text paragraphs so far


def _cut(paras, classify, file: str) -> list[_Unit]:
    """Cut the paragraphs into units. `classify(k, text, unit)` returns "drop" (no text:
    a repeated title, a Latin incipit), "heading" (a heading line, whatever it looks
    like), "subheading" (one at level 2 wherever it stands), "text" (text, whatever it
    looks like), a `_Unit` the paragraph opens, or None (text, or a heading by its look).
    A unit with no more text than its `keep` (only its headings, or a part's line of
    description) takes the headings of the unit after it instead of ending. A paragraph
    is read with `TEXT_FIXES`, as the editor reads it."""
    units: list[_Unit] = []
    for k, p in enumerate(paras):
        text = _text(p)
        for printed, read in TEXT_FIXES.get((file, p.get("id")), ()):
            text = text.replace(printed, read)
        unit = units[-1] if units else None
        # A printer's rule ("*       *       *") is no text.
        kind = classify(k, text, unit) if text and not _SEPARATOR.fullmatch(text) else "drop"
        if kind == "drop":
            continue
        if isinstance(kind, _Unit):
            if unit is not None and unit.body <= unit.keep:
                unit.book = kind.book
                unit.label = kind.label
                unit.keep = max(unit.keep, kind.keep)
            else:
                units.append(kind)
                unit = kind
            heading = True
        else:
            heading = kind in ("heading", "subheading") or kind != "text" and (
                _caps(text) or p.get("class") == "italic"
                or headings.looks_like_heading(text) and len(text) <= _TITLE_LINE_MAX
                or _TITLE_LINE.match(text) is not None)
        if unit is None:
            raise ValueError(f"text before the first chapter: {text[:60]!r}")
        if isinstance(kind, _Unit) and not kind.shown:
            continue                          # an editor's numbering, a label only
        unit.paras.append(p)
        if heading:
            opening = unit.body <= unit.keep and kind != "subheading" and (
                _caps(text) or isinstance(kind, _Unit))       # a chapter's own title
            unit.heads.append((p, 1 if opening else 2, text))
        else:
            unit.body += 1
    return units


def _text_chapters(units: list[_Unit]) -> list:
    """The units as (book, div, ChapterPlan), each a `<div1 id="u<n>">`."""
    out = []
    for n, unit in enumerate(units, 1):
        div = Element("div1", {"id": f"u{n}", "title": unit.label})
        for p in unit.paras:
            div.append(p)
        heads = []
        for p, level, text in unit.heads:
            p.set("class", _HEADING_CLASS)
            said = headings.normalized(text)
            repeats = level == 1 and bool(said) and (
                headings.repeats_label(text, unit.label)
                or headings.normalized(unit.label).endswith(said))
            heads.append((p.get("id"), level, repeats))
        label = _MINOR_WORDS.sub(lambda m: m.group().lower(), unit.label)
        out.append((unit.book, div, ChapterPlan(label=_clip(label), headings=tuple(heads))))
    return out


# The Glories of Mary (Dunigan, 1852): the author's protest, petition, address to the
# reader, introduction and prayer for a good death; Part I on the Salve Regina (ten
# chapters, most in sections, then the saints' prayers); Part II's nine discourses on the
# feasts and dolors, the seven dolors, the virtues and the practices of devotion; then
# the examples, the novena, the meditations and the prayers. Left out: the title page,
# the archbishop's approbation, the publishers' preface to the American edition, the
# contents, the repeated "THE GLORIES OF MARY.", "END OF THE FIRST PART.", the divider
# before the examples (it names them and the meditations), each chapter's Latin line of
# the Salve Regina (rule E; the English under it heads the chapter, level 2), the notes
# (Alphonsus's sources, most in Latin: rule G keeps their count and scripture
# references) and the index.
_GLORIES_OWN = {"PROTEST OF THE AUTHOR.": None, "PETITION OF THE AUTHOR TO JESUS AND MARY.": None,
                "TO THE READER.": None, "INTRODUCTION": None,
                "PRAYER TO THE BLESSED VIRGIN TO OBTAIN A GOOD DEATH.": None,
                "SOME DEVOUT PRAYERS OF VARIOUS SAINTS TO THE HOLY MOTHER.": "Part I",
                "OF THE VIRTUES OF THE MOST HOLY MARY.": "Part II",
                "VARIOUS PRACTICES OF DEVOTION TO THE DIVINE MOTHER.": "Part II",
                "VARIOUS ADDITIONAL EXAMPLES APPERTAINING TO THE MOST HOLY MARY.": None,
                "NOVENA OF MEDITATIONS": None,
                "PRAYERS TO THE DIVINE MOTHER": None,
                "LITTLE ROSARY OF THE SEVEN DOLORS OF MARY.": None,
                "A Little Rosary of the Immaculate Mary,": None,
                "VARIOUS PRAYERS TO MARY.": None, "ACCLAMATIONS IN PRAISE OF MARY.": None}
_GLORIES_LABELS = {"INTRODUCTION": "Introduction",
                   "A Little Rosary of the Immaculate Mary,":
                       "A Little Rosary of the Immaculate Mary",
                   "NOVENA OF MEDITATIONS": "Novena of Meditations for the Purification",
                   "PRAYERS TO THE DIVINE MOTHER":
                       "Prayers to the Divine Mother for Every Day of the Week"}
# Titles inside the closing prayers that no rule above reads as headings.
_GLORIES_TITLES = {"Sweetness.", "Dedication of oneself to Mary.", "Dedication of a Family to Mary.",
                   "Another Prayer.", "Ejaculations to the Most Holy Mary.",
                   "Which is recited in some Churches."}
_GLORIES_DROP = {"THE GLORIES OF MARY.", "END OF THE FIRST PART.",
                 "MEDITATIONS FOR VARIOUS FESTIVALS, AND DIFFERENT DEVOTIONS IN HER HONOR."}
_GLORIES_PART = re.compile(r"^PART (FIRST|SECOND)\b")
_GLORIES_NUMBER = re.compile(r"^(CHAPTER|SECTION|DISCOURSE) ([IVX]+)\.$")
_GLORIES_DOLOR = re.compile(rf"^ON THE ({_ORDINAL}) DOLOR\.$")
_GLORIES_DAY = re.compile(rf"^({_ORDINAL}) DAY\.$")
_GLORIES_DEVOTION = re.compile(r"^DEVOTION ([IVX]+)\.—(.+?)\.?$|^(TENTH AND LAST DEVOTION)\.$")
_GLORIES_MEDITATION = re.compile(r"^MEDITATION(?: (FOR .+?))?\.?$")
_MEDITATIONS = "Meditations for Various Feasts of Mary"
_GLORIES_DOLORS = "REFLECTIONS ON EACH OF THE SEVEN DOLORS OF MARY IN PARTICULAR."
_WEEKDAYS = {f"{d}." for d in ("SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                               "FRIDAY", "SATURDAY")}


def _glories_chapters(root):
    paras = list(root[0])
    texts = [_text(p) for p in paras]
    apparatus = text_apparatus("pg72411.txt", texts)
    divider = texts.index("VARIOUS ADDITIONAL EXAMPLES APPERTAINING TO THE MOST HOLY MARY.")
    # What a numbered heading waits for: the line after it that names it.
    state = {"part": None, "chapter": None, "virtues": False, "names": None}

    def classify(k, text, unit):
        if k in apparatus or k == divider or text in _GLORIES_DROP:
            return "drop"
        if k and texts[k - 1].startswith("CHAPTER ") and _GLORIES_NUMBER.match(texts[k - 1]):
            return "drop"                   # the Latin line of the Salve Regina
        if text in _GLORIES_OWN:
            state["part"] = _GLORIES_OWN[text]
            state["virtues"] = text.startswith("OF THE VIRTUES")
            label = _GLORIES_LABELS.get(text) or _title(text.rstrip("."))
            return _Unit(state["part"], label, keep=1 if text == "NOVENA OF MEDITATIONS" else 0)
        if m := _GLORIES_PART.match(text):
            state["part"] = "Part I" if m.group(1) == "FIRST" else "Part II"
            return _Unit(state["part"], state["part"], keep=1)
        if m := _GLORIES_NUMBER.match(text):
            kind, n = m.groups()
            if kind == "CHAPTER":
                state["chapter"] = n
                state["virtues"] = False
            state["names"] = (kind, n)
            return _Unit(state["part"], f"{kind.capitalize()} {n}")
        if text in _GLORIES_TITLES:
            return "subheading"
        if text == _GLORIES_DOLORS:
            return _Unit(state["part"], "On the Seven Dolors")
        if text in _WEEKDAYS:
            return "subheading"
        if _caps(text) and unit is not None and unit.body == 0 and state["names"] is None \
                and re.fullmatch(r"Chapter [IVX]+\. .+", unit.label):
            # A chapter without sections: its title line names it, not the Latin's English.
            unit.label = f"{unit.label.split('.')[0]}. {_title(text.rstrip('.!'))}"
            return "heading"
        if m := _GLORIES_DOLOR.match(text):
            state["names"] = ("DOLOR", m.group(1))
            return _Unit(state["part"], f"On the {m.group(1).capitalize()} Dolor")
        if m := _GLORIES_DEVOTION.match(text):
            if m.group(3):
                return _Unit(state["part"], "Tenth and Last Devotion")
            title = _title(m.group(2)).replace("“hail", "“Hail").rstrip(".”") + (
                "”" if "“" in m.group(2) else "")
            return _Unit(state["part"], f"Devotion {m.group(1)}. {title}")
        if m := _GLORIES_DAY.match(text):
            return _Unit("Novena of Meditations for the Purification",
                         f"{m.group(1).capitalize()} Day")
        if m := _GLORIES_MEDITATION.match(text):
            if m.group(1) is None:
                state["names"] = ("MEDITATION", "")
                return _Unit(_MEDITATIONS, "Meditation")
            return _Unit(_MEDITATIONS, _title(text.rstrip(".")))
        if state["names"] and unit is not None:
            kind, n = state["names"]
            state["names"] = None
            title = _title(text.rstrip(".!")) if _caps(text) else text.rstrip(".")
            if kind == "CHAPTER":
                unit.label = f"Chapter {n}. {title[0].upper()}{title[1:]}"
            elif kind == "SECTION" and state["virtues"]:
                unit.label = f"The Virtues of Mary, Section {n}. {title}"
            elif kind == "SECTION":
                unit.label = f"Chapter {state['chapter']}, Section {n}. {title}"
            elif kind == "DOLOR":
                unit.label = f"On the {n.capitalize()} Dolor. {title}"
            elif kind == "DISCOURSE":
                unit.label = f"Discourse {n}. {title}"
            elif kind == "MEDITATION":
                title = _title(text.upper().rstrip("."))
                unit.label = f"Meditation {title[0].lower()}{title[1:]}"
            return "heading"
        return None

    return _text_chapters(_cut(paras, classify, "pg72411.txt"))


# The Practice of the Presence of God (Revell, about 1895): the four Conversations, which
# are attributed to Joseph de Beaufort (the document's note says so), and the fifteen
# Letters. The Conversations' headings are Beaufort's, so they stay in the text; the
# Letters' numbers and the Eighth's caption ("(Concerning wandering thoughts in
# Prayer.)") are the editor's (the French edition orders and heads them otherwise), so
# the numbers and the "LETTERS." divider are labels only. Left out: the title page, the publishers' preface, that
# caption and the translator's four notes (rule G).
_LAWRENCE_PART = {"CONVERSATIONS.": "Conversations", "LETTERS.": "Letters"}
_LAWRENCE_UNIT = re.compile(rf"^({_ORDINAL}) (CONVERSATION|LETTER)\.$")


def _lawrence_chapters(root):
    paras = list(root[0])
    apparatus = text_apparatus("pg13871.txt", [_text(p) for p in paras])
    state = {"book": None}

    def classify(k, text, unit):
        if k in apparatus:
            return "drop"
        if text in _LAWRENCE_PART:
            state["book"] = _LAWRENCE_PART[text]
            # The editor's gathering of the Letters names their book, a label only.
            return _Unit(state["book"], state["book"], shown=text == "CONVERSATIONS.")
        if m := _LAWRENCE_UNIT.match(text):
            return _Unit(state["book"], f"{m.group(1).capitalize()} {m.group(2).capitalize()}",
                         shown=m.group(2) == "CONVERSATION")
        if text == "(Concerning wandering thoughts in Prayer.)":
            unit.label += ". Concerning Wandering Thoughts in Prayer"   # the editor's caption
            return "drop"
        if text.startswith("To "):
            return "text"                     # a letter's address ("To the Reverend--")
        return None

    return _text_chapters(_cut(paras, classify, "pg13871.txt"))

# A paragraph the file closes mid-sentence: it ends on a lower-case word, a comma, a
# semicolon, a dash or the word "I", or the next part starts in lower case. A next part
# that opens with its section number ("25. The devils") is a paragraph of its own.
_OPEN_END = re.compile(r"(?:[a-z,;—-]|\bI)$")
_SECTION_START = re.compile(r"^\d+\.?\s")
# The classes a file gives its plain text paragraphs; any other class (a heading, an
# outline, a note) is never joined on.
_BODY_CLASSES = (None, "Body", "noindent")


# Files whose paragraphs split with nothing between are joined only when the second part
# runs on: Julian's lead-ins and Thérèse's addresses and signatures are lines of their own.
_RUN_ON_FILES = frozenset({"julian-revelations.xml", "therese-autobio.xml"})


def _rejoin_split_paragraphs(chapters, work: ThmlWork) -> int:
    """Join each paragraph of the chapters the build reads that the CCEL file splits at a
    page break (`<pb>` between two `<p>`; the Life, 25 times) back into one, so a
    sentence is not cut by a paragraph break. A paragraph the build drops by id
    (`NOT_BODY_PARAGRAPHS`) between the two parts is passed over. Returns how many were
    joined."""
    skipped = NOT_BODY_PARAGRAPHS.get(work.file, {})
    joined = 0
    for parent in chapters:
        kids = list(parent)
        k = 0
        while k < len(kids):
            first = kids[k]
            if first.tag != "p" or first.get("id") in skipped \
                    or first.get("class") == _HEAD_CLASS:
                k += 1
                continue
            j = k + 1
            while j < len(kids) and (kids[j].tag == "pb" or kids[j].get("id") in skipped):
                j += 1
            nxt = kids[j] if j < len(kids) else None
            head, tail = _text(first), _text(nxt) if nxt is not None else ""
            # Across a page break (or a dropped line) a paragraph ending mid-sentence or a
            # part starting in lower case is one paragraph; with nothing between, in the
            # files of `_RUN_ON_FILES`, only the second (an address's or a signature's
            # lines are paragraphs of their own there).
            broken = j > k + 1
            if nxt is not None and tail and not broken and work.file in _RUN_ON_FILES \
                    and not re.match(r"[a-z.,;:]", tail):
                k += 1
                continue
            if nxt is None or nxt.tag != "p" or not head or not tail \
                    or nxt.get("class") not in _BODY_CLASSES \
                    or _SECTION_START.match(tail) \
                    or not (_OPEN_END.search(head) or tail[0].islower()):
                k += 1
                continue
            _append(first, nxt)
            parent.remove(nxt)
            kids.pop(j)
            joined += 1
    return joined


# A class a file gives each line of a short verse quotation set as paragraphs (the
# Treatise's couplet from Pythagoras, II ch. xviii).
_VERSE_LINE_CLASSES = ("List7",)
# Verse lines a file sets as plain paragraphs, by `<p>` id: the Devout Life's closing
# couplet from St Francis's song (V ch. xviii).
_VERSE_LINES = {"desales-devout_life.xml": frozenset({"vii.xviii-p11", "vii.xviii-p12"}),
                # The Particular Examen's chart, a line of "G"s, one for each day.
                "ignatius-exercises.xml": frozenset(f"xii.ii-p{n}" for n in range(18, 29, 2))}
_VERSE_FILES = frozenset({"desales-love.xml", "desales-devout_life.xml",
                          "ignatius-exercises.xml"})


def _verse_blocks(chapters, work: ThmlWork) -> None:
    """Turn each verse quotation inside a chapter into a `<verse>` of `<l>` lines, which
    the builder reads as one paragraph, line by line, as it reads the Fathers' poems: a
    plain `<div>` of `<p>` lines (the Treatise's five, set as an indented block), and a
    run of `<p>` lines of a verse-line class or listed in `_VERSE_LINES`. Only the files
    in `_VERSE_FILES` print verse so."""
    if work.file not in _VERSE_FILES:
        return
    listed = _VERSE_LINES.get(work.file, frozenset())

    def is_line(block) -> bool:
        return block.tag == "p" and (block.get("class") in _VERSE_LINE_CLASSES
                                     or block.get("id") in listed)

    for chapter in chapters:
        kids = list(chapter)
        k = 0
        while k < len(kids):
            child = kids[k]
            if child.tag == "div" and all(line.tag == "p" for line in child):
                lines, run = list(child), [child]
            elif is_line(child):
                j = k
                while j < len(kids) and (is_line(kids[j]) or (
                        kids[j].tag == "p" and not _text(kids[j])
                        and j + 1 < len(kids) and is_line(kids[j + 1]))):
                    j += 1                    # an empty paragraph between lines passed over
                lines = run = kids[k:j]
            else:
                k += 1
                continue
            verse = Element("verse", {"id": child.get("id")})
            for line in lines:
                line.tag = "l"
                verse.append(line)
            verse.tail = run[-1].tail
            position = list(chapter).index(run[0])
            for gone in run:
                if gone in list(chapter):
                    chapter.remove(gone)
            chapter.insert(position, verse)
            kids = list(chapter)
            k = position + 1


def _append(first, nxt) -> None:
    """Move `nxt`'s text and children to the end of `first`, a space between."""
    text = " " + (nxt.text or "").lstrip()
    if len(first):
        first[-1].tail = (first[-1].tail or "").rstrip() + text
    else:
        first.text = (first.text or "").rstrip() + text
    first.extend(list(nxt))


WORKS: tuple[ThmlWork, ...] = (
    ThmlWork(file="teresa-castle2.xml", url="https://ccel.org/ccel/t/teresa/castle2.xml",
             title="The Interior Castle", author="Teresa of Avila", year=1577,
             translation="Benedictines of Stanbrook (1921)", chapters=_castle_chapters,
             genre="treatise", title_classes=frozenset({"Centered"})),
    ThmlWork(file="teresa-life.xml", url="https://ccel.org/ccel/t/teresa/life.xml",
             title="The Life of St. Teresa of Jesus", author="Teresa of Avila", year=1565,
             translation="David Lewis (1904)", chapters=_life_chapters, genre="other",
             notes=LIFE_NOTE),
    # The 1876 translation names no translator (R6, the rights row).
    ThmlWork(file="desales-devout_life.xml",
             url="https://ccel.org/ccel/d/desales/devout_life.xml",
             title="Introduction to the Devout Life", author="Francis de Sales", year=1609,
             translation=ANONYMOUS_1876, chapters=_devout_chapters, genre="manual"),
    ThmlWork(file="desales-love.xml", url="https://ccel.org/ccel/d/desales/love.xml",
             title="Treatise on the Love of God", author="Francis de Sales", year=1616,
             translation="Henry Benedict Mackey (1884)", chapters=_love_chapters,
             genre="treatise",
             title_classes=_LOVE_TITLES),
    ThmlWork(file="julian-revelations.xml", url="https://ccel.org/ccel/j/julian/revelations.xml",
             title="Revelations of Divine Love", author="Julian of Norwich", year=1393,
             translation="Grace Warrack (1901)", chapters=_julian_chapters,
             genre="treatise"),
    ThmlWork(file="therese-autobio.xml", url="https://ccel.org/ccel/t/therese/autobio.xml",
             title="The Story of a Soul", author="Thérèse of Lisieux", year=1897,
             translation="T. N. Taylor (1912)", chapters=_therese_chapters, genre="other",
             notes=THERESE_NOTE),
    ThmlWork(file="ignatius-exercises.xml", url="https://ccel.org/ccel/i/ignatius/exercises.xml",
             title="The Spiritual Exercises of St. Ignatius of Loyola",
             author="Ignatius of Loyola", year=1548,
             translation="Elder Mullan (1914)", chapters=_exercises_chapters,
             genre="manual", title_classes=_EXERCISES_TITLES),
    ThmlWork(file="ignatius-autobiography.xml",
             url="https://ccel.org/ccel/i/ignatius/autobiography.xml",
             title="The Autobiography of St. Ignatius", author="Ignatius of Loyola", year=1555,
             translation="J. F. X. O'Conor (1900)", chapters=_autobiography_chapters,
             genre="other", notes=IGNATIUS_NOTE),
    # The two Gutenberg texts (`ingest.gutenberg_text`); neither names its translator.
    ThmlWork(file="pg72411.txt", url="https://www.gutenberg.org/cache/epub/72411/pg72411.txt",
             title="The Glories of Mary", author="Alphonsus Liguori", year=1750,
             translation=ANONYMOUS_1852, chapters=_glories_chapters, genre="treatise",
             title_classes=frozenset({_HEADING_CLASS}), ebook=72411,
             notes_heading="FOOTNOTES"),
    ThmlWork(file="pg13871.txt", url="https://www.gutenberg.org/cache/epub/13871/pg13871.txt",
             title="The Practice of the Presence of God", author="Brother Lawrence",
             year=1692, translation=ANONYMOUS_1895, chapters=_lawrence_chapters,
             genre="other", title_classes=frozenset({_HEADING_CLASS}), ebook=13871,
             notes_heading="NOTES:", notes=LAWRENCE_NOTE),
)


def build_work(work: ThmlWork) -> Document:
    path = os.path.join(_SRC, work.file)
    root = (gutenberg_text.read_root(path, work.notes_heading) if work.ebook
            else _read_root(path))
    chapters = work.chapters(root)
    _verse_blocks([div for _, div, _ in chapters], work)
    if not work.ebook:                    # a Gutenberg paragraph is the printed one
        _rejoin_split_paragraphs([div for _, div, _ in chapters], work)
    parent_map = _build_parent_map(root)
    editor = _WorkEditor(work.file, work.source_key, parent_map,
                         title_classes=work.title_classes)
    doc = make_doc(collection=COLLECTION, filename=f"../{SOURCE_DIR}/{work.file}",
                   author=work.author, title=work.title,
                   chapters=chapters, source_key=work.source_key,
                   year=work.year, editor=editor, vulgate_references=bool(work.ebook),
                   extra_meta={"source_url": work.url,
                               **({"gutenberg_ebook": work.ebook} if work.ebook else {})})
    if doc is None:
        raise ValueError(f"{work.file}: no passages")
    doc.translation = work.translation
    doc.notes = work.notes
    return doc


def genre(source_key: str) -> str | None:
    """A work's genre by its source key (2.3's `document_facts`); None for another key."""
    return next((w.genre for w in WORKS if w.source_key == source_key), None)


def build_documents() -> list[Document]:
    return [build_work(w) for w in WORKS]
