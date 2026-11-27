"""Church Fathers ingestion — one Document per (father, work).

Parses each ANF/NPNF ThML volume into per-work documents with the correct
Church Father as author (not the series editor) and the specific work title.
Works nest to variable depth (work→chapter or work→book→chapter); book-structured
works (City of God, Against Heresies, …) stay ONE document, with the book carried
into the chapter label and metadata (flat sections for now; richer book→chapter
navigation can be layered on later without re-ingesting).

1.8c fixes what the ANF volumes' layout gets wrong: container names taken for authors,
the greetings printed above a letter's first chapter, the two Ignatian recensions printed
side by side, the commentators printed inside Peter of Alexandria's canons, Asterius
Urbanus's text held directly in its work div, and the works inside one document (D6).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from glob import glob
from xml.etree.ElementTree import Element, tostring

import defusedxml.ElementTree as ET

from model import Document, Work
from registry import drop_removed, removed_document_ids
from normalize.caps import smart_title_case
from normalize.text import fold_ligatures
from ingest.common import (_block_text, _build_parent_map, _cf_skippable, _strip_tags,
                           direct_blocks, iter_chapters)
from ingest.editorial import (PLAIN_CALLERS, RULE_LINE, Editor, Removed, _cut_brackets, _norm,
                               _record, span_sha1, strip_editorial_lines)
from ingest.editorial_keep import QuoteEdit, kept_quotes
from ingest import stromata_chadwick
from ingest.thml_doc import ChapterPlan, _chapter_label, _clip, distinct_titles, make_doc

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "church-fathers")
_SINGLE_AUTHOR = {"confessions.xml": "Augustine"}
_AUGUSTINE_FILES = {"city-of-god.xml", "on-the-holy-trinity.xml"}

# ------------------------------------------------------------------ 1.8b: NPNF Augustine

# The treatise volume whose div2s are each a work: "Doctrinal Treatises" and "Moral
# Treatises" split into their 16 works, the one exception to D6 (Carter, 4 Nov 2026).
# The registry pins On the Holy Trinity and On Continence to the two volumes' IDs.
_WORK_PER_DIV2 = frozenset({"on-the-holy-trinity.xml"})

# ------------------------------------------------------------------ 1.8d: On the Incarnation

# Volumes only some works of which are emitted, by file: {work div id: author}. NPNF2-04's
# On the Incarnation is Robertson's translation, which replaces Lawson's (1.8d); the rest of
# the volume (Against the Heathen, the anti-Arian works) is 5.6a's. The registry keeps the
# work's document ID. `checks.source_text.VOLUME_SCOPE` names the same divs.
VOLUME_WORKS = {"npnf204.xml": {"vii.ii": "Athanasius"}}
# "§1. " at the head of a section: before Robertson's italic analytical heading, or, in §5,
# which prints none, before the author's text.
_SECTION_NUMBER = re.compile(r"^\s*§\s*(\d+)\.\s*")

# ------------------------------------------------------------------ 5.6a: NPNF additions


@dataclass(frozen=True)
class NpnfWork:
    """One work an NPNF volume adds (5.6a): its div1, author and title. Only these divs
    of the volume are read, so its title pages, prolegomena and indexes stay out (rule G).
    `skip` names the editors' divs inside the work: an introduction, a translator's
    preface, a note on letters the volume does not translate, and a letter whose only
    text is the translator's bracketed summary of it. `letters` makes each div2 a work of
    the document (D6), as Cyprian's Epistles are."""
    div: str
    author: str
    title: str
    skip: frozenset[str] = frozenset()
    letters: bool = False
    # How the volume prints a chapter's head (`_HEADS`): Basil's "Chapter I." and title,
    # Cyril's lectures with their Scripture reading, Gregory's orations under the editor's
    # notes, Gregory's letters under "Ep. N." and the editor's dating.
    style: str = "basil"
    # Each chapter a work of the document, titled by its number (Gregory's orations, D6).
    works: bool = False
    # Chapters that are a work of their own inside the document, by first chapter div:
    # {div: (work key, title)}; a later chapter belongs to the last work opened (Cyril's
    # Mystagogical Lectures, whose authorship is disputed apart from the rest).
    groups: tuple = ()


# Basil's letters that NPNF2-08 summarizes in brackets instead of translating ("[A short
# letter of introduction.]") or prints by their title line alone (Letters 166 and 323 to
# 325), by div id, and the note on Letters 361 to 365, which it does not translate
# (ix.ccclvi).
_BASIL_SUMMARIES = frozenset(f"ix.{n}" for n in (
    "clxvii", "cccxxi", "cccxxii", "cccxxiii", "ccxcvii", "ccxcviii", "ccxcix", "ccci", "cccii", "ccciii", "cccv", "cccvi", "cccviii",
    "cccix", "cccx", "cccxi", "cccxii", "cccxiii", "cccxiv", "cccxv", "cccxvi", "cccxvii",
    "cccxviii", "cccxix", "cccxx", "cccxxiv", "cccxxv", "cccxxvi", "cccxxvii", "cccxxviii",
    "ccclvi"))
# NPNF2-07's editors' divs inside its works: title pages, Gifford's preface and
# introduction, the Prolegomena, the introduction to the Theological Orations, the
# introduction to the letters' first division, and three letters listed again in a later
# division with only the editor's pointer to where they are printed (Letters XLII, CCII
# and CXXV).
_NPNF207_SKIP = frozenset({"ii.i", "ii.ii", "ii.iii", "iii.i", "iii.ii", "iii.xii", "iv.i",
                           "iv.ii.i", "iv.iv.iii.i", "iv.iv.vi.vi", "iv.iv.ix.iv"})
# Leo's letters that NPNF2-12 gives only as Feltoe's summary ("(Congratulating him on being
# present at the synod of Ephesus.)", or in brackets, as the "Second Tome", Letter CLXV,
# whose text he leaves to the Councils), or by a pointer to another letter ("See Letter
# CLVIII."), or only his note on it ("Much shorter than, but to nearly the same effect as,
# xxxi."), by div id. The two divs that print several letters' numbers (CXXI and CXXII;
# LXII to LXIV) are summaries too.
_LEO_SUMMARIES = frozenset(f"ii.iv.{n}" for n in (
    "ii", "iii", "v", "viii", "xi", "xiii", "xxv", "xxx", "xxxvi", "xli", "xlvi", "xlvii",
    "xlviii", "xlix", "l", "li", "liii", "liv", "lvii", "lviii", "lix", "lx", "lxv",
    "lxvi", "lxvii", "lxviii", "lxix", "lxx", "lxxi", "lxxii", "lxxiii", "lxxvi",
    "lxxviii", "lxxix", "lxxxi", "lxxxii", "lxxxiv", "lxxxv", "lxxxvi", "lxxxvii",
    "lxxxix", "xci", "xcii", "xciv", "xcv", "xcvii", "xcviii", "cii", "cv", "cvi",
    "cvii", "cix", "cx", "cxi", "cxiii", "cxvi", "cxix", "cxx", "cxxi", "cxxii",
    "cxxiv", "cxxv", "cxxvi", "cxxvii", "cxxviii", "cxxix", "cxxx", "cxxxi", "cxxxii",
    "cxxxiv", "cxxxv", "cxxxvi", "cxxxvii", "cxxxviii", "cxxxix", "cxl", "cxli",
    "cxlii", "cxliii", "cxliv", "cxlv", "cxlvi", "cxlvii", "cxlviii", "cxlix", "cli",
    "cliv", "clv", "clvii", "clix", "clxii", "clxiv", "clxvi", "clxvii"))
