"""John of the Cross in David Lewis's translation, The Complete Works of Saint John of the
Cross, ed. the Oblate Fathers of St. Charles (London: Longman, Green, Longman, Roberts &
Green, 1864), corpus-cleanup 5.6c: one PR per treatise.

Each treatise is read from 1.2f's frozen OCR text, `ocr/texts/<work>.json`, which its
config (`ocr/works/<work>.json`) cleans from the 1864 volume's Internet Archive scan, its
side notes taken out as furniture (`side_notes`). Cardinal Wiseman's preface, the
editors' side notes and the page-foot notes are left out (rule G): the config reads only
the treatise's pages, and the clean-up keeps the notes apart. The note calls the text
keeps (`*`, `†`, `‡`, `§`, and the OCR's readings of them) are taken off here
(`strip_calls`).

A treatise is its Argument and Prologue, then its books' chapters. Each "CHAPTER N." is
followed by Lewis's title for it, one paragraph (the work's fixes set it so); the title
goes into the chapter label, never the text, and the chapters must run 1, 2, 3 within each
book. A passage is a chapter, cut at paragraphs where it runs past `MAX_CHARS`. Every
passage carries the scanned-text label (`ocr.label`).
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from identity import PIECE_MARK, anchor as make_anchor  # noqa: E402
from ingest.common import split_display_passage  # noqa: E402
from ingest.pieces import piece_reference  # noqa: E402
from model import Document, Passage  # noqa: E402
from normalize.text import clean_text  # noqa: E402
from ocr.fixes import read_text  # noqa: E402
from ocr.label import label_passage  # noqa: E402
from registry import ANCHOR_SCHEME, resolve_document_id  # noqa: E402

# The source key 5.6b's and 5.6c's works are registered under until 5.1b.4 renames it;
# `publication` publishes them as `theologians`.
SOURCE = "medieval"
AUTHOR = "John of the Cross"
MAX_CHARS = 3500
GENRE = "treatise"


@dataclass(frozen=True)
class Treatise:
    work: str            # the OCR work (`ocr/works/<work>.json`)
    scan: str            # the Internet Archive item
    slug: str            # the source key's last part and the anchors' first
    title: str
    year: int
    books: int
    chapters: tuple[int, ...]   # chapters in each book, from the volume's contents


TREATISES = (
    Treatise("lewis-ascent-of-mount-carmel", "completeworksofs01johnuoft",
             "ascent-of-mount-carmel", "The Ascent of Mount Carmel", 1585, 3, (15, 32, 44)),
)

_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}


def roman(numeral: str) -> int:
    total = 0
    for k, ch in enumerate(numeral):
        value = _ROMAN[ch]
        total += -value if k + 1 < len(numeral) and _ROMAN[numeral[k + 1]] > value else value
    return total


_CHAPTER = re.compile(r"^CHAPTER ([IVXL]+)\.$")
_BOOK = re.compile(r"^BOOK ([IVX]+)\.$")
_SECTION = re.compile(r"^(ARGUMENT|PROLOGUE)\.$")
# The treatise's own title at its head, the stanzas' heading and numerals, and a stanza's
# heading inside a chapter ("STANZA II."): headings, never text.
_DROPPED = re.compile(r"^(THE|[A-Z ]+ OF [A-Z ]+\.|STANZAS\.?|[IVX]+\.?|STANZA [IVX]+\.)$")
# A book's title in capitals under its heading.
_CAPITALS = re.compile(r"^[^a-z]{12,}$")

# The note calls: the marks themselves (the OCR reads a dagger as "{", "|" or "¢" too), a
# dagger read as a lone "t" or "f" after a sentence's or a quotation's end ("disciple’ f
# of Christ", "fatness.’f"), and a figure read for one ("defiled with it.’1 He").
_CALL_MARKS = re.compile(r"\s?[*†‡§¶‖|{}¢®©+]+")
_READ_CALL = re.compile(r"(?<=[.,;:!?’”'])\s?[tf](?=\s|$)")
_FIGURE_CALL = re.compile(r"(?<=[.,;:!?][’”])\d(?=\s[A-Z])")


def _call_mark(m: re.Match) -> str:
    """A call mark goes; one standing between a space and the next word leaves the space
    ("him.’ ††‘Be not afraid")."""
    after = m.string[m.end():m.end() + 1]
    return " " if m.group()[:1].isspace() and after and not after.isspace() else ""


def strip_calls(text: str) -> str:
    text = _FIGURE_CALL.sub("", _READ_CALL.sub("", _CALL_MARKS.sub(_call_mark, text)))
    # The page's specks the OCR read as "~" or "_" (Lewis prints neither).
    return re.sub(r"[ ]{2,}", " ", re.sub(r"\s*_+\s*", " ", text.replace("~", " "))).strip()


@dataclass
class _Chapter:
    key: str
    label: str
    paragraphs: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)


def chapters(treatise: Treatise, passages: list[dict]) -> list[_Chapter]:
    """The treatise's chapters, in order, read off the frozen passages' paragraphs."""
    out: list[_Chapter] = []
    book = 0
    title_next = False
    for p in passages:
        for k, para in enumerate(q.strip() for q in p["text"].split("\n\n") if q.strip()):
            if k == 0 and p.get("continues"):
                if not out or not out[-1].paragraphs:
                    raise ValueError(f"{treatise.work}: {p['id']} continues no paragraph")
                out[-1].paragraphs[-1] += " " + para
            elif title_next:
                out[-1].label += f". {para.rstrip('.')}"
                title_next = False
            elif m := _SECTION.match(para):
                name = m.group(1).title()
                key = name.lower() if not book else f"book-{book}/{name.lower()}"
                out.append(_Chapter(key, name if not book else f"Book {_numeral(book)}, {name}"))
            elif m := _BOOK.match(para):
                if roman(m.group(1)) != book + 1:
                    raise ValueError(f"{treatise.work}: {para!r} after book {book}")
                book += 1
                out.append(_Chapter("", ""))   # its title, if any, until a chapter opens
            elif m := _CHAPTER.match(para):
                n = roman(m.group(1))
                done = sum(1 for c in out if c.key.startswith(f"book-{book}/chapter-"))
                if not book or n != done + 1:
                    raise ValueError(f"{treatise.work}: {para!r} in book {book} after chapter {done}")
                out.append(_Chapter(f"book-{book}/chapter-{n}",
                                    f"Book {_numeral(book)}, Chapter {_numeral(n)}"))
                title_next = True
            elif _DROPPED.match(para) or (out and not out[-1].key and _CAPITALS.match(para)):
                continue
            else:
                if not out or not out[-1].key:
                    raise ValueError(f"{treatise.work}: text outside a chapter in {p['id']}: {para[:60]!r}")
                out[-1].paragraphs.append(para)
            if out:
                for pg in p["pages"]:
                    if pg and pg not in out[-1].pages:
                        out[-1].pages.append(pg)
    out = [c for c in out if c.key]
    counts = tuple(sum(1 for c in out if c.key.startswith(f"book-{b}/chapter-"))
                   for b in range(1, treatise.books + 1))
    if counts != treatise.chapters:
        raise ValueError(f"{treatise.work}: chapters per book {counts}, the contents print "
                         f"{treatise.chapters}")
    if empty := [c.key for c in out if not c.paragraphs]:
        raise ValueError(f"{treatise.work}: chapters with no text: {empty}")
    return out


def _numeral(n: int) -> str:
    out = ""
    for value, letters in ((40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= value:
            out += letters
            n -= value
    return out


def _pieces(paragraphs: list[str]) -> list[tuple[int, str]]:
    """(first paragraph, text) of each piece: paragraphs packed up to `MAX_CHARS`, and a
    longer paragraph cut on its own."""
    out: list[tuple[int, str]] = []
    current: list[str] = []
    first = 0
    for i, para in enumerate(paragraphs):
        if current and len("\n\n".join(current + [para])) > MAX_CHARS:
            out.append((first, "\n\n".join(current)))
            current = []
        if not current:
            first = i
        current.append(para)
    if current:
        out.append((first, "\n\n".join(current)))
    pieces: list[tuple[int, str]] = []
    for first, text in out:
        pieces += [(first, t) for t in split_display_passage(text, MAX_CHARS)]
    return pieces


def source_key(treatise: Treatise) -> str:
    return f"theologians/{treatise.scan}/{treatise.slug}"


def build_document(treatise: Treatise, text: dict | None = None) -> Document:
    data = text if text is not None else read_text(treatise.work)
    did = resolve_document_id(SOURCE, source_key(treatise), (SOURCE, treatise.slug))
    passages: list[Passage] = []
    for chapter in chapters(treatise, data["passages"]):
        chapter_key = make_anchor(treatise.slug, *chapter.key.split("/"))
        pieces = _pieces([strip_calls(q) for q in chapter.paragraphs])
        seen: dict[int, int] = {}
        for k, (first, body) in enumerate(pieces, 1):
            seen[first] = seen.get(first, 0) + 1
            anchor = chapter_key if k == 1 else (
                f"{chapter_key}{PIECE_MARK}p{first + 1}"
                + (f"-{seen[first]}" if seen[first] > 1 else ""))
            short = chapter.label.split(". ", 1)[0]
            passage = Passage(
                content=clean_text(body),
                reference=piece_reference(f"{treatise.title}, {short}", None, None, k, len(pieces)),
                anchor=anchor, chapter_key=chapter_key, chapter_label=chapter.label,
                position=len(passages), unit_label=None,
                metadata={"pages": chapter.pages})
            passages.append(label_passage(passage, data["metadata"]["scan_id"]))
    return Document(
        id=did, collection=SOURCE, title=treatise.title, author=AUTHOR, year=treatise.year,
        metadata={"source": "David Lewis, The Complete Works of Saint John of the Cross "
                            "(1864), Internet Archive scan, through the OCR tool (1.2f)",
                  "source_key": source_key(treatise),
                  # The scan lies in `sources/theologians/`, beside this source key's folder.
                  "source_file": f"../theologians/{treatise.scan}/",
                  "url": f"https://archive.org/details/{treatise.scan}",
                  "genre": GENRE, "anchor_scheme": ANCHOR_SCHEME},
        passages=passages)


def build_documents() -> list[Document]:
    return [build_document(t) for t in TREATISES]
