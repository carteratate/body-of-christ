"""Apply a staged publish to live, switch the alias, roll back, clean up (2.2w, D2, D3).

`apply` moves the staged corpus into the live tables in one transaction:
  1. upsert documents (un-retiring any staged one), with `reader_access` derived again
     from the rights inventory, refusing when it differs from the staged value (D12);
     retire the documents of the staged collections that staging lacks; upsert works;
  2. move the live passages of the touched documents to temporary positions (and
     anchors), so nothing collides on the unique keys;
  3. upsert passages by ID: changed text keeps its ID (D1), new IDs insert, a staged ID
     that was retired is un-retired and loses its tombstone, a reclaimed ID loses its
     redirect, and a passage moved between documents keeps its ID;
  4. retire the live passages staging lacks: `retired_at` set and moved below every
     retired position of the document, never deleted (D3);
  5. write the staged tombstones and redirects;
  6. call the user-data remap (4.1a), or refuse when user rows point at a redirected ID
     and there is no remap yet;
  7. replace the touched documents' contents trees and refresh their reader outlines.
No DELETE is issued on `chunks` or `documents` anywhere in this module.

Inside the transaction, under the publish lock and before any write, the apply writes
the live rows it replaces to `releases/snapshots/<release>-before/`, which `rollback`
reads. `rollback` runs the same
core with the snapshot as the staged content, in one transaction, with the reverse remap,
then points the alias back.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Protocol

import reader_access
import registry as reg
import retirements
from publication import PUBLISH_LOCK_KEY, lock_publishes
from writers import reader_writer as rw

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_ROOT = os.path.join(DATAPIPELINE, "releases", "snapshots")
FLIPPED_POINTS = "flipped_points.json"
ROLLED_BACK_SENTENCE = "This passage was added in a corpus update that has been undone."
USER_TABLES = ("retrievals", "bookmarks", "retrieval_labels", "guest_trial_retrievals")
RETIRED_BASE = -1_000_000
ROLLBACK_WINDOW = timedelta(days=14)        # Carter, 4 Nov 2026 (4.1b step 12)


class ApplyRefused(ValueError):
    """An apply, switch, rollback or cleanup that must not run."""


# --------------------------------------------------------------------------- remap

@dataclass
class RemapLedger:
    """What a remap moved: public counts per table, for the publish log."""
    counts: dict[str, int] = field(default_factory=dict)


class UserDataRemap(Protocol):
    """4.1a implements this; the apply calls it inside its transaction (D11).
    `forward` moves user rows along this publish's redirects; `reverse` undoes only
    what forward's ledger recorded, skipping (and counting) rows changed since."""

    async def forward(self, conn, release: str, redirects: list[dict],
                      chapter_remap: list[dict]) -> RemapLedger: ...

    async def reverse(self, conn, release: str) -> RemapLedger: ...


async def referenced_redirects(conn) -> dict[str, int]:
    """User rows pointing at an ID or position the staged redirects move."""
    sql = "SELECT old_id FROM staging.corpus_redirects WHERE entity = 'passage'"
    tables = USER_TABLES
    # Feedback on a passage moves with the remap too (apply step 6); absent from schemas
    # without 0028, such as a rehearsal copy.
    if await conn.fetchval("SELECT to_regclass('public.product_feedback')") is not None:
        tables += ("product_feedback",)
    out = {t: await conn.fetchval(f"SELECT count(*) FROM public.{t} WHERE chunk_id IN ({sql})")
           for t in tables}
    out["reading_progress"] = await conn.fetchval(
        """SELECT count(*) FROM public.reading_progress r WHERE EXISTS (
             SELECT 1 FROM staging.corpus_redirects x WHERE x.old_document_id = r.document_id
               AND ((x.entity = 'chapter' AND x.old_anchor = r.chapter_key)
                 OR (x.entity = 'anchor' AND x.old_anchor = r.anchor)))""")
    return {t: n for t, n in out.items() if n}


# --------------------------------------------------------------------------- snapshot

def _rows_sql(table: str, columns: tuple[str, ...], where: str) -> str:
    return f"SELECT {', '.join(columns)} FROM public.{table} t WHERE {where}"


SNAPSHOT_TABLES = {
    "documents": rw.DOCUMENT_COLUMNS,
    "chunks": rw.CHUNK_COLUMNS,
    "document_works": rw.WORK_COLUMNS,
    "document_contents": rw.CONTENTS_COLUMNS,
    "document_chapters": ("document_id", "ordinal", "chapter_key", "chapter_label"),
}
REDIRECT_ROW = ("entity", "old_id", "old_document_id", "old_anchor", "new_id",
                "new_document_id", "new_anchor", "kind", "publish_id", "created_at")


def _document_scope(collections: list[str] | None, document_ids: list[str] | None) -> str:
    return ("t.collection = ANY($1::text[])" if collections is not None
            else "t.id = ANY($1::uuid[])")


