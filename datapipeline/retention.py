"""What a publish's closed rollback window lets go (corpus-cleanup 4.1b step 13, D3).

    python3 publish.py purge-retired --release <name>                            # dry run
    python3 publish.py purge-retired --release <name> --execute --disk-free-gb <GB>
    python3 publish.py drop-old-collection --release <name>                      # dry run
    python3 publish.py drop-old-collection --release <name> --execute --confirm <collection>

`purge-retired` deletes retired passages and documents that nothing points at. The
foreign keys into `chunks` and `documents` are read from the live catalog at run time,
so a table added later (Studies) is covered without a change here. A retired row stays
when any row outside the corpus tables points at it, whatever the key's ON DELETE
action: a cascade would delete that row, and SET NULL would cut its link. It also
stays when:
  - another corpus row points at it (`superseded_by`), or, for a document, one of its
    passages stays;
  - its tombstone's reason is one under which the text is expected back
    (`HELD_REASONS`): ADR 0001 keeps those rows in the database, never deleted.
A document's own reader outline, contents tree and works go with it (they cascade).

Each batch of at most 1,000 rows is its own transaction, under the publish lock and
`lock_timeout`. It locks its rows, checks the references again (a row someone pointed
at since the plan stays), copies each passage's anchor and chapter key into its
tombstone's snapshot (the API finds the notice for an old reader link by them once the
row is gone), deletes, and refreshes the outlines of the documents it touched (0037's
trigger clears `chunk_count` on every DELETE). A batch that fails rolls back alone; a
rerun plans again from what is left.

Both commands refuse a live run before the publish's rollback window has closed, while
any publish holds staging or is inside its own window, and unless PUBLISH_LOCK.json
approves step `apply` for the release. A dry run writes nothing: it reads inside a
READ ONLY transaction.

Every DELETE writes the transaction log (WAL), which filled the database disk after the
republish's apply (#192). The plan estimates the WAL from the pages the batches touch,
and a live run refuses unless `--disk-free-gb`, read from the Supabase dashboard
(Database -> Disk) just before, covers twice that plus 1 GiB.
"""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from publication import lock_publishes
from writers.apply import ROLLBACK_WINDOW
BATCH_SIZE = 1000
# The corpus's own tables. A reference from any other table is a user's (or a later
# feature's) and keeps the row.
PASSAGES, DOCUMENTS = "public.chunks", "public.documents"
CORPUS_TABLES = frozenset({PASSAGES, DOCUMENTS, "public.document_chapters",
                           "public.document_contents", "public.document_works"})
# Rows a document owns, deleted with it.
DOCUMENT_PARTS = frozenset({"public.document_chapters", "public.document_contents",
                            "public.document_works"})
# Removal reasons whose text is held, not dropped: kept in the database so it can
# return unchanged (ADR 0001; D9's council gaps; 1.5b's amended canons).
HELD_REASONS = ("awaiting-permission", "translation-in-preparation")
ACTIONS = {"a": "no action", "r": "restrict", "c": "cascade", "n": "set null",
           "d": "set default"}

PAGE = 8192                 # a full-page image, before compression
TUPLE_WAL = 100             # one heap delete or update record, generously
TOAST_CHUNK = 1996          # bytes of a toasted value per toast row
SAFETY = 2                  # WAL is kept until a checkpoint, and the last one's too
MARGIN = 1 << 30            # room for Postgres to checkpoint and recover


class RetentionRefused(ValueError):
    """A step-13 command that must not run."""


@dataclass(frozen=True)
class Reference:
    """One foreign key into the corpus: `table.column` -> `target`."""
    table: str              # schema-qualified, as format('%I.%I') prints it
    column: str
    target: str             # PASSAGES or DOCUMENTS
    action: str             # ACTIONS' words

    @property
    def corpus(self) -> bool:
        return self.table in CORPUS_TABLES

    @property
    def label(self) -> str:
        return f"{self.table}.{self.column} ({self.action})"


