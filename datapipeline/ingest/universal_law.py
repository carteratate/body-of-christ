"""Universal law outside the Code: Universi Dominici Gregis, corpus-cleanup 5.4 (#203).

The Church law collection's second source (`sources/church-law/`), beside the 1983 Code
(`ingest/canon_law.py`). John Paul II's apostolic constitution on the vacancy of the
Apostolic See and the election of the Roman Pontiff (22 February 1996), in three
documents, all from vatican.va's English:

- **Universi Dominici Gregis (as amended 2013)**, the consolidated text vatican.va
  publishes as current since Benedict XVI's *Normas nonnullas* (22 February 2013). It is
  searchable: questions about how a pope is elected are answered from it (rule F).
- **Universi Dominici Gregis (1996 original)**, the text as first promulgated, from
  vatican.va's PDF, and **Normas Nonnullas** (2013), the motu proprio that amended it.
  Both are superseded text kept as history (D5): every passage has `searchable = False`,
  and the registry points each at the current text (`superseded_by`, works.json).

*De aliquibus mutationibus* (2007), which replaced No. 75 before *Normas nonnullas*
replaced it again, is Latin only on vatican.va, so it is not added (rule E, revised
29 Oct 2026); Normas Nonnullas' note says where its Latin is published. The Congregation of Cardinals'
declaration of 30 April 2025 on No. 33 is a dispensation, not an amendment (source
memo), so it is only named in the current text's note.

One passage per number (`No. 75`), with the paragraphs that run on after it; the preamble
and the promulgation one passage per paragraph. Chapters are the constitution's own:
`part-1/chapter-1` ("Part One, Chapter I: The Powers of the College of Cardinals …"),
with the preamble and the promulgation chapters of their own. The Part and Chapter
headings stay in the text of the passage they open, marked with `headings.MarkedText`
(#445). The page's notes, its callers ("[13]"), the "n" vatican.va sets beside each
amended number, and its list of what was amended (kept as the document's note) are left
out. Normas nonnullas is one chapter: its two opening paragraphs, one passage per norm
it replaces ("No. 46 § 1"), and its closing.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

import headings
from config import settings
from identity import PIECE_MARK, anchor as make_anchor
from ingest.pieces import pack_units
from model import Document, Passage
from normalize.caps import smart_title_case
from normalize.footnotes import strip_note_callers
from normalize.text import clean_text
from registry import ANCHOR_SCHEME, resolve_document_id

COLLECTION = "church-law"
SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "sources", COLLECTION)

_VATICAN = "https://www.vatican.va/content/"


@dataclass(frozen=True)
class Edition:
    slug: str
    file: str
    title: str
    cite: str               # how a passage's reference names it
    author: str
    year: int
    url: str
    genre: str
    searchable: bool


CURRENT = Edition(
    "universi-dominici-gregis", "universi-dominici-gregis.html",
    "Universi Dominici Gregis (as amended 2013)", "Universi Dominici Gregis",
    "Pope John Paul II", 1996,
    _VATICAN + "john-paul-ii/en/apost_constitutions/documents/"
               "hf_jp-ii_apc_22021996_universi-dominici-gregis.html",
    "apostolic-constitution", True)
ORIGINAL = Edition(
    "universi-dominici-gregis-1996", "universi-dominici-gregis-1996.pdf",
    "Universi Dominici Gregis (1996 original)", "Universi Dominici Gregis (1996)",
    "Pope John Paul II", 1996,
    _VATICAN + "dam/john-paul-ii/pdf/apost_constitutions/documents/"
               "universi-dominici-gregis-19960222_en.pdf",
    "apostolic-constitution", False)
NORMAS = Edition(
    "normas-nonnullas", "normas-nonnullas.html", "Normas Nonnullas", "Normas Nonnullas",
    "Pope Benedict XVI", 2013,
    _VATICAN + "benedict-xvi/en/motu_proprio/documents/"
               "hf_ben-xvi_motu-proprio_20130222_normas-nonnullas.html",
    "motu-proprio", False)
EDITIONS = (CURRENT, ORIGINAL, NORMAS)

NUMBERS = 92
# The numbers Normas nonnullas replaced, as the consolidated page's closing note lists
# them; the build checks that note against this list.
AMENDED = ("35", "37", "43", "46,1", "47", "48", "49", "50", "51,2", "55,3", "62", "64",
           "70,2", "75", "87")

# The documents' notes, shown in the overview and the Library, which render plain text:
# each names where the text it mentions is published rather than printing a URL.
CURRENT_NOTE = (
    "The text as amended by Benedict XVI in the motu proprio Normas Nonnullas (22 February "
    "2013), which changed Nos. 35, 37, 43, 46 § 1, 47 to 50, 51 § 2, 55 § 3, 62, 64, 70 § 2, "
    "75 and 87. No. 33's limit of 120 Cardinal electors is unchanged: on 30 April 2025 the "
    "Congregation of Cardinals declared, in a statement published by the Holy See Press "
    "Office, that Pope Francis had dispensed from it by creating more electors.")
NORMAS_NOTE = (
    "It also amends Benedict XVI's motu proprio De aliquibus mutationibus (11 June 2007), "
    "which had replaced No. 75; that act is published in Latin only, on vatican.va.")

# A word the typesetting broke with a hyphen and a space, in both editions
# ("abso- lutely"), or at a 1996 line end, as it reads joined: (pattern, word).
_BROKEN = (
    (re.compile(r"\bmen- ?tioned\b"), "mentioned"),
    (re.compile(r"\bPal- ?aces\b"), "Palaces"),
    (re.compile(r"\bcardinal- ?ate\b"), "cardinalate"),
    (re.compile(r"\babso- ?lutely\b"), "absolutely"),
    (re.compile(r"\bimmedi- ?ately\b"), "immediately"),
    (re.compile(r"\babove- mentioned\b"), "above-mentioned"),
    (re.compile(r"\bnewly- elected\b"), "newly-elected"),
)
# Misprints in the consolidated page, by number: what it prints and the reading of the
# same words in Normas nonnullas, which gives the amended number's text.
CURRENT_FIXES = {62: ("Since Since the forms", "Since the forms")}

_NUMBERED = re.compile(r"^(\d{1,2})\.\s*(.*)$", re.DOTALL)
_PART = re.compile(r"^PART (ONE|TWO)$")
_CHAPTER = re.compile(r"^CHAPTER ([IVX]+)$")
_PROMULGATION = "PROMULGATION"
_PARTS = {"ONE": 1, "TWO": 2}
_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7}
# Normas nonnullas' norms: "No. 46 § 1.", "No. 51 §2."
# The promulgation's dating line and the signature after it.
_CLOSING = re.compile(r"^(?:Given in Rome\b|IOANNES PAULUS PP\. II$)")
_NORM = re.compile(r"^No\. (\d{1,2})(?:\s*§\s*(\d))?\.\s")


@dataclass
class _Block:
    kind: str     # part, part-title, chapter, chapter-title, promulgation, para
    text: str


@dataclass
class _Unit:
    anchor: str
    chapter_key: str
    chapter_label: str
    unit_label: str | None
    reference: str
    paragraphs: list[str]
    held: list[headings.Heading] = field(default_factory=list)


# --------------------------------------------------------------------------- reading

def _clean(text: str) -> str:
    text = strip_note_callers(" ".join(text.split()))
    for pattern, word in _BROKEN:
        text = pattern.sub(word, text)
    return clean_text(text)


def _paragraph_texts(path: str, start: str, stop: str) -> list[str]:
    """The paragraphs of a vatican.va page's `div.documento`, from the first that opens
    with `start` up to the first that opens with `stop`, the "n" amendment marks
    (superscripts) dropped. Each `<p>` opens a paragraph, and text outside any `<p>`
    continues the one before it: Normas nonnullas' markup closes No. 48's oath early, in
    the middle of "(‘latae sententiae’)". Inline tags join without a space
    ("<i>Pastor Bonus</i>,")."""
    with open(path, "rb") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    main = soup.find(class_="documento")
    for tag in main.find_all(["sup", "script", "style"]):
        tag.decompose()
    for br in main.find_all("br"):
        br.replace_with(" ")
    parts: list[list[str]] = []
    for node in main.descendants:
        if isinstance(node, Tag):
            if node.name == "p":
                parts.append([])
        elif isinstance(node, NavigableString) and not isinstance(node, Comment) and parts:
            # Between tags outside a paragraph only words count, not layout whitespace.
            if node.find_parent("p") is not None or node.strip():
                parts[-1].append(str(node))
    texts = [" ".join("".join(p).split()) for p in parts]
    texts = [t for t in texts if t]
    first = next(i for i, t in enumerate(texts) if t.startswith(start))
    last = next(i for i, t in enumerate(texts) if i > first and t.startswith(stop))
    return texts[first:last]


def _classify(texts: list[str]) -> list[_Block]:
    """The constitution's blocks, from its paragraphs in order: a Part's and a Chapter's
    number line and the title after it, the promulgation's heading, and text."""
    out: list[_Block] = []
    for text in texts:
        prev = out[-1].kind if out else None
        if _PART.match(text):
            out.append(_Block("part", text))
        elif _CHAPTER.match(text):
            out.append(_Block("chapter", text))
        elif text == _PROMULGATION:
            out.append(_Block("promulgation", text))
        elif prev in ("part", "chapter"):
            out.append(_Block(f"{prev}-title", text))
        else:
            out.append(_Block("para", text))
    return out


