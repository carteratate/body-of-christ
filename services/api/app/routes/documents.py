import hashlib
import logging
import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.verify import verify_supabase_jwt
from app.db import POOL_ACQUIRE_TIMEOUT_SECONDS, get_pool
from app.derived_contents import derive_summa_contents
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.reader_access import restricted_error, source_url
from app.models.documents import (
    ContentsNode, DocumentResponse, ReaderPassage, ReaderChapter, TocEntry, TocResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)

# Chapter structure comes from the precomputed outline (migration 0037:
# documents.chunk_count and document_chapters), maintained when a collection is
# published. A document whose chunk_count is NULL has no current outline, and its
# structure is derived from chunks as before; `outline_ready` selects the path. The
# COALESCE evaluates the count subquery only for such a document.
_DOCUMENT_SQL_TEMPLATE = """
    SELECT d.id, d.collection, d.title, d.author, d.year, d.translation, d.metadata,
           {reader_access} AS reader_access,
           d.chunk_count IS NOT NULL AS outline_ready,
           COALESCE(d.chunk_count,
                    (SELECT count(*) FROM chunks c WHERE c.document_id = d.id)) AS cnt
    FROM documents d WHERE d.id = $1
"""
_DOCUMENT_SQL = _DOCUMENT_SQL_TEMPLATE.format(reader_access="d.reader_access")
# The same row on a database without 0041 (reader_access, issue #265): every document
# reads as full, so the API can deploy before the migration is applied.
_PRE_ACCESS_DOCUMENT_SQL = _DOCUMENT_SQL_TEMPLATE.format(reader_access="'full'")
# And on a database without 0037 either.
_PRE_OUTLINE_DOCUMENT_SQL = """
    SELECT d.id, d.collection, d.title, d.author, d.year, d.translation, d.metadata,
           'full' AS reader_access,
           false AS outline_ready,
           (SELECT count(*) FROM chunks c WHERE c.document_id = d.id) AS cnt
    FROM documents d WHERE d.id = $1
"""

_DOCUMENT_SQLS = (_DOCUMENT_SQL, _PRE_ACCESS_DOCUMENT_SQL, _PRE_OUTLINE_DOCUMENT_SQL)

_OUTLINE_TOC_SQL = """
    SELECT chapter_key, chapter_label FROM document_chapters
    WHERE document_id = $1 ORDER BY ordinal
"""
_LEGACY_TOC_SQL = """
    SELECT chapter_key, chapter_label
    FROM chunks WHERE document_id = $1 AND chapter_key IS NOT NULL
    GROUP BY chapter_key, chapter_label
    ORDER BY min(position)
"""

_OUTLINE_FIRST_CHAPTER_SQL = """
    SELECT chapter_key FROM document_chapters WHERE document_id = $1 AND ordinal = 1
"""
_LEGACY_FIRST_CHAPTER_SQL = """
    SELECT chapter_key FROM chunks WHERE document_id = $1 AND chapter_key IS NOT NULL
    ORDER BY position LIMIT 1
"""

_OUTLINE_NEIGHBORS_SQL = """
    SELECT (SELECT p.chapter_key FROM document_chapters p
            WHERE p.document_id = c.document_id AND p.ordinal = c.ordinal - 1) AS prev_key,
           (SELECT n.chapter_key FROM document_chapters n
            WHERE n.document_id = c.document_id AND n.ordinal = c.ordinal + 1) AS next_key
    FROM document_chapters c WHERE c.document_id = $1 AND c.chapter_key = $2
"""
_LEGACY_CHAPTER_KEYS_SQL = """
    SELECT chapter_key FROM chunks WHERE document_id = $1 AND chapter_key IS NOT NULL
    GROUP BY chapter_key ORDER BY min(position)
"""

