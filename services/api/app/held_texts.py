"""Held texts in their place (corpus-cleanup 4.3, issue #394).

A held text is one text of a document that the republish holds back (a council's gap
text, a run of a papal document's paragraphs awaiting permission). The datapipeline's
stage writes each document's list into `documents.metadata.held_texts`, in reading
order: `{key, label, heading, after_anchor, after_chapter_key, url}`. `/toc` sends the
list with each entry's link resolved; `/documents/{id}` and `/sources` send only
`held_count`; and no `metadata` the API returns carries the list.

A held text has no passage behind it, so nothing ties the list to the chunks once it is
written. `/toc` checks it the way `_contents_tree` checks a contents tree, and drops a
stale list whole rather than send readers to the wrong place.
"""
from __future__ import annotations

import logging

from app.models.documents import HeldText

logger = logging.getLogger(__name__)

KEY = "held_texts"


def _http_url(value) -> str | None:
    return value if isinstance(value, str) and value.startswith(("https://", "http://")) else None


def stored(metadata) -> list[dict]:
    """The document's stored entries; empty when it has none, or a malformed list."""
    entries = metadata.get(KEY) if isinstance(metadata, dict) else None
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        return []
    return entries


def held_count(metadata) -> int:
    return len(stored(metadata))


def public_metadata(metadata):
    """`metadata` as the API returns it: without the held-text list, which `/toc` sends
    once, resolved."""
    if isinstance(metadata, dict) and KEY in metadata:
        return {k: v for k, v in metadata.items() if k != KEY}
    return metadata


def link(entry: dict, metadata: dict) -> str | None:
    """Where a held text is read: the entry's own link, else the document's
    `held_text_url`, else its `url` (the rule `corpus_lifecycle.read_elsewhere_url`
    gives the held passages' tombstones)."""
    return (_http_url(entry.get("url")) or _http_url(metadata.get("held_text_url"))
            or _http_url(metadata.get("url")))


def anchors_to_check(metadata) -> list[str]:
    return sorted({e["after_anchor"] for e in stored(metadata)
                   if isinstance(e.get("after_anchor"), str)})


def resolve(doc_id, metadata, chapter_keys: list[str],
            anchor_chapters: dict[str, str]) -> list[HeldText]:
    """The entries `/toc` returns, or [] when the list is stale.

    Current means every entry names a heading and a label, every `after_anchor` is a
    visible passage of the chapter its `after_chapter_key` names, that chapter is in
    `chapter_keys`, and the entries meet the chapters in reading order. Otherwise the
    reader shows chapters only. `anchor_chapters` maps each visible `after_anchor` to
    its chapter. An entry with no link at all is left out, and logged."""
    entries = stored(metadata)
    if not entries:
        return []
    order: dict[str, int] = {}
    for index, key in enumerate(chapter_keys):
        order.setdefault(key, index)
    previous = -1
    problem = None
    for e in entries:
        anchor, chapter = e.get("after_anchor"), e.get("after_chapter_key")
        if not all(isinstance(e.get(k), str) and e[k].strip() for k in ("key", "label", "heading")):
            problem = f"entry {e.get('key')!r} lacks a key, label or heading"
        elif not all(e.get(k) is None or isinstance(e[k], str)
                     for k in ("after_anchor", "after_chapter_key")):
            problem = f"entry {e['key']!r} has a malformed place"
        elif anchor is None:
            index = -1
            if chapter is not None:
                problem = f"entry {e['key']!r} names a chapter but no passage"
        elif order.get(chapter) is None:
            problem = f"entry {e['key']!r} follows missing chapter {chapter!r}"
        elif anchor_chapters.get(anchor) != chapter:
            problem = f"entry {e['key']!r} follows missing passage {anchor!r}"
        else:
            index = order[chapter]
        if problem is None and index < previous:
            problem = f"entry {e['key']!r} is out of reading order"
        if problem:
            logger.warning("held texts of document %s are stale (%s); serving chapters only",
                           doc_id, problem)
            return []
        previous = index

    out = []
    for e in entries:
        url = link(e, metadata)
        if url is None:
            logger.warning("held text %s of document %s has no link; left out",
                           e["key"], doc_id)
            continue
        out.append(HeldText(key=e["key"], label=e["label"], heading=e["heading"],
                            after_anchor=e.get("after_anchor"),
                            after_chapter_key=e.get("after_chapter_key"), url=url))
    return out
