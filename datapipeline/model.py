"""Canonical passage + document dataclasses emitted by the parse stage.

One Passage is the unit shared by the reader (Supabase) and search (Qdrant),
per the passage contract spec §3.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Passage:
    content: str          # clean reading text (no breadcrumb headers, no (1/3))
    reference: str        # clean human citation
    anchor: str           # stable deep-link key, unique within a document
    chapter_key: str      # groups passages into a reader chapter-section
    chapter_label: str    # display heading for that section
    position: int         # global 0-based order within the document
    unit_label: str | None = None   # inline ordinal (verse no., "Reply to Objection 2")
    metadata: dict | None = None


@dataclass
class ContentsNode:
    """One heading in a document's contents tree (issue #250).

    The tree points into the reader's chapters; it never defines them. Checked by
    contents.check before anything is written.
    """
    key: str              # unique within the document and stable across builds
    kind: str             # one of contents.KINDS, e.g. "part", "question", "article"
    label: str            # the full heading
    short_label: str      # what the tree row shows, e.g. "Art. 4 · The Sacrament of Penance"
    chapter_key: str      # the chapter it opens; a grouping node uses its first descendant's
    anchor: str | None = None        # a passage in that chapter to scroll to
    range_label: str | None = None   # e.g. "§§1422–1498", "Qq. 2–26", "10 articles"
    children: list[ContentsNode] = field(default_factory=list)


@dataclass
class Document:
    id: str               # deterministic document_id (identity.document_id)
    collection: str
    title: str
    author: str | None = None
    year: int | None = None
    translation: str = ""
    metadata: dict | None = None
    passages: list[Passage] = field(default_factory=list)
    contents: list[ContentsNode] | None = None   # tree roots; None = no contents tree
