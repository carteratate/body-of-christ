"""Corpus-cleanup fields shared by search results, bookmarks and the reader (2.4a).

Every field is optional, so a client that does not know them, and a database without
migration 0042, are both unaffected.
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

Certainty = Literal["genuine", "disputed", "pseudonymous", "anonymous"]
PassageStatus = Literal["current", "moved", "removed"]


class DocumentFacts(BaseModel):
    year: Optional[int] = None
    date_display: Optional[str] = None
    translation: Optional[str] = None
    genre: Optional[str] = None
    # How the papal chancery issued the document, "bull" or "brief" (0044, issue #330);
    # None where none is recorded and on a database without 0044.
    form: Optional[str] = None
    issuer: Optional[str] = None        # slug, for filters
    issuer_label: Optional[str] = None  # shown to users
    certainty: Optional[Certainty] = None
    attribution_note: Optional[str] = None
    notes: Optional[str] = None
    # The rights holder's line for this text. An excerpt-only document's required
    # notice (`reader_access.source_credit`, e.g. the USCCB's for the Catechism) wins
    # over `documents.source_credit`, so the legally required wording is never replaced.
    source_credit: Optional[str] = None
    superseded_by: Optional[str] = None
    superseded_note: Optional[str] = None
    work_title: Optional[str] = None   # from document_works when the passage has a work_key


CautionKind = Literal["incomplete", "wording", "authorship", "authority"]


class CardLink(BaseModel):
    """A caution's link: an external page (`href`, opened in a new tab), or the reader's
    current text of a superseded document (`document_id`, which the client turns into
    its own reader path)."""
    label: str
    href: Optional[str] = None
    document_id: Optional[str] = None


class CardCaution(BaseModel):
    """Slot 1, "Read with care": TheoCorpus's caution about the passage (4.4)."""
    kind: CautionKind
    text: str
    link: Optional[CardLink] = None


class PassageCard(BaseModel):
    """The notes under an opened passage (corpus cleanup 4.4, issue #407): at most three
    slots, each left empty when it has nothing to say. Sent only for a passage whose
    document a 4.4 publish wrote (`metadata.card_version`); its absence means a response
    from before that data, which clients render as they did."""
    cautions: list[CardCaution] = []
    # Slot 2, "About this text": the items of one line, joined by " · " on screen.
    record: list[str] = []
    # Slot 3: the rights holder's required notice, verbatim, or None.
    notice: Optional[str] = None


class OverviewNote(BaseModel):
    """A document-wide note for the reader overview or the Library row (4.4). `kind` is
    the caution kind for a caution, None for a note that is part of the record."""
    kind: Optional[CautionKind] = None
    text: str


class WorkInfo(BaseModel):
    """One work inside a document (D6), with its own attribution."""
    work_key: str
    ordinal: int
    title: str
    author: Optional[str] = None
    certainty: Optional[Certainty] = None
    attribution_note: Optional[str] = None
    notes: Optional[str] = None
    date_display: Optional[str] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    clavis_ref: Optional[str] = None


class Tombstone(BaseModel):
    """Why a passage or document left the corpus. Shown in place of its text."""
    entity: Literal["document", "passage"]
    rule: str
    reason_code: str
    public_reason: str
    church_act: Optional[str] = None
    # Where the text can still be read, for a text held for permission or awaiting a
    # translation (1.2a, 1.3d; ADR 0001). See `corpus_lifecycle.read_elsewhere_url`.
    read_elsewhere_url: Optional[str] = None
    retired_at: datetime
    title: Optional[str] = None
    author: Optional[str] = None
    reference: Optional[str] = None


class Redirect(BaseModel):
    """Where a moved passage, anchor, chapter or document now is."""
    kind: Literal["moved", "split", "merged", "renumbered"]
    document_id: str
    anchor: Optional[str] = None
    chunk_id: Optional[str] = None
    chapter_key: Optional[str] = None


class RedirectedFrom(BaseModel):
    """The location a reader request named, when the API followed a redirect from it."""
    document_id: str
    anchor: Optional[str] = None
    chapter_key: Optional[str] = None
