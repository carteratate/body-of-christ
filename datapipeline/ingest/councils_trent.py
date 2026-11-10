"""The Council of Trent from Waterworth's translation (1848), as papalencyclicals.net prints
it (1.2b).

The page holds the whole of Waterworth's text in one article element, mostly as bare text
between `<br>`s rather than in paragraphs. Headings are `<center>` lines ("SESSION THE
SIXTH,", "DECREE ON JUSTIFICATION", "CHAPTER VII." over its title); a few are paragraphs
of their own ("DECREE ON REFORMATION", "CHAPTER III." with its title on the next line or
in the next paragraph). The page numbers of the print stand in the text as "[Page N]".

The walk reads the article's descendants in document order: a `<center>` is a heading,
a run of two or more `<br>`s or a paragraph boundary ends a paragraph, and one `<br>`
ends a line. The council's own structure follows: the bull of indiction, then each
session, each holding its documents (decrees, doctrines, canons, decrees on reformation,
indictions, safe-conducts), each document a reader chapter holding its chapters or
canons. The bulls the council printed between its sessions and the bull of confirmation
are under `bulls/`.

Anchors: `council-of-trent/bulls/indiction`, `council-of-trent/session-6/decree-on-justification/chapter-7`,
`council-of-trent/session-6/canons-on-justification/canon-9`,
`council-of-trent/session-4/decree-concerning-the-canonical-scriptures` (a document with
no chapters is one unit), `council-of-trent/confirmation`, `council-of-trent/bulls/confirmation`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from config import settings
from identity import anchor as make_anchor, slugify
from ingest.pieces import Segment, name_pieces, pack_units, piece_reference
from model import Document, Passage
from normalize.caps import smart_title_case
from normalize.text import clean_text
from registry import ANCHOR_SCHEME

log = logging.getLogger(__name__)

COUNCIL = "Council of Trent"
SLUG = slugify(COUNCIL)
TRANSLATION = ("J. Waterworth, The Canons and Decrees of the Sacred and Oecumenical "
               "Council of Trent (1848)")

# The site's own text, which is not Waterworth's. The advert is C-05.
_CHROME = re.compile(
    r"automatically notified|more information about this site|fan of our facebook"
    r"|^search tips$|^sitemap$|return to (?:the )?home|wysiwyg HTML editor", re.IGNORECASE)
# The site editor's note under the title it supplies for session 21's decree.
_SITE_NOTE = re.compile(r"^Note: This title is missing in the Waterworth translation")
_PAGE = re.compile(r"\[Page (\d+)\]")

_ORDINALS = ("FIRST SECOND THIRD FOURTH FIFTH SIXTH SEVENTH EIGHTH NINTH TENTH ELEVENTH "
             "TWELFTH THIRTEENTH FOURTEENTH FIFTEENTH SIXTEENTH SEVENTEENTH EIGHTEENTH "
             "NINETEENTH TWENTIETH TWENTY-FIRST TWENTY-SECOND TWENTY-THIRD TWENTY-FOURTH "
             "TWENTY-FIFTH").split()
_SESSION = re.compile(r"^SESSION THE ([A-Z-]+),?$")
_CHAPTER = re.compile(r"^CHAPTER ([IVXL]+)\b\.?\s*(.*)$", re.DOTALL)
# "CANON IX.-If", "CANON II.–If"; the page reads some numerals' I as l or 1 ("CANON lI.",
# "CANON VlI.", "CANON 11.").
_CANON = re.compile(r"^CANON ([IVXLl1]+)\s*\.?\s*[-–—]\s*(.*)$", re.DOTALL)
_PROEM = re.compile(r"^Proem\.?$")
# A heading set as a paragraph of its own; signatures in capitals end with a stop.
_PARAGRAPH_HEADING = re.compile(r"^(?:DECREE|DOCTRINE|ON)\b[^.]*$")
_BULLS = (("INDICTION", "indiction", "Bull of Indiction"),
          ("TRANFER", "transfer", "Bull with Faculty to Transfer the Council"),
          ("TRANSFER", "transfer", "Bull with Faculty to Transfer the Council"),
          ("RESUMPTION", "resumption", "Bull for the Resumption of the Council"),
          ("CELEBRATION", "celebration", "Bull for the Celebration of the Council"),
          ("CONFIRMATION", "confirmation", "Bull of Confirmation"))
# Headings in mixed case that are headings all the same.
_MIXED_HEADINGS = {"Doctrine on the Sacrament of Penance."}
# Documents whose heading makes a long anchor or a label the title-caser gets wrong:
# (session, heading) → (slug, label).
_DOCUMENTS = {
    (2, "DECREE TOUCHING THE MANNER OF LIVING, AND OTHER MATTERS TO BE OBSERVED, DURING THE "
        "COUNCIL"):
        ("decree-touching-the-manner-of-living",
         "Decree Touching the Manner of Living, and Other Matters to Be Observed, During the Council"),
    (21, "DECREE ON COMMUNION UNDER BOTH SPECIES, AND THE COMMUNION OF INFANTS"):
        ("decree-on-communion-under-both-species",
         "Decree on Communion Under Both Species, and the Communion of Infants"),
    (14, "ON THE SACRAMENT OF EXTREME UNCTION"):
        ("doctrine-on-the-sacrament-of-extreme-unction",
         "Doctrine on the Sacrament of Extreme Unction"),
    (13, "DECREE FOR POSTPONING THE DEFINITION OF FOUR ARTICLES TOUCHING THE SACRAMENT OF "
         "THE EUCHARIST, AND FOR GIVING A SAFE-CONDUCT TO PROTESTANTS"):
        ("decree-postponing-four-articles",
         "Decree for Postponing the Definition of Four Articles Touching the Sacrament of "
         "the Eucharist, and for Giving a Safe-Conduct to Protestants"),
    (18, "DECREE ON THE CHOICE OF BOOKS; AND FOR INVITING ALL MEN ON THE PUBLIC FAITH TO "
         "THE COUNCIL"):
        ("decree-on-the-choice-of-books",
         "Decree on the Choice of Books, and for Inviting All Men on the Public Faith to the Council"),
    (22, "DECREE CONCERNING THE THINGS TO BE OBSERVED, AND TO BE AVOIDED, IN THE CELEBRATION "
         "OF MASS"):
        ("decree-on-the-celebration-of-mass",
         "Decree Concerning the Things to Be Observed, and to Be Avoided, in the Celebration of Mass"),
    (22, "DECREE TOUCHING THE PETITION FOR THE CONCESSION OF THE CHALICE"):
        ("decree-on-the-petition-for-the-chalice",
         "Decree Touching the Petition for the Concession of the Chalice"),
    (23, "THE TRUE AND CATHOLIC DOCTRINE, TOUCHING THE SACRAMENT OF ORDER, DECREED AND "
         "PUBLISHED BY THE HOLY SYNOD OF TRENT, IN THE SEVENTH SESSION, IN CONDEMNATION OF "
         "THE ERRORS OF OUR TIME"):
        ("doctrine-on-the-sacrament-of-order",
         "The True and Catholic Doctrine Touching the Sacrament of Order"),
    (25, "ON THE INVOCATION, VENERATION, AND RELICS, OF SAlNTS, AND ON SACRED IMAGES"):
        ("on-the-invocation-of-saints-and-on-sacred-images",
         "On the Invocation, Veneration, and Relics, of Saints, and on Sacred Images"),
    (25, "ON RECITING, IN SESSION, THE DECREES OF THE COUNCIL UNDER PAUL III. AND JULIUS III"):
        ("on-reciting-the-decrees-under-paul-iii-and-julius-iii",
         "On Reciting, in Session, the Decrees of the Council Under Paul III. and Julius III."),
    (25, "ON THE CLOSE OF THE COUNCIL, AND ON SUING FOR CONFIRMATION FROM OUR MOST HOLY LORD"):
        ("on-the-close-of-the-council",
         "On the Close of the Council, and on Suing for Confirmation from Our Most Holy Lord"),
    (25, "ACCLAMATIONS OF THE FATHERS AT THE CLOSE OF THE COUNCIL"):
        ("acclamations", "Acclamations of the Fathers at the Close of the Council"),
}
# Canons whose heading makes a long anchor: (session, heading) → (slug, label).
_CANONS = {
    (21, "ON COMMUNION UNDER BOTH SPECIES, AND ON THE COMMUNION OF INFANTS"):
        ("canons-on-communion-under-both-species",
         "Canons on Communion Under Both Species, and on the Communion of Infants"),
}
# A heading that dates a second day of a session; its dating line opens the next document.
_CONTINUATION = "CONTINUATION OF THE SESSION"
# The record of the consistory that confirmed the council, before the bull.
_CONFIRMATION = "CONFIRMATION OF THE COUNCIL"


# --------------------------------------------------------------------------- blocks

@dataclass
class Block:
    kind: str                    # "heading" or "text"
    lines: list[str]             # one per `<br>`-separated line, page markers taken out
    pages: list[str]

    @property
    def text(self) -> str:
        return " ".join(self.lines)


def _blocks(article: Tag) -> list[Block]:
    """The article as headings and paragraphs, in reading order."""
    out: list[Block] = []
    lines: list[str] = [""]
    pages: list[str] = []
    page = "1"
    brs = 0

    def flush(kind: str = "text") -> None:
        nonlocal lines, pages
        kept = [re.sub(r"\s+", " ", ln).strip() for ln in lines]
        kept = [ln for ln in kept if ln and not _SITE_NOTE.match(ln)]
        if kept:
            out.append(Block(kind, kept, pages or [page]))
        lines, pages = [""], []

    def add(text: str) -> None:
        if not pages:
            pages.append(page)
        lines[-1] += text

    def walk(node: Tag) -> None:
        nonlocal brs, page
        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                if child.strip():
                    if brs >= 2:
                        flush()
                    elif brs == 1:
                        lines.append("")
                    brs = 0
                add(str(child))
                continue
            if child.name in ("script", "style", "noscript", "img"):
                continue
            if child.name == "br":
                brs += 1
                continue
            marker = _PAGE.fullmatch(child.get_text().strip())
            if child.name == "strong" and marker:
                page = marker.group(1)
                if pages and page not in pages:
                    pages.append(page)
                add(" ")
                continue
            if child.name == "center":
                flush()
                brs = 0
                walk(child)
                flush("heading")
                continue
            if child.name in ("p", "div", "hr"):
                flush()
                brs = 0
                walk(child)
                flush()
                brs = 0
                continue
            walk(child)

    walk(article)
    flush()
    return out


# --------------------------------------------------------------------------- structure

@dataclass
class _Unit:
    tail: str                    # anchor under the council
    chapter: str                 # reader chapter under the council
    chapter_label: str
    unit_label: str
    reference: str
    paragraphs: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)

    def add(self, text: str, pages: list[str]) -> None:
        self.paragraphs.append(text)
        self.pages += [p for p in pages if p not in self.pages]


def _roman(token: str) -> str:
    return token.replace("l", "I").replace("1", "I")


_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50}


def _value(roman: str) -> int:
    total = 0
    for k, ch in enumerate(roman):
        v = _ROMAN_VALUES[ch]
        total += -v if k + 1 < len(roman) and _ROMAN_VALUES[roman[k + 1]] > v else v
    return total


def _heading_key(text: str) -> str:
    return text.strip().strip("[]").rstrip(".").strip()


def _is_heading(block: Block) -> bool:
    text = block.text
    if block.kind == "heading":
        if _PROEM.match(text) or text in _MIXED_HEADINGS or _CHAPTER.match(text):
            return True
        letters = [c for c in text if c.isalpha()]
        return sum(c.isupper() for c in letters) > 0.8 * len(letters)
    if _PROEM.match(text) or re.fullmatch(r"CHAPTER [IVXL]+\.?", block.lines[0]):
        return True
    return bool(_PARAGRAPH_HEADING.match(text)) and text.upper() == text


def _units(blocks: list[Block]) -> list[_Unit]:
    units: list[_Unit] = []
    session: int | None = None
    document: tuple[str, str] | None = None     # (chapter tail, label) of the open document
    loose: _Unit | None = None                   # an open bull or the confirmation record
    canons = False
    expected = 0                                 # the next chapter or canon number
    pending: list[tuple[str, list[str]]] = []    # dating lines for the next unit
    seen: set[str] = set()

    def open_unit(tail: str, chapter: str, chapter_label: str, unit_label: str,
                  reference: str) -> _Unit:
        if tail in seen:
            raise ValueError(f"Trent: two units at {tail}")
        seen.add(tail)
        unit = _Unit(tail, chapter, chapter_label, unit_label, reference)
        for text, pages in pending:
            unit.add(text, pages)
        pending.clear()
        units.append(unit)
        return unit

    def in_document(suffix: str, unit_label: str) -> _Unit:
        tail, label = document
        name = f"{tail}/{suffix}" if suffix else tail
        ref = f"{COUNCIL}, Session {session}, {label}"
        return open_unit(name, tail, f"Session {session}: {label}", unit_label,
                         f"{ref}, {unit_label}" if suffix else ref)

    k = 0
    while k < len(blocks):
        block = blocks[k]
        text = block.text
        k += 1
        if _CHROME.search(text):
            log.info("Trent: dropped the site's text %r", text[:60])
            continue
        if not _is_heading(block):
            if loose is not None:
                loose.add(text, block.pages)
                continue
            if session is None:
                raise ValueError(f"Trent: text outside any session or bull: {text[:60]!r}")
            if document is None:
                if _dating(text):
                    pending.append((text, block.pages))
                    continue
                # Session 12 prints its decree under no heading.
                document, canons, expected = (f"session-{session}/decree", "Decree"), False, 1
            if canons:
                m = _CANON.match(text)
                if m is None and expected == 1:
                    raise ValueError(f"Trent: {document[0]}: text before canon 1: {text[:60]!r}")
                if m is not None:
                    number = _roman(m.group(1))
                    if _value(number) != expected:
                        raise ValueError(f"Trent: {document[0]} canon {number}, expected {expected}")
                    body = m.group(2)
                    if body.startswith(("lf ", "if ")):
                        body = "If " + body[3:]          # the page's "lf", "if" for "If"
                    in_document(f"canon-{expected}", f"Canon {number}").add(body, block.pages)
                    expected += 1
                    continue
                if not units[-1].tail.endswith("/conclusion"):
                    # Text after the last canon closes the document (session 21's two
                    # reserved articles), as Dei Filius's conclusion does (1.2d).
                    in_document("conclusion", "Conclusion")
            unit = units[-1] if units else None
            if unit is None or unit.chapter != document[0]:
                # Text before a document's first chapter is its preamble; a document with no
                # chapters is one unit.
                unit = (in_document("preamble", "Preamble") if _chapters_follow(blocks, k)
                        else in_document("", document[1]))
            unit.add(text, block.pages)
            continue

        key = _heading_key(text)
        if (m := _SESSION.match(block.lines[0])):
            if pending:
                raise ValueError(f"Trent: dating lines left before session {m.group(1)}")
            session = _ORDINALS.index(m.group(1)) + 1
            document, loose, canons = None, None, False
            continue
        if key.startswith(("THE BULL", "BULL")):
            slug, label = next((s, lbl) for word, s, lbl in _BULLS if word in key)
            document, canons = None, False
            loose = open_unit(f"bulls/{slug}", f"bulls/{slug}", label, label, f"{COUNCIL}, {label}")
            continue
        if key == _CONFIRMATION:
            document, canons = None, False
            label = "Confirmation of the Council"
            loose = open_unit("confirmation", "confirmation", label, label, f"{COUNCIL}, {label}")
            continue
        if session is None:
            raise ValueError(f"Trent: a heading outside any session: {text[:60]!r}")
        loose = None
        if key == _CONTINUATION:
            document, canons = None, False          # its dating line opens the next document
            continue
        if _PROEM.match(key + "."):
            in_document("proem", "Proem")
            continue
        if (m := _CHAPTER.match(block.text if block.kind == "heading" else block.lines[0])):
            if document is None or canons:
                raise ValueError(f"Trent: a chapter outside a decree: {text[:60]!r}")
            number = m.group(1)
            if _value(number) != expected:
                raise ValueError(f"Trent: {document[0]} chapter {number}, expected {expected}")
            title_lines = block.lines[1:]
            if not title_lines:
                # The title is the next paragraph ("CHAPTER III." / "Benefices shall be …").
                title_lines = blocks[k].lines
                k += 1
            in_document(f"chapter-{expected}", f"Chapter {number}").add(
                " ".join(title_lines), block.pages)
            expected += 1
            continue
        # A document's heading.
        nxt = blocks[k] if k < len(blocks) else None
        if nxt is not None and _is_heading(nxt) and not _PROEM.match(nxt.text) \
                and not _CHAPTER.match(nxt.lines[0]):
            # A title over the document that follows (session 14's "ON THE MOST HOLY
            # SACRAMENTS OF PENANCE AND EXTREME UNCTION").
            log.info("Trent: session %s: title %r", session, key)
            continue
        if key in {_heading_key(x) for x in _MIXED_HEADINGS}:
            key = key.upper()
        is_canons = nxt is not None and _CANON.match(nxt.text) is not None
        slug, label = (None, None) if is_canons else _DOCUMENTS.get((session, key), (None, None))
        if is_canons:
            slug, label = _CANONS.get((session, key), (None, None))
        if slug is None:
            slug, label = slugify(key), smart_title_case(key)    # "Decree on Justification"
            if is_canons:
                slug, label = f"canons-{slug}", f"Canons {label[0].lower()}{label[1:]}"
        document, canons, expected = (f"session-{session}/{slug}", label), is_canons, 1
    if pending:
        raise ValueError("Trent: dating lines left at the end")
    return units


def _dating(text: str) -> bool:
    return bool(re.match(r"^(?:Celebrated|Being the|Begun on|Of the (?:sacred and )?holy|On the "
                         r"fourth day of December)", text, re.IGNORECASE))


def _chapters_follow(blocks: list[Block], k: int) -> bool:
    """Whether a chapter heading comes before the next document or session heading."""
    for block in blocks[k:]:
        if not _is_heading(block):
            continue
        if _CHAPTER.match(block.text if block.kind == "heading" else block.lines[0]):
            return True
        if not _PROEM.match(block.text):
            return False
    return False


# --------------------------------------------------------------------------- passages

def _passages(units: list[_Unit], entry: dict) -> list[Passage]:
    out: list[Passage] = []
    for unit in units:
        if not unit.paragraphs:
            raise ValueError(f"Trent: {unit.tail}: no text")
        paragraphs = [clean_text(p) for p in unit.paragraphs]
        raw = "\n\n".join(paragraphs)
        segments = [Segment(f"p{k}", p) for k, p in enumerate(paragraphs, 1)]
        parts = [p.text for p in pack_units([(None, p) for p in paragraphs],
                                            settings.MAX_PASSAGE_CHARS)]
        anchor = make_anchor(SLUG, *unit.tail.split("/"))
        meta = {"council": COUNCIL, "year": entry["year"], "url": entry["url"],
                "pages": unit.pages}
        for k, (part, (piece_anchor, held)) in enumerate(
                zip(parts, name_pieces(anchor, raw, parts, segments)), 1):
            out.append(Passage(content=part,
                               reference=piece_reference(unit.reference, None, None, k, len(parts)),
                               anchor=piece_anchor,
                               chapter_key=make_anchor(SLUG, *unit.chapter.split("/")),
                               chapter_label=unit.chapter_label, position=len(out),
                               unit_label=unit.unit_label, metadata=meta, source_units=held))
    return out


def read_units(soup: BeautifulSoup) -> list[_Unit]:
    article = soup.find("div", class_="entry-content")
    if article is None:
        raise ValueError("Trent: no article element")
    return _units(_blocks(article))


def build_trent(entry: dict, soup: BeautifulSoup, document_id: str, source_key: str) -> Document:
    return Document(id=document_id, collection="councils", title=entry["council"],
                    author=COUNCIL, year=entry["year"], translation=TRANSLATION,
                    metadata={"url": entry["url"], "council_number": entry.get("council_number"),
                              "source_key": source_key, "anchor_scheme": ANCHOR_SCHEME},
                    passages=_passages(read_units(soup), entry))
