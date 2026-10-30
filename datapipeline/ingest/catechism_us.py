"""Put the US edition's text into the Catechism source's structure (issue #279, B2).

`ccc.json` (vatican.va's English) gives the structure the adapter chunks: page nodes,
their order and the paragraphs each holds. Its words are not the US edition's: UK
spelling, lines dropped by the old header test (1.6a), the 1997 CCC 2267. The US
edition, `us-edition/ccc-us.json`, gives the words.

The paragraph numbers (`ref-ccc`) cut both files into the same sequence of gaps: the
unnumbered text before CCC 1, between N-1 and N, and after 2865. Within each gap the
source's unnumbered lines are matched to the US headings of the same gap by their words
(`words`): a run of source lines whose words equal one US heading's is that heading.
Lines before the gap's first matched heading continue the numbered paragraph before them;
the paragraph's whole run is replaced by the US text for its number. Every source line is
consumed once. A US heading no source line matches is inserted where it belongs; a line
after a matched heading that matches nothing stays unmatched. Both are reported.

What the US text replaces it replaces whole: the paragraph's words, a heading's words,
and the footnotes of each. Structural titles (Part, Section, Chapter, Article) are the
exception: the US site prints them only as breadcrumbs ("Section 2: The Ten
Commandments"), which are its own formatting, so a matched structural line keeps the
source's printed form ("SECTION TWO", "THE TEN COMMANDMENTS"), its words checked against
the breadcrumb. An inserted structural title is printed the source's way, in capitals.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ingest.catechism_headings import TEXT_FIXES
from normalize.text import clean_text

US_SOURCE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "sources", "catechism", "us-edition", "ccc-us.json",
)

_MAX_RUN = 8  # source lines one US heading may span (the Prologue's epigraph is 3)
_NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
}
_ORDINAL_WORDS = {"first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5",
                  "sixth": "6", "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10"}
# UK and US spellings meet in one form. Applied to both sides, so an over-eager rule can
# only make two different words equal, never make equal words differ.
_SPELLING = (
    (re.compile(r"(?<=[a-z]{2})our(?=s?$|ed$|ing$|able$|ite$)"), "or"),  # saviour, honour; not "your"
    (re.compile(r"is(?=e[sd]?$|ing$|ation)"), "iz"),         # baptise, organisation
    (re.compile(r"ys(?=e[sd]?$|ing$)"), "yz"),               # analyse
    (re.compile(r"tre(?=s?$)"), "ter"),                      # centre
    (re.compile(r"ogue(?=s?$)"), "og"),                      # catalogue
    (re.compile(r"ll"), "l"),                                # travelled; fulfils/fulfills
    (re.compile(r"ae"), "e"),                                # mediaeval
    (re.compile(r"ement$"), "ment"),                         # judgement
)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for wrong, right in TEXT_FIXES:
        text = text.replace(wrong, right)
    return text.casefold().replace("’", "'").replace("‘", "'")


# Pairs no pattern catches without catching real words too.
_SPELLING_WORDS = {"defence": "defense", "offence": "offense", "offences": "offenses",
                   "licence": "license", "pretence": "pretense", "practise": "practice",
                   "practised": "practiced", "practising": "practicing", "grey": "gray",
                   "programme": "program", "cheque": "check", "towards": "toward",
                   "formulae": "formulas", "foetus": "fetus", "manoeuvre": "maneuver"}


def spelling_form(word: str) -> str:
    word = _SPELLING_WORDS.get(word, word)
    for pattern, replacement in _SPELLING:
        word = pattern.sub(replacement, word)
    return word


def words(text: str) -> list[str]:
    """A text's words for matching: case, punctuation, hyphenation ("co-operate"),
    number words and UK/US spelling folded away."""
    tokens = re.findall(r"[a-z0-9]+", _fold(text).replace("-", "").replace("'", ""))
    out = []
    for token in tokens:
        token = _NUMBER_WORDS.get(token, _ORDINAL_WORDS.get(token, token))
        out.append(spelling_form(token))
    return out


_LEVELS = {"part", "section", "chapter", "article"}


def structure_words(text: str) -> list[str]:
    """`words`, with the level word folded: the site's breadcrumbs call Part Four's
    Articles "Chapter", and the source's printed titles keep "Article"."""
    return ["level" if w in _LEVELS else w for w in words(text)]


