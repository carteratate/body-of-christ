from pydantic import BaseModel, Field
from typing import Literal, Optional


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


class BookmarkChunk(BaseModel):
    content: str
    source: BookmarkSource


class BookmarkResponse(BaseModel):
    id: str
    chunk_id: str
    created_at: str
    note: Optional[str] = None
    chunk: Optional[BookmarkChunk] = None


class BookmarkListResponse(BaseModel):
    bookmarks: list[BookmarkResponse]
