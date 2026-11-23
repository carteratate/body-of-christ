"""Headings inside passages: `metadata.headings`, the helper adapters mark them with, and
the cut that carries them into split pieces (issue #445).

Adapters keep a heading in the text of the passage it introduces (1.1, 1.2e, 1.3a, #279).
The build marks it as character offsets into `content`, in the pattern of
`metadata.footnotes`, so the web can set it as a heading while `content`, the embeddings
and the keyword index stay as they are:

    [{"at": 0, "end": 30, "level": 2, "role": "heading"}, ...]

- `role` is "heading" or "epigraph" (a scripture line set under a heading).
- `level`, on a heading only: 1 is a division the reader's chapter label names, 2 is one
  tier below it, 3 is anything deeper.
- `pairs_next: true` marks a level label printed on its own line before its title (the
  Catechism's `Article 1` / `THE REVELATION OF GOD`); the next mark is its title, at the
  same level, and the two show as one heading.
- `chapter_title: true` marks a level-1 heading that repeats its chapter label, which the
  reader hides where the passage opens its chapter.

Every mark covers one whole paragraph (`\\n\\n`-separated block). Adapters never write
offsets by hand: they build a passage's text with `MarkedText` or `prepend`, cut it with
`hold_headings` and `split_marks`, and store the marks with `with_headings`.
`problems` is the contract; health.py's block rules apply it to the build, and
`looks_like_heading` is the classifier that trips the rule for unmarked headings in the
collections that opt in. Nothing here reads `ingest/`.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

HEADING = "heading"
EPIGRAPH = "epigraph"
ROLES = (HEADING, EPIGRAPH)
LEVELS = (1, 2, 3)
PARAGRAPH = "\n\n"
KEY = "headings"


class HeadingError(ValueError):
    """A heading mark breaks the contract; the build must not publish it."""


@dataclass(frozen=True)
class Heading:
    """A heading or epigraph an adapter holds until it joins the passage it introduces
    (a `pending` list): its printed text and how to mark it."""
    text: str
    level: int | None = None
    role: str = HEADING
    pairs_next: bool = False
    chapter_title: bool = False


def mark(at: int, end: int, *, level: int | None = None, role: str = HEADING,
         pairs_next: bool = False, chapter_title: bool = False) -> dict:
    """One `metadata.headings` entry. A heading takes a level, an epigraph none; the
    flags are written only when set."""
    if role not in ROLES:
        raise HeadingError(f"unknown heading role {role!r}")
    if not (isinstance(pairs_next, bool) and isinstance(chapter_title, bool)):
        raise HeadingError("pairs_next and chapter_title are booleans")
    if role == HEADING and (type(level) is not int or level not in LEVELS):
        raise HeadingError(f"a heading's level is one of {LEVELS}, not {level!r}")
    if role == EPIGRAPH and (level is not None or pairs_next or chapter_title):
        raise HeadingError("an epigraph takes no level, pairs_next or chapter_title")
    if chapter_title and level != 1:
        raise HeadingError("only a level-1 heading repeats its chapter label")
    out: dict = {"at": at, "end": end}
    if level is not None:
        out["level"] = level
    out["role"] = role
    if pairs_next:
        out["pairs_next"] = True
    if chapter_title:
        out["chapter_title"] = True
    return out


def _paragraph_text(text: str) -> str:
    body = text.strip()
    if not body:
        raise HeadingError("a heading or paragraph is empty")
    if PARAGRAPH in body:
        raise HeadingError(f"a heading is more than one paragraph: {body[:60]!r}")
    return body


class MarkedText:
    """A passage's text built paragraph by paragraph, with its headings marked.

        text = MarkedText()
        text.heading("SECTION 1 The Avoidance of War", level=2)
        text.paragraph("Even though recent wars ...")
        passage_meta = with_headings(meta, text.marks)
        content = text.text
    """

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._length = 0
        self.marks: list[dict] = []

    @property
    def text(self) -> str:
        return PARAGRAPH.join(self._parts)

    def _append(self, body: str) -> int:
        """Add one block of text; return its offset."""
        at = self._length + (len(PARAGRAPH) if self._parts else 0)
        self._parts.append(body)
        self._length = at + len(body)
        return at

    def heading(self, text: str, level: int, *, pairs_next: bool = False,
                chapter_title: bool = False) -> MarkedText:
        body = _paragraph_text(text)
        entry = mark(0, 0, level=level, pairs_next=pairs_next, chapter_title=chapter_title)
        at = self._append(body)
        self.marks.append({**entry, "at": at, "end": at + len(body)})
        return self

    def epigraph(self, text: str) -> MarkedText:
        body = _paragraph_text(text)
        at = self._append(body)
        self.marks.append(mark(at, at + len(body), role=EPIGRAPH))
        return self

    def add(self, held: Heading) -> MarkedText:
        if held.role == EPIGRAPH:
            return self.epigraph(held.text)
        return self.heading(held.text, held.level, pairs_next=held.pairs_next,
                            chapter_title=held.chapter_title)

    def paragraph(self, text: str) -> MarkedText:
        """Body text: one or more paragraphs, kept as given apart from the whitespace
        around it."""
        body = text.strip()
        if body:
            self._append(body)
        return self

    def extend(self, text: str, marks: Iterable[dict] = ()) -> MarkedText:
        """Text that already carries marks (a passage being joined onto), shifted."""
        body = text.strip()
        if not body:
            return self
        lead = len(text) - len(text.lstrip())
        at = self._append(body)
        self.marks.extend(shift(marks, at - lead))
        return self


def prepend(held: Sequence[Heading], text: str, marks: Iterable[dict] = ()
            ) -> tuple[str, list[dict]]:
    """`text` with the headings an adapter held for it joined on before it, each its own
    paragraph, and its marks shifted to match: what 1.1, 1.3a and Trent do when a heading
    moves onto the passage it introduces."""
    out = MarkedText()
    for h in held:
        out.add(h)
    out.extend(text, marks)
    return out.text, out.marks


def shift(marks: Iterable[dict], by: int) -> list[dict]:
    return [{**m, "at": m["at"] + by, "end": m["end"] + by} for m in marks]


def with_headings(metadata: dict | None, marks: Sequence[dict]) -> dict | None:
    """`metadata` with `headings` set to `marks`, or without the key when there are
    none, so an unmarked passage's metadata is what it was before #445."""
    out = dict(metadata or {})
    if marks:
        out[KEY] = sorted((dict(m) for m in marks), key=lambda m: m["at"])
    else:
        out.pop(KEY, None)
    return out or (None if metadata is None else {})


