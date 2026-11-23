"""The release report of a staged publish (2.2w): `publish.py report`.

Runs 0.1c's report (release/report.py) with the staged corpus in place of a build, and
the live corpus, exported read-only at the time of the report, as its snapshot. Then
adds the publish checks:

- `retirements_explained`: every live ID the staging lacks has a tombstone or a passage
  redirect (D4).
- `ids_kept`: each live ID of the staged collections is staged under the same ID, or
  explained; the counts, and every new ID with its registry reason (D1).
- `points_match`: one point per staged passage, with `collection`, `genre`, `issuer` and
  `searchable` equal to staging.
- `index.embedding_input_hash`: every point's `embed_sha256` is the hash of its staged
  passage's embedding input, and every point names its model (C-23).
- `index.dedup_collision_rate:<collection>`: the share of same-document passage pairs
  within two positions whose vectors exceed the API's dedup threshold, beside the live
  figure; flagged above 5% (C-09). Informs RF-1; fails nothing.
- the document-facts diff (2.3), the works diff (3.2), the held-texts diff (4.3:
  `metadata.held_texts` entries added, removed or changed per document), user impact,
  the staging storage and the projected database size, and the 10% shrink and churn
  warnings that used to stop a publish.

Writes publish.json and a "Publish checks" section at the end of report.md, then records
`<sha256 of report.json and publish.json>:<sha256 of the staged rows>` in
`corpus_publishes.report_sha256`; `apply` refuses when the staged rows no longer match.
That one write is the report's only one, and it asks the publish lock for the `stage`
step the stage itself needed.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

DATAPIPELINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if DATAPIPELINE not in sys.path:
    sys.path.insert(0, DATAPIPELINE)

import collection_keys  # noqa: E402
import publication  # noqa: E402
from model import ContentsNode, Document, Passage, Work  # noqa: E402
from release import report as release_report  # noqa: E402
from writers import search_writer  # noqa: E402
from writers.reader_writer import STAGED_TABLES  # noqa: E402

# services/api/app/rag/dedup.py: two passages of one document within two positions whose
# vectors exceed this are deduplicated.
DEDUP_COSINE_THRESHOLD = 0.9
DEDUP_WINDOW = 2
DEDUP_FLAG = 0.05
# The checks that used to refuse a publish outright (publication._validate_build).
MAX_SHRINK = 0.10
USER_TABLES = ("retrievals", "bookmarks", "retrieval_labels", "guest_trial_retrievals")
FACT_COLUMNS = ("title", "author", "year", "translation", "reader_access", "genre", "issuer",
                "issuer_label", "date_display", "certainty", "attribution_note", "notes",
                "source_credit", "clavis_ref", "superseded_by", "superseded_note", "form")
# A work's labels inside its document (D6; 3.2), `document_works`.
WORK_COLUMNS = ("title", "author", "certainty", "attribution_note", "notes", "date_display",
                "year", "genre", "clavis_ref")


class ReportRefused(ValueError):
    pass


# --------------------------------------------------------------------------- staged content

async def staged_content_sha256(conn) -> str:
    """One hash over every row of every staging table, in a stable order. Staging holds
    one publish at a time, so this is that publish's staged content."""
    h = hashlib.sha256()
    for table in sorted(STAGED_TABLES):
        digest = await conn.fetchval(
            f"""SELECT encode(sha256(convert_to(coalesce(
                    string_agg(t::text, E'\\n' ORDER BY t::text), ''), 'UTF8')), 'hex')
                FROM staging.{table} t""")
        h.update(f"{table}:{digest}\n".encode())
    return h.hexdigest()


def _tree(rows: list[dict]) -> list[ContentsNode] | None:
    if not rows:
        return None
    nodes, roots = {}, []
    for r in sorted(rows, key=lambda r: r["ordinal"]):
        node = ContentsNode(key=r["node_key"], kind=r["kind"], label=r["label"],
                            short_label=r["short_label"], chapter_key=r["chapter_key"],
                            anchor=r["anchor"], range_label=r["range_label"])
        nodes[r["ordinal"]] = node
        (nodes[r["parent_ordinal"]].children if r["parent_ordinal"] else roots).append(node)
    return roots


