from pydantic import BaseModel, Field
from typing import Optional


class ReadingProgressUpdate(BaseModel):
    chapter_key: str = Field(..., min_length=1, max_length=500)
    anchor: Optional[str] = Field(default=None, min_length=1, max_length=500)


class ReadingProgressItem(BaseModel):
    document_id: str
    chapter_key: str
    chapter_label: str
    anchor: Optional[str] = None
    updated_at: str
    collection: str
    document_title: str
    author: Optional[str] = None


class ReadingProgressListResponse(BaseModel):
    items: list[ReadingProgressItem]
