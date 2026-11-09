"""Retired passages and documents: tombstones and redirects (corpus cleanup 2.4a, D3).

The stage-then-apply writer (2.2w) never deletes a passage or document that leaves the
corpus. It sets `retired_at`, and records why in `corpus_tombstones` or where it went in
`corpus_redirects`. User rows (saved searches, bookmarks, reading progress) keep
pointing at the retired row, and this module says what to show for it:

  current  the row and its document are not retired (or nothing explains it);
  moved    a redirect names where the text now is;
  removed  a tombstone gives the reason, and the text is not shown (Carter, 9 Nov 2026).

Order of checks for a passage: current; else its passage redirect, followed up to three
hops to a current passage; else its passage tombstone; else its document's tombstone;
else its document's redirect; else current, with a warning (2.2w's D4 check makes that
impossible). Nothing here runs on a database without 0042 (`CorpusSchema.lifecycle`).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException

from app.corpus_schema import CorpusSchema
from app.models.corpus import Redirect, Tombstone

logger = logging.getLogger(__name__)

_MAX_HOPS = 3

# Reasons whose text can still be read elsewhere, by removal scope (1.2a, 1.3d; Carter,
# 31 Oct, 1 Nov and 4 Nov 2026; ADR 0001). A council gap passage (`passage` scope,
# `translation-in-preparation`) links out only in the councils collection.
_ELSEWHERE_DOCUMENT_REASONS = frozenset({"translation-in-preparation", "awaiting-permission"})
_ELSEWHERE_PASSAGE_REASONS = frozenset({"awaiting-permission"})
_ELSEWHERE_COUNCIL_PASSAGE_REASONS = frozenset({"translation-in-preparation"})


def _http_url(value) -> str | None:
    return value if isinstance(value, str) and value.startswith(("https://", "http://")) else None


def read_elsewhere_url(reason_code: str, collection: str | None, document_scope: bool,
                       metadata: dict | None) -> str | None:
    """Where a removed text can still be read, or None.

    Set for a retired document, or a passage of one, removed for permission or for a
    translation in preparation; for a passage removed alone awaiting permission; and for
    a councils passage removed alone for a translation in preparation (a gap passage).
    The link is the document's `metadata.held_text_url` when set (a partly rebuilt
    document or a rebuilt council with gaps), otherwise its `metadata.url`."""
    if document_scope:
        allowed = reason_code in _ELSEWHERE_DOCUMENT_REASONS
    else:
        allowed = reason_code in _ELSEWHERE_PASSAGE_REASONS or (
            collection == "councils" and reason_code in _ELSEWHERE_COUNCIL_PASSAGE_REASONS)
    if not allowed:
        return None
    metadata = metadata or {}
    return _http_url(metadata.get("held_text_url")) or _http_url(metadata.get("url"))


def tombstone(row) -> Tombstone:
    """A Tombstone from a `_TOMBSTONE_SQL` row."""
    snapshot = row["snapshot"] or {}
    collection = snapshot.get("collection") or row["collection"]
    document_scope = row["entity"] == "document" or bool(row["document_scope"])
    return Tombstone(
        entity=row["entity"], rule=row["rule"], reason_code=row["reason_code"],
        public_reason=row["public_reason"], church_act=row["church_act"],
        read_elsewhere_url=read_elsewhere_url(row["reason_code"], collection,
                                              document_scope, row["metadata"]),
        retired_at=row["retired_at"],
        title=snapshot.get("title"), author=snapshot.get("author"),
        reference=snapshot.get("reference"),
    )


def redirect(row) -> Redirect:
    """A Redirect from a `corpus_redirects` row."""
    entity = row["entity"]
    return Redirect(
        kind=row["kind"], document_id=str(row["new_document_id"]),
        anchor=row["new_anchor"] if entity in ("passage", "anchor") else None,
        chunk_id=str(row["new_id"]) if entity == "passage" and row["new_id"] else None,
        chapter_key=row["new_anchor"] if entity == "chapter" else None,
    )


@dataclass(frozen=True)
class Resolution:
    status: Literal["current", "moved", "removed"]
    redirect: Redirect | None = None
    tombstone: Tombstone | None = None


CURRENT = Resolution("current")

# A passage's tombstone, or its document's. `document_scope` says whether the document
# itself left (a passage of a removed document carries the document entry's reason).
_TOMBSTONE_SQL = """
    SELECT t.entity, t.id::text AS id, t.document_id::text AS document_id, t.retired_at,
           t.rule, t.reason_code, t.public_reason, t.church_act, t.snapshot,
           d.collection, d.metadata,
           EXISTS (SELECT 1 FROM corpus_tombstones dt
                   WHERE dt.entity = 'document' AND dt.id = t.document_id) AS document_scope
    FROM corpus_tombstones t
    LEFT JOIN documents d ON d.id = t.document_id
    WHERE (t.entity = 'passage' AND t.id = ANY($1::uuid[]))
       OR (t.entity = 'document' AND t.id = ANY($2::uuid[]))
