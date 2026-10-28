"""Read Catholic Cross Reference's Catechism pages into US-edition items (issue #279, B1).

`scripts/fetch_us_catechism.py` caches the site's search responses; this module turns
their HTML into the items `sources/catechism/us-edition/ccc-us.json` holds. Each page is
a run of `div.heading` (classes `pre`, `head`, `subhead`) and `div.paragraph` blocks in
reading order. A paragraph's text is `div.text`, with footnote markers as
`<a id="fnref:<N>:<k>"><SUP>k</SUP></a>`, and its notes in `div.footnotes > div.note`.
A heading's markers are `fnref:h<X>:<k>`; the site prints those notes among the
footnotes of a later paragraph, as `fn:h<Y>:<k>`.

Part, Section, Chapter and Article titles are not `div.heading`s: the site prints them
only as `div.navigation` breadcrumbs, "Section 2: The Ten Commandments (2052 - 2557)",
and repeats the current ones at the top of every page. They are read as `structure`
items carrying their range; `drop_repeated_structure` keeps only those that open their
range, which a repeat at a page top does not.

The site files a few heading notes under a different id from their markers (the
Prologue's epigraph has markers `h753` and notes `h14`). `HEADING_NOTE_ALIASES` names
each such case, reviewed by hand; `resolve` fails on any marker without a note and any
note without a marker, so a new case cannot slip through.

Parsing is strict: a tag it does not know raises, so a page that differs from the
reviewed ones stops the build instead of losing text.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

# Heading markers whose notes the site files under another heading id. Checked against
# the printed Catechism: the Prologue epigraph's notes 1 to 3 are Jn 17:3, 1 Tim 2:3-4
# and Acts 4:12, which the site attaches to the heading before CCC 14.
HEADING_NOTE_ALIASES: dict[str, str] = {
    "h753": "h14",
}

_INLINE = {"em", "i", "b", "strong", "span", "u", "small"}
_MARKER_ID = re.compile(r"^fnref:((?:h)?\d+):(\d+)$")
_NOTE_ID = re.compile(r"^fn:((?:h)?\d+):(\d+)$")
_RANGE = re.compile(r"^(?P<title>.*?)\s*\((?P<first>\d+)\s*-\s*(?P<last>\d+)\)$", re.S)
_UP_ARROW = "⇡"


class _Text:
    """Builds plain text with whitespace collapsed, and records marker offsets."""

    def __init__(self):
        self.text = ""

    def add(self, s: str) -> None:
        s = re.sub(r"[ \t\r\n ]+", " ", s)
        if not s:
            return
        if (not self.text or self.text.endswith((" ", "\n"))) and s.startswith(" "):
            s = s[1:]
        self.text += s

    def paragraph_break(self) -> None:
        self.text = self.text.rstrip(" ")
        if self.text and not self.text.endswith("\n\n"):
            self.text += "\n\n"

    def offset(self) -> int:
        # A marker sits after the word it follows, never after a trailing space.
        return len(self.text.rstrip(" \n"))

    def done(self) -> str:
        return self.text.strip()


def _walk(node: Tag, out: _Text, markers: list[dict]) -> None:
    for child in node.children:
        if isinstance(child, NavigableString):
            out.add(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name.lower()
        if name == "a":
            marker = _MARKER_ID.match(child.get("id", ""))
            if marker:
                sup = child.find("sup")
                if sup is None or int(sup.get_text(strip=True)) != int(marker.group(2)):
                    raise ValueError(f"marker {child.get('id')} has no matching <SUP>")
                markers.append({"n": int(marker.group(2)), "id": f"{marker.group(1)}:{marker.group(2)}",
                                "at": out.offset()})
            elif child.get_text(strip=True) == _UP_ARROW:
                continue  # the site's "go to this range" link
            else:
                _walk(child, out, markers)  # a scripture or paragraph link: keep its text
        elif name in _INLINE:
            _walk(child, out, markers)
        elif name == "p":
            out.paragraph_break()
            _walk(child, out, markers)
            out.paragraph_break()
        elif name == "br":
            out.add(" ")
        elif name == "sup":
            raise ValueError(f"<SUP> outside a footnote link: {child}")
        else:
            raise ValueError(f"unexpected <{name}> in text: {str(child)[:200]}")


def _plain(node: Tag) -> tuple[str, list[dict]]:
    out, markers = _Text(), []
    _walk(node, out, markers)
    text = out.done()
    for marker in markers:
        marker["at"] = min(marker["at"], len(text))
    return text, markers


def _note_text(node: Tag) -> str:
    text, markers = _plain(node)
    if markers:
        raise ValueError(f"footnote holds a footnote marker: {text[:80]}")
    return text


def parse_page(html: str) -> tuple[list[dict], dict[str, str]]:
    """The items on one page in reading order, and every note it prints by id.

    Items carry unresolved markers, `{"n", "id", "at"}`; `resolve` turns them into
    `{"n", "text", "at"}` once every page is read.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []
    notes: dict[str, str] = {}
    for block in soup.find_all("div", class_=["navigation", "heading", "paragraph"]):
        classes = block.get("class", [])
        if "navigation" in classes:
            text, markers = _plain(block)
            match = _RANGE.match(text)
            if not match or markers:
                raise ValueError(f"navigation without a range: {text[:120]!r}")
            items.append({"kind": "structure", "text": match["title"],
                          "first": int(match["first"]), "last": int(match["last"]),
                          "footnotes": []})
            continue
        if "heading" in classes:
            text, markers = _plain(block)
            style = next((c for c in classes if c != "heading"), None)
            items.append({"kind": "heading", "style": style, "text": text, "footnotes": markers})
            continue
        number = block.find("div", class_="number")
        body = block.find("div", class_="text")
        if number is None or body is None:
            raise ValueError(f"paragraph block without number or text: {block.get('id')}")
        n = int(number.get_text(strip=True))
        if block.get("id") != f"para-{n}":
            raise ValueError(f"paragraph id {block.get('id')} does not match number {n}")
        text, markers = _plain(body)
        items.append({"kind": "paragraph", "n": n, "text": text, "footnotes": markers})
        for note in block.select("div.footnotes > div.note"):
            note_id = _NOTE_ID.match(note.get("id", ""))
            if not note_id:
                raise ValueError(f"note with unexpected id {note.get('id')!r}")
            key = f"{note_id.group(1)}:{note_id.group(2)}"
            if key in notes:
                raise ValueError(f"note {key} printed twice")
            notes[key] = _note_text(note.find("div", class_="text"))
    return items, notes


