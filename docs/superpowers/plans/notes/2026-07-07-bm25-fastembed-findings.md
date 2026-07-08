# BM25 fastembed verification spike — findings

**Date:** 2026-07-07
**Package tested:** `fastembed==0.8.0`, model `Qdrant/bm25`
**Script:** `datapipeline/scripts/spike_bm25.py` (throwaway, deleted after this note was written)

## Decision: Outcome (B) — stateless IDF, persist config not the model object

`fastembed`'s `SparseTextEmbedding("Qdrant/bm25")` does **not** fit corpus-relative IDF
statistics. It uses a fixed, hand-set BM25 parameterization (`k=1.2`, `b=0.75`,
`avg_len=256.0`, `language='english'`) baked in as defaults at construction time,
regardless of what text is later passed to `.embed()`. There is no "fit" step and no
corpus-derived state to persist. Additionally, the naive `pickle.dump(model)` approach
from the spec's draft script **fails outright** — the model holds a native/C
`SnowballStemmer` object that is not picklable.

Both findings independently point to the same fix: Tasks 15–17 must persist the BM25
**config** (a handful of plain values), not a pickled model instance.

## Evidence

### 1. `pickle.dump(model)` raises `TypeError`

```
pickle round-trip succeeded: False
pickle error: TypeError("cannot pickle 'builtins.SnowballStemmer' object")
```

The inner `fastembed.sparse.bm25.Bm25` object (accessible as `model.model`) stores a
`stemmer` attribute that is a native `SnowballStemmer` instance (from
`py-rust-stemmers`), which cannot be pickled. This isn't a corpus-fit issue — it's a
non-picklable native object embedded in every instance, present even before any
`.embed()` call. **The spec's `pickle.dump(model)` approach cannot work as written,
independent of the IDF question.**

### 2. No corpus-relative IDF fitting occurs

```
has attributes: []          # dir(model) has nothing matching "idf" or "avg"
unaffected by prior embed(corpus) call - indices equal: True
unaffected by prior embed(corpus) call - values equal: True
fresh instance (corpus-exposed) vs fresh instance (naive) - indices equal: True
fresh instance (corpus-exposed) vs fresh instance (naive) - values equal: True
```

- Embedding the same query text before and after calling `list(model.embed(corpus))`
  (a 150-doc corpus, per the spike script) produces **identical** sparse vectors —
  proving `.embed()` has no side effect that changes future output.
- Two independently constructed `SparseTextEmbedding("Qdrant/bm25")` instances — one
  that was first exposed to the 150-doc corpus via `.embed(corpus)`, one that was
  never shown any corpus — produce **identical** sparse vectors for the same query.
  This rules out any hidden/lazy corpus-fit state; the "IDF" component of this BM25
  implementation is not document-frequency-based at all in the classic corpus sense —
  it's computed from fixed constants (`k`, `b`, `avg_len`) applied per-document via a
  BM25-style term-frequency saturation formula, not from term document-frequency
  counts collected across a corpus.

### 3. Inner model dict — the full, fixed parameter set

```python
{'model_name': 'Qdrant/bm25', 'cache_dir': '.../fastembed_cache', 'threads': None,
 '_local_files_only': False, 'language': 'english', 'k': 1.2, 'b': 0.75,
 'avg_len': 256.0, '_specific_model_path': None, '_model_dir': PosixPath(...),
 'token_max_length': 40, 'punctuation': {...}, 'disable_stemmer': False,
 'stopwords': {...}, 'stemmer': <builtins.SnowballStemmer object at 0x...>,
 'tokenizer': <class 'fastembed.sparse.utils.tokenizer.SimpleTokenizer'>}
```

`Bm25.__init__` signature confirms these are all constructor defaults, settable
per-instance, nothing corpus-derived:

```python
Bm25.__init__(self, model_name: str, cache_dir: str | None = None, k: float = 1.2,
              b: float = 0.75, avg_len: float = 256.0, language: str = 'english',
              token_max_length: int = 40, disable_stemmer: bool = False,
              specific_model_path: str | None = None, **kwargs)
```

## Exact parameters to pin (Tasks 15–17)

Persist this config (JSON is sufficient — no pickle needed) alongside index-time
artifacts, and re-instantiate identically at query time:

```json
{
  "model_name": "Qdrant/bm25",
  "k": 1.2,
  "b": 0.75,
  "avg_len": 256.0,
  "language": "english",
  "token_max_length": 40,
  "disable_stemmer": false
}
```

At query time, do:

```python
from fastembed import SparseTextEmbedding
model = SparseTextEmbedding(model_name=config["model_name"], **{
    k: v for k, v in config.items() if k != "model_name"
})
```

This reconstructs a byte-for-byte-equivalent encoder to the one used at index time,
because none of these parameters are corpus-derived — they're just the config passed
at construction.

## Implications for Tasks 15–17

- **Tasks 15/16 ("fit corpus IDF")** become **"instantiate + persist config."** There is
  no actual corpus-relative fitting step to perform. `list(model.embed(corpus))  #
  triggers corpus IDF fit` from the spec draft is misleading — that line does nothing
  but produce sparse vectors for the corpus; it does not change the model's future
  behavior. Whatever downstream artifact Tasks 15/16 were going to persist should be
  the JSON config above (trivial, effectively static across runs — it will only change
  if someone deliberately overrides `k`/`b`/`avg_len`/`language` from the defaults).
- **Task 17's gates still hold**: the index build still depends on the persisted
  config artifact existing before query-time encoding can run, exactly as the original
  plan assumed for the pickle file — just swap "pickled model" for "config JSON" in
  whatever gate/dependency check Task 17 implements.
- Do **not** attempt `pickle.dump(model)` (or the inner `Bm25`) directly — it will
  raise `TypeError: cannot pickle 'builtins.SnowballStemmer' object` on `fastembed
  0.8.0`. If a future fastembed version makes the stemmer picklable, the config-based
  approach above still works and is simpler/more portable (e.g. across Python/fastembed
  versions), so there's no reason to revisit pickling even if it becomes possible.
- Sparse vector consistency across index/query time depends only on all four
  parameters (`k`, `b`, `avg_len`, `language`) plus `token_max_length` and
  `disable_stemmer` matching — not on any fit corpus. Different corpora will **not**
  produce different sparse vectors for the same input text under this
  implementation.

## Environment notes

- `fastembed==0.8.0` was installed into `datapipeline/.venv` and added to
  `datapipeline/requirements.txt`.
- First run of the spike downloaded the `Qdrant/bm25` model files (18 files) from
  Hugging Face Hub to a local cache (`$TMPDIR/fastembed_cache`); this is a one-time
  network fetch per machine/cache location.
