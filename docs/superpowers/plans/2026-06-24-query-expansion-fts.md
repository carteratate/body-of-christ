# Query Expansion — FTS Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing `expand_query()` function into the search pipeline so its 2 alternative phrasings (synonym + related concept) are used as additional FTS inputs during retrieval, running concurrently with HyDE at zero added latency cost.

**Architecture:** `expand_query()` is added to the initial `asyncio.gather` in `pipeline.py` alongside the existing HyDE calls — it finishes in ~1s, well inside the Bible HyDE window (~3-4s). The 2 expansion strings are passed as a new `expansion_queries` parameter to `retrieve_candidates()`, where each becomes an additional `_search_fts()` call inside the existing per-collection `asyncio.gather`. Results feed into RRF alongside the existing strategies with no change to the reranker or any downstream code. FTS only — no new Qdrant searches.

**Tech Stack:** Python asyncio, FastAPI lifespan, asyncpg (Postgres FTS), Anthropic SDK (Haiku via `expand_query`), pytest-asyncio

## Global Constraints

- No new Qdrant searches — expansion goes to `_search_fts` only
- All expansion calls run inside the existing `asyncio.gather` blocks — no new serial steps
- Graceful fallback: if `expand_query` fails it returns `[]`; `expand_candidates` default is `None`; no behaviour change if expansion is absent
- No changes to `_rrf_merge`, `rerank_collection`, `stream_explanation`, or SSE event schema
- Follow existing mock patterns in `test_retrieve.py` (patch at module level, not pool.fetch)
- All test IDs use the `xxxxxxxx-0000-0000-0000-000000000001` format already in `test_retrieve.py`

---

## File Map

| File | Change |
|---|---|
| `services/api/app/main.py` | Add `init_query_expand` / `close_query_expand` to lifespan |
| `services/api/app/rag/retrieve.py` | Add `expansion_queries` parameter; add FTS calls per expansion string |
| `services/api/app/rag/pipeline.py` | Import `expand_query`; add to initial gather; extract result; pass to `retrieve_candidates` |
| `services/api/tests/test_retrieve.py` | Add 2 tests for the new `expansion_queries` parameter |
| `services/api/tests/test_query_expand.py` | New file — 4 unit tests for `expand_query` |

---

## Task 1: Wire query_expand lifecycle into main.py

**Files:**
- Modify: `services/api/app/main.py:51-64`

**Interfaces:**
- Consumes: `init_query_expand()` and `close_query_expand()` from `app.rag.query_expand` (already exist, already correct — just never called)
- Produces: nothing new; `expand_query()` will work at runtime (returns `[]` when client not initialised otherwise)

- [ ] **Step 1: Add the import**

Open `services/api/app/main.py`. After the existing `from app.rag.hyde import close_hyde, init_hyde` import line (currently line 20), add:

```python
from app.rag.query_expand import close_query_expand, init_query_expand
```

- [ ] **Step 2: Call init in lifespan startup**

In the `lifespan` function, the startup block currently ends with:
```python
    init_llm()
    init_embed()
    init_hyde()
    init_qdrant()
    init_rerank()
    init_explain()
    yield
```

Add `init_query_expand()` after `init_hyde()`:
```python
    init_llm()
    init_embed()
    init_hyde()
    init_query_expand()
    init_qdrant()
    init_rerank()
    init_explain()
    yield
```

- [ ] **Step 3: Call close in lifespan teardown**

The teardown block currently reads:
```python
    await close_embed()
    await close_hyde()
    await close_qdrant()
    await close_rerank()
    await close_explain()
    await close_pool()
    await close_llm()
```

Add `await close_query_expand()` after `await close_hyde()`:
```python
    await close_embed()
    await close_hyde()
    await close_query_expand()
    await close_qdrant()
    await close_rerank()
    await close_explain()
    await close_pool()
    await close_llm()
```

- [ ] **Step 4: Verify the file parses**

```bash
cd services/api && python -c "from app.main import app; print('OK')"
```

Expected output: `OK`

