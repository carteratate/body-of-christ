"""Read-only export of the live corpus for the release report (corpus-cleanup item 0.1c).

    cd datapipeline
    python3 scripts/export_live_snapshot.py [--date YYYY-MM-DD] [--root <dir>]

Opens one connection to DATABASE_URL (the environment, else datapipeline/.env), sets the
session read only before its first query, and reads everything inside one READ ONLY,
REPEATABLE READ transaction, so the passages and the reference counts describe one moment.
It issues SELECTs only. It writes, under releases/snapshots/<date>/ (gitignored: the
snapshot holds in-copyright text and must never be committed):

- passages.jsonl.gz: one row per chunk, the fields in PASSAGE_FIELDS.
- documents.jsonl: one row per document, the fields in DOCUMENT_FIELDS.
- references.json: per passage ID, how many rows of each user table in REFERENCE_TABLES
  point at it; per document ID, the reading_progress row count and its rows grouped by
  (chapter_key, anchor). Counts only: no user_id, no query text, no timestamps.
- snapshot.json: when, the row count of every table read, and the sha256 of each file.

It also records the snapshot in the tracked index releases/snapshots.json (date, row counts
and sha256s, no content), so a release report can name the snapshot it used and a reviewer
can check a local copy against it. An existing snapshot directory is never overwritten.
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASES = os.path.join(DATAPIPELINE, "releases")
SNAPSHOT_ROOT = os.path.join(RELEASES, "snapshots")
INDEX_PATH = os.path.join(RELEASES, "snapshots.json")

PASSAGES_FILE = "passages.jsonl.gz"
DOCUMENTS_FILE = "documents.jsonl"
REFERENCES_FILE = "references.json"
SNAPSHOT_FILE = "snapshot.json"
FORMAT = 1

# checks.health.load_snapshot reads these; unit_label lets the release report treat the
# display pieces of one Summa objection or reply as one unit.
PASSAGE_FIELDS = ("id", "document_id", "collection", "title", "author", "anchor",
                  "chapter_key", "chapter_label", "reference", "unit_label", "position",
                  "content")
DOCUMENT_FIELDS = ("id", "collection", "title", "author", "year", "translation",
                   "chunk_count", "metadata")
# User tables that reference a passage by chunk_id. Every one cascades on delete (D3).
REFERENCE_TABLES = ("retrievals", "bookmarks", "guest_trial_retrievals", "retrieval_labels")

READ_ONLY = "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"

PASSAGES_SQL = """
SELECT c.id::text AS id, c.document_id::text AS document_id, d.collection, d.title,
       d.author, c.anchor, c.chapter_key, c.chapter_label, c.reference, c.unit_label,
       c.position, c.content
