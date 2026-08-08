from pydantic import BaseModel, Field
from typing import Optional


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