def raw_words(text: str) -> list[str]:
    """Words with case and punctuation folded, but spelling kept (for the report)."""
    return re.findall(r"[a-z0-9]+", _fold(text).replace("-", "").replace("'", ""))


# ---------------------------------------------------------------------------
# The two sequences
# ---------------------------------------------------------------------------

@dataclass
class SourceLine:
    node_id: str
    index: int                  # position in the node's `paragraphs`
    text: str                   # the line's text elements, joined as the adapter does
    number: int | None          # its CCC number, if the line opens a numbered paragraph


@dataclass
class Gap:
    """What sits after paragraph `after` (0: before CCC 1) and before the next."""
    after: int
    source: list[SourceLine] = field(default_factory=list)
    us: list[dict] = field(default_factory=list)


def _line_text(paragraph: dict) -> str:
    return " ".join(
        el.get("text", "") for el in paragraph.get("elements", [])
        if el.get("type") == "text" and el.get("text")
    ).strip()


def ordered_node_ids(page_nodes: dict) -> list[str]:
    def key(k: str) -> int:
        try:
            return int(k.split("-", 1)[1])
        except (IndexError, ValueError):
            return 0
    return sorted(page_nodes, key=key)


def source_lines(page_nodes: dict) -> list[SourceLine]:
    lines = []
    for node_id in ordered_node_ids(page_nodes):
        for index, paragraph in enumerate(page_nodes[node_id].get("paragraphs", [])):
            number = next((el.get("ref_number") for el in paragraph.get("elements", [])
                           if el.get("type") == "ref-ccc"), None)
            text = _line_text(paragraph)
            if number is None and not text:
                continue                          # spacers
            lines.append(SourceLine(node_id, index, text, number))
    return lines


def gaps(lines: list[SourceLine], us_items: list[dict]) -> dict[int, Gap]:
    out: dict[int, Gap] = {}
    after = 0
    out[0] = Gap(0)
    for line in lines:
        if line.number is not None:
            after = line.number
            out[after] = Gap(after)
        else:
            out[after].source.append(line)
    after = 0
    for item in us_items:
        if item["kind"] == "paragraph":
            after = item["n"]
            if after not in out:
                raise ValueError(f"US paragraph {after} has no source paragraph")
        else:
            out[after].us.append(item)
    return out


# ---------------------------------------------------------------------------
# Matching within a gap, word by word
# ---------------------------------------------------------------------------
#
# The source sometimes glues a heading onto the end of a text line ("... moral
# conscience. the obligation" then "of the Decalogue"), so a gap is matched as one
# stream of words, each remembering the line it came from.

_TOKEN = re.compile(r"[^\W_]+(?:['\u2019\-][^\W_]+)*")
_CONTINUATION_MIN = 0.8   # share of a line's words found, in order, in the US paragraph


@dataclass
class Token:
    word: str           # folded (`words`)
    line: int           # index into the gap's source lines
    start: int          # character span in that line's text
    end: int


def tokens(lines: list[SourceLine]) -> list[Token]:
    out = []
    for i, line in enumerate(lines):
        for m in _TOKEN.finditer(line.text):
            for w in words(m.group(0)):
                out.append(Token(w, i, m.start(), m.end()))
    return out


@dataclass
class HeadingMatch:
    item: dict              # the US heading
    start: int              # token range in the gap's stream
    end: int
    fuzzy: bool = False     # one misprinted word, or a heading the source cut short
    numbering: str = ""     # the source's "I." before a heading the US prints without it
    title_missing: bool = False   # the source prints only "SECTION TWO" (toc-45)