# Gregory's Register letters that NPNF2-13 gives by a pointer to an identical one ("For
# the rest of this epistle see preceding Epistle IX."), and NPNF2-13's editors' divs
# (title page, Barmby's literature list and his notes to the Pastoral Rule and Register).
_NPNF213_SKIP = frozenset({"ii.i", "ii.ii", "ii.iii", "ii.iv", "ii.ix.vii"})
NPNF_WORKS = {
    "npnf207.xml": (
        NpnfWork("ii", "Cyril of Jerusalem", "Catechetical Lectures", skip=_NPNF207_SKIP,
                 style="lectures",
                 groups=(("ii.iv", ("ii.iv", "Lectures to the Candidates for Baptism")),
                         ("ii.xxiii", ("ii.xxiii", "Mystagogical Lectures")))),
        NpnfWork("iii", "Gregory of Nazianzus", "Select Orations", skip=_NPNF207_SKIP,
                 style="orations", works=True),
        NpnfWork("iv", "Gregory of Nazianzus", "Select Letters", skip=_NPNF207_SKIP,
                 letters=True, style="letters207"),
    ),
    "npnf208.xml": (
        NpnfWork("vii", "Basil", "On the Holy Spirit", skip=frozenset({"vii.i"})),
        NpnfWork("viii", "Basil", "The Hexaemeron", skip=frozenset({"viii.i"})),
        NpnfWork("ix", "Basil", "Letters", skip=frozenset({"ix.i"}) | _BASIL_SUMMARIES,
                 letters=True),
    ),
    "npnf212.xml": (
        # Named for him here, so Basil's Letters keep their title (`distinct_titles`).
        NpnfWork("ii.iv", "Leo the Great", "Letters of Leo the Great", skip=_LEO_SUMMARIES,
                 letters=True, style="leo"),
        NpnfWork("ii.v", "Leo the Great", "Sermons", style="leo", works=True),
        # Barmby's preface on the title (iii.iv.i) is the editor's.
        NpnfWork("iii.iv", "Gregory the Great", "The Book of Pastoral Rule",
                 skip=frozenset({"iii.iv.i"}), style="pastoral"),
        NpnfWork("iii.v", "Gregory the Great", "Register of Letters, Books I to VIII",
                 letters=True, style="register"),
    ),
    "npnf213.xml": (
        NpnfWork("ii", "Gregory the Great", "Register of Letters, Books IX to XIV",
                 skip=_NPNF213_SKIP, letters=True, style="register"),
    ),
}
# A letter part of which is another writer's, cut into a work of its own at the paragraph
# that opens that part, by (file, letter div): (first paragraph id, the part's label).
# Letter 197's second section, on the relics of Dionysius of Milan, is not Basil's
# (Cavallin 1945, in Quasten; Fedwick 1981, "De reliquis Dionysii").
_LETTER_PARTS = {("npnf208.xml", "ix.cxcviii"): ("ix.cxcviii-p9", "Section 2"),
                 # Gregory's Register II, 41: some manuscripts give the letter in another
                 # form, with a paper on monasteries' privileges, which Barmby prints after
                 # it under a note (cut, rule G).
                 ("npnf212.xml", "iii.v.ii.xxii"): ("iii.v.ii.xxii-p6", "Second version")}
# The headings inside such a part, by paragraph id: level. The paper the second version of
# Register II, 41 appends opens "Of the privileges of Monasteries."
_PART_HEADINGS = {"iii.v.ii.xxii-p8": 2}
# Letters in a collection that another writer sent, by (file, letter div): the sender,
# from the letter's title line, as 1.8c credits Cyprian's correspondents ("Antipater to
# Basil."). 3.2's labels (`attributions`) add the rest.
_NPNF_SENDERS = {
    ("npnf208.xml", "ix.clxxxviii"): "Antipater",
    # NPNF2-12: the letters to Leo his collection keeps, and two to Gregory in his Register.
    **{("npnf212.xml", div): sender for div, sender in (
        ("ii.iv.xxi", "Eutyches"), ("ii.iv.xxii", "Flavian of Constantinople"),
        ("ii.iv.xxvi", "Flavian of Constantinople"), ("ii.iv.lii", "Theodoret of Cyrus"),
        ("ii.iv.lv", "Galla Placidia"), ("ii.iv.lxiii", "Ceretius, Salonius and Veranus"),
        ("ii.iv.xciii", "Council of Chalcedon"), ("ii.iv.xcvi", "Anatolius of Constantinople"),
        ("iii.v.ii.xxx", "Licinianus of Cartagena"), ("iii.v.iii.xxix", "John of Ravenna"))},
    # NPNF2-13: three letters to Gregory.
    **{("npnf213.xml", div): sender for div, sender in (
        ("ii.v.xxx", "Recared"), ("ii.v.lx", "Columbanus"), ("ii.x.vii", "Felix of Messana"))},
}
# The line over a chapter, homily or letter that numbers it: "Chapter I.", "Homily IX.",
# "Letter CCCLX.".
# Rule E (3.3's way): paragraphs a translator left in Greek, cut from the chapter, by
# (file, chapter div): the sha1 of each (`editorial.span_sha1`), never its text. Letter 125
# quotes the Creed of Nicaea, which NPNF2-08 prints in Greek with the editor's brackets
# marking the Constantinopolitan creed's wording; the letter's English stays.
NOT_ENGLISH = {("npnf208.xml", "ix.cxxvi"): frozenset({
    "ea0d9b08b078984a3e8f0dbecea96054280e7a02", "e40f497fe5532ff2912ab84a5903489ff1b484c6",
    "fa01c65840b37a60b4f216538a3382742ad5287b", "17b2e62402c4a612c300a7955db433d313d45a91",
    "fbaa9a65ac57db6ed2d4cf0bf0de1379b03bf538", "dff9be04901f0d288ba214de3e9316fa4dc8859e",
    "d0bebb268f8129d0195001f0966b1e21a4021cbf", "143dd979110a5557598a3cde26f6bb0823b886f5"})}
# Jackson's comparisons with the English Bibles inside a quotation ("[A.V., of]", "[lxx.,
# known]"): the editor's, as `editorial.EDITOR_BRACKET`'s are. Supplied words ("[the
# Spirit]") and the passages Newman's version marks in brackets (Letters 2, 71, 203, 204)
# are the translation's and stay.
_NPNF_EDITOR_BRACKET = re.compile(r"\bA\.\s?V\.|\blxx\b", re.IGNORECASE)
# The editors' notes in brackets inside a paragraph: Barmby's pointers to the Pastoral Rule
# ("[See Reg. Past., Pt. II. ch. 6…]") and his notes on the manuscripts ("[N.B. This date is
# absent…]", "[al., … So Bede.]"), and Feltoe's to the editors' chapters ("[as we said
# above, chap. viii.]"). Their glosses ("[i.e. monks of St. Theodore]") and supplied words
# stay, as Jackson's do.
_NPNF_NOTE_BRACKET = re.compile(r"^\[(?:See |N\.B\.|A long passage|al\.,|as we said above)")
# The same comparison printed in parentheses, by (file, paragraph id): the span as printed.
_NPNF_EDITOR_SPANS = {
    ("npnf208.xml", "vii.vi-p56"): (" (A.V., “of” instead of “through a woman”)",),
    # The translator's source line under Gregory's quotation of Homer (Letter V).
    ("npnf207.xml", "iv.iii.iv-p6"): ("—Od. viii. 492.",),
    # Barmby's reading from Bede, in Augustine's tenth question (Register XI, 64).
    ("npnf213.xml", "ii.vii.xxx-p54"): (" (ministerium: in Bede, mysterium)",)}
_NPNF_NUMBER = re.compile(r"^(Chapter|Homily|Letter) ([IVXLC]+)\.$")
_CANONICA = re.compile(r"^\(?Canonica \w+\.?\)?$")
# NPNF2-07: Cyril's number lines ("Lecture IV.", "FIRST CATECHETICAL LECTURE"), Gregory's
# ("Oration II."), and a letter's "Ep. CCII." wherever its head line prints it.
_LECTURE_NUMBER = re.compile(r"^(?:Lecture ([IVXLC]+)\.|(FIRST) CATECHETICAL LECTURE)$")
_ORATION_NUMBER = re.compile(r"^Oration ([IVXLC]+)\.$")
_EP = re.compile(r"\bEp\. ([CLXVI]+)\b")
# A paragraph that numbers itself: Gregory's sections ("I.") and Cyril's ("1.").
_NUMBERED = re.compile(r"^(?:\d+|[IVXLC]+)\.\s")
# Oration XXXI prints no number line over its title.
_ORATION_FIX = {("npnf207.xml", "iii.xvii"): "XXXI"}
# The classes NPNF2-07 prints Cyril's Scripture reading in, under each lecture's title.
_READING_CLASSES = frozenset({"c41", "c42", "c43", "c44"})
# Cyril's own headings inside a lecture ("I. Of God." in Lecture IV), level 2.
_LECTURE_HEADING_CLASS = "c40"
# Letters whose "Ep. N." line prints the wrong number: the letter to Gregory of Nyssa on
# his teaching rhetoric is Gregory's Letter XI, though NPNF2-07 prints "Ep. I." over it
# (a second "Letter I", beside the first letter to Basil).
_LETTER_FIX = {("npnf207.xml", "iv.iv.ii.i"): "XI"}
# Gregory's letters without an address line: the division they stand in names it.
_LETTER_ADDRESS = {("npnf207.xml", "iv.iii"): "To Basil"}
# A chapter whose end is the editor's, from this paragraph on: Gifford's appendix to
# Lecture IX, variant readings from a homily printed under Basil's name.
_NPNF_TAILS = {("npnf207.xml", "ii.xiii"): "ii.xiii-p86"}

# ------------------------------------------------------------------ 1.8c: names