async def staged_documents(conn, collections: list[str]) -> dict[str, list[Document]]:
    """The staged corpus as Documents, per collection, each passage's ID in `id` and in
    `metadata["passage_id"]` (which 0.1c's remap reads)."""
    docs = await conn.fetch(
        """SELECT * FROM staging.documents WHERE collection = ANY($1::text[])
           ORDER BY id""", collections)
    ids = [d["id"] for d in docs]
    chunks, works, trees = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in await conn.fetch("SELECT * FROM staging.chunks WHERE document_id = ANY($1::uuid[]) "
                              "ORDER BY document_id, position", ids):
        chunks[r["document_id"]].append(r)
    for r in await conn.fetch("SELECT * FROM staging.document_works "
                              "WHERE document_id = ANY($1::uuid[]) ORDER BY ordinal", ids):
        works[r["document_id"]].append(r)
    for r in await conn.fetch("SELECT * FROM staging.document_contents "
                              "WHERE document_id = ANY($1::uuid[])", ids):
        trees[r["document_id"]].append(dict(r))
    out: dict[str, list[Document]] = {c: [] for c in collections}
    for d in docs:
        by_id = {str(c["id"]): c["anchor"] for c in chunks[d["id"]]}
        passages = []
        for c in chunks[d["id"]]:
            metadata = json.loads(c["metadata"]) if c["metadata"] else {}
            passages.append(Passage(
                content=c["content"], reference=c["reference"] or "", anchor=c["anchor"] or "",
                chapter_key=c["chapter_key"] or "", chapter_label=c["chapter_label"] or "",
                position=c["position"], unit_label=c["unit_label"],
                metadata={**metadata, "passage_id": str(c["id"])}, work_key=c["work_key"],
                searchable=c["searchable"], language=c["language"],
                passage_author=c["passage_author"], voice=c["voice"], note=c["note"],
                superseded_by_anchor=by_id.get(str(c["superseded_by"])) if c["superseded_by"] else None,
                id=str(c["id"])))
        out[d["collection"]].append(Document(
            id=str(d["id"]), collection=d["collection"], title=d["title"], author=d["author"],
            year=d["year"], translation=d["translation"] or "",
            metadata=json.loads(d["metadata"]) if d["metadata"] else None,
            passages=passages, contents=_tree(trees[d["id"]]),
            works=[Work(work_key=w["work_key"], ordinal=w["ordinal"], title=w["title"],
                        author=w["author"], certainty=w["certainty"],
                        attribution_note=w["attribution_note"], notes=w["notes"],
                        date_display=w["date_display"], year=w["year"], genre=w["genre"],
                        clavis_ref=w["clavis_ref"]) for w in works[d["id"]]],
            genre=d["genre"], form=d["form"], issuer=d["issuer"], issuer_label=d["issuer_label"],
            date_display=d["date_display"], certainty=d["certainty"],
            attribution_note=d["attribution_note"], notes=d["notes"],
            source_credit=d["source_credit"], clavis_ref=d["clavis_ref"],
            superseded_by=str(d["superseded_by"]) if d["superseded_by"] else None,
            superseded_note=d["superseded_note"]))
    return out


# --------------------------------------------------------------------------- live export

async def export_live(conn, root: str) -> str:
    """Export live read-only, as scripts/export_live_snapshot.py does, without the
    retired rows, into `root/<date>` with its own index; return the directory."""
    from scripts import export_live_snapshot as export

    exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = await export.read_live(conn)
    retired = {str(r["id"]) for r in await conn.fetch(
        "SELECT id FROM chunks WHERE retired_at IS NOT NULL")}
    retired_documents = {str(r["id"]) for r in await conn.fetch(
        "SELECT id FROM documents WHERE retired_at IS NOT NULL")}
    data["passages"] = [p for p in data["passages"] if p["id"] not in retired]
    data["documents"] = [d for d in data["documents"] if d["id"] not in retired_documents]
    return export.write_snapshot(data, root, exported_at[:10], exported_at,
                                 os.path.join(root, "snapshots.json"))


# --------------------------------------------------------------------------- checks

async def explanation_checks(conn, collections: list[str], registry_rows: dict) -> dict:
    """retirements_explained and ids_kept."""
    # Live rows still filed under an old key of a staged collection count (5.1b.3).
    live = {str(r["id"]): r for r in await conn.fetch(
        """SELECT c.id, c.document_id, d.collection FROM public.chunks c
           JOIN public.documents d ON d.id = c.document_id
           WHERE d.collection = ANY($1::text[]) AND c.retired_at IS NULL""",
        collection_keys.live_keys(collections))}
    staged = {str(r["id"]) for r in await conn.fetch(
        """SELECT s.id FROM staging.chunks s JOIN staging.documents d ON d.id = s.document_id
           WHERE d.collection = ANY($1::text[])""", collections)}
    retired = {str(r["id"]) for r in await conn.fetch(
        "SELECT id FROM staging.corpus_tombstones WHERE entity = 'passage'")}
    redirected = {str(r["old_id"]) for r in await conn.fetch(
        "SELECT old_id FROM staging.corpus_redirects WHERE entity = 'passage'")}
    kept = [i for i in live if i in staged]
    unexplained = sorted(i for i in live if i not in staged and i not in retired
                         and i not in redirected)
    new = sorted(staged - set(live))
    return {
        "kept": len(kept),
        "retired": len([i for i in live if i in retired and i not in staged]),
        "redirected": len([i for i in live if i in redirected and i not in staged]),
        "unexplained": unexplained,
        "new": [{"id": i, "reason": (registry_rows.get(i) or {}).get("added_by")
                 or "not in the passage registry: a new unit"} for i in new],
    }