@dataclass
class GapMatch:
    after: int
    lines: list[SourceLine]
    toks: list[Token]
    headings: list[HeadingMatch]
    inserted: list[tuple[int, dict]]            # (headings matched before it, US heading)
    continuation: list[int]                     # line indexes consumed as continuation
    unmatched: list[int]                        # line indexes kept as source text
    free_text: dict[int, str] = field(default_factory=dict)   # line -> its words outside headings
    moved: list[tuple[int, int]] = field(default_factory=list)  # (line, gap the US puts it in)


def _boundaries(toks: list[Token], lines: list[SourceLine]) -> tuple[list[bool], list[bool]]:
    """Where a heading may start and end. It ends at the end of a source line, and
    starts at the start of one or right after sentence punctuation: the source glues a
    few headings onto the line before ("... moral conscience. the obligation"), never
    into the middle of a sentence ("46 books for the Old Testament (45 if ...")."""
    starts, ends = [], []
    for k, t in enumerate(toks):
        line = lines[t.line].text
        first_on_line = k == 0 or toks[k - 1].line != t.line
        before = line[:t.start].rstrip()
        after = line[t.end:]
        starts.append(first_on_line or before.endswith((".", "!", "?", ":", ";", '"', "\u201d"))
                      or line[:t.start].endswith((" - ", " \u2014 ")))
        ends.append(k == len(toks) - 1 or toks[k + 1].line != t.line
                    or after.startswith((" - ", " \u2014 ")))   # two headings on one line
    return starts, ends


_SIMILAR = 0.85   # letters-only similarity for a badly misprinted whole-line heading


def _letters(ws: list[str]) -> str:
    return "".join(ws)


def _find(stream: list[str], target: list[str], taken: set[int],
          starts: list[bool], ends: list[bool]) -> tuple[int, int, bool] | None:
    """(start, end, fuzzy) of the source run that is `target`, or None. Tried in turn:
    the exact words; one misprinted word; for runs of whole lines, letters at least
    85% alike ("Characteristics of the People of Got", "T he Eucharist"). Whole lines
    are preferred to a heading glued after a sentence, then the earliest place."""
    n = len(target)
    if not n:
        return None
    free = lambda i, j: not any(k in taken for k in range(i, j))  # noqa: E731
    candidates = [i for i in range(len(stream) - n + 1)
                  if starts[i] and ends[i + n - 1] and free(i, i + n)]
    candidates.sort(key=lambda i: (not _line_start(i, starts, ends), i))
    for i in candidates:
        if stream[i:i + n] == target:
            return i, i + n, False
    if n >= 4:
        for i in candidates:
            if sum(a != b for a, b in zip(stream[i:i + n], target)) == 1 \
                    and stream[i] == target[0] and stream[i + n - 1] == target[-1]:
                return i, i + n, True
    want = _letters(target)
    best = None
    for i in range(len(stream)):
        if not _line_start(i, starts, ends) or i in taken:
            continue
        for j in range(i + 1, min(len(stream), i + 3 * n) + 1):
            if not free(i, j):
                break
            if not ends[j - 1]:
                continue
            got = _letters(stream[i:j])
            if len(got) > 1.25 * len(want):
                break
            if len(got) < 0.75 * len(want):
                continue
            ratio = SequenceMatcher(None, got, want, autojunk=False).ratio()
            if ratio >= _SIMILAR and (best is None or ratio > best[0]):
                best = (ratio, i, j)
    if best:
        return best[1], best[2], True
    return None


def _line_start(i: int, starts: list[bool], ends: list[bool]) -> bool:
    return i == 0 or ends[i - 1]


def _in_order_share(part: list[str], paragraph: list[str]) -> float:
    if not part:
        return 1.0
    from difflib import SequenceMatcher
    blocks = SequenceMatcher(None, part, paragraph, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks) / len(part)


