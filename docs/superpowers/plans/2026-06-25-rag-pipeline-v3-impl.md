# V3 RAG Pipeline (Pre-Enrichment) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Sonnet reranking with a local BGE cross-encoder, add position+cosine dedup with per-title cap, wire 4-key API isolation for HyDE, and remove `expand_query` — saving ~$0.111/search with no enrichment data required.

**Architecture:** 9 focused tasks in dependency order. Each RAG submodule (`cross_encoder.py`, `dedup.py`, `api_keys.py`) is a single-responsibility file tested in isolation before being wired into `pipeline.py`. All BGE scoring runs synchronously in a thread executor so it doesn't block the event loop.

**Tech Stack:** Python 3.11, FastAPI, `sentence-transformers>=3.0.0` (BGE cross-encoder), asyncpg, qdrant-client, anthropic SDK, pytest + asyncio

## Global Constraints

- `services/api/` is the working directory for all backend changes
- Run `cd services/api && python -m pytest tests/ -v` after every task
- Run `cd services/api && python -m ruff check app/` if linting fails in CI
- Never import from `app.rag.query_expand` after Task 8 (it will be deleted in Task 9)
- `RankedChunk` stays defined in `app/rag/rerank.py` — do not move it
- BGE scores are log-odds (−10 to +10); always sigmoid-normalize to [0, 1] before storing in `reranker_score`
- Per-title cap is 2, cosine dedup threshold is 0.9, position proximity is ≤ 2

---

## Task 1: Dependencies + Dockerfile

**Files:**
- Modify: `services/api/pyproject.toml`
- Modify: `services/api/Dockerfile`

**Interfaces:**
- Produces: `from sentence_transformers import CrossEncoder` importable; `CrossEncoder('BAAI/bge-reranker-v2-m3')` loads without downloading (baked into Docker image)

- [ ] **Step 1: Add sentence-transformers to pyproject.toml**

Open `services/api/pyproject.toml`. The `dependencies` list currently ends with `"qdrant-client>=1.9.0"`. Add one line after it:

```toml
[project]
name = "body-of-christ-api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic-settings>=2.2.0",
    "asyncpg>=0.29.0",
    "httpx>=0.27.0",
    "PyJWT[cryptography]>=2.8.0",
    "cryptography>=42.0.0",
    "anthropic>=0.40.0",
    "openai>=1.0.0",
    "qdrant-client>=1.9.0",
    "sentence-transformers>=3.0.0",
]
```

- [ ] **Step 2: Install and smoke-test**

```bash
cd services/api && pip install -e ".[dev]"
python -c "from sentence_transformers import CrossEncoder; m = CrossEncoder('BAAI/bge-reranker-v2-m3'); scores = m.predict([('what is grace?', 'Grace is a gift from God.')]); print('score:', float(scores[0]))"
```

Expected output: `score: <some float>` (typically between -2 and +10 for a relevant pair).

- [ ] **Step 3: Pre-bake model in Dockerfile**

Open `services/api/Dockerfile`. Current content:

```dockerfile
FROM python:3.11-slim

RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY app/ app/

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Replace with:

```dockerfile
FROM python:3.11-slim

RUN adduser --disabled-password --gecos "" appuser

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Pre-download BGE cross-encoder weights so the first request isn't blocked
# downloading ~1GB from HuggingFace. Weights are baked into this image layer.
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3')"

COPY app/ app/

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: Verify existing tests still pass**

```bash
cd services/api && python -m pytest tests/ -v
```

Expected: all tests pass (no changes to application code yet).

- [ ] **Step 5: Commit**

```bash
git add services/api/pyproject.toml services/api/Dockerfile
git commit -m "feat(api): add sentence-transformers dep; pre-bake BGE model in Docker"
```

---

## Task 2: Add `position` field to `RankedChunk`

**Files:**
- Modify: `services/api/app/rag/rerank.py` (lines 62–73)
- Test: `services/api/tests/test_rerank.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `RankedChunk.position: int | None = None` — available to all callers that import `RankedChunk`

- [ ] **Step 1: Write the failing test**

Append to `services/api/tests/test_rerank.py`:

```python
def test_ranked_chunk_has_position_field():
    """RankedChunk must carry a position field for downstream dedup."""
    from app.rag.rerank import RankedChunk
    chunk = RankedChunk(
        chunk_id="00000000-0000-0000-0000-000000000010",
        content="test",
        reference="Gen 1:1",
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis",
        author=None,
        reranker_score=0.8,
        position=5,
    )
    assert chunk.position == 5


def test_ranked_chunk_position_defaults_to_none():
    """position must default to None so existing callers don't need to change."""
    from app.rag.rerank import RankedChunk
    chunk = RankedChunk(
        chunk_id="00000000-0000-0000-0000-000000000011",
        content="test",
        reference=None,
        collection="catechism",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="CCC",
        author=None,
        reranker_score=0.5,
    )
    assert chunk.position is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/api && python -m pytest tests/test_rerank.py::test_ranked_chunk_has_position_field tests/test_rerank.py::test_ranked_chunk_position_defaults_to_none -v
```

Expected: FAIL — `RankedChunk.__init__() got an unexpected keyword argument 'position'`

- [ ] **Step 3: Add `position` field to `RankedChunk`**

In `services/api/app/rag/rerank.py`, the `RankedChunk` dataclass currently ends at line 73 with `anchor: str | None = None`. Add one field after it:

```python
@dataclass
class RankedChunk:
    chunk_id: str
    content: str
    reference: str | None
    collection: str
    document_id: str
    document_title: str
    author: str | None
    reranker_score: float  # 0.0–1.0
    include: bool = True
    anchor: str | None = None
    position: int | None = None
```

- [ ] **Step 4: Run all rerank tests**

```bash
cd services/api && python -m pytest tests/test_rerank.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/rag/rerank.py services/api/tests/test_rerank.py
git commit -m "feat(rerank): add position field to RankedChunk for dedup"
```

---

## Task 3: `ChunkCandidate` position/annotation + FTS SQL + batch position lookup

**Files:**
- Modify: `services/api/app/rag/retrieve.py`
- Modify: `services/api/tests/test_retrieve.py`

**Interfaces:**
- Consumes: `pool.fetch("SELECT id::text, position FROM chunks WHERE id::text = ANY($1)", ...)` — new DB call after RRF merge
- Produces:
  - `ChunkCandidate.position: int | None` — populated from FTS result or batch DB lookup
  - `ChunkCandidate.annotation: dict | None` — populated from FTS result when enrichment data exists; `None` until enrichment runs

- [ ] **Step 1: Write the failing tests**

Append to `services/api/tests/test_retrieve.py`:

```python
def test_chunk_candidate_has_position_field():
    """ChunkCandidate must carry position for dedup."""
    c = ChunkCandidate(
        chunk_id="aaaa0000-0000-0000-0000-000000000001",
        content="test",
        reference=None,
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis",
        author=None,
        rrf_score=0.5,
        position=7,
    )
    assert c.position == 7


def test_chunk_candidate_position_defaults_to_none():
    c = ChunkCandidate(
        chunk_id="aaaa0000-0000-0000-0000-000000000002",
        content="test",
        reference=None,
        collection="catechism",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="CCC",
        author=None,
        rrf_score=0.5,
    )
    assert c.position is None