# Authors where the ANF div1 title is a container's name, by (file, div1 id). A callable
# takes the work div. The registry keeps every document ID through the relabel.
_AUTHOR_FIX = {
    ("third-century.xml", "iii"): "Tertullian",                # "Tertullian: Part Fourth."
    ("third-century-2.xml", "vii"): "Anonymous",               # "Appendix." (3.2 labels it)
    ("third-century-3.xml", "iv"): "Dionysius of Alexandria",  # "Dionysius."
    ("third-century-3.xml", "vi"): lambda work: _work_title(work),  # "Anatolius and Minor Writers."
    ("second-century.xml", "ii"): "Hermas",                    # "THE PASTOR OF HERMAS"
}
# Titles by (file, work div id).
_TITLE_FIX = {
    ("second-century.xml", "ii.ii"): "The Shepherd: Visions",
    ("second-century.xml", "ii.iii"): "The Shepherd: Commandments",
    ("second-century.xml", "ii.iv"): "The Shepherd: Similitudes",
    ("third-century-3.xml", "ix.iv"): "The Canonical Epistle",
}
_SPELLING = {"Pierus of Alexandria": "Pierius of Alexandria"}

# ------------------------------------------------------------------ 1.8c: greetings

# A work div whose own paragraphs, above its first chapter, are not an opening to emit:
# the text of Lactantius's fragments waits for 5.6a with the other whole works (1.8e,
# Decision log "Whole Fathers works").
_ROOT_TEXT_LATER = frozenset({("third-fourth-century.xml", "iii.vi")})
# "Ignatius, who is also called Theophorus, to the Church which is at Ephesus";
# "Polycarp, and the presbyters with him, to the Church"; "to her who has obtained mercy".
_SALUTATION = re.compile(r"^[A-Z][^.;:]*?,? to (?:the |her |him |[A-Z])")

# ------------------------------------------------------------------ 1.8c: Ignatius

# The seven genuine letters print the shorter recension and the longer side by side: in
# each unit (the greeting and each chapter) the first paragraph is the shorter, the second
# the longer. Only the shorter is emitted; the longer is removed under rule B (D11).
_RECENSIONS = frozenset(("apostolic fathers.xml", f"v.{n}")
                        for n in ("ii", "iii", "iv", "v", "vi", "vii", "viii"))
_RECENSION_SUFFIX = ": Shorter and Longer Versions"
# Units printing one paragraph, by the ANF01 print page: Ephesians prints chapter XX
# twice (the shorter in the left column, p. 58, the longer in the right), and CCEL kept
# only the left column of Romans X (p. 78), which ends "(that is, on the twenty-third day
# of August). … Amen."
_RECENSION_OVERRIDE = {"v.ii.xx": "short", "v.ii.xxi": "long", "v.v.x": "short"}

# ------------------------------------------------------------------ 1.8c: Peter

# Peter of Alexandria's canons, each followed by Balsamon's and Zonaras's commentary.
_COMMENTARY = frozenset({("third-century-3.xml", "ix.iv")})
_COMMENTATORS = ("Balsamon", "Zonaras")
# The editor's heading over the canons, at the top of Canon I.
_CANONS_HEADING = "The Canons of the Blessed Peter"

# ------------------------------------------------------------------ 1.8c: whole works

# Works whose text sits directly in the work div, with no chapter divs: their paragraphs
# are cut at the headings into chapters. 1.8e decides which others join (Carter: none
# before Phase 4).
_WHOLE_WORK_DIVS = frozenset({("third-fourth-century.xml", "v.ii")})
_HEADINGS = frozenset(f"h{n}" for n in range(1, 7))

# ------------------------------------------------------------------ 1.8c: works (D6)

# Container documents, by (file, work div id): the div level that is each work.
_CONTAINERS = {
    ("third-century-3.xml", "iii.iii"): 3,      # Gregory, "Acknowledged Writings"
    ("third-century-3.xml", "iii.iv"): 3,       # Gregory, "Dubious or Spurious Writings"
    ("third-century-2.xml", "iii.iv"): 4,       # Hippolytus, under Part I and Part II
    ("third-century-2.xml", "iii.v"): 3,        # Appendix to the Works of Hippolytus
    ("third-century-2.xml", "iv.iv"): 3,        # Cyprian's Epistles: each letter
    ("third-century-2.xml", "iv.v"): 3,         # The Treatises of Cyprian
    ("third-century-2.xml", "iv.vii"): 3,       # Treatises Attributed to Cyprian
    ("third-fourth-century.xml", "iii.vi"): 3,  # Fragments of Lactantius
}
# Cyprian's Epistles: the letters written by others (C-02), by div id, as (sender,
# recipient), from each letter's title line and greeting. Epistle XXX, Novatian's for
# the Roman clergy, is credited to no one here: 3.1 removes it under rule A.
_LETTER_SENDERS = {
    "iv.iv.ii": ("The Roman clergy", "the clergy of Carthage"),
    "iv.iv.xvi": ("The confessors", "Cyprian"),
    "iv.iv.xviii": ("Caldonius", "Cyprian"),
    "iv.iv.xx": ("Celerinus", "Lucian"),
    "iv.iv.xxi": ("Lucian", "Celerinus"),
    "iv.iv.xxv": ("Moyses, Maximus, Nicostratus and the other confessors", "Cyprian"),
    "iv.iv.xxix": ("The presbyters and deacons at Rome", "Cyprian"),
    "iv.iv.xxxviii": ("Caldonius, Herculanus and others", "Cyprian"),
    "iv.iv.xlv": ("Pope Cornelius", "Cyprian"),
    "iv.iv.xlvii": ("Pope Cornelius", "Cyprian"),
    "iv.iv.xlix": ("Maximus, Urbanus, Sidonius and Macharius", "Cyprian"),
    "iv.iv.lxxiv": ("Firmilian of Caesarea", "Cyprian"),
    "iv.iv.lxxvii": ("Nemesianus, Dativus, Felix and Victor", "Cyprian"),
    "iv.iv.lxxviii": ("Lucius and the brethren with him", "Cyprian"),
    "iv.iv.lxxix": ("Felix, Jader, Polianus and the martyrs at the mines", "Cyprian"),
}
# Epistle XXX: written by Novatian for the Roman clergy, credited to no one (above).
_UNCREDITED_LETTERS = frozenset({"iv.iv.xxx"})
# A work inside a document that is otherwise one work (C-15), by (file, document div):
# {work div: (title, label prefix, chapter label)}. The div is the work's own chapter, or
# holds its chapters. A chapter label of None keeps the chapter's own. 3.2 adds the
# Apostolic Canons, the canons at the end of Constitutions Book VIII (D10), and the
# Muratorian Fragment, printed as section III of Caius's fragments.
_EMBEDDED_WORKS = {
    ("third-fourth-century.xml", "iii.ii"): {
        "iii.ii.viii": ("Epitome of the Divine Institutes", "Epitome", None)},
    ("third-fourth-century.xml", "ix.ix"): {
        "ix.ix.vi": ("The Apostolic Canons", None, "Canons")},
    ("third-century-2.xml", "v.iii"): {
        "v.iii.iii": ("The Muratorian Fragment", None, None)},
}
# Works inside a container that share a title with another there, by work div id:
# Hippolytus's second set of Psalms fragments (from de Magistris) prints "On the Psalms."
# as the first does.
_WORK_TITLE_FIX = {"iii.iv.i.xiv": "On the Psalms: Further Fragments"}
# Book divs whose title omits the word "Book" (On the Apparel of Women prints "II").
_BOOK_FIX = {("third-century.xml", "iii.iii.ii"): "Book II"}


def _strip_doctype(xml: str) -> str:
    return re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)


def _read_root(path: str):
    with open(path, encoding="utf-8", errors="replace") as f:
        return ET.fromstring(_strip_doctype(f.read()))


def _source_key(filename, work=None) -> str:
    return f"church-fathers/{filename}" + (f"#{work.get('id')}" if work is not None else "")


def _make_doc(filename, author, title, chapters, work=None, editor=None, works=None):
    """`work` is the div holding the work when the file holds several."""
    return make_doc(collection="church-fathers", filename=filename, author=author,
                    title=title, chapters=chapters, source_key=_source_key(filename, work),
                    editor=editor, works=works)


def _work_title(div) -> str:
    title = fold_ligatures(smart_title_case((div.get("title") or "").strip()).rstrip(" ."))
    return _SPELLING.get(title, title)


# ------------------------------------------------------------------ paragraph selection

def recension_blocks(unit) -> tuple[list, list]:
    """A recension unit's (shorter, longer) paragraphs."""
    blocks = [b for b in direct_blocks(unit) if _block_text(b)]
    which = _RECENSION_OVERRIDE.get(unit.get("id"))
    if which == "short":
        return blocks, []
    if which == "long":
        return [], blocks
    if len(blocks) != 2:
        raise ValueError(f"recension unit {unit.get('id')} has {len(blocks)} paragraphs")
    return blocks[:1], blocks[1:]


def _commentator(block) -> bool:
    lead = next(iter(block), None)
    return (lead is not None and lead.tag == "span" and lead.get("class") == "sc"
            and (lead.text or "").strip() in _COMMENTATORS)