async def references(conn) -> list[Reference]:
    """Every foreign key into `chunks` or `documents`, from the catalog."""
    rows = await conn.fetch(
        """SELECT format('%I.%I', n.nspname, r.relname) AS tbl,
                  (SELECT array_agg(a.attname ORDER BY k.i) FROM unnest(c.conkey)
                     WITH ORDINALITY AS k(attnum, i)
                     JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum)
                    AS columns,
                  format('%I.%I', tn.nspname, t.relname) AS target, c.confdeltype
           FROM pg_constraint c
           JOIN pg_class r ON r.oid = c.conrelid
           JOIN pg_namespace n ON n.oid = r.relnamespace
           JOIN pg_class t ON t.oid = c.confrelid
           JOIN pg_namespace tn ON tn.oid = t.relnamespace
           WHERE c.contype = 'f' AND c.confrelid = ANY($1::regclass[])
           ORDER BY 3, 1, 2""", [PASSAGES, DOCUMENTS])
    out = []
    for r in rows:
        if len(r["columns"]) != 1:
            raise RetentionRefused(f"REFUSING: {r['tbl']} has a foreign key of "
                                   f"{len(r['columns'])} columns into {r['target']}; this "
                                   "command checks single-column keys only")
        action = r["confdeltype"]        # a "char", which asyncpg returns as bytes
        action = action.decode() if isinstance(action, bytes) else action
        out.append(Reference(r["tbl"], r["columns"][0], r["target"],
                             ACTIONS.get(action, action)))
    return out


async def _pointed_at(conn, ref: Reference, ids: Sequence[str]) -> dict[str, int]:
    """id -> how many rows of `ref.table` point at it. `ref.table` is quoted already."""
    if not ids:
        return {}
    column = '"' + ref.column.replace('"', '""') + '"'
    rows = await conn.fetch(
        f"SELECT {column}::text AS id, count(*) AS n FROM {ref.table} "
        f"WHERE {column} = ANY($1::uuid[]) GROUP BY 1", list(ids))
    return {r["id"]: r["n"] for r in rows}


# --------------------------------------------------------------------------- blocks

def _user_reason(ref: Reference) -> str:
    return f"{'corpus' if ref.corpus else 'users'}: {ref.label}"


async def passage_blocks(conn, refs: list[Reference], ids: Sequence[str],
                         ) -> dict[str, dict[str, int]]:
    """For each retired passage that must stay: reason -> rows behind it."""
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for ref in refs:
        if ref.target != PASSAGES:
            continue
        for i, n in (await _pointed_at(conn, ref, ids)).items():
            out[i][_user_reason(ref)] = n
    # A reading position names a chapter, not a passage: its retired passages keep the
    # chapter's label for the position (reading_progress.py's single-document GET).
    if await conn.fetchval("SELECT to_regclass('public.reading_progress') IS NOT NULL"):
        for r in await conn.fetch(
                """SELECT c.id::text AS id, count(*) AS n FROM public.chunks c
                   JOIN public.reading_progress rp ON rp.document_id = c.document_id
                    AND rp.chapter_key = c.chapter_key
                   WHERE c.id = ANY($1::uuid[]) GROUP BY 1""", list(ids)):
            out[r["id"]]["users: public.reading_progress (its chapter)"] = r["n"]
    for r in await conn.fetch(
            """SELECT c.id::text AS id, t.reason_code FROM public.chunks c
               JOIN public.corpus_tombstones t
                 ON (t.entity = 'passage' AND t.id = c.id)
                 OR (t.entity = 'document' AND t.id = c.document_id)
               WHERE c.id = ANY($1::uuid[]) AND t.reason_code = ANY($2::text[])""",
            list(ids), list(HELD_REASONS)):
        out[r["id"]][f"held: {r['reason_code']} (ADR 0001)"] = 1
    return dict(out)