@pytest.mark.asyncio
async def test_retrieve_candidates_populates_position_from_fts():
    """FTS results must include position; it must reach ChunkCandidate.position."""
    chunk_id = "fts00000-0000-0000-0000-000000000001"
    fts_row = {
        "id": chunk_id,
        "content": "FTS result",
        "reference": "Test 1:1",
        "collection": "catechism",
        "document_id": "00000000-0000-0000-0000-000000000099",
        "document_title": "CCC",
        "author": None,
        "anchor": None,
        "position": 42,
        "annotation": None,
    }

    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(side_effect=RuntimeError("no qdrant"))

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(side_effect=[
        [],           # _get_excluded_ids
        [fts_row],    # _search_fts
        # No batch position lookup needed — FTS already has position
    ])

    with (
        patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieve.get_pool", return_value=mock_pool),
        patch("app.rag.retrieve.settings") as mock_settings,
    ):
        mock_settings.candidate_multiplier = 3
        results = await retrieve_candidates(
            query_text="grace",
            query_vec=[0.1] * 1536,
            hyde_vec=None,
            extra_vecs=[],
            collection="catechism",
            quota=4,
            user_id="00000000-0000-0000-0000-000000000001",
        )

    assert len(results) == 1
    assert results[0].position == 42


@pytest.mark.asyncio
async def test_retrieve_candidates_batch_fetches_position_for_qdrant_results():
    """Qdrant-sourced candidates have no position in payload; must be fetched from DB."""
    chunk_id = "qdrant00-0000-0000-0000-000000000001"
    mock_client = AsyncMock()
    mock_client.query_points = AsyncMock(return_value=_mock_query_response([
        _scored_point(chunk_id),
    ]))

    mock_pool = MagicMock()
    mock_pool.fetch = AsyncMock(side_effect=[
        [],   # _get_excluded_ids
        [],   # _search_fts (empty)
        [{"id": chunk_id, "position": 17}],  # batch position lookup
    ])

    with (
        patch("app.rag.retrieve.get_qdrant_client", return_value=mock_client),
        patch("app.rag.retrieve.get_pool", return_value=mock_pool),
        patch("app.rag.retrieve.settings") as mock_settings,
    ):
        mock_settings.candidate_multiplier = 3
        results = await retrieve_candidates(
            query_text="test",
            query_vec=[0.1] * 1536,
            hyde_vec=None,
            extra_vecs=[],
            collection="bible",
            quota=4,
            user_id="00000000-0000-0000-0000-000000000001",
        )

    assert len(results) >= 1
    assert results[0].position == 17
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/api && python -m pytest tests/test_retrieve.py::test_chunk_candidate_has_position_field tests/test_retrieve.py::test_chunk_candidate_position_defaults_to_none tests/test_retrieve.py::test_retrieve_candidates_populates_position_from_fts tests/test_retrieve.py::test_retrieve_candidates_batch_fetches_position_for_qdrant_results -v
```

Expected: FAIL — `ChunkCandidate.__init__() got an unexpected keyword argument 'position'` and position-related assertion failures.

- [ ] **Step 3: Update `ChunkCandidate` dataclass**

In `services/api/app/rag/retrieve.py`, the `ChunkCandidate` dataclass currently ends with `anchor: str | None = None`. Replace the entire dataclass:

```python
@dataclass
class ChunkCandidate:
    chunk_id: str
    content: str
    reference: str | None
    collection: str
    document_id: str
    document_title: str
    author: str | None
    rrf_score: float
    anchor: str | None = None
    position: int | None = None
    annotation: dict | None = None   # populated post-enrichment; None until then
```

- [ ] **Step 4: Update `_search_fts` SQL to include position and annotation**

In `services/api/app/rag/retrieve.py`, replace the `_search_fts` function body. The SQL query currently selects `c.id::text, c.content, c.reference, c.anchor, c.document_id::text, d.title, d.author, d.collection`. Replace the entire function:

```python
async def _search_fts(
    pool: asyncpg.Pool,
    collection: str,
    user_id: str,
    query_text: str,
    limit: int,
) -> list[dict]:
    """Full-text search against search_vector using plainto_tsquery (Supabase/Postgres)."""
    query = """
        SELECT c.id::text AS id, c.content, c.reference, c.anchor, c.position,
               c.annotation,
               c.document_id::text AS document_id,
               d.title AS document_title, d.author, d.collection
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.collection = $1
          AND c.search_vector @@ plainto_tsquery('english', $3)
          AND NOT EXISTS (
              SELECT 1 FROM chunk_feedback cf
              WHERE cf.chunk_id = c.id
                AND cf.user_id = $2
                AND cf.feedback = 'down'
          )
        ORDER BY ts_rank(c.search_vector, plainto_tsquery('english', $3)) DESC
        LIMIT $4
    """
    rows = await pool.fetch(query, collection, user_id, query_text, limit)
    logger.debug("fts search: collection=%s returned %d rows", collection, len(rows))
    return [dict(r) for r in rows]
```

- [ ] **Step 5: Update `_rrf_merge` metadata dict to capture position and annotation**

In `services/api/app/rag/retrieve.py`, inside `_rrf_merge`, find the `metadata[chunk_id] = {...}` block. Replace it:

```python
            if chunk_id not in metadata:
                metadata[chunk_id] = {
                    "chunk_id": chunk_id,
                    "content": row["content"],
                    "reference": row["reference"],
                    "collection": row["collection"],
                    "document_id": str(row["document_id"]),
                    "document_title": row["document_title"],
                    "author": row["author"],
                    "anchor": row.get("anchor"),
                    "position": row.get("position"),
                    "annotation": row.get("annotation"),
                }
```

- [ ] **Step 6: Add batch position lookup after `_rrf_merge` in `retrieve_candidates`**

In `services/api/app/rag/retrieve.py`, inside `retrieve_candidates`, find the line `merged = _rrf_merge(result_lists, top_n=n)`. Add the following block immediately after it:

```python
    merged = _rrf_merge(result_lists, top_n=n)

    # Qdrant payload does not include position. Batch-fetch from DB for any
    # candidate that arrived via vector search (position will be None).
    missing_ids = [e["chunk_id"] for e in merged if e.get("position") is None]
    if missing_ids and pool is not None:
        try:
            pos_rows = await pool.fetch(
                "SELECT id::text, position FROM chunks WHERE id::text = ANY($1)",
                missing_ids,
            )
            pos_map = {r["id"]: r["position"] for r in pos_rows}
            for e in merged:
                if e.get("position") is None:
                    e["position"] = pos_map.get(e["chunk_id"])
        except Exception as exc:
            logger.warning("retrieve_candidates: position batch lookup failed: %s", exc)
```

- [ ] **Step 7: Update `ChunkCandidate` construction to pass new fields**

In `services/api/app/rag/retrieve.py`, inside `retrieve_candidates`, find the list comprehension that builds `candidates`. Replace it:

```python
    candidates = [
        ChunkCandidate(
            chunk_id=entry["chunk_id"],
            content=entry["content"],
            reference=entry["reference"],
            collection=entry["collection"],
            document_id=entry["document_id"],
            document_title=entry["document_title"],
            author=entry["author"],
            rrf_score=entry["rrf_score"],
            anchor=entry.get("anchor"),
            position=entry.get("position"),
            annotation=entry.get("annotation"),
        )
        for entry in merged
    ]
