"""Move user rows along a publish's redirects, and undo it (corpus-cleanup 4.1a, D1, D11).

2.2w's `apply` calls `UserDataRemapImpl.forward` inside its transaction, after it has
written the publish's redirects, and its `rollback` calls `reverse` inside its own. Only
a row on an ID or anchor that has a redirect moves: a passage whose text changed keeps its
ID (D1), and a row on a removed passage stays on it and shows the tombstone (D3).

    cd datapipeline
    python3 -m remap_user_data --dry-run [--rows] [--redirects <file.jsonl>]

The dry run prints what `forward` would do with the staged publish's redirects (or a
JSONL file of rows shaped like `corpus_redirects`) against the database, in a read-only
transaction. Nothing here writes outside 2.2w's `apply` and `rollback`, which hold the
publish lock (0.4).

`forward`, one pass per table, each ending with an assertion that no row of the table is
left on a redirected ID:
  - bookmarks: repoint; when a user's bookmarks meet on one passage, keep the earliest and
    join the differing notes with a blank line if the result fits 3,000 characters, else
    keep the earliest note (the other stays in the ledger);
  - retrieval_labels: repoint; on (user, passage, search) keep the latest label;
  - guest_trial_retrievals: repoint; on (trial, passage) keep the lowest rank;
  - retrievals: repoint; a search holding the passage twice keeps the lowest rank;
  - product_feedback: repoint;
  - reading_progress: document and chapter through the chapter redirects, anchor through
    the anchor redirects; a chapter with no live passage becomes the document's first live
    chapter with no anchor; on (user, document) keep the later `updated_at`.

The ledger records every row forward changed or dropped: its key, its row before, and the
row forward left (or, for a dropped row, the survivor as forward left it). Its private
form, which holds user IDs and note text, is `user_remap_ledger.jsonl` in the publish's
before-snapshot folder (gitignored, `releases/snapshots/<release>-before/`), and its
sha256 joins the snapshot's in `corpus_publishes.snapshot_sha256` in the same commit.
Never commit it; delete it with the snapshot when the rollback window closes. The public
form is the counts `forward` and `reverse` return, per table and rule, with no IDs.

`reverse` undoes only what the ledger recorded and never overwrites or recreates what a
user changed since the apply: a row is moved back only while it still holds what forward
wrote; a dropped row comes back only while its survivor is unchanged, its parents exist,
its guest trial has not been claimed since the apply, and no row holds its unique key.
Every skip is counted by reason and never raises; only a ledger that does not parse or
does not match its recorded sha256, or a database error, aborts the rollback.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

DATAPIPELINE = os.path.dirname(os.path.abspath(__file__))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

from writers.apply import SNAPSHOT_ROOT, RemapLedger, snapshot_dir  # noqa: E402

LEDGER_FILE = "user_remap_ledger.jsonl"
NOTE_LIMIT = 3000      # bookmarks.note CHECK (0016)
LEDGER_VERSION = 1


class RemapRefused(ValueError):
    """A remap that must not run (a redirect to a missing passage, an applied publish)."""


class RemapFault(RuntimeError):
    """A ledger that cannot be trusted, or a pass that left a row on a redirected ID."""


@dataclass(frozen=True)
class ChunkTable:
    """A user table whose rows point at one passage."""
    name: str
    pk: tuple[str, ...]
    group: tuple[str, ...]     # with chunk_id, the key rows merge on; () never merges
    parents: tuple[tuple[str, str], ...]   # (column, "schema.table") that must exist


BOOKMARKS = ChunkTable("bookmarks", ("id",), ("user_id",), (("user_id", "auth.users"),))
LABELS = ChunkTable("retrieval_labels", ("id",), ("user_id", "search_id"),
                    (("user_id", "auth.users"), ("search_id", "public.searches")))
GUEST = ChunkTable("guest_trial_retrievals", ("id",), ("guest_trial_id",),
                   (("guest_trial_id", "public.guest_trials"),))
RETRIEVALS = ChunkTable("retrievals", ("id",), ("search_id",),
                        (("search_id", "public.searches"),))
FEEDBACK = ChunkTable("product_feedback", ("id",), (), ())
CHUNK_TABLES = (BOOKMARKS, LABELS, GUEST, RETRIEVALS, FEEDBACK)
READING = "reading_progress"
READING_PK = ("user_id", "document_id")
READING_PARENTS = (("user_id", "auth.users"), ("document_id", "public.documents"))
TABLES = {t.name: t for t in CHUNK_TABLES}

SKIP_REASONS = ("deleted_by_user", "changed_by_user", "parent_deleted", "guest_claimed",
                "unique_key_taken")


def _ts(value: str | None) -> datetime:
    return datetime.fromisoformat(value) if value else datetime.min


def _key(row: dict, columns: Sequence[str]) -> tuple:
    return tuple(row[c] for c in columns)


def _note(row: dict) -> str:
    return (row.get("note") or "").strip()


# --------------------------------------------------------------------------- redirects

@dataclass
class Redirects:
    """One publish's redirects, as 2.2w passes them (`corpus_redirects` rows)."""
    passages: dict[str, str] = field(default_factory=dict)            # old ID -> new ID
    anchors: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    chapters: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)
    documents: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_rows(cls, redirects: list[dict], chapter_remap: list[dict]) -> "Redirects":
        out = cls()
        for r in [*redirects, *chapter_remap]:
            entity = r["entity"]
            if entity == "passage":
                out.passages[str(r["old_id"])] = str(r["new_id"])
            elif entity == "document":
                out.documents[str(r["old_id"])] = str(r["new_document_id"])
            elif entity in ("anchor", "chapter"):
                side = out.anchors if entity == "anchor" else out.chapters
                side[(str(r["old_document_id"]), r["old_anchor"])] = (
                    str(r["new_document_id"]), r["new_anchor"])
            else:
                raise RemapRefused(f"REFUSING: unknown redirect entity {entity!r}")
        return out