async def document_blocks(conn, refs: list[Reference], ids: Sequence[str],
                          leaving: set[str] = frozenset()) -> dict[str, dict[str, int]]:
    """For each retired document that must stay: reason -> rows behind it. Passages in
    `leaving` are about to be deleted and do not hold their document."""
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for ref in refs:
        if ref.target != DOCUMENTS or (ref.table in DOCUMENT_PARTS and ref.action == "cascade"):
            continue
        if ref.table == PASSAGES and ref.column == "document_id":
            staying = defaultdict(int)
            for r in await conn.fetch(
                    "SELECT id::text AS id, document_id::text AS d FROM public.chunks "
                    "WHERE document_id = ANY($1::uuid[])", list(ids)):
                if r["id"] not in leaving:
                    staying[r["d"]] += 1
            for d, n in staying.items():
                out[d]["its passages that stay"] = n
            continue
        for i, n in (await _pointed_at(conn, ref, ids)).items():
            out[i][_user_reason(ref)] = n
    for r in await conn.fetch(
            """SELECT id::text AS id, reason_code FROM public.corpus_tombstones
               WHERE entity = 'document' AND id = ANY($1::uuid[])
                 AND reason_code = ANY($2::text[])""", list(ids), list(HELD_REASONS)):
        out[r["id"]][f"held: {r['reason_code']} (ADR 0001)"] = 1
    return dict(out)


# --------------------------------------------------------------------------- refusals

async def refusals(conn, release: str) -> list[str]:
    """Why a live step-13 run must not run now; empty when it may."""
    from writers.reader_writer import staging_exists

    row = await conn.fetchrow(
        """SELECT *, now() AS db_now FROM corpus_publishes WHERE id = $1""", release)
    if row is None:
        return [f"no publish named '{release}'"]
    out = []
    if row["applied_at"] is None:
        out.append(f"publish '{release}' was never applied")
    elif row["rolled_back_at"] is not None:
        out.append(f"publish '{release}' was rolled back")
    elif row["db_now"] < row["applied_at"] + ROLLBACK_WINDOW:
        out.append(f"the rollback window of '{release}' is open until "
                   f"{row['applied_at'] + ROLLBACK_WINDOW:%Y-%m-%d %H:%M %Z} "
                   f"(applied {row['applied_at']:%Y-%m-%d %H:%M %Z}, "
                   f"{ROLLBACK_WINDOW.days} days)")
    for r in await conn.fetch(
            """SELECT id, applied_at FROM corpus_publishes
               WHERE discarded_at IS NULL AND cleaned_up_at IS NULL ORDER BY id"""):
        out.append(f"publish '{r['id']}' is open: it holds staging"
                   + ("" if r["applied_at"] else " and was never applied")
                   + "; clean it up or discard it first")
    for r in await conn.fetch(
            """SELECT id, applied_at FROM corpus_publishes
               WHERE id <> $1 AND applied_at IS NOT NULL AND rolled_back_at IS NULL
                 AND applied_at + $2::interval > now() ORDER BY id""",
            release, ROLLBACK_WINDOW):
        out.append(f"publish '{r['id']}' is inside its own rollback window, until "
                   f"{r['applied_at'] + ROLLBACK_WINDOW:%Y-%m-%d %H:%M %Z}")
    if await staging_exists(conn):
        out.append("the staging tables exist; a publish is in progress")
    return out


# --------------------------------------------------------------------------- plan

@dataclass
class WalEstimate:
    passage_pages: int = 0          # heap pages holding the passages, one image each
    passage_rows: int = 0
    toast_pages: int = 0
    document_pages: int = 0         # documents and their parts
    document_rows: int = 0
    outline_bytes: int = 0          # reader outlines rebuilt, twice their size per batch
    tombstone_bytes: int = 0        # snapshots updated, at most twice their size
    vacuum_bytes: int = 0           # VACUUM (analyze) chunks, at most every page once

    @property
    def purge_bytes(self) -> int:
        return ((self.passage_pages + self.toast_pages + self.document_pages) * PAGE
                + (self.passage_rows + self.document_rows) * TUPLE_WAL
                + self.outline_bytes + self.tombstone_bytes)

    @staticmethod
    def headroom(wal: int) -> int:
        return SAFETY * wal + MARGIN