async def read_snapshot_rows(conn, collections: list[str] | None = None,
                             document_ids: list[str] | None = None,
                             *, staged: bool = True) -> dict[str, list[dict]]:
    """The live rows an apply (or a retire-only apply) replaces: the non-retired corpus
    rows of the staged collections (or of `document_ids`), and the tombstone and redirect
    rows the apply deletes (only when `staged`)."""
    arg = collections if collections is not None else document_ids
    scope = _document_scope(collections, document_ids)
    documents = f"SELECT t.id FROM public.documents t WHERE {scope} AND t.retired_at IS NULL"
    out = {"documents": [dict(r) for r in await conn.fetch(
        _rows_sql("documents", rw.DOCUMENT_COLUMNS, f"{scope} AND t.retired_at IS NULL"), arg)]}
    out["chunks"] = [dict(r) for r in await conn.fetch(
        _rows_sql("chunks", rw.CHUNK_COLUMNS,
                  f"t.document_id IN ({documents}) AND t.retired_at IS NULL"), arg)]
    for table in ("document_works", "document_contents", "document_chapters"):
        out[table] = [dict(r) for r in await conn.fetch(
            _rows_sql(table, SNAPSHOT_TABLES[table], f"t.document_id IN ({documents})"), arg)]
    out["corpus_tombstones"], out["corpus_redirects"] = [], []
    if staged:
        out["corpus_tombstones"] = [dict(r) for r in await conn.fetch(
            f"""SELECT {', '.join(rw.TOMBSTONE_COLUMNS)} FROM public.corpus_tombstones t
                WHERE t.id IN (SELECT id FROM staging.chunks UNION SELECT id FROM staging.documents)""")]
        out["corpus_redirects"] = [dict(r) for r in await conn.fetch(
            f"""SELECT {', '.join(REDIRECT_ROW)} FROM public.corpus_redirects t
                WHERE (t.entity = 'passage' AND t.old_id IN (
                         SELECT id FROM staging.chunks
                         UNION SELECT old_id FROM staging.corpus_redirects WHERE entity = 'passage'))
                   OR (t.entity IN ('anchor', 'chapter') AND EXISTS (
                         SELECT 1 FROM staging.corpus_redirects s WHERE s.entity = t.entity
                           AND s.old_document_id = t.old_document_id
                           AND s.old_anchor = t.old_anchor))
                   OR (t.entity = 'document' AND t.old_id IN (
                         SELECT id FROM staging.documents
                         UNION SELECT old_id FROM staging.corpus_redirects WHERE entity = 'document'))""")]
    return out


def snapshot_dir(release: str, root: str = SNAPSHOT_ROOT) -> str:
    return os.path.join(root, f"{release}-before")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_snapshot(rows: dict[str, list[dict]], directory: str, *,
                   replace: bool = False) -> dict[str, str]:
    """Write one gzipped JSONL file per table (corpus text only, no user data) and return
    {file: sha256}. 4.1a's remap adds its private ledger to the same folder later in the
    apply transaction (`remap_user_data.LEDGER_FILE`), with its sha256. An existing snapshot is replaced only when `replace` (its publish was
    never applied, so nothing can roll back to it)."""
    if os.path.exists(directory):
        if not replace:
            raise ApplyRefused(f"REFUSING: {directory} exists; the before-snapshot of an "
                               "applied publish is never overwritten")
        import shutil
        shutil.rmtree(directory)
    os.makedirs(directory)
    hashes = {}
    for table, table_rows in rows.items():
        name = f"{table}.jsonl.gz"
        path = os.path.join(directory, name)
        with gzip.GzipFile(path, "wb", mtime=0) as f:
            for r in table_rows:
                f.write((json.dumps(r, default=str, ensure_ascii=False) + "\n").encode())
        hashes[name] = _sha256(path)
    return hashes


def read_snapshot(directory: str, expected: dict[str, str]) -> dict[str, list[dict]]:
    """The snapshot's rows, after checking every file against the recorded sha256s."""
    for name, digest in expected.items():
        path = os.path.join(directory, name)
        if not os.path.exists(path) or _sha256(path) != digest:
            raise ApplyRefused(f"REFUSING: {path} is missing or differs from its recorded "
                               "sha256")
    out = {}
    for name in expected:
        if name.endswith(".jsonl.gz"):
            with gzip.open(os.path.join(directory, name), "rt", encoding="utf-8") as f:
                out[name.removesuffix(".jsonl.gz")] = [json.loads(line) for line in f if line.strip()]
    return out


# --------------------------------------------------------------------------- core

@dataclass
class CoreResult:
    touched: list[str]
    retired_documents: list[str]
    retired_passages: list[str]
    inserted_passages: list[str]


def _set(columns: tuple[str, ...], skip: tuple[str, ...] = ("id",)) -> str:
    return ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in skip)


