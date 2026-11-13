import hashlib
import logging
import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import corpus_lifecycle, corpus_schema
from app.auth.verify import verify_supabase_jwt
from app.db import POOL_ACQUIRE_TIMEOUT_SECONDS, get_pool
from app.catechism_contents import catechism_contents
from app.derived_contents import derive_summa_contents
from app.deps.auth import get_current_user
from app.models.auth import AuthUser
from app.corpus_lifecycle import CorpusLifecycleError
from app.corpus_schema import CorpusSchema
from app.reader_access import (passage_source_url, restricted_error, source_credit,
                               source_url)
from app.models.corpus import DocumentFacts, RedirectedFrom, WorkInfo
from app.rag.steps import document_facts
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
#
# Retired passages and documents (migration 0042, corpus cleanup 2.4a) are never read
# as part of a document: every chunks query below adds `CorpusSchema.visible`, which is
# empty on a database without 0042, and the outline already leaves retired rows out.
def _outline_columns(visible: str) -> str:
    return f"""d.chunk_count IS NOT NULL AS outline_ready,
           COALESCE(d.chunk_count,
                    (SELECT count(*) FROM chunks c WHERE c.document_id = d.id{visible})) AS cnt"""


# The same columns on a database without 0037, so the API can deploy before it is applied.
def _pre_outline_columns(visible: str) -> str:
    return f"""false AS outline_ready,
           (SELECT count(*) FROM chunks c WHERE c.document_id = d.id{visible}) AS cnt"""


# Document facts (0042), for DocumentResponse.facts.
_FACT_COLUMNS = """,
           d.date_display, d.genre, d.issuer, d.issuer_label, d.certainty,
           d.attribution_note, d.notes, d.source_credit,
           d.superseded_by::text AS superseded_by, d.superseded_note"""


def _document_sql(*, access: bool, outline: bool,
                  schema: CorpusSchema = corpus_schema.LEGACY) -> str:
    """The document row. Without 0041 (`access` false) every document reads as full,
    so the API can deploy before that migration is applied (issue #265). Without 0042
    nothing is retired and there are no facts."""
    visible = schema.visible("c")
    return f"""
    SELECT d.id, d.collection, d.title, d.author, d.year, d.translation, d.metadata,
           {"d.reader_access" if access else "'full'"} AS reader_access,
           {_outline_columns(visible) if outline else _pre_outline_columns(visible)},
           {"d.retired_at IS NOT NULL" if schema.retired else "false"} AS retired{_FACT_COLUMNS if schema.facts else ""}
    FROM documents d WHERE d.id = $1
"""


_DOCUMENT_SQL = _document_sql(access=True, outline=True)

_OUTLINE_TOC_SQL = """
    SELECT chapter_key, chapter_label FROM document_chapters
    WHERE document_id = $1 ORDER BY ordinal
"""
_LEGACY_TOC_SQL = """
    SELECT chapter_key, chapter_label
    FROM chunks c WHERE document_id = $1 AND chapter_key IS NOT NULL{visible}
    GROUP BY chapter_key, chapter_label
    ORDER BY min(position)
"""