async def point_checks(conn, qdrant, name: str, documents: dict[str, list[Document]],
                       model: str | None) -> dict:
    """points_match and index.embedding_input_hash."""
    from writers.qdrant import count_points, retrieve

    mismatches, hash_failures, counts = [], [], {}
    for collection, docs in documents.items():
        staged = sum(len(d.passages) for d in docs)
        points = await count_points(qdrant, name, collection)
        counts[collection] = {"staged": staged, "points": points}
        if points != staged:
            mismatches.append(f"{collection}: {points} points, {staged} staged passages")
        for d in docs:
            inputs = search_writer.embedding_inputs(d)
            found = await retrieve(qdrant, name, [p.id for p in d.passages], with_vectors=False)
            for p, text in zip(d.passages, inputs):
                point = found.get(p.id)
                if point is None:
                    mismatches.append(f"{p.id}: no point")
                    continue
                pl = point.payload or {}
                want = {"collection": d.collection, "genre": d.genre, "issuer": d.issuer,
                        "searchable": p.searchable}
                got = {k: pl.get(k) for k in want}
                if got != want:
                    mismatches.append(f"{p.id}: payload {got}, staged {want}")
                if pl.get("embed_sha256") != search_writer.input_sha256(text) \
                        or not pl.get("embed_model") or pl.get("embed_model") != model:
                    hash_failures.append(p.id)
    return {"counts": counts, "mismatches": mismatches, "hash_failures": hash_failures}


async def text_changes(conn, collections: list[str]) -> dict[str, int]:
    """Per staged collection, how many passages keep their live ID with different
    stored text. Informs; fails nothing (4.3's publish shows 0)."""
    rows = await conn.fetch(
        """SELECT d.collection, count(*) AS n
           FROM staging.chunks s JOIN staging.documents d ON d.id = s.document_id
           JOIN public.chunks c ON c.id = s.id
           WHERE d.collection = ANY($1::text[]) AND c.content IS DISTINCT FROM s.content
           GROUP BY d.collection""", collections)
    found = {r["collection"]: r["n"] for r in rows}
    return {c: found.get(c, 0) for c in collections}


async def live_point_changes(qdrant, name: str, live: str | None,
                             documents: dict[str, list[Document]]) -> dict:
    """Per staged collection, how many staged points differ from the live point of the
    same ID: in any payload field (its `content` is the passage text), and in
    `embed_sha256` (the embedding input); how many staged points have no live point of
    their ID, and how many live points of the collection staging lacks (the switch drops
    them). Informs; fails nothing. A publish that changes only document metadata (4.3's held texts)
    shows 0 and 0."""
    from writers.qdrant import retrieve, scroll_points

    out = {}
    if live is None:
        return out
    # A point staging has under another collection is not dropped (Boethius, 5.1b.3).
    all_staged = {p.id for docs in documents.values() for d in docs for p in d.passages}
    for collection, docs in documents.items():
        payload = embed = compared = missing = 0
        fields: set[str] = set()
        for d in docs:
            ids = [p.id for p in d.passages]
            new = await retrieve(qdrant, name, ids, with_vectors=False)
            old = await retrieve(qdrant, live, ids, with_vectors=False)
            for i in ids:
                if i not in new:
                    continue
                if i not in old:
                    missing += 1
                    continue
                compared += 1
                a, b = old[i].payload or {}, new[i].payload or {}
                if a != b:
                    payload += 1
                    fields |= {k for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
                embed += a.get("embed_sha256") != b.get("embed_sha256")
        live_only = 0
        for key in [collection, *collection_keys.old_keys(collection)]:
            async for page in scroll_points(qdrant, live, key):
                live_only += sum(str(p.id) not in all_staged for p in page)
        out[collection] = {"compared": compared, "payload_changed": payload,
                           "embed_sha256_changed": embed, "missing_live": missing,
                           "live_only": live_only, "fields": sorted(fields)}
    return out


def collision_rate(vectors: dict[str, list[float]], order: list[str]) -> tuple[int, int]:
    """(collisions, pairs) among passages within DEDUP_WINDOW positions of each other."""
    ids = [i for i in order if i in vectors]
    if len(ids) < 2:
        return 0, 0
    m = np.asarray([vectors[i] for i in ids], dtype=np.float32)
    m /= np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-12)
    hits = pairs = 0
    for k in range(1, DEDUP_WINDOW + 1):
        if len(ids) <= k:
            break
        sims = np.einsum("ij,ij->i", m[:-k], m[k:])
        pairs += len(sims)
        hits += int((sims > DEDUP_COSINE_THRESHOLD).sum())
    return hits, pairs