def commentary_blocks(canon) -> tuple[list, list]:
    """A canon's (Peter's, the commentators') paragraphs: the commentary starts at the
    first paragraph led by "Balsamon" or "Zonaras" in small capitals. The editor's
    heading over the canons, at the top of the first, is Peter's neither (rule G)."""
    blocks = direct_blocks(canon)
    at = next((k for k, b in enumerate(blocks) if _commentator(b)), len(blocks))
    own = [b for b in blocks[:at] if not _block_text(b).startswith(_CANONS_HEADING)]
    return own, blocks[at:]


def canons_heading(canon) -> list:
    return [b for b in direct_blocks(canon) if _block_text(b).startswith(_CANONS_HEADING)]


class _FathersEditor(Editor):
    """Rule G (1.8a), and, in the works that need it, only the paragraphs that are the
    work's own text (1.8c): the shorter Ignatian recension, Peter's canons without their
    commentators."""

    def __init__(self, source_file, source_key, parent_map, keep=None):
        super().__init__(source_file, source_key, parent_map)
        self.keep = keep

    def chapter(self, elem, label):
        edit = super().chapter(elem, label)
        if self.keep is None:
            return edit
        kept = {id(b) for b in self.keep(elem)}
        inner = edit.edit

        def own_only(block, marked, notes):
            if id(block) not in kept:
                return "", []
            return inner(block, marked, notes)

        edit.edit = own_only
        return edit


# ------------------------------------------------------------------ chapters

def _opening(filename, work):
    """The work div's own paragraphs above its first chapter, as an opening unit: a
    letter's greeting ("Salutation") or an address ("Opening"). None when the div holds
    none or only title lines. The caller asks only for a work with chapters: a work whose
    text is all in its own div is a whole work (1.8e)."""
    if (filename, work.get("id")) in _ROOT_TEXT_LATER:
        return None
    blocks = direct_blocks(work)
    if not blocks:
        return None
    if (filename, work.get("id")) in _RECENSIONS:
        blocks = recension_blocks(work)[0]
    text = strip_editorial_lines([t for b in blocks if (t := _block_text(b))],
                                 titles=(work.get("title") or "",))
    if not text:
        return None
    kind = "salutation" if _SALUTATION.match(text[0][:200]) else "opening"
    return (None, work, ChapterPlan(label=kind.title(), anchor=f"{work.get('id')}/{kind}",
                                    any_length=True))


def _heading_label(text: str) -> str:
    """"i. the exordium" -> "I. The Exordium"; "iv" -> "IV"."""
    m = re.match(r"^([ivxlc]+)\b\.?\s*(.*)$", text, re.IGNORECASE)
    if not m:
        return smart_title_case(text.upper())
    rest = smart_title_case(m.group(2).upper()) if m.group(2) else ""
    return f"{m.group(1).upper()}. {rest}" if rest else m.group(1).upper()


def _sections(work, parent_map) -> list:
    """A whole work's direct paragraphs cut at its headings, each run under a heading as
    a chapter div `<work id>/<numeral or slug>` titled by the heading."""
    from identity import slugify

    out = []
    current = None
    for child in work:
        if not isinstance(child.tag, str):
            continue
        if child.tag in _HEADINGS:
            text = " ".join(_strip_tags(tostring(child, encoding="unicode")).split())
            text = text.rstrip(".").strip()
            m = re.match(r"^([ivxlc]+)\b", text, re.IGNORECASE)
            name = m.group(1).lower() if m else slugify(text)[:40]
            current = Element("div3", {"id": f"{work.get('id')}/{name}", "title": text})
            parent_map[current] = work
            out.append(current)
        elif child.tag in ("p", "verse") and current is not None:
            current.append(child)
    return out


def _work_of(elem, root, level: int, parent_map):
    """The div at `level` under `root` that holds `elem` (itself included), or None."""
    cur = elem
    while cur is not None and cur is not root:
        if cur.tag == f"div{level}":
            return cur
        cur = parent_map.get(cur)
    return None


def _container_work(div, ordinal: int) -> Work:
    key = div.get("id")
    sender = _LETTER_SENDERS.get(key)
    if sender:
        return Work(work_key=key, ordinal=ordinal, title=f"{sender[0]}, to {sender[1]}",
                    author=sender[0])
    if key.startswith("iv.iv.") and div.get("shorttitle"):      # one of Cyprian's letters
        return Work(work_key=key, ordinal=ordinal, title=smart_title_case(div.get("shorttitle")),
                    author=None if key in _UNCREDITED_LETTERS else "Cyprian")
    return Work(work_key=key, ordinal=ordinal,
                title=_WORK_TITLE_FIX.get(key) or _work_title(div))


def _anf_chapters(filename, work, parent_map, editor):
    """(chapters with their plans, works) for one ANF work div."""
    key = (filename, work.get("id"))
    if key in _WHOLE_WORK_DIVS:
        # Its child divs are the editor's (Asterius's Elucidation): skipped, and so
        # recorded for the removal registry (1.8a). Any other would be text lost.
        for div in work:
            if isinstance(div.tag, str) and div.tag.startswith("div") and not editor.skip(div):
                raise ValueError(f"{filename}#{div.get('id')}: a whole work's child div "
                                 "that is not an editor's")
        sections = [s for s in _sections(work, parent_map) if not editor.skip(s)]
        return [(None, s, ChapterPlan(label=_heading_label(s.get("title"))))
                for s in sections], []
    chapters = []
    works: dict[str, Work] = {}
    level = _CONTAINERS.get(key)
    embedded = _EMBEDDED_WORKS.get(key, {})
    for book, elem in iter_chapters(work, parent_map, editor.skip):
        parent = parent_map.get(elem)
        book = book or (_BOOK_FIX.get((filename, parent.get("id"))) if parent is not None
                        else None)
        plan = ChapterPlan()
        if key in _RECENSIONS:
            plan = ChapterPlan(anchor=f"{elem.get('id')}/short")
        elif level:
            w = _work_of(elem, work, level, parent_map)
            if w is not None:
                if w.get("id") not in works:
                    works[w.get("id")] = _container_work(w, len(works) + 1)
                # The label names the work, unless the chapter's own label already does.
                prefix = works[w.get("id")].title
                if _chapter_label(elem).casefold() == prefix.casefold():
                    prefix = None
                plan = ChapterPlan(work_key=w.get("id"), work_label=prefix)
        else:
            div = elem.get("id", "")
            holder = next((k for k in embedded if div == k or div.startswith(k + ".")),
                          None)
            if holder:
                title, prefix, own = embedded[holder]
                if holder not in works:
                    works[holder] = Work(work_key=holder, ordinal=len(works) + 1,
                                         title=title)
                label = own or re.sub(r"^(?:The )?Preface$", "Preface",
                                      re.sub(r"^Chap\. ", "Chapter ", _chapter_label(elem)))
                plan = ChapterPlan(label=label, work_key=holder, work_label=prefix,
                                   cites=title)
        chapters.append((book, elem, plan))
    opening = _opening(filename, work) if chapters else None
    if opening:
        chapters.insert(0, opening)
    return chapters, list(works.values())


def _keeper(key):
    if key in _RECENSIONS:
        return lambda unit: recension_blocks(unit)[0]
    if key in _COMMENTARY:
        return lambda canon: commentary_blocks(canon)[0]
    return None


def _anf_document(filename, father, work, parent_map, d1):
    """One ANF work's document, or None when it is an editor's or holds no text."""
    key = (filename, work.get("id"))
    editor = _FathersEditor(filename, _source_key(filename, work), parent_map,
                            keep=_keeper(key))
    if editor.skip(work):
        return None
    fix = _AUTHOR_FIX.get((filename, d1.get("id")))
    author = fix(work) if callable(fix) else fix or father
    title = _TITLE_FIX.get(key) or _work_title(work) or father
    if key in _RECENSIONS:
        title = title.removesuffix(_RECENSION_SUFFIX)
    chapters, works = _anf_chapters(filename, work, parent_map, editor)
    return _make_doc(filename, author, title, chapters, work=work, editor=editor,
                     works=works)


# ------------------------------------------------------------------ On the Incarnation (1.8d)