_OUTLINE_FIRST_CHAPTER_SQL = """
    SELECT chapter_key FROM document_chapters WHERE document_id = $1 AND ordinal = 1
"""
_LEGACY_FIRST_CHAPTER_SQL = """
    SELECT chapter_key FROM chunks c WHERE document_id = $1 AND chapter_key IS NOT NULL{visible}
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
    SELECT chapter_key FROM chunks c WHERE document_id = $1 AND chapter_key IS NOT NULL{visible}
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
                 AND c.chapter_key = dc.chapter_key{visible}
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
            async def check(schema: CorpusSchema) -> bool:
                return await conn.fetchval(_guest_access_sql(schema), token_hash, doc_uuid)

            allowed = await corpus_schema.run_with_fallback(check, conn)
    except Exception as exc:
        logger.error("guest document access check failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
    if not allowed:
        raise HTTPException(status_code=403, detail="Document is not part of this guest session")


_GUEST_SESSION = """FROM guest_trials gt
                       JOIN guest_trial_retrievals gr ON gr.guest_trial_id=gt.id
                       JOIN chunks c ON c.id=gr.chunk_id"""
_GUEST_LIVE = """AND gt.created_at > now() - interval '30 days'
                         AND gt.claimed_by IS NULL"""


def _guest_access_sql(schema: CorpusSchema) -> str:
    """Whether the guest retrieved a passage of the document. With redirects (0042,
    2.4a), also a document that redirects lead to, up to three hops, from a passage the
    guest retrieved or its document, so a moved result still opens."""
    redirected = f""" OR EXISTS (
                       WITH RECURSIVE reach (document_id, passage_id, hops) AS (
                           SELECT c.document_id, gr.chunk_id, 0 {_GUEST_SESSION}
                           WHERE gt.session_token_hash=$1
                             {_GUEST_LIVE}
                           UNION
                           SELECT r.new_document_id, r.new_id, reach.hops + 1
                           FROM reach JOIN corpus_redirects r
                             ON r.old_id = reach.passage_id
                             OR r.old_document_id = reach.document_id
                           WHERE reach.hops < 3
                       )
                       SELECT 1 FROM reach WHERE document_id=$2
                   )""" if schema.redirects else ""
    return f"""SELECT EXISTS (
                       SELECT 1 {_GUEST_SESSION}
                       WHERE gt.session_token_hash=$1 AND c.document_id=$2
                         {_GUEST_LIVE}
                   ){redirected}"""


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


async def _fetch_document(conn: asyncpg.Connection, doc_uuid: uuid.UUID,
                          schema: CorpusSchema = corpus_schema.LEGACY) -> asyncpg.Record:
    """The document row, or the reader's answer for one that is gone: 410 with its
    tombstone when it was removed, 404 with its redirect when it moved (2.4a), and
    today's 404 otherwise."""
    # Fall back one migration at a time, and only for the column actually missing:
    # a missing outline must never also switch off the reader_access check. A missing
    # 0042 column reaches `run_with_fallback`, which retries the request without 0042.
    access = outline = True
    while True:
        try:
            doc_row = await conn.fetchrow(
                _document_sql(access=access, outline=outline, schema=schema), doc_uuid)
            break
        except asyncpg.UndefinedColumnError as exc:
            if access and "reader_access" in str(exc):
                # Migration 0041 is not applied: no document is excerpt-only yet.
                logger.warning("documents.reader_access is missing; reading every document as full")
                access = False
            elif outline and "chunk_count" in str(exc):
                # Migration 0037 is not applied: outline_ready is false, so every later
                # query of the request takes the chunks-derived path too.
                outline = False
            else:
                raise
    if doc_row is None or doc_row.get("retired"):
        resolution = await corpus_lifecycle.resolve_document(conn, doc_uuid, schema)
        if resolution is not None:
            raise CorpusLifecycleError(resolution)
        if doc_row is not None:
            logger.warning("document %s is retired but has no tombstone or redirect; "
                           "serving it", doc_uuid)
    if doc_row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc_row


_WORKS_SQL = """
    SELECT work_key, ordinal, title, author, certainty, attribution_note, notes,
           date_display, year, genre, clavis_ref
    FROM document_works WHERE document_id = $1 ORDER BY ordinal
"""


async def _fetch_works(conn: asyncpg.Connection, doc_uuid: uuid.UUID,
                       schema: CorpusSchema) -> list[WorkInfo]:
    if not schema.works:
        return []
    return [WorkInfo(**dict(r)) for r in await conn.fetch(_WORKS_SQL, doc_uuid)]