@dataclass
class Plan:
    release: str
    references: list[Reference]
    retired_passages: int
    retired_documents: int
    passages: list[str]                         # to delete, in heap order
    documents: list[str]
    kept_passages: dict[str, dict[str, int]]    # id -> reason -> rows
    kept_documents: dict[str, dict[str, int]]
    wal: WalEstimate = field(default_factory=WalEstimate)
    refusals: list[str] = field(default_factory=list)


async def _distinct_pages(conn, table: str, column: str, ids: Sequence[str]) -> tuple[int, int]:
    row = await conn.fetchrow(
        f"""SELECT count(DISTINCT (ctid::text::point)[0])::bigint AS pages,
                   count(*)::bigint AS n
            FROM {table} WHERE {column} = ANY($1::uuid[])""", list(ids))
    return row["pages"], row["n"]


# The columns of `chunks` that can be stored out of line.
TOASTABLE = ("content", "annotation", "metadata", "search_vector", "annotation_vector",
             "note")


async def _estimate(conn, passages: list[str], documents: list[str]) -> WalEstimate:
    est = WalEstimate()
    # A heap page holding rows of two batches is written (and imaged) by each.
    page = {r["id"]: r["page"] for r in await conn.fetch(
        """SELECT id::text AS id, (ctid::text::point)[0] AS page FROM public.chunks
           WHERE id = ANY($1::uuid[])""", passages)}
    est.passage_rows = len(page)
    est.passage_pages = sum(len({page[i] for i in passages[b:b + BATCH_SIZE] if i in page})
                            for b in range(0, len(passages), BATCH_SIZE))
    columns = [r["attname"] for r in await conn.fetch(
        """SELECT attname FROM pg_attribute WHERE attrelid = 'public.chunks'::regclass
           AND attname = ANY($1::text[]) AND NOT attisdropped""", list(TOASTABLE))]
    # Every value stored out of line, whatever its size (Postgres moves values out once
    # the whole row is too long); each toast row counted as its own page, per batch.
    # Before Postgres 17 nothing says which values are out of line, so all count.
    exact = await conn.fetchval("SELECT current_setting('server_version_num')::int >= 170000")
    toasted = " + ".join(
        (f"CASE WHEN pg_column_toast_chunk_id({c}) IS NULL THEN 0 ELSE " if exact else
         f"CASE WHEN {c} IS NULL THEN 0 ELSE ")
        + f"ceil(pg_column_size({c}) / {TOAST_CHUNK}.0) END" for c in columns) or "0"
    est.toast_pages = await conn.fetchval(
        f"""SELECT coalesce(sum({toasted}), 0)::bigint FROM public.chunks
            WHERE id = ANY($1::uuid[])""", passages)
    for table, column in ((DOCUMENTS, "id"), *((t, "document_id") for t in sorted(DOCUMENT_PARTS))):
        pages, n = await _distinct_pages(conn, table, column, documents)
        est.document_pages += pages
        est.document_rows += n
    size = await conn.fetchrow(
        """SELECT pg_total_relation_size('public.documents') AS documents,
                  pg_total_relation_size('public.document_chapters') AS chapters,
                  pg_total_relation_size('public.document_contents')
                  + pg_total_relation_size('public.document_works') AS parts,
                  pg_total_relation_size('public.corpus_tombstones') AS tombstones""")
    if documents:
        # Their toast and indexes, at most all of each table once.
        est.document_pages += math.ceil((size["documents"] + size["parts"]) / PAGE)
    if passages:
        # Each batch clears and rebuilds outlines (documents and document_chapters,
        # deleted and inserted): at most twice both tables, per batch.
        batches = math.ceil(len(passages) / BATCH_SIZE)
        est.outline_bytes = batches * 2 * (size["documents"] + size["chapters"])
        est.tombstone_bytes = 2 * size["tombstones"]
    est.vacuum_bytes = await conn.fetchval("SELECT pg_total_relation_size('public.chunks')")
    return est


