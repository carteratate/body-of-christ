"""Global BM25 content fit -> bm25_content_model.bin. Runs once after ALL readers complete.

FILENAME/FORMAT NOTE (Task 16, per Task 1's fastembed spike findings — see
docs/superpowers/plans/notes/2026-07-07-bm25-fastembed-findings.md):

`fastembed==0.8.0`'s `SparseTextEmbedding("Qdrant/bm25")` does NOT fit corpus-relative
IDF statistics — it uses fixed constructor parameters (k, b, avg_len, language,
token_max_length, disable_stemmer) that are identical regardless of what corpus is
passed to `.embed()`. There is nothing corpus-derived to persist. Additionally,
`pickle.dump(model)` fails outright (`TypeError: cannot pickle 'builtins.SnowballStemmer'
object`) independent of the corpus-fitting question.

So `fit()` here does NOT pickle a model. It persists a small JSON config (model name +
the pinned BM25 parameters) to `out_path`. The **filename keeps the `.bin` extension**
(`bm25_content_model.bin`) for continuity with the plan doc and Task 18's orchestrator,
which gates on this file's existence — the extension is cosmetic and doesn't affect
Python's ability to read it. The **file's actual content is UTF-8 JSON text**, not a
pickle/binary blob. Read it with `json.load()`, not `pickle.load()`. At query/index
time, reconstruct the encoder with:

    config = json.load(open(out_path))
    model = SparseTextEmbedding(model_name=config["model_name"],
                                 **{k: v for k, v in config.items() if k != "model_name"})

`corpus` is accepted and validated (non-empty) but otherwise unused, since there is no
actual corpus-relative fitting step — this keeps the function signature stable for
Task 18's call sites, which pass the loaded corpus per the original (pickle-based) plan.
"""
from __future__ import annotations

import json

DEFAULT_OUT = "bm25_content_model.bin"

# Pinned Qdrant/bm25 constructor parameters (fastembed==0.8.0 defaults, confirmed fixed
# and non-corpus-derived by the Task 1 spike). Persisted verbatim so query-time code
# reconstructs a byte-for-byte-equivalent encoder.
_MODEL_CONFIG = {
    "model_name": "Qdrant/bm25",
    "k": 1.2,
    "b": 0.75,
    "avg_len": 256.0,
    "language": "english",
    "token_max_length": 40,
    "disable_stemmer": False,
}


def load_content_corpus_sql() -> str:
    return "SELECT content FROM chunks ORDER BY id"


async def load_content_corpus(conn) -> list[str]:
    rows = await conn.fetch(load_content_corpus_sql())
    return [r["content"] for r in rows]


def fit(corpus: list[str], out_path: str = DEFAULT_OUT) -> None:
    """Persist the pinned BM25 config to `out_path` as JSON.

    `corpus` has no effect on the persisted config (see module docstring) — it is only
    sanity-checked to be non-empty, matching the calling convention future tasks expect
    (a real corpus is loaded and passed in by the orchestrator).
    """
    if not corpus:
        raise ValueError("fit() requires a non-empty corpus")
    with open(out_path, "w") as f:
        json.dump(_MODEL_CONFIG, f)