```

- [ ] **Step 8: Run all retrieve tests**

```bash
cd services/api && python -m pytest tests/test_retrieve.py -v
```

Expected: all tests PASS, including the 4 new ones.

- [ ] **Step 9: Commit**

```bash
git add services/api/app/rag/retrieve.py services/api/tests/test_retrieve.py
git commit -m "feat(retrieve): add position/annotation to ChunkCandidate; batch position lookup for Qdrant results"
```

---

## Task 4: Config keys B/C/D + `api_keys.py`

**Files:**
- Modify: `services/api/app/config.py`
- Create: `services/api/app/rag/api_keys.py`
- Create: `services/api/tests/test_api_keys.py`

**Interfaces:**
- Consumes: `settings.anthropic_api_key` (key A), `settings.anthropic_api_key_b/c/d` (optional)
- Produces:
  - `init_api_keys() -> None` — call once at startup
  - `close_api_keys() -> Coroutine` — call at shutdown
  - `get_key_for(collection: str) -> str` — returns `"A"`, `"B"`, `"C"`, or `"D"`
  - `get_client(key: str) -> anthropic.AsyncAnthropic`
  - `get_semaphore(key: str) -> asyncio.Semaphore`

- [ ] **Step 1: Write failing tests**

Create `services/api/tests/test_api_keys.py`:

```python
"""Tests for API key assignment and semaphore management."""
import asyncio
from unittest.mock import MagicMock, patch
import pytest

from app.rag.api_keys import get_key_for, get_client, get_semaphore, init_api_keys


def _mock_settings(key_a="sk-a", key_b=None, key_c=None, key_d=None):
    s = MagicMock()
    s.anthropic_api_key = key_a
    s.anthropic_api_key_b = key_b
    s.anthropic_api_key_c = key_c
    s.anthropic_api_key_d = key_d
    return s


def test_bible_always_gets_key_a():
    with patch("app.rag.api_keys.settings", _mock_settings()):
        init_api_keys()
        assert get_key_for("bible") == "A"


def test_non_bible_cycles_through_bcd():
    with patch("app.rag.api_keys.settings", _mock_settings()):
        init_api_keys()
        keys = [get_key_for("catechism") for _ in range(6)]
    # Must cycle through B, C, D repeatedly — never A
    assert all(k in ("B", "C", "D") for k in keys)
    assert len(set(keys)) >= 2  # at least two distinct keys used


def test_get_client_returns_anthropic_client():
    import anthropic
    with patch("app.rag.api_keys.settings", _mock_settings()):
        init_api_keys()
        client = get_client("A")
    assert isinstance(client, anthropic.AsyncAnthropic)


def test_get_semaphore_bible_has_value_4():
    with patch("app.rag.api_keys.settings", _mock_settings()):
        init_api_keys()
        sem = get_semaphore("A")
    # asyncio.Semaphore._value reflects current capacity
    assert sem._value == 4


def test_get_semaphore_non_bible_has_value_3():
    with patch("app.rag.api_keys.settings", _mock_settings()):
        init_api_keys()
        assert get_semaphore("B")._value == 3
        assert get_semaphore("C")._value == 3
        assert get_semaphore("D")._value == 3


def test_single_key_fallback_when_bcd_not_configured():
    """All keys use the same underlying API key when B/C/D env vars are absent."""
    with patch("app.rag.api_keys.settings", _mock_settings(key_a="sk-only")):
        init_api_keys()
        # Clients for B/C/D must still exist (fallback to key A's value)
        client_b = get_client("B")
        client_a = get_client("A")
    import anthropic
    assert isinstance(client_b, anthropic.AsyncAnthropic)
    assert isinstance(client_a, anthropic.AsyncAnthropic)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/api && python -m pytest tests/test_api_keys.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.rag.api_keys'`

- [ ] **Step 3: Add keys B/C/D to `config.py`**

In `services/api/app/config.py`, after the `anthropic_api_key` field, add:

```python
    # API keys for per-key HyDE semaphoring
    # Key A (anthropic_api_key) = Bible dedicated
    # Keys B/C/D = non-Bible collections, round-robin per query
    # All default to None; runtime falls back to anthropic_api_key when unset
    anthropic_api_key_b: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY_B")
    anthropic_api_key_c: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY_C")
    anthropic_api_key_d: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY_D")
```

- [ ] **Step 4: Create `services/api/app/rag/api_keys.py`**

```python
"""API key assignment and per-key semaphore management for HyDE generation.

Key A: Bible (dedicated, semaphore=4 for 2-wave 8-call HyDE)
Key B: round-robin non-Bible
Key C: round-robin non-Bible
Key D: round-robin non-Bible

Falls back to ANTHROPIC_API_KEY for any key not configured via env var.
"""
from __future__ import annotations

import asyncio
import itertools
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

_BIBLE_COLLECTION = "bible"
_NON_BIBLE_KEYS = ["B", "C", "D"]

_clients: dict[str, anthropic.AsyncAnthropic] = {}
_semaphores: dict[str, asyncio.Semaphore] = {}
_key_cycle = itertools.cycle(_NON_BIBLE_KEYS)


def init_api_keys() -> None:
    """Build one Anthropic client and one semaphore per key letter. Call once at startup."""
    global _key_cycle
    _key_cycle = itertools.cycle(_NON_BIBLE_KEYS)  # reset on re-init

    key_values = {
        "A": settings.anthropic_api_key,
        "B": settings.anthropic_api_key_b or settings.anthropic_api_key,
        "C": settings.anthropic_api_key_c or settings.anthropic_api_key,
        "D": settings.anthropic_api_key_d or settings.anthropic_api_key,
    }
    semaphore_sizes = {"A": 4, "B": 3, "C": 3, "D": 3}

    _clients.clear()
    _semaphores.clear()
    for letter, api_key in key_values.items():
        _clients[letter] = anthropic.AsyncAnthropic(api_key=api_key)
        _semaphores[letter] = asyncio.Semaphore(semaphore_sizes[letter])

    logger.info(
        "api_keys: A=...%s B=...%s C=...%s D=...%s",
        key_values["A"][-4:], key_values["B"][-4:],
        key_values["C"][-4:], key_values["D"][-4:],
    )


async def close_api_keys() -> None:
    """Close all Anthropic clients. Call at shutdown."""
    for client in _clients.values():
        await client.close()
    _clients.clear()
    _semaphores.clear()


def get_key_for(collection: str) -> str:
    """Return the key letter for this collection. Bible always gets 'A'."""
    if collection == _BIBLE_COLLECTION:
        return "A"
    return next(_key_cycle)


def get_client(key: str) -> anthropic.AsyncAnthropic:
    return _clients.get(key, _clients["A"])


def get_semaphore(key: str) -> asyncio.Semaphore:
    return _semaphores.get(key, _semaphores["A"])
```

- [ ] **Step 5: Run api_keys tests**

```bash
cd services/api && python -m pytest tests/test_api_keys.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
cd services/api && python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/config.py services/api/app/rag/api_keys.py services/api/tests/test_api_keys.py
git commit -m "feat(api): add 4-key isolation with per-key semaphores for HyDE concurrency"
```

---

## Task 5: `hyde.py` — inject client + semaphore

**Files:**
- Modify: `services/api/app/rag/hyde.py`

**Interfaces:**
- Consumes: `client: anthropic.AsyncAnthropic`, `semaphore: asyncio.Semaphore` — passed in by callers
- Produces:
  - `generate_hyde_passages(query, collection, client, semaphore) -> list[str]` — new signature
  - Removes: `init_hyde()`, `close_hyde()`, module-level `_client`

Note: there are no unit tests for `hyde.py` currently; no test file to update. The change is covered by integration when pipeline tests run.

- [ ] **Step 1: Remove module-level client state and update `_generate_single`**