async def _core(conn, scope_documents: list[str], *, release: str,
                rollback: bool = False) -> CoreResult:
    """Steps 1 to 4 and the contents trees, from the staging tables. `scope_documents`
    are the live documents considered: any of them staging lacks is retired, and so is
    any of their live passages staging lacks."""
    staged_documents = [str(r["id"]) for r in await conn.fetch("SELECT id FROM staging.documents")]
    retire_documents = [d for d in scope_documents if d not in set(staged_documents)]
    touched = sorted(set(staged_documents) | set(scope_documents))
    before = {str(r["id"]) for r in await conn.fetch(
        "SELECT id FROM public.chunks WHERE id IN (SELECT id FROM staging.chunks)")}

    # 1. Documents and works.
    doc_cols = ", ".join(rw.DOCUMENT_COLUMNS)
    await conn.execute(
        f"""INSERT INTO public.documents ({doc_cols})
            SELECT {doc_cols} FROM staging.documents
            ON CONFLICT (id) DO UPDATE SET {_set(rw.DOCUMENT_COLUMNS)}, retired_at = NULL""")
    if retire_documents:
        await conn.execute(
            """UPDATE public.documents SET retired_at = now()
               WHERE id = ANY($1::uuid[]) AND retired_at IS NULL""", retire_documents)
    # Park the live works above every ordinal the staged ones take. A rollback's staging
    # (the before-snapshot) can hold a work an earlier publish already parked, so it parks
    # them on the next free ordinals above the highest on either side.
    if not rollback:
        await conn.execute(
            """UPDATE public.document_works SET ordinal = ordinal + 1000000
               WHERE document_id IN (SELECT id FROM staging.documents)""")
    else:
        await conn.execute(
            """UPDATE public.document_works w SET ordinal = p.top + p.rn
               FROM (SELECT x.document_id, x.work_key,
                            row_number() OVER (PARTITION BY x.document_id ORDER BY x.ordinal) AS rn,
                            greatest(max(x.ordinal) OVER (PARTITION BY x.document_id),
                                     coalesce((SELECT max(s.ordinal) FROM staging.document_works s
                                               WHERE s.document_id = x.document_id), 0)) AS top
                     FROM public.document_works x
                     WHERE x.document_id IN (SELECT id FROM staging.documents)) p
               WHERE w.document_id = p.document_id AND w.work_key = p.work_key""")
    work_cols = ", ".join(rw.WORK_COLUMNS)
    await conn.execute(
        f"""INSERT INTO public.document_works ({work_cols})
            SELECT {work_cols} FROM staging.document_works
            ON CONFLICT (document_id, work_key) DO UPDATE SET
              {_set(rw.WORK_COLUMNS, ('document_id', 'work_key'))}""")

    # 2. Live passages of the touched documents out of the way, and any anchor a retired
    # row still holds that a staged passage now carries (a returning text, 1.8d).
    await conn.execute(
        """UPDATE public.chunks c SET anchor = c.anchor || '#retired-' || $2
           WHERE c.document_id = ANY($1::uuid[]) AND c.retired_at IS NOT NULL
             AND c.id NOT IN (SELECT id FROM staging.chunks)
             AND (c.document_id, c.anchor) IN (SELECT document_id, anchor FROM staging.chunks)""",
        touched, release)
    await conn.execute(
        """UPDATE public.chunks SET position = -position - 1,
                  anchor = CASE WHEN anchor IS NULL THEN NULL ELSE '~' || anchor END
           WHERE document_id = ANY($1::uuid[]) AND retired_at IS NULL""", touched)

    # 3. Passages by ID; annotations are never written by a publish.
    chunk_cols = ", ".join(rw.CHUNK_COLUMNS)
    await conn.execute(
        f"""INSERT INTO public.chunks ({chunk_cols})
            SELECT {chunk_cols} FROM staging.chunks
            ON CONFLICT (id) DO UPDATE SET {_set(rw.CHUNK_COLUMNS)}, retired_at = NULL""")
    if not rollback:
        # A live passage never also shows a removal notice or resolves as moved.
        await conn.execute(
            """DELETE FROM public.corpus_tombstones
               WHERE id IN (SELECT id FROM staging.chunks UNION SELECT id FROM staging.documents)""")
        await conn.execute(
            """DELETE FROM public.corpus_redirects
               WHERE (entity = 'passage' AND old_id IN (SELECT id FROM staging.chunks))
                  OR (entity = 'document' AND old_id IN (SELECT id FROM staging.documents))""")

    # 4. Retire what staging lacks, below every retired position of its document. An
    # anchor a staged passage now carries (a piece whose text moved, 1.10b) is kept with
    # a suffix, since the unique key on (document_id, anchor) covers retired rows too.
    retired = await conn.fetch(
        """
        WITH r AS (
            SELECT c.id, c.document_id,
                   row_number() OVER (PARTITION BY c.document_id ORDER BY c.position DESC) AS rn
            FROM public.chunks c
            WHERE c.document_id = ANY($1::uuid[]) AND c.retired_at IS NULL
              AND c.id NOT IN (SELECT id FROM staging.chunks)),
        b AS (
            SELECT d AS document_id,
                   LEAST($2::int, coalesce((SELECT min(position) - 1 FROM public.chunks
                                            WHERE document_id = d AND retired_at IS NOT NULL),
                                           $2::int)) AS base
            FROM unnest($1::uuid[]) AS d)
        UPDATE public.chunks c
        SET retired_at = now(), position = b.base - (r.rn - 1)::int,
            anchor = CASE
                WHEN c.anchor IS NULL THEN NULL
                WHEN EXISTS (SELECT 1 FROM public.chunks o WHERE o.document_id = c.document_id
                               AND o.anchor = substr(c.anchor, 2) AND o.id <> c.id)
                    THEN substr(c.anchor, 2) || '#retired-' || $3
                ELSE substr(c.anchor, 2) END
        FROM r JOIN b USING (document_id)
        WHERE c.id = r.id
        RETURNING c.id
        """, touched, RETIRED_BASE, release)
    leftover = await conn.fetchval(
        """SELECT count(*) FROM public.chunks
           WHERE document_id = ANY($1::uuid[]) AND anchor LIKE '~%'""", touched)
    if leftover:
        raise ApplyRefused(f"REFUSING: {leftover} passages kept a temporary anchor")

    # Contents trees of the staged documents (decided by Carter on 2 Nov 2026).
    await conn.execute(
        "DELETE FROM public.document_contents WHERE document_id IN (SELECT id FROM staging.documents)")
    contents_cols = ", ".join(rw.CONTENTS_COLUMNS)
    await conn.execute(
        f"""INSERT INTO public.document_contents ({contents_cols})
            SELECT {contents_cols} FROM staging.document_contents ORDER BY document_id, ordinal""")
    # Works no staged or retired passage names any more. A rollback's staging is the
    # before-snapshot, which holds every work its documents had, so it restores exactly
    # those: a work the publish added goes. Only retired rows can still name one (a
    # restored row names a snapshot work), whether this rollback or an earlier one retired
    # them, so they let go of it first.
    if rollback:
        await conn.execute(
            """UPDATE public.chunks c SET work_key = NULL
               WHERE c.retired_at IS NOT NULL AND c.work_key IS NOT NULL
                 AND c.document_id IN (SELECT id FROM staging.documents)
                 AND (c.document_id, c.work_key) NOT IN
                     (SELECT document_id, work_key FROM staging.document_works)""")
    named_elsewhere = "" if rollback else """
             AND NOT EXISTS (SELECT 1 FROM public.chunks c
                             WHERE c.document_id = w.document_id AND c.work_key = w.work_key)"""
    await conn.execute(
        f"""DELETE FROM public.document_works w
           WHERE w.document_id IN (SELECT id FROM staging.documents)
             AND (w.document_id, w.work_key) NOT IN (SELECT document_id, work_key FROM staging.document_works){named_elsewhere}""")
    staged = {str(r["id"]) for r in await conn.fetch("SELECT id FROM staging.chunks")}
    return CoreResult(touched=touched, retired_documents=retire_documents,
                      retired_passages=[str(r["id"]) for r in retired],
                      inserted_passages=sorted(staged - before))