# --------------------------------------------------------------------------- database

async def _rows(conn, table: str, where: str, *args) -> list[dict]:
    return [json.loads(r[0]) for r in await conn.fetch(
        f"SELECT to_jsonb(t)::text FROM public.{table} t WHERE {where}", *args)]


async def _table_exists(conn, name: str) -> bool:
    return await conn.fetchval("SELECT to_regclass($1)", name) is not None


def _match(columns: Sequence[str], table: str, param: int) -> str:
    """`(cols) = (cols of the JSON row $param)`, typed by the table's own row type."""
    cols = ", ".join(columns)
    return (f"({cols}) = (SELECT {cols} FROM jsonb_populate_record(NULL::public.{table}, "
            f"${param}::jsonb))")


async def _fetch(conn, table: str, pk: Sequence[str], row: dict) -> dict | None:
    found = await _rows(conn, table, _match(pk, table, 1), json.dumps(row))
    return found[0] if found else None


async def _delete(conn, table: str, pk: Sequence[str], row: dict) -> None:
    await conn.execute(f"DELETE FROM public.{table} t WHERE {_match(pk, table, 1)}",
                       json.dumps(row))


async def _insert(conn, table: str, row: dict) -> None:
    await conn.execute(
        f"INSERT INTO public.{table} SELECT * FROM jsonb_populate_record(NULL::public.{table}, $1::jsonb)",
        json.dumps(row))


async def _update(conn, table: str, pk: Sequence[str], key_row: dict, row: dict) -> None:
    """Set every column of the row `key_row` names to `row`'s values."""
    cols = ", ".join(row)
    await conn.execute(
        f"""UPDATE public.{table} t SET ({cols}) = (
              SELECT {cols} FROM jsonb_populate_record(NULL::public.{table}, $2::jsonb))
            WHERE {_match(pk, table, 1)}""", json.dumps(key_row), json.dumps(row))