In `services/api/app/rag/hyde.py`, remove the line:

```python
_client: anthropic.AsyncAnthropic | None = None
```

Replace the `_generate_single` function (currently at the bottom, before the public API section):

```python
async def _generate_single(
    client: anthropic.AsyncAnthropic,
    system: str,
    query: str,
    max_tokens: int,
) -> str | None:
    """Generate one HyDE passage. Returns None on failure."""
    try:
        response = await client.messages.create(
            model=settings.hyde_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": query}],
        )
        return response.content[0].text
    except Exception as exc:
        logger.warning("HyDE passage generation failed: %s", exc)
        return None
```

- [ ] **Step 2: Remove `init_hyde` / `close_hyde` and update `generate_hyde_passages`**

Remove the `init_hyde` and `close_hyde` functions entirely. Replace `generate_hyde_passages` with the following:

```python
async def generate_hyde_passages(
    query: str,
    collection: str | None,
    client: anthropic.AsyncAnthropic,
    semaphore: asyncio.Semaphore,
) -> list[str]:
    """Return hypothetical passages for the given collection.

    For 'bible', generates 8 passages in parallel: one unconstrained free passage
    plus one per genre (all 7 genres simultaneously), gated by the semaphore.
    For all other collections, returns a single-item list. Never raises.
    """
    max_tokens = _COLLECTION_MAX_TOKENS.get(collection or "", _DEFAULT_MAX_TOKENS)

    if collection == "bible":
        async def _guarded(system: str) -> str | None:
            async with semaphore:
                return await _generate_single(client, system, query, max_tokens)

        results = await asyncio.gather(
            _guarded(_HYDE_BIBLE_FREE_PROMPT),
            *[_guarded(p) for p in _GENRE_HYDE_PROMPTS.values()],
        )
        return [r for r in results if r is not None]

    system = _COLLECTION_HYDE_PROMPTS.get(collection or "", _HYDE_SYSTEM_DEFAULT)
    async with semaphore:
        result = await _generate_single(client, system, query, max_tokens)
    return [result] if result is not None else []
```

- [ ] **Step 3: Run the full test suite**

```bash
cd services/api && python -m pytest tests/ -v
```

Expected: all tests PASS. (The `query_expand` tests still pass — that module is untouched.)

- [ ] **Step 4: Commit**

```bash
git add services/api/app/rag/hyde.py
git commit -m "refactor(hyde): inject client+semaphore; remove module-level state"
```

---

## Task 6: `cross_encoder.py` — BGE scoring module

**Files:**
- Create: `services/api/app/rag/cross_encoder.py`
- Create: `services/api/tests/test_cross_encoder.py`

**Interfaces:**
- Consumes: `list[ChunkCandidate]`, `query: str`
- Produces:
  - `init_cross_encoder() -> None`
  - `close_cross_encoder() -> None`
  - `score_candidates(candidates: list[ChunkCandidate], query: str) -> list[RankedChunk]`
    — synchronous; call via `run_in_executor` from async pipeline
    — scores are sigmoid-normalized to [0, 1]
    — returns all candidates sorted descending by `reranker_score`

- [ ] **Step 1: Write failing tests**

Create `services/api/tests/test_cross_encoder.py`:

```python
"""Tests for BGE cross-encoder scoring module."""
import math
from unittest.mock import MagicMock, patch

import pytest

from app.rag.cross_encoder import _sigmoid, score_candidates, init_cross_encoder, close_cross_encoder
from app.rag.retrieve import ChunkCandidate
from app.rag.rerank import RankedChunk


def _make_candidate(
    chunk_id: str,
    content: str = "Test content about grace.",
    annotation: dict | None = None,
    position: int | None = None,
) -> ChunkCandidate:
    return ChunkCandidate(
        chunk_id=chunk_id,
        content=content,
        reference="Gen 1:1",
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis",
        author=None,
        rrf_score=0.5,
        position=position,
        annotation=annotation,
    )


def test_sigmoid_of_zero_is_half():
    assert _sigmoid(0.0) == pytest.approx(0.5)


def test_sigmoid_of_large_positive_approaches_one():
    assert _sigmoid(10.0) > 0.99


def test_sigmoid_of_large_negative_approaches_zero():
    assert _sigmoid(-10.0) < 0.01


def test_score_candidates_returns_ranked_chunks():
    candidates = [
        _make_candidate("00000000-0000-0000-0000-000000000001"),
        _make_candidate("00000000-0000-0000-0000-000000000002"),
    ]
    mock_model = MagicMock()
    mock_model.predict.return_value = [2.0, -1.0]

    with patch("app.rag.cross_encoder._model", mock_model):
        result = score_candidates(candidates, "what is grace?")

    assert len(result) == 2
    assert all(isinstance(r, RankedChunk) for r in result)
    # sorted descending — higher raw score first
    assert result[0].chunk_id == "00000000-0000-0000-0000-000000000001"
    assert result[1].chunk_id == "00000000-0000-0000-0000-000000000002"


def test_score_candidates_normalizes_scores_to_0_1():
    candidates = [_make_candidate("00000000-0000-0000-0000-000000000003")]
    mock_model = MagicMock()
    mock_model.predict.return_value = [5.0]

    with patch("app.rag.cross_encoder._model", mock_model):
        result = score_candidates(candidates, "query")

    assert 0.0 <= result[0].reranker_score <= 1.0
    assert result[0].reranker_score == pytest.approx(_sigmoid(5.0))


def test_score_candidates_prepends_annotation_when_present():
    """When annotation dict has 'annotation' key, it must be prepended to content."""
    annotation = {"topics": ["grace"], "annotation": "Theological note on grace."}
    candidate = _make_candidate(
        "00000000-0000-0000-0000-000000000004",
        content="For by grace you have been saved.",
        annotation=annotation,
    )
    mock_model = MagicMock()
    mock_model.predict.return_value = [1.0]

    with patch("app.rag.cross_encoder._model", mock_model):
        score_candidates([candidate], "grace and salvation")

    # The pair passed to model.predict must include the annotation text
    call_pair = mock_model.predict.call_args[0][0][0]  # first pair
    assert "Theological note on grace." in call_pair[1]
    assert "For by grace you have been saved." in call_pair[1]


def test_score_candidates_uses_content_only_when_annotation_is_none():
    candidate = _make_candidate(
        "00000000-0000-0000-0000-000000000005",
        content="The word of God is living.",
        annotation=None,
    )
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.5]

    with patch("app.rag.cross_encoder._model", mock_model):
        score_candidates([candidate], "scripture")

    call_pair = mock_model.predict.call_args[0][0][0]
    assert call_pair[1] == "The word of God is living."


def test_score_candidates_falls_back_to_rrf_order_when_model_none():
    candidates = [
        _make_candidate("00000000-0000-0000-0000-000000000006"),
        _make_candidate("00000000-0000-0000-0000-000000000007"),
    ]
    with patch("app.rag.cross_encoder._model", None):
        result = score_candidates(candidates, "query")

    assert len(result) == 2
    assert all(isinstance(r, RankedChunk) for r in result)
    # fallback assigns descending scores
    assert result[0].reranker_score >= result[1].reranker_score


def test_score_candidates_propagates_position_to_ranked_chunk():
    candidate = _make_candidate("00000000-0000-0000-0000-000000000008", position=13)
    mock_model = MagicMock()
    mock_model.predict.return_value = [1.0]

    with patch("app.rag.cross_encoder._model", mock_model):
        result = score_candidates([candidate], "query")

    assert result[0].position == 13


def test_score_candidates_empty_input_returns_empty():
    result = score_candidates([], "query")
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/api && python -m pytest tests/test_cross_encoder.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.rag.cross_encoder'`