async def _refresh(conn, documents: list[str]) -> None:
    for d in documents:
        await conn.execute("SELECT refresh_document_outline($1::uuid)", d)


async def _check_reader_access(conn) -> None:
    """D12: the staged reader_access must equal the inventory's verdict now."""
    differ = [f"{r['id']} staged {r['reader_access']}, inventory {reader_access.access_for(str(r['id']))}"
              for r in await conn.fetch("SELECT id, reader_access FROM staging.documents")
              if reader_access.access_for(str(r["id"])) != r["reader_access"]]
    if differ:
        raise ApplyRefused("REFUSING: reader access changed since the stage; stage again: "
                           + "; ".join(differ[:10]))


async def _live_documents(conn, collections: list[str]) -> list[str]:
    return [str(r["id"]) for r in await conn.fetch(
        """SELECT id FROM public.documents
           WHERE collection = ANY($1::text[]) AND retired_at IS NULL""", collections)]


# --------------------------------------------------------------------------- apply

@dataclass
class ApplyResult:
    release: str
    touched: int
    inserted: int
    retired_passages: int
    retired_documents: int
    tombstones: int
    redirects: int
    remap: dict[str, int]


async def apply(conn, release: str, *, remap: UserDataRemap | None = None,
                root: str = SNAPSHOT_ROOT, fail_after_retire=None) -> ApplyResult:
    """Snapshot, then the apply transaction. `fail_after_retire` is a test hook."""
    from release.staged import staged_content_sha256

    async with conn.transaction():
        await conn.execute("SET LOCAL lock_timeout = '2s'")
        await lock_publishes(conn)
        row = await conn.fetchrow("SELECT * FROM corpus_publishes WHERE id = $1", release)
        _check_applicable(row, release)
        collections = list(row["collections"])
        # The before-snapshot is read here, under the publish lock and before any write, so
        # a concurrent apply of the same release cannot overwrite it with applied rows. The
        # publish is unapplied, so an earlier refused attempt's snapshot is safe to replace.
        hashes = write_snapshot(await read_snapshot_rows(conn, collections),
                                snapshot_dir(release, root), replace=True)
        await conn.execute("UPDATE corpus_publishes SET snapshot_sha256 = $2::jsonb WHERE id = $1",
                           release, json.dumps(hashes))
        if row["report_sha256"].split(":")[-1] != await staged_content_sha256(conn):
            raise ApplyRefused("REFUSING: staging changed since the report; run "
                               "`publish.py report` again")
        await _check_reader_access(conn)
        referenced = await referenced_redirects(conn)
        if referenced and remap is None:
            raise ApplyRefused(
                "REFUSING: user rows point at IDs this publish redirects, and the user-data "
                "remap (4.1a) is not merged: "
                + ", ".join(f"{t} {n}" for t, n in referenced.items()))

        core = await _core(conn, await _live_documents(conn, collections), release=release)
        explained = {str(r["id"]) for r in await conn.fetch(
            """SELECT id FROM staging.corpus_tombstones WHERE entity = 'passage'
               UNION SELECT old_id FROM staging.corpus_redirects WHERE entity = 'passage'""")}
        unexplained = [i for i in core.retired_passages if i not in explained]
        if unexplained:
            raise ApplyRefused(f"REFUSING: {len(unexplained)} retirements are unexplained "
                               f"(D4), first {unexplained[0]}")
        if fail_after_retire is not None:
            await fail_after_retire(conn)

        # 5. Tombstones and redirects, replacing any older row for the same old anchor.
        await conn.execute(
            """DELETE FROM public.corpus_redirects t USING staging.corpus_redirects s
               WHERE s.entity = t.entity AND (
                 (t.entity IN ('anchor', 'chapter') AND s.old_document_id = t.old_document_id
                   AND s.old_anchor = t.old_anchor)
                 OR (t.entity IN ('passage', 'document') AND s.old_id = t.old_id))""")
        tomb_cols = ", ".join(c for c in rw.TOMBSTONE_COLUMNS if c != "retired_at")
        tombstones = await conn.execute(
            f"""INSERT INTO public.corpus_tombstones ({tomb_cols}, retired_at)
                SELECT {tomb_cols}, now() FROM staging.corpus_tombstones""")
        red_cols = ", ".join(rw.REDIRECT_COLUMNS)
        redirects = await conn.execute(
            f"""INSERT INTO public.corpus_redirects ({red_cols})
                SELECT {red_cols} FROM staging.corpus_redirects ORDER BY id""")

        # 6. User rows move in the same commit.
        ledger = RemapLedger()
        if remap is not None:
            redirect_rows = [dict(r) for r in await conn.fetch(
                "SELECT * FROM staging.corpus_redirects WHERE entity <> 'chapter' ORDER BY id")]
            chapter_rows = [dict(r) for r in await conn.fetch(
                "SELECT * FROM staging.corpus_redirects WHERE entity = 'chapter' ORDER BY id")]
            ledger = await remap.forward(conn, release, redirect_rows, chapter_rows)

        # 7. Outlines last.
        await _refresh(conn, core.touched)
        await conn.execute("UPDATE corpus_publishes SET applied_at = now() WHERE id = $1", release)

    return ApplyResult(release=release, touched=len(core.touched),
                       inserted=len(core.inserted_passages),
                       retired_passages=len(core.retired_passages),
                       retired_documents=len(core.retired_documents),
                       tombstones=int(tombstones.split()[-1]),
                       redirects=int(redirects.split()[-1]), remap=ledger.counts)