def current_blocks(path: str | None = None) -> list[_Block]:
    """The consolidated text: after the page's "Current Version" lines, up to its note on
    what was amended. The signature, which closes the promulgation, is kept."""
    texts = _paragraph_texts(path or os.path.join(SRC, CURRENT.file),
                             "The Shepherd of the Lord's whole flock", "NOTE:")
    return _classify(texts)


def amendment_note(path: str | None = None) -> list[str]:
    """The numbers the consolidated page's closing note says Normas nonnullas modified."""
    with open(path or os.path.join(SRC, CURRENT.file), "rb") as f:
        text = " ".join(BeautifulSoup(f.read(), "lxml").get_text("").split())
    m = re.search(r"were modified: ([\d,; ]+)\.", text)
    return [n.strip() for n in m[1].split(";")]


# Vertical distance between baselines, in points, that separates paragraphs in the 1996
# PDF: its lines are about 14 points apart, its paragraphs about 28.
_PARAGRAPH_GAP = 21.0
# At a page break a line that ends before this x (points) closed its paragraph.
_RAGGED_SHORT = 420.0
# What a paragraph's last line ends with.
_ENDS = ".:;”\""
# The 1996 PDF's hyphens at a line end that are a compound's own; any other is joined.
_COMPOUNDS = ("pre-scrutiny", "above-mentioned")
_HELD_JOIN = re.compile("(\\w+)­\\s*(\\w+)")


