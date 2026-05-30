from pydantic import BaseModel
from typing import Optional


class BookmarkCreate(BaseModel):
    chunk_id: str


class BookmarkSource(BaseModel):
    collection: str
    document_title: str
    author: Optional[str] = None
    reference: Optional[str] = None


class BookmarkChunk(BaseModel):
    content: str
    source: BookmarkSource


class BookmarkResponse(BaseModel):
    id: str
    chunk_id: str
    created_at: str
    chunk: Optional[BookmarkChunk] = None


class BookmarkListResponse(BaseModel):
    bookmarks: list[BookmarkResponse]
