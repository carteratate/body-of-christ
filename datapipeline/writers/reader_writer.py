"""Write staged documents and passages into the `staging` schema (2.2w, D2).

A publish never writes the live corpus tables here. A stage builds each collection into
`staging.*` (made by 2.2a's `create_corpus_staging()`, the live tables' shape with no
foreign keys), and `publish.py apply` later moves it into live in one transaction.
Nothing in this module issues a statement against a `public` table except SELECTs, and
nothing anywhere in the datapipeline deletes a live chunk or document row (D3).

Does NOT populate content_embedding (retired: vectors live only in Qdrant).
chunks.id is the passage ID (`Passage.id`, from 2.1's registry), so it matches the
Qdrant point ID.
"""
from __future__ import annotations

import json

import asyncpg

import contents
import reader_access
from model import Document

# The tables 2.2a's staging schema mirrors, in the order a stage clears them.
STAGED_TABLES = ("corpus_redirects", "corpus_tombstones", "document_contents",
                 "document_works", "document_chapters", "chunks", "documents")

DOCUMENT_COLUMNS = (
    "id", "collection", "title", "translation", "author", "year", "metadata",
    "reader_access", "genre", "issuer", "issuer_label", "date_display", "certainty",
    "attribution_note", "notes", "source_credit", "clavis_ref", "superseded_by",
    "superseded_note", "form",
)
CHUNK_COLUMNS = (
    "id", "document_id", "content", "position", "reference", "anchor", "chapter_key",
    "chapter_label", "unit_label", "metadata", "searchable", "language", "work_key",
    "passage_author", "voice", "note", "superseded_by",
)
WORK_COLUMNS = ("document_id", "work_key", "ordinal", "title", "author", "certainty",
                "attribution_note", "notes", "date_display", "year", "genre", "clavis_ref")
CONTENTS_COLUMNS = ("document_id", "ordinal", "parent_ordinal", "depth", "node_key", "kind",
                    "label", "short_label", "chapter_key", "anchor", "range_label")
TOMBSTONE_COLUMNS = ("entity", "id", "document_id", "retired_at", "publish_id",
                     "removal_key", "rule", "reason_code", "public_reason", "church_act",
                     "snapshot")
REDIRECT_COLUMNS = ("entity", "old_id", "old_document_id", "old_anchor", "new_id",
                    "new_document_id", "new_anchor", "kind", "publish_id")

# Columns compared between staging and live. Defaults are left out: `LIKE` copies an
# identity column's sequence under another name. A column's place is its rank, not its
# attribute number, which keeps a gap where a column was dropped (2.2c's drop-and-add
# path before Postgres 17) that `LIKE` closes.
_SHAPE_SQL = """
SELECT table_name, column_name, data_type, is_nullable, is_generated,
       coalesce(generation_expression, '') AS generation_expression,
       row_number() OVER (PARTITION BY table_name ORDER BY ordinal_position) AS ordinal_position
FROM information_schema.columns
WHERE table_schema = $1 AND table_name = ANY($2::text[])
ORDER BY table_name, ordinal_position
"""


def _json(value) -> str | None:
    # The datapipeline's connections register no jsonb codec, so jsonb goes as text.
    return json.dumps(value) if value is not None else None


async def staging_exists(conn: asyncpg.Connection) -> bool:
    for t in STAGED_TABLES:
        if not await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"staging.{t}"):
            return False
    return True


