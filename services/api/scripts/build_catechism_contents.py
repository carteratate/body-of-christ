"""Build the Catechism's stopgap contents tree from the vendored source.

Writes app/catechism_contents.json: the Catechism's headings (Prologue > Part > Section >
Chapter > Article > sub-headings, as `toc_link_tree` in ccc.json nests them) with each
heading's paragraph range. The file holds no chapter keys or anchors; the API points each
heading at the passage holding its first paragraph when it serves /toc
(app/catechism_contents.py), so the tree follows whatever passages are live.

This is a stopgap until the Catechism adapter emits its own tree (#253, after 1.6, #168).
Delete this script, the JSON and app/catechism_contents.py then.

ccc.json is the vendored source the datapipeline reads (nossbigg/catechism-ccc-json, see
datapipeline/SOURCES.md). It is gitignored, so regenerating needs a local copy.

Run from services/api:
    python3 scripts/build_catechism_contents.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "datapipeline" / "sources" / "catechism" / "ccc.json"
OUTPUT = Path(__file__).resolve().parents[1] / "app" / "catechism_contents.json"

# Where the source's heading text is wrong. Section Two of Part One prints only its first
# sub-heading ("I. The Creeds"), which heads the section's own paragraphs (§§185–197); the
# section's title is restored and the sub-heading becomes a child node.
_TITLE_FIXES = {
    "toc-45": "SECTION TWO THE PROFESSION OF THE CHRISTIAN FAITH",
    "toc-207": "SECTION ONE MAN'S VOCATION: LIFE IN THE SPIRIT",
}
_OWN_HEADING = {"toc-45": "I. The Creeds"}
_TEXT_FIXES = (("AGAlN", "AGAIN"),)
_UNNUMBERED = {"toc-44"}

_NUMBER_WORDS = r"ONE|TWO|THREE|FOUR"
_STRUCTURE = (
    ("part", re.compile(rf"^PART ({_NUMBER_WORDS}):?\s*(.*)$", re.I)),
    ("section", re.compile(rf"^SECTION ({_NUMBER_WORDS})\s+(.*)$", re.I)),
    ("chapter", re.compile(rf"^CHAPTER ({_NUMBER_WORDS})\s+(.*)$", re.I)),
    ("article", re.compile(r"^ARTICLE (\d+)\s+(.*)$", re.I)),
    ("paragraph", re.compile(r"^PARAGRAPH (\d+)\.\s*(.*)$", re.I)),
)
_KEEP = {"I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"}
_SMALL = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "of", "on", "or",
          "the", "to", "with", "who", "art"}
_WORD = re.compile(r"[A-Za-z][A-Za-z'’]*")


def _title_case(text: str) -> str:
    """Title-case the words the source prints in capitals: whole headings ("THE SACRAMENT
    OF BAPTISM") or runs inside a mixed one ("... Who Trespass AGAINST US"). Roman
    numerals and "I" stay as they are."""
    letters = [c for c in text if c.isalpha()]
    shouting = bool(letters) and all(c.isupper() for c in letters)
    seen_word = False

    def fix(match: re.Match[str]) -> str:
        nonlocal seen_word
        word, first = match.group(0), not seen_word
        seen_word = True
        capitals = sum(c.isalpha() for c in word) >= 2 and word.upper() == word
        if word in _KEEP or not (shouting or capitals):
            return word
        lower = word.lower()
        # A word that opens the heading, or follows a colon, full stop or opening quote,
        # starts a phrase.
        before = text[:match.start()].rstrip()
        starts = first or before.endswith((":", ".", '"', "“", "-", "—"))
        return lower if lower in _SMALL and not starts else lower[:1].upper() + lower[1:]

    return _WORD.sub(fix, text)


def _classify(node_id: str, raw: str) -> tuple[str, str, str]:
    """(kind, label, short_label) for one heading."""
    text = _TITLE_FIXES.get(node_id, raw)
    for wrong, right in _TEXT_FIXES:
        text = text.replace(wrong, right)
    text = " ".join(text.split())
    if text.upper() == "PROLOGUE":
        return "prologue", "Prologue", "Prologue"
    if text.upper() == "IN BRIEF":
        return "heading", "In Brief", "In Brief"
    for kind, pattern in _STRUCTURE:
        match = pattern.match(text)
        if match:
            number, title = match.group(1), _title_case(match.group(2).strip())
            name = f"{kind.capitalize()} {number.capitalize() if not number.isdigit() else number}"
            return kind, title, f"{name} · {title}"
    label = _title_case(text)
    return "heading", label, label


def _own_paragraphs(page: dict | None) -> list[int]:
    if not page:
        return []
    return [element["ref_number"] for paragraph in page["paragraphs"]
            for element in paragraph["elements"] if element.get("type") == "ref-ccc"]


def _range_label(first: int, last: int) -> str:
    return f"§{first}" if first == last else f"§§{first}–{last}"


def build(source: dict) -> list[dict]:
    toc, pages = source["toc_nodes"], source["page_nodes"]

    def visit(link: dict) -> dict | None:
        node_id = link["id"]
        kind, label, short_label = _classify(node_id, toc[node_id]["text"])
        children = [node for node in map(visit, link["children"]) if node]
        own = _own_paragraphs(pages.get(node_id))
        if own and children:
            # A heading's own paragraphs come before its first sub-heading (Part Two's
            # §§1066–1075 before Section One). They get an entry of their own, so every
            # heading with sub-headings only groups them and every entry that opens a
            # place is a leaf, as in the Summa's tree.
            if max(own) >= children[0]["first"]:
                raise ValueError(f"heading {node_id} has paragraphs after its first sub-heading")
            heading = _OWN_HEADING.get(node_id, "Introduction")
            children.insert(0, {
                "key": f"ccc/{node_id}/own", "kind": "heading", "label": heading,
                "short_label": heading, "first": min(own), "last": max(own),
                "range_label": _range_label(min(own), max(own)), "children": [],
            })
        numbers = own + [n for child in children for n in (child["first"], child["last"])]
        if not numbers:
            # "The Credo" (toc-44) prints the two creeds between §184 and §185 with no
            # paragraph number, and no passage holds it: nothing to point at.
            if node_id not in _UNNUMBERED:
                raise ValueError(f"heading {node_id} ({label!r}) holds no paragraphs")
            return None
        first, last = min(numbers), max(numbers)
        return {"key": f"ccc/{node_id}", "kind": kind, "label": label,
                "short_label": short_label, "first": first, "last": last,
                "range_label": _range_label(first, last), "children": children}

    roots = [node for node in map(visit, source["toc_link_tree"]) if node]
    _check(roots)
    return roots


def _check(roots: list[dict]) -> None:
    """Refuse a tree whose headings are out of order or leave paragraphs uncovered."""
    flat: list[dict] = []

    def walk(nodes: list[dict]) -> None:
        for node in nodes:
            flat.append(node)
            walk(node["children"])

    walk(roots)
    starts = [node["first"] for node in flat]
    if starts != sorted(starts):
        raise ValueError("headings are not in paragraph order")
    if roots[0]["first"] != 1 or roots[-1]["last"] != 2865:
        raise ValueError("the tree does not span §1 to §2865")
    for previous, current in zip(roots, roots[1:]):
        if current["first"] != previous["last"] + 1:
            raise ValueError(f"gap or overlap between {previous['key']} and {current['key']}")
    if len({node["key"] for node in flat}) != len(flat):
        raise ValueError("duplicate keys")


def main() -> None:
    roots = build(json.loads(SOURCE.read_text()))
    OUTPUT.write_text(json.dumps(roots, ensure_ascii=False, indent=1) + "\n")

    def count(nodes: list[dict]) -> int:
        return sum(1 + count(node["children"]) for node in nodes)

    print(f"wrote {count(roots)} headings to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