def drop_repeated_structure(items: list[dict]) -> list[dict]:
    """Keep a `structure` item only where its range opens: the next paragraph is its
    first number. The breadcrumbs repeated at the top of each page fail that test."""
    kept = []
    for i, item in enumerate(items):
        if item["kind"] == "structure":
            following = next((x["n"] for x in items[i + 1:] if x["kind"] == "paragraph"), None)
            if following != item["first"]:
                continue
        kept.append(item)
    return kept


def resolve(items: list[dict], notes: dict[str, str],
            aliases: dict[str, str] = HEADING_NOTE_ALIASES) -> list[dict]:
    """Give every marker its note text. Fails on a marker with no note, or a note no
    marker uses, naming them."""
    used: set[str] = set()
    missing: list[str] = []
    out: list[dict] = []
    for item in items:
        footnotes = []
        for marker in item["footnotes"]:
            owner, k = marker["id"].split(":")
            key = marker["id"] if marker["id"] in notes else f"{aliases.get(owner, owner)}:{k}"
            if key not in notes:
                missing.append(marker["id"])
                continue
            used.add(key)
            footnotes.append({"n": marker["n"], "text": notes[key], "at": marker["at"]})
        out.append({**item, "footnotes": footnotes})
    unused = sorted(set(notes) - used)
    if missing or unused:
        raise ValueError(f"footnotes unresolved: markers without notes {missing[:20]}, "
                         f"notes without markers {unused[:20]}")
    return out