async def plan(conn, release: str) -> Plan:
    """What a live run would delete and keep now, with its WAL estimate. Reads only."""
    refs = await references(conn)
    retired = [r["id"] for r in await conn.fetch(
        "SELECT id::text AS id FROM public.chunks WHERE retired_at IS NOT NULL "
        "ORDER BY document_id, ctid")]
    kept_passages = await passage_blocks(conn, refs, retired)
    passages = [i for i in retired if i not in kept_passages]
    retired_docs = [r["id"] for r in await conn.fetch(
        "SELECT id::text AS id FROM public.documents WHERE retired_at IS NOT NULL ORDER BY id")]
    kept_documents = await document_blocks(conn, refs, retired_docs, set(passages))
    documents = [d for d in retired_docs if d not in kept_documents]
    return Plan(release=release, references=refs, retired_passages=len(retired),
                retired_documents=len(retired_docs), passages=passages, documents=documents,
                kept_passages=kept_passages, kept_documents=kept_documents,
                wal=await _estimate(conn, passages, documents),
                refusals=await refusals(conn, release))


async def read_plan(conn, release: str) -> Plan:
    """`plan` inside a READ ONLY transaction, so a dry run cannot write."""
    async with conn.transaction(readonly=True):
        await _no_row_security(conn)
        return await plan(conn, release)


async def _no_row_security(conn) -> None:
    """A policy that hid user rows from the reference checks would let a delete cascade
    to them unseen; with row security off, such a query errors instead."""
    await conn.execute("SET LOCAL row_security = off")


# --------------------------------------------------------------------------- report

def _mb(n: int) -> str:
    return f"{n / (1 << 20):,.0f} MB" if n < 1 << 30 else f"{n / (1 << 30):,.2f} GB"


def _n(n: int, noun: str) -> str:
    return f"{n:,} {noun}{'' if n == 1 else 's'}"


def _reasons(kept: dict[str, dict[str, int]]) -> list[tuple[str, int, int]]:
    """(reason, rows kept, referencing rows), most first. A row kept for two reasons
    counts under each."""
    rows, refs = defaultdict(int), defaultdict(int)
    for reasons in kept.values():
        for reason, n in reasons.items():
            rows[reason] += 1
            refs[reason] += n
    return sorted(((r, rows[r], refs[r]) for r in rows), key=lambda t: (-t[1], t[0]))


def describe(p: Plan) -> list[str]:
    """The dry run's report, in plain lines."""
    w = p.wal
    lines = [f"purge-retired {p.release}: dry run, nothing written", "",
             "Foreign keys into the corpus (read from the database):"]
    lines += [f"  {r.label} -> {r.target}{'  [corpus]' if r.corpus else ''}"
              for r in p.references]
    lines += ["", f"Retired passages: {p.retired_passages:,}",
              f"  would delete: {len(p.passages):,}",
              f"  stay: {len(p.kept_passages):,}"]
    lines += [f"    {reason}: {_n(n, 'passage')} ({_n(refs, 'row')})"
              for reason, n, refs in _reasons(p.kept_passages)]
    lines += [f"Retired documents: {p.retired_documents:,}",
              f"  would delete: {len(p.documents):,}",
              f"  stay: {len(p.kept_documents):,}"]
    lines += [f"    {reason}: {_n(n, 'document')} ({_n(refs, 'row')})"
              for reason, n, refs in _reasons(p.kept_documents)]
    batches = math.ceil(len(p.passages) / BATCH_SIZE) + math.ceil(len(p.documents) / BATCH_SIZE)
    lines += ["", f"Batches: {batches} of at most {BATCH_SIZE:,} rows, each its own transaction",
              "", "Transaction log (WAL), estimated generously, before compression:",
              f"  passages: {w.passage_rows:,} rows on {w.passage_pages:,} heap pages, "
              f"{w.toast_pages:,} toast pages",
              f"  documents and their parts: {w.document_rows:,} rows on "
              f"{w.document_pages:,} pages",
              f"  outlines and tombstone snapshots rewritten: "
              f"{_mb(w.outline_bytes + w.tombstone_bytes)}",
              f"  purge-retired total: {_mb(w.purge_bytes)}; needs "
              f"{_mb(WalEstimate.headroom(w.purge_bytes))} free on the database disk",
              f"  VACUUM (analyze) chunks afterwards: at most {_mb(w.vacuum_bytes)}; needs "
              f"{_mb(WalEstimate.headroom(w.vacuum_bytes))} free",
              "  Read Database -> Disk in the Supabase dashboard right before each, and pass "
              "the free space as --disk-free-gb."]
    lines += ["", "A live run now would refuse:" if p.refusals else
              "A live run now would pass the publish checks (the lock and the disk are "
              "checked when it starts)."]
    lines += [f"  - {r}" for r in p.refusals]
    return lines