FROM chunks c JOIN documents d ON d.id = c.document_id
ORDER BY d.collection, c.document_id, c.position, c.id
"""
# documents.chunk_count arrived in 0037; a database without it exports null.
DOCUMENT_COLUMNS_SQL = """
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'documents'
"""
TABLE_EXISTS_SQL = "SELECT to_regclass($1) IS NOT NULL"
READ_ONLY_CHECK_SQL = "SELECT current_setting('transaction_read_only')"


def documents_sql(columns: set[str]) -> str:
    select = ", ".join(
        "id::text AS id" if f == "id" else (f if f in columns else f"NULL AS {f}")
        for f in DOCUMENT_FIELDS)
    return f"SELECT {select} FROM documents ORDER BY id"


def count_sql(table: str) -> str:
    return f"SELECT count(*) FROM public.{table}"


def references_sql(table: str) -> str:
    return (f"SELECT chunk_id::text AS chunk_id, count(*) AS n FROM public.{table} "
            "GROUP BY chunk_id ORDER BY chunk_id")


READING_PROGRESS_SQL = """
SELECT document_id::text AS document_id, chapter_key, anchor, count(*) AS n
FROM public.reading_progress
GROUP BY document_id, chapter_key, anchor
ORDER BY document_id, chapter_key, anchor NULLS FIRST
"""


# --------------------------------------------------------------------------- read

async def read_live(conn) -> dict:
    """Everything the snapshot holds, read through `conn` (an asyncpg connection or a
    fake with the same execute / fetch / fetchval / transaction methods)."""
    await conn.execute(READ_ONLY)
    async with conn.transaction(isolation="repeatable_read", readonly=True):
        if await conn.fetchval(READ_ONLY_CHECK_SQL) != "on":
            raise RuntimeError("REFUSING: the transaction is not read only")

        async def exists(table: str) -> bool:
            return bool(await conn.fetchval(TABLE_EXISTS_SQL, f"public.{table}"))

        passages = [dict(r) for r in await conn.fetch(PASSAGES_SQL)]
        columns = {r["column_name"] for r in await conn.fetch(DOCUMENT_COLUMNS_SQL)}
        documents = [dict(r) for r in await conn.fetch(documents_sql(columns))]
        tables = {"chunks": await conn.fetchval(count_sql("chunks")),
                  "documents": await conn.fetchval(count_sql("documents"))}

        by_passage: dict[str, dict[str, int]] = {}
        for table in REFERENCE_TABLES:
            if not await exists(table):
                tables[table] = None
                continue
            tables[table] = await conn.fetchval(count_sql(table))
            for r in await conn.fetch(references_sql(table)):
                by_passage.setdefault(r["chunk_id"], {})[table] = r["n"]

        by_document: dict[str, dict] = {}
        if await exists("reading_progress"):
            tables["reading_progress"] = await conn.fetchval(count_sql("reading_progress"))
            for r in await conn.fetch(READING_PROGRESS_SQL):
                doc = by_document.setdefault(r["document_id"],
                                             {"reading_progress": 0, "positions": []})
                doc["reading_progress"] += r["n"]
                doc["positions"].append({"chapter_key": r["chapter_key"],
                                         "anchor": r["anchor"], "rows": r["n"]})
        else:
            tables["reading_progress"] = None

    for d in documents:
        if isinstance(d.get("metadata"), str):   # asyncpg returns jsonb as text
            d["metadata"] = json.loads(d["metadata"])
    references = {
        "passages": {pid: {t: counts.get(t, 0) for t in REFERENCE_TABLES}
                     for pid, counts in sorted(by_passage.items())},
        "documents": dict(sorted(by_document.items())),
    }
    return {"passages": passages, "documents": documents, "references": references,
            "tables": tables}


# --------------------------------------------------------------------------- write

def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _jsonl(rows: list[dict], fields: tuple[str, ...]) -> bytes:
    return "".join(json.dumps({f: r.get(f) for f in fields}, ensure_ascii=False) + "\n"
                   for r in rows).encode("utf-8")


def write_snapshot(data: dict, root: str, date: str, exported_at: str,
                   index_path: str = INDEX_PATH) -> str:
    """Write the snapshot directory and its index entry; return the directory."""
    final = os.path.join(root, date)
    if os.path.exists(final):
        raise FileExistsError(f"{final} exists; a snapshot is never overwritten")
    os.makedirs(root, exist_ok=True)
    work = tempfile.mkdtemp(prefix=f".{date}-", dir=root)
    try:
        # mtime 0 and no file name in the gzip header, so equal content gives an equal hash.
        buffer = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as gz:
            gz.write(_jsonl(data["passages"], PASSAGE_FIELDS))
        with open(os.path.join(work, PASSAGES_FILE), "wb") as f:
            f.write(buffer.getvalue())
        with open(os.path.join(work, DOCUMENTS_FILE), "wb") as f:
            f.write(_jsonl(data["documents"], DOCUMENT_FIELDS))
        with open(os.path.join(work, REFERENCES_FILE), "w", encoding="utf-8") as f:
            json.dump(data["references"], f, indent=1, sort_keys=True)
            f.write("\n")
        files = {name: _sha256(os.path.join(work, name))
                 for name in (PASSAGES_FILE, DOCUMENTS_FILE, REFERENCES_FILE)}
        meta = {"format": FORMAT, "date": date, "exported_at": exported_at,
                "tables": data["tables"], "files": files}
        with open(os.path.join(work, SNAPSHOT_FILE), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=1)
            f.write("\n")
        os.rename(work, final)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    record_in_index(meta, index_path)
    return final


def record_in_index(meta: dict, index_path: str = INDEX_PATH) -> None:
    """Add or replace this date's entry in the tracked index; keep every other entry."""
    index = {"snapshots": []}
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
    entries = [e for e in index.get("snapshots", []) if e.get("date") != meta["date"]]
    entries.append({k: meta[k] for k in ("date", "exported_at", "tables", "files")})
    index["snapshots"] = sorted(entries, key=lambda e: e["date"])
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1)
        f.write("\n")


# --------------------------------------------------------------------------- main

async def _export(url: str, root: str, date: str) -> str:
    import asyncpg

    # statement_cache_size=0: the Supabase pooler does not keep prepared statements.
    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        data = await read_live(conn)
    finally:
        await conn.close()
    return write_snapshot(data, root, date, exported_at)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--root", default=SNAPSHOT_ROOT,
                        help="where the <date> directory is made (default releases/snapshots)")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(os.path.join(DATAPIPELINE, ".env"))
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    out = asyncio.run(_export(url, args.root, args.date))
    with open(os.path.join(out, SNAPSHOT_FILE), encoding="utf-8") as f:
        tables = json.load(f)["tables"]
    print(f"wrote {out}: " + ", ".join(f"{t} {n}" for t, n in tables.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