async def dedup_checks(conn, qdrant, name: str, live: str | None,
                       documents: dict[str, list[Document]]) -> dict:
    """index.dedup_collision_rate:<collection>, new and live, per staged collection. The
    live figure uses live documents in their live order."""
    from writers.qdrant import retrieve

    out = {}
    for collection, docs in documents.items():
        totals = {"new": [0, 0], "live": [0, 0]}
        live_order: dict[str, list[str]] = defaultdict(list)
        for r in await conn.fetch(
                """SELECT c.id::text AS id, c.document_id::text AS document_id
                   FROM public.chunks c JOIN public.documents d ON d.id = c.document_id
                   WHERE d.collection = ANY($1::text[]) AND c.retired_at IS NULL
                   ORDER BY c.document_id, c.position""",
                [collection, *collection_keys.old_keys(collection)]):
            live_order[r["document_id"]].append(r["id"])
        sides = [("new", name, d.id, [p.id for p in d.passages]) for d in docs]
        if live is not None:
            sides += [("live", live, document_id, order)
                      for document_id, order in live_order.items()]
        for side, source, document_id, order in sides:
            found = await retrieve(qdrant, source, order)
            vectors = {i: p.vector for i, p in found.items()
                       if (p.payload or {}).get("document_id", document_id) == document_id}
            hits, pairs = collision_rate(vectors, order)
            totals[side][0] += hits
            totals[side][1] += pairs
        rate = {side: (h / p if p else 0.0) for side, (h, p) in totals.items()}
        out[collection] = {"new": round(rate["new"], 4), "live": round(rate["live"], 4),
                           "pairs": totals["new"][1], "flagged": rate["new"] > DEDUP_FLAG}
    return out


async def facts_diff(conn, collections: list[str]) -> list[dict]:
    """Per document, the facts staging changes against live (2.3's diff)."""
    cols = ", ".join(f"d.{c} AS live_{c}, s.{c} AS staged_{c}" for c in FACT_COLUMNS)
    rows = await conn.fetch(
        f"""SELECT s.id::text AS id, s.collection, (d.id IS NULL) AS new_document, {cols}
            FROM staging.documents s LEFT JOIN public.documents d ON d.id = s.id
            WHERE s.collection = ANY($1::text[]) ORDER BY s.collection, s.id""", collections)
    out = []
    for r in rows:
        changed = {c: {"live": _plain(r[f"live_{c}"]), "staged": _plain(r[f"staged_{c}"])}
                   for c in FACT_COLUMNS
                   if not r["new_document"] and r[f"live_{c}"] != r[f"staged_{c}"]}
        if changed or r["new_document"]:
            out.append({"id": r["id"], "collection": r["collection"],
                        "new_document": r["new_document"], "changed": changed})
    return out


async def works_diff(conn, collections: list[str]) -> list[dict]:
    """Per work inside a document, the labels staging changes against live (3.2): each
    changed `document_works` column, and for a new work every value it is given."""
    cols = ", ".join(f"w.{c} AS live_{c}, s.{c} AS staged_{c}" for c in WORK_COLUMNS)
    rows = await conn.fetch(
        f"""SELECT s.document_id::text AS document_id, s.work_key, sd.collection,
                   (w.work_key IS NULL) AS new_work, {cols}
            FROM staging.document_works s
            JOIN staging.documents sd ON sd.id = s.document_id
            LEFT JOIN public.document_works w
                   ON w.document_id = s.document_id AND w.work_key = s.work_key
            WHERE sd.collection = ANY($1::text[])
            ORDER BY sd.collection, s.document_id, s.work_key""", collections)
    out = []
    for r in rows:
        changed = {c: {"live": _plain(r[f"live_{c}"]), "staged": _plain(r[f"staged_{c}"])}
                   for c in WORK_COLUMNS
                   if r[f"live_{c}"] != r[f"staged_{c}"]}
        if changed or r["new_work"]:
            out.append({"document_id": r["document_id"], "work_key": r["work_key"],
                        "collection": r["collection"], "new_work": r["new_work"],
                        "changed": changed})
    return out