# --------------------------------------------------------------------------- execute

@dataclass
class PurgeResult:
    passages: int = 0
    documents: int = 0
    newly_kept: int = 0         # rows someone pointed at between the plan and their batch
    batches: int = 0
    outlines: int = 0


# Before a passage row goes, its tombstone keeps where it was, so an old reader link to
# it still finds the removal notice (app/corpus_lifecycle.py reads these keys).
_KEEP_LOCATION_SQL = """
    UPDATE public.corpus_tombstones t
    SET snapshot = t.snapshot || jsonb_build_object('anchor', c.anchor,
                                                    'chapter_key', c.chapter_key)
    FROM public.chunks c
    WHERE t.entity = 'passage' AND t.id = c.id AND c.id = ANY($1::uuid[])
      AND NOT (t.snapshot ? 'anchor' AND t.snapshot ? 'chapter_key')
"""


async def _batch_start(conn, release: str) -> list[Reference]:
    """Start a batch: the publish lock, the refusals again, and the foreign keys read
    afresh under a table lock that keeps a new one from being added until the commit
    (ADD FOREIGN KEY needs the same lock; only a publish writes these tables)."""
    await conn.execute("SET LOCAL lock_timeout = '2s'")
    await _no_row_security(conn)
    await lock_publishes(conn)
    await conn.execute(
        "LOCK TABLE public.chunks, public.documents IN SHARE ROW EXCLUSIVE MODE")
    problems = await refusals(conn, release)
    if problems:
        raise RetentionRefused("REFUSING: " + "; ".join(problems))
    return await references(conn)


async def _delete_passages(conn, release: str, batch: list[str],
                           result: PurgeResult) -> None:
    async with conn.transaction():
        refs = await _batch_start(conn, release)
        # Locking the rows first makes any user row added from here on wait for this
        # commit (its foreign key check needs them), and the check below, a new
        # statement, sees every one committed before.
        locked = [r["id"] for r in await conn.fetch(
            """SELECT id::text AS id FROM public.chunks
               WHERE id = ANY($1::uuid[]) AND retired_at IS NOT NULL
               ORDER BY id FOR UPDATE""", batch)]
        blocked = await passage_blocks(conn, refs, locked)
        ids = [i for i in locked if i not in blocked]
        await conn.execute(_KEEP_LOCATION_SQL, ids)
        documents = sorted({r["document_id"] for r in await conn.fetch(
            """DELETE FROM public.chunks WHERE id = ANY($1::uuid[]) AND retired_at IS NOT NULL
               RETURNING document_id::text AS document_id""", ids)})
        # 0037's trigger cleared chunk_count for these documents; put their outlines back.
        for d in documents:
            await conn.execute("SELECT public.refresh_document_outline($1::uuid)", d)
    result.passages += len(ids)
    result.newly_kept += len(blocked) + len(batch) - len(locked)
    result.outlines += len(documents)


async def _delete_documents(conn, release: str, batch: list[str],
                            result: PurgeResult) -> None:
    async with conn.transaction():
        refs = await _batch_start(conn, release)
        locked = [r["id"] for r in await conn.fetch(
            """SELECT id::text AS id FROM public.documents
               WHERE id = ANY($1::uuid[]) AND retired_at IS NOT NULL
               ORDER BY id FOR UPDATE""", batch)]
        blocked = await document_blocks(conn, refs, locked)
        ids = [i for i in locked if i not in blocked]
        done = await conn.execute(
            "DELETE FROM public.documents WHERE id = ANY($1::uuid[]) AND retired_at IS NOT NULL",
            ids)
    result.documents += int(done.split()[-1])
    result.newly_kept += len(blocked) + len(batch) - len(locked)