async def _parent_missing(conn, parents, row: dict) -> bool:
    for column, table in parents:
        if row.get(column) is None or not await _table_exists(conn, table):
            continue
        if not await conn.fetchval(f"SELECT EXISTS (SELECT 1 FROM {table} WHERE id = $1::uuid)",
                                   row[column]):
            return True
    return False


# --------------------------------------------------------------------------- plan

@dataclass
class Plan:
    """What forward will do: ledger entries (without the rows it leaves, which are read
    back after the writes) and the public counts."""
    entries: list[dict] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def count(self, table: str, rule: str, n: int = 1) -> None:
        self.counts[f"{table}.{rule}"] += n


def _survivor(table: ChunkTable, rows: list[dict]) -> dict:
    if table is BOOKMARKS:
        return min(rows, key=lambda r: (_ts(r["created_at"]), r["id"]))
    if table is LABELS:
        return max(rows, key=lambda r: (_ts(r["created_at"]), r["id"]))
    return min(rows, key=lambda r: (r["rank"], _ts(r["created_at"]), r["id"]))


def _joined_note(rows: list[dict], survivor: dict, plan: Plan) -> str | None:
    """The survivor's note after a bookmark merge (rows in created_at order)."""
    notes, seen = [], set()
    for r in sorted(rows, key=lambda r: (_ts(r["created_at"]), r["id"])):
        if _note(r) and _note(r) not in seen:
            notes.append(r["note"])
            seen.add(_note(r))
    if len(notes) <= 1:
        return notes[0] if notes else survivor.get("note")
    joined = "\n\n".join(n.strip() for n in notes)
    if len(joined) <= NOTE_LIMIT:
        plan.count(BOOKMARKS.name, "notes_joined")
        return joined
    plan.count(BOOKMARKS.name, "notes_kept_apart")
    return notes[0]


async def _plan_chunk_table(conn, table: ChunkTable, redirects: Redirects, plan: Plan) -> None:
    moving = await _rows(conn, table.name, "t.chunk_id = ANY($1::uuid[])",
                         list(redirects.passages))
    if not moving:
        return
    targets = sorted({redirects.passages[r["chunk_id"]] for r in moving})
    resident = (await _rows(conn, table.name, "t.chunk_id = ANY($1::uuid[])", targets)
                if table.group else [])
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in moving:
        after = {**r, "chunk_id": redirects.passages[r["chunk_id"]]}
        key = (_key(after, table.group), after["chunk_id"]) if table.group else (r["id"],)
        groups[key].append(r)
    for r in resident:
        key = (_key(r, table.group), r["chunk_id"])
        if key in groups:
            groups[key].append(r)

    for rows in groups.values():
        if len(rows) == 1:
            r = rows[0]
            plan.entries.append({"table": table.name, "action": "moved", "rule": "repointed",
                                 "before": r, "after": {**r, "chunk_id": redirects.passages[r["chunk_id"]]}})
            plan.count(table.name, "repointed")
            continue
        survivor = _survivor(table, rows)
        after = {**survivor, "chunk_id": redirects.passages.get(survivor["chunk_id"],
                                                                 survivor["chunk_id"])}
        if table is BOOKMARKS:
            after["note"] = _joined_note(rows, survivor, plan)
        if after != survivor:
            plan.entries.append({"table": table.name, "action": "moved", "rule": "merged",
                                 "before": survivor, "after": after})
        plan.count(table.name, "merged")
        for r in rows:
            if r is not survivor:
                plan.entries.append({"table": table.name, "action": "dropped",
                                     "rule": "merged", "before": r, "survivor": after})
                plan.count(table.name, "dropped")


