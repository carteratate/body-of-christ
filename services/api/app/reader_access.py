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
from urllib.parse import urlparse

import asyncpg
from fastapi import HTTPException

from app import catechism_pages, source_links

logger = logging.getLogger(__name__)

ReaderAccess = Literal["full", "excerpt"]

RESTRICTED_CODE = "reader_restricted"

# The official edition for documents whose metadata carries no source URL. The
# Catechism's is the USCCB's own online edition: the USCCB holds the US English text.
_COLLECTION_SOURCE_URLS = {
    "catechism": catechism_pages.COVER_URL,
    "canon-law": "https://www.vatican.va/archive/cod-iuris-canonici/cic_index_en.html",
}


def source_url(collection: str, metadata: dict | None) -> str | None:
    """Where to read a document's full text outside TheoCorpus, or None if unknown."""
    url = (metadata or {}).get("url")
    if isinstance(url, str) and url.startswith(("https://", "http://")):
        return url
    return _COLLECTION_SOURCE_URLS.get(collection)


# The rights holders' credit lines, shown right after an excerpt-only passage. The
# Catechism notice is the exact wording the USCCB requires on any use of its text
# ("Use of the Catechism of the Catholic Church", usccb.org). It belongs to the
# Catechism of the Catholic Church only, not to every document in the collection (a
# Compendium from vatican.va would carry the LEV line). LEV holds the rights to the
# papal and Vatican II texts taken from vatican.va, whose footer names the Dicastery.
CATECHISM_TITLE = "Catechism of the Catholic Church"
CATECHISM_NOTICE = (
    "Excerpts from the English translation of the Catechism of the Catholic Church for "
    "use in the United States of America Copyright \u00a9 1994, United States Catholic "
    "Conference, Inc. -- Libreria Editrice Vaticana. Used with Permission. English "
    "translation of the Catechism of the Catholic Church: Modifications from the Editio "
    "Typica copyright \u00a9 1997, United States Conference of Catholic "
    "Bishops\u2014Libreria Editrice Vaticana."
)
VATICAN_CREDIT = "\u00a9 Dicastery for Communication \u2013 Libreria Editrice Vaticana"


def source_credit(collection: str, url: str | None, title: str | None = None) -> str | None:
    """The credit line owed to a document's rights holder, or None if none is known."""
    if collection == "catechism" and title == CATECHISM_TITLE:
        return CATECHISM_NOTICE
    host = urlparse(url).hostname if url else None
    if host and (host == "vatican.va" or host.endswith(".vatican.va")):
        return VATICAN_CREDIT
    return None


@dataclass(frozen=True)
class DocumentAccess:
    reader_access: ReaderAccess
    source_url: str | None
    source_credit: str | None = None


FULL_ACCESS = DocumentAccess("full", None)

_ACCESS_SQL = """
    SELECT id, collection, title, metadata, reader_access FROM documents
    WHERE id = ANY($1::uuid[])
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
    access: dict[str, DocumentAccess] = {}
    for r in rows:
        if r["reader_access"] != "excerpt":
            access[str(r["id"])] = FULL_ACCESS
            continue
        url = source_url(r["collection"], r["metadata"])
        access[str(r["id"])] = DocumentAccess(
            "excerpt", url, source_credit(r["collection"], url, r.get("title")))
    return access


def access_fields(access: dict[str, DocumentAccess], document_id,
                  unit_label: str | None = None, *, chunk_id=None,
                  content: str | None = None) -> dict:
    """The `reader_access`, `source_url` and `source_credit` fields of a passage's source.

    A passage of a document that links to the USCCB's Catechism flipbook links to the
    page where its first paragraph (`unit_label`, "§1127") starts, not the cover. One
    whose document links to its own page on vatican.va links to the passage's opening
    words there with a text fragment (2.4e, `source_links.py`); pass no content for a
    passage that shows none."""
    a = access.get(str(document_id), FULL_ACCESS)
    return {"reader_access": a.reader_access,
            "source_url": passage_source_url(a.source_url, unit_label, chunk_id, content),
            "source_credit": a.source_credit}


def passage_source_url(url: str | None, unit_label: str | None = None, chunk_id=None,
                       content: str | None = None) -> str | None:
    """A document's source URL narrowed to one passage where the source allows it."""
    if url == catechism_pages.COVER_URL:
        return catechism_pages.page_url(unit_label) or url
    # A collection's fallback URL is an index page, not one holding the passage's text.
    if url and content and url not in _COLLECTION_SOURCE_URLS.values():
        return source_links.passage_url(url, chunk_id, content)
    return url


def restricted_error(source: str | None) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "code": RESTRICTED_CODE,
            "message": "The full text of this document isn't available on TheoCorpus.",
            "source_url": source,
        },
    )