"""

_REDIRECT_COLUMNS = """entity, old_id::text AS old_id, old_document_id::text AS old_document_id,
       old_anchor, new_id::text AS new_id, new_document_id::text AS new_document_id,
       new_anchor, kind"""

_STATE_SQL = """
    SELECT c.id::text AS id, c.document_id::text AS document_id,
           c.retired_at IS NULL AND d.retired_at IS NULL AS current,
           d.retired_at IS NOT NULL AS document_retired
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE c.id = ANY($1::uuid[])
"""


def _uuids(ids) -> list[uuid.UUID]:
    return [uuid.UUID(str(i)) for i in ids]


async def _follow_passage_redirects(conn, ids: set[str],
                                    ) -> tuple[dict[str, Redirect], dict[str, str]]:
    """Old passage ID -> the redirect to a current passage, following up to three hops.
    The redirect's kind is the first hop's: that is the change the reader made. Also
    returns, for a chain that ends at a passage that is not current, its last ID, so a
    later removal of the target is shown as removed rather than as the old text."""
    out: dict[str, Redirect] = {}
    pending = {i: i for i in ids}       # original id -> id at the current hop
    first: dict[str, dict] = {}
    last: dict[str, str] = {}           # original id -> furthest non-current id reached
    for _ in range(_MAX_HOPS):
        if not pending:
            break
        rows = await conn.fetch(
            f"SELECT {_REDIRECT_COLUMNS} FROM corpus_redirects "
            "WHERE entity = 'passage' AND old_id = ANY($1::uuid[])",
            _uuids(set(pending.values())))
        by_old = {r["old_id"]: r for r in rows}
        hops = {orig: by_old[at] for orig, at in pending.items() if at in by_old}
        if not hops:
            break
        for orig, row in hops.items():
            first.setdefault(orig, row)
        state = {r["id"]: r["current"] for r in await conn.fetch(
            _STATE_SQL, _uuids({r["new_id"] for r in hops.values()}))}
        pending = {}
        for orig, row in hops.items():
            if state.get(row["new_id"]):
                out[orig] = redirect(row).model_copy(update={"kind": first[orig]["kind"]})
            else:
                pending[orig] = last[orig] = row["new_id"]
    return out, last


async def resolve_passages(conn, ids, schema: CorpusSchema) -> dict[str, Resolution]:
    """What to show for each passage ID: current, moved (with the redirect) or removed
    (with the tombstone). IDs with no row are left out."""
    ids = sorted({str(i) for i in ids})
    if not ids or not schema.lifecycle:
        return {i: CURRENT for i in ids}
    states = {r["id"]: r for r in await conn.fetch(_STATE_SQL, _uuids(ids))}
    out = {i: CURRENT for i, s in states.items() if s["current"]}
    pending = {i for i, s in states.items() if not s["current"]}
    if not pending:
        return out

    terminal: dict[str, str] = {}
    if schema.redirects:
        moved, terminal = await _follow_passage_redirects(conn, pending)
        for i, r in moved.items():
            out[i] = Resolution("moved", redirect=r)
        pending -= set(out)

    if pending and schema.tombstones:
        documents = {states[i]["document_id"] for i in pending}
        rows = await conn.fetch(_TOMBSTONE_SQL, _uuids(pending | set(terminal.values())),
                                _uuids(documents))
        passage = {r["id"]: r for r in rows if r["entity"] == "passage"}
        document = {r["id"]: r for r in rows if r["entity"] == "document"}
        for i in list(pending):
            row = (passage.get(i) or document.get(states[i]["document_id"])
                   or passage.get(terminal.get(i)))
            if row is not None:
                out[i] = Resolution("removed", tombstone=tombstone(row))
                pending.discard(i)

    if pending and schema.redirects:
        retired_documents = {states[i]["document_id"] for i in pending
                             if states[i]["document_retired"]}
        moved = await _follow_document_redirects(conn, retired_documents)
        for i in list(pending):
            r = moved.get(states[i]["document_id"])
            if r is not None:
                out[i] = Resolution("moved", redirect=r)
                pending.discard(i)

    for i in pending:
        logger.warning("passage %s is retired but has no tombstone or redirect; "
                       "showing it as current", i)
        out[i] = CURRENT
    return out


async def _follow_document_redirects(conn, ids: set[str]) -> dict[str, Redirect]:
    out: dict[str, Redirect] = {}
    pending = {i: i for i in ids}
    first: dict[str, dict] = {}
    for _ in range(_MAX_HOPS):
        if not pending:
            break
        rows = await conn.fetch(
            f"SELECT {_REDIRECT_COLUMNS} FROM corpus_redirects "
            "WHERE entity = 'document' AND old_id = ANY($1::uuid[])",
            _uuids(set(pending.values())))
        by_old = {r["old_id"]: r for r in rows}
        hops = {orig: by_old[at] for orig, at in pending.items() if at in by_old}
        if not hops:
            break
        for orig, row in hops.items():
            first.setdefault(orig, row)
        live = {str(r["id"]) for r in await conn.fetch(
            "SELECT id FROM documents WHERE id = ANY($1::uuid[]) AND retired_at IS NULL",
            _uuids({r["new_document_id"] for r in hops.values()}))}
        pending = {}
        for orig, row in hops.items():
            if row["new_document_id"] in live:
                out[orig] = redirect(row).model_copy(update={"kind": first[orig]["kind"]})
            else:
                pending[orig] = row["new_document_id"]
    return out


async def resolve_document(conn, doc_id, schema: CorpusSchema) -> Resolution | None:
    """A document that is retired or missing: removed (its tombstone), moved (its
    redirect, which may name another document), or None when nothing explains it."""
    doc_id = str(doc_id)
    if not schema.lifecycle:
        return None
    if schema.tombstones:
        rows = await conn.fetch(_TOMBSTONE_SQL, [], _uuids([doc_id]))
        if rows:
            return Resolution("removed", tombstone=tombstone(rows[0]))
    if schema.redirects:
        moved = await _follow_document_redirects(conn, {doc_id})
        if doc_id in moved:
            return Resolution("moved", redirect=moved[doc_id])
    return None


async def _retired_anchor(conn, doc_uuid: uuid.UUID, anchor: str,
                          schema: CorpusSchema) -> Resolution | None:
    """The resolution of the retired passage that carries `anchor`, if not current."""
    passage = await conn.fetchval(
        "SELECT id::text FROM chunks WHERE document_id = $1 AND anchor = $2",
        doc_uuid, anchor)
    if passage is None:
        return None
    resolved = (await resolve_passages(conn, [passage], schema)).get(passage)
    return resolved if resolved is not None and resolved.status != "current" else None


async def resolve_location(conn, doc_id, *, anchor: str | None, chapter: str | None,
                           schema: CorpusSchema) -> Resolution | None:
    """An `?anchor=` or `?chapter=` that no visible passage of the document carries:
    moved (an anchor or chapter redirect, followed up to three hops to a location a
    visible passage carries, or the redirect of the retired passage the anchor names),
    removed (that passage's tombstone), or None.

    An anchor that a current passage gave up carries the suffix `#retired-<release>` on
    the retired row (2.2w); a link holding the suffix finds that row here."""
    if not schema.lifecycle:
        return None
    doc_uuid = uuid.UUID(str(doc_id))
    entity, old = ("anchor", anchor) if anchor else ("chapter", chapter)
    if old is None:
        return None
    column = "anchor" if entity == "anchor" else "chapter_key"
    first = last = None
    at_doc, at_key = doc_uuid, old
    if schema.redirects:
        # Each publish adds redirects from the locations live at that moment, so an
        # old link can need several hops (old -> middle -> new).
        for _ in range(_MAX_HOPS):
            row = await conn.fetchrow(
                f"SELECT {_REDIRECT_COLUMNS} FROM corpus_redirects "
                "WHERE entity = $1 AND old_document_id = $2 AND old_anchor = $3",
                entity, at_doc, at_key)
            if row is None or row["new_anchor"] is None:
                break
            first, last = first or row, row
            at_doc, at_key = uuid.UUID(row["new_document_id"]), row["new_anchor"]
            if await conn.fetchval(
                    f"SELECT EXISTS (SELECT 1 FROM chunks WHERE document_id = $1 "
                    f"AND {column} = $2 AND retired_at IS NULL)", at_doc, at_key):
                break
    if last is not None:
        if entity == "anchor" and (at_doc, at_key) != (doc_uuid, old):
            # The chain ends at an anchor no visible passage carries: that passage's
            # own redirect or tombstone, when it has one.
            resolved = await _retired_anchor(conn, at_doc, at_key, schema)
            if resolved is not None:
                return resolved
        return Resolution("moved", redirect=redirect(last).model_copy(
            update={"kind": first["kind"]}))
    if anchor:
        return await _retired_anchor(conn, doc_uuid, anchor, schema)
    return None


async def resolve_saved(conn, rows, schema: CorpusSchema, passage_sql: str,
                        ) -> tuple[dict[str, Resolution], dict[str, object]]:
    """For saved rows that name a passage (history restore, bookmarks): the resolution
    of each row whose `current` column is false, and the rows of the passages moved
    ones now point at, fetched with `passage_sql` (which takes `$1::uuid[]` and returns
    a `chunk_id` column). Rows without a `current` column (no 0042) resolve to nothing."""
    stale = [str(r["chunk_id"]) for r in rows if "current" in r.keys() and not r["current"]]
    if not stale:
        return {}, {}
    resolutions = await resolve_passages(conn, stale, schema)
    wanted = {r.redirect.chunk_id for r in resolutions.values()
              if r.status == "moved" and r.redirect.chunk_id}
    targets = ({str(t["chunk_id"]): t for t in await conn.fetch(passage_sql, _uuids(wanted))}
               if wanted else {})
    return resolutions, targets


class CorpusLifecycleError(HTTPException):
    """A reader request for a removed or moved document or passage.

    410 `{"detail": "removed", "tombstone": {...}}` or 404 `{"detail": "moved",
    "redirect": {...}}`; `app.main` renders the body. A subclass of HTTPException, so
    the routes' `except HTTPException: raise` passes it through."""

    def __init__(self, resolution: Resolution):
        if resolution.status == "removed":
            super().__init__(status_code=410, detail="removed")
            self.body = {"detail": "removed",
                         "tombstone": resolution.tombstone.model_dump(mode="json")}
        else:
            super().__init__(status_code=404, detail="moved")
            self.body = {"detail": "moved",
                         "redirect": resolution.redirect.model_dump(mode="json")}
        self.resolution = resolution