# The live passages as the apply leaves them. Forward runs after the apply has written
# them; a dry run sees them before, so it reads the staged documents from staging.
LIVE = "(SELECT id, document_id, chapter_key, anchor, position FROM public.chunks WHERE retired_at IS NULL)"
AFTER_STAGE = """(SELECT id, document_id, chapter_key, anchor, position FROM staging.chunks
                  UNION ALL
                  SELECT id, document_id, chapter_key, anchor, position FROM public.chunks
                  WHERE retired_at IS NULL
                    AND document_id NOT IN (SELECT id FROM staging.documents)
                    -- a document of a staged collection that staging lacks is retired
                    AND document_id NOT IN (
                        SELECT d.id FROM public.documents d JOIN corpus_publishes p
                          ON d.collection = ANY(p.collections)
                        WHERE p.staged_at IS NOT NULL AND p.applied_at IS NULL
                          AND p.discarded_at IS NULL))"""


async def _live_chapter_of(conn, corpus: str, document: str, anchor: str) -> str | None:
    return await conn.fetchval(
        f"SELECT chapter_key FROM {corpus} c WHERE document_id = $1::uuid AND anchor = $2",
        document, anchor)


async def _chapter_is_live(conn, corpus: str, document: str, chapter: str) -> bool:
    return await conn.fetchval(
        f"""SELECT EXISTS (SELECT 1 FROM {corpus} c WHERE document_id = $1::uuid
            AND chapter_key = $2)""", document, chapter)


async def _first_live_chapter(conn, corpus: str, document: str) -> str | None:
    return await conn.fetchval(
        f"""SELECT chapter_key FROM {corpus} c WHERE document_id = $1::uuid
            AND chapter_key IS NOT NULL ORDER BY position LIMIT 1""", document)


async def _reading_target(conn, corpus: str, row: dict,
                          redirects: Redirects) -> tuple[dict, str] | None:
    """The row forward leaves for a reading position and its rule, or None when no
    redirect names its chapter, anchor or document and its chapter is still live."""
    document, chapter, anchor = row["document_id"], row["chapter_key"], row["anchor"]
    if anchor is not None and (document, anchor) in redirects.anchors:
        new_document, new_anchor = redirects.anchors[(document, anchor)]
        new_chapter = await _live_chapter_of(conn, corpus, new_document, new_anchor)
        if new_chapter is not None:
            moved = (new_document, new_chapter, new_anchor)
        else:
            moved = (*redirects.chapters.get((document, chapter), (document, chapter)), None)
    elif (document, chapter) in redirects.chapters:
        new_document, new_chapter = redirects.chapters[(document, chapter)]
        keep = (anchor if anchor is not None and new_document == document
                and await _live_chapter_of(conn, corpus, document, anchor) == new_chapter
                else None)
        moved = (new_document, new_chapter, keep)
    elif document in redirects.documents:
        moved = (redirects.documents[document], None, None)
    else:
        # No redirect: a chapter retired with no successor (0.1c gives it no chapter
        # redirect) still goes to its document's first live chapter (step 2).
        moved = (document, chapter, anchor)
    new_document, new_chapter, new_anchor = moved
    rule = "rewritten"
    if new_chapter is None or not await _chapter_is_live(conn, corpus, new_document, new_chapter):
        new_chapter, new_anchor, rule = (await _first_live_chapter(conn, corpus, new_document),
                                         None, "first_chapter")
        if new_chapter is None:
            raise RemapRefused(f"REFUSING: document {new_document} has no live chapter for "
                               "a reading position to move to")
    after = {**row, "document_id": new_document, "chapter_key": new_chapter,
             "anchor": new_anchor}
    return None if after == row else (after, rule)


