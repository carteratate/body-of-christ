from pydantic import BaseModel, Field
from typing import Optional


class SearchFilters(BaseModel):
    collections: list[str]
    translation: str = "CPDV"


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    filters: SearchFilters
    quota: int = Field(default=4, ge=3, le=5)


class ChunkSource(BaseModel):
    collection: str
    document_title: str
    author: Optional[str] = None
    reference: Optional[str] = None
    document_id: str
    position: Optional[int] = None
    anchor: Optional[str] = None
    chapter_key: Optional[str] = None


class ChunkResult(BaseModel):
    chunk_id: str
    content: str
    source: ChunkSource
    reranker_score: Optional[float] = None
    explanation: Optional[str] = None


class SearchDoneResponse(BaseModel):
    search_id: str
    result_count: int


class SearchSummary(BaseModel):
    id: str
    query: str
    filters: Optional[dict] = None
    result_count: Optional[int] = None
    created_at: str


class SearchHistoryResponse(BaseModel):
    searches: list[SearchSummary]
    next_cursor: Optional[str] = None


class SearchResultsResponse(BaseModel):
    search_id: str
    query: str
    results: list[ChunkResult]
    restore_status: str = "complete"
    expected_result_count: int = 0
