from pydantic import BaseModel, Field
from typing import Literal, Optional

from app.models.corpus import (DocumentFacts, PassageCard, PassageStatus, Redirect,
                               Tombstone)
from app.rag.outcomes import CollectionOutcome, PersistedSearchOutcome


SearchQuota = Literal[3, 4, 5, 10]


class ScopeSelection(BaseModel):
    """What to search inside one collection (5.1a). An absent list is every value."""
    genres: Optional[list[str]] = Field(default=None, max_length=50)
    issuers: Optional[list[str]] = Field(default=None, max_length=100)


class SearchFilters(BaseModel):
    collections: list[str]
    translation: str = "CPDV"
    # Per collection; absent is the whole of every collection.
    scopes: Optional[dict[str, ScopeSelection]] = None

    def scope_filters(self) -> dict[str, dict] | None:
        if not self.scopes:
            return None
        return {col: sel.model_dump() for col, sel in self.scopes.items()}


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    filters: SearchFilters
    quota: SearchQuota = 4


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
    # "excerpt": the document's rights are not cleared, so clients link to
    # `source_url` instead of the reader (issue #265).
    reader_access: Literal["full", "excerpt"] = "full"
    source_url: Optional[str] = None
    # The rights holder's credit line, shown right after the passage (excerpt-only).
    source_credit: Optional[str] = None
    # Corpus cleanup 2.4a, from migration 0042; absent on a database without it.
    facts: Optional[DocumentFacts] = None
    language: Optional[str] = None        # ISO 639 code; None means English
    passage_note: Optional[str] = None
    passage_author: Optional[str] = None  # a quoted author, shown instead of `author`
    # "rejected": the passage states a position its document rejects (2.4d). The card
    # shows `unit_label` above the text.
    voice: Optional[Literal["rejected"]] = None
    # From the passage's metadata (2.4f), shown when the passage is opened. "ocr": the
    # text came from a scanned edition (1.2f). "unofficial_english": a canon in the
    # L'Osservatore Romano English, whose Latin at `official_latin_url` is official
    # (1.5b). The live event sends them only when set.
    text_source: Optional[Literal["ocr"]] = None
    text_status: Optional[Literal["unofficial_english"]] = None
    official_latin_url: Optional[str] = None
    # The notes under the opened passage (4.4, `app/card_notes.py`), only for a passage
    # whose document a 4.4 publish wrote. Absent, clients show the fields above as before.
    card: Optional[PassageCard] = None


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


class Footnote(BaseModel):
    """One of a passage's footnotes (issue #279): its own number, its text, and the
    character offset in the passage's `content` where its marker sits."""

    n: int
    text: str
    at: int


class PassageHeading(BaseModel):
    """A heading or epigraph inside a passage's text (issue #445): the character offsets
    of its paragraph in `content`, its role, its level (1 to 3, headings only), and
    whether it is a level label printed before its title (`pairs_next`) or repeats its
    chapter label (`chapter_title`). See app/headings.py."""

    at: int
    end: int
    role: Literal["heading", "epigraph"]
    level: Optional[Literal[1, 2, 3]] = None
    pairs_next: bool = False
    chapter_title: bool = False


class ChunkResult(BaseModel):
    chunk_id: str
    content: str
    source: ChunkSource
    reranker_score: Optional[float] = None
    explanation: Optional[str] = None
    # The passage completing this result, or None. See AttachedContext.
    context: Optional[AttachedContext] = None
    # The passage's footnotes (issue #279); [] for every passage without them.
    footnotes: list[Footnote] = Field(default_factory=list)
    # The headings marked inside the passage (issue #445); [] for an unmarked passage.
    headings: list[PassageHeading] = Field(default_factory=list)
    # A saved result whose passage left the corpus (2.4a). "removed": `tombstone` says
    # why and `content` is empty. "moved": `redirect` says where, and `content` and
    # `source` are the passage it moved to.
    status: PassageStatus = "current"
    tombstone: Optional[Tombstone] = None
    redirect: Optional[Redirect] = None


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
    delivery_outcome: Optional[Literal["complete", "underfilled", "minimum_floor"]] = None
    outcome: Optional[PersistedSearchOutcome] = None
    collection_outcomes: Optional[dict[str, CollectionOutcome]] = None
