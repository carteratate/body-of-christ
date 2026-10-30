"""Read Catholic Cross Reference's Catechism pages into US-edition items (issue #279, B1).

`scripts/fetch_us_catechism.py` caches the site's search responses; this module turns
their HTML into the items `sources/catechism/us-edition/ccc-us.json` holds. Each page is
a run of `div.heading` (classes `pre`, `head`, `subhead`) and `div.paragraph` blocks in
reading order. A paragraph's text is `div.text`, with footnote markers as
`<a id="fnref:<N>:<k>"><SUP>k</SUP></a>`, and its notes in `div.footnotes > div.note`.
A heading's markers are `fnref:h<X>:<k>`; the site prints those notes among the
footnotes of a later paragraph, as `fn:h<Y>:<k>`.

Part, Section, Chapter and Article titles are not `div.heading`s: the site prints them
only as `div.navigation` breadcrumbs, "Section 2: The Ten Commandments (2052 - 2557)".
It reprints every open breadcrumb and heading at the top of each page, and some
epigraphs again where a new article starts, so every structure item and heading carries
the range it heads (a heading's from its "⇡" link), and `drop_repeated_structure` keeps
only those whose range opens at the next paragraph. That also drops the one heading the
site prints twice in a row ("Prayer to Jesus" before CCC 2665 and again before 2666).

The site files most heading notes under a different id from their markers: the
Prologue's epigraph has markers `h753:1-3` and notes `h14:1-3`, the First Commandment's
`h559:3-4` and `h2112:3-4`. The note numbers always agree and the notes always print
later. `resolve` gives each heading's markers the nearest later unused note group with
exactly the same numbers; a group left over must repeat a used one word for word (the
site prints a few twice). Anything else fails, so a new case cannot slip through.

Parsing is strict: a tag it does not know raises, so a page that differs from the
reviewed ones stops the build instead of losing text.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup, NavigableString, Tag

_INLINE = {"em", "i", "b", "strong", "span", "u", "small"}
# Lists print one item per line: "- " for a bullet, "1. " for a numbered item, as the
# printed Catechism does (ccc.json writes the bullets inline, "- orally ...").
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

    def line_break(self) -> None:
        self.text = self.text.rstrip(" ")
        if self.text and not self.text.endswith("\n"):
            self.text += "\n"

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
                continue  # the site's "go to this range" link (read by parse_page)
            else:
                _walk(child, out, markers)  # a scripture or paragraph link: keep its text
        elif name in _INLINE:
            _walk(child, out, markers)
        elif name == "p":
            out.paragraph_break()
            _walk(child, out, markers)
            out.paragraph_break()
        elif name == "br":
            out.line_break()                 # a line of verse or of a prayer
        elif name in ("ul", "ol"):
            number = int(child.get("start", 1))
            for li in child.find_all("li", recursive=False):
                out.line_break()
                out.add("- " if name == "ul" else f"{number}. ")
                number += 1
                _walk(li, out, markers)
            out.line_break()
        elif name == "sup":
            if child.get_text(strip=True).isdigit():
                raise ValueError(f"numbered <SUP> outside a footnote link: {child}")
            _walk(child, out, markers)       # a typographic superscript ("nº")
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
            link = next((a for a in block.find_all("a") if a.get_text(strip=True) == _UP_ARROW), None)
            span = re.search(r"#!/search/(\d+)(?:-(\d+))?", link.get("href", "")) if link else None
            if span is None:
                raise ValueError(f"heading without its range link: {text[:80]!r}")
            items.append({"kind": "heading", "style": style, "text": text, "footnotes": markers,
                          "first": int(span.group(1)), "last": int(span.group(2) or span.group(1))})
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
            printed_with = n
            note_id = _NOTE_ID.match(note.get("id", ""))
            if not note_id:
                raise ValueError(f"note with unexpected id {note.get('id')!r}")
            key = f"{note_id.group(1)}:{note_id.group(2)}"
            if key in notes:
                raise ValueError(f"note {key} printed twice")
            notes[key] = {"text": _note_text(note.find("div", class_="text")), "printed_with": printed_with}
    return items, notes


def drop_repeated_structure(items: list[dict]) -> list[dict]:
    """Keep a structure item or heading only where its range opens: the next paragraph
    is its first number. What the site reprints (page tops, article starts) fails it."""
    kept = []
    for i, item in enumerate(items):
        if item["kind"] in ("structure", "heading"):
            following = next((x["n"] for x in items[i + 1:] if x["kind"] == "paragraph"), None)
            if following != item["first"]:
                continue
        kept.append(item)
    return kept


def resolve(items: list[dict], notes: dict[str, dict]) -> list[dict]:
    """Give every marker its note text, returning the items.

    A paragraph's markers `N:k` take note `N:k`. A heading's markers take, as a group,
    the nearest unused heading-note group printed at or after the paragraph the heading
    opens whose note numbers are exactly the markers'. Fails on a marker left without a
    note, or a note group left over that does not repeat a used group word for word.
    """
    groups: dict[str, dict[int, dict]] = {}
    for key, note in notes.items():
        owner, k = key.split(":")
        groups.setdefault(owner, {})[int(k)] = note
    used: set[str] = set()
    missing: list[str] = []
    out: list[dict] = []
    for item in items:
        markers = item["footnotes"]
        chosen: dict[str, dict] = {}
        if item["kind"] == "heading" and markers:
            numbers = {m["n"] for m in markers}
            owner = markers[0]["id"].split(":")[0]
            if owner in groups and set(groups[owner]) == numbers and owner not in used:
                pick = owner
            else:
                candidates = sorted(
                    (min(note["printed_with"] for note in g.values()), name)
                    for name, g in groups.items()
                    if name.startswith("h") and name not in used and set(g) == numbers
                    and min(note["printed_with"] for note in g.values()) >= item["first"])
                pick = candidates[0][1] if candidates else None
            if pick is not None:
                used.add(pick)
                chosen = {m["id"]: groups[pick][m["n"]] for m in markers}
        else:
            for m in markers:
                if m["id"] in notes:
                    used.add(m["id"].split(":")[0] if m["id"].startswith("h") else m["id"])
                    chosen[m["id"]] = notes[m["id"]]
        footnotes = []
        for m in markers:
            if m["id"] not in chosen:
                missing.append(m["id"])
                continue
            footnotes.append({"n": m["n"], "text": chosen[m["id"]]["text"], "at": m["at"]})
        out.append({**item, "footnotes": footnotes})

    # A note no marker used must repeat a placed note word for word: the site prints a
    # few twice (heading-note groups, and CCC 1675's note 181 again under 1676).
    placed = {(f["n"], f["text"]) for item in out for f in item["footnotes"]}
    leftover = []
    for key, note in notes.items():
        owner = key.split(":")[0]
        if (owner if owner.startswith("h") else key) in used:
            continue
        if (int(key.split(":")[1]), note["text"]) not in placed:
            leftover.append(key)
    if missing or leftover:
        raise ValueError(f"footnotes unresolved: markers without notes {missing[:20]}, "
                         f"notes without markers {leftover[:20]}")
    return out