def match_gap(gap: Gap, paragraph_words: list[str] | None) -> GapMatch:
    toks = tokens(gap.source)
    stream = [t.word for t in toks]
    level_stream = ["level" if w in _LEVELS else w for w in stream]
    starts, ends = _boundaries(toks, gap.source)
    found: dict[int, HeadingMatch] = {}
    taken: set[int] = set()
    # Exact matches first, over the whole gap, so a misprint elsewhere cannot take a
    # line that another heading matches exactly; then the rest.
    for exact_pass in (True, False):
        for k, item in enumerate(gap.us):
            if k in found:
                continue
            if item["kind"] == "structure":
                hit = _find(level_stream, structure_words(item["text"]), taken, starts, ends)
            else:
                hit = _find(stream, words(item["text"]), taken, starts, ends)
            if hit is None or (exact_pass and hit[2]):
                continue
            i, j, fuzzy = hit
            found[k] = HeadingMatch(item, i, j, fuzzy)
            taken.update(range(i, j))
    headings = sorted(found.values(), key=lambda h: h.start)
    inserted: list[tuple[int, dict]] = []
    for k, item in enumerate(gap.us):
        if k not in found:
            # Goes before the first matched heading that follows it in the US order.
            later = [found[x].start for x in found if x > k]
            inserted.append((sum(h.start < min(later) for h in headings) if later else len(headings), item))

    # A heading the source prints cut short ("Consecrated virgins" for the US
    # "Consecrated virgins and widows"): a whole unmatched line that begins the heading
    # and holds at least half its words is that heading.
    taken = {k for h in headings for k in range(h.start, h.end)}
    for order, item in list(inserted):
        target = words(item["text"])
        for li in range(len(gap.source)):
            span = [k for k, t in enumerate(toks) if t.line == li]
            if not span or any(k in taken for k in span):
                continue
            run = [stream[k] for k in span]
            if 2 <= len(run) < len(target) and target[:len(run)] == run and 2 * len(run) >= len(target):
                before = [h for h in headings if h.start < span[0]]
                if len(before) != order:
                    continue            # out of order with the matched headings
                headings.insert(order, HeadingMatch(item, span[0], span[-1] + 1, True))
                inserted.remove((order, item))
                taken.update(span)
                inserted = [(o + 1 if o > order else o, it) for o, it in inserted]
                break

    # A heading the source glues onto the end of a line in mid-sentence: an inserted
    # heading whose exact words end a line among the words no heading took.
    for order, item in list(inserted):
        target = words(item["text"])
        if len(target) < 3:
            continue
        for i in range(len(stream) - len(target) + 1):
            j = i + len(target)
            if ends[j - 1] and stream[i:j] == target and not any(k in taken for k in range(i, j)):
                headings.insert(order, HeadingMatch(item, i, j, True))
                inserted.remove((order, item))
                taken.update(range(i, j))
                inserted = [(o + 1 if o > order else o, it) for o, it in inserted]
                break

    # A structural title the source prints without its title, "SECTION TWO" alone
    # (Part One's Section Two, toc-45 in catechism_headings.TITLE_FIXES): a whole
    # unmatched line holding just its level and number.
    for order, item in list(inserted):
        if item["kind"] != "structure":
            continue
        target = structure_words(item["text"])[:2]
        for li in range(len(gap.source)):
            span = [k for k, t in enumerate(toks) if t.line == li]
            if span and not any(k in taken for k in span) and \
                    [level_stream[k] for k in span] == target:
                headings.insert(order, HeadingMatch(item, span[0], span[-1] + 1, True, title_missing=True))
                inserted.remove((order, item))
                taken.update(span)
                inserted = [(o + 1 if o > order else o, it) for o, it in inserted]
                break

    # The source's numbering before a heading the US site prints bare ("I. THE
    # CREEDS" against "THE CREEDS"): the numeral joins the heading.
    for h in headings:
        k = h.start - 1
        if k >= 0 and toks[k].line == toks[h.start].line and k not in taken and \
                re.fullmatch(r"[ivxl]+|\d+", toks[k].word) and \
                (k == 0 or toks[k - 1].line != toks[k].line):
            line = gap.source[toks[k].line].text
            h.numbering = line[toks[k].start:toks[h.start].start].strip()
            h.start = k
            taken.add(k)

    # Each token is in a heading, or else free; free tokens are grouped by line.
    in_heading = [False] * len(toks)
    for h in headings:
        for k in range(h.start, h.end):
            in_heading[k] = True
    first_heading = headings[0].start if headings else len(toks)
    continuation, unmatched = [], []
    free_text: dict[int, str] = {}
    for li in range(len(gap.source)):
        free = [k for k, t in enumerate(toks) if t.line == li and not in_heading[k]]
        if not free:
            continue
        part = [stream[k] for k in free]
        before_headings = all(k < first_heading for k in free)
        if (paragraph_words is not None and before_headings
                and _in_order_share(part, paragraph_words) >= _CONTINUATION_MIN):
            continuation.append(li)
        else:
            unmatched.append(li)
        free_text[li] = gap.source[li].text[toks[free[0]].start:toks[free[-1]].end]
    return GapMatch(gap.after, gap.source, toks, headings, inserted, continuation, unmatched,
                    free_text)