- [ ] **Step 3: Create `services/api/app/rag/cross_encoder.py`**

```python
"""BGE cross-encoder — zero-cost replacement for Sonnet reranking.

Loaded once at startup via init_cross_encoder(). score_candidates() is
synchronous (CPU-bound); callers must run it in a thread executor to avoid
blocking the event loop:

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, score_candidates, candidates, query)
"""
from __future__ import annotations

import logging
import math

from sentence_transformers import CrossEncoder

from app.rag.retrieve import ChunkCandidate
from app.rag.rerank import RankedChunk

logger = logging.getLogger(__name__)

_MODEL_NAME = "BAAI/bge-reranker-v2-m3"
_model: CrossEncoder | None = None


def init_cross_encoder() -> None:
    global _model
    _model = CrossEncoder(_MODEL_NAME)
    logger.info("Cross-encoder loaded: %s", _MODEL_NAME)


def close_cross_encoder() -> None:
    global _model
    _model = None


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def score_candidates(
    candidates: list[ChunkCandidate],
    query: str,
) -> list[RankedChunk]:
    """Score candidates with BGE cross-encoder. SYNCHRONOUS — run in executor.

    Input text for scoring = annotation text + '\\n\\n' + content when annotation
    is populated; falls back to content alone until enrichment runs.
    Scores are sigmoid-normalized to [0, 1]. Falls back to RRF order on failure.
    Returns all candidates sorted descending by reranker_score.
    """
    if not candidates:
        return []
    if _model is None:
        logger.warning("cross_encoder not initialized; returning RRF order fallback")
        return _fallback_ranked(candidates)

    pairs = []
    for c in candidates:
        annotation_text = ""
        if c.annotation and isinstance(c.annotation, dict):
            annotation_text = c.annotation.get("annotation", "")
            if annotation_text:
                annotation_text += "\n\n"
        pairs.append((query, annotation_text + c.content))

    try:
        raw_scores = _model.predict(pairs)
    except Exception as exc:
        logger.warning("cross_encoder.predict failed: %s", exc)
        return _fallback_ranked(candidates)

    ranked = [
        RankedChunk(
            chunk_id=c.chunk_id,
            content=c.content,
            reference=c.reference,
            collection=c.collection,
            document_id=c.document_id,
            document_title=c.document_title,
            author=c.author,
            reranker_score=_sigmoid(float(score)),
            include=True,
            anchor=c.anchor,
            position=c.position,
        )
        for c, score in zip(candidates, raw_scores)
    ]
    ranked.sort(key=lambda r: r.reranker_score, reverse=True)
    return ranked


def _fallback_ranked(candidates: list[ChunkCandidate]) -> list[RankedChunk]:
    return [
        RankedChunk(
            chunk_id=c.chunk_id,
            content=c.content,
            reference=c.reference,
            collection=c.collection,
            document_id=c.document_id,
            document_title=c.document_title,
            author=c.author,
            reranker_score=max(0.0, 1.0 - i * 0.01),
            include=True,
            anchor=c.anchor,
            position=c.position,
        )
        for i, c in enumerate(candidates)
    ]
```

- [ ] **Step 4: Run cross_encoder tests**

```bash
cd services/api && python -m pytest tests/test_cross_encoder.py -v
```

Expected: all 9 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd services/api && python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/rag/cross_encoder.py services/api/tests/test_cross_encoder.py
git commit -m "feat(rag): add BGE cross-encoder module; sigmoid normalization; annotation+content scoring"
```

---

## Task 7: `dedup.py` — position+cosine dedup + per-title cap

**Files:**
- Create: `services/api/app/rag/dedup.py`
- Create: `services/api/tests/test_dedup.py`

**Interfaces:**
- Consumes: `list[RankedChunk]` (sorted descending by `reranker_score`), Qdrant client for vector fetch
- Produces:
  - `apply_dedup(ranked: list[RankedChunk]) -> Coroutine[list[RankedChunk]]`
    — drops the lower-scorer in any pair from the same document where `|pos_a − pos_b| ≤ 2` AND cosine similarity > 0.9
    — then applies per-title cap: at most 2 chunks per `document_title`
    — returns filtered list in original score order

- [ ] **Step 1: Write failing tests**

Create `services/api/tests/test_dedup.py`:

```python
"""Tests for position+cosine dedup and per-title cap."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.rag.dedup import _cosine_sim, apply_dedup
from app.rag.rerank import RankedChunk


def _chunk(chunk_id: str, doc_id: str, doc_title: str, score: float, position: int | None = None) -> RankedChunk:
    return RankedChunk(
        chunk_id=chunk_id,
        content="content",
        reference="Ref 1:1",
        collection="catechism",
        document_id=doc_id,
        document_title=doc_title,
        author=None,
        reranker_score=score,
        include=True,
        position=position,
    )


# ---------------------------------------------------------------------------
# _cosine_sim
# ---------------------------------------------------------------------------

def test_cosine_sim_identical_vectors_returns_one():
    v = [1.0, 0.0, 0.0]
    assert _cosine_sim(v, v) == pytest.approx(1.0)


def test_cosine_sim_orthogonal_vectors_returns_zero():
    assert _cosine_sim([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_sim_zero_vector_returns_zero():
    assert _cosine_sim([0.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


def test_cosine_sim_opposite_vectors_returns_minus_one():
    assert _cosine_sim([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


# ---------------------------------------------------------------------------
# apply_dedup — cosine dedup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dedup_drops_lower_scorer_when_close_and_cosine_high():
    """Position ≤2 apart AND cosine > 0.9 → lower scorer dropped."""
    a = _chunk("aaaa-0000-0000-0000-000000000001", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000002", "doc1", "CCC", 0.7, position=2)

    vec = [1.0] + [0.0] * 1535  # cosine(v, v) = 1.0 > 0.9

    mock_pt_a = MagicMock(); mock_pt_a.id = "aaaa-0000-0000-0000-000000000001"; mock_pt_a.vector = vec
    mock_pt_b = MagicMock(); mock_pt_b.id = "bbbb-0000-0000-0000-000000000002"; mock_pt_b.vector = vec
    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[mock_pt_a, mock_pt_b])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000001" in ids
    assert "bbbb-0000-0000-0000-000000000002" not in ids


@pytest.mark.asyncio
async def test_dedup_keeps_both_when_cosine_below_threshold():
    """Same document, close positions, but cosine < 0.9 → keep both."""
    a = _chunk("aaaa-0000-0000-0000-000000000003", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000004", "doc1", "CCC", 0.7, position=2)

    vec_a = [1.0] + [0.0] * 1535
    vec_b = [0.0, 1.0] + [0.0] * 1534  # cosine(a, b) = 0.0

    mock_pt_a = MagicMock(); mock_pt_a.id = "aaaa-0000-0000-0000-000000000003"; mock_pt_a.vector = vec_a
    mock_pt_b = MagicMock(); mock_pt_b.id = "bbbb-0000-0000-0000-000000000004"; mock_pt_b.vector = vec_b
    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[mock_pt_a, mock_pt_b])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000003" in ids
    assert "bbbb-0000-0000-0000-000000000004" in ids


@pytest.mark.asyncio
async def test_dedup_keeps_both_when_positions_far_apart():
    """Positions > 2 apart → skip cosine check entirely, keep both."""
    a = _chunk("aaaa-0000-0000-0000-000000000005", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000006", "doc1", "CCC", 0.7, position=10)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000005" in ids
    assert "bbbb-0000-0000-0000-000000000006" in ids
    # Qdrant should not be called when no close pairs exist
    mock_client.retrieve.assert_not_called()


@pytest.mark.asyncio
async def test_dedup_keeps_both_when_position_is_none():
    """When position is missing, cannot check proximity — keep both chunks."""
    a = _chunk("aaaa-0000-0000-0000-000000000007", "doc1", "CCC", 0.9, position=None)
    b = _chunk("bbbb-0000-0000-0000-000000000008", "doc1", "CCC", 0.7, position=None)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    assert len(result) == 2


# ---------------------------------------------------------------------------
# apply_dedup — per-title cap
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_per_title_cap_drops_third_chunk():
    """Max 2 results per document_title — third is dropped regardless of score."""
    # Three chunks with same title but different document_ids (different translations)
    a = _chunk("aaaa-0000-0000-0000-000000000009", "doc_a", "Summa Theologica", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000010", "doc_b", "Summa Theologica", 0.8, position=50)
    c = _chunk("cccc-0000-0000-0000-000000000011", "doc_c", "Summa Theologica", 0.7, position=100)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b, c])

    assert len(result) == 2
    ids = [r.chunk_id for r in result]
    assert "aaaa-0000-0000-0000-000000000009" in ids
    assert "bbbb-0000-0000-0000-000000000010" in ids
    assert "cccc-0000-0000-0000-000000000011" not in ids


@pytest.mark.asyncio
async def test_per_title_cap_allows_two_different_titles():
    """Different document titles are each allowed up to 2 results."""
    a = _chunk("aaaa-0000-0000-0000-000000000012", "doc1", "Summa", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000013", "doc1", "Summa", 0.8, position=50)
    c = _chunk("cccc-0000-0000-0000-000000000014", "doc2", "Catechism", 0.7, position=1)
    d = _chunk("dddd-0000-0000-0000-000000000015", "doc2", "Catechism", 0.6, position=50)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(return_value=[])

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b, c, d])

    assert len(result) == 4


@pytest.mark.asyncio
async def test_dedup_graceful_on_qdrant_failure():
    """If Qdrant retrieve fails, dedup is skipped but per-title cap still applies."""
    a = _chunk("aaaa-0000-0000-0000-000000000016", "doc1", "CCC", 0.9, position=1)
    b = _chunk("bbbb-0000-0000-0000-000000000017", "doc1", "CCC", 0.7, position=2)

    mock_client = AsyncMock()
    mock_client.retrieve = AsyncMock(side_effect=RuntimeError("Qdrant down"))

    with patch("app.rag.dedup.get_qdrant_client", return_value=mock_client):
        result = await apply_dedup([a, b])

    # Both survive (cosine dedup skipped), per-title cap allows 2
    assert len(result) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd services/api && python -m pytest tests/test_dedup.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.rag.dedup'`

- [ ] **Step 3: Create `services/api/app/rag/dedup.py`**

```python
"""Position+cosine dedup and per-title cap for post-scoring results.