async def _plan_reading(conn, corpus: str, redirects: Redirects, plan: Plan) -> None:
    documents = sorted({d for d, _ in redirects.anchors} | {d for d, _ in redirects.chapters}
                       | set(redirects.documents))
    # Rows on a redirect, and rows in a document that stays live whose chapter does not.
    candidates = await _rows(
        conn, READING,
        f"""t.document_id = ANY($1::uuid[])
            OR (EXISTS (SELECT 1 FROM {corpus} c WHERE c.document_id = t.document_id)
                AND NOT EXISTS (SELECT 1 FROM {corpus} c WHERE c.document_id = t.document_id
                                AND c.chapter_key = t.chapter_key))""", documents)
    moving = []
    for r in candidates:
        target = await _reading_target(conn, corpus, r, redirects)
        if target is not None:
            moving.append((r, *target))
    if not moving:
        return
    moving_keys = {_key(r, READING_PK) for r, _, _ in moving}
    resident = {_key(r, READING_PK): r for r in await _rows(
        conn, READING, "(t.user_id, t.document_id) IN (SELECT * FROM unnest($1::uuid[], $2::uuid[]))",
        [a["user_id"] for _, a, _ in moving], [a["document_id"] for _, a, _ in moving])
        if _key(r, READING_PK) not in moving_keys}
    groups: dict[tuple, list[tuple[dict, dict, str | None]]] = defaultdict(list)
    for before, after, rule in moving:
        groups[_key(after, READING_PK)].append((before, after, rule))
    for key, members in groups.items():
        if key in resident:
            members.append((resident[key], resident[key], None))
        best = max(members, key=lambda m: (_ts(m[1]["updated_at"]), m[0]["document_id"] == key[1]))
        for before, after, rule in members:
            if before is best[0]:
                if rule is not None:
                    plan.entries.append({"table": READING, "action": "moved", "rule": rule,
                                         "before": before, "after": after})
                    plan.count(READING, rule)
            else:
                plan.entries.append({"table": READING, "action": "dropped", "rule": "merged",
                                     "before": before, "survivor": best[1]})
                plan.count(READING, "dropped")


async def plan_forward(conn, redirects: Redirects, *, staged: bool = False) -> Plan:
    """What forward would do, read only. `staged` plans against the corpus the staged
    publish will leave (a dry run before the apply), instead of the live tables."""
    corpus = AFTER_STAGE if staged else LIVE
    targets = sorted(set(redirects.passages.values()))
    found = {r[0] for r in await conn.fetch(
        f"SELECT id::text FROM {corpus} c WHERE id = ANY($1::uuid[])", targets)}
    missing = [t for t in targets if t not in found]
    if missing:
        raise RemapRefused(f"REFUSING: {len(missing)} redirect targets are missing from "
                           f"chunks or retired, first {missing[0]}")
    plan = Plan()
    for table in CHUNK_TABLES:
        if await _table_exists(conn, f"public.{table.name}"):
            await _plan_chunk_table(conn, table, redirects, plan)
    await _plan_reading(conn, corpus, redirects, plan)
    return plan


# --------------------------------------------------------------------------- ledger file

def _ledger_bytes(release: str, entries: list[dict]) -> bytes:
    body = "".join(json.dumps(e, sort_keys=True, ensure_ascii=False) + "\n" for e in entries)
    header = {"version": LEDGER_VERSION, "release": release, "entries": len(entries),
              "body_sha256": hashlib.sha256(body.encode()).hexdigest()}
    return (json.dumps(header, sort_keys=True) + "\n" + body).encode()


def write_ledger(path: str, release: str, entries: list[dict]) -> str:
    """Write the private ledger (owner-only), atomically; return its sha256."""
    data = _ledger_bytes(release, entries)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return hashlib.sha256(data).hexdigest()


def read_ledger(path: str, release: str, sha256: str) -> list[dict]:
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as error:
        raise RemapFault(f"the user-data ledger {path} cannot be read: {error}") from error
    if hashlib.sha256(data).hexdigest() != sha256:
        raise RemapFault(f"{path} differs from the sha256 the apply recorded")
    try:
        header, *lines = data.decode().splitlines(keepends=True)
        header = json.loads(header)
        entries = [json.loads(line) for line in lines]
    except (ValueError, UnicodeDecodeError) as error:
        raise RemapFault(f"{path} does not parse: {error}") from error
    if (header.get("version") != LEDGER_VERSION or header.get("release") != release
            or header.get("entries") != len(entries)):
        raise RemapFault(f"{path} is not the ledger of publish '{release}'")
    for e in entries:
        if e.get("action") not in ("moved", "dropped") or (e.get("table") not in TABLES
                                                           and e.get("table") != READING):
            raise RemapFault(f"{path} holds an entry it cannot undo: {e.get('table')} "
                             f"{e.get('action')}")
    return entries