# --------------------------------------------------------------------------- splitting

def _piece_starts(text: str, pieces: Sequence[str]) -> list[int]:
    """Each piece's start in `text`, found moving forward: the splitters keep every
    word once, in order (`ingest.pieces.piece_spans`)."""
    starts, cursor = [], 0
    for piece in pieces:
        start = text.find(piece, cursor)
        if start < 0:
            raise HeadingError("a piece is not in its unit's text")
        starts.append(start)
        cursor = start + len(piece)
    return starts


def hold_headings(text: str, pieces: Sequence[str], marks: Sequence[dict]) -> list[str]:
    """`pieces`, cut from `text` by any splitter, with no cut left inside or after a
    heading: a piece that ends on marked headings, or inside one, gives them to the next
    piece, and a piece that held only headings joins it. Packing keeps a title with its first paragraph, as 1.3a
    does for papal headings (the City of God pieces that held only their capitulum).
    The last piece keeps what it ends with: a unit that ends on a heading is the
    adapter's to fix, and the health check blocks it."""
    if len(pieces) < 2 or not marks:
        return list(pieces)
    starts = _piece_starts(text, pieces)
    spans = [(s, s + len(p)) for s, p in zip(starts, pieces)]
    ordered = sorted(marks, key=lambda m: m["at"], reverse=True)
    out: list[tuple[int, int]] = []
    carried: int | None = None            # where the next piece now starts
    for k, (start, end) in enumerate(spans):
        if carried is not None:
            start, carried = carried, None
        cut = end
        if k + 1 < len(spans):
            # Walk back over the heading the cut falls in and those the piece then
            # ends with, last first.
            for m in ordered:
                if m["at"] >= start and (m["end"] == cut or m["at"] < cut < m["end"]):
                    cut = carried = m["at"]
                    while cut > start and text[cut - 1].isspace():
                        cut -= 1
        if cut > start:                   # a piece of only headings joins the next
            out.append((start, cut))
    return [text[a:b] for a, b in out]


def split_marks(text: str, pieces: Sequence[str], marks: Sequence[dict]
                ) -> list[list[dict]]:
    """The marks of each piece cut from `text`, with offsets into the piece. A cut
    inside a marked span is refused: headings are whole paragraphs, and the splitters
    prefer paragraph breaks, so one there means the unit's text and its marks disagree."""
    starts = _piece_starts(text, pieces)
    out: list[list[dict]] = [[] for _ in pieces]
    for m in sorted(marks, key=lambda m: m["at"]):
        for k, (start, piece) in enumerate(zip(starts, pieces)):
            if start <= m["at"] and m["end"] <= start + len(piece):
                out[k].append({**m, "at": m["at"] - start, "end": m["end"] - start})
                break
        else:
            raise HeadingError(f"a cut falls inside the heading at {m['at']}..{m['end']}: "
                               f"{text[m['at']:m['end']][:60]!r}")
    return out


# --------------------------------------------------------------------------- the contract

def paragraphs(content: str) -> list[tuple[int, int]]:
    """(start, end) of each non-blank paragraph of `content`, without its surrounding
    whitespace."""
    out, at = [], 0
    for block in content.split(PARAGRAPH):
        body = block.strip()
        if body:
            lead = len(block) - len(block.lstrip())
            out.append((at + lead, at + lead + len(body)))
        at += len(block) + len(PARAGRAPH)
    return out


