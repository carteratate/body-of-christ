"""BM25 index stage: encode chunk content + annotation, upsert named sparse vectors to Qdrant."""
from __future__ import annotations

import logging

from qdrant_client.models import PointVectors, SparseVector

from identity import passage_id
from writers.qdrant import QDRANT_COLLECTION
from stages.enrich_io import annotation_prose


def encode(model, text: str) -> tuple[list[int], list[float]]:
    result = list(model.embed([text]))[0]
    return list(result.indices), list(result.values)


def build_sparse_update(chunk_id, content_indices, content_values,
                        ann_indices, ann_values) -> dict:
    return {
        "id": chunk_id,
        "vector": {
            "sparse_content": SparseVector(indices=content_indices, values=content_values),
            "sparse_annotation": SparseVector(indices=ann_indices, values=ann_values),
        },
    }


async def index_collection(collection, conn, qdrant, content_model, annotation_model) -> int:
    rows = await conn.fetch(
        "SELECT c.id, c.content, c.annotation FROM chunks c "
        "JOIN documents d ON d.id = c.document_id WHERE d.collection = $1 ORDER BY c.id",
        collection)
    updates = []
    for r in rows:
        if not r["annotation"]:
            logging.warning("bm25-index: chunk %s has no annotation — run enrich first", r["id"])
            continue
        ci, cv = encode(content_model, r["content"])
        ai, av = encode(annotation_model, annotation_prose(r["annotation"]))
        upd = build_sparse_update(str(r["id"]), ci, cv, ai, av)
        updates.append(PointVectors(id=upd["id"], vector=upd["vector"]))
    if updates:
        # qdrant-client 1.18.0 (installed) exposes AsyncQdrantClient.update_vectors +
        # PointVectors directly — no fallback to upsert/PointStruct is needed. This
        # updates only the named sparse vectors on each existing point; the point's
        # dense vector and payload are untouched (Qdrant's update_vectors endpoint
        # merges into existing named vectors rather than replacing the whole point).
        await qdrant.update_vectors(collection_name=QDRANT_COLLECTION, points=updates, wait=True)
    return len(updates)
