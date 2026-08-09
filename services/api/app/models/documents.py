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


class TocResponse(BaseModel):
    document: DocumentResponse
    chapters: list[TocEntry]
