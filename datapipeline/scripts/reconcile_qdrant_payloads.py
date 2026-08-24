"""Reconcile Qdrant chunk payloads against Postgres without re-embedding.

    cd datapipeline
    python3 scripts/reconcile_qdrant_payloads.py --collection summa           # dry run
    python3 scripts/reconcile_qdrant_payloads.py --collection all             # dry run, every collection
    python3 scripts/reconcile_qdrant_payloads.py --collection summa --apply   # write

Uses `set_payload`, which rewrites payload only — vectors, point ids and the
collection schema are untouched, so nothing is re-embedded and no chunk id changes.
That is the whole reason this exists rather than a re-ingest: `run_collection.py`
would call `reader_writer.clear_collection`, and `retrievals`, `bookmarks`,
`retrieval_labels` and `guest_trial_retrievals` all cascade on `chunks.id`.

DRY RUN IS THE DEFAULT. `--apply` is required to write.

⚠️  `--fields content` IS NOT A SAFE PAYLOAD SYNC — two separate hazards
1. summa (~26,599 points). Syncing content REMOVES the inline "Objection 1 " prefix
   Qdrant still carries, because Postgres moved that marker into `unit_label`. That
   stale prefix is currently the ONLY thing telling the reranker a passage is an
   objection Aquinas refutes rather than his teaching. Measured over the 84 persisted
   searches that returned a Summa passage (202 Summa results), bare objections are
   39.3% of the summa corpus but only 4 of those 202 results — 2.0% — and the inline
   marker is the most likely reason. Fix by plumbing `unit_label` through
   `ChunkCandidate`, `retrieve_fts` and the reranker cards first.
2. apostolic-exhortations (78) and summa (8) — 86 points where Qdrant holds text
   UNRELATED to its Postgres row: a footnote ("Cf. Phil. 4:4-5; Ps. 145:18.") or an
   off-by-one passage. The VECTOR was embedded from that other text, and
   `set_payload` cannot change a vector — so a content sync makes those passages
   retrievable by text they no longer display. Only a re-embed fixes that.
   The other 30 drifts (20 trailing-boilerplate strips across councils, encyclicals,
   papal-documents and apostolic-exhortations; 10 summa edits) are the same passage
   and ARE safely fixed by this sync.

`--allow-content-sync` is required to apply either.

⚠️  ORDERING: run `scripts/reembed_drifted_vectors.py` BEFORE this. That tool
classifies on the very field this sync overwrites, so syncing first destroys the
evidence for 54 broken points — silently, since the re-embed would still report a
healthy-looking selection afterwards.

`--fields structural` (the default: `unit_label` + `chapter_key`) is additive TODAY,
because no point currently carries either field — verified by a full payload census
of all 53,747 points, which hold exactly: collection, document_id, document_title,
author, content, reference, anchor, chapter_label. After the first apply it is no
longer purely additive: a later re-chunk that changes `make_anchor` would make this
overwrite chapter_key rather than add it. Re-read the dry run before re-applying;
`summary()` reports `to_write` for exactly this reason.

Do NOT expect it to change search results. `fetch_positions` already backfills
`chapter_key` from Postgres for every Qdrant candidate (it fires on `position is
None`, which every Qdrant candidate has), and all 29,297 rows in the three
chapter-keyed collections have a non-NULL `chapter_key` — so dedup is already using
the chapter grain on the healthy path. What this write buys is that the grain also
survives the DEGRADED path, where the backfill is skipped and dedup would otherwise
fall back to the coarser per-title grain. `unit_label` buys nothing at all until the
step-3 plumbing lands; it is written now so that step is a pure code change.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reconcile import (  # noqa: E402
    RECONCILED_FIELDS, STRUCTURAL_FIELDS, ReconcileReport, build_report,
)

# `config` and `writers.qdrant` are imported lazily inside the functions that need
# them. Both read required environment variables at import time and raise without a
# populated .env, which would make importing this module for `resolve_args` — and so
# testing the safety gates — impossible in an environment without production
# credentials. The gates are exactly what must stay covered.

FIELD_SETS: dict[str, tuple[str, ...]] = {
    "structural": STRUCTURAL_FIELDS,
    "content": ("content",),
    "all": RECONCILED_FIELDS,
}

# Derived from RECONCILED_FIELDS rather than written out, so a field added there
# cannot silently go unselected — `row.get` would return None for it and the diff
# would report "nothing to do" for a genuinely drifting field.
_SQL = f"""
    SELECT c.id::text AS id, {', '.join('c.' + f for f in RECONCILED_FIELDS)}
    FROM chunks c JOIN documents d ON d.id = c.document_id
    WHERE d.collection = $1