# ---------------------------------------------------------------------------
# Applying the US text to the source's nodes
# ---------------------------------------------------------------------------

_NUMBER_NAMES = {str(n): w.upper() for w, n in _NUMBER_WORDS.items()}


def _structural_caps(title: str) -> str:
    """An inserted structural title printed as the source prints its own: "SECTION TWO"
    then the title on its own line, in capitals ("Article 3" keeps its digit, as there)."""
    m = re.match(r"^(Part|Section|Chapter|Article)\s+(\d+):\s*(.*)$", title, re.S)
    if not m:
        return title.upper()
    level, number, rest = m.groups()
    number = number if level == "Article" else _NUMBER_NAMES.get(number, number)
    return f"{level.upper()} {number}\n\n{rest.upper()}"


def _source_form(match: GapMatch, h: HeadingMatch) -> str:
    """The source's printed text for a matched structural title, lines kept apart."""
    first, last = match.toks[h.start], match.toks[h.end - 1]
    # A run that starts or ends its line takes the line's edge, so the quotation marks
    # and punctuation around the words stay ('"OUR FATHER WHO ART IN HEAVEN"').
    opens_line = h.start == 0 or match.toks[h.start - 1].line != first.line
    closes_line = h.end == len(match.toks) or match.toks[h.end].line != last.line
    parts = []
    for li in range(first.line, last.line + 1):
        text = match.lines[li].text
        lo = first.start if li == first.line and not opens_line else 0
        hi = last.end if li == last.line and not closes_line else len(text)
        parts.append(_fix(text[lo:hi]).strip())
    return "\n\n".join(p for p in parts if p)


@dataclass
class Alignment:
    page_nodes: dict                         # ccc.json's nodes, with US text in them
    items: dict[str, dict]                   # item key -> {kind, text, footnotes, n?}
    order: list[str]                         # item keys in reading order
    matches: list[GapMatch]
    old_paragraphs: dict[int, str]           # the source's own text, for the report


def _paragraph(text: str, number: int | None, key: str, heading: bool) -> dict:
    # Cleaned on its own, before the chunker joins it to its neighbours: cleaning the
    # joined text lets the ellipsis rule reach across a paragraph break and eat the
    # full stop before it (CCC 76's 'writing".' followed by "... continued").
    text = clean_text(text)
    elements = []
    if number is not None:
        elements.append({"type": "ref-ccc", "ref_number": number})
    elements.append({"type": "text", "text": text})
    return {"attrs": {}, "elements": elements, "_item": key, "_heading": heading}


def _heading_fixes(us: dict) -> tuple[dict, dict]:
    """(after -> [(find, replace)], after -> {texts to drop}) from the US file's corrections."""
    fixes, drops = {}, {}
    for h in us.get("_heading_corrections", []):
        if "replace_line" in h:
            fixes.setdefault(("line", h["after"]), []).append((h["replace_line"], h["with"]))
        elif "drop" in h:
            drops.setdefault(h["after"], set()).add(h["drop"])
        else:
            fixes.setdefault(h["after"], []).append((h["find"], h["replace"]))
    return fixes, drops