class _SectionEditor(Editor):
    """Rule G for a work printed in numbered sections, each opening with the translator's
    analytical heading: "§1. Introductory.—The subject of this treatise…" in Robertson's On
    the Incarnation, his summary, not the author's (R6). The heading paragraph goes as a
    `section-summary`, recorded for the removal registry. A section that prints none (§5)
    loses only its "§5." number, a heading the label repeats."""

    def chapter(self, elem, label):
        return self._sectioned(super().chapter(elem, label), elem, label)

    def _sectioned(self, edit, elem, label):
        """`edit` with the section's heading or number taken out; its `again()` (the
        audit's fresh edit, `tests/test_editorial.py`) takes out the same."""
        plain = edit.again
        edit.again = lambda: self._sectioned(plain(), elem, label)
        n = int(label.removeprefix("Section "))
        lead = next(b for b in direct_blocks(elem)
                    if _block_text(b) and id(b) not in edit.dropped)
        text = _block_text(lead)
        m = _SECTION_NUMBER.match(text)
        if m is None or int(m.group(1)) != n:
            raise ValueError(f"{elem.get('id')}: does not open with §{n}")
        locator = edit.locators[id(lead)]
        if _norm(text[m.end():]) == _norm(elem.get("title") or ""):
            edit.dropped[id(lead)] = "section-summary"
            edit.removed.append(Removed(locator, "section-summary", text))
            return edit
        inner, cut = edit.edit, []

        def without_number(block, marked, notes):
            marked, notes = inner(block, marked, notes)
            if block is lead:
                number = _SECTION_NUMBER.match(marked)
                if not cut:
                    cut.append(number.group(0))
                    edit.removed.append(Removed(locator, "heading", number.group(0).strip()))
                marked = marked[number.end():]
            return marked, notes

        edit.edit = without_number
        return edit


def _section_chapters(work) -> list:
    """The work's sections, labelled "Section 1" to "Section N" in order."""
    sections = [d for d in work if isinstance(d.tag, str) and d.tag.startswith("div")]
    if any(direct_blocks(work)) or any(not direct_blocks(d) for d in sections):
        raise ValueError(f"{work.get('id')}: text outside its sections")
    return [(None, d, ChapterPlan(label=f"Section {k}")) for k, d in enumerate(sections, 1)]


def _volume_documents(filename, root, parent_map) -> list[Document]:
    divs = {e.get("id"): e for e in root.iter() if e.get("id")}
    docs = []
    for work_id, author in VOLUME_WORKS[filename].items():
        work = divs[work_id]
        editor = _SectionEditor(filename, _source_key(filename, work), parent_map)
        d = _make_doc(filename, author, _work_title(work), _section_chapters(work),
                      work=work, editor=editor)
        if d:
            docs.append(d)
    return docs


# ------------------------------------------------------------------ 5.6a: NPNF additions

class _NpnfEditor(Editor):
    """Rule G for a work an NPNF volume adds (5.6a): the work's `skip` divs, and in each
    chapter the editors' head lines over the text (`_npnf_head`: "Chapter I.", "Homily
    I.", "Letter VIII." and the title under it), which the chapter label carries instead
    (Decision log "Editors' chapter titles in passage text"). They count as heading lines,
    a letter's title line too, since its label names it."""

    def __init__(self, source_file, source_key, parent_map, skip, style="basil"):
        super().__init__(source_file, source_key, parent_map)
        self.skips = skip
        self.style = style

    def skip(self, elem) -> bool:
        if elem.get("id") in self.skips:
            _record(self.source_key, elem.get("id"), (elem.get("title") or "").strip())
            return True
        return super().skip(elem)

    def chapter(self, elem, label):
        return self._headed(super().chapter(elem, label), elem)

    def _headed(self, edit, elem):
        """`edit` with the chapter's head lines dropped as heading lines; its `again()`
        (the audit's fresh edit) drops the same."""
        plain = edit.again
        edit.again = lambda: self._headed(plain(), elem)
        head = (_HEADS[self.style](self.source_file, elem, self.parent_map)
                if elem.get("id") not in _PART_DIVS else _Head(None, "", []))
        for r in edit.removed:
            if r.kind == "letter-title":
                r.kind = "heading"
        for k, kind in edit.dropped.items():
            if kind == "letter-title":
                edit.dropped[k] = "heading"
        cut = [(b, "heading") for b in head.lines] + [(b, "editor-note") for b in head.notes]
        tail = _NPNF_TAILS.get((self.source_file, elem.get("id")))
        blocks = direct_blocks(elem)
        if tail is not None:
            at = [b.get("id") for b in blocks].index(tail)
            cut += [(b, "editor-note") for b in blocks[at:] if _block_text(b)]
        if self.style != "basil":
            # Rule lines between sections ("______"), the editor's typography.
            cut += [(b, "heading") for b in blocks if RULE_LINE.match(_block_text(b) or "x")]
        if self.style == "letters207":
            # A paragraph wholly in parentheses is the editor's in Gregory's letters, at
            # their end too ("(We insert here the three letters to Eusebius…)").
            cut += [(b, "editor-note") for b in blocks
                    if (t := _text(b)).startswith("(") and t.endswith(")")]
        for b, kind in cut:
            if id(b) not in edit.dropped:
                edit.dropped[id(b)] = kind
                edit.removed.append(Removed(edit.locators[id(b)], kind, _block_text(b)))
        greek = NOT_ENGLISH.get((self.source_file, elem.get("id")), frozenset())
        found = set()
        for b in direct_blocks(elem):
            key = span_sha1(_block_text(b))
            if key in greek:
                found.add(key)
                edit.dropped[id(b)] = "not-english"
                edit.removed.append(Removed(edit.locators[id(b)], "not-english",
                                            _block_text(b)))
        if found != greek:
            raise ValueError(f"{elem.get('id')}: rule-E paragraphs not found: "
                             f"{sorted(greek - found)}")
        inner, read = edit.edit, set()

        def without_comparisons(block, marked, notes):
            marked, notes = inner(block, marked, notes)
            for span in _NPNF_EDITOR_SPANS.get((self.source_file, block.get("id")), ()):
                if marked.count(span) != 1:
                    raise ValueError(f"{block.get('id')}: {span!r} is not printed once")
                marked = marked.replace(span, "")
                if id(block) not in read:
                    edit.removed.append(Removed(edit.locators[id(block)], "bracket",
                                                span.strip()))
            if "[" not in marked:
                read.add(id(block))
                return marked, notes
            out, spans, cuts = _cut_brackets(
                marked, lambda span: bool(_NPNF_EDITOR_BRACKET.search(span)
                                          or _NPNF_NOTE_BRACKET.match(span)))
            if id(block) not in read:           # paragraph_segments reads it again
                read.add(id(block))
                edit.removed += [Removed(edit.locators[id(block)], "bracket", t)
                                 for t in spans]
            if cuts:
                marks = [k for k, c in enumerate(marked) if c == "\u2063"]
                notes = [n for n, at in zip(notes, marks)
                         if not any(a <= at < b for a, b in cuts)]
            return out, notes

        edit.edit = without_comparisons
        return edit


# The classes of an NPNF volume's body paragraphs; a chapter's head is every paragraph
# from its number line to the first of them.
_NPNF_BODY_CLASSES = frozenset({"c20", "c21"})
# Chapter divs made by `_letter_part`, which print no head.
_PART_DIVS: set[str] = set()


@dataclass
class _Head:
    """What a chapter prints over its text, as one volume's head reader reads it."""
    number: str | None                  # the label's number: "Chapter V", "Letter CCII"
    title: str                          # the label's title, as printed
    lines: list                         # number and title lines, dropped (the label says them)
    notes: list = field(default_factory=list)       # the editor's notes, dropped (rule G)
    epigraphs: list = field(default_factory=list)   # Cyril's Scripture reading, kept, marked
    headings: list = field(default_factory=list)    # (paragraph, level): the work's own


def _basil_head(filename, elem, parent_map=None) -> _Head:
    kind, n, title, head = _npnf_head(elem)
    return _Head(f"{kind} {n}", title, head)


def _text(block) -> str:
    return " ".join(_block_text(block).split())


def _attr_title(elem) -> str:
    return " ".join((elem.get("title") or "").split()).rstrip(" .")


def _lecture_head(filename, elem, parent_map=None) -> _Head:
    """A lecture's head is everything above its first paragraph of text: the title page
    lines of the series (the Procatechesis, the Mystagogical Lectures), the number line,
    the title, and the Scripture reading Cyril set for it, which stays as an epigraph. His
    own headings inside the lecture stay too, level 2."""
    blocks = [b for b in direct_blocks(elem) if _text(b)]
    start = next((k for k, b in enumerate(blocks) if b.get("class") in (None, "c23")), None)
    if start is None:
        raise ValueError(f"{elem.get('id')}: no text")
    number, lines, readings = None, [], []
    for b in blocks[:start]:
        t = _text(b)
        m = _LECTURE_NUMBER.match(t)
        if m:
            number = f"Lecture {m.group(1) or 'I'}"
        if b.get("class") in _READING_CLASSES or (b.get("class") == "Centered"
                                                   and t.startswith("With a ")):
            readings.append(b)
        else:
            lines.append(b)
    headings = [(b, 2) for b in blocks[start:] if b.get("class") == _LECTURE_HEADING_CLASS]
    return _Head(number, _attr_title(elem), lines, epigraphs=readings, headings=headings)