def _check_applicable(row, release: str) -> None:
    if row is None:
        raise ApplyRefused(f"REFUSING: no publish named '{release}'")
    for column in ("applied_at", "discarded_at", "cleaned_up_at"):
        if row[column] is not None:
            raise ApplyRefused(f"REFUSING: publish '{release}' was {column.removesuffix('_at')}")
    if row["staged_at"] is None:
        raise ApplyRefused(f"REFUSING: publish '{release}' is not staged")
    if not row["report_sha256"]:
        raise ApplyRefused(f"REFUSING: publish '{release}' has no passing report; run "
                           "`publish.py report` first")


# --------------------------------------------------------------------------- switch

async def switch(conn, qdrant, release: str, alias: str) -> tuple[str | None, str]:
    """Point `alias` at the publish's collection in one alias call; record the old one.
    Holds the publish lock throughout, and records the old target before the alias moves,
    so a retry after a lost response keeps it."""
    from qdrant_client.models import (CreateAlias, CreateAliasOperation, DeleteAlias,
                                      DeleteAliasOperation)

    from writers.qdrant import alias_target

    await conn.execute("SELECT pg_advisory_lock(hashtext($1))", PUBLISH_LOCK_KEY)
    try:
        row = await conn.fetchrow("SELECT * FROM corpus_publishes WHERE id = $1", release)
        if row is None or row["applied_at"] is None or row["rolled_back_at"] is not None:
            raise ApplyRefused(f"REFUSING: publish '{release}' is not applied")
        await _refuse_if_superseded(conn, row)
        new = row["qdrant_collection"]
        old = await alias_target(qdrant, alias)
        if old != new:
            await conn.execute(
                """UPDATE corpus_publishes
                   SET previous_qdrant_collection = coalesce(previous_qdrant_collection, $2)
                   WHERE id = $1""", release, old)
            operations = ([DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias))]
                          if old is not None else [])
            operations.append(CreateAliasOperation(create_alias=CreateAlias(
                collection_name=new, alias_name=alias)))
            await qdrant.update_collection_aliases(change_aliases_operations=operations)
        await conn.execute("UPDATE corpus_publishes SET alias_switched_at = now() WHERE id = $1",
                           release)
    finally:
        await conn.execute("SELECT pg_advisory_unlock(hashtext($1))", PUBLISH_LOCK_KEY)
    return old, new


async def point_alias(qdrant, alias: str, collection: str) -> None:
    from qdrant_client.models import (CreateAlias, CreateAliasOperation, DeleteAlias,
                                      DeleteAliasOperation)

    from writers.qdrant import alias_target

    current = await alias_target(qdrant, alias)
    if current == collection:
        return
    operations = ([DeleteAliasOperation(delete_alias=DeleteAlias(alias_name=alias))]
                  if current is not None else [])
    operations.append(CreateAliasOperation(create_alias=CreateAlias(
        collection_name=collection, alias_name=alias)))
    await qdrant.update_collection_aliases(change_aliases_operations=operations)


# --------------------------------------------------------------------------- rollback

async def _load_snapshot_into_staging(conn, rows: dict[str, list[dict]]) -> None:
    await rw.ensure_staging(conn)
    for table in rw.STAGED_TABLES:
        await conn.execute(f"DELETE FROM staging.{table}")
    for d in rows["documents"]:
        # D12: the stricter of the snapshot and the inventory as it stands now. The
        # inventory alone would open an older edition under its replacement's row, and
        # the snapshot alone would reopen a text whose permission was withdrawn.
        d["reader_access"] = reader_access.stricter(d["reader_access"],
                                                    reader_access.access_for(d["id"]))
        # A snapshot taken before documents.form was written (issue #330) has no form.
        await conn.execute(rw._DOCUMENT_SQL, *[d.get(c) for c in rw.DOCUMENT_COLUMNS])
    await conn.executemany(rw._WORK_SQL, [tuple(r[c] for c in rw.WORK_COLUMNS)
                                          for r in rows["document_works"]])
    await conn.executemany(rw._CHUNK_SQL, [tuple(r[c] for c in rw.CHUNK_COLUMNS)
                                           for r in rows["chunks"]])
    await conn.executemany(rw._CONTENTS_SQL, [tuple(r[c] for c in rw.CONTENTS_COLUMNS)
                                              for r in rows["document_contents"]])


