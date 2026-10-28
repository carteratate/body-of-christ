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

from ingest.catechism_headings import TEXT_FIXES

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
    (re.compile(r"our(?=s?$|ed$|ing$|able$|ite$)"), "or"),   # saviour, honour, favourite
    (re.compile(r"is(?=e[sd]?$|ing$|ation)"), "iz"),         # baptise, organisation
    (re.compile(r"ys(?=e[sd]?$|ing$)"), "yz"),               # analyse
    (re.compile(r"tre(?=s?$)"), "ter"),                      # centre
    (re.compile(r"ogue(?=s?$)"), "og"),                      # catalogue
    (re.compile(r"ll(?=ed$|ing$|er$|ors?$)"), "l"),          # travelled, counsellor
    (re.compile(r"ae"), "e"),                                # mediaeval
    (re.compile(r"(?<=[a-z])oe(?=[a-z])"), "e"),             # foetus
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
                   "programme": "program", "cheque": "check", "towards": "toward"}


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
    fuzzy: bool = False


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


def _find(stream: list[str], target: list[str], start: int) -> tuple[int, bool] | None:
    n = len(target)
    if not n:
        return None
    for i in range(start, len(stream) - n + 1):
        if stream[i:i + n] == target:
            return i, False
    if n >= 4:   # one misprinted word ("The Decalogue ant the natural law")
        for i in range(start, len(stream) - n + 1):
            if sum(a != b for a, b in zip(stream[i:i + n], target)) == 1 \
                    and stream[i] == target[0] and stream[i + n - 1] == target[-1]:
                return i, True
    return None


def _in_order_share(part: list[str], paragraph: list[str]) -> float:
    if not part:
        return 1.0
    from difflib import SequenceMatcher
    blocks = SequenceMatcher(None, part, paragraph, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks) / len(part)


def match_gap(gap: Gap, paragraph_words: list[str] | None) -> GapMatch:
    toks = tokens(gap.source)
    stream = [t.word for t in toks]
    headings: list[HeadingMatch] = []
    inserted: list[tuple[int, dict]] = []
    cursor = 0
    for item in gap.us:
        found = _find(stream, words(item["text"]), cursor)
        if found is None:
            inserted.append((len(headings), item))
            continue
        i, fuzzy = found
        n = len(words(item["text"]))
        headings.append(HeadingMatch(item, i, i + n, fuzzy))
        cursor = i + n

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

def _structural_caps(title: str) -> str:
    """An inserted structural title in the source's style: "SECTION TWO THE ..."."""
    return title.replace(":", "").upper()


def _source_form(match: GapMatch, h: HeadingMatch) -> str:
    """The source's printed text for a matched structural title, lines kept apart."""
    first, last = match.toks[h.start], match.toks[h.end - 1]
    parts = []
    for li in range(first.line, last.line + 1):
        text = match.lines[li].text
        lo = first.start if li == first.line else 0
        hi = last.end if li == last.line else len(text)
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
    elements = []
    if number is not None:
        elements.append({"type": "ref-ccc", "ref_number": number})
    elements.append({"type": "text", "text": text})
    return {"attrs": {}, "elements": elements, "_item": key, "_heading": heading}


def align(source: dict, us: dict) -> Alignment:
    page_nodes = source["page_nodes"]
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

    for after in sorted(all_gaps):
        gap = all_gaps[after]
        paragraph_words = words(us_paragraphs[after]["text"]) if after else None
        match = match_gap(gap, paragraph_words)
        matches.append(match)
        slot = {li: [] for li in range(len(gap.source))}
        consumed = set(match.continuation)
        for li in match.continuation:
            old[after].append(match.free_text[li])
        for h in match.headings:
            key = f"g{after}.{gap.us.index(h.item)}"
            structural = h.item["kind"] == "structure"
            text = _source_form(match, h) if structural else h.item["text"]
            first_line = match.toks[h.start].line
            items[key] = {"kind": h.item["kind"], "text": text,
                          "footnotes": [] if structural else h.item["footnotes"],
                          "fuzzy": h.fuzzy,
                          "source_line": (gap.source[first_line].node_id, gap.source[first_line].index)}
            slot[first_line].append(_paragraph(text, None, key, True))
            for li in range(first_line, match.toks[h.end - 1].line + 1):
                consumed.add(li)
        for li in match.unmatched:
            # Kept as the source prints it, after anything that starts on the line.
            consumed.discard(li)
            slot[li].append(None)
        for order, heading in match.inserted:
            key = f"g{after}.{gap.us.index(heading)}"
            structural = heading["kind"] == "structure"
            text = _structural_caps(heading["text"]) if structural else heading["text"]
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


def _fix(text: str) -> str:
    for wrong, right in TEXT_FIXES:
        text = text.replace(wrong, right)
    return text


def load_us(path: str = US_SOURCE) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)
