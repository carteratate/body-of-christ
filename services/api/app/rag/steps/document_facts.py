"""Document facts for result passages (corpus cleanup 2.4a).

One query per search: each passage's document facts (migration 0042's columns on
`documents`), its work's (`document_works`, D6) and its own passage fields. The card's
author comes from here, not from the Qdrant payload, so a corrected author shows as soon
as Postgres has it.

Work-level values override document-level ones when a passage has a `work_key`: the
author and certainty of "Dubious or Spurious Writings." come from the work. A passage's
`passage_author` (a Father quoted in the Catena Aurea) is sent separately and wins for
the author shown.

Three keys of the passage's `metadata` also leave the API here (2.4f): `text_source`
("ocr", a passage built from a scanned edition, 1.2f), `text_status`
("unofficial_english", a canon shown in the L'Osservatore Romano English, 1.5b) and
`official_latin_url`. The rest of `metadata` stays internal.

A document's `form` (bull or brief, 0044, issue #330) is read only where the column
exists, so the API deploys before that migration is applied.

Best-effort: on a database without 0042 it returns nothing and runs no query; on a
failure or timeout it returns nothing and the caller sends today's payload.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from app import corpus_schema
from app.models.corpus import DocumentFacts

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 1.0

_DOCUMENT_FIELDS = ("year", "date_display", "translation", "genre", "form", "issuer",
                    "issuer_label", "certainty", "attribution_note", "notes",
                    "source_credit", "superseded_by", "superseded_note")
# Work values that replace the document's when the passage belongs to a work.
_WORK_FIELDS = ("year", "date_display", "genre", "certainty", "attribution_note", "notes")


# The passage-metadata keys clients see (2.4f), and the one value of each they act on.
TEXT_SOURCE_OCR = "ocr"
TEXT_STATUS_UNOFFICIAL_ENGLISH = "unofficial_english"
TEXT_LABEL_COLUMNS = ("c.metadata->>'text_source' AS text_source, "
                       "c.metadata->>'text_status' AS text_status, "
                       "c.metadata->>'official_latin_url' AS official_latin_url")


def text_labels(row) -> dict:
    """The text labels a passage row carries, only those set and only known values, so
    a passage without them sends nothing new (2.4f). `row` holds the three columns
    `TEXT_LABEL_COLUMNS` names."""
    labels = {}
    if row["text_source"] == TEXT_SOURCE_OCR:
        labels["text_source"] = TEXT_SOURCE_OCR
    if row["text_status"] == TEXT_STATUS_UNOFFICIAL_ENGLISH:
        labels["text_status"] = TEXT_STATUS_UNOFFICIAL_ENGLISH
    url = row["official_latin_url"]
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        labels["official_latin_url"] = url
    return labels


def _sql(works: bool, form: bool = False) -> str:
    work = ("""w.title AS work_title, w.author AS work_author, w.year AS work_year,
           w.date_display AS work_date_display, w.genre AS work_genre,
           w.certainty AS work_certainty, w.attribution_note AS work_attribution_note,
           w.notes AS work_notes""" if works else
            """NULL::text AS work_title, NULL::text AS work_author, NULL::int AS work_year,
           NULL::text AS work_date_display, NULL::text AS work_genre,
           NULL::text AS work_certainty, NULL::text AS work_attribution_note,
           NULL::text AS work_notes""")
    join = ("LEFT JOIN document_works w ON w.document_id = c.document_id "
            "AND w.work_key = c.work_key" if works else "")
    return f"""
    SELECT c.id::text AS chunk_id, c.language, c.note, c.passage_author, c.voice,
           {TEXT_LABEL_COLUMNS},
           d.author, d.year, NULLIF(d.translation, '') AS translation, d.date_display,
           d.genre, {"d.form" if form else "NULL::text AS form"}, d.issuer, d.issuer_label,
           d.certainty, d.attribution_note, d.notes,
           d.source_credit, d.superseded_by::text AS superseded_by, d.superseded_note,
           {work}
    FROM chunks c
    JOIN documents d ON d.id = c.document_id
    {join}
    WHERE c.id = ANY($1::uuid[])
"""


@dataclass(frozen=True)
class PassageFacts:
    author: str | None
    facts: DocumentFacts
    language: str | None
    passage_note: str | None
    passage_author: str | None
    voice: str | None = None
    text_labels: dict = field(default_factory=dict)

    def source_fields(self, required_credit: str | None = None) -> dict:
        """The fields this adds to a passage's `source`, author included.
        `required_credit` is an excerpt-only document's required notice
        (`reader_access.source_credit`), which wins over the stored credit."""
        facts = self.facts
        if required_credit:
            facts = facts.model_copy(update={"source_credit": required_credit})
        fields = {"author": self.author, "facts": facts.model_dump(),
                  "language": self.language, "passage_note": self.passage_note,
                  "passage_author": self.passage_author}
        # Only when set (2.4d): a saved search or bookmark marks a rejected passage.
        if self.voice:
            fields["voice"] = self.voice
        # Likewise only when set (2.4f): no passage carries them before Phase 4.
        fields.update(self.text_labels)
        return fields


def _passage_facts(row) -> PassageFacts:
    values = {f: row[f] for f in _DOCUMENT_FIELDS}
    in_work = row["work_title"] is not None
    if in_work:
        for f in _WORK_FIELDS:
            if row[f"work_{f}"] is not None:
                values[f] = row[f"work_{f}"]
    return PassageFacts(
        author=(row["work_author"] if in_work and row["work_author"] else row["author"]),
        facts=DocumentFacts(**values, work_title=row["work_title"]),
        language=row["language"], passage_note=row["note"],
        passage_author=row["passage_author"], voice=row["voice"],
        text_labels=text_labels(row),
    )


async def fetch(conn, chunk_ids) -> dict[str, PassageFacts]:
    """chunk_id -> PassageFacts. `conn` is a connection or pool. Raises on a failed
    query; `fetch_best_effort` does not."""
    ids = sorted({str(i) for i in chunk_ids if i is not None})
    if not ids or conn is None:
        return {}
    schema = await corpus_schema.current(conn)
    if not schema.facts:
        return {}

    async def run(s: corpus_schema.CorpusSchema):
        if not s.facts:
            return []
        return await conn.fetch(_sql(s.works, s.form), [uuid.UUID(i) for i in ids])

    rows = await corpus_schema.run_with_fallback(run, conn)
    return {r["chunk_id"]: _passage_facts(r) for r in rows}


async def fetch_best_effort(conn, chunk_ids,
                            ) -> tuple[dict[str, PassageFacts], Exception | None]:
    """`fetch`, bounded by TIMEOUT_SECONDS; on failure ({}, the exception)."""
    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            return await fetch(conn, chunk_ids), None
    except Exception as exc:
        logger.warning("document facts lookup failed (%s); results go without facts",
                       exc.__class__.__name__)
        return {}, exc