def align(source: dict, us: dict) -> Alignment:
    page_nodes = source["page_nodes"]
    fixes, drops = _heading_fixes(us)
    used_fixes: set = set()

    def fix(after: int, text: str) -> str:
        for find, replace in fixes.get(after, []):
            if text.count(find) == 1:
                used_fixes.add((after, find))
                text = text.replace(find, replace)
        return text
    us_items = us["items"]
    lines = source_lines(page_nodes)
    all_gaps = gaps(lines, us_items)
    us_paragraphs = {item["n"]: item for item in us_items if item["kind"] == "paragraph"}
    numbered = {line.number: line for line in lines if line.number is not None}
    if set(us_paragraphs) != set(numbered):
        raise ValueError("the US edition and the source number different paragraphs")

    # For each source line: what it becomes, in order (US items starting there, or the
    # line itself when it stays). A line absent from the map is kept unchanged.
    out: dict[tuple[str, int], list[dict]] = {}
    items: dict[str, dict] = {}
    old: dict[int, list[str]] = {}
    matches = []

    for n, line in numbered.items():
        key = f"p{n}"
        item = us_paragraphs[n]
        items[key] = {"kind": "paragraph", "n": n, "text": item["text"],
                      "footnotes": item["footnotes"]}
        out[(line.node_id, line.index)] = [_paragraph(item["text"], n, key, False)]
        old[n] = [line.text]

    by_gap = {}
    for after in sorted(all_gaps):
        # Matched against the text as fetched: the source's lines were written from it,
        # not from the corrections applied to it afterwards.
        fetched = us_paragraphs[after].get("_fetched_text", us_paragraphs[after]["text"]) if after else None
        paragraph_words = words(fetched) if after else None
        by_gap[after] = match_gap(all_gaps[after], paragraph_words)
    _moves(by_gap)

    for after in sorted(all_gaps):
        gap = all_gaps[after]
        match = by_gap[after]
        matches.append(match)
        slot = {li: [] for li in range(len(gap.source))}
        consumed = set(match.continuation)
        if after:
            _trim_glued(old, after, numbered[after], match)
        for li in match.continuation:
            old[after].append(match.free_text[li])
        for h in match.headings:
            key = f"g{after}.{gap.us.index(h.item)}"
            structural = h.item["kind"] == "structure"
            if structural and h.title_missing:
                text = _structural_caps(h.item["text"])
            elif structural:
                text = _source_form(match, h)
            else:
                text = f"{h.numbering} {h.item['text']}" if h.numbering else h.item["text"]
            text = fix(after, text)
            first_line = match.toks[h.start].line
            items[key] = {"kind": h.item["kind"], "text": text,
                          "footnotes": [] if structural else h.item["footnotes"],
                          "fuzzy": h.fuzzy,
                          "source_line": (gap.source[first_line].node_id, gap.source[first_line].index)}
            slot[first_line].append(_paragraph(text, None, key, True))
            for li in range(first_line, match.toks[h.end - 1].line + 1):
                consumed.add(li)
        for li, _ in match.moved:
            consumed.add(li)          # the US heading is printed in the neighbouring gap
        for li in list(match.unmatched):
            if gap.source[li].text in drops.get(after, ()):
                used_fixes.add((after, gap.source[li].text))
                match.unmatched.remove(li)
                consumed.add(li)              # not in the book (corrections)
                continue
            # Kept as the source prints it, after anything that starts on the line,
            # unless the corrections give the book's text for the whole line.
            consumed.discard(li)
            line_fix = next((w for f, w in fixes.get(("line", after), []) if f == gap.source[li].text), None)
            if line_fix is not None:
                used_fixes.add((("line", after), gap.source[li].text))
                slot[li].append(_paragraph(line_fix, None, f"src:{gap.source[li].node_id}:{gap.source[li].index}", False))
            else:
                slot[li].append(None)
        for order, heading in match.inserted:
            key = f"g{after}.{gap.us.index(heading)}"
            structural = heading["kind"] == "structure"
            text = _structural_caps(heading["text"]) if structural else heading["text"]
            if text in drops.get(after, ()):
                used_fixes.add((after, text))
                continue                      # the book prints it elsewhere (corrections)
            text = fix(after, text)
            items[key] = {"kind": heading["kind"], "text": text,
                          "footnotes": heading["footnotes"], "inserted": True}
            para = _paragraph(text, None, key, True)
            if order < len(match.headings):
                slot[match.toks[match.headings[order].start].line].insert(0, para)
            else:
                following = next((n for n in sorted(numbered) if n > after), None)
                if following is None:
                    raise ValueError(f"a US heading after CCC {after} has nowhere to go")
                target = numbered[following]
                out[(target.node_id, target.index)].insert(0, para)
        for li, line in enumerate(gap.source):
            if li in consumed or slot[li]:
                out[(line.node_id, line.index)] = slot[li]

    wanted = {(a, f) for a, fs in fixes.items() for f, _ in fs} | {(a, t) for a, ts in drops.items() for t in ts}
    if wanted - used_fixes:
        raise ValueError(f"catechism heading corrections do not apply: {sorted(wanted - used_fixes)[:10]}")

    nodes = {}
    order: list[str] = []
    for node_id in ordered_node_ids(page_nodes):
        node = page_nodes[node_id]
        paragraphs = []
        for index, paragraph in enumerate(node.get("paragraphs", [])):
            key = (node_id, index)
            kept = {**paragraph, "_item": f"src:{node_id}:{index}", "_heading": False}
            if key not in out:
                if _line_text(paragraph):
                    paragraphs.append(kept)          # a line no match touched, as printed
                    order.append(kept["_item"])
                continue
            for produced in out[key]:
                produced = kept if produced is None else produced  # None: unmatched, as printed
                paragraphs.append(produced)
                order.append(produced["_item"])
        nodes[node_id] = {**node, "paragraphs": paragraphs}
    return Alignment(nodes, items, order, matches,
                     {n: "\n".join(parts) for n, parts in old.items()})