"""


async def _fetch_payloads(client, collection: str) -> dict[str, dict]:
    """Every Qdrant payload for one collection, keyed by point id."""
    from writers.qdrant import QDRANT_COLLECTION, collection_filter

    payloads: dict[str, dict] = {}
    offset = None
    while True:
        points, offset = await client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=collection_filter(collection),
            limit=1000,
            offset=offset,
            with_payload=list(RECONCILED_FIELDS),
            with_vectors=False,
        )
        for point in points:
            payloads[str(point.id)] = point.payload or {}
        if offset is None:
            return payloads


async def _apply(client, report: ReconcileReport, batch_size: int) -> int:
    """Write each diff's changed fields, `batch_size` points per HTTP round trip.

    Uses `batch_update_points` with one SetPayloadOperation per point rather than
    `set_payload(points=[...])` with a shared payload: every field being written here
    is per-point unique (each chunk has its own content and chapter_key), so grouping
    points by identical payload would degenerate to one request per point — ~26,750
    round trips for the Summa alone.

    SetPayload MERGES, so keys not listed (author, reference, document_title,
    anchor, chapter_label, collection, document_id) are preserved untouched.
    """
    from qdrant_client.models import SetPayload, SetPayloadOperation

    from writers.qdrant import QDRANT_COLLECTION

    written = 0
    for start in range(0, len(report.diffs), batch_size):
        window = report.diffs[start:start + batch_size]
        operations = [
            SetPayloadOperation(
                set_payload=SetPayload(payload=diff.changes, points=[diff.point_id])
            )
            for diff in window
        ]
        # Retry transient failures with backoff, matching writers/qdrant.upsert_points
        # — a summa run is ~54 sequential calls and one blip would otherwise abort it.
        # Qdrant rejects a malformed batch atomically (no partial application), and a
        # re-run recomputes the diff from scratch, so retrying is safe and the whole
        # script is resumable after any failure.
        for attempt in range(4):
            try:
                await client.batch_update_points(
                    collection_name=QDRANT_COLLECTION,
                    update_operations=operations,
                    wait=True,
                )
                break
            except Exception:
                if attempt == 3:
                    raise
                await asyncio.sleep(2 ** attempt)
        written += len(window)
        print(f"      … {written}/{len(report.diffs)}", flush=True)
    return written


async def reconcile_collection(client, conn, collection: str,
                               fields: tuple[str, ...]) -> ReconcileReport:
    rows = [dict(r) for r in await conn.fetch(_SQL, collection)]
    payloads = await _fetch_payloads(client, collection)
    return build_report(collection, payloads, rows, fields)


async def main(collections: list[str], fields: tuple[str, ...],
               apply: bool, batch_size: int) -> int:
    """Returns a process exit code: 0 unless a WRITE failed.

    Orphaned/unvectorised/blank rows are reported but do not fail the run — they are
    pre-existing corpus conditions (280 unvectorised rows live today), so failing on
    them would make `--collection all` exit non-zero forever and make a genuine write
    failure indistinguishable from routine drift in CI or a `&&` chain.
    """
    from config import settings
    from writers.qdrant import get_client

    # Nested try/finally rather than one block acquiring both: whichever resource is
    # opened second can raise, and a single block would then never close the first.
    # Nesting also guarantees the client is closed even if conn.close() itself raises.
    conn = await asyncpg.connect(settings.DATABASE_URL, statement_cache_size=0)
    exit_code = 0
    try:
        client = get_client()
        try:
            for collection in collections:
                report = await reconcile_collection(client, conn, collection, fields)
                print(report.summary())
                if report.orphaned:
                    print(f"    ⚠️  {len(report.orphaned)} orphaned point(s) in Qdrant with no "
                          f"chunks row — NOT written. They need a targeted delete BY POINT ID; "
                          f"do NOT use --reset-search-index, which deletes EVERY point in the "
                          f"collection. First ids: {report.orphaned[:5]}")
                if report.unvectorised:
                    print(f"    ⚠️  {len(report.unvectorised)} row(s) with no Qdrant point — "
                          f"NOT written; these are reachable only by FTS until re-embedded")
                for name, ids in sorted(report.blank_in_source.items()):
                    print(f"    ⚠️  {len(ids)} row(s) hold a blank {name!r} in Postgres while "
                          f"Qdrant holds text — never written, whatever --fields is set to, "
                          f"since writing a blank would produce empty results. This is an "
                          f"ingest defect. First ids: {ids[:5]}")
                if not report.diffs:
                    print("    nothing to do")
                    continue
                if not apply:
                    print(f"    DRY RUN — {len(report.diffs)} point(s) would be updated "
                          f"(fields: {', '.join(fields)}). Re-run with --apply to write.")
                    continue
                try:
                    written = await _apply(client, report, batch_size)
                except Exception as exc:
                    print(f"    ✗ WRITE FAILED after retries: {exc}")
                    print(f"      Re-run to resume — the diff is recomputed from scratch, "
                          f"so already-written points are skipped.")
                    exit_code = 1
                    continue
                print(f"    wrote {written} point(s)")
        finally:
            await client.close()
    finally:
        await conn.close()
    return exit_code


class ArgError(ValueError):
    """A rejected argument combination. Raised by `resolve_args` so the validation
    is testable without argparse's SystemExit, then converted by the CLI."""