async def staging_shape_problems(conn: asyncpg.Connection) -> list[str]:
    """How the staging tables differ in columns from the live ones; empty when equal.
    Generation expressions count: a migration that redefines a generated column (2.2c's
    search_vector) leaves staging made before it on the old one."""
    def shape(rows):
        return {(r["table_name"], r["column_name"]):
                (r["data_type"], r["is_nullable"], r["is_generated"],
                 r["generation_expression"], r["ordinal_position"])
                for r in rows}
    live = shape(await conn.fetch(_SHAPE_SQL, "public", list(STAGED_TABLES)))
    staged = shape(await conn.fetch(_SHAPE_SQL, "staging", list(STAGED_TABLES)))
    problems = [f"staging.{t}.{c} is missing" for (t, c) in sorted(live.keys() - staged.keys())]
    problems += [f"staging.{t}.{c} is not in live" for (t, c) in sorted(staged.keys() - live.keys())]
    problems += [f"staging.{t}.{c} is {staged[(t, c)]}, live is {live[(t, c)]}"
                 for (t, c) in sorted(live.keys() & staged.keys())
                 if live[(t, c)] != staged[(t, c)]]
    return problems


async def ensure_staging(conn: asyncpg.Connection) -> None:
    """Create the staging tables if absent (2.2a's function), and refuse when existing
    ones differ in shape from live."""
    live = {r["column_name"] for r in await conn.fetch(_SHAPE_SQL, "public", ["documents"])}
    missing = [c for c in DOCUMENT_COLUMNS if c not in live]
    if missing:
        # documents.form is migration 0044's (issue #330).
        raise ValueError(f"REFUSING: live documents has no {', '.join(missing)}; apply the "
                         "migration that adds it (documents.form: 0044) first")
    if not await staging_exists(conn):
        await conn.execute("SELECT public.create_corpus_staging()")
    problems = await staging_shape_problems(conn)
    if problems:
        raise ValueError("REFUSING: the staging tables differ from live: "
                         + "; ".join(problems[:10]))


async def clear_staged_collections(conn: asyncpg.Connection, collections: list[str]) -> None:
    """Remove the staged rows of `collections` (staging tables only) before they are
    staged again. Tombstones are found by the collection in their snapshot, redirects by
    the live or staged document they leave or reach."""
    documents = "SELECT id FROM staging.documents WHERE collection = ANY($1::text[])"
    live_documents = "SELECT id FROM public.documents WHERE collection = ANY($1::text[])"
    await conn.execute(
        f"""DELETE FROM staging.corpus_redirects
            WHERE old_document_id IN ({live_documents}) OR old_document_id IN ({documents})
               OR new_document_id IN ({documents})""", collections)
    await conn.execute(
        "DELETE FROM staging.corpus_tombstones WHERE snapshot->>'collection' = ANY($1::text[])",
        collections)
    for table in ("document_contents", "document_works", "document_chapters", "chunks"):
        await conn.execute(
            f"DELETE FROM staging.{table} WHERE document_id IN ({documents})", collections)
    await conn.execute("DELETE FROM staging.documents WHERE collection = ANY($1::text[])",
                       collections)


def document_row(doc: Document) -> tuple:
    return (doc.id, doc.collection, doc.title, doc.translation or "", doc.author, doc.year,
            _json(doc.metadata or None), reader_access.access_for_document(doc), doc.genre,
            doc.issuer, doc.issuer_label, doc.date_display, doc.certainty,
            doc.attribution_note, doc.notes, doc.source_credit, doc.clavis_ref,
            doc.superseded_by, doc.superseded_note, doc.form)


def chunk_rows(doc: Document) -> list[tuple]:
    by_anchor = {p.anchor: p.id for p in doc.passages}
    rows = []
    for p in doc.passages:
        if p.id is None:
            raise ValueError(f"{doc.title}: passage {p.anchor} has no ID; the stage assigns them")
        rows.append((p.id, doc.id, p.content, p.position, p.reference, p.anchor,
                     p.chapter_key, p.chapter_label, p.unit_label, _json(p.metadata or None),
                     p.searchable, p.language, p.work_key, p.passage_author, p.voice, p.note,
                     by_anchor.get(p.superseded_by_anchor) if p.superseded_by_anchor else None))
    return rows


def work_rows(doc: Document) -> list[tuple]:
    return [(doc.id, w.work_key, w.ordinal, w.title, w.author, w.certainty,
             w.attribution_note, w.notes, w.date_display, w.year, w.genre, w.clavis_ref)
            for w in doc.works]