def _document_facts(doc_row) -> DocumentFacts | None:
    """The document's facts (0042), or None without them. An excerpt-only document's
    required notice wins over the stored credit, as on search cards."""
    if "genre" not in doc_row.keys():
        return None
    required = None
    if doc_row["reader_access"] == "excerpt":
        required = source_credit(doc_row["collection"],
                                 source_url(doc_row["collection"], doc_row["metadata"]),
                                 doc_row["title"])
    return DocumentFacts(
        year=doc_row["year"], date_display=doc_row["date_display"],
        translation=doc_row["translation"] or None, genre=doc_row["genre"],
        issuer=doc_row["issuer"], issuer_label=doc_row["issuer_label"],
        certainty=doc_row["certainty"], attribution_note=doc_row["attribution_note"],
        notes=doc_row["notes"], source_credit=required or doc_row["source_credit"],
        superseded_by=doc_row["superseded_by"], superseded_note=doc_row["superseded_note"],
    )


def _document_response(doc_row, works: list[WorkInfo] | None = None) -> DocumentResponse:
    access = doc_row["reader_access"]
    return DocumentResponse(
        id=str(doc_row["id"]), collection=doc_row["collection"], title=doc_row["title"],
        author=doc_row["author"], year=doc_row["year"], translation=doc_row.get("translation"), metadata=doc_row["metadata"],
        chunk_count=doc_row["cnt"], reader_access=access,
        source_url=(source_url(doc_row["collection"], doc_row["metadata"])
                    if access == "excerpt" else None),
        facts=_document_facts(doc_row), works=works or [],
    )


def _with_visible(sql: str, schema: CorpusSchema) -> str:
    return sql.replace("{visible}", schema.visible("c"))


def _require_full_reader(doc_row, passage=None) -> None:
    """Refuse the full text of an excerpt-only document (issue #265), for guests and
    signed-in readers alike. With the passage the request named (a row with `id` and
    `content`), the source link opens at that passage where it can (2.4e)."""
    if doc_row["reader_access"] == "excerpt":
        url = source_url(doc_row["collection"], doc_row["metadata"])
        if passage is not None:
            url = passage_source_url(url, chunk_id=passage["id"], content=passage["content"])
        raise restricted_error(url)


async def _restricted_passage(conn, doc_row, anchor: str | None, schema: CorpusSchema):
    """The visible passage an anchor names in an excerpt-only document, for its 403."""
    if doc_row["reader_access"] != "excerpt" or not anchor:
        return None
    return await conn.fetchrow(
        f"SELECT id, content FROM chunks c WHERE document_id=$1 AND anchor=$2{schema.visible('c')}",
        doc_row["id"], anchor)


