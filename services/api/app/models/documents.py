from pydantic import BaseModel
from typing import Optional


class DocumentResponse(BaseModel):
    id: str
    collection: str
    title: str
    author: Optional[str] = None
    year: Optional[int] = None
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