- [ ] **Step 5: Commit**

```bash
git add services/api/app/main.py
git commit -m "feat: wire query_expand lifecycle into app lifespan"
```

---

## Task 2: Add expansion_queries parameter to retrieve_candidates

**Files:**
- Modify: `services/api/app/rag/retrieve.py:192-283`
- Test: `services/api/tests/test_retrieve.py`

**Interfaces:**
- Consumes: `_search_fts(pool, collection, user_id, query_text, limit) -> list[dict]` — already exists at line 113
- Produces: `retrieve_candidates(..., expansion_queries: list[str] | None = None)` — Task 3 relies on this exact signature

- [ ] **Step 1: Write the two failing tests**

Append to `services/api/tests/test_retrieve.py`:

```python
# ---------------------------------------------------------------------------
# expansion_queries parameter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieve_candidates_calls_fts_for_each_expansion():
    """FTS is called once per expansion query plus once for the original query."""
    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([]))

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(return_value=[])  # _get_excluded_ids

    with (
        patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieve.get_pool", return_value=mock_pool),
        patch("app.rag.retrieve.settings") as mock_settings,
        patch("app.rag.retrieve._search_fts", new_callable=AsyncMock) as mock_fts,
    ):
        mock_settings.candidate_multiplier = 3
        mock_fts.return_value = []

        await retrieve_candidates(
            query_text="Holy Spirit",
            query_vec=[0.1] * 1536,
            hyde_vec=None,
            extra_vecs=[],
            collection="catechism",
            quota=4,
            user_id="00000000-0000-0000-0000-000000000001",
            expansion_queries=["Holy Ghost", "divine grace"],
        )

    # original + 2 expansion = 3 FTS calls
    assert mock_fts.call_count == 3
    fts_texts = {call.args[3] for call in mock_fts.call_args_list}
    assert fts_texts == {"Holy Spirit", "Holy Ghost", "divine grace"}


@pytest.mark.asyncio
async def test_retrieve_candidates_no_expansion_by_default():
    """Without expansion_queries, only the original FTS call is made."""
    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([]))

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(return_value=[])

    with (
        patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieve.get_pool", return_value=mock_pool),
        patch("app.rag.retrieve.settings") as mock_settings,
        patch("app.rag.retrieve._search_fts", new_callable=AsyncMock) as mock_fts,
    ):
        mock_settings.candidate_multiplier = 3
        mock_fts.return_value = []

        await retrieve_candidates(
            query_text="grace",
            query_vec=[0.1] * 1536,
            hyde_vec=None,
            extra_vecs=[],
            collection="catechism",
            quota=4,
            user_id="00000000-0000-0000-0000-000000000001",
        )

    assert mock_fts.call_count == 1
    assert mock_fts.call_args.args[3] == "grace"
```

- [ ] **Step 2: Run both tests — expect failure**

```bash
cd services/api && python -m pytest tests/test_retrieve.py::test_retrieve_candidates_calls_fts_for_each_expansion tests/test_retrieve.py::test_retrieve_candidates_no_expansion_by_default -v
```

Expected: `FAILED` — `retrieve_candidates() got an unexpected keyword argument 'expansion_queries'`

- [ ] **Step 3: Update the retrieve_candidates signature**

In `services/api/app/rag/retrieve.py`, change the function signature at line 192:

```python
# OLD
async def retrieve_candidates(
    query_text: str,
    query_vec: list[float],
    hyde_vec: list[float] | None,
    extra_vecs: list[list[float]],
    collection: str,
    quota: int,
    user_id: str,
) -> list[ChunkCandidate]:
```

```python
# NEW
async def retrieve_candidates(
    query_text: str,
    query_vec: list[float],
    hyde_vec: list[float] | None,
    extra_vecs: list[list[float]],
    collection: str,
    quota: int,
    user_id: str,
    expansion_queries: list[str] | None = None,
) -> list[ChunkCandidate]:
```

Also update the docstring Args block (the line after `user_id` description):