async def held_texts_diff(conn, collections: list[str]) -> list[dict]:
    """Per document, the held-text entries (4.3, `metadata.held_texts`) staging adds,
    removes or changes against live, matched by `key`."""
    rows = await conn.fetch(
        """SELECT s.id::text AS id, s.collection, s.title,
                  s.metadata->'held_texts' AS staged, d.metadata->'held_texts' AS live
           FROM staging.documents s LEFT JOIN public.documents d ON d.id = s.id
           WHERE s.collection = ANY($1::text[])
             AND (s.metadata->'held_texts') IS DISTINCT FROM (d.metadata->'held_texts')
           ORDER BY s.collection, s.title, s.id""", collections)
    out = []
    for r in rows:
        staged = {h["key"]: h for h in json.loads(r["staged"] or "[]")}
        live = {h["key"]: h for h in json.loads(r["live"] or "[]")}
        changed = [{"key": k, "live": live[k], "staged": staged[k]}
                   for k in staged.keys() & live.keys() if staged[k] != live[k]]
        out.append({"id": r["id"], "collection": r["collection"], "title": r["title"],
                    "added": [h for k, h in staged.items() if k not in live],
                    "removed": sorted(live.keys() - staged.keys()),
                    "changed": sorted(changed, key=lambda c: c["key"]),
                    # Order matters to the reader, also among entries that stay.
                    "reordered": [k for k in staged if k in live] != [k for k in live
                                                                       if k in staged]})
    return out


async def metadata_diff(conn, collections: list[str]) -> list[dict]:
    """Per document, the `metadata` keys other than `held_texts` that staging changes
    against live: the apply replaces the whole object, so this shows what else a
    held-texts publish (4.3) would change."""
    rows = await conn.fetch(
        """SELECT s.id::text AS id, s.collection, s.title,
                  coalesce(s.metadata, '{}') - 'held_texts' AS staged,
                  coalesce(d.metadata, '{}') - 'held_texts' AS live
           FROM staging.documents s JOIN public.documents d ON d.id = s.id
           WHERE s.collection = ANY($1::text[])
             AND coalesce(s.metadata, '{}') - 'held_texts'
                 <> coalesce(d.metadata, '{}') - 'held_texts'
           ORDER BY s.collection, s.title, s.id""", collections)
    out = []
    for r in rows:
        staged, live = json.loads(r["staged"] or "{}"), json.loads(r["live"] or "{}")
        out.append({"id": r["id"], "collection": r["collection"], "title": r["title"],
                    "keys": sorted(k for k in staged.keys() | live.keys()
                                   if (k in staged) != (k in live)
                                   or staged.get(k) != live.get(k))})
    return out


def _plain(value):
    return str(value) if value is not None and not isinstance(value, (int, str, bool)) else value


async def user_impact(conn) -> dict:
    """User rows that point at the IDs this publish retires or redirects."""
    out = {}
    for label, sql in (
        ("retired", "SELECT id FROM staging.corpus_tombstones WHERE entity = 'passage'"),
        ("redirected", "SELECT old_id FROM staging.corpus_redirects WHERE entity = 'passage'"),
    ):
        out[label] = {t: await conn.fetchval(
            f"SELECT count(*) FROM public.{t} WHERE chunk_id IN ({sql})")
            for t in USER_TABLES}
    out["retired"]["reading_progress"] = await conn.fetchval(
        """SELECT count(*) FROM public.reading_progress WHERE document_id IN
           (SELECT id FROM staging.corpus_tombstones WHERE entity = 'document')""")
    out["redirected"]["reading_progress"] = await conn.fetchval(
        """SELECT count(*) FROM public.reading_progress r WHERE EXISTS (
             SELECT 1 FROM staging.corpus_redirects x WHERE x.old_document_id = r.document_id
               AND ((x.entity = 'chapter' AND x.old_anchor = r.chapter_key)
                 OR (x.entity = 'anchor' AND x.old_anchor = r.anchor)))""")
    return out