def original_blocks(path: str | None = None) -> list[_Block]:
    """The 1996 original from vatican.va's PDF (`papal_pdf.read_lines`): from the
    preamble's first words to the first of the notes printed after the text. A paragraph
    is told by the gap above it, a page break by the line before it ending short; the
    text is not justified, so line length alone tells nothing."""
    from ingest import papal_pdf

    lines = papal_pdf.read_lines(path or os.path.join(SRC, ORIGINAL.file))
    first = next(i for i, ln in enumerate(lines)
                 if ln.text.strip().startswith("The Shepherd of the Lord's whole flock"))
    texts: list[str] = []
    prev = None
    expected = 1
    heading_next = False
    for ln in lines[first:]:
        text = ln.text.strip()
        if text.startswith("[1] "):
            break
        head = bool(_PART.match(text) or _CHAPTER.match(text) or text == _PROMULGATION)
        title = heading_next and text.isupper()
        m = _NUMBERED.match(text)
        numbered = m is not None and int(m[1]) == expected
        if numbered:
            expected += 1
        if prev is None or head or numbered:
            new = True
        elif title:
            new = not (texts and texts[-1].isupper() and not _is_heading_line(texts[-1]))
        elif ln.page != prev.page:
            new = prev.x1 < _RAGGED_SHORT and _ends_sentence(prev.text)
        else:
            new = heading_next or (prev.baseline - ln.baseline > _PARAGRAPH_GAP
                                   and _ends_sentence(prev.text))
        if new:
            texts.append(text)
        else:
            texts[-1] = _join_line(texts[-1], text)
        heading_next = head or title
        prev = ln
    return _classify([_held_joined(t) for t in texts])


def _ends_sentence(line: str) -> bool:
    """Whether a line ends as a paragraph's last line can, a note caller after it aside."""
    return re.sub(r"\[\d+\]$", "", line.rstrip()).rstrip()[-1:] in _ENDS


def _is_heading_line(text: str) -> bool:
    return bool(_PART.match(text) or _CHAPTER.match(text) or text == _PROMULGATION)