async def execute(conn, release: str, *, disk_free_bytes: int | None,
                  batch_size: int = BATCH_SIZE, progress: Callable[[str], None] = print,
                  after_batch: Callable | None = None) -> PurgeResult:
    """Delete what `plan` finds, in batches. `after_batch` is a test hook, awaited
    with the batch number after each commit."""
    p = await read_plan(conn, release)
    if p.refusals:
        raise RetentionRefused("REFUSING: " + "; ".join(p.refusals))
    need = WalEstimate.headroom(p.wal.purge_bytes)
    if disk_free_bytes is None or disk_free_bytes < need:
        raise RetentionRefused(
            f"REFUSING: the purge needs {_mb(need)} free on the database disk (twice its "
            f"estimated WAL of {_mb(p.wal.purge_bytes)}, plus 1 GB); read Database -> Disk "
            "in the Supabase dashboard and pass the free space as --disk-free-gb"
            + ("" if disk_free_bytes is None else f" (given {_mb(disk_free_bytes)})"))
    result = PurgeResult()
    work = [("passages", _delete_passages, p.passages[i:i + batch_size])
            for i in range(0, len(p.passages), batch_size)]
    work += [("documents", _delete_documents, p.documents[i:i + batch_size])
             for i in range(0, len(p.documents), batch_size)]
    for number, (kind, run, batch) in enumerate(work, 1):
        await run(conn, release, batch, result)
        result.batches = number
        progress(f"batch {number}/{len(work)} ({kind}) committed: {result.passages:,} "
                 f"passages and {result.documents:,} documents deleted so far, "
                 f"{result.newly_kept} kept since the plan")
        if after_batch is not None:
            await after_batch(number)
    return result


# --------------------------------------------------------------------------- Qdrant

@dataclass
class OldCollection:
    name: str | None
    points: int | None
    problems: list[str]


async def old_collection(conn, qdrant, release: str, alias: str) -> OldCollection:
    """The Qdrant collection the publish's switch moved the live alias away from, and
    why deleting it must wait. Reads only."""
    row = await conn.fetchrow("SELECT * FROM corpus_publishes WHERE id = $1", release)
    problems = await refusals(conn, release)
    name = row["previous_qdrant_collection"] if row is not None else None
    if row is not None and name is None:
        problems.append(f"publish '{release}' records no previous collection")
    points = None
    if name is not None:
        owners = await conn.fetch(
            "SELECT id FROM corpus_publishes WHERE qdrant_collection = $1 ORDER BY id", name)
        problems += [f"'{name}' is the collection of publish '{r['id']}'" for r in owners]
        aliases = (await qdrant.get_aliases()).aliases
        problems += [f"alias '{a.alias_name}' points at '{name}'" for a in aliases
                     if a.collection_name == name]
        if not any(a.alias_name == alias for a in aliases):
            problems.append(f"the live alias '{alias}' does not exist")
        if await qdrant.collection_exists(name):
            points = (await qdrant.count(name, exact=True)).count
        else:
            problems.append(f"'{name}' does not exist (already deleted?)")
    return OldCollection(name=name, points=points, problems=problems)


async def drop_old_collection(conn, qdrant, release: str, alias: str,
                              confirm: str) -> tuple[str, bool]:
    """Delete the old collection, once nothing needs it and `confirm` names it.
    Returns its name and whether this call deleted it (False: it was already gone)."""
    async with conn.transaction():
        await lock_publishes(conn)
        old = await old_collection(conn, qdrant, release, alias)
        gone = f"'{old.name}' does not exist (already deleted?)"
        if old.problems and old.problems != [gone]:
            raise RetentionRefused("REFUSING: " + "; ".join(old.problems))
        if confirm != old.name:
            raise RetentionRefused(f"REFUSING: --confirm must name the collection, "
                                   f"'{old.name}'")
        if not old.problems:
            await qdrant.delete_collection(old.name)
    # Already absent: a retry after a deletion whose response was lost has nothing to do.
    return old.name, not old.problems
