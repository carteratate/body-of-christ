from pydantic import BaseModel
from typing import Literal, Optional

from app.models.corpus import DocumentFacts, OverviewNote, RedirectedFrom, WorkInfo


class DocumentResponse(BaseModel):
    id: str
    collection: str
    title: str
    author: Optional[str] = None
    year: Optional[int] = None
    translation: Optional[str] = None
    metadata: Optional[dict] = None
    chunk_count: int
    # "excerpt": the rights are not cleared, so /reader and /toc refuse this document
    # with 403 reader_restricted and clients link to `source_url` (issue #265).
    reader_access: Literal["full", "excerpt"] = "full"
    # The official edition, for an excerpt-only document; None otherwise.
    source_url: Optional[str] = None
    # Corpus cleanup 2.4a, from migration 0042. A retired document is never returned
    # here (410 or 404 instead), so `status` is always "current".
    facts: Optional[DocumentFacts] = None
    works: list[WorkInfo] = []
    status: Literal["current"] = "current"
    # Texts of this document held back for now and read online instead (4.3). `/toc`
    # lists them; `metadata` never carries them.
    held_count: int = 0
    # The document-wide notes (4.4, `card_notes.overview_notes`), which the overview
    # shows in place of the facts' notes. None for a document from before 4.4.
    overview_notes: Optional[list[OverviewNote]] = None


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
    # Corpus cleanup 2.4a, from migration 0042.
    language: Optional[str] = None
    note: Optional[str] = None
    work_key: Optional[str] = None
    passage_author: Optional[str] = None
    # "rejected": a position the document states in order to reject it (2.4d). The
    # reader shows `unit_label` above the text.
    voice: Optional[Literal["rejected"]] = None
    # Same as ChunkSource (2.4f): scanned edition, unofficial English, the Latin's link.
    text_source: Optional[Literal["ocr"]] = None
    text_status: Optional[Literal["unofficial_english"]] = None
    official_latin_url: Optional[str] = None
    # Set only on a history passage (rule F): the ID of the current passage that
    # replaced it. Shown as earlier text beside that passage, never in the flow.
    superseded_by: Optional[str] = None


class ReaderChapter(BaseModel):
    document: DocumentResponse
    chapter_key: str
    chapter_label: str
    passages: list[ReaderPassage]
    prev_chapter_key: Optional[str] = None
    next_chapter_key: Optional[str] = None
    highlight_anchor: Optional[str] = None
    # The anchor or chapter the request named, when it had moved and the API followed
    # its redirect (2.4a). `document` is then where it moved to, which may be another
    # document, and `highlight_anchor` is its new anchor.
    redirected_from: Optional[RedirectedFrom] = None


class TocEntry(BaseModel):
    chapter_key: str
    chapter_label: str


class ContentsNode(BaseModel):
    """One heading of a document's contents tree (migration 0040, issue #250). Opening
    it loads `chapter_key` and, when set, scrolls to the passage `anchor`."""
    key: str
    kind: str
    label: str
    short_label: str
    chapter_key: str
    anchor: Optional[str] = None
    range_label: Optional[str] = None
    children: list["ContentsNode"] = []


class HeldText(BaseModel):
    """A text of the document that is not on TheoCorpus at present (corpus cleanup 4.3):
    a council's gap text, or a run of paragraphs awaiting permission. It has no passage
    and no text here; `url` opens it online. It follows the passage `after_anchor`, in
    chapter `after_chapter_key`, or comes before every passage when both are None."""
    key: str
    label: str
    heading: str
    after_anchor: Optional[str] = None
    after_chapter_key: Optional[str] = None
    url: str


class TocResponse(BaseModel):
    document: DocumentResponse
    chapters: list[TocEntry]
    # The contents tree's roots, or None when the document has no current tree; the
    # reader then navigates by `chapters` alone.
    contents: Optional[list[ContentsNode]] = None
    # In reading order; empty when the document holds none or its list is stale.
    held_texts: list[HeldText] = []