# The contents tree (migration 0040), with a flag for any node whose anchor no longer
# names a passage in its chapter. Served only when every node is current; see
# _contents_tree. The NOT EXISTS uses chunks' unique (document_id, anchor) index.
_CONTENTS_SQL = """
    SELECT dc.ordinal, dc.parent_ordinal, dc.node_key, dc.kind, dc.label, dc.short_label,
           dc.chapter_key, dc.anchor, dc.range_label,
           dc.anchor IS NOT NULL AND NOT EXISTS (
               SELECT 1 FROM chunks c
               WHERE c.document_id = dc.document_id AND c.anchor = dc.anchor
                 AND c.chapter_key = dc.chapter_key
           ) AS anchor_missing
    FROM document_contents dc WHERE dc.document_id = $1 ORDER BY dc.ordinal
"""


async def require_document_access(
    doc_id: str,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Allow authenticated readers or a guest who retrieved this document."""
    if credentials is not None:
        await verify_supabase_jwt(credentials.credentials)
        return
    guest_token = request.headers.get("x-theocorpus-guest-token")
    if not guest_token or not 32 <= len(guest_token) <= 128:
        raise HTTPException(status_code=401, detail="Missing authorization")
    doc_uuid = _parse_doc_id(doc_id)
    pool = _require_pool()
    token_hash = hashlib.sha256(guest_token.encode()).hexdigest()
    try:
        async with pool.acquire(timeout=POOL_ACQUIRE_TIMEOUT_SECONDS) as conn:
            allowed = await conn.fetchval(
                """SELECT EXISTS (
                       SELECT 1 FROM guest_trials gt
                       JOIN guest_trial_retrievals gr ON gr.guest_trial_id=gt.id
                       JOIN chunks c ON c.id=gr.chunk_id
                       WHERE gt.session_token_hash=$1 AND c.document_id=$2
                         AND gt.created_at > now() - interval '30 days'
                         AND gt.claimed_by IS NULL
                   )""",
                token_hash, doc_uuid,
            )
    except Exception as exc:
        logger.error("guest document access check failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
    if not allowed:
        raise HTTPException(status_code=403, detail="Document is not part of this guest session")


def _parse_doc_id(doc_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid doc_id: must be a UUID")


def _require_pool() -> asyncpg.Pool:
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    return pool


async def _fetch_document(conn: asyncpg.Connection, doc_uuid: uuid.UUID) -> asyncpg.Record:
    doc_row = None
    for i, sql in enumerate(_DOCUMENT_SQLS):
        try:
            doc_row = await conn.fetchrow(sql, doc_uuid)
            break
        except asyncpg.UndefinedColumnError:
            # A migration is not applied (0041, then 0037). Without 0037, outline_ready
            # is false, so every later query of the request takes the chunks-derived
            # path too.
            if i == len(_DOCUMENT_SQLS) - 1:
                raise
    if doc_row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc_row


def _document_response(doc_row) -> DocumentResponse:
    access = doc_row["reader_access"]
    return DocumentResponse(
        id=str(doc_row["id"]), collection=doc_row["collection"], title=doc_row["title"],
        author=doc_row["author"], year=doc_row["year"], translation=doc_row.get("translation"), metadata=doc_row["metadata"],
        chunk_count=doc_row["cnt"], reader_access=access,
        source_url=(source_url(doc_row["collection"], doc_row["metadata"])
                    if access == "excerpt" else None),
    )


def _require_full_reader(doc_row) -> None:
    """Refuse the full text of an excerpt-only document (issue #265), for guests and
    signed-in readers alike."""
    if doc_row["reader_access"] == "excerpt":
        raise restricted_error(source_url(doc_row["collection"], doc_row["metadata"]))


async def _neighbor_keys(
    conn: asyncpg.Connection, doc_uuid: uuid.UUID, chapter_key: str, outline_ready: bool,
) -> tuple[str | None, str | None]:
    """Return the previous and next chapter keys around `chapter_key`."""
    if outline_ready:
        row = await conn.fetchrow(_OUTLINE_NEIGHBORS_SQL, doc_uuid, chapter_key)
        if row is not None:
            return row["prev_key"], row["next_key"]
        # The chapter has passages but no outline row. The invalidation triggers clear
        # outline_ready when chunks change, so this is a read racing a publish that
        # committed between this request's queries (they share no snapshot). Answer
        # this request from chunks; the next request sees the cleared flag.
        logger.warning(
            "reader outline for document %s lacks chapter %r; deriving neighbors from chunks",
            doc_uuid, chapter_key,
        )

    keys = [r["chapter_key"] for r in await conn.fetch(_LEGACY_CHAPTER_KEYS_SQL, doc_uuid)]
    idx = keys.index(chapter_key) if chapter_key in keys else 0
    prev_key = keys[idx - 1] if idx > 0 else None
    next_key = keys[idx + 1] if idx + 1 < len(keys) else None
    return prev_key, next_key


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    user: AuthUser | None = Depends(require_document_access),
) -> DocumentResponse:
    """Return metadata for a single document."""
    doc_uuid = _parse_doc_id(doc_id)
    pool = _require_pool()
    try:
        async with pool.acquire(timeout=POOL_ACQUIRE_TIMEOUT_SECONDS) as conn:
            doc_row = await _fetch_document(conn, doc_uuid)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_document query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
    return _document_response(doc_row)


async def _fetch_contents_rows(conn: asyncpg.Connection, doc_uuid: uuid.UUID) -> list:
    try:
        return await conn.fetch(_CONTENTS_SQL, doc_uuid)
    except asyncpg.UndefinedTableError:
        # Migration 0040 is not applied: no document has a contents tree yet.
        return []


def _contents_tree(doc_uuid: uuid.UUID, rows: list, chapter_keys: list[str],
                   ) -> list[ContentsNode] | None:
    """Assemble the contents tree from its pre-order rows, or None if it is not current.

    The datapipeline writes the tree with the chunks, but nothing ties the two together
    afterwards (the outline's invalidation triggers cover chapters only). A tree is
    served only if every node opens a chapter in `chapter_keys`, every anchor is a
    passage in its node's chapter, and a pre-order walk meets chapters in reading
    order. Otherwise the reader falls back to the flat chapter list, which is always
    current, rather than sending readers to dead or misplaced chapters.
    """
    if not rows:
        return None
    # First occurrence wins: the chunks-derived list groups by (key, label), so a key
    # whose passages carry two labels can appear twice, and its place in reading order
    # is its first position, as in the outline and the datapipeline's check.
    order: dict[str, int] = {}
    for index, key in enumerate(chapter_keys):
        order.setdefault(key, index)
    previous = -1
    problem = None
    for row in rows:
        index = order.get(row["chapter_key"])
        if index is None:
            problem = f"node {row['node_key']!r} opens missing chapter {row['chapter_key']!r}"
        elif row["anchor_missing"]:
            problem = f"node {row['node_key']!r} points at missing anchor {row['anchor']!r}"
        elif index < previous:
            problem = f"node {row['node_key']!r} is out of reading order"
        if problem:
            logger.warning("contents tree for document %s is stale (%s); serving chapters only",
                           doc_uuid, problem)
            return None
        previous = index

    roots: list[ContentsNode] = []
    by_ordinal: dict[int, ContentsNode] = {}
    for row in rows:
        node = ContentsNode(
            key=row["node_key"], kind=row["kind"], label=row["label"],
            short_label=row["short_label"], chapter_key=row["chapter_key"],
            anchor=row["anchor"], range_label=row["range_label"], children=[],
        )
        by_ordinal[row["ordinal"]] = node
        parent = row["parent_ordinal"]
        (roots if parent is None else by_ordinal[parent].children).append(node)
    return roots


@router.get("/documents/{doc_id}/toc", response_model=TocResponse)
async def get_document_toc(
    doc_id: str,
    user: AuthUser | None = Depends(require_document_access),
) -> TocResponse:
    """Ordered chapter list for the reader's pickers + Contents drawer, and the
    document's contents tree when it has a current one."""
    doc_uuid = _parse_doc_id(doc_id)
    pool = _require_pool()
    try:
        async with pool.acquire(timeout=POOL_ACQUIRE_TIMEOUT_SECONDS) as conn:
            doc_row = await _fetch_document(conn, doc_uuid)
            _require_full_reader(doc_row)
            toc_sql = _OUTLINE_TOC_SQL if doc_row["outline_ready"] else _LEGACY_TOC_SQL
            chapter_rows = await conn.fetch(toc_sql, doc_uuid)
            contents_rows = await _fetch_contents_rows(conn, doc_uuid)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_document_toc query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    chapters = [TocEntry(chapter_key=r["chapter_key"], chapter_label=r["chapter_label"])
                for r in chapter_rows]
    contents = _contents_tree(doc_uuid, contents_rows, [c.chapter_key for c in chapters])
    if not contents_rows and doc_row["collection"] == "summa":
        # Stopgap until the Summa is published with a stored tree (#254): derive
        # Part > Question > Article from today's chapter keys and labels.
        contents = derive_summa_contents([(c.chapter_key, c.chapter_label) for c in chapters])
    return TocResponse(document=_document_response(doc_row), chapters=chapters,
                       contents=contents)


@router.get("/documents/{doc_id}/reader", response_model=ReaderChapter)
async def get_document_reader(
    doc_id: str,
    anchor: str | None = Query(default=None, description="Deep-link passage anchor"),
    chapter: str | None = Query(default=None, description="chapter_key to load directly"),
    user: AuthUser | None = Depends(require_document_access),
) -> ReaderChapter:
    """Return one chapter section of clean passages, with prev/next chapter keys."""
    doc_uuid = _parse_doc_id(doc_id)
    pool = _require_pool()
    try:
        async with pool.acquire(timeout=POOL_ACQUIRE_TIMEOUT_SECONDS) as conn:
            doc_row = await _fetch_document(conn, doc_uuid)
            _require_full_reader(doc_row)

            # Resolve target chapter_key (explicit chapter > anchor > first chapter).
            chapter_key = chapter
            if chapter_key is None and anchor:
                row = await conn.fetchrow(
                    "SELECT chapter_key FROM chunks WHERE document_id=$1 AND anchor=$2",
                    doc_uuid, anchor)
                chapter_key = row["chapter_key"] if row else None
            if chapter_key is None:
                first_sql = (_OUTLINE_FIRST_CHAPTER_SQL if doc_row["outline_ready"]
                             else _LEGACY_FIRST_CHAPTER_SQL)
                row = await conn.fetchrow(first_sql, doc_uuid)
                if row is None:
                    raise HTTPException(status_code=404, detail="Document has no readable passages")
                chapter_key = row["chapter_key"]

            passage_rows = await conn.fetch(
                """SELECT id, anchor, chapter_key, chapter_label, unit_label, reference, content
                   FROM chunks WHERE document_id=$1 AND chapter_key=$2 ORDER BY position""",
                doc_uuid, chapter_key,
            )
            if not passage_rows:
                raise HTTPException(status_code=404, detail="Chapter not found")

            prev_key, next_key = await _neighbor_keys(
                conn, doc_uuid, chapter_key, doc_row["outline_ready"])
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_document_reader query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    passages = [
        ReaderPassage(
            id=str(r["id"]), anchor=r["anchor"], chapter_key=r["chapter_key"],
            chapter_label=r["chapter_label"], unit_label=r["unit_label"],
            reference=r["reference"], content=r["content"],
        ) for r in passage_rows
    ]
    return ReaderChapter(
        document=_document_response(doc_row), chapter_key=chapter_key,
        chapter_label=passage_rows[0]["chapter_label"], passages=passages,
        prev_chapter_key=prev_key, next_chapter_key=next_key, highlight_anchor=anchor,
    )