```python
        expansion_queries: Optional list of alternative query phrasings (synonym,
            related concept) to run as additional FTS searches. None = no expansion.
```

- [ ] **Step 4: Add expansion FTS calls**

Find the FTS block in `retrieve_candidates` (lines 236-242). It currently reads:

```python
    if pool is not None:
        coros.append(_search_fts(pool, collection, user_id, query_text, n))
        labels.append("fts")
    else:
        logger.warning(
            "retrieve_candidates: no DB pool — skipping FTS for collection '%s'", collection
        )
```

Replace it with:

```python
    if pool is not None:
        coros.append(_search_fts(pool, collection, user_id, query_text, n))
        labels.append("fts")
        for i, eq in enumerate(expansion_queries or []):
            coros.append(_search_fts(pool, collection, user_id, eq, n))
            labels.append(f"fts_expand_{i}")
    else:
        logger.warning(
            "retrieve_candidates: no DB pool — skipping FTS for collection '%s'", collection
        )
```

- [ ] **Step 5: Run the new tests — expect pass**

```bash
cd services/api && python -m pytest tests/test_retrieve.py::test_retrieve_candidates_calls_fts_for_each_expansion tests/test_retrieve.py::test_retrieve_candidates_no_expansion_by_default -v
```

Expected: `PASSED PASSED`

- [ ] **Step 6: Run the full retrieve test suite — expect no regressions**

```bash
cd services/api && python -m pytest tests/test_retrieve.py -v
```

