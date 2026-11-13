from pydantic import BaseModel
from typing import Literal, Optional

from app.models.corpus import DocumentFacts, RedirectedFrom, WorkInfo


class DocumentResponse(BaseModel):
    id: str
    collection: str
    title: str
    author: Optional[str] = None
    year: Optional[int] = None
    translation: Optional[str] = None
    metadata: Optional[dict] = None
    chunk_count: int
    # "excerpt": the rights are not cleared, so /reader and /toc refuse this document
    # with 403 reader_restricted and clients link to `source_url` (issue #265).
    reader_access: Literal["full", "excerpt"] = "full"
    # The official edition, for an excerpt-only document; None otherwise.
    source_url: Optional[str] = None
    # Corpus cleanup 2.4a, from migration 0042. A retired document is never returned
    # here (410 or 404 instead), so `status` is always "current".
    facts: Optional[DocumentFacts] = None
    works: list[WorkInfo] = []
    status: Literal["current"] = "current"


class ReaderChunk(BaseModel):
    id: str
    position: int
    reference: Optional[str] = None
    content: str


class ReaderResponse(BaseModel):
    document: DocumentResponse
    chunks: list[ReaderChunk]
    highlight_chunk_id: str
    # Pivot IDs for non-overlapping prev/next page navigation.
    # None means there is no previous/next page.
    prev_nav_chunk_id: Optional[str] = None
    next_nav_chunk_id: Optional[str] = None


# ── Passage contract models (canonical-passage reader) ───────────────────────


class ReaderPassage(BaseModel):
    id: str
    anchor: str
    chapter_key: str
    chapter_label: str
    unit_label: Optional[str] = None
    reference: Optional[str] = None
    content: str
    # Corpus cleanup 2.4a, from migration 0042.
    language: Optional[str] = None
    note: Optional[str] = None
    work_key: Optional[str] = None
    passage_author: Optional[str] = None
    # "rejected": a position the document states in order to reject it (2.4d). The
    # reader shows `unit_label` above the text.
    voice: Optional[Literal["rejected"]] = None
    # Set only on a history passage (rule F): the ID of the current passage that
    # replaced it. Shown as earlier text beside that passage, never in the flow.
    superseded_by: Optional[str] = None


class ReaderChapter(BaseModel):
    document: DocumentResponse
    chapter_key: str
    chapter_label: str
    passages: list[ReaderPassage]
    prev_chapter_key: Optional[str] = None
    next_chapter_key: Optional[str] = None
    highlight_anchor: Optional[str] = None
    # The anchor or chapter the request named, when it had moved and the API followed
    # its redirect (2.4a). `document` is then where it moved to, which may be another
    # document, and `highlight_anchor` is its new anchor.
    redirected_from: Optional[RedirectedFrom] = None


class TocEntry(BaseModel):
    chapter_key: str
    chapter_label: str


class ContentsNode(BaseModel):
    """One heading of a document's contents tree (migration 0040, issue #250). Opening
    it loads `chapter_key` and, when set, scrolls to the passage `anchor`."""
    key: str
    kind: str
    label: str
    short_label: str
    chapter_key: str
    anchor: Optional[str] = None
    range_label: Optional[str] = None
    children: list["ContentsNode"] = []


class TocResponse(BaseModel):
    document: DocumentResponse
    chapters: list[TocEntry]
    # The contents tree's roots, or None when the document has no current tree; the
    # reader then navigates by `chapters` alone.
    contents: Optional[list[ContentsNode]] = None