apply_dedup(ranked) drops the lower-scorer in any pair from the same document
where abs(position_a - position_b) <= 2 AND cosine_similarity > 0.9, then
caps results at 2 per document_title. Input must already be sorted descending
by reranker_score (the pipeline's global sort precedes this call).
"""
from __future__ import annotations

import logging
import math

from app.rag.qdrant_client import QDRANT_COLLECTION, get_qdrant_client
from app.rag.rerank import RankedChunk

logger = logging.getLogger(__name__)

_COSINE_THRESHOLD = 0.9
_POSITION_PROXIMITY = 2
_PER_TITLE_CAP = 2


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


async def apply_dedup(ranked: list[RankedChunk]) -> list[RankedChunk]:
    """Drop cosine-close adjacent duplicates and apply per-title cap.

    Assumes `ranked` is already sorted descending by reranker_score.
    """
    # 1. Find pairs within _POSITION_PROXIMITY in the same document
    by_doc: dict[str, list[RankedChunk]] = {}
    for chunk in ranked:
        if chunk.include:
            by_doc.setdefault(chunk.document_id, []).append(chunk)

    close_pairs: list[tuple[str, str]] = []
    for chunks in by_doc.values():
        for i, a in enumerate(chunks):
            for b in chunks[i + 1:]:
                if (
                    a.position is not None
                    and b.position is not None
                    and abs(a.position - b.position) <= _POSITION_PROXIMITY
                ):
                    close_pairs.append((a.chunk_id, b.chunk_id))

    # 2. Fetch vectors for close pairs and compute cosine similarity
    to_drop: set[str] = set()
    if close_pairs:
        close_ids = {cid for pair in close_pairs for cid in pair}
        client = get_qdrant_client()
        if client is not None:
            try:
                points = await client.retrieve(
                    collection_name=QDRANT_COLLECTION,
                    ids=list(close_ids),
                    with_vectors=True,
                )
                vec_map: dict[str, list[float]] = {
                    str(p.id): p.vector
                    for p in points
                    if p.vector is not None
                }
                score_map = {r.chunk_id: r.reranker_score for r in ranked}
                for id_a, id_b in close_pairs:
                    if id_a in to_drop or id_b in to_drop:
                        continue
                    vec_a = vec_map.get(id_a)
                    vec_b = vec_map.get(id_b)
                    if vec_a is None or vec_b is None:
                        continue
                    if _cosine_sim(vec_a, vec_b) > _COSINE_THRESHOLD:
                        drop = (
                            id_a if score_map.get(id_a, 0.0) < score_map.get(id_b, 0.0) else id_b
                        )
                        to_drop.add(drop)
            except Exception as exc:
                logger.warning("apply_dedup: Qdrant vector fetch failed, skipping cosine check: %s", exc)

    # 3. Apply cosine dedup + per-title cap in one pass (input already score-sorted)
    title_counts: dict[str, int] = {}
    final: list[RankedChunk] = []
    for chunk in ranked:
        if not chunk.include or chunk.chunk_id in to_drop:
            continue
        count = title_counts.get(chunk.document_title, 0)
        if count < _PER_TITLE_CAP:
            title_counts[chunk.document_title] = count + 1
            final.append(chunk)
    return final
```

- [ ] **Step 4: Run dedup tests**

```bash
cd services/api && python -m pytest tests/test_dedup.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd services/api && python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/rag/dedup.py services/api/tests/test_dedup.py
git commit -m "feat(rag): add position+cosine dedup and per-title cap in dedup.py"
```

---

## Task 8: Wire `pipeline.py` + remove `expansion_queries` from `retrieve.py`

**Files:**
- Modify: `services/api/app/rag/pipeline.py`
- Modify: `services/api/app/rag/retrieve.py` (remove `expansion_queries` parameter)
- Modify: `services/api/tests/test_retrieve.py` (remove expansion tests)

**Interfaces:**
- Consumes: `score_candidates` from `cross_encoder`, `apply_dedup` from `dedup`, `get_client`/`get_key_for`/`get_semaphore` from `api_keys`
- Produces: updated `run_search_pipeline` and `_hyde_and_embed` — pipeline runs BGE instead of Sonnet, dedup applied before collection guarantee

- [ ] **Step 1: Remove `expansion_queries` from `retrieve_candidates` and its test**

In `services/api/app/rag/retrieve.py`, find `retrieve_candidates`. Remove the `expansion_queries` parameter and all code that uses it:

Remove from function signature:
```python
    expansion_queries: list[str] | None = None,
```

Remove from function body (the two lines that add FTS expansion coroutines):
```python
        for i, eq in enumerate(expansion_queries or []):
            coros.append(_search_fts(pool, collection, user_id, eq, n))
            labels.append(f"fts_expand_{i}")
```

In `services/api/tests/test_retrieve.py`, delete the two tests that test expansion_queries behavior (they will fail once the parameter is removed). Delete these two entire test functions:
- `test_retrieve_candidates_calls_fts_for_each_expansion`
- `test_retrieve_candidates_no_expansion_by_default`

- [ ] **Step 2: Verify retrieve tests pass after removal**

```bash
cd services/api && python -m pytest tests/test_retrieve.py -v
```

Expected: all remaining tests PASS (the two expansion tests are now gone).

- [ ] **Step 3: Rewrite `pipeline.py`**

Replace the entire content of `services/api/app/rag/pipeline.py`:

```python
"""RAG search pipeline — orchestrates HyDE, embedding, retrieval, scoring, and explanation."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

from app.config import settings
from app.db import get_pool
from app.rag.api_keys import get_client, get_key_for, get_semaphore
from app.rag.cross_encoder import score_candidates
from app.rag.dedup import apply_dedup
from app.rag.embed import embed_text
from app.rag.explain import stream_explanation
from app.rag.hyde import generate_hyde_passages
from app.rag.retrieve import retrieve_candidates, ChunkCandidate
from app.rag.rerank import RankedChunk
from app.rag.constants import VALID_COLLECTIONS

logger = logging.getLogger(__name__)


async def _hyde_and_embed(
    query: str,
    col: str,
) -> tuple[str, list[list[float]]]:
    """Generate HyDE passages for one collection then embed them immediately.

    Routes to the correct API key and acquires the key's semaphore for
    concurrency control. Returns (collection, [embedding_vectors]).
    """
    key = get_key_for(col)
    client = get_client(key)
    semaphore = get_semaphore(key)

    passages = await generate_hyde_passages(query, col, client, semaphore)
    if not passages:
        return col, []
    results = await asyncio.gather(*[embed_text(p) for p in passages], return_exceptions=True)
    return col, [v for v in results if not isinstance(v, BaseException)]


async def run_search_pipeline(
    query: str,
    collections: list[str],
    translation: str,
    quota: int,
    user_id: str,
):
    """Async generator yielding SSE-compatible dicts.

    Event types: "status", "chunk", "explanation_delta", "done", "error"
    """
    collections = [c for c in collections if c in VALID_COLLECTIONS]
    if not collections:
        yield {"type": "error", "detail": "No valid collections selected."}
        return

    try:
        _t0 = time.perf_counter()

        # ------------------------------------------------------------------
        # Steps 1+2 — query embedding + per-collection HyDE → embed (parallel)
        # ------------------------------------------------------------------
        all_results = await asyncio.gather(
            embed_text(query),
            *[_hyde_and_embed(query, col) for col in collections],
            return_exceptions=True,
        )

        query_vec_result = all_results[0]
        hyde_embed_results = all_results[1:]

        _t1 = time.perf_counter()
        logger.info("pipeline timing: steps1_2=%.2fs collections=%s", _t1 - _t0, collections)

        if isinstance(query_vec_result, BaseException):
            logger.error("Query embedding failed: %s", query_vec_result)
            yield {"type": "error", "detail": "Embedding failed"}
            return
        query_vec: list[float] = query_vec_result

        per_col_hyde_vec: dict[str, list[float] | None] = {col: None for col in collections}
        per_col_extra_hyde_vecs: dict[str, list[list[float]]] = {col: [] for col in collections}
        for item in hyde_embed_results:
            if isinstance(item, BaseException):
                logger.warning("_hyde_and_embed failed: %s", item)
                continue
            col, vecs = item
            if not vecs:
                continue
            per_col_hyde_vec[col] = vecs[0]
            per_col_extra_hyde_vecs[col] = vecs[1:]

        # ------------------------------------------------------------------
        # Step 3 — Per-collection retrieval (parallel)
        # ------------------------------------------------------------------
        yield {"type": "status", "phase": "searching", "collections": collections}
        retrieve_tasks = [
            retrieve_candidates(
                query, query_vec, per_col_hyde_vec[col],
                per_col_extra_hyde_vecs[col],
                col, quota, user_id,
            )
            for col in collections
        ]
        retrieve_results = await asyncio.gather(*retrieve_tasks, return_exceptions=True)

        per_collection_candidates: list[list[ChunkCandidate]] = []
        for col, result in zip(collections, retrieve_results):
            if isinstance(result, BaseException):
                logger.warning("retrieve_candidates failed for '%s': %s", col, result)
            else:
                per_collection_candidates.append(result)

        _t3 = time.perf_counter()
        logger.info("pipeline timing: step3(retrieval)=%.2fs", _t3 - _t1)

        if not per_collection_candidates:
            yield {"type": "done", "search_id": str(uuid.uuid4()), "result_count": 0}
            return

        # ------------------------------------------------------------------
        # Step 4 — BGE cross-encoder scoring per collection (parallel, in executor)
        # ------------------------------------------------------------------
        yield {"type": "status", "phase": "ranking"}
        loop = asyncio.get_event_loop()
        score_results = await asyncio.gather(*[
            loop.run_in_executor(None, score_candidates, col_candidates, query)
            for col_candidates in per_collection_candidates
        ], return_exceptions=True)

        _t4 = time.perf_counter()
        logger.info("pipeline timing: step4(cross_encoder)=%.2fs", _t4 - _t3)

        all_scored: list[RankedChunk] = []
        for result in score_results:
            if isinstance(result, BaseException):
                logger.warning("score_candidates failed: %s", result)
            else:
                all_scored.extend(result)

        # ------------------------------------------------------------------
        # Step 5 — Global sort → dedup → per-collection guarantee + quota
        # ------------------------------------------------------------------
        _GUARANTEE_MIN_SCORE = 0.25

        all_sorted = sorted(all_scored, key=lambda c: c.reranker_score, reverse=True)

        # 5b. Combined dedup: position proximity + cosine threshold + per-title cap
        deduped = await apply_dedup(all_sorted)

        # 5c. Collection guarantee: inject best chunk for any selected collection
        #     absent after dedup, if it clears the minimum score threshold.
        represented = {r.collection for r in deduped}
        for col in collections:
            if col not in represented:
                col_best = next(
                    (r for r in all_sorted
                     if r.collection == col and r.reranker_score >= _GUARANTEE_MIN_SCORE),
                    None,
                )
                if col_best:
                    deduped.append(col_best)

        # 5d. Per-collection quota cap
        col_counts: dict[str, int] = {}
        final_results: list[RankedChunk] = []
        for c in deduped:
            col_counts[c.collection] = col_counts.get(c.collection, 0) + 1
            if col_counts[c.collection] <= quota:
                final_results.append(c)

        # ------------------------------------------------------------------
        # Step 6 — Yield chunk events
        # ------------------------------------------------------------------
        for chunk in final_results:
            yield {
                "type": "chunk",
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "source": {
                    "collection": chunk.collection,
                    "document_title": chunk.document_title,
                    "author": chunk.author,
                    "reference": chunk.reference,
                    "document_id": chunk.document_id,
                    "anchor": chunk.anchor,
                },
                "reranker_score": chunk.reranker_score,
            }

        # ------------------------------------------------------------------
        # Step 7 — Persist search + retrievals to DB
        # ------------------------------------------------------------------
        pool = get_pool()
        if pool is None:
            logger.error("DB pool not available, skipping persistence")
            yield {"type": "done", "search_id": None, "result_count": len(final_results)}
            return

        search_id = str(uuid.uuid4())
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO searches (id, user_id, query, filters, result_count) VALUES ($1,$2,$3,$4::jsonb,$5)",
                    uuid.UUID(search_id),
                    uuid.UUID(user_id),
                    query,
                    json.dumps({"collections": collections, "translation": translation, "quota": quota}),
                    len(final_results),
                )
                if final_results:
                    await conn.executemany(
                        "INSERT INTO retrievals (id, search_id, chunk_id, rank, reranker_score) VALUES ($1,$2,$3,$4,$5)",
                        [
                            (uuid.uuid4(), uuid.UUID(search_id), uuid.UUID(chunk.chunk_id), rank, chunk.reranker_score)
                            for rank, chunk in enumerate(final_results)
                        ],
                    )

        _t7 = time.perf_counter()
        logger.info(
            "pipeline timing: step7(db)=%.2fs total=%.2fs results=%d",
            _t7 - _t4, _t7 - _t0, len(final_results),
        )

        # ------------------------------------------------------------------
        # Step 8 — Yield done
        # ------------------------------------------------------------------
        yield {"type": "done", "search_id": search_id, "result_count": len(final_results)}

        # ------------------------------------------------------------------
        # Step 9 — Sequential streaming explanations
        # ------------------------------------------------------------------
        for chunk in final_results:
            accumulated_text = ""
            try:
                async for delta in stream_explanation(
                    chunk.content, chunk.reference, chunk.collection, query
                ):
                    accumulated_text += delta
                    yield {"type": "explanation_delta", "chunk_id": chunk.chunk_id, "delta": delta}
            except Exception as exc:
                logger.warning("explanation error for chunk %s: %s", chunk.chunk_id, exc)

            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE retrievals SET explanation = $1 WHERE search_id = $2 AND chunk_id = $3",
                    accumulated_text[:2000],
                    uuid.UUID(search_id),
                    uuid.UUID(chunk.chunk_id),
                )

    except Exception:
        logger.exception("run_search_pipeline unhandled error")
        yield {"type": "error", "detail": "Search failed. Please try again."}
