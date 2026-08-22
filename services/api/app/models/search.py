from pydantic import BaseModel, Field
from typing import Literal, Optional


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
    # The passage's role in its document ("Objection 1", "I answer that", "Can. 6 §2").
    # Exposed so the UI can mark a passage the author states in order to refute — 39.3%
    # of the Summa — rather than presenting it as his teaching. Optional: most
    # collections have no such structure, and it is null for every pre-existing row.
    unit_label: Optional[str] = None


class ContextPart(BaseModel):
    """One passage attached to a matched Summa result to make it intelligible.

    Presentation only — not a search result. No score, not persisted to `retrievals`,
    not bookmarkable: the matched passage is what the user addressed.
    """

    content: str
    reference: Optional[str] = None
    unit_label: Optional[str] = None
    anchor: Optional[str] = None


class AttachedContext(BaseModel):
    """What completes a matched Summa passage, and where it belongs on the card.

    relation = "answered_by": the match is an objection Aquinas refutes; `parts` are his
      determination and render BELOW it. 109 of 3,120 articles split the determination
      across parts, which arrive in document order and are shown in full.
    relation = "answers": the match is a reply, and `parts` is the single objection it
      answers, rendering ABOVE it — a reply opens mid-thought and reads no other way.
    """

    # Literal, not str: these two values are the wire contract the frontend switches
    # on to decide whether the attachment renders above or below the match, so an
    # unknown value must fail here rather than reach a renderer that cannot place it.
    relation: Literal["answered_by", "answers"]
    parts: list[ContextPart]


class ChunkResult(BaseModel):
    chunk_id: str
    content: str
    source: ChunkSource
    reranker_score: Optional[float] = None
    explanation: Optional[str] = None
    # The passage completing this result, or None. See AttachedContext.
    context: Optional[AttachedContext] = None


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
    filters: Optional[dict] = None
    results: list[ChunkResult]
    restore_status: str = "complete"
    expected_result_count: int = 0