def _trim_glued(old: dict[int, list[str]], after: int, line: SourceLine, match: GapMatch) -> None:
    """Some headings sit glued to the end of the numbered paragraph's own line ("... over
    all that he has made.  God creates "out of nothing""). The US text replaces that line
    and the heading is inserted after it, so the output is right; only the report's old
    text must leave the heading's words out."""
    toks = tokens([line])
    stream = [t.word for t in toks]
    for _, item in match.inserted:
        target = words(item["text"])
        if target and len(stream) > len(target) and stream[-len(target):] == target:
            old[after][0] = line.text[:toks[-len(target)].start].rstrip()
            item["_glued"] = True
            break


def _moves(by_gap: dict[int, GapMatch]) -> None:
    """A heading the US site prints one gap away from the source ("What is an
    indulgence?": the site before CCC 1471, the source inside it) is the same heading:
    the source line is consumed and the US placement kept."""
    order = sorted(by_gap)
    for pos, after in enumerate(order):
        match = by_gap[after]
        for other in (order[pos - 1] if pos else None, order[pos + 1] if pos + 1 < len(order) else None):
            if other is None:
                continue
            for _, item in by_gap[other].inserted:
                target = words(item["text"])
                for li in list(match.unmatched):
                    got = words(match.lines[li].text)
                    if got == target or (len(target) >= 2 and SequenceMatcher(
                            None, _letters(got), _letters(target), autojunk=False).ratio() >= _SIMILAR):
                        match.unmatched.remove(li)
                        match.moved.append((li, other))
                        break


def _fix(text: str) -> str:
    for wrong, right in TEXT_FIXES:
        text = text.replace(wrong, right)
    return text


CORRECTIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catechism_corrections.json")


def _move_offset(at: int, start: int, find: str, replace: str) -> int:
    """Where a footnote offset lands after `find` at `start` becomes `replace`."""
    end = start + len(find)
    if at <= start:
        return at
    if at >= end:
        return at + len(replace) - len(find)
    # Inside the corrected words: follow the character alignment of old and new.
    inside = at - start
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, find, replace, autojunk=False).get_opcodes():
        if i1 <= inside <= i2:
            return start + (j1 + min(inside - i1, j2 - j1) if tag == "equal" else j2)
    return start + len(replace)