def _pk(table: str) -> tuple[str, ...]:
    return READING_PK if table == READING else TABLES[table].pk


def _parents(table: str):
    return READING_PARENTS if table == READING else TABLES[table].parents


def _unique_columns(table: str) -> tuple[str, ...] | None:
    """The unique key besides the primary key a restored row must not collide with."""
    return {"bookmarks": ("user_id", "chunk_id"),
            "retrieval_labels": ("user_id", "chunk_id", "search_id"),
            "guest_trial_retrievals": ("guest_trial_id", "chunk_id")}.get(table)


# --------------------------------------------------------------------------- the remap

class UserDataRemapImpl:
    """2.2w's `UserDataRemap` (writers/apply.py). `root` is the snapshot root the apply
    and rollback use, so the ledger sits in the publish's before-snapshot folder."""

    def __init__(self, root: str = SNAPSHOT_ROOT):
        self.root = root

    def ledger_path(self, release: str) -> str:
        return os.path.join(snapshot_dir(release, self.root), LEDGER_FILE)

    async def _lock(self, conn) -> None:
        # Reads stay open; user writes wait for the commit (the apply's lock_timeout holds).
        for name in [t.name for t in CHUNK_TABLES] + [READING]:
            if await _table_exists(conn, f"public.{name}"):
                await conn.execute(f"LOCK TABLE public.{name} IN EXCLUSIVE MODE")

    async def forward(self, conn, release: str, redirects: list[dict],
                      chapter_remap: list[dict]) -> RemapLedger:
        if not conn.is_in_transaction():
            raise RemapRefused("REFUSING: forward runs only inside 2.2w's apply transaction")
        publish = await conn.fetchrow(
            "SELECT applied_at, snapshot_sha256 FROM corpus_publishes WHERE id = $1", release)
        if publish is None or publish["applied_at"] is not None:
            raise RemapRefused(f"REFUSING: publish '{release}' is missing or already applied")
        await self._lock(conn)
        plan = await plan_forward(conn, Redirects.from_rows(redirects, chapter_remap))

        # Deletes first, so no move meets a row that is leaving; reading positions move by
        # delete and insert, since their key is the document, which can move both ways.
        for e in plan.entries:
            if e["action"] == "dropped" or e["table"] == READING:
                await _delete(conn, e["table"], _pk(e["table"]), e["before"])
        for e in plan.entries:
            if e["action"] != "moved":
                continue
            if e["table"] == READING:
                await _insert(conn, READING, e["after"])
            else:
                await _update(conn, e["table"], _pk(e["table"]), e["before"], e["after"])
        # Record what the database holds now, not what was meant, for reverse to compare.
        for e in plan.entries:
            key = "after" if e["action"] == "moved" else "survivor"
            found = await _fetch(conn, e["table"], _pk(e["table"]), e[key])
            if found is None:
                raise RemapFault(f"{e['table']}: a row forward wrote is missing")
            e[key] = found
        await self._assert_none_left(conn, Redirects.from_rows(redirects, chapter_remap))

        sha = write_ledger(self.ledger_path(release), release, plan.entries)
        await conn.execute(
            """UPDATE corpus_publishes
               SET snapshot_sha256 = coalesce(snapshot_sha256, '{}'::jsonb) || jsonb_build_object($2::text, $3::text)
               WHERE id = $1""", release, LEDGER_FILE, sha)
        return RemapLedger(dict(sorted(plan.counts.items())))

    async def _assert_none_left(self, conn, redirects: Redirects) -> None:
        for table in CHUNK_TABLES:
            if not await _table_exists(conn, f"public.{table.name}"):
                continue
            left = await conn.fetchval(
                f"SELECT count(*) FROM public.{table.name} WHERE chunk_id = ANY($1::uuid[])",
                list(redirects.passages))
            if left:
                raise RemapFault(f"{table.name}: {left} rows still point at a redirected ID")
        for r in await _rows(conn, READING, "t.document_id = ANY($1::uuid[])",
                             sorted({d for d, _ in redirects.anchors}
                                    | {d for d, _ in redirects.chapters}
                                    | set(redirects.documents))):
            if ((r["document_id"], r["chapter_key"]) in redirects.chapters
                    or (r["document_id"], r["anchor"]) in redirects.anchors
                    or r["document_id"] in redirects.documents):
                raise RemapFault("reading_progress: a row still points at a redirected "
                                 "document, chapter or anchor")

    async def reverse(self, conn, release: str) -> RemapLedger:
        if not conn.is_in_transaction():
            raise RemapRefused("REFUSING: reverse runs only inside 2.2w's rollback transaction")
        publish = await conn.fetchrow(
            "SELECT applied_at, snapshot_sha256 FROM corpus_publishes WHERE id = $1", release)
        if publish is None or publish["applied_at"] is None:
            raise RemapRefused(f"REFUSING: publish '{release}' is not applied")
        hashes = publish["snapshot_sha256"]
        hashes = json.loads(hashes) if isinstance(hashes, str) else (hashes or {})
        if LEDGER_FILE not in hashes:
            # Applied without the remap (before 4.1a merged): forward moved nothing.
            return RemapLedger({})
        entries = read_ledger(self.ledger_path(release), release, hashes[LEDGER_FILE])
        await self._lock(conn)
        counts: dict[str, int] = defaultdict(int)

        # Judge every entry against the state the rollback found, before changing any row.
        current = {}
        for i, e in enumerate(entries):
            key = "after" if e["action"] == "moved" else "survivor"
            current[i] = await _fetch(conn, e["table"], _pk(e["table"]), e[key])

        async def skip_reason(e: dict, now: dict | None, expected: dict) -> str | None:
            if now is None:
                return ("parent_deleted" if await _parent_missing(conn, _parents(e["table"]), e["before"])
                        else "deleted_by_user")
            return None if now == expected else "changed_by_user"

        async def key_taken(e: dict, ignore: dict | None) -> bool:
            table, row = e["table"], e["before"]
            for columns in filter(None, (_pk(table), _unique_columns(table))):
                found = await _rows(conn, table, _match(columns, table, 1), json.dumps(row))
                if any(ignore is None or _key(f, _pk(table)) != _key(ignore, _pk(table))
                       for f in found):
                    return True
            return False

        for i, e in enumerate(entries):
            if e["action"] != "moved":
                continue
            table = e["table"]
            reason = await skip_reason(e, current[i], e["after"])
            if reason is None and await key_taken(e, current[i]):
                reason = "unique_key_taken"
            if reason is not None:
                counts[f"{table}.skipped_{reason}"] += 1
                continue
            if table == READING:
                await _delete(conn, READING, READING_PK, e["after"])
                await _insert(conn, READING, e["before"])
            else:
                await _update(conn, table, _pk(table), e["after"], e["before"])
            counts[f"{table}.restored"] += 1

        for i, e in enumerate(entries):
            if e["action"] != "dropped":
                continue
            table = e["table"]
            if await _parent_missing(conn, _parents(table), e["before"]):
                reason = "parent_deleted"
            elif table == GUEST.name and await conn.fetchval(
                    """SELECT claimed_at IS NOT NULL AND claimed_at >= $2
                       FROM public.guest_trials WHERE id = $1::uuid""",
                    e["before"]["guest_trial_id"], publish["applied_at"]):
                reason = "guest_claimed"
            else:
                reason = await skip_reason(e, current[i], e["survivor"])
                if reason is None and await key_taken(e, None):
                    reason = "unique_key_taken"
            if reason is not None:
                counts[f"{table}.skipped_{reason}"] += 1
                continue
            await _insert(conn, table, e["before"])
            counts[f"{table}.reinserted"] += 1

        await self._count_unnamed(conn, release, publish["applied_at"], entries, counts)
        return RemapLedger(dict(sorted(counts.items())))

    async def _count_unnamed(self, conn, release, applied_at, entries, counts) -> None:
        """Rows made since the apply on this publish's redirect targets, or on a passage the
        rollback has just retired (one only the new corpus had), which the ledger does not
        name: left alone, and counted."""
        named = defaultdict(set)
        for e in entries:
            named[e["table"]].add(e["before"]["id"] if e["table"] != READING else None)
        for table in CHUNK_TABLES:
            if not await _table_exists(conn, f"public.{table.name}"):
                continue
            n = await conn.fetchval(
                f"""SELECT count(*) FROM public.{table.name} t
                    WHERE t.created_at > $2 AND NOT (t.id::text = ANY($3::text[]))
                      AND (t.chunk_id IN (SELECT new_id FROM public.corpus_redirects
                                          WHERE publish_id = $1 AND entity = 'passage')
                           OR t.chunk_id IN (SELECT id FROM public.chunks
                                             WHERE retired_at = transaction_timestamp()))""",
                release, applied_at, sorted(named[table.name] - {None}))
            if n:
                counts[f"{table.name}.untouched_made_after_apply"] += n