```

- [ ] **Step 4: Run full test suite**

```bash
cd services/api && python -m pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/rag/pipeline.py services/api/app/rag/retrieve.py services/api/tests/test_retrieve.py
git commit -m "feat(pipeline): wire BGE cross-encoder, api key routing, dedup; remove expand_query"
```

---

## Task 9: `main.py` lifecycle swap + delete dead files

**Files:**
- Modify: `services/api/app/main.py`
- Delete: `services/api/app/rag/query_expand.py`
- Delete: `services/api/tests/test_query_expand.py`

**Interfaces:**
- Consumes: `init_cross_encoder`, `close_cross_encoder` from `cross_encoder`; `init_api_keys`, `close_api_keys` from `api_keys`
- Produces: server starts cleanly with log line `"Cross-encoder loaded: BAAI/bge-reranker-v2-m3"`

- [ ] **Step 1: Update `main.py` lifecycle**

Open `services/api/app/main.py`. Replace the import block that currently contains:

```python
from app.rag.hyde import close_hyde, init_hyde
from app.rag.query_expand import close_query_expand, init_query_expand
from app.rag.qdrant_client import close_qdrant, init_qdrant
from app.rag.rerank import close_rerank, init_rerank
```

With:

```python
from app.rag.api_keys import close_api_keys, init_api_keys
from app.rag.cross_encoder import close_cross_encoder, init_cross_encoder
from app.rag.qdrant_client import close_qdrant, init_qdrant
```

Replace the startup block inside `lifespan` that currently calls:

```python
    init_hyde()
    init_query_expand()
    init_qdrant()
    init_rerank()