async def _neighbor_keys(
    conn: asyncpg.Connection, doc_uuid: uuid.UUID, chapter_key: str, outline_ready: bool,
    schema: CorpusSchema = corpus_schema.LEGACY,
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

    keys = [r["chapter_key"] for r in await conn.fetch(
        _with_visible(_LEGACY_CHAPTER_KEYS_SQL, schema), doc_uuid)]
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
            async def load(schema: CorpusSchema):
                doc_row = await _fetch_document(conn, doc_uuid, schema)
                return doc_row, await _fetch_works(conn, doc_uuid, schema)

            doc_row, works = await corpus_schema.run_with_fallback(load, conn)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_document query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc
    return _document_response(doc_row, works)


# The paragraph numbers each Catechism passage holds, for the stopgap tree.
_CATECHISM_PARAGRAPHS_SQL = """
SELECT chapter_key, anchor, metadata->'ccc_paragraphs' AS paragraphs
FROM chunks c
WHERE document_id = $1 AND jsonb_typeof(metadata->'ccc_paragraphs') = 'array'{visible}
ORDER BY position
"""


async def _fetch_contents_rows(conn: asyncpg.Connection, doc_uuid: uuid.UUID,
                               schema: CorpusSchema = corpus_schema.LEGACY) -> list:
    try:
        return await conn.fetch(_with_visible(_CONTENTS_SQL, schema), doc_uuid)
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
            async def load(schema: CorpusSchema):
                doc_row = await _fetch_document(conn, doc_uuid, schema)
                _require_full_reader(doc_row)
                toc_sql = (_OUTLINE_TOC_SQL if doc_row["outline_ready"]
                           else _with_visible(_LEGACY_TOC_SQL, schema))
                chapter_rows = await conn.fetch(toc_sql, doc_uuid)
                contents_rows = await _fetch_contents_rows(conn, doc_uuid, schema)
                catechism_passages = []
                if not contents_rows and doc_row["collection"] == "catechism":
                    catechism_passages = await conn.fetch(
                        _with_visible(_CATECHISM_PARAGRAPHS_SQL, schema), doc_uuid)
                works = await _fetch_works(conn, doc_uuid, schema)
                return doc_row, chapter_rows, contents_rows, catechism_passages, works

            (doc_row, chapter_rows, contents_rows, catechism_passages,
             works) = await corpus_schema.run_with_fallback(load, conn)
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
    elif not contents_rows and doc_row["collection"] == "catechism":
        # Stopgap until the Catechism is published with a stored tree (#253): its
        # headings from the source, pointed at today's passages by paragraph number.
        contents = catechism_contents(
            [(r["chapter_key"], r["anchor"], r["paragraphs"]) for r in catechism_passages],
            [c.chapter_key for c in chapters])
    return TocResponse(document=_document_response(doc_row, works), chapters=chapters,
                       contents=contents)


_PASSAGE_FIELDS = f""",
                   language, note, work_key, passage_author, voice,
                   superseded_by::text AS superseded_by, {document_facts.TEXT_LABEL_COLUMNS}"""


def _passages_sql(schema: CorpusSchema) -> str:
    """One chapter's passages. History passages (rule F) are not retired, so they come
    with their chapter and the reader shows them as earlier text."""
    return f"""SELECT id, anchor, chapter_key, chapter_label, unit_label, reference, content{_PASSAGE_FIELDS if schema.facts else ""}
                   FROM chunks c WHERE document_id=$1 AND chapter_key=$2{schema.visible("c")} ORDER BY position"""


async def _anchor_chapter(conn, doc_uuid: uuid.UUID, anchor: str,
                          schema: CorpusSchema) -> str | None:
    row = await conn.fetchrow(
        f"SELECT chapter_key FROM chunks c WHERE document_id=$1 AND anchor=$2{schema.visible('c')}",
        doc_uuid, anchor)
    return row["chapter_key"] if row else None


async def _follow_location(conn, doc_row, doc_uuid: uuid.UUID, *, anchor: str | None,
                           chapter: str | None, schema: CorpusSchema):
    """An anchor or chapter the document no longer shows: the location its redirect
    names, as (document row, document id, chapter_key, anchor, redirected_from), or
    None when nothing explains it. A removed passage raises 410 with its tombstone."""
    resolution = await corpus_lifecycle.resolve_location(
        conn, doc_uuid, anchor=anchor, chapter=chapter, schema=schema)
    if resolution is None:
        return None
    if resolution.status == "removed":
        raise CorpusLifecycleError(resolution)
    target = resolution.redirect
    target_uuid = uuid.UUID(target.document_id)
    if target_uuid != doc_uuid:
        doc_row = await _fetch_document(conn, target_uuid, schema)
        _require_full_reader(doc_row)
    chapter_key = target.chapter_key
    if chapter_key is None and target.anchor:
        chapter_key = await _anchor_chapter(conn, target_uuid, target.anchor, schema)
    origin = RedirectedFrom(document_id=str(doc_uuid), anchor=anchor if not chapter else None,
                            chapter_key=chapter)
    return doc_row, target_uuid, chapter_key, target.anchor, origin


@router.get("/documents/{doc_id}/reader", response_model=ReaderChapter)
async def get_document_reader(
    doc_id: str,
    anchor: str | None = Query(default=None, description="Deep-link passage anchor"),
    chapter: str | None = Query(default=None, description="chapter_key to load directly"),
    user: AuthUser | None = Depends(require_document_access),
) -> ReaderChapter:
    """Return one chapter section of clean passages, with prev/next chapter keys.

    An anchor or chapter that moved (2.4a) answers with the chapter it moved to, which
    may be in another document, with `redirected_from` naming the request. An anchor of
    a removed passage, including one carrying 2.2w's `#retired-<release>` suffix, is
    410 with the passage's tombstone."""
    doc_uuid = _parse_doc_id(doc_id)
    pool = _require_pool()
    try:
        async with pool.acquire(timeout=POOL_ACQUIRE_TIMEOUT_SECONDS) as conn:
            async def load(schema: CorpusSchema):
                doc_row = await _fetch_document(conn, doc_uuid, schema)
                _require_full_reader(
                    doc_row, await _restricted_passage(conn, doc_row, anchor, schema))
                target_uuid, highlight, redirected_from = doc_uuid, anchor, None

                # Resolve target chapter_key (explicit chapter > anchor > first chapter).
                chapter_key = chapter
                if chapter_key is None and anchor:
                    chapter_key = await _anchor_chapter(conn, doc_uuid, anchor, schema)
                    if chapter_key is None:
                        followed = await _follow_location(
                            conn, doc_row, doc_uuid, anchor=anchor, chapter=None, schema=schema)
                        if followed is not None:
                            (doc_row, target_uuid, chapter_key, highlight,
                             redirected_from) = followed
                if chapter_key is None:
                    first_sql = (_OUTLINE_FIRST_CHAPTER_SQL if doc_row["outline_ready"]
                                 else _with_visible(_LEGACY_FIRST_CHAPTER_SQL, schema))
                    row = await conn.fetchrow(first_sql, target_uuid)
                    if row is None:
                        raise HTTPException(status_code=404, detail="Document has no readable passages")
                    chapter_key = row["chapter_key"]

                passage_rows = await conn.fetch(_passages_sql(schema), target_uuid, chapter_key)
                if not passage_rows and chapter is not None and redirected_from is None:
                    followed = await _follow_location(
                        conn, doc_row, doc_uuid, anchor=None, chapter=chapter, schema=schema)
                    if followed is not None and followed[2] is not None:
                        (doc_row, target_uuid, chapter_key, _,
                         redirected_from) = followed
                        highlight = anchor
                        passage_rows = await conn.fetch(
                            _passages_sql(schema), target_uuid, chapter_key)
                if not passage_rows:
                    raise HTTPException(status_code=404, detail="Chapter not found")

                prev_key, next_key = await _neighbor_keys(
                    conn, target_uuid, chapter_key, doc_row["outline_ready"], schema)
                works = await _fetch_works(conn, target_uuid, schema)
                return (doc_row, chapter_key, passage_rows, prev_key, next_key, highlight,
                        redirected_from, works)

            (doc_row, chapter_key, passage_rows, prev_key, next_key, highlight,
             redirected_from, works) = await corpus_schema.run_with_fallback(load, conn)
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
            **({key: r[key] for key in ("language", "note", "work_key", "passage_author",
                                        "voice", "superseded_by")}
               if "language" in r.keys() else {}),
            # Scanned edition, unofficial English and the Latin's link (2.4f).
            **(document_facts.text_labels(r) if "text_source" in r.keys() else {}),
        ) for r in passage_rows
    ]
    return ReaderChapter(
        document=_document_response(doc_row, works), chapter_key=chapter_key,
        chapter_label=passage_rows[0]["chapter_label"], passages=passages,
        prev_chapter_key=prev_key, next_chapter_key=next_key, highlight_anchor=highlight,
        redirected_from=redirected_from,
    )