async def _reinsert(conn, rows: dict[str, list[dict]]) -> None:
    """Put back the tombstone and redirect rows the forward apply deleted."""
    tomb_cols = ", ".join(rw.TOMBSTONE_COLUMNS)
    for t in rows.get("corpus_tombstones", []):
        await conn.execute(
            f"""INSERT INTO public.corpus_tombstones ({tomb_cols}) VALUES
                ($1, $2::uuid, $3::uuid, $4::text::timestamptz, $5, $6, $7, $8, $9, $10, $11::jsonb)""",
            *[t[c] for c in rw.TOMBSTONE_COLUMNS])
    red_cols = ", ".join(REDIRECT_ROW)
    for r in rows.get("corpus_redirects", []):
        await conn.execute(
            f"""INSERT INTO public.corpus_redirects ({red_cols}) VALUES
                ($1, $2::uuid, $3::uuid, $4, $5::uuid, $6::uuid, $7, $8, $9, $10::text::timestamptz)""",
            *[r[c] for c in REDIRECT_ROW])


async def _rolled_back_tombstones(conn, release: str, documents: list[str],
                                  passages: list[str]) -> None:
    await conn.execute(
        """INSERT INTO public.corpus_tombstones
             (entity, id, document_id, retired_at, publish_id, removal_key, rule, reason_code,
              public_reason, church_act, snapshot)
           SELECT 'passage', c.id, c.document_id, now(), $1, NULL, 'other', $3, $4, NULL,
                  jsonb_build_object('collection', d.collection, 'title', d.title,
                                     'author', d.author, 'reference', c.reference,
                                     'chapter_label', c.chapter_label)
           FROM public.chunks c JOIN public.documents d ON d.id = c.document_id
           WHERE c.id = ANY($2::uuid[])""", release, passages, reg.ROLLED_BACK,
        ROLLED_BACK_SENTENCE)
    await conn.execute(
        """INSERT INTO public.corpus_tombstones
             (entity, id, document_id, retired_at, publish_id, removal_key, rule, reason_code,
              public_reason, church_act, snapshot)
           SELECT 'document', d.id, d.id, now(), $1, NULL, 'other', $3, $4, NULL,
                  jsonb_build_object('collection', d.collection, 'title', d.title,
                                     'author', d.author, 'reference', NULL,
                                     'chapter_label', NULL)
           FROM public.documents d WHERE d.id = ANY($2::uuid[])""", release, documents,
        reg.ROLLED_BACK, ROLLED_BACK_SENTENCE)


@dataclass
class RollbackResult:
    release: str
    restored_passages: int
    retired_passages: int
    retired_documents: int
    remap: dict[str, int]
    alias: str | None


async def rollback(conn, qdrant, release: str, *, alias: str,
                   remap: UserDataRemap | None = None,
                   root: str = SNAPSHOT_ROOT) -> RollbackResult:
    """Undo an applied publish from its before-snapshot (D11): one transaction, then the
    alias back (or, for a retire-only publish, the flipped points searchable again). The
    publish lock is held from the first read to the alias restore, so no cleanup or other
    rollback can run between the commit and the alias."""
    await conn.execute("SELECT pg_advisory_lock(hashtext($1))", PUBLISH_LOCK_KEY)
    try:
        return await _rollback(conn, qdrant, release, alias=alias, remap=remap, root=root)
    finally:
        await conn.execute("SELECT pg_advisory_unlock(hashtext($1))", PUBLISH_LOCK_KEY)


