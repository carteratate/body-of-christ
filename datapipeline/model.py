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
    # Fields an adapter may set; a passage-registry override wins (2.1, D11).
    work_key: str | None = None     # the Work of a container document this belongs to (D6)
    searchable: bool = True
    language: str | None = None     # ISO 639 code; None means English
    passage_author: str | None = None
    voice: str | None = None        # None, or "rejected": a position the document rejects
    superseded_by_anchor: str | None = None   # a history passage names its current one
    # Build-time only, never written: for a split piece, the source units whose text starts
    # in it, in order, each as (locator, offset in content); one opening inside a unit
    # lists that unit first at offset 0. Empty for a whole unit, which holds them all.
    # The registry uses it to find the piece that holds a unit.
    source_units: tuple[tuple[str, int], ...] = ()


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


@dataclass(frozen=True)
class Work:
    """One work inside a container document (D6). Which passages belong to it is
    recorded per passage, as `Passage.work_key`, never as an anchor or position range."""
    work_key: str
    ordinal: int
    title: str
    author: str | None = None
    certainty: str | None = None     # genuine, disputed, pseudonymous or anonymous
    attribution_note: str | None = None
    notes: str | None = None
    date_display: str | None = None
    year: int | None = None
    genre: str | None = None         # one of registry.genres.ALL_GENRES
    clavis_ref: str | None = None


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
    works: list[Work] = field(default_factory=list)
