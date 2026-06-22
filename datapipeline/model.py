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
class Document:
    id: str               # deterministic document_id (identity.document_id)
    collection: str
    title: str
    author: str | None = None
    year: int | None = None
    translation: str = ""
    metadata: dict | None = None
    passages: list[Passage] = field(default_factory=list)
