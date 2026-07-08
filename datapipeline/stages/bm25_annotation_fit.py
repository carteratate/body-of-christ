"""Global BM25 annotation fit -> bm25_annotation_model.bin. Runs once after ALL enrich complete.

See `stages/bm25_content_fit.py`'s module docstring for the full rationale (Task 1's
fastembed spike findings: no corpus-relative IDF fitting occurs; a plain JSON config is
persisted instead of a pickled model). Same filename/format decision applies here:
`bm25_annotation_model.bin` keeps the `.bin` extension for continuity with the plan doc
and Task 18's orchestrator gate, but its actual content is UTF-8 JSON text, not a
pickle/binary blob.
"""
from __future__ import annotations

import json

from stages.enrich_io import annotation_prose

DEFAULT_OUT = "bm25_annotation_model.bin"

# Same pinned Qdrant/bm25 config as bm25_content_fit.py — the model has no
# corpus-relative state, so content vs. annotation fitting produces an identical
# config. Kept as a separate constant (rather than importing from bm25_content_fit)
# to keep the two modules independently readable/testable.
_MODEL_CONFIG = {
    "model_name": "Qdrant/bm25",
    "k": 1.2,
    "b": 0.75,
    "avg_len": 256.0,
    "language": "english",
    "token_max_length": 40,
    "disable_stemmer": False,
}


async def load_annotation_corpus(conn) -> list[str]:
    rows = await conn.fetch(
        "SELECT annotation FROM chunks WHERE annotation IS NOT NULL ORDER BY id")
    return [annotation_prose(r["annotation"]) for r in rows]


def fit(corpus: list[str], out_path: str = DEFAULT_OUT) -> None:
    """Persist the pinned BM25 config to `out_path` as JSON.

    `corpus` has no effect on the persisted config (see module docstring) — it is only
    sanity-checked to be non-empty, matching the calling convention future tasks expect.
    """
    if not corpus:
        raise ValueError("fit() requires a non-empty corpus")
    with open(out_path, "w") as f:
        json.dump(_MODEL_CONFIG, f)