Expected: all existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/rag/retrieve.py services/api/tests/test_retrieve.py
git commit -m "feat: add expansion_queries parameter to retrieve_candidates for FTS multi-query"
```

---

## Task 3: Wire expand_query into pipeline + unit-test expand_query

**Files:**
- Modify: `services/api/app/rag/pipeline.py:14-118`
- Create: `services/api/tests/test_query_expand.py`

**Interfaces:**
- Consumes: `expand_query(query: str) -> list[str]` from `app.rag.query_expand` (existing, returns ≤2 strings, never raises)
- Consumes: `retrieve_candidates(..., expansion_queries: list[str] | None = None)` from Task 2
- Produces: no new public interface — pipeline internals only

- [ ] **Step 1: Write unit tests for expand_query**

Create `services/api/tests/test_query_expand.py`:

```python
"""Unit tests for expand_query."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.query_expand import expand_query


@pytest.mark.asyncio
async def test_expand_query_returns_two_variants():
    """On success, returns exactly the 2 strings from the model response."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='["Holy Ghost", "divine mercy"]')]

    with patch("app.rag.query_expand._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await expand_query("What is the Holy Spirit?")

    assert result == ["Holy Ghost", "divine mercy"]


@pytest.mark.asyncio
async def test_expand_query_returns_empty_when_not_initialized():
    """Returns empty list (never raises) when the client has not been initialised."""
    with patch("app.rag.query_expand._client", None):
        result = await expand_query("test query")

    assert result == []


@pytest.mark.asyncio
async def test_expand_query_returns_empty_on_api_failure():
    """Returns empty list (never raises) when the Anthropic API call fails."""
    with patch("app.rag.query_expand._client") as mock_client:
        mock_client.messages.create = AsyncMock(side_effect=Exception("network error"))
        result = await expand_query("test query")

    assert result == []


@pytest.mark.asyncio
async def test_expand_query_caps_at_two():
    """Never returns more than 2 strings even if the model returns extras."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='["a", "b", "c", "d"]')]

    with patch("app.rag.query_expand._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await expand_query("test")

    assert len(result) <= 2
```

- [ ] **Step 2: Run the new tests — expect failure**

```bash
cd services/api && python -m pytest tests/test_query_expand.py -v
```

Expected: `FAILED` with `ModuleNotFoundError` or `ImportError` — the module exists but `_client` is `None` at import time, so only the `_not_initialized` test may pass. The key failure to confirm is that the tests *run* against the real module.

- [ ] **Step 3: Verify the module imports cleanly**

```bash
cd services/api && python -c "from app.rag.query_expand import expand_query; print('OK')"
```

Expected: `OK`

If this passes, re-run the tests:

```bash
cd services/api && python -m pytest tests/test_query_expand.py -v
```

Expected: all 4 `PASSED` — these tests mock at the `_client` level so no real API key is needed.

- [ ] **Step 4: Add the expand_query import to pipeline.py**

In `services/api/app/rag/pipeline.py`, the import block currently ends around line 18:

```python
from app.rag.constants import VALID_COLLECTIONS
```

Add the new import on the next line:

```python
from app.rag.query_expand import expand_query
```

- [ ] **Step 5: Add expand_query to the initial asyncio.gather**

The current gather in `run_search_pipeline` (lines 71-75):

```python
        all_results = await asyncio.gather(
            embed_text(query),
            *[_hyde_and_embed(query, col) for col in collections],
            return_exceptions=True,
        )
```

Replace with:

```python
        all_results = await asyncio.gather(
            embed_text(query),
            expand_query(query),
            *[_hyde_and_embed(query, col) for col in collections],
            return_exceptions=True,
        )
```

- [ ] **Step 6: Update result unpacking**

The current unpacking (lines 77-78):

```python
        query_vec_result = all_results[0]
        hyde_embed_results = all_results[1:]  # one (col, [vecs]) tuple per collection
```

Replace with:

```python
        query_vec_result = all_results[0]
        expansion_result = all_results[1]
        hyde_embed_results = all_results[2:]  # one (col, [vecs]) tuple per collection

        expansion_queries: list[str] = (
            expansion_result
            if not isinstance(expansion_result, BaseException)
            else []
        )
```

- [ ] **Step 7: Pass expansion_queries to each retrieve_candidates call**

The current retrieve task list (lines 110-116):

```python
        retrieve_tasks = [
            retrieve_candidates(
                query, query_vec, per_col_hyde_vec[col],
                per_col_extra_hyde_vecs[col],
                col, quota, user_id,
            )
            for col in collections
        ]
```

Replace with:

```python
        retrieve_tasks = [
            retrieve_candidates(
                query, query_vec, per_col_hyde_vec[col],
                per_col_extra_hyde_vecs[col],
                col, quota, user_id,
                expansion_queries=expansion_queries,
            )
            for col in collections
        ]
```

- [ ] **Step 8: Verify the pipeline file parses**

```bash
cd services/api && python -c "from app.rag.pipeline import run_search_pipeline; print('OK')"
```

Expected: `OK`

- [ ] **Step 9: Run the full test suite**

```bash
cd services/api && python -m pytest tests/ -v
```

Expected: all tests pass. The pipeline integration isn't tested end-to-end here (that would require a live Qdrant + Anthropic API), but the unit tests confirm each piece works in isolation.

- [ ] **Step 10: Commit**

```bash
git add services/api/app/rag/pipeline.py services/api/tests/test_query_expand.py
git commit -m "feat: wire expand_query into pipeline — expansion strings fed to FTS at no latency cost"
```

---

## Self-Review

**Spec coverage:**
- ✅ `expand_query()` runs in the initial gather (zero wall-clock cost)
- ✅ Expansion strings go to FTS only — no new Qdrant searches
- ✅ Results merge into RRF pool alongside existing strategies (no downstream changes needed)
- ✅ Graceful fallback: BaseException → `[]` → `expansion_queries or []` → no extra FTS calls
- ✅ Lifecycle init/close wired
- ✅ All 3 modified files have tests

**Placeholder scan:** None found.

**Type consistency:**
- `expansion_queries: list[str] | None = None` in `retrieve_candidates` (Task 2)
- `expansion_queries: list[str]` extracted in pipeline (Task 3) — guaranteed `list[str]` because BaseException case returns `[]`
- `expansion_queries=expansion_queries` passed as kwarg — matches parameter name exactly
- `call.args[3]` in tests — `_search_fts(pool, collection, user_id, query_text, limit)` → index 3 is `query_text` ✅
