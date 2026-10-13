"""A stopgap Catechism contents tree, built from the vendored source (issue #255).

The Catechism adapter will emit its own tree (Prologue > Part > Section > Chapter >
Article > sub-headings, #253) once the 1.6 adapter rework (#168) is published. Until a
stored tree exists, /toc serves the headings in catechism_contents.json, which
scripts/build_catechism_contents.py generates from ccc.json. Delete this module, the JSON,
the script and the call in routes/documents.py once the Catechism is published with a
stored tree.

The JSON holds each heading's paragraph range, not chapter keys or anchors. Every
Catechism passage lists the paragraph numbers it holds (`metadata.ccc_paragraphs`), so a
heading opens the first passage, in reading order, that holds its first paragraph. Today
every heading begins a passage. If a heading's paragraph is in no passage, or the
headings would meet chapters out of reading order, the tree is not served and the reader
keeps the flat chapter list.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

from app.models.documents import ContentsNode

logger = logging.getLogger(__name__)

_SOURCE = Path(__file__).with_name("catechism_contents.json")


@lru_cache(maxsize=1)
def _headings() -> list[dict]:
    return json.loads(_SOURCE.read_text())


def catechism_contents(
    passages: list[tuple[str, str, list[int] | None]],
    chapter_keys: list[str],
    headings: list[dict] | None = None,
) -> list[ContentsNode] | None:
    """The tree for (chapter_key, anchor, ccc_paragraphs) passages in reading order."""
    try:
        return _build(passages, chapter_keys, headings if headings is not None else _headings())
    except (LookupError, TypeError, ValueError) as exc:
        # A stopgap only ever degrades to the flat list, whatever the passages hold.
        logger.warning("catechism contents tree not served (%s); serving chapters only", exc)
        return None


def _build(passages, chapter_keys, headings) -> list[ContentsNode] | None:
    place: dict[int, tuple[int, str, str]] = {}
    for index, (chapter_key, anchor, paragraphs) in enumerate(passages):
        for number in paragraphs or []:
            place.setdefault(int(number), (index, chapter_key, anchor))
    order: dict[str, int] = {}
    for position, key in enumerate(chapter_keys):
        order.setdefault(key, position)

    # Headings must meet chapters, and passages within them, in reading order. The
    # Catechism's chapters are 100-paragraph buckets, so chapter order alone is coarse.
    previous = (-1, -1)

    def build(node: dict) -> ContentsNode:
        nonlocal previous
        target = place.get(node["first"])
        if target is None or target[1] not in order:
            raise LookupError(f"no passage holds §{node['first']} ({node['key']})")
        index, chapter_key, anchor = target
        here = (order[chapter_key], index)
        if here < previous:
            raise LookupError(f"{node['key']} is out of reading order")
        previous = here
        return ContentsNode(
            key=node["key"], kind=node["kind"], label=node["label"],
            short_label=node["short_label"], chapter_key=chapter_key, anchor=anchor,
            range_label=node["range_label"],
            children=[build(child) for child in node["children"]],
        )

    return [build(node) for node in headings] or None
