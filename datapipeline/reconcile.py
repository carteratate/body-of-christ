"""Diff Qdrant chunk payloads against Postgres, the source of truth.

The two stores can drift because they are written by SEPARATE pipeline targets:
`reader_writer` writes Postgres (`--target reader`) and `search_writer` writes
Qdrant (`--target search`). Running one without the other, or changing an ingest
adapter between the two runs, leaves the vector store serving text that no longer
matches the row the reader and search-history restore from.

That is not hypothetical — it is the live state as of 2026-08-19:

  summa                  26,750 pts, 26,599 content drift (99.4%; a further 21 rows
                         hold content='' in Postgres and are never written).
                         `ingest/summa.py` used to
                         emit "Objection 1 It would seem..." with the dialectical
                         marker inline; commit 16f6d27 moved the marker into
                         `unit_label` and stripped it from `content`. Postgres was
                         rewritten 38 minutes later; Qdrant never was.
  apostolic-exhortations  2,922 pts vs 3,024 rows — 102 absent, plus 79 drifts of
                         which 78 are stale chunks from an older chunking (a footnote
                         fragment "2 Cor. 11:28." where Postgres now holds prose).
                         Those 78 were EMBEDDED from the footnote, so only a re-embed
                         fixes them — see the content hazard in the CLI's docstring.
  councils                2,173 pts, 15 drifts, all trailing-boilerplate strips
                         (" Want to be automatically notified of new documents? …").
                         Same passage, valid vector — safely fixed by a payload sync.
  encyclicals             5,941 pts vs 6,110 rows — 169 absent, 2 trailer strips.
  papal-documents           476 pts vs   485 rows —   9 absent, 2 trailer strips.

Classifying all 26,697 content drifts (2026-08-19): 26,581 summa prefix strips,
20 trailer strips, 10 summa edits — all the same passage, safely synced — and 86
where Qdrant holds UNRELATED text (apostolic-exhortations 78, summa 8) whose vectors
need re-embedding rather than a payload write.

`unit_label` and `chapter_key` are absent from ALL 53,747 points because
`writers/search_writer.build_point` never wrote them.

This module is pure: it computes what WOULD change. `scripts/reconcile_qdrant_payloads.py`
does the I/O and the optional write. Splitting them is what makes the decision
logic testable without a live Qdrant.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Payload fields this module reconciles. `content` is what search reranks and
# displays. `chapter_key` is read by retrieve_vector but normally supplied by
# fetch_positions' Postgres backfill, so writing it here is insurance for the
# degraded path rather than a fix for the healthy one. `unit_label` is read by
# nothing in services/api today — it is inert until the step-3 plumbing through
# ChunkCandidate, retrieve_fts and the rerank cards lands. build_point emitted
# neither.
#
# `position` is deliberately NOT here. `fetch_positions` treats `position is None`
# as its signal to query Postgres, and that query is also what detects orphaned
# Qdrant points (a vector whose chunks row is gone) and drops them before they can
# break the reader or fail a retrievals FK. Populating position would make that
# query stop running and silently disable orphan detection.
RECONCILED_FIELDS: tuple[str, ...] = ("content", "unit_label", "chapter_key")

# The subset safe to write at any time: fields no point currently carries, so the
# write is strictly additive and cannot overwrite a value. Lives HERE, not in the
# CLI, for two reasons: this module imports nothing (so the safety invariant stays
# testable without database or Qdrant credentials), and keeping it beside
# RECONCILED_FIELDS is what lets the assertion below catch a field added to one
# list and not the other.
STRUCTURAL_FIELDS: tuple[str, ...] = ("unit_label", "chapter_key")

# A field added to RECONCILED_FIELDS but not classified is a silent no-op: `_SQL`
# would not select it, `row.get` would return None, and `_is_blank` would skip it —
# reporting "nothing to do" for a genuinely drifting field.
assert set(STRUCTURAL_FIELDS) | {"content"} == set(RECONCILED_FIELDS), (
    "every RECONCILED_FIELD must be classified as structural or content"
)


def _is_blank(value: object) -> bool:
    """True for NULL and for empty/whitespace-only strings.

    Both mean "no usable value in the source row", and neither should ever
    overwrite a populated Qdrant payload — but they mean different things about the
    corpus, so `build_report` records the empty-string case separately.
    """
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


@dataclass(frozen=True)
class PointDiff:
    """One point needing a payload write."""

    point_id: str
    changes: dict[str, object]      # field -> new value
    reasons: tuple[str, ...]        # 'content_drift' | 'field_missing'


@dataclass
class ReconcileReport:
    collection: str
    qdrant_points: int = 0
    postgres_rows: int = 0
    in_sync: int = 0
    content_drift: int = 0
    fields_missing: int = 0
    orphaned: list[str] = field(default_factory=list)     # in Qdrant, absent from PG
    unvectorised: list[str] = field(default_factory=list)  # in PG, absent from Qdrant
    # Postgres rows whose source value is empty/whitespace-only while Qdrant holds
    # usable text. Never written (see _is_blank); surfaced because it is a corpus
    # defect worth fixing at ingest, not a reconcile action.
    blank_in_source: dict[str, list[str]] = field(default_factory=dict)
    diffs: list[PointDiff] = field(default_factory=list)

    def summary(self) -> str:
        # `to_write` is len(diffs), NOT content_drift + fields_missing: one point can
        # need both, so those two overlap and must not be added together.
        blanks = sum(len(v) for v in self.blank_in_source.values())
        return (
            f"{self.collection:24} qdrant={self.qdrant_points:>6} pg={self.postgres_rows:>6} "
            f"in_sync={self.in_sync:>6} to_write={len(self.diffs):>6} "
            f"(content_drift={self.content_drift} fields_missing={self.fields_missing}) "
            f"orphaned={len(self.orphaned):>4} unvectorised={len(self.unvectorised):>4} "
            f"blank_in_source={blanks:>4}"
        )


def diff_point(
    payload: dict,
    row: dict,
    fields: tuple[str, ...] = RECONCILED_FIELDS,
) -> PointDiff | None:
    """What must change on one Qdrant payload to match its Postgres row.

    Returns None when the point is already correct, so an already-reconciled corpus
    produces zero writes and the script is safe to re-run.

    A Postgres NULL never overwrites a present payload value: the intent is to
    propagate the source of truth, and a NULL is far more likely to mean "this
    collection does not populate that column" than "delete what Qdrant has".
    """
    changes: dict[str, object] = {}
    reasons: list[str] = []

    for name in fields:
        new = row.get(name)
        if _is_blank(new):
            # Blank covers NULL *and* empty/whitespace-only. NULL usually means "this
            # collection does not populate that column" (church-fathers and medieval
            # have no unit_label at all). Empty string means a real data defect: 21
            # summa chunks hold content='' from `_split_article`'s `else ""` branch,
            # and their Qdrant payloads still hold usable text ("Objection 4").
            # Writing '' over that would produce blank result cards, because
            # retrieve_vector's completeness guard tests `is None` and an empty
            # string passes it. Never write a blank over a populated value; report
            # it instead (see ReconcileReport.blank_in_source).
            continue
        old = payload.get(name)
        if old == new:
            continue
        changes[name] = new
        reasons.append("content_drift" if name == "content" else "field_missing")

    if not changes:
        return None
    return PointDiff(
        point_id=str(row["id"]),
        changes=changes,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def build_report(
    collection: str,
    payloads: dict[str, dict],
    rows: list[dict],
    fields: tuple[str, ...] = RECONCILED_FIELDS,
) -> ReconcileReport:
    """Compare every Postgres row for a collection against its Qdrant payload.

    `payloads` maps point id -> payload for the points Qdrant holds for this
    collection; `rows` is the Postgres side. Ids present on only one side are
    reported, never written: an orphaned Qdrant point needs a targeted delete BY
    POINT ID, an unvectorised row needs an embed run, and silently doing either from
    a payload-reconcile tool would hide a broken ingest rather than surface it.

    ⚠️  Do NOT reach for `scripts/delete_collection_qdrant.py` to clear orphans — it
    deletes EVERY point in the collection (a filter delete on `collection`), which
    for summa means all 26,750 vectors and a full re-embed. The repo has no per-id
    delete path; orphan ids are reported here so they can be removed deliberately.
    """
    report = ReconcileReport(
        collection=collection,
        qdrant_points=len(payloads),
        postgres_rows=len(rows),
    )
    seen: set[str] = set()

    for row in rows:
        point_id = str(row["id"])
        seen.add(point_id)
        payload = payloads.get(point_id)
        if payload is None:
            report.unvectorised.append(point_id)
            continue

        # Scanned over EVERY reconciled field, not just the selected ones: a blank
        # source shadowing real payload text is an ingest defect worth surfacing
        # whichever field set this run happens to be writing. Reporting it only under
        # `--fields content` would hide the 21 blank summa rows from the default run.
        for name in RECONCILED_FIELDS:
            if _is_blank(row.get(name)) and not _is_blank(payload.get(name)):
                report.blank_in_source.setdefault(name, []).append(point_id)

        diff = diff_point(payload, row, fields)
        if diff is None:
            report.in_sync += 1
            continue
        if "content_drift" in diff.reasons:
            report.content_drift += 1
        if "field_missing" in diff.reasons:
            report.fields_missing += 1
        report.diffs.append(diff)

    report.orphaned = sorted(set(payloads) - seen)
    return report