def _oration_head(filename, elem, parent_map=None) -> _Head:
    """An oration's head runs to its first numbered section ("I.", "1."). Above it, the
    lines up to the number and the title lines under it go to the label; the rest is the
    editor's: his introduction, his dating and his analysis of the oration."""
    blocks = [b for b in direct_blocks(elem) if _text(b)]
    start = next(k for k, b in enumerate(blocks)
                 if b.get("class") in (None, "c23") and _NUMBERED.match(_text(b)))
    head = blocks[:start]
    at = next((k for k, b in enumerate(head) if _ORATION_NUMBER.match(_text(b))), None)
    if at is None:
        n, at = _ORATION_FIX[(filename, elem.get("id"))], -1
    else:
        n = _ORATION_NUMBER.match(_text(head[at])).group(1)
    lines, notes, titles = list(head[:at + 1]), [], True
    for b in head[at + 1:]:
        t = _text(b)
        titles = titles and len(t) < 200 and not t.startswith("(") \
            and "a.d." not in t.lower() and not re.match(r"(?:Delivered|Preached) ", t)
        (lines if titles else notes).append(b)
    # "Introduction to Oration II." and its text stand above the number line.
    notes += [b for b in head[:at + 1] if len(_text(b)) >= 200]
    lines = [b for b in lines if b not in notes]
    return _Head(f"Oration {n}", _attr_title(elem), lines, notes)


def _letter207_head(filename, elem, parent_map=None) -> _Head:
    """A letter's head in NPNF2-07: the division and section heads over the first letter
    of each, the "Ep. N." line (with its address, or after it), and the editor's notes in
    parentheses, which date the letter or say what it answers."""
    blocks = [b for b in direct_blocks(elem) if _text(b)]
    lines, notes, number, address = [], [], None, None
    k = 0
    while k < len(blocks):
        b, t = blocks[k], _text(blocks[k])
        ep = _EP.search(t) if len(t) < 200 and (
            b.get("class") == "c42" or t.startswith("Ep.") or "(Ep." in t) else None
        if ep:
            number = number or ep.group(1)
            rest = re.sub(r"\(?\bEp\. [CLXVI]+\.?\)?|\(About a\.d\. \d+\)\.?|\band [CLXVI]+\.",
                          "", t).strip(" .")
            address = address or rest or None
            lines.append(b)
        elif t.startswith("(") and t.endswith(")"):
            notes.append(b)
        elif b.get("class") in ("c39", "c27", "c57", "c5", "c56") and len(t) < 200:
            lines.append(b)
        else:
            break
        k += 1
    number = _LETTER_FIX.get((filename, elem.get("id")), number)
    if number is None:
        raise ValueError(f"{elem.get('id')}: no Ep. line")
    if address is None:
        title = _attr_title(elem)
        parent = elem
        while address is None and parent is not None:
            parent = parent_map.get(parent)
            if parent is None:
                break
            address = _LETTER_ADDRESS.get((filename, parent.get("id")))
            if address is None and _attr_title(parent).startswith("To "):
                address = _attr_title(parent)
        if address is None and not re.fullmatch(r"Letter [CLXVI]+", title):
            address = title
    return _Head(f"Letter {number}", address or "", lines, notes)


def _npnf_head(elem) -> tuple[str, str, str, list]:
    """("Letter", "VIII", the title as printed, the head's paragraphs): the lines over a
    chapter, homily or letter that number and title it, as the volume prints them. The
    title comes from the printed line, not the div's title attribute, which CCEL garbled
    in places ("That v: not found “of whom”…")."""
    blocks = direct_blocks(elem)
    at = next((k for k, b in enumerate(blocks) if _NPNF_NUMBER.match(_block_text(b))), None)
    if at is None:
        raise ValueError(f"{elem.get('id')}: no number line")
    kind, n = _NPNF_NUMBER.match(_block_text(blocks[at])).groups()
    end = next((k for k in range(at + 1, len(blocks))
                if blocks[k].get("class") in _NPNF_BODY_CLASSES), len(blocks))
    head = blocks[at:end]
    # The first canonical letters print the canonists' name over their address line
    # ("(Canonica Prima.)"); the address is the title.
    titles = [t for b in head[1:] if (t := " ".join(_block_text(b).split()))
              and not _CANONICA.match(t)]
    if not titles or at != 0 or len(head) > 3:
        raise ValueError(f"{elem.get('id')}: a head of {len(head)} lines, titled {titles}")
    return kind, n, titles[0].rstrip(" ."), head


# NPNF2-12: Leo's "Letter I." or "Sermon I." and the address or title under it.
_LEO_NUMBER = re.compile(r"^(Letter|Sermon) ([IVXLC]+)\.$")
# Where a Leo div's own letter starts, when the div opens with Feltoe's summary of the
# letters around it (Letters LV to LVIII: four summarized, LVI printed).
_LEO_FROM = {("npnf212.xml", "ii.iv.lv"): "ii.iv.lv-p7"}
# The classes Feltoe prints the editors' chapter summaries in ("I. Through the negligence
# of the authorities…", "He thanks him for his information…"): the Ballerini's and
# Quesnel's, not Leo's (rule G). Leo's salutations and the questions Rusticus put to him
# (Letter CLXVII) are printed in the same classes, and stay.
_LEO_SUMMARY_CLASSES = frozenset({"c27", "c30", "c31", "c33"})
# A salutation in parentheses is Leo's own only when it opens with his name (Letter CLIX);
# "(To Marcian Augustus, about…)" is Feltoe's summary (Letter CIV).
_LEO_SALUTATION = re.compile(r"^(?:\(?Leo\b|To )")
_LEO_QUESTION = re.compile(r"^Question [IVXL]+\.")


def _wholly_editorial(t: str) -> bool:
    """A paragraph that is all the editor's summary: in parentheses or brackets."""
    t = t.rstrip(".")
    return (t.startswith("(") and t.endswith(")")) or (t.startswith("[") and t.endswith("]"))


def _leo_head(filename, elem, parent_map=None) -> _Head:
    """A letter's or sermon's head in NPNF2-12's Leo: the series lines over the first
    ("Letters.", a rule), "Letter N." or "Sermon N.", and the address or title. The
    editors' chapter summaries and Feltoe's summaries in parentheses, wherever they
    stand, are notes (rule G)."""
    blocks = [b for b in direct_blocks(elem) if _text(b)]
    start = _LEO_FROM.get((filename, elem.get("id")))
    k0 = [b.get("id") for b in blocks].index(start) if start else 0
    at = next((k for k in range(k0, len(blocks)) if _LEO_NUMBER.match(_text(blocks[k]))),
              None)
    if at is None:
        raise ValueError(f"{elem.get('id')}: no number line")
    kind, n = _LEO_NUMBER.match(_text(blocks[at])).groups()
    # Feltoe's pointer to another volume ("(See vol. iii. of this Series, p. 293.)") and a
    # period inside the closing quotation mark are not the title's.
    title = re.sub(r"\s*\(See vol\. [^)]*\)$", "", _attr_title(elem))
    title = re.sub(r"\.(”)$", r"\1", title).rstrip(" .")
    lines = blocks[:at + 1]
    if at + 1 < len(blocks) and blocks[at + 1].get("class") in ("c26", "c32"):
        lines.append(blocks[at + 1])
    rest = blocks[len(lines):]
    notes = [b for b in rest if (b.get("class") in _LEO_SUMMARY_CLASSES
                                 or _wholly_editorial(_text(b)))
             and not _LEO_SALUTATION.match(_text(b)) and not _LEO_QUESTION.match(_text(b))]
    headings = [(b, 2) for b in rest if _LEO_QUESTION.match(_text(b))]
    if start:
        notes = blocks[:k0] + notes
        lines = [b for b in lines if b not in notes]
        title = _text(blocks[at + 1]).strip("().") if at + 1 < len(blocks) else title
    return _Head(f"{kind} {n}", title, lines, notes, headings=headings)


# NPNF2-12: the Pastoral Rule's four Parts, by div.
_PASTORAL_PARTS = {"iii.iv.ii": "I", "iii.iv.iii": "II", "iii.iv.iv": "III", "iii.iv.v": "IV"}
_PASTORAL_LINE_CLASSES = frozenset({"c25", "c23", "c37", "c39", "Centered"})
_CHAPTER_LINE = re.compile(r"^(?:Chapter ([IVXLC]+)|Prologue)\.$")


def _pastoral_head(filename, elem, parent_map=None) -> _Head:
    """A chapter's head in the Pastoral Rule: the book's title lines over the first, the
    Part's number and title over each Part's first, "Chapter N." and the chapter's title.
    Gregory's letter to John that opens the book stays, and so does his own list heading
    in Part III ("Differently to be admonished are these that follow:—")."""
    blocks = [b for b in direct_blocks(elem) if _text(b)]
    lines, number, after_number = [], None, False
    for b in blocks:
        t = _text(b)
        m = _CHAPTER_LINE.match(t)
        if m:
            number = f"Chapter {m.group(1)}" if m.group(1) else "Prologue"
            after_number = True
        elif b.get("class") in _PASTORAL_LINE_CLASSES or (after_number
                                                          and b.get("class") == "c30"):
            after_number = False
        else:
            break
        lines.append(b)
    part = _PASTORAL_PARTS.get(elem.get("id")) or _PASTORAL_PARTS[parent_map[elem].get("id")]
    title = "" if number == "Prologue" else _attr_title(elem)
    if number is None and elem.get("id") != "iii.iv.v":
        number = _attr_title(elem)
        title = ""
    label = f"Part {part}, {number}" if number else f"Part {part}"
    return _Head(label, title, lines)


