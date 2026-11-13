from pydantic import BaseModel, Field
from typing import Literal, Optional

from app.models.corpus import DocumentFacts, PassageStatus, Redirect, Tombstone
from app.models.search import Footnote


class BookmarkCreate(BaseModel):
    chunk_id: str


class BookmarkNoteUpdate(BaseModel):
    note: Optional[str] = Field(None, max_length=3000)


class BookmarkSource(BaseModel):
    collection: str
    document_title: str
    author: Optional[str] = None
    reference: Optional[str] = None
    document_id: str
    anchor: Optional[str] = None
    chapter_key: Optional[str] = None
    # Same field, same reason, as ChunkSource.unit_label: a bookmarked Summa objection
    # renders as ordinary teaching without it, and a bookmark is the longest-lived
    # surface in the product.
    unit_label: Optional[str] = None
    # Same as ChunkSource: an excerpt-only document links to its source (issue #265).
    reader_access: Literal["full", "excerpt"] = "full"
    source_url: Optional[str] = None
    # The rights holder's credit line, shown right after the passage (excerpt-only).
    source_credit: Optional[str] = None
    # Same as ChunkSource (2.4a).
    facts: Optional[DocumentFacts] = None
    language: Optional[str] = None
    passage_note: Optional[str] = None
    passage_author: Optional[str] = None
    voice: Optional[Literal["rejected"]] = None  # same as ChunkSource (2.4d)
    # Same as ChunkSource (2.4f).
    text_source: Optional[Literal["ocr"]] = None
    text_status: Optional[Literal["unofficial_english"]] = None
    official_latin_url: Optional[str] = None


class BookmarkChunk(BaseModel):
    content: str
    source: BookmarkSource
    # Same as ChunkResult.footnotes (issue #279).
    footnotes: list[Footnote] = Field(default_factory=list)


class BookmarkResponse(BaseModel):
    id: str
    chunk_id: str
    created_at: str
    note: Optional[str] = None
    chunk: Optional[BookmarkChunk] = None
    # Same as ChunkResult (2.4a); the note is kept in every state.
    status: PassageStatus = "current"
    tombstone: Optional[Tombstone] = None
    redirect: Optional[Redirect] = None


class BookmarkListResponse(BaseModel):
    bookmarks: list[BookmarkResponse]