async def storage(conn) -> dict:
    staged = sum([await conn.fetchval(f"SELECT pg_total_relation_size('staging.{t}')")
                  for t in STAGED_TABLES])
    chunks = await conn.fetchval("SELECT pg_relation_size('staging.chunks')")
    database = await conn.fetchval("SELECT pg_database_size(current_database())")
    # The apply writes a new version of every staged row; the old ones stay until VACUUM.
    return {"staging_bytes": staged, "database_bytes": database,
            "projected_after_apply_bytes": database + chunks}


async def size_warnings(conn, collections: list[str]) -> list[str]:
    out = []
    for c in collections:
        live = {str(r["id"]) for r in await conn.fetch(
            """SELECT c.id FROM public.chunks c JOIN public.documents d ON d.id = c.document_id
               WHERE d.collection = $1 AND c.retired_at IS NULL""", c)}
        staged = {str(r["id"]) for r in await conn.fetch(
            """SELECT s.id FROM staging.chunks s JOIN staging.documents d ON d.id = s.document_id
               WHERE d.collection = $1""", c)}
        if live and len(staged) < len(live) * (1 - MAX_SHRINK):
            out.append(f"{c}: {len(staged)} staged passages against {len(live)} live "
                       f"({1 - len(staged) / len(live):.0%} fewer)")
        gone = live - staged
        if live and len(gone) > len(live) * MAX_SHRINK:
            out.append(f"{c}: {len(gone)} of {len(live)} live passage IDs leave "
                       f"({len(gone) / len(live):.0%})")
    return out


def facts_md(diff: list[dict]) -> list[str]:
    """2.3's "Document facts" section: per field and collection, how many documents'
    values staging changes against live (new documents counted apart), and every
    document whose author changes."""
    collections = sorted({d["collection"] for d in diff})
    counts = {(c, f): 0 for c in collections for f in FACT_COLUMNS}
    new = {c: 0 for c in collections}
    authors = []
    for d in diff:
        if d["new_document"]:
            new[d["collection"]] += 1
        for f in d["changed"]:
            counts[(d["collection"], f)] += 1
        if "author" in d["changed"]:
            authors.append((d["collection"], d["id"], d["changed"]["author"]))
    lines = ["", "## Document facts (2.3)", ""]
    if not diff:
        return lines + ["No document fact differs from live.", ""]
    fields = [f for f in FACT_COLUMNS if any(counts[(c, f)] for c in collections)]
    lines += ["Documents whose value differs from live, by field and collection.", "",
              "| Field | " + " | ".join(collections) + " |",
              "|---|" + "---|" * len(collections)]
    for f in fields:
        lines.append(f"| {f} | " + " | ".join(str(counts[(c, f)]) for c in collections) + " |")
    lines.append("| (new documents) | " + " | ".join(str(new[c]) for c in collections) + " |")
    lines += ["", f"Author changes: {len(authors)}.", ""]
    lines += [f"- {c} `{i}`: {a['live']!r} → {a['staged']!r}" for c, i, a in authors]
    return lines + [""]


def works_md(diff: list[dict]) -> list[str]:
    """3.2's "Works" section: per field and collection, how many works inside documents
    staging changes against live (new works counted apart), and every changed work with
    its changes."""
    lines = ["", "## Works inside documents (3.2)", ""]
    if not diff:
        return lines + ["No work differs from live.", ""]
    collections = sorted({d["collection"] for d in diff})
    counts = {(c, f): 0 for c in collections for f in WORK_COLUMNS}
    new = {c: 0 for c in collections}
    for d in diff:
        new[d["collection"]] += d["new_work"]
        for f in d["changed"]:
            counts[(d["collection"], f)] += not d["new_work"]
    lines += ["Works whose value differs from live, by field and collection.", "",
              "| Field | " + " | ".join(collections) + " |",
              "|---|" + "---|" * len(collections)]
    for f in WORK_COLUMNS:
        if any(counts[(c, f)] for c in collections):
            lines.append(f"| {f} | " + " | ".join(str(counts[(c, f)]) for c in collections)
                         + " |")
    lines += ["| (new works) | " + " | ".join(str(new[c]) for c in collections) + " |", ""]
    for d in diff:
        if d["new_work"]:
            what = "new: " + "; ".join(f"{f} {v['staged']!r}" for f, v in d["changed"].items())
        else:
            what = "; ".join(f"{f} {v['live']!r} → {v['staged']!r}"
                             for f, v in d["changed"].items())
        lines.append(f"- {d['collection']} `{d['document_id']}` {d['work_key']}: {what}")
    return lines + [""]