_EPISTLE = re.compile(r"^Epistle ([IVXLC]+)\.?$")
_BOOK = re.compile(r"^Book ([IVXLC]+)\b")
# The Register's first book prints its number on the letter's head, not on its div, whose
# title is the indiction line.
_REGISTER_BOOKS = {("npnf212.xml", "iii.v.i"): "I"}
# The headings of the Book of Answers (Book XI, 64): Augustine of Canterbury's questions
# and requests, and the answers and grant that follow each ("Augustine's first question",
# "Answer of the blessed pope Gregory."), level 2.
_AUGUSTINE_QUESTION = re.compile(r"^(?:Augustine[’']s (?:\w+ )?(?:question|request)|Answer of "
                                 r"(?:Saint|the blessed) [Pp]ope Gregory|Answer of Saint "
                                 r"Gregory|The grant of Gregory)\b")
# A manuscript's title line over a letter ("Here begins the epistle of the blessed
# Gregory…"), which the label's address says (Book XI, 64).
_INCIPIT = re.compile(r"^Here (?:begins|follows) the (?i:epistle)\b")


def _register_head(filename, elem, parent_map=None) -> _Head:
    """A letter's head in Gregory's Register (NPNF2-12 and NPNF2-13): the Register's and
    the Book's lines over the first letter of each Book, with the Book's indiction line,
    "Epistle N." and the address. Gregory's own salutation under it stays."""
    blocks = [b for b in direct_blocks(elem) if _text(b)]
    at = next((k for k, b in enumerate(blocks) if _EPISTLE.match(_text(b))), None)
    if at is None:
        raise ValueError(f"{elem.get('id')}: no Epistle line")
    n = _EPISTLE.match(_text(blocks[at])).group(1)
    lines = blocks[:at + 2]
    while len(lines) < len(blocks) and _INCIPIT.match(_text(blocks[len(lines)])):
        lines.append(blocks[len(lines)])
    parent = parent_map[elem]
    book = _REGISTER_BOOKS.get((filename, parent.get("id")))
    if book is None:
        m = _BOOK.match(_attr_title(parent))
        if m is None:
            raise ValueError(f"{elem.get('id')}: no Book")
        book = m.group(1)
    headings = [(b, 2) for b in blocks if _AUGUSTINE_QUESTION.match(_text(b))]
    # Barmby's notes in brackets inside a letter: a manuscript's dating, a pointer to the
    # same words in another letter (rule G).
    notes = [b for b in blocks[len(lines):] if _wholly_editorial(_text(b))]
    return _Head(f"Book {book}, Letter {n}", _attr_title(elem), lines, notes,
                 headings=headings)


_HEADS = {"basil": _basil_head, "lectures": _lecture_head, "orations": _oration_head,
          "letters207": _letter207_head, "leo": _leo_head, "pastoral": _pastoral_head,
          "register": _register_head}


def _letter_part(filename, letter, parent_map):
    """The part of `letter` another writer wrote, or another version of it
    (`_LETTER_PARTS`), moved out of it into a chapter div of its own, `<letter>/<n>`, or
    None."""
    part = _LETTER_PARTS.get((filename, letter.get("id")))
    if part is None:
        return None
    first, label = part
    blocks = direct_blocks(letter)
    ids = [b.get("id") for b in blocks]
    if first not in ids:
        raise ValueError(f"{letter.get('id')}: {first} is not one of its paragraphs")
    n = label.split()[-1]
    chapter = Element(letter.tag, {"id": f"{letter.get('id')}/{n}", "title": label})
    for b in blocks[ids.index(first):]:
        letter.remove(b)
        chapter.append(b)
    parent_map[chapter] = parent_map.get(letter)
    _PART_DIVS.add(chapter.get("id"))
    return chapter, label


def _npnf_document(filename, w: NpnfWork, work, parent_map):
    editor = _NpnfEditor(filename, _source_key(filename, work), parent_map, w.skip, w.style)
    groups = dict(w.groups)
    chapters, works = [], []
    group = None
    for _, elem in list(iter_chapters(work, parent_map, editor.skip,
                                      front_matter=lambda title: False)):
        head = _HEADS[w.style](filename, elem, parent_map)
        title = _clip(head.title)
        # The work's own headings stay in the text, marked (#452): Cyril's reading as an
        # epigraph, his headings inside a lecture at their level.
        marks = tuple([(b.get("id"), None, False) for b in head.epigraphs]
                      + [(b.get("id"), level, False) for b, level in head.headings])
        if elem.get("id") in groups:
            group = groups[elem.get("id")]
            works.append(Work(work_key=group[0], ordinal=len(works) + 1, title=group[1],
                              author=w.author))
        if w.works:
            works.append(Work(work_key=elem.get("id"), ordinal=len(works) + 1,
                              title=head.number, author=w.author))
            chapters.append((None, elem, ChapterPlan(
                label=title, work_key=elem.get("id"), work_label=head.number,
                headings=marks)))
            continue
        if not w.letters:
            label = f"{head.number}. {title}" if head.number and title \
                else head.number or title
            chapters.append((None, elem, ChapterPlan(
                label=label, work_key=group[0] if group else None, headings=marks)))
            continue
        number = head.number
        part = _letter_part(filename, elem, parent_map)
        works.append(Work(work_key=elem.get("id"), ordinal=len(works) + 1, title=number,
                          author=_NPNF_SENDERS.get((filename, elem.get("id")), w.author)))
        chapters.append((None, elem, ChapterPlan(label=title, work_key=elem.get("id"),
                                                 work_label=number, any_length=True,
                                                 headings=marks)))
        if part is not None:
            div, label = part
            works.append(Work(work_key=div.get("id"), ordinal=len(works) + 1,
                              title=f"{number}, {label}", author=w.author))
            chapters.append((None, div, ChapterPlan(
                label=f"{title}: {label}", work_key=div.get("id"), work_label=number,
                any_length=True, headings=tuple(
                    (b.get("id"), _PART_HEADINGS[b.get("id")], False)
                    for b in direct_blocks(div) if b.get("id") in _PART_HEADINGS))))
    return _make_doc(filename, w.author, w.title, chapters, work=work, editor=editor,
                     works=works)


def _npnf_documents(filename, root, parent_map) -> list[Document]:
    divs = {e.get("id"): e for e in root.iter() if e.get("id")}
    return [d for w in NPNF_WORKS[filename]
            if (d := _npnf_document(filename, w, divs[w.div], parent_map))]


# ------------------------------------------------------------------ NPNF Augustine (1.8b)

def _npnf_front_matter(title: str) -> bool:
    """Front matter, except a "Preface": in these volumes that is Augustine's own (City
    of God V to VII, On Christian Doctrine); the translators' are `Editor.skip`'s."""
    return _cf_skippable(title) and title.strip().rstrip(".").lower() != "preface"


class _AugustineEditor(Editor):
    """Rule G for an NPNF Augustine work, and the quotations of Augustine kept from the
    editors' matter it skips (`ingest.editorial_keep`)."""

    def __init__(self, source_file, source_key, parent_map, quotes):
        super().__init__(source_file, source_key, parent_map, book_text=True)
        self.quotes = {q.anchor: q for q in quotes}

    def chapter(self, elem, label):
        quote = self.quotes.get(elem.get("id"))
        return QuoteEdit(quote) if quote else super().chapter(elem, label)


def _quote_chapter(quote, div, parent_map):
    """A kept quotation as a chapter div of its own, `<div>/<slug>`, holding the
    paragraphs it spans."""
    blocks = direct_blocks(div)
    ids = [b.get("id") for b in blocks]
    chapter = Element("div4", {"id": quote.anchor, "title": quote.label})
    for b in blocks[ids.index(quote.first):ids.index(quote.last) + 1]:
        chapter.append(b)
    parent_map[chapter] = div
    quoted_in = (div.get("title") or "").strip().rstrip(".").replace("’", "'").lower()
    return (None, chapter, ChapterPlan(label=quote.label, any_length=True,
                                       meta={"from": quote.source, "quoted_in": quoted_in}))