```

With:

```python
    init_qdrant()
    init_cross_encoder()
    init_api_keys()
```

Replace the shutdown block that currently calls:

```python
    await close_hyde()
    await close_query_expand()
    await close_qdrant()
    await close_rerank()
```

With:

```python
    await close_api_keys()
    await close_cross_encoder()
    await close_qdrant()
```

- [ ] **Step 2: Delete dead files**

```bash
rm services/api/app/rag/query_expand.py
rm services/api/tests/test_query_expand.py
```

- [ ] **Step 3: Run full test suite**

```bash
cd services/api && python -m pytest tests/ -v
```

Expected: all tests PASS. The deleted `test_query_expand.py` no longer runs; no other tests import from `query_expand`.

- [ ] **Step 4: Start the dev server and verify startup log**

```bash
cd services/api && uvicorn app.main:app --reload
```

Expected log output includes:
```
INFO  Cross-encoder loaded: BAAI/bge-reranker-v2-m3
INFO  api_keys: A=...XXXX B=...XXXX C=...XXXX D=...XXXX
```

Ctrl+C to stop.

- [ ] **Step 5: Run a search end-to-end**

In a second terminal with the server running:

```bash
curl -s -N -X POST http://localhost:8000/v1/search \
  -H "Authorization: Bearer <YOUR_JWT>" \
  -H "Content-Type: application/json" \
  -d '{"query":"what is the Eucharist","filters":{"collections":["catechism"]},"quota":2}' \
  | head -40
```

Expected: SSE stream with `event: status`, one or more `event: chunk` lines, `event: done`. No `expand_query` calls in server logs.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/main.py
git commit -m "feat(main): swap lifecycle to cross-encoder + api_keys; remove hyde/rerank/query_expand lifecycle"
```

---

## Self-Review

**Spec coverage:**

| V3 pre-enrichment feature | Task |
|---|---|
| BGE cross-encoder replaces Sonnet | Task 6 + 8 |
| Remove `expand_query` | Task 8 + 9 |
| `position` field plumbing | Task 2 + 3 |
| `annotation` field plumbing (stub) | Task 3 |
| API key isolation (4 keys, semaphores) | Task 4 |
| `hyde.py` client injection | Task 5 |
| Combined position+cosine dedup | Task 7 |
| Per-title cap (max 2) | Task 7 |
| Per-collection quota cap retained | Task 8 |
| Collection guarantee retained | Task 8 |
| `pyproject.toml` dependency | Task 1 |
| Dockerfile model pre-bake | Task 1 |
| `main.py` lifecycle swap | Task 9 |
| Delete dead files | Task 9 |

**Placeholder scan:** No TBDs, no "implement later", all code steps are complete.

**Type consistency check:**
- `ChunkCandidate.position: int | None` defined Task 3 → used in Task 7 (`_cosine_sim` pairs) ✓
- `ChunkCandidate.annotation: dict | None` defined Task 3 → read in Task 6 (`cross_encoder.py`) ✓
- `RankedChunk.position: int | None` defined Task 2 → populated Task 6, read Task 7 ✓
- `score_candidates(candidates, query)` defined Task 6 → called Task 8 with `run_in_executor` ✓
- `apply_dedup(ranked)` defined Task 7 → called Task 8 after global sort ✓
- `generate_hyde_passages(query, collection, client, semaphore)` defined Task 5 → called Task 8 via `_hyde_and_embed` ✓
- `get_key_for`, `get_client`, `get_semaphore` defined Task 4 → used Task 8 in `_hyde_and_embed` ✓
