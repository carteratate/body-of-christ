"""Decide what a missing-vector backfill must write, and how to embed it.

280 passages exist in Postgres with no Qdrant point (encyclicals 169,
apostolic-exhortations 102, papal-documents 9, measured 2026-08-20). They are
reachable only by full-text search — invisible to vector search and to HyDE, with no
error anywhere. The cause is structural: `reader_writer` writes Postgres and
`search_writer` writes Qdrant, and the two targets were run out of step.

THE HARD PART IS NOT FINDING THEM, IT IS EMBEDDING THEM THE SAME WAY.

A vector is only comparable to its neighbours if it was produced from the same input
shape. `search_writer.build_embedding_input` does not embed a passage's text alone: it
prepends a prefix and splices in the tail of the previous passage and the head of the
next, when they share a chapter. Get any of that wrong and the backfilled point is a
subtly different kind of object sitting in the same index — retrievable, plausible, and
systematically mis-scored against everything around it.

Reproducing it means matching the writer that produced the LIVE data, which is NOT the
one in the tree today (verified against git history 2026-08-20):

  prefix      f"[{chapter_label}] "   — the current writer uses an author/title prefix
                                        instead (changed in 15af127). Live vectors were
                                        built with the chapter-label form.
  dimensions  1536, passed explicitly  — the current writer omits `dimensions=` and so
                                        emits text-embedding-3-large's native 3072.
                                        The live collection is 1536 and unnamed.
  overlap     settings.overlap_for()   — unchanged since the live write, so the current
                                        config is safe to read.
  vector      unnamed                  — the current writer emits a NAMED "dense" vector,
                                        which this collection would reject.

`build_embedding_input` itself is byte-identical between the two versions, so it is
imported rather than reimplemented.

FIDELITY IS VERIFIED, NOT ASSUMED. Reconstructing the input for chunks that ALREADY
have vectors and re-embedding reproduces the stored vector at cosine >= 0.9999 — except
where `chapter_label` has itself drifted between the stores, which is the prefix. 296
chunks (0.55%) are in that state, all in the three collections that also have the
missing vectors: encyclicals 223, apostolic-exhortations 69, papal-documents 4. One
incomplete re-ingest explains every symptom. That drift is PRE-EXISTING and does not
affect this tool's output — the 280 chunks being backfilled have no stored vector to be
inconsistent with, and Postgres is the source of truth for the prefix either way. It is
recorded here because the payload reconcile does NOT sync `chapter_label`, and syncing
it would not fix the affected vectors anyway (they were embedded with the old label);
only a re-embed would.
"""
from __future__ import annotations

from dataclasses import dataclass

from model import Passage

# The live collection's dimensionality. Deliberately a module constant rather than
# `settings.EMBEDDING_DIMS`: that value is now 3072 for the V5 pipeline, and reading it
# here would silently emit vectors the collection cannot accept.
LIVE_EMBEDDING_DIMS = 1536

# Pinned for the same reason as the dimensionality, and it is the same risk: the live
# vectors were produced by this model, and `settings.EMBEDDING_MODEL` is a moving target
# the V5 pipeline already drifted once. A future model swap would otherwise embed the
# backfill into a different vector space at the right dimensionality — which Qdrant
# accepts silently, and which no length or shape check can detect.
LIVE_EMBEDDING_MODEL = "text-embedding-3-large"

# Payload written for a backfilled point. The first eight are what `build_point`
# emitted for every existing point; `chapter_key` and `unit_label` were added to all
# 53,747 points by the payload reconcile, so a new point must carry them too or it
# arrives already inconsistent with its neighbours.
PAYLOAD_FIELDS: tuple[str, ...] = (
    "collection", "document_id", "document_title", "author",
    "content", "reference", "anchor", "chapter_label",
    "chapter_key", "unit_label",
)


@dataclass(frozen=True)
class PassageRow:
    """One `chunks` row, with the document context needed to embed it."""

    chunk_id: str
    document_id: str
    document_title: str
    author: str | None
    collection: str
    content: str
    reference: str | None
    anchor: str | None
    chapter_key: str | None
    chapter_label: str | None
    unit_label: str | None
    position: int


def legacy_prefix(row: PassageRow) -> str:
    """The prefix the live vectors were built with.

    `f"[{chapter_label}] "` — see the module docstring. A None chapter_label renders as
    the string "None" in the original too (it was an f-string over the attribute), so
    this reproduces that rather than "fixing" it: consistency with the existing vectors
    matters more than tidiness in a repair tool.
    """
    return f"[{row.chapter_label}] "


def missing_chunk_ids(postgres_ids: set[str], qdrant_ids: set[str]) -> list[str]:
    """Chunk ids present in Postgres and absent from Qdrant, sorted for determinism.

    Only this direction is actionable. The reverse — a Qdrant point with no `chunks`
    row — is an orphan needing a targeted delete, which this tool deliberately does not
    do (see `reconcile.build_report`).
    """
    return sorted(postgres_ids - qdrant_ids)


def to_passages(rows: list[PassageRow]) -> list[Passage]:
    """Rebuild the document's `Passage` list so `build_embedding_input` can be REUSED.

    Deliberately not a reimplementation of the neighbour-splicing rule. That rule has
    three parts — only splice across a shared chapter, take the previous passage's TAIL
    and the next passage's HEAD, strip verse markers — and reimplementing any of them
    slightly differently would produce vectors that look fine and sit wrong in the
    index. Reconstructing the input type and calling the original function makes the
    fidelity structural instead of asserted.

    Requires `rows` to be the document's FULL passage list in position order: a missing
    neighbour silently changes the embedding input of the passage beside it.
    """
    return [
        Passage(
            content=row.content,
            reference=row.reference or "",
            anchor=row.anchor or "",
            chapter_key=row.chapter_key or "",
            chapter_label=row.chapter_label or "",
            position=row.position,
            unit_label=row.unit_label,
        )
        for row in rows
    ]


def build_payload(row: PassageRow) -> dict:
    """Payload for a backfilled point, matching what its neighbours already carry.

    `content` is the CLEAN passage text, never the neighbour-augmented string used for
    embedding — the same invariant `build_point` documents. The augmentation exists to
    give the vector context; storing it would change what search displays.
    """
    return {
        "collection": row.collection,
        "document_id": row.document_id,
        "document_title": row.document_title,
        "author": row.author,
        "content": row.content,
        "reference": row.reference,
        "anchor": row.anchor,
        "chapter_label": row.chapter_label,
        "chapter_key": row.chapter_key,
        "unit_label": row.unit_label,
    }