CONTENT_HAZARD = (
    "includes `content`, which is NOT a safe payload sync. Classifying all 26,697 "
    "live content drifts gives two distinct hazards (2026-08-19):\n"
    "  1. summa, 26,581 points — these would lose the inline 'Objection N ' prefix, "
    "currently the ONLY signal telling the reranker a passage is an objection "
    "Aquinas refutes. The passage is otherwise the same, so the vector stays valid; "
    "the fix is to plumb unit_label through ChunkCandidate, retrieve_fts and the "
    "rerank cards FIRST.\n"
    "  2. 86 points — apostolic-exhortations (78) and summa (8) — where Qdrant holds "
    "text UNRELATED to the Postgres row (a footnote, 'Cf. Phil. 4:4-5; Ps. 145:18.', "
    "or an off-by-one passage). Their VECTORS were embedded from that other text and "
    "set_payload cannot change a vector, so syncing content makes those passages "
    "retrievable by text they no longer display. Only a re-embed fixes them.\n"
    "The remaining 30 drifts (20 trailing-boilerplate strips across councils, "
    "encyclicals, papal-documents and apostolic-exhortations, plus 10 summa edits) "
    "are the same passage and ARE safely fixed by this sync.\n"
    "  3. ORDERING — run `scripts/reembed_drifted_vectors.py` FIRST. This sync "
    "overwrites Qdrant `content`, which is the signal that tool classifies on. "
    "Simulated live, syncing first makes 54 points permanently undetectable (25 "
    "content_unrelated, 17 of them Gaudete in Domino; all 29 minor_text) — and the "
    "re-embed would still report selected=296 rather than nothing-to-do, so the loss "
    "is silent.\n"
    "Pass --allow-content-sync only once (1), (2) and (3) are addressed."
)


def resolve_args(fields_name: str, collection: str, apply: bool,
                 allow_content_sync: bool, batch_size: int,
                 valid_collections: set[str]) -> tuple[list[str], tuple[str, ...]]:
    """Validate an argument combination; return (collection names, fields).

    Extracted from `__main__` so the safety gates are reachable from tests. They
    previously lived inline under `if __name__ == "__main__":`, where no test could
    execute them — the same gap that let the D3 invariant go unverified.
    """
    # Collection is validated FIRST: a typo is the likeliest mistake, and reporting a
    # batch-size or content-gate error instead would send the operator chasing the
    # wrong thing while the real problem (nothing would be reconciled) goes unmentioned.
    if collection == "all":
        names = sorted(valid_collections)
    elif collection in valid_collections:
        names = [collection]
    else:
        # Without this a typo reports "nothing to do" and exits 0, so an operator
        # believes a collection was reconciled when nothing was read or written.
        raise ArgError(f"unknown collection {collection!r}. "
                       f"Valid: {', '.join(sorted(valid_collections))}, or 'all'")

    if batch_size < 1:
        raise ArgError(f"--batch-size must be >= 1 (got {batch_size}); a non-positive "
                       f"value silently writes nothing and reports success")

    # argparse `choices` covers the CLI, but this function is public and tested, so a
    # bad name must raise ArgError like every other rejection rather than KeyError.
    if fields_name not in FIELD_SETS:
        raise ArgError(f"unknown field set {fields_name!r}. "
                       f"Valid: {', '.join(sorted(FIELD_SETS))}")
    fields = FIELD_SETS[fields_name]

    if "content" in fields and apply and not allow_content_sync:
        raise ArgError(f"--fields {fields_name} {CONTENT_HAZARD}")

    return names, fields


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collection", required=True,
                    help="collection name, or 'all'")
    ap.add_argument("--fields", choices=["structural", "content", "all"],
                    default="structural",
                    help="structural = unit_label + chapter_key — additive today (no point carries either field). Does NOT change search results on the healthy path: fetch_positions already backfills chapter_key for every Qdrant candidate. Its benefit is insurance for the DEGRADED path, where that backfill is skipped and dedup falls back to the coarser per-title grain; "
                         "content = content only (see the ordering constraint above); "
                         "all = both")
    ap.add_argument("--apply", action="store_true",
                    help="actually write; omit for a dry run")
    ap.add_argument("--allow-content-sync", action="store_true",
                    help="REQUIRED to apply a field set containing `content`. TWO hazards: it strips "
                         "the inline dialectical marker from 26,581 summa payloads "
                         "(the reranker's only objection signal), and it desyncs 86 "
                         "points whose vector was embedded from unrelated text and "
                         "which need a re-embed instead. See the module docstring.")
    ap.add_argument("--batch-size", type=int, default=500)
    args = ap.parse_args()

    # SOURCE_ADAPTERS is the datapipeline's canonical collection registry, mirroring
    # services/api's VALID_COLLECTIONS. Import it here so importing this module for
    # its helpers does not pull in publication dependencies.
    from publication import SOURCE_ADAPTERS  # noqa: E402

    try:
        names, fields = resolve_args(
            args.fields, args.collection, args.apply,
            args.allow_content_sync, args.batch_size, set(SOURCE_ADAPTERS),
        )
    except ArgError as exc:
        ap.error(str(exc))

    if "content" in fields:
        print("⚠️  field set includes `content` — see --help before applying.\n")

    raise SystemExit(asyncio.run(main(names, fields, args.apply, args.batch_size)))