async def _rollback(conn, qdrant, release: str, *, alias: str,
                    remap: UserDataRemap | None, root: str) -> RollbackResult:
    row = await conn.fetchrow("SELECT * FROM corpus_publishes WHERE id = $1", release)
    if row is None or row["applied_at"] is None:
        raise ApplyRefused(f"REFUSING: publish '{release}' is not applied")
    directory = snapshot_dir(release, root)
    retire_only = row["staged_at"] is None
    if row["rolled_back_at"] is not None:
        # The database reversal committed; finish the Qdrant step, which a retry repeats
        # safely (it may have failed the first time), unless a later publish now owns it.
        async with conn.transaction():
            await lock_publishes(conn)
            # Only while nothing has been applied or rolled back since, so the restore
            # cannot overwrite a newer state; inside the lock, so none can start meanwhile.
            moved_on = await conn.fetchval(
                """SELECT id FROM corpus_publishes WHERE id <> $1
                   AND (applied_at > $2 OR rolled_back_at > $2) LIMIT 1""",
                release, row["rolled_back_at"])
            if moved_on is not None:
                raise ApplyRefused(f"REFUSING: publish '{moved_on}' changed live after "
                                   f"'{release}' was rolled back; nothing to finish")
            target = await _restore_qdrant(qdrant, row, directory, alias, retire_only)
        return RollbackResult(release=release, restored_passages=0, retired_passages=0,
                              retired_documents=0, remap={}, alias=target)
    expected = row["snapshot_sha256"]
    expected = json.loads(expected) if isinstance(expected, str) else expected
    rows = read_snapshot(directory, expected)

    async with conn.transaction():
        await conn.execute("SET LOCAL lock_timeout = '2s'")
        await lock_publishes(conn)
        # Re-read under the lock: an overlapping rollback may have finished meanwhile.
        row = await conn.fetchrow("SELECT * FROM corpus_publishes WHERE id = $1", release)
        if row["rolled_back_at"] is not None:
            raise ApplyRefused(f"REFUSING: publish '{release}' was rolled back meanwhile")
        # After the window, 4.1b step 13 may have deleted retired rows (which the
        # snapshot cannot fully restore) and the previous Qdrant collection.
        if await conn.fetchval("SELECT now() >= $1::timestamptz + $2::interval",
                               row["applied_at"], ROLLBACK_WINDOW):
            raise ApplyRefused(f"REFUSING: the {ROLLBACK_WINDOW.days}-day rollback window of "
                               f"'{release}' has closed")
        await _refuse_if_superseded(conn, row)
        holder = await conn.fetchval(
            """SELECT id FROM corpus_publishes WHERE id <> $1 AND cleaned_up_at IS NULL
               AND discarded_at IS NULL LIMIT 1""", release)
        if holder is not None:
            raise ApplyRefused(f"REFUSING: staging holds publish '{holder}'; clean it up or "
                               "discard it first")
        await _load_snapshot_into_staging(conn, rows)
        scope = ([d["id"] for d in rows["documents"]] if retire_only
                 else await _live_documents(conn, list(row["collections"])))
        core = await _core(conn, scope, release=release, rollback=True)
        ledger = RemapLedger()
        if remap is not None:
            ledger = await remap.reverse(conn, release)
        await conn.execute("DELETE FROM public.corpus_redirects WHERE publish_id = $1", release)
        await conn.execute("DELETE FROM public.corpus_tombstones WHERE publish_id = $1", release)
        await _reinsert(conn, rows)
        # Rows the publish inserted get a rolled-back tombstone. A row it un-retired is
        # retired again under the tombstone or redirect it had before, put back above.
        restored = {str(t["id"]) for t in rows.get("corpus_tombstones", [])} | {
            str(r["old_id"]) for r in rows.get("corpus_redirects", [])
            if r["entity"] in ("passage", "document")}
        await _rolled_back_tombstones(
            conn, release, [d for d in core.retired_documents if d not in restored],
            [p for p in core.retired_passages if p not in restored])
        await _refresh(conn, core.touched)
        # Staging now holds the snapshot: it must be cleaned up before the next stage.
        await conn.execute(
            """UPDATE corpus_publishes SET rolled_back_at = now(), cleaned_up_at = NULL
               WHERE id = $1""", release)

    target = await _restore_qdrant(qdrant, row, directory, alias, retire_only)
    return RollbackResult(release=release, restored_passages=len(rows["chunks"]),
                          retired_passages=len(core.retired_passages),
                          retired_documents=len(core.retired_documents),
                          remap=ledger.counts, alias=target)


async def _refuse_if_superseded(conn, row) -> None:
    """Refuse while a publish applied after this one is still in place: undoing this one
    would put live, and the alias, back under it."""
    newer = await conn.fetchval(
        """SELECT id FROM corpus_publishes WHERE id <> $1 AND applied_at > $2
           AND rolled_back_at IS NULL ORDER BY applied_at DESC LIMIT 1""",
        row["id"], row["applied_at"])
    if newer is not None:
        raise ApplyRefused(f"REFUSING: publish '{newer}' was applied after "
                           f"'{row['id']}'; roll it back first")


async def _restore_qdrant(qdrant, row, directory: str, alias: str, retire_only: bool) -> str | None:
    """Undo the publish in Qdrant: the flipped points searchable again for a retire-only
    publish, else the alias back on the previous collection. Repeatable."""
    if retire_only:
        await set_searchable(qdrant, row["qdrant_collection"], _flipped(directory), True)
        return None
    if row["previous_qdrant_collection"]:
        await point_alias(qdrant, alias, row["previous_qdrant_collection"])
        return row["previous_qdrant_collection"]
    return None


# --------------------------------------------------------------------------- cleanup

async def cleanup(conn, release: str) -> None:
    """Drop the staging tables once the apply (or rollback) is checked. Rollback stays
    possible: it rebuilds staging from the snapshot."""
    async with conn.transaction():
        await lock_publishes(conn)
        row = await conn.fetchrow("SELECT * FROM corpus_publishes WHERE id = $1", release)
        if row is None or row["applied_at"] is None:
            raise ApplyRefused(f"REFUSING: publish '{release}' is not applied; discard an "
                               "unapplied publish instead")
        if row["cleaned_up_at"] is not None:
            raise ApplyRefused(f"REFUSING: publish '{release}' is already cleaned up")
        await conn.execute("SELECT public.drop_corpus_staging()")
        await conn.execute("UPDATE corpus_publishes SET cleaned_up_at = now() WHERE id = $1",
                           release)


# --------------------------------------------------------------------------- retire only

async def set_searchable(qdrant, collection: str, ids: list[str], value: bool) -> None:
    for start in range(0, len(ids), 256):
        await qdrant.set_payload(collection, payload={"searchable": value},
                                 points=ids[start:start + 256], wait=True)