def held_texts_md(diff: list[dict]) -> list[str]:
    """4.3's "Held texts" section (`document.held_texts`): per document, every entry
    added, removed or changed against live."""
    lines = ["", "## Held texts (4.3)", ""]
    if not diff:
        return lines + ["No document's held texts differ from live.", ""]
    for d in diff:
        lines.append(f"- {d['collection']} `{d['id']}` {d['title']}: {len(d['added'])} added, "
                     f"{len(d['removed'])} removed, {len(d['changed'])} changed"
                     + (", reordered" if d["reordered"] else ""))
        lines += [f"  - + {h['key']} {h['label']} · {h['heading']} (after "
                  f"{h['after_anchor'] or 'the start'})" for h in d["added"]]
        lines += [f"  - − {k}" for k in d["removed"]]
        lines += [f"  - ~ {c['key']}: " + "; ".join(
                      f"{f} {c['live'].get(f)!r} → {c['staged'].get(f)!r}"
                      for f in sorted(c["staged"].keys() | c["live"].keys())
                      if c["live"].get(f) != c["staged"].get(f))
                  for c in d["changed"]]
    return lines + [""]


def publish_md(data: dict) -> str:
    ids = data["ids"]
    lines = ["", "## Publish checks (2.2w)", "",
             f"Release `{data['release']}`, Qdrant collection `{data['qdrant_collection']}`, "
             f"live alias target `{data['live_collection']}`.", "",
             f"- Live IDs kept {ids['kept']:,}, retired {ids['retired']:,}, redirected "
             f"{ids['redirected']:,}, unexplained {len(ids['unexplained']):,}; new IDs "
             f"{len(ids['new']):,}.",
             f"- Points: {len(data['points']['mismatches'])} mismatches; embedding input hash "
             f"failures {len(data['points']['hash_failures'])}.",
             "- Passages whose stored text differs from live (same ID): " + ", ".join(
                 f"{c} {n:,}" for c, n in data["text_changes"].items()) + ".",
             "- Points against live (same ID): " + ("; ".join(
                 f"{c} {d['payload_changed']:,} of {d['compared']:,} with another payload "
                 f"({', '.join(d['fields']) or 'no field'}), {d['embed_sha256_changed']:,} "
                 f"with another embedding input, {d['missing_live']:,} with no live point, "
                 f"{d['live_only']:,} live points not staged"
                 for c, d in data["live_points"].items()) or "no live collection") + ".",
             f"- Document facts changed on {len(data['facts_diff'])} documents; works "
             f"inside documents changed or new: {len(data['works_diff'])}; held texts "
             f"changed on {len(data['held_texts_diff'])} documents; other metadata on "
             f"{len(data['metadata_diff'])}"
             + (": " + "; ".join(f"{d['title']} ({', '.join(d['keys'])})"
                                 for d in data["metadata_diff"][:20])
                if data["metadata_diff"] else "") + ".",
             f"- Staging holds {data['storage']['staging_bytes'] / 2**20:,.1f} MiB; database "
             f"{data['storage']['database_bytes'] / 2**20:,.1f} MiB, projected after apply "
             f"{data['storage']['projected_after_apply_bytes'] / 2**20:,.1f} MiB.", "",
             "| Collection | Dedup collision rate, new | Live | Pairs | Flag |",
             "|---|---|---|---|---|"]
    for c, d in data["dedup"].items():
        lines.append(f"| {c} | {d['new']:.1%} | {d['live']:.1%} | {d['pairs']:,} | "
                     f"{'over 5%' if d['flagged'] else ''} |")
    lines += ["", "User rows pointing at retired or redirected IDs:", ""]
    for label, counts in data["user_impact"].items():
        lines.append(f"- {label}: " + ", ".join(f"{t} {n}" for t, n in counts.items()))
    if data["warnings"]:
        lines += ["", "Warnings (not failures):", ""] + [f"- {w}" for w in data["warnings"]]
    lines += facts_md(data["facts_diff"])
    lines += works_md(data["works_diff"])
    lines += held_texts_md(data["held_texts_diff"])
    lines += [f"Publish checks {'PASS' if data['pass'] else 'FAIL'}."]
    if data["failures"]:
        lines += [""] + [f"- {f}" for f in data["failures"][:50]]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- run