def _augustine_document(filename, work, parent_map):
    """One NPNF Augustine work: City of God, On Christian Doctrine, or one of the 16
    treatises. Author Augustine; the editors' matter goes (rule G), Augustine's prefaces
    and the quotations of him in it stay."""
    source_key = _source_key(filename, work)
    divs = {e.get("id"): e for e in work.iter() if e.get("id")}
    quotes = [q for q in kept_quotes(filename) if q.div in divs]
    editor = _AugustineEditor(filename, source_key, parent_map, quotes)
    if direct_blocks(work):
        editor.title_page(work)
    order = {id(e): k for k, e in enumerate(work.iter())}
    chapters = [(order[id(elem)], 0, (book, elem)) for book, elem in
                iter_chapters(work, parent_map, editor.skip, front_matter=_npnf_front_matter)]
    chapters += [(order[id(divs[q.div])], k, _quote_chapter(q, divs[q.div], parent_map))
                 for k, q in enumerate(quotes, 1)]
    title = smart_title_case((work.get("title") or "").strip())
    return _make_doc(filename, "Augustine", title, [c for *_, c in sorted(chapters)],
                     work=work, editor=editor)


class _CallerEditor:
    """Takes the Confessions' four plain-digit footnote callers out (1.8b); nothing else."""

    def chapter(self, elem, label):
        return self

    label_title = None

    def edit(self, block, marked, notes):
        for printed, without in PLAIN_CALLERS.get(("confessions.xml", block.get("id")), ()):
            if marked.count(printed) != 1:
                raise ValueError(f"{block.get('id')}: {printed!r} is not printed once")
            marked = marked.replace(printed, without)
        return marked, notes


def build_documents(path: str) -> list[Document]:
    filename = os.path.basename(path)
    if filename == "summa.xml":
        return []
    root = _read_root(path)
    parent_map = _build_parent_map(root)
    docs: list[Document] = []

    if filename in VOLUME_WORKS:
        return _volume_documents(filename, root, parent_map)
    if filename in NPNF_WORKS:
        return _npnf_documents(filename, root, parent_map)
    single = _SINGLE_AUTHOR.get(filename)
    if single:
        title = smart_title_case((root.findtext(".//DC.Title") or "Unknown").strip())
        chapters = list(iter_chapters(root, parent_map))
        editor = _CallerEditor() if filename == "confessions.xml" else None
        d = _make_doc(filename, single, title, chapters, editor=editor)
        if d:
            docs.append(d)
        return docs

    div1s = [d for d in root.iter("div1") if not _cf_skippable(d.get("title") or "")]
    if filename in _AUGUSTINE_FILES:
        # div1 = work, or in the treatise volume div2 = work (1.8b); author Augustine.
        works = ([w for d1 in div1s for w in d1.findall("div2")
                  if not _cf_skippable(w.get("title") or "")]
                 if filename in _WORK_PER_DIV2 else div1s)
        for w in works:
            d = _augustine_document(filename, w, parent_map)
            if d:
                docs.append(d)
    else:
        # Multi-author volume: div1 = father, div2 = work (else father itself is the work).
        # These are the ANF volumes, where rule G takes the editors' matter out (1.8a).
        for d1 in div1s:
            father = smart_title_case((d1.get("title") or "").strip())
            editor = Editor(filename, _source_key(filename, d1), parent_map)
            if editor.skip(d1):
                continue
            works = [w for w in d1.iter("div2") if not _cf_skippable(w.get("title") or "")]
            for w in works or [d1]:
                d = _anf_document(filename, father, w, parent_map, d1)
                if d:
                    docs.append(d)
    return docs


# ------------------------------------------------------------------ 3.3: rule E

# Paragraphs the ANF translators left in Latin inside passages that are otherwise English,
# by (document ID, passage anchor): the sha1 of each paragraph (`editorial.span_sha1`),
# never its text. They are cut and the passage keeps its ID (Carter, 14 Nov 2026); each
# has a `span` entry in the removal registry. The wholly Latin passages are `passage`
# entries, which `build_all` skips through `registry.drop_removed`, as the papal adapters
# do, so the release report's raw build agrees with the stage.
NON_ENGLISH_PARAGRAPHS = {
    ("96584290-90c2-50bc-9d3d-c353b8969e1f", "vi.iii.ii.x"):
        frozenset({"1028a38462d03a8677a6d83b71afffc696f2af6a"}),
    ("96584290-90c2-50bc-9d3d-c353b8969e1f", "vi.iii.ii.x/from-p30"):
        frozenset({"33b265ad15540da891491b2b4cb3b47488fbd422"}),
    ("f913305f-b259-578b-a5ca-532fac927aab", "iii.iv.xiii"):
        frozenset({"0e4c520e29733fbcd27902da4661a375fd97d8c3"}),
}
# The works that lose passages to rule E and keep the rest: the Instructor, the Divine
# Institutes and On the Workmanship of God (3.3's note, approved 14 Nov 2026). The
# Stromata left the list when Book III came back in Chadwick's English (#399).
NON_ENGLISH_OMITTED = frozenset({
    "96584290-90c2-50bc-9d3d-c353b8969e1f", "9e03c96d-8295-5e5e-a4d3-3570ddcf0415",
    "f913305f-b259-578b-a5ca-532fac927aab"})
NON_ENGLISH_NOTE = ("Some passages are omitted: the translators left them in Latin and no "
                    "public-domain English translation exists.")


def _without_paragraphs(passage, cut: frozenset[str]):
    """The passage without the paragraphs whose sha1 is in `cut`. Each must be found, so
    a source change that moves one fails the build instead of leaving Latin in place.
    A split piece's `source_units` and its footnotes' offsets move with the text they
    point at; a unit that opens a cut paragraph, or a note placed in one, is dropped and
    the notes left are renumbered."""
    parts = passage.content.split("\n\n")
    found = {span_sha1(p) for p in parts} & cut
    if found != cut:
        raise ValueError(f"{passage.anchor}: rule-E paragraphs not found: "
                         f"{sorted(cut - found)}")
    kept, spans, starts, at = [], [], [], 0   # spans: (start, end) of each cut
    for p in parts:
        end = at + len(p)
        starts.append(at)
        if span_sha1(p) in cut:
            spans.append((at, min(end + 2, len(passage.content))))
        else:
            kept.append(p)
        at = end + 2

    def moved(offset: int) -> int:
        return offset - sum(end - start for start, end in spans if offset >= end)

    # A unit's offset is measured before the text is cleaned, so it lands near, not on,
    # the start of its paragraph: it belongs to the paragraph whose start is nearest.
    # One in a cut paragraph has no text left in the piece; the rest move to the start
    # of their paragraph in the new text.
    units = []
    for loc, off in passage.source_units:
        start = min(starts, key=lambda a: abs(a - off))
        if not any(a == start for a, _ in spans):
            units.append((loc, moved(start)))
    units = tuple(units)
    metadata = passage.metadata
    if metadata and metadata.get("footnotes"):
        # A note sits after the character at `at`; one inside a cut paragraph goes with it.
        notes = [n for n in metadata["footnotes"]
                 if not any(start < n["at"] <= end for start, end in spans)]
        metadata = {**metadata, "footnotes": [
            {**n, "n": i, "at": moved(n["at"])} for i, n in enumerate(notes, 1)]}
        if not metadata["footnotes"]:
            del metadata["footnotes"]
    return replace(passage, content="\n\n".join(kept), source_units=units,
                   metadata=metadata)


def _rule_e(document: Document) -> Document:
    passages = [_without_paragraphs(p, NON_ENGLISH_PARAGRAPHS[(document.id, p.anchor)])
                if (document.id, p.anchor) in NON_ENGLISH_PARAGRAPHS else p
                for p in document.passages]
    if document.id in NON_ENGLISH_OMITTED:
        if document.notes:
            raise ValueError(f"{document.title} already has notes")
        return replace(document, passages=passages, notes=NON_ENGLISH_NOTE)
    return replace(document, passages=passages)


def _without_empty_works(document: Document) -> Document:
    """An NPNF addition (5.6a) without the works whose passages the removal registry
    retires (rule A's letters), so the reader's list of works names only what it holds.
    The registry keeps their rows; documents built before 5.6a are left as published."""
    if (document.metadata or {}).get("source_file") not in NPNF_WORKS:
        return document
    used = {p.work_key for p in document.passages}
    return replace(document, works=[w for w in document.works if w.work_key in used])


def build_all() -> list[Document]:
    docs: list[Document] = []
    for path in sorted(glob(os.path.join(_SRC_DIR, "*.xml"))):
        if path.endswith(".Zone.Identifier"):
            continue
        docs.extend(build_documents(path))
    # A work an open `document` removal retires (rules A to C, 3.1) emits nothing, and a
    # unit a `passage` removal retires is skipped, as the papal adapters do: the adapter
    # asks the registry, never an author or title.
    held = removed_document_ids()
    # Stromata III, which ANF left in Latin, is read from Chadwick's English (#399).
    docs = [_without_empty_works(drop_removed(_rule_e(stromata_chadwick.restore(d))))
            for d in distinct_titles(docs) if d.id not in held]
    built = {(d.id, p.anchor) for d in docs for p in d.passages}
    missing = sorted(set(NON_ENGLISH_PARAGRAPHS) - built)
    if missing:
        raise ValueError(f"rule-E passages not built: {missing}")
    return docs