def problems(content: str, marks) -> list[str]:
    """What is wrong with a passage's `metadata.headings`, [] when nothing is: each mark
    is well formed and covers one whole paragraph, marks do not overlap, the passage
    neither ends on a heading nor holds only headings, a `pairs_next` label is followed
    by its title at the same level, and levels never skip downwards within a stack of
    consecutive headings (1 then 3)."""
    if marks is None:
        return []
    if not isinstance(marks, list):
        return ["headings is not a list"]
    found: list[str] = []
    paras = paragraphs(content)
    para_index = {span: i for i, span in enumerate(paras)}
    placed: list[tuple[int, dict]] = []          # (paragraph index, mark)
    for m in marks:
        if not isinstance(m, dict):
            found.append("a mark is not an object")
            continue
        at, end = m.get("at"), m.get("end")
        if not (isinstance(at, int) and isinstance(end, int)) \
                or isinstance(at, bool) or isinstance(end, bool):
            found.append(f"mark {m!r}: at and end are not integers")
            continue
        try:
            mark(at, end, level=m.get("level"), role=m.get("role"),
                 pairs_next=m.get("pairs_next", False),
                 chapter_title=m.get("chapter_title", False))
        except HeadingError as exc:
            found.append(f"mark at {at}: {exc}")
            continue
        unknown = set(m) - {"at", "end", "level", "role", "pairs_next", "chapter_title"}
        if unknown:
            found.append(f"mark at {at}: unknown keys {sorted(unknown)}")
        if (at, end) not in para_index:
            found.append(f"mark at {at}..{end} is not one whole paragraph")
            continue
        placed.append((para_index[(at, end)], m))
    placed.sort(key=lambda pm: pm[0])
    indices = [i for i, _ in placed]
    if len(set(indices)) != len(indices):
        found.append("two marks cover one paragraph")
    if found:
        return found
    marked = {i: m for i, m in placed}
    if paras and len(marked) == len(paras):
        found.append("the passage holds only headings")
    elif paras and len(paras) - 1 in marked:
        found.append("the passage ends on a heading")
    for i, m in placed:
        if m.get("pairs_next"):
            title = marked.get(i + 1)
            if title is None or title.get("role") != HEADING \
                    or title.get("level") != m.get("level"):
                found.append(f"mark at {m['at']}: pairs_next is not followed by a "
                             "heading at its level")
        prev = marked.get(i - 1)
        if (prev is not None and m.get("role") == HEADING and prev.get("role") == HEADING
                and m["level"] > prev["level"] + 1):
            found.append(f"mark at {m['at']}: level {m['level']} under level "
                         f"{prev['level']} skips a level")
    return found


# --------------------------------------------------------------------------- the classifier

# The passage-headings survey's rule (docs/corpus-cleanup/passage-headings-survey.md):
# a paragraph of one line, at most about 110 characters, that opens with no `§`, verse
# marker, list mark or quotation mark and ends without sentence punctuation, or that
# names a division with its number. It only trips the check for unmarked headings; it
# never draws one.
MAX_HEADING_CHARS = 110
_OPENS_AS_TEXT = re.compile(r"""^(?:§|\{\{v:|["“”‘’'«(\[]|[-–—•*]\s|\d+[.)]\s)""")
_ENDS_AS_SENTENCE = re.compile(r"""[.!?:;,]["”’'»)\]]*$|:—$""")
_LETTER = re.compile(r"[^\W\d_]")
_DIVISION = re.compile(
    r"""^(?:PART|SECTION|CHAPTER|ARTICLE|BOOK|QUESTION|TITLE|PARAGRAPH)\s+
        (?:[0-9]+|[IVXLC]+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)\b
      | ^Chapter\s+[0-9IVXLC]+\.\s*[—–-]""",
    re.IGNORECASE | re.VERBOSE)


def looks_like_division(paragraph: str) -> bool:
    """A paragraph that names a division with its number ("CHAPTER ONE: ...",
    "Chapter 2.—On Twins."): a heading even where it stands alone in a passage."""
    text = paragraph.strip()
    return "\n" not in text and bool(_DIVISION.match(text))


def looks_like_heading(paragraph: str) -> bool:
    text = paragraph.strip()
    if not text or "\n" in text or not _LETTER.search(text):
        return False
    if _DIVISION.match(text):
        return True
    return (len(text) <= MAX_HEADING_CHARS and not _OPENS_AS_TEXT.match(text)
            and not _ENDS_AS_SENTENCE.search(text))


def normalized(text: str) -> str:
    """Text compared without case, punctuation or spacing: a chapter label against the
    heading that repeats it."""
    return " ".join(re.findall(r"[^\W_]+", text.casefold()))


_DIVISION_PREFIX = re.compile(
    r"^(?:part|section|chapter|article|book|question|title|paragraph)\s+"
    r"(?:[0-9]+|[ivxlc]+|one|two|three|four|five|six|seven|eight|nine|ten)\b\s*")


def repeats_label(heading: str, label: str) -> bool:
    """Whether a heading says what its chapter label says, either allowed to drop a
    leading division and number the other prints ("Chapter One What is ..." and "What
    is ...", "Article 1 The Revelation of God" and "The Revelation of God")."""
    heading, label = normalized(heading), normalized(label)
    if not heading or not label:
        return False
    forms = {heading, _DIVISION_PREFIX.sub("", heading)}
    return bool(forms & {label, _DIVISION_PREFIX.sub("", label)})
