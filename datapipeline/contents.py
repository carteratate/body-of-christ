"""Contents trees: checking a document's tree and flattening it for document_contents.

A contents tree is the hierarchy of a document's headings (Part > Question > Article,
for example). It points into the reader's chapters and never defines them, so every
node must open a chapter the document has, and a pre-order walk must meet chapters in
reading order. Issue #250 defines the contract; adapters emit the trees.

`check` runs in the build (publication.CollectionPublicationRunner.build), so a dry run
catches a broken tree before any store is opened.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from model import ContentsNode, Document

KINDS = frozenset({
    "part", "treatise", "section", "chapter", "article", "question", "prologue", "heading",
    "paragraph",   # the Catechism's "Paragraph" units inside an Article of the Creed
})


class ContentsError(ValueError):
    """A document's contents tree breaks the contract; the build must not publish it."""


@dataclass(frozen=True)
class ContentsRow:
    """One document_contents row. `ordinal` is the 1-based pre-order position."""
    ordinal: int
    parent_ordinal: int | None
    depth: int
    node_key: str
    kind: str
    label: str
    short_label: str
    chapter_key: str
    anchor: str | None
    range_label: str | None


def walk(nodes: list[ContentsNode]) -> Iterator[tuple[ContentsNode, ContentsNode | None, int]]:
    """Yield (node, parent, depth) in pre-order, depth 0 for roots."""
    stack: list[tuple[ContentsNode, ContentsNode | None, int]] = [
        (node, None, 0) for node in reversed(nodes)
    ]
    while stack:
        node, parent, depth = stack.pop()
        yield node, parent, depth
        stack.extend((child, node, depth + 1) for child in reversed(node.children))


def flatten(nodes: list[ContentsNode]) -> list[ContentsRow]:
    """The tree as document_contents rows, in pre-order."""
    rows: list[ContentsRow] = []
    ordinals: dict[int, int] = {}
    for node, parent, depth in walk(nodes):
        ordinal = len(rows) + 1
        ordinals[id(node)] = ordinal
        rows.append(ContentsRow(
            ordinal=ordinal,
            parent_ordinal=None if parent is None else ordinals[id(parent)],
            depth=depth,
            node_key=node.key,
            kind=node.kind,
            label=node.label,
            short_label=node.short_label,
            chapter_key=node.chapter_key,
            anchor=node.anchor,
            range_label=node.range_label,
        ))
    return rows


def check(document: Document) -> list[str]:
    """Raise ContentsError if `document.contents` breaks the contract.

    Returns the chapter keys no node opens, in reading order. That is a warning, not
    an error, so a partial tree can ship while an adapter is in progress; the release
    report lists them.
    """
    if document.contents is None:
        return []

    first_position: dict[str, int] = {}
    anchor_chapter: dict[str, str] = {}
    for passage in document.passages:
        if passage.chapter_key not in first_position:
            first_position[passage.chapter_key] = passage.position
        else:
            first_position[passage.chapter_key] = min(
                first_position[passage.chapter_key], passage.position)
        anchor_chapter[passage.anchor] = passage.chapter_key

    problems: list[str] = []
    seen_keys: set[str] = set()
    reached: set[str] = set()
    previous: tuple[int, str] | None = None
    for node, _parent, _depth in walk(document.contents):
        where = f"node {node.key!r}"
        if not node.key:
            problems.append("a node has an empty key")
        elif node.key in seen_keys:
            problems.append(f"{where}: duplicate key")
        seen_keys.add(node.key)
        if node.kind not in KINDS:
            problems.append(f"{where}: unknown kind {node.kind!r}")
        if not node.label.strip() or not node.short_label.strip():
            problems.append(f"{where}: empty label or short_label")
        if node.chapter_key not in first_position:
            problems.append(f"{where}: chapter {node.chapter_key!r} is not in the document")
            continue
        if node.anchor is not None and anchor_chapter.get(node.anchor) != node.chapter_key:
            problems.append(
                f"{where}: anchor {node.anchor!r} is not a passage in chapter "
                f"{node.chapter_key!r}")
        reached.add(node.chapter_key)
        position = first_position[node.chapter_key]
        if previous is not None and position < previous[0]:
            problems.append(
                f"{where}: chapter {node.chapter_key!r} comes before chapter "
                f"{previous[1]!r} in reading order")
        previous = (position, node.chapter_key)

    if problems:
        shown = "; ".join(problems[:10])
        more = f" (and {len(problems) - 10} more)" if len(problems) > 10 else ""
        raise ContentsError(
            f"contents tree of document {document.id} ({document.title!r}): {shown}{more}")

    return sorted((key for key in first_position if key not in reached),
                  key=first_position.__getitem__)