def _flipped(directory: str) -> list[str]:
    path = os.path.join(directory, FLIPPED_POINTS)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def retire_only(conn, qdrant, release: str, collection: str, *, alias: str,
                      registry: reg.WorkRegistry | None = None,
                      root: str = SNAPSHOT_ROOT) -> dict:
    """Retire the live documents an open `document` removal entry names in `collection`,
    with their passages, and nothing else (the On the Incarnation procedure, D7). No
    staging and no new Qdrant collection: the points stay, marked not searchable."""
    from datetime import datetime, timezone

    from writers.qdrant import alias_target

    registry = registry or reg.current()
    entries = {e["document_id"]: e for e in reg.open_removals(registry)
               if e.get("scope") == "document" and e.get("collection") == collection}
    live = await conn.fetch(
        """SELECT id::text AS id, title, author FROM public.documents
           WHERE collection = $1 AND retired_at IS NULL AND id = ANY($2::uuid[])""",
        collection, list(entries))
    if not live:
        raise ApplyRefused(f"REFUSING: no live document of '{collection}' has an open "
                           "document removal entry")
    target = await alias_target(qdrant, alias)
    if target is None:
        raise ApplyRefused(f"REFUSING: there is no Qdrant alias '{alias}'")
    documents = [r["id"] for r in live]

    at = datetime.now(timezone.utc)
    async with conn.transaction():
        await conn.execute("SET LOCAL lock_timeout = '2s'")
        await lock_publishes(conn)
        if await conn.fetchval("SELECT 1 FROM corpus_publishes WHERE id = $1", release):
            raise ApplyRefused(f"REFUSING: publish '{release}' exists; name a new release")
        # Under the lock and before any write, as in `apply`. No publish row exists yet, so
        # nothing can roll back to an earlier attempt's snapshot.
        hashes = write_snapshot(await read_snapshot_rows(conn, document_ids=documents,
                                                         staged=False),
                                snapshot_dir(release, root), replace=True)
        # No staging is used, so the publish is cleaned up from the start.
        await conn.execute(
            """INSERT INTO corpus_publishes (id, collections, qdrant_collection,
                 previous_qdrant_collection, snapshot_sha256, cleaned_up_at)
               VALUES ($1, ARRAY[$2], $3, $3, $4::jsonb, now())""",
            release, collection, target, json.dumps(hashes))
        passages = await conn.fetch(
            """SELECT c.id::text AS id, c.document_id::text AS document_id, c.reference,
                      c.chapter_label FROM public.chunks c
               WHERE c.document_id = ANY($1::uuid[]) AND c.retired_at IS NULL""", documents)
        await conn.execute(
            """WITH r AS (SELECT id, document_id, row_number() OVER (
                            PARTITION BY document_id ORDER BY position) AS rn
                          FROM public.chunks WHERE document_id = ANY($1::uuid[])
                            AND retired_at IS NULL),
                    b AS (SELECT d AS document_id,
                            LEAST($2::int, coalesce((SELECT min(position) - 1 FROM public.chunks
                                    WHERE document_id = d AND retired_at IS NOT NULL), $2::int)) AS base
                          FROM unnest($1::uuid[]) AS d)
               UPDATE public.chunks c SET retired_at = now(), position = b.base - (r.rn - 1)::int
               FROM r JOIN b USING (document_id) WHERE c.id = r.id""",
            documents, RETIRED_BASE)
        await conn.execute(
            "UPDATE public.documents SET retired_at = now() WHERE id = ANY($1::uuid[])", documents)
        rows = []
        for d in live:
            snapshot = retirements._snapshot(collection, d["title"], d["author"], None, None)
            rows.append(retirements.tombstone(entries[d["id"]], entity="document", id=d["id"],
                                              document_id=d["id"], snapshot=snapshot,
                                              release=release, at=at))
        title = {d["id"]: d for d in live}
        for p in passages:
            d = title[p["document_id"]]
            snapshot = retirements._snapshot(collection, d["title"], d["author"],
                                             p["reference"], p["chapter_label"])
            rows.append(retirements.tombstone(entries[p["document_id"]], entity="passage",
                                              id=p["id"], document_id=p["document_id"],
                                              snapshot=snapshot, release=release, at=at))
        tomb_cols = ", ".join(rw.TOMBSTONE_COLUMNS)
        await conn.executemany(
            f"""INSERT INTO public.corpus_tombstones ({tomb_cols}) VALUES
                ($1, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)""",
            [tuple(json.dumps(t[c]) if c == "snapshot" else t[c] for c in rw.TOMBSTONE_COLUMNS)
             for t in rows])
        await _refresh(conn, documents)
        await conn.execute("UPDATE corpus_publishes SET applied_at = now() WHERE id = $1", release)

    # Only points that were searchable are flipped and recorded, so rollback never makes
    # a point searchable that was not before.
    ids = []
    for start in range(0, len(passages), 256):
        points = await qdrant.retrieve(target, ids=[p["id"] for p in passages[start:start + 256]],
                                       with_payload=["searchable"])
        ids += [str(p.id) for p in points if (p.payload or {}).get("searchable") is not False]
    directory = snapshot_dir(release, root)
    with open(os.path.join(directory, FLIPPED_POINTS), "w", encoding="utf-8") as f:
        json.dump(ids, f)
    await set_searchable(qdrant, target, ids, False)
    return {"documents": len(documents), "passages": len(passages), "collection": target}