def _join_line(text: str, line: str) -> str:
    if text.endswith("-") and not text.endswith(" -"):
        return text + line           # a compound broken at its own hyphen
    return text + " " + line


def _held_joined(text: str) -> str:
    """A word broken at a line end (the text layer's mark, `papal_pdf`) joined, or
    hyphenated where it is one of `_COMPOUNDS`."""
    def join(m: re.Match) -> str:
        hyphenated = f"{m[1]}-{m[2]}"
        return hyphenated if hyphenated in _COMPOUNDS else m[1] + m[2]
    return _HELD_JOIN.sub(join, text)


def normas_paragraphs(path: str | None = None) -> list[str]:
    """Normas nonnullas' paragraphs: from its first words to its copyright line."""
    return _paragraph_texts(path or os.path.join(SRC, NORMAS.file),
                            "With the Apostolic Letter", "© Copyright")


# --------------------------------------------------------------------------- units

def constitution_units(blocks: list[_Block], edition: Edition) -> list[_Unit]:
    """The constitution's passages-to-be: the preamble's paragraphs, each number with
    the paragraphs after it, and the promulgation's paragraphs, with the dating line and
    the signature joined to the last. Each Part and Chapter heading is held for the unit
    it opens."""
    units: list[_Unit] = []
    held: list[headings.Heading] = []
    part = chapter = 0
    chapter_key, chapter_label = "preamble", "Preamble"
    expected = 1
    for b in blocks:
        if b.kind == "part":
            part, chapter = _PARTS[_PART.match(b.text)[1]], 0
            held.append(headings.Heading(b.text, level=1, pairs_next=True))
        elif b.kind == "part-title":
            held.append(headings.Heading(b.text, level=1))
        elif b.kind == "chapter":
            chapter = _ROMAN[_CHAPTER.match(b.text)[1]]
            held.append(headings.Heading(b.text, level=2, pairs_next=True))
        elif b.kind == "chapter-title":
            chapter_key = make_anchor(f"part-{part}", f"chapter-{chapter}")
            chapter_label = (f"Part {_PART_WORD[part]}, Chapter {_roman(chapter)}: "
                             f"{smart_title_case(b.text)}")
            held.append(headings.Heading(b.text, level=2))
        elif b.kind == "promulgation":
            chapter_key, chapter_label = "promulgation", "Promulgation"
            held.append(headings.Heading(b.text, level=1))
        elif chapter_key == "promulgation" and _CLOSING.match(b.text):
            units[-1].paragraphs.append(b.text)     # the dating line, the signature
        elif chapter_key in ("preamble", "promulgation") and expected in (1, NUMBERS + 1):
            k = sum(1 for u in units if u.chapter_key == chapter_key) + 1
            units.append(_Unit(make_anchor(chapter_key, k), chapter_key, chapter_label,
                               None, f"{edition.cite}, {chapter_label}", [b.text], held))
            held = []
        elif (m := _NUMBERED.match(b.text)) and int(m[1]) == expected:
            n = expected
            expected += 1
            text = m[2]
            if edition is CURRENT and n in CURRENT_FIXES:
                wrong, right = CURRENT_FIXES[n]
                if wrong not in text:
                    raise ValueError(f"No. {n}: the misprint {wrong!r} is not there")
                text = text.replace(wrong, right)
            units.append(_Unit(make_anchor("no", n), chapter_key, chapter_label,
                               f"No. {n}", f"{edition.cite}, No. {n}", [text], held))
            held = []
        else:
            if not units or held:
                raise ValueError(f"{edition.title}: text with no number under a heading: "
                                 f"{b.text[:60]!r}")
            units[-1].paragraphs.append(b.text)     # a paragraph run on after its number
    if expected != NUMBERS + 1:
        raise ValueError(f"{edition.title}: {expected - 1} numbers, expected {NUMBERS}")
    if held:
        raise ValueError(f"{edition.title}: headings with no text after them")
    return _counted(units)


def _counted(units: list[_Unit]) -> list[_Unit]:
    """Units with no number of their own cite their place in their chapter, as the papal
    parser's do: "Universi Dominici Gregis, Preamble (part 3 of 14)"."""
    totals: dict[str, int] = {}
    for u in units:
        if u.unit_label is None:
            totals[u.reference] = totals.get(u.reference, 0) + 1
    seen: dict[str, int] = {}
    for u in units:
        if u.unit_label is None and totals[u.reference] > 1:
            seen[u.reference] = seen.get(u.reference, 0) + 1
            u.reference = f"{u.reference} (part {seen[u.reference]} of {totals[u.reference]})"
    return units