def apply_corrections(us: dict, corrections: list[dict]) -> dict:
    """The US items with the reviewed corrections applied (paragraphs, in order).
    Each `find` must occur exactly once in its paragraph; footnote offsets move with
    the text. Raises on any entry that does not apply."""
    paragraphs = {item["n"]: item for item in us["items"] if item.get("kind") == "paragraph"}
    problems = []
    for c in corrections:
        item = paragraphs.get(c["n"])
        if item is None or item["text"].count(c["find"]) != 1:
            problems.append(f"CCC {c['n']}: {c['find'][:60]!r} "
                            f"occurs {0 if item is None else item['text'].count(c['find'])} times")
            continue
        start = item["text"].index(c["find"])
        item.setdefault("_fetched_text", item["text"])     # what alignment matches against
        item["text"] = item["text"][:start] + c["replace"] + item["text"][start + len(c["find"]):]
        for note in item["footnotes"]:
            note["at"] = _move_offset(note["at"], start, c["find"], c["replace"])
    if problems:
        raise ValueError("catechism corrections do not apply: " + "; ".join(problems[:10]))
    return us


def apply_footnote_corrections(us: dict, footnotes: list[dict], lists: list[dict]) -> dict:
    """The US items with the reviewed footnote corrections applied, after the text ones.

    A `footnotes` entry gives one note's corrected text: the note numbered `note` on
    paragraph `n`, or on the heading whose fetched text is `heading`. A `lists` entry
    replaces paragraph `n`'s notes outright (where the site numbers or places them
    wrongly): each note sits after its `after` words, which must occur exactly once in
    the corrected paragraph. Raises on any entry that does not apply."""
    paragraphs = {item["n"]: item for item in us["items"] if item.get("kind") == "paragraph"}
    headings: dict[str, list[dict]] = {}
    for item in us["items"]:
        if item.get("kind") == "heading":
            headings.setdefault(item["text"], []).append(item)
    problems = []
    for c in footnotes:
        where = f"CCC {c['n']}" if "n" in c else f"heading {c['heading'][:40]!r}"
        owners = [paragraphs[c["n"]]] if c.get("n") in paragraphs else headings.get(c.get("heading"), [])
        notes = [note for owner in owners for note in owner["footnotes"] if note["n"] == c["note"]]
        if len(owners) != 1 or len(notes) != 1:
            problems.append(f"{where} note {c['note']}: found {len(notes)}")
            continue
        notes[0]["text"] = c["text"]
    for c in lists:
        item = paragraphs.get(c["n"])
        if item is None:
            problems.append(f"CCC {c['n']}: no such paragraph")
            continue
        replaced = []
        for note in c["notes"]:
            if item["text"].count(note["after"]) != 1:
                problems.append(f"CCC {c['n']} note {note['n']}: {note['after']!r} "
                                f"occurs {item['text'].count(note['after'])} times")
                continue
            at = item["text"].index(note["after"]) + len(note["after"])
            replaced.append({"n": note["n"], "text": note["text"], "at": at})
        item["footnotes"] = sorted(replaced, key=lambda note: note["at"])
    if problems:
        raise ValueError("catechism footnote corrections do not apply: " + "; ".join(problems[:10]))
    return us


def load_corrections(path: str = CORRECTIONS) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["corrections"]


def load_us(path: str = US_SOURCE, corrections: list[dict] | None = None) -> dict:
    """The US edition, with the reviewed corrections applied. They belong to the vendored
    file, so another file (a test fixture) gets none unless they are passed."""
    with open(path, encoding="utf-8") as f:
        us = json.load(f)
    vendored = os.path.abspath(path) == os.path.abspath(US_SOURCE)
    if corrections is None:
        corrections = load_corrections() if vendored else []
    us = apply_corrections(us, corrections)
    if vendored:
        with open(CORRECTIONS, encoding="utf-8") as f:
            table = json.load(f)
        us["_heading_corrections"] = table.get("headings", [])
        us = apply_footnote_corrections(us, table.get("footnotes", []), table.get("footnote_lists", []))
    return us