async def run(conn, qdrant, release: str, out: str, *, public: bool = True,
              live_alias: str = "chunks_live", record=None, registry=None,
              run_checks: bool | None = None) -> int:
    """Write the staged release report into `out`; return 0 when every check passes.
    `record(report_sha256)` stores the hashes (the CLI gates it with the lock).
    `registry` is a registry.WorkRegistry (default: the tracked files)."""
    from writers.qdrant import alias_target

    row = await conn.fetchrow("SELECT * FROM corpus_publishes WHERE id = $1", release)
    if row is None or row["staged_at"] is None:
        raise ReportRefused(f"REFUSING: publish '{release}' is not staged")
    if row["applied_at"] is not None or row["discarded_at"] is not None:
        raise ReportRefused(f"REFUSING: publish '{release}' is no longer staged")
    collections = list(row["collections"])
    os.makedirs(out, exist_ok=True)

    content_before = await staged_content_sha256(conn)
    snapshot_dir = await export_live(conn, os.path.join(out, "live"))
    staged = await staged_documents(conn, collections)
    # 0.1c judges sources (`publication.by_source`), the names its known defects use, and
    # reads the live rows of the staged collections under whatever key they are filed.
    by_source = publication.by_source([d for docs in staged.values() for d in docs], registry)
    sources = tuple(sorted(set(by_source) | set(_live_sources(snapshot_dir, collections))))
    code = release_report.run(snapshot_dir, sources, out, public,
                              registry=_remap_registry(registry),
                              build={s: by_source.get(s, []) for s in sources},
                              run_checks=run_checks, published=tuple(collections),
                              index_path=os.path.join(out, "live", "snapshots.json"))

    registry_rows = {r["passage_id"]: r for r in (registry or _current()).passages}
    live = await alias_target(qdrant, live_alias)
    data = {
        "release": release, "qdrant_collection": row["qdrant_collection"],
        "live_collection": live, "collections": collections,
        "ids": await explanation_checks(conn, collections, registry_rows),
        "points": await point_checks(conn, qdrant, row["qdrant_collection"], staged,
                                     row["embed_model"]),
        "dedup": await dedup_checks(conn, qdrant, row["qdrant_collection"], live, staged),
        "live_points": await live_point_changes(qdrant, row["qdrant_collection"], live, staged),
        "text_changes": await text_changes(conn, collections),
        "facts_diff": await facts_diff(conn, collections),
        "works_diff": await works_diff(conn, collections),
        "held_texts_diff": await held_texts_diff(conn, collections),
        "metadata_diff": await metadata_diff(conn, collections),
        "user_impact": await user_impact(conn),
        "storage": await storage(conn),
        "warnings": await size_warnings(conn, collections),
    }
    failures = [f"unexplained live ID {i}" for i in data["ids"]["unexplained"]]
    failures += data["points"]["mismatches"]
    failures += [f"index.embedding_input_hash: {i}" for i in data["points"]["hash_failures"]]
    if code:
        failures.append("the release report (0.1c) has unexpected failures; see above")
    data["failures"], data["pass"] = failures, not failures

    with open(os.path.join(out, "publish.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, default=str)
        f.write("\n")
    with open(os.path.join(out, "report.md"), "a", encoding="utf-8") as f:
        f.write(publish_md(data))

    if await staged_content_sha256(conn) != content_before:
        raise ReportRefused("REFUSING: staging changed while the report ran; rerun it")
    h = hashlib.sha256()
    for name in ("report.json", "publish.json"):
        with open(os.path.join(out, name), "rb") as f:
            h.update(f.read())
    report_sha256 = f"{h.hexdigest()}:{content_before}"
    if record is not None and data["pass"]:
        await record(report_sha256)
    print(f"publish checks: {'PASS' if data['pass'] else 'FAIL'} "
          f"({len(failures)} failures); kept {data['ids']['kept']:,}, retired "
          f"{data['ids']['retired']:,}, redirected {data['ids']['redirected']:,}, new "
          f"{len(data['ids']['new']):,}")
    return 0 if data["pass"] else 1


def _live_sources(snapshot_dir: str, collections: list[str]) -> list[str]:
    """The sources of the live documents a publish of `collections` covers, so a source
    whose documents the build drops is still judged."""
    from checks import health as health_cli

    return sorted(health_cli.load_snapshot(snapshot_dir, None, published=collections))


def _current():
    import registry

    return registry.current()


def _remap_registry(work_registry):
    """0.1c's view of a registry.WorkRegistry; None reads the tracked files."""
    if work_registry is None:
        return None
    from release import remap as R

    supersedes = {old: w["document_id"] for w in work_registry.works
                  for old in (w.get("supersedes") or [])}
    return R.Registry(redirects=[r for r in work_registry.redirects if not r.get("closed_by")],
                      removals=work_registry.removals, supersedes=supersedes,
                      kept_text={e["passage_id"]: e["reason"] for e in work_registry.kept_text},
                      enforce_redirects=True, per_piece=True)