_PART_WORD = {1: "One", 2: "Two"}


def _roman(n: int) -> str:
    return next(r for r, v in _ROMAN.items() if v == n)


def normas_units(texts: list[str]) -> list[_Unit]:
    """Normas nonnullas: its opening paragraphs, one unit per norm it gives with the
    paragraphs that run on, and its closing paragraphs as one unit."""
    units: list[_Unit] = []
    key, label = make_anchor(NORMAS.slug), NORMAS.title
    closing = False
    for k, text in enumerate(texts):
        m = _NORM.match(text)
        if text.startswith("All that I have laid down"):
            closing = True
            units.append(_Unit("closing", key, label, None, f"{NORMAS.cite}, Conclusion",
                               [text]))
        elif closing:
            units[-1].paragraphs.append(text)
        elif m:
            n, section = m[1], m[2]
            anchor = make_anchor("no", f"{n}-{section}" if section else n)
            unit_label = f"No. {n} § {section}" if section else f"No. {n}"
            units.append(_Unit(anchor, key, label, unit_label,
                               f"{NORMAS.cite}, {unit_label}", [text]))
        elif units and units[-1].unit_label is not None:
            units[-1].paragraphs.append(text)        # an oath, a paragraph run on
        else:
            units.append(_Unit(make_anchor("preamble", len(units) + 1), key, label, None,
                               f"{NORMAS.cite}, Preamble", [text]))
    return _counted(units)


# --------------------------------------------------------------------------- documents

def _passages(units: list[_Unit], edition: Edition) -> list[Passage]:
    """Passages in reading order, a unit longer than the cap packed by its paragraphs,
    its headings kept with what follows them."""
    meta = {"url": edition.url, "source_url": edition.url}
    out: list[Passage] = []
    for u in units:
        text = headings.MarkedText()
        for h in u.held:
            text.add(h)
        for p in u.paragraphs:
            text.paragraph(_clean(p))
        content, marks = text.text, text.marks
        packed = pack_units([(None, p) for p in content.split("\n\n")],
                            settings.MAX_PASSAGE_CHARS)
        pieces = headings.hold_headings(content, [p.text for p in packed], marks)
        piece_marks = headings.split_marks(content, pieces, marks)
        starts = [content.find(p) for p in pieces]
        for i, (piece, pm) in enumerate(zip(pieces, piece_marks)):
            first_para = content[:starts[i]].count("\n\n") + 1
            anchor = u.anchor if i == 0 else f"{u.anchor}{PIECE_MARK}p{first_para}"
            reference = u.reference if len(pieces) == 1 else \
                f"{u.reference} (part {i + 1} of {len(pieces)})"
            out.append(Passage(
                content=piece, reference=reference, anchor=anchor,
                chapter_key=u.chapter_key, chapter_label=u.chapter_label,
                position=len(out), unit_label=u.unit_label,
                metadata=headings.with_headings(meta, pm),
                searchable=edition.searchable))
    return out


def _document(edition: Edition, units: list[_Unit], notes: str | None) -> Document:
    source_key = f"{COLLECTION}/{edition.slug}"
    did = resolve_document_id(COLLECTION, source_key, (COLLECTION, edition.slug))
    return Document(
        id=did, collection=COLLECTION, title=edition.title, author=edition.author,
        year=edition.year,
        metadata={"url": edition.url, "source_url": edition.url, "pope": edition.author,
                  "source_key": source_key, "source_file": edition.file,
                  "anchor_scheme": ANCHOR_SCHEME, "genre": edition.genre},
        passages=_passages(units, edition), notes=notes)


def build_documents() -> list[Document]:
    """The current text, then the two history documents."""
    if amendment_note() != list(AMENDED):
        raise ValueError(f"the page's note on what was amended reads {amendment_note()}, "
                         f"not {list(AMENDED)}")
    return [
        _document(CURRENT, constitution_units(current_blocks(), CURRENT), CURRENT_NOTE),
        _document(ORIGINAL, constitution_units(original_blocks(), ORIGINAL), None),
        _document(NORMAS, normas_units(normas_paragraphs()), NORMAS_NOTE),
    ]
