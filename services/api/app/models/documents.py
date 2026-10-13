from pydantic import BaseModel
from typing import Optional


class DocumentResponse(BaseModel):
    id: str
    collection: str
    title: str
    author: Optional[str] = None
    year: Optional[int] = None
    translation: Optional[str] = None
    metadata: Optional[dict] = None
    chunk_count: int


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


class ReaderChapter(BaseModel):
    document: DocumentResponse
    chapter_key: str
    chapter_label: str
    passages: list[ReaderPassage]
    prev_chapter_key: Optional[str] = None
    next_chapter_key: Optional[str] = None
    highlight_anchor: Optional[str] = None


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