# --------------------------------------------------------------------------- CLI

def _print_plan(plan: Plan, rows: bool) -> None:
    if not plan.counts:
        print("forward would move no user row")
    for key, n in sorted(plan.counts.items()):
        print(f"{key}: {n}")
    if rows:
        for e in plan.entries:
            key = {c: e["before"][c] for c in _pk(e["table"])}
            where = ({"document_id": e["after"]["document_id"],
                      "chapter_key": e["after"]["chapter_key"]} if e["table"] == READING
                     and e["action"] == "moved"
                     else {"chunk_id": e.get("after", e.get("survivor", {})).get("chunk_id")})
            print(f"  {e['table']} {e['action']} ({e['rule']}) {json.dumps(key)} -> {json.dumps(where)}")


def _load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


async def dry_run(conn, redirects_path: str | None = None, rows: bool = False) -> Plan:
    async with conn.transaction(readonly=True):
        if redirects_path:
            loaded = _load_jsonl(redirects_path)
            redirects = [r for r in loaded if r["entity"] != "chapter"]
            chapters = [r for r in loaded if r["entity"] == "chapter"]
        else:
            redirects = [dict(r) for r in await conn.fetch(
                "SELECT * FROM staging.corpus_redirects WHERE entity <> 'chapter' ORDER BY id")]
            chapters = [dict(r) for r in await conn.fetch(
                "SELECT * FROM staging.corpus_redirects WHERE entity = 'chapter' ORDER BY id")]
        plan = await plan_forward(conn, Redirects.from_rows(redirects, chapters),
                                  staged=True)
    _print_plan(plan, rows)
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python3 -m remap_user_data", description=(
        "Show what 4.1a's forward remap would do. It never writes: user rows move only "
        "inside publish.py apply and rollback."))
    parser.add_argument("--dry-run", action="store_true", required=True,
                        help="required: print the plan, change nothing")
    parser.add_argument("--redirects", help="a JSONL of corpus_redirects-shaped rows "
                                            "(default: the staged publish's)")
    parser.add_argument("--rows", action="store_true",
                        help="also list each row's key and target (no note text)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    async def run() -> None:
        import asyncpg

        from config import settings

        conn = await asyncpg.connect(settings.DATABASE_URL, statement_cache_size=0)
        try:
            await dry_run(conn, args.redirects, args.rows)
        finally:
            await conn.close()
    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
