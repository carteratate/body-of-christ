"""Excerpt-only documents (issue #265).

`documents.reader_access` (migration 0041) is `excerpt` for a document whose rights are
not cleared. Its passages stay in search, but the API refuses its reader and contents
(403 `reader_restricted`) and every surface links to the official source instead. The
column is derived from the rights inventory by the datapipeline (`reader_access.py`
there); the API only reads it.

The API runs on a database without 0041: every document then reads as `full`.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Literal

import asyncpg
from fastapi import HTTPException

logger = logging.getLogger(__name__)

ReaderAccess = Literal["full", "excerpt"]

RESTRICTED_CODE = "reader_restricted"

# The official edition for documents whose metadata carries no source URL.
_COLLECTION_SOURCE_URLS = {
    "catechism": "https://www.vatican.va/archive/ENG0015/_INDEX.HTM",
    "canon-law": "https://www.vatican.va/archive/cod-iuris-canonici/cic_index_en.html",
}


def source_url(collection: str, metadata: dict | None) -> str | None:
    """Where to read a document's full text outside TheoCorpus, or None if unknown."""
    url = (metadata or {}).get("url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        return url
    return _COLLECTION_SOURCE_URLS.get(collection)


@dataclass(frozen=True)
class DocumentAccess:
    reader_access: ReaderAccess
    source_url: str | None


FULL_ACCESS = DocumentAccess("full", None)

_ACCESS_SQL = """
    SELECT id, collection, metadata, reader_access FROM documents WHERE id = ANY($1::uuid[])
"""


async def document_access(conn, document_ids) -> dict[str, DocumentAccess]:
    """Reader access for each id, keyed by the id as a string. `conn` is a connection
    or pool. Ids not found, and every id on a database without 0041, read as full."""
    ids = sorted({str(i) for i in document_ids if i is not None})
    if not ids:
        return {}
    try:
        rows = await conn.fetch(_ACCESS_SQL, [uuid.UUID(i) for i in ids])
    except asyncpg.UndefinedColumnError:
        return {}
    return {
        str(r["id"]): DocumentAccess(
            r["reader_access"],
            source_url(r["collection"], r["metadata"]) if r["reader_access"] == "excerpt" else None,
        )
        for r in rows
    }


def access_fields(access: dict[str, DocumentAccess], document_id) -> dict:
    """The `reader_access` and `source_url` fields of a passage's source."""
    a = access.get(str(document_id), FULL_ACCESS)
    return {"reader_access": a.reader_access, "source_url": a.source_url}


def restricted_error(source: str | None) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "code": RESTRICTED_CODE,
            "message": "The full text of this document isn't available on TheoCorpus.",
            "source_url": source,
        },
    )
