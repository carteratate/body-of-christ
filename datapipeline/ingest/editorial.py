"""Editors' words out of the Fathers' text under rule G (corpus-cleanup 1.8a).

The ANF volumes print a later editor's or translator's matter beside the Fathers' own
text: Elucidations and editor's notes as whole divs, title, number and rule lines and
translator credits at the top of a chapter, "Argument" summaries, the editor's title
line of each letter, edition source lines, and bracketed comments inside sentences.
Class names can't tell them apart (ANF01 to 06 use generated classes), so this module
keys on div titles, div ids and text patterns.

- `EDITORIAL_DIV_TITLE` / `editorial_div`: a div that is an editor's, skipped whole at
  any depth (R4's seven authorial "Contents." divs of the Refutation excepted).
- `ChapterEdit`: what one chapter div loses: whole paragraphs (`strip_editorial_lines`
  is the same rules over bare strings) and bracketed spans (`strip_editor_brackets`).
  The three ANF works whose chapter titles are a later editor's (Decision log "Editors'
  chapter titles in passage text") move that line into the chapter label instead.
- `recording()`: collects what each chapter lost, so the removal registry entries can be
  generated from a build (scripts/editorial_removals.py). Builds outside it record
  nothing.

Rule G also says to keep the editors' authenticity judgments: `judgment()` finds them in
the removed text, and the registry carries them into the work's attribution.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass, field

from ingest.common import _block_text, direct_blocks

_DIR = os.path.dirname(os.path.abspath(__file__))
BRACKETS_PATH = os.path.join(_DIR, "editorial_brackets.json")

EDITORIAL_DIV_TITLE = re.compile(
    r"elucidations?|general notes?|(?:two )?notes? by the (?:american editor|edinburgh "
    r"translator)|general notes? by the american editor|translator'?s (?:biographical "
    r"notice|introduction|preface)|introductory (?:note|notice).*|prefatory notice.*"
    r"|title pages?|contents|note"
    # The NPNF Augustine volumes (1.8b): Shedd's essay, the Enchiridion's "Argument", the
    # editor's digest of On Christian Doctrine.
    r"|introductory essay|argument|contents of christian doctrine")

# A heading inside an author's chapter that opens an editor's section running to the
# next heading or the chapter's end ("General Notes by the American Editor." after
# Lactantius, Institutes IV.30; "General notice" after Apostolic Constitutions VII).
EDITORIAL_HEADING = re.compile(
    r"elucidations?|general (?:notes?|notices?)(?: by the american editor)?|(?:two )?notes? "
    r"by the (?:american editor|edinburgh translator)|introductory (?:note|notice).*")
_HEADINGS = frozenset(f"h{n}" for n in range(1, 7))

# R4 (docs/research/R4-refutation-contents.md, section 4): the Refutation's book tables
# of contents are Hippolytus's own, so these "Contents." divs stay passages.
AUTHORIAL_CONTENTS = frozenset({
    ("third-century-2.xml", div) for div in (
        "iii.iii.i.i", "iii.iii.iii.i", "iii.iii.iv.i", "iii.iii.v.i", "iii.iii.vi.i",
        "iii.iii.vii.i", "iii.iii.viii.i")})
# The same research: the Refutation's book summaries are the author's, not "Argument"s.
AUTHORIAL_ARGUMENTS = frozenset({"church-fathers/third-century-2.xml#iii.iii"})

# The works whose chapter titles are a later editor's, by source key: the Banquet, On the
# Apparel of Women and To His Wife (1.8a); On the Trinity, the Enchiridion, On the
# Catechising of the Uninstructed, Faith and the Creed and On Christian Doctrine, whose
# chapter titles are the Benedictine editors' (1.8b). The title line moves into the
# chapter label. City of God's titles are the ancient capitula and stay.
CHAPTER_TITLE_WORKS = frozenset({
    "church-fathers/third-century-3.xml#xi.iii",
    "church-fathers/third-century.xml#iii.iii",
    "church-fathers/third-century.xml#iii.v",
    "church-fathers/on-the-holy-trinity.xml#iv.i",
    "church-fathers/on-the-holy-trinity.xml#iv.ii",
    "church-fathers/on-the-holy-trinity.xml#iv.iii",
    "church-fathers/on-the-holy-trinity.xml#iv.iv",
    "church-fathers/city-of-god.xml#v",
})

RULE_LINE = re.compile(r"^[—–‒―\-_\s]{3,}$")
CREDIT_LINE = re.compile(r"^\[(?:Translated by .*|(?:Circa|Oxford number|a\.\s?d\.).*)\]$",
                         re.IGNORECASE)
NUMBER_LINE = re.compile(
    r"^(?:(?:Chapter|Chap|Book|Epistle|Letter|Treatise|Canon|Topic|Fragment|Section|Part"
    r"|Discourse|Homily|Oration)\.?\s+)?(?:[IVXLCDM]+|\d+)\.?$", re.IGNORECASE)
ARGUMENT_LINE = re.compile(r"^(?:Chapter [IVXLC]+\.?\s*[—-]*\s*)?Argument\s*[.:—]")
CHAPTER_TITLE_LINE = re.compile(r"^(?:Chapter|Chap\.) (?P<n>[IVXLC\d]+)\s*\.?\s*[—–-]+\s*(?P<t>\S.*)$")
# A preface's title in the same works: "Preface.—Why Augustin Writes of the Trinity." on
# one line, or "Preface." over a line of its own (On Christian Doctrine).
PREFACE_TITLE_LINE = re.compile(r"^Preface\.?\s*[—–-]+\s*(?P<t>\S.*)$")
PREFACE_LINE = re.compile(r"^Preface\.?$")
LETTER_NUMBER_LINE = re.compile(r"^(?:Epistle|Letter) [IVXLC]+\.")
# An edition's source line on a paragraph of its own (C-22): an edition abbreviation
# with a volume or page number. The same pattern as 0.1d's `editorial.provenance_lines`.
PROVENANCE_LINE = re.compile(
    r"(?<![\w\[])(?:Mai|Script\.\s?[Vv]et\.|Gallandi|Galland|Apud|Fabricius|Combefis|Pitra|"
    r"Bandini|Routh|Lambecius|Ex Leontio|Ex Leontii|Spicil\.)(?=\W).*?"
    r"\b(?:vol|tom|p|pp|lib|col|cap|t)\.\s*[\divxlc]+")
PROVENANCE_MAX_CHARS = 200
_PROVENANCE_PROSE = re.compile(r"\brefers?\b")

# Footnote callers a source prints as plain digits glued after the sentence, with no
# <note> for 1.10b's strip to take, by (file, paragraph id): (as printed, without it). The
# Confessions' four in Book VII, chapter XI (C-17; Carter, 1 Nov 2026, NEEDS-CARTER 1.8b).
PLAIN_CALLERS = {
    ("confessions.xml", "viii.xi-p1"): (("immutably.2 ", "immutably. "), ("God,3 ", "God, "),
                                        ("things.4 ", "things. "),
                                        ("gooodness.5", "gooodness.")),
}

BRACKET = re.compile(r"\[[^\[\]]*\]")
EDITOR_BRACKET = re.compile(
    r"See (?:vol|Elucidation|note)|Translated by|Circa|a\.\s?d\.|Oxford|American editor"
    r"|Comp\.|vol\. [ivx]+|p\. \d+|Gallandi", re.IGNORECASE)

# The spec's words, plus "ascrib" ("Wrongly ascribed to Hippolytus." heads a piece of the
# Hippolytus appendix).
JUDGMENT = re.compile(r"genuine|spurious|dubious|doubtful|interpolat|forg|authentic|attributed"
                      r"|ascrib", re.IGNORECASE)

# A chapter's heading lines sit above its first paragraph of real length.
_LEAD_MAX_CHARS = 200
_LEAD_MAX_BLOCKS = 8


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").casefold()
    text = text.replace("æ", "ae").replace("œ", "oe")
    return " ".join(re.findall(r"[^\W_]+", text))


def editorial_div(title: str, div_id: str | None = None, source_file: str | None = None
                  ) -> bool:
    """True for a div written by an editor or translator, by its title."""
    if (source_file, div_id) in AUTHORIAL_CONTENTS:
        return False
    t = (title or "").replace("’", "'").strip().rstrip(".").strip().lower()
    return bool(EDITORIAL_DIV_TITLE.fullmatch(t))


def span_sha1(text: str) -> str:
    """The key of a bracketed span in `editorial_brackets.json`: sha1 of its text with
    whitespace collapsed."""
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()


_reviewed: frozenset[str] | None = None


def reviewed_editor_brackets() -> frozenset[str]:
    """The sha1s of the long bracketed spans Carter marked "editor" (1.8a's sheet)."""
    global _reviewed
    if _reviewed is None:
        with open(BRACKETS_PATH, encoding="utf-8") as f:
            _reviewed = frozenset(e["sha1"] for e in json.load(f))
    return _reviewed


def editor_bracket(span: str) -> bool:
    """A bracketed span (with its brackets) that is an editor's: the pattern, or a
    reviewed hash. Everything else is the translator's and stays."""
    return bool(EDITOR_BRACKET.search(span)) or span_sha1(span) in reviewed_editor_brackets()


def strip_editor_brackets(text: str, doc_key: str | None = None) -> str:
    """`text` without the editor's bracketed spans, closing up the space each leaves.
    `doc_key` is accepted for the spec's signature; the reviewed hashes are global."""
    return _cut_brackets(text, editor_bracket)[0]


def _cut_brackets(text: str, is_editor) -> tuple[str, list[str], list[tuple[int, int]]]:
    """`text` without the bracketed spans `is_editor` accepts, those spans, and the
    ranges of `text` cut. A span may hold invisible note marks
    (`ingest.common._NOTE_MARK`); `is_editor` sees it without them."""
    removed: list[str] = []
    cuts: list[tuple[int, int]] = []
    pieces: list[str] = []
    last = 0
    for m in BRACKET.finditer(text):
        span = m.group(0)
        if not is_editor(_unmarked(span)):
            continue
        start, end = m.start(), m.end()
        # Close up: drop the space before the span, or else the one after it.
        if start > last and text[start - 1] == " ":
            start -= 1
        elif end < len(text) and text[end] == " ":
            end += 1
        pieces.append(text[last:start])
        last = end
        removed.append(_unmarked(span))
        cuts.append((start, end))
    pieces.append(text[last:])
    return "".join(pieces), removed, cuts


def _unmarked(text: str) -> str:
    return text.replace("⁣", "")


def judgments(text: str) -> list[str]:
    """Each sentence of `text` that holds an authenticity word, in order, at most 300
    characters each (a longer sentence is cut around the word)."""
    out: list[str] = []
    for m in JUDGMENT.finditer(text):
        start = text.rfind(". ", 0, m.start())
        start = 0 if start < 0 else start + 2
        end = text.find(". ", m.end())
        end = len(text) if end < 0 else end + 1
        sentence = " ".join(text[start:end].split())
        if len(sentence) > 300:
            at = max(0, len(" ".join(text[start:m.start()].split())) - 140)
            sentence = sentence[at:at + 300].strip()
        if sentence not in out:
            out.append(sentence)
    return out


def judgment(text: str) -> str | None:
    """The first sentence of `text` that holds an authenticity word, or None."""
    found = judgments(text)
    return found[0] if found else None


# --------------------------------------------------------------------------- lines

@dataclass
class Removed:
    """One thing a chapter lost: a whole paragraph or a bracketed span inside one."""
    block: str              # the paragraph's id (or `n<k>`)
    kind: str               # heading | credit | argument | summary | letter-title |
                            # provenance | bracket | section
    text: str


@dataclass
class LineVerdicts:
    drop: dict[int, str] = field(default_factory=dict)    # paragraph index -> kind
    label_title: str | None = None                        # a title line moved to the label


def classify_lines(paragraphs: list[str], titles: frozenset[str] = frozenset(),
                   *, own_title: str | None = None, argument_lines: bool = True,
                   chapter_title_to_label: bool = False, book_text: bool = False
                   ) -> LineVerdicts:
    """Which paragraphs of a chapter are an editor's, and why. `titles` are the
    normalized titles and short titles of the chapter's div and its ancestors.

    Anywhere in the chapter: a bracketed translator credit or date line, an "Argument"
    summary (unless `argument_lines` is off), an edition's source line. Among the
    heading lines above the chapter's first paragraph of real length: rule lines, number
    lines ("Chapter IV.", "Epistle LXXIV.", "IV."), lines that repeat a title of the
    chapter or a div holding it (whole, or a run of its words, as the Banquet's title is
    printed over three lines), and the letter's title line after its number line
    (`own_title`, the letter div's title, normalized). With
    `chapter_title_to_label`, the first "Chapter N.—Title" line there is the label's
    (`label_title`); elsewhere such lines are left in the text, since only the works
    the Decision log names move theirs. A preface's title goes the same way, printed
    after "Preface.—" or on the line below "Preface.".

    `book_text` is a book div's own text in the NPNF Augustine works (`_book_text`)."""
    if book_text:
        return _book_text(paragraphs)
    v = LineVerdicts()
    lead = True
    after_number = after_preface = False
    for i, raw in enumerate(paragraphs):
        t = " ".join(raw.split())
        if lead and (i >= _LEAD_MAX_BLOCKS
                     or (len(t) >= _LEAD_MAX_CHARS and not CHAPTER_TITLE_LINE.match(t)
                         and not PREFACE_TITLE_LINE.match(t))):
            lead = False
        if CREDIT_LINE.match(t):
            v.drop[i] = "credit"
            continue
        if argument_lines and ARGUMENT_LINE.match(t):
            v.drop[i] = "argument"
            continue
        if len(t) < PROVENANCE_MAX_CHARS and not t.startswith("[") \
                and PROVENANCE_LINE.search(t) and not _PROVENANCE_PROSE.search(t):
            v.drop[i] = "provenance"
            continue
        if not lead:
            continue
        preface, after_preface = after_preface, False
        m = CHAPTER_TITLE_LINE.match(t)
        if m:
            if chapter_title_to_label and v.label_title is None:
                v.drop[i] = "label"
                v.label_title = f"Chapter {m.group('n')}: {m.group('t').rstrip(' .')}"
            after_number = False
            continue
        if chapter_title_to_label and v.label_title is None:
            m = PREFACE_TITLE_LINE.match(t)
            if m or (preface and not t[:1].isdigit()):
                v.drop[i] = "label"
                v.label_title = f"Preface: {(m.group('t') if m else t).rstrip(' .')}"
                after_number = False
                continue
            after_preface = bool(PREFACE_LINE.match(t))
        if RULE_LINE.match(t) or NUMBER_LINE.match(t):
            v.drop[i] = "heading"
            after_number = bool(LETTER_NUMBER_LINE.match(t)) or (after_number and RULE_LINE.match(t))
            continue
        if after_number and own_title and _is_title(t, frozenset({own_title})):
            v.drop[i] = "letter-title"
            after_number = False
            continue
        if _is_title(t, titles):
            v.drop[i] = "heading"
            after_number = False
            continue
        after_number = False
    return v


def _book_text(paragraphs: list[str]) -> LineVerdicts:
    """A book div's own paragraphs in the NPNF Augustine works, which are all the
    editors' (1.8b): the title lines down to the last rule line ("The City of God.",
    "Book I.", "The fifteen books of aurelius augustinus", "———"), then the editor's
    summary of the book: Dods's "Argument—…" in City of God and On Christian Doctrine,
    the Benedictine summary in On the Trinity ("In which the unity and equality…",
    "Augustin pursues his defense…"). More than one paragraph after the rule line would
    be text this rule was not written for, so it raises."""
    v = LineVerdicts()
    lines = [" ".join(p.split()) for p in paragraphs]
    rules = [i for i, t in enumerate(lines) if RULE_LINE.match(t)]
    start = rules[-1] + 1 if rules else 0
    if len(lines) - start > 1:
        raise ValueError(f"a book's own text holds {len(lines) - start} paragraphs after "
                         f"its heading: {lines[start][:60]!r}")
    for i, t in enumerate(lines):
        v.drop[i] = ("heading" if i < start
                     else "argument" if ARGUMENT_LINE.match(t) else "summary")
    return v


def _is_title(line: str, titles: frozenset[str]) -> bool:
    n = _norm(line)
    if not n:
        return False
    if n in titles:
        return True
    # A title printed over several lines: each line is a run of its words.
    return any(f" {n} " in f" {t} " for t in titles if len(t) > len(n))


def strip_editorial_lines(paragraphs: list[str], titles: tuple[str, ...] = ()) -> list[str]:
    """`paragraphs` without the editor's lines `classify_lines` finds."""
    v = classify_lines(paragraphs, frozenset(_norm(t) for t in titles))
    return [p for i, p in enumerate(paragraphs) if i not in v.drop]


# --------------------------------------------------------------------------- chapters

_log: list | None = None


@contextmanager
def recording():
    """Collect `(source_key, chapter div id, ChapterEdit)` for every chapter built inside
    the block, each editorial div skipped as `(source_key, div id, its title)`, and each
    title page left out as `(source_key, work div id, TitlePage)`."""
    global _log
    previous, _log = _log, []
    try:
        yield _log
    finally:
        _log = previous


def _record(source_key: str, div_id: str, removed) -> None:
    if _log is not None:
        _log.append((source_key, div_id, removed))


class Editor:
    """Rule G for one work: which divs to skip, and what each chapter loses. With
    `book_text`, a book div's own text is the editors' (`_book_text`): the NPNF Augustine
    works print only title lines and a summary there (1.8b)."""

    def __init__(self, source_file: str, source_key: str, parent_map: dict, *,
                 book_text: bool = False):
        self.source_file = source_file
        self.source_key = source_key
        self.parent_map = parent_map
        self.book_text = book_text

    def skip(self, elem) -> bool:
        if editorial_div(elem.get("title") or "", elem.get("id"), self.source_file):
            _record(self.source_key, elem.get("id"), (elem.get("title") or "").strip())
            return True
        return False

    def chapter(self, elem, label: str) -> "ChapterEdit":
        """`label` is the chapter label the adapter gives the div. Its own title counts
        as a title line only when the label says the same; otherwise the line is the one
        place its subject is named (a fragment labelled from a short title), so it stays."""
        own = _norm(elem.get("title") or "")
        titles = {_norm(elem.get("shorttitle") or "")}
        if own and own == _norm(label):
            titles.add(own)
        cur = self.parent_map.get(elem)
        while cur is not None and isinstance(cur.tag, str) and cur.tag.startswith("div"):
            titles |= {_norm(cur.get("title") or ""), _norm(cur.get("shorttitle") or "")}
            cur = self.parent_map.get(cur)
        titles.discard("")
        edit = ChapterEdit(elem, frozenset(titles), own_title=own or None,
                           argument_lines=self.source_key not in AUTHORIAL_ARGUMENTS,
                           chapter_title_to_label=self.source_key in CHAPTER_TITLE_WORKS,
                           book_text=self.book_text
                           and (elem.get("type") or "").lower() == "book")
        _record(self.source_key, elem.get("id"), edit)
        return edit

    def title_page(self, elem) -> None:
        """Record a work div's own text, its title page, as left out: the title, Latin
        title and translator's credit, and an editor's notice (1.8b)."""
        _record(self.source_key, elem.get("id"),
                TitlePage((elem.get("title") or "").strip(), _block_texts(elem)))


@dataclass
class TitlePage:
    """A work's title page, which the build leaves out (its text, paragraph by paragraph)."""
    title: str
    paragraphs: list[str]


def _block_texts(elem) -> list[str]:
    return [t for t in (_block_text(b) for b in direct_blocks(elem)) if t]


class ChapterEdit:
    """What one chapter div loses. `edit(block, marked, notes)` is called by
    `ingest.common.direct_blocks_text` with each paragraph's text as read with note
    marks, and returns it edited (empty to drop it) with the notes it keeps."""

    def __init__(self, elem, titles: frozenset[str], *, own_title: str | None = None,
                 argument_lines: bool = True, chapter_title_to_label: bool = False,
                 book_text: bool = False):
        self.elem = elem
        self.again = lambda: ChapterEdit(       # a fresh edit of the same chapter
            elem, titles, own_title=own_title, argument_lines=argument_lines,
            chapter_title_to_label=chapter_title_to_label, book_text=book_text)
        blocks = direct_blocks(elem)
        div = elem.get("id") or ""
        self.locators = {id(b): _locator(b, div, k) for k, b in enumerate(blocks, 1)}
        self.order = [self.locators[id(b)] for b in blocks]   # paragraphs, reading order
        sections = _editor_sections(elem)
        self.removed: list[Removed] = [
            Removed(self.locators[id(b)], "section", t) for b in blocks
            if id(b) in sections and (t := _block_text(b))]
        kept = [(b, t) for b, t in ((b, _block_text(b)) for b in blocks)
                if t and id(b) not in sections]
        v = classify_lines([t for _, t in kept], titles, own_title=own_title,
                           argument_lines=argument_lines,
                           chapter_title_to_label=chapter_title_to_label, book_text=book_text)
        self.label_title = v.label_title
        self._read: set[int] = set()
        self.dropped = {id(kept[i][0]): kind for i, kind in v.drop.items()}
        self.dropped.update((i, "section") for i in sections)
        self.removed += [
            Removed(self.locators[id(kept[i][0])], kind, kept[i][1])
            for i, kind in sorted(v.drop.items()) if kind != "label"]
        self.label_line = next((kept[i][1] for i, kind in v.drop.items() if kind == "label"),
                               None)

    def edit(self, block, marked: str, notes: list[str]) -> tuple[str, list[str]]:
        if id(block) in self.dropped:
            return "", []
        if "[" not in marked:
            return marked, notes
        out, spans, cuts = _cut_brackets(marked, editor_bracket)
        if id(block) not in self._read:       # paragraph_segments reads it again
            self._read.add(id(block))
            self.removed += [Removed(self.locators[id(block)], "bracket", s) for s in spans]
        if cuts:
            # A note inside a removed span goes with it.
            marks = [k for k, c in enumerate(marked) if c == "\u2063"]
            notes = [n for n, at in zip(notes, marks)
                     if not any(a <= at < b for a, b in cuts)]
        return out, notes


def _editor_sections(elem) -> set[int]:
    """The `id()`s of a chapter's paragraphs that stand under an editor's heading
    (`EDITORIAL_HEADING`), up to the next other heading."""
    from ingest.common import _strip_tags
    from xml.etree.ElementTree import tostring

    out: set[int] = set()
    level = 0                                  # the open section's heading level, or 0
    previous = None
    for child in elem:
        if child.tag in _HEADINGS:
            text = " ".join(_strip_tags(tostring(child, encoding="unicode",
                                                 method="xml")).split())
            n = int(child.tag[1])
            if EDITORIAL_HEADING.fullmatch(text.replace("\u2019", "'").rstrip(".").lower()):
                level = n
                # The rule line printed above the heading opens the section.
                if previous is not None and RULE_LINE.match(_block_text(previous) or "x"):
                    out.add(id(previous))
            elif level and n <= level and not NUMBER_LINE.match(text):
                level = 0                      # an author's heading ends it; "I." does not
        elif child.tag in ("p", "verse"):
            if level:
                out.add(id(child))
            previous = child
    return out


def _locator(block, div: str, k: int) -> str:
    """A paragraph's name in its chapter, as `ingest.thml_doc.paragraph_segments` gives it."""
    pid = block.get("id")
    if pid and div and pid.startswith(div + "-"):
        return pid[len(div) + 1:]
    return pid or f"n{k}"


# --------------------------------------------------------------------------- audit

_WORD = re.compile(r"[^\W_]+")


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def unexplained_changes(before: str, after: str, removed: list[str]) -> list[str]:
    """How a chapter's text read without rule G (`before`) differs from its text with it
    (`after`) other than by the `removed` texts, in reading order: an empty list means
    the author's words are unchanged (1.8a's coverage check). Compared word by word, so
    the spaces a cut closes up don't count, nor the order the removals are listed in."""
    from difflib import SequenceMatcher

    a, b = _words(before), _words(after)
    lost: list[str] = []
    problems: list[str] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "delete":
            lost += a[i1:i2]
        elif tag != "equal":
            problems.append(f"{tag}: {' '.join(a[i1:i2])[:80]!r} -> {' '.join(b[j1:j2])[:80]!r}")
    expected = [w for text in removed for w in _words(text)]
    if sorted(lost) != sorted(expected):
        problems.append(f"removed {len(lost)} words, the record explains {len(expected)}")
    return problems