def contents_rows(doc: Document) -> list[tuple]:
    if doc.contents is None:
        return []
    return [(doc.id, r.ordinal, r.parent_ordinal, r.depth, r.node_key, r.kind, r.label,
             r.short_label, r.chapter_key, r.anchor, r.range_label)
            for r in contents.flatten(doc.contents)]


def _insert_sql(table: str, columns: tuple[str, ...], casts: dict[str, str]) -> str:
    values = ", ".join(f"${i}{casts.get(c, '')}" for i, c in enumerate(columns, 1))
    return f"INSERT INTO staging.{table} ({', '.join(columns)}) VALUES ({values})"


_UUID = "::uuid"
_JSONB = "::jsonb"
_DOCUMENT_SQL = _insert_sql("documents", DOCUMENT_COLUMNS,
                            {"id": _UUID, "metadata": _JSONB, "superseded_by": _UUID})
_CHUNK_SQL = _insert_sql("chunks", CHUNK_COLUMNS, {"id": _UUID, "document_id": _UUID,
                                                   "metadata": _JSONB, "superseded_by": _UUID})
_WORK_SQL = _insert_sql("document_works", WORK_COLUMNS, {"document_id": _UUID})
_CONTENTS_SQL = _insert_sql("document_contents", CONTENTS_COLUMNS, {"document_id": _UUID})
_TOMBSTONE_SQL = _insert_sql("corpus_tombstones", TOMBSTONE_COLUMNS,
                             {"id": _UUID, "document_id": _UUID, "snapshot": _JSONB})
_REDIRECT_SQL = _insert_sql("corpus_redirects", REDIRECT_COLUMNS,
                            {"old_id": _UUID, "old_document_id": _UUID, "new_id": _UUID,
                             "new_document_id": _UUID})


async def write_staged_document(conn: asyncpg.Connection, doc: Document) -> None:
    """Insert one built document into staging: its row (with `reader_access` from the
    rights inventory, D12), works, passages and contents tree, then its staged reader
    outline. Call inside the stage's transaction, after `clear_staged_collections`.
    Every passage must carry its `Passage.id`."""
    contents.check(doc)  # a broken tree writes nothing
    await conn.execute(_DOCUMENT_SQL, *document_row(doc))
    if doc.works:
        await conn.executemany(_WORK_SQL, work_rows(doc))
    rows = chunk_rows(doc)
    if rows:
        await conn.executemany(_CHUNK_SQL, rows)
    tree = contents_rows(doc)
    if tree:
        # Pre-order, so each parent row exists before the rows that reference it.
        await conn.executemany(_CONTENTS_SQL, tree)
    await conn.execute("SELECT staging.refresh_document_outline($1::uuid)", doc.id)


async def copy_live_annotations(conn: asyncpg.Connection, collections: list[str]) -> None:
    """Give each staged passage the live row's annotation, by ID. No publish writes
    annotations (stages/enrich_io.py does) and the apply leaves them as they are, so
    this makes staging read the way live will after the apply, for the eval (4.2)."""
    await conn.execute(
        """
        UPDATE staging.chunks s
        SET annotation = c.annotation, annotation_vector = c.annotation_vector
        FROM public.chunks c, staging.documents d
        WHERE c.id = s.id AND d.id = s.document_id AND d.collection = ANY($1::text[])
          AND (c.annotation IS NOT NULL OR c.annotation_vector IS NOT NULL)
        """, collections)


async def write_staged_retirements(conn: asyncpg.Connection, tombstones: list[dict],
                                   redirects: list[dict]) -> None:
    """Insert the stage's tombstone and redirect rows into staging."""
    if tombstones:
        await conn.executemany(_TOMBSTONE_SQL, [
            tuple(_json(t[c]) if c == "snapshot" else t[c] for c in TOMBSTONE_COLUMNS)
            for t in tombstones])
    if redirects:
        await conn.executemany(_REDIRECT_SQL, [
            tuple(r[c] for c in REDIRECT_COLUMNS) for r in redirects])
