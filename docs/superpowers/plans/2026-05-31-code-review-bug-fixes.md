# Code Review Bug Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 9 confirmed/plausible bugs from a full-codebase code review — 2 production-breaking, 2 security, and 5 functional/reliability issues — without altering any public API contracts, data models, or existing behaviour.

**Architecture:** Each fix is the smallest correct change that addresses the root cause. No refactoring, no abstractions beyond the fix. Tasks are ordered most-to-least severe and are mutually independent (no shared state, no ordering dependency) except Task 4, which depends on Task 0 for test infrastructure.

**Tech Stack:** FastAPI, asyncpg ≥ 0.29, Pydantic v2, pytest ≥ 8, pytest-asyncio ≥ 0.23, Next.js 15 App Router, TypeScript 5

---

## File Map

| Task | Files Modified / Created |
|------|--------------------------|
| 0 | `services/api/pyproject.toml`, `services/api/tests/__init__.py`, `services/api/tests/conftest.py` |
| 1 | `apps/web/src/app/v1/[...path]/route.ts` |
| 2 | `services/api/app/rag/pipeline.py` |
| 3 | `services/api/app/main.py` |
| 4 | `services/api/app/routes/search.py`, `services/api/tests/test_search_routes.py` |
| 5 | `services/api/app/rag/rerank.py`, `services/api/tests/test_rerank.py` |
| 6 | `services/api/app/routes/sessions.py`, `services/api/tests/test_sessions_routes.py` |
| 7 | `supabase/migrations/0009_backfill_canon_law_preferences.sql` |
| 8 | `apps/web/src/components/search/SearchPage.tsx` |

---

## Task 0: Set Up Backend Test Infrastructure

**Purpose:** Create the minimal pytest environment that Tasks 4–6 depend on. There are currently no test files in `services/api/`.

**Files:**
- Modify: `services/api/pyproject.toml`
- Create: `services/api/tests/__init__.py`
- Create: `services/api/tests/conftest.py`

- [ ] **Step 1: Add pytest dev dependencies and pytest config to pyproject.toml**

Append the following to `services/api/pyproject.toml` (after the existing `[tool.hatch.build.targets.wheel]` section):

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Install dev dependencies**

```bash
cd services/api && pip install -e ".[dev]"
```

Expected: installs `pytest` and `pytest-asyncio` without errors.

- [ ] **Step 3: Create empty test package**

Create `services/api/tests/__init__.py` as an empty file.

- [ ] **Step 4: Create conftest.py**

Create `services/api/tests/conftest.py`:

```python
# Shared fixtures will be added here as needed.
```

- [ ] **Step 5: Confirm pytest discovers tests**

```bash
cd services/api && python -m pytest --collect-only
```

Expected: `no tests ran` — no errors, no import failures.

- [ ] **Step 6: Commit**

```bash
git add services/api/pyproject.toml services/api/tests/
git commit -m "chore(api): add pytest + pytest-asyncio dev dependencies"
```

---

## Task 1: Fix Next.js Proxy — Missing DELETE/PUT Exports and Dropped Retry-After Header

**Bugs fixed:**
- **#1 (Production-breaking)** — The proxy exports only `GET` and `POST`. Every `DELETE /v1/bookmarks/{id}` call (bookmark deletion) and every `PUT /v1/preferences` call (preferences save) hits a `405 Method Not Allowed` from Next.js and never reaches FastAPI. Bookmark deletion and preference persistence are silently broken for all users.
- **#5 (Functional)** — The proxy builds a minimal `responseHeaders` object that does not forward the upstream `Retry-After` header. The rate-limit modal therefore receives `null` and renders "retry in NaN seconds".

**File:** `apps/web/src/app/v1/[...path]/route.ts`

- [ ] **Step 1: Add DELETE/PUT exports and forward Retry-After header**

Replace the full content of `apps/web/src/app/v1/[...path]/route.ts` with:

```typescript
import { NextRequest } from "next/server";

const API_URL = process.env.API_URL;

async function proxy(req: NextRequest): Promise<Response> {
  if (!API_URL) {
    return new Response(JSON.stringify({ detail: "API unavailable" }), {
      status: 503,
      headers: { "content-type": "application/json" },
    });
  }

  const url = new URL(req.url);
  const target = `${API_URL}${url.pathname}${url.search}`;

  // Forward only the headers the backend needs.
  // Never forward Host, Cookie, or other ambient browser headers.
  const headers = new Headers();
  const authorization = req.headers.get("authorization");
  const contentType = req.headers.get("content-type");
  if (authorization) headers.set("authorization", authorization);
  if (contentType) headers.set("content-type", contentType);
  if (process.env.INTERNAL_API_SECRET) {
    headers.set("x-internal-secret", process.env.INTERNAL_API_SECRET);
  }

  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body: req.method !== "GET" && req.method !== "HEAD" ? req.body : undefined,
    // Required for streaming request bodies in Node.js fetch
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ...(req.method !== "GET" && req.method !== "HEAD" ? { duplex: "half" } as any : {}),
  });

  // Pipe upstream body directly — no buffering — so SSE tokens reach the
  // browser as they arrive instead of being held until the stream closes.
  const responseHeaders = new Headers({
    "content-type": upstream.headers.get("content-type") ?? "application/json",
    "cache-control": "no-cache",
    "x-accel-buffering": "no",
  });

  // Forward Retry-After so the rate-limit modal can display an accurate countdown.
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) responseHeaders.set("retry-after", retryAfter);

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
```

- [ ] **Step 2: Verify TypeScript compiles cleanly**

```bash
cd apps/web && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Manual smoke test — bookmark deletion**

Start `npm run dev`. Log in. Add a bookmark to a chunk. Click delete. Confirm the bookmark disappears from the UI and does not reappear on reload.

- [ ] **Step 4: Manual smoke test — preferences save**

Toggle a collection off. Reload the page. Confirm the collection remains off (the preference was persisted).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/app/v1/[...path]/route.ts
git commit -m "fix(proxy): export DELETE + PUT handlers; forward Retry-After header"
```

---

## Task 2: Fix asyncpg jsonb Serialization in Search Pipeline

**Bug fixed:**
- **#2 (Production-breaking)** — The `INSERT INTO searches` at pipeline.py line 153 passes a raw Python `dict` as the `$4` parameter for the `searches.filters` column (type `jsonb`). asyncpg 0.29 cannot encode a Python `dict` as a native jsonb binary value without an explicit type codec. The query raises `asyncpg.exceptions.DataError` at runtime, is caught by the outer `except Exception`, and the pipeline yields `{"type": "error"}` instead of persisting the search row. As a result, `GET /v1/searches` always returns an empty list and search history is permanently broken.

**Fix:** Serialize the dict with `json.dumps()` and use `$4::jsonb` in the SQL so PostgreSQL performs the text→jsonb cast server-side. This is the smallest change possible and has zero blast radius beyond this one INSERT.

**File:** `services/api/app/rag/pipeline.py`

- [ ] **Step 1: Add `import json` to the imports block**

In `services/api/app/rag/pipeline.py`, the imports currently begin with:

```python
from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
```

Change to:

```python
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
```

- [ ] **Step 2: Fix the INSERT to serialize the dict and cast to jsonb**

In `services/api/app/rag/pipeline.py`, find the INSERT block (~line 148):

```python
                await conn.execute(
                    "INSERT INTO searches (id, user_id, query, filters, result_count) VALUES ($1,$2,$3,$4,$5)",
                    uuid.UUID(search_id),
                    uuid.UUID(user_id),
                    query,
                    {"collections": collections, "translation": translation, "quota": quota},
                    len(final_results),
                )
```

Replace with:

```python
                await conn.execute(
                    "INSERT INTO searches (id, user_id, query, filters, result_count) VALUES ($1,$2,$3,$4::jsonb,$5)",
                    uuid.UUID(search_id),
                    uuid.UUID(user_id),
                    query,
                    json.dumps({"collections": collections, "translation": translation, "quota": quota}),
                    len(final_results),
                )
```

- [ ] **Step 3: Manual verification**

With the backend running against a real database, perform a search from the frontend, then call `GET /v1/searches`:

```bash
# Run a search
curl -X POST http://localhost:8000/v1/search \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"query":"grace","filters":{"collections":["catechism"],"translation":"CPDV"},"quota":3}' \
  --no-buffer

# Check history (should return the search just performed)
curl http://localhost:8000/v1/searches \
  -H "Authorization: Bearer <your-token>"
```

Expected: `GET /v1/searches` returns a non-empty list containing the search just performed. Before this fix it always returned `{"searches":[]}`.

- [ ] **Step 4: Commit**

```bash
git add services/api/app/rag/pipeline.py
git commit -m "fix(pipeline): serialize filters dict with json.dumps for asyncpg jsonb INSERT"
```

---

## Task 3: Harden InternalSecretMiddleware Startup Guard

**Bug fixed:**
- **#3 (Security)** — `InternalSecretMiddleware` unconditionally passes all requests through when `INTERNAL_API_SECRET` is not set. The existing startup check only raises in `production`; Railway staging deployments (which also have a public URL) silently have no network-layer protection if the secret is omitted.

**Fix:** Extend the startup `RuntimeError` to all environments where `APP_ENV` is not `"development"`. Local dev continues to work without a secret; any Railway deployment (staging, preview, production) that omits the secret fails fast at boot before accepting a single request.

**File:** `services/api/app/main.py`

- [ ] **Step 1: Extend the startup guard to all non-development environments**

In `services/api/app/main.py`, find the secret check in the `lifespan` function (~line 36):

```python
    if not settings.internal_api_secret:
        logger.warning("INTERNAL_API_SECRET is not set — all requests will bypass the secret check")
        if settings.app_env == "production":
            raise RuntimeError("INTERNAL_API_SECRET must be set in production")
```

Replace with:

```python
    if not settings.internal_api_secret:
        logger.warning("INTERNAL_API_SECRET is not set — all requests will bypass the secret check")
        if settings.app_env != "development":
            raise RuntimeError(
                "INTERNAL_API_SECRET must be set in all non-development environments. "
                "Set APP_ENV=development to disable this check locally."
            )
```

- [ ] **Step 2: Verify local dev still starts without the secret**

```bash
cd services/api && APP_ENV=development uvicorn app.main:app --reload
```

Expected: server starts successfully, logs the warning, no error.

- [ ] **Step 3: Verify non-dev environments fail fast without the secret**

```bash
cd services/api && APP_ENV=staging uvicorn app.main:app
```

Expected: raises `RuntimeError: INTERNAL_API_SECRET must be set in all non-development environments.` and exits before the port opens.

- [ ] **Step 4: Commit**

```bash
git add services/api/app/main.py
git commit -m "fix(security): require INTERNAL_API_SECRET in all non-development environments"
```

---

## Task 4: Rate-Limit After Collection Validation + Daily Retry-After Header

**Bugs fixed:**
- **#4 (Security/Functional)** — FastAPI resolves all `Depends()` before the handler body. `check_search_rate_limit` is a dependency, so it increments the user's rate/quota counter before the collection-validity check in the handler body can reject the request. A client that sends only invalid collections in `filters.collections` drains the user's daily quota (30 searches) with zero successful searches.
- **#5 (Functional — backend half)** — The daily-quota `HTTPException` at line ~75 of `search.py` has no `headers` argument, so no `Retry-After` header reaches the proxy or client for daily limit hits.

**Fix strategy for #4:** Extract collection validation into a new `_validate_collections` dependency and make `check_search_rate_limit` depend on it. FastAPI's dependency graph then guarantees validation runs first; invalid-collection requests get a 400 before the counter is touched. FastAPI deduplicates `_validate_collections` within a single request, so it runs only once even though both the rate-limit dep and the endpoint handler reference it.

**File:** `services/api/app/routes/search.py`

**Requires:** Task 0 (pytest infrastructure)

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/test_search_routes.py`:

```python
"""Tests for _validate_collections dependency in search routes."""
import pytest
from fastapi import HTTPException

from app.models.search import SearchFilters, SearchRequest
from app.routes.search import _validate_collections


@pytest.mark.asyncio
async def test_validate_collections_returns_valid_subset():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(collections=["bible", "not-a-collection"], translation="CPDV"),
        quota=3,
    )
    result = await _validate_collections(body)
    assert result == ["bible"]


@pytest.mark.asyncio
async def test_validate_collections_raises_400_when_all_invalid():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(collections=["not-a-collection", "also-invalid"], translation="CPDV"),
        quota=3,
    )
    with pytest.raises(HTTPException) as exc_info:
        await _validate_collections(body)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_collections_raises_400_when_empty():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(collections=[], translation="CPDV"),
        quota=3,
    )
    with pytest.raises(HTTPException) as exc_info:
        await _validate_collections(body)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_collections_accepts_all_valid():
    body = SearchRequest(
        query="grace",
        filters=SearchFilters(
            collections=["bible", "catechism", "church-fathers", "encyclicals", "saints", "canon-law"],
            translation="CPDV",
        ),
        quota=3,
    )
    result = await _validate_collections(body)
    assert set(result) == {"bible", "catechism", "church-fathers", "encyclicals", "saints", "canon-law"}
```

- [ ] **Step 2: Run the failing tests**

```bash
cd services/api && python -m pytest tests/test_search_routes.py -v
```

Expected: `ImportError` or `AttributeError` — `_validate_collections` does not exist yet.

- [ ] **Step 3a: Add `import datetime` to the top of search.py**

In `services/api/app/routes/search.py`, the current imports are:

```python
import json
import logging
import uuid
```

Change to:

```python
import datetime
import json
import logging
import uuid
```

- [ ] **Step 3b: Add `_validate_collections` before `check_search_rate_limit`**

In `services/api/app/routes/search.py`, insert the following function immediately after the `_VALID_TRANSLATIONS` constant (~line 27) and before `check_search_rate_limit`:

```python
async def _validate_collections(body: SearchRequest) -> list[str]:
    """Validate collection names and return the allowed subset.

    Declared as a dependency so that requests with only invalid collections
    are rejected before the rate-limit counter is incremented.
    """
    valid = [c for c in body.filters.collections if c in _VALID_COLLECTIONS]
    if not valid:
        raise HTTPException(
            status_code=400,
            detail=f"No valid collections specified. Valid values: {sorted(_VALID_COLLECTIONS)}",
        )
    return valid
```

- [ ] **Step 3c: Update `check_search_rate_limit` to depend on `_validate_collections` and add daily Retry-After**

Replace the existing `check_search_rate_limit` function with:

```python
async def check_search_rate_limit(
    user: AuthUser = Depends(get_current_user),
    _valid: list[str] = Depends(_validate_collections),
) -> None:
    """Rate limit for V2 search endpoints (stricter than V1 chat).

    Depends on _validate_collections so that invalid-collection requests
    are rejected with 400 before the counter is incremented.

    TODO: Currently shares the same user_usage counters (rate_count / quota_count)
    as V1 chat. Add search_rate_count / search_quota_count columns in a future
    migration so that chat and search quotas are tracked independently.
    """
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO user_usage (user_id, rate_window_start, rate_count, quota_date, quota_count)
            VALUES ($1, now(), 1, current_date, 1)
            ON CONFLICT (user_id) DO UPDATE SET
                rate_window_start = CASE
                    WHEN now() - user_usage.rate_window_start >= INTERVAL '60 seconds'
                    THEN now() ELSE user_usage.rate_window_start END,
                rate_count = CASE
                    WHEN now() - user_usage.rate_window_start >= INTERVAL '60 seconds'
                    THEN 1 ELSE user_usage.rate_count + 1 END,
                quota_date = current_date,
                quota_count = CASE
                    WHEN user_usage.quota_date < current_date
                    THEN 1 ELSE user_usage.quota_count + 1 END
            RETURNING rate_count, quota_count
            """,
            user.user_id,
        )
    except Exception as exc:
        logger.error("search rate_limit check failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    if row["rate_count"] > settings.rate_limit_search_per_minute:
        raise HTTPException(
            status_code=429,
            detail="Search rate limit reached. Try again in a moment.",
            headers={"Retry-After": "60"},
        )
    if row["quota_count"] > settings.daily_search_quota:
        now = datetime.datetime.now(datetime.timezone.utc)
        midnight = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        retry_after = str(max(1, int((midnight - now).total_seconds())))
        raise HTTPException(
            status_code=429,
            detail="Daily search limit reached. Try again tomorrow.",
            headers={"Retry-After": retry_after},
        )
```

- [ ] **Step 3d: Update the `search` endpoint to use the dependency-injected `valid_collections`**

Replace the existing `search` endpoint signature and its collection-validation block:

```python
@router.post("/search")
async def search(
    body: SearchRequest,
    user: AuthUser = Depends(get_current_user),
    _: None = Depends(check_search_rate_limit),
) -> StreamingResponse:
    """Stream RAG search results as Server-Sent Events."""
    # Filter out invalid collection values; reject if none remain
    valid_collections = [c for c in body.filters.collections if c in _VALID_COLLECTIONS]
    if not valid_collections:
        raise HTTPException(
            status_code=400,
            detail=f"No valid collections specified. Valid values: {sorted(_VALID_COLLECTIONS)}",
        )

    # Validate translation; default to "CPDV" if invalid (non-fatal)
    translation = body.filters.translation if body.filters.translation in _VALID_TRANSLATIONS else "CPDV"
```

With:

```python
@router.post("/search")
async def search(
    body: SearchRequest,
    user: AuthUser = Depends(get_current_user),
    valid_collections: list[str] = Depends(_validate_collections),
    _: None = Depends(check_search_rate_limit),
) -> StreamingResponse:
    """Stream RAG search results as Server-Sent Events."""
    # Validate translation; default to "CPDV" if invalid (non-fatal)
    translation = body.filters.translation if body.filters.translation in _VALID_TRANSLATIONS else "CPDV"
```

The rest of the `search` function body is unchanged — `valid_collections` is now an injected parameter rather than a local variable.

- [ ] **Step 4: Run tests (expect pass)**

```bash
cd services/api && python -m pytest tests/test_search_routes.py -v
```

Expected:
```
PASSED tests/test_search_routes.py::test_validate_collections_returns_valid_subset
PASSED tests/test_search_routes.py::test_validate_collections_raises_400_when_all_invalid
PASSED tests/test_search_routes.py::test_validate_collections_raises_400_when_empty
PASSED tests/test_search_routes.py::test_validate_collections_accepts_all_valid
```

- [ ] **Step 5: Commit**

```bash
git add services/api/app/routes/search.py services/api/tests/test_search_routes.py
git commit -m "fix(search): validate collections before rate-limit dep; add Retry-After to daily 429"
```

---

## Task 5: Harden Rerank Score Parsing Against LLM Formatting Errors

**Bug fixed:**
- **#6 (Reliability)** — If Claude Haiku returns a JSON item where `"score"` is `null` or a non-numeric string (e.g. `"high"`), `float(item.get("score", 0.0))` raises `TypeError` or `ValueError`. This exception propagates out of the per-item loop, escapes `rerank_collection`, and is caught by `pipeline.py`'s `asyncio.gather(return_exceptions=True)`, which logs a warning and drops **all** chunks from that collection silently. The entire collection's results vanish from the search output with no user-visible error.

**Fix:** Wrap the `float()` call in a per-item `try/except`. A bad score for one item defaults to `0.0` and logs a warning; all other items in the batch continue normally.

**File:** `services/api/app/rag/rerank.py`

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/test_rerank.py`:

```python
"""Tests for per-item score error handling in rerank_collection."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.rag.rerank import rerank_collection
from app.rag.retrieve import ChunkCandidate


def _make_candidate(chunk_id: str) -> ChunkCandidate:
    return ChunkCandidate(
        chunk_id=chunk_id,
        content="Sample content about grace",
        reference="Gen 1:1",
        collection="bible",
        document_id="00000000-0000-0000-0000-000000000099",
        document_title="Genesis",
        author=None,
        rrf_score=0.5,
    )


@pytest.mark.asyncio
async def test_rerank_null_score_defaults_to_zero_not_dropped():
    """A null score from the LLM should default to 0.0; the chunk must still appear in results."""
    chunk_id = "00000000-0000-0000-0000-000000000001"
    candidate = _make_candidate(chunk_id)
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text=f'[{{"chunk_id": "{chunk_id}", "score": null}}]')
    ]

    with patch("app.rag.rerank._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await rerank_collection([candidate], "grace", quota=3)

    assert len(result) == 1
    assert result[0].chunk_id == chunk_id
    assert result[0].reranker_score == 0.0


@pytest.mark.asyncio
async def test_rerank_string_score_defaults_to_zero_not_dropped():
    """A non-numeric string score like 'high' should default to 0.0; the chunk must still appear."""
    chunk_id = "00000000-0000-0000-0000-000000000002"
    candidate = _make_candidate(chunk_id)
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text=f'[{{"chunk_id": "{chunk_id}", "score": "high"}}]')
    ]

    with patch("app.rag.rerank._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await rerank_collection([candidate], "grace", quota=3)

    assert len(result) == 1
    assert result[0].chunk_id == chunk_id
    assert result[0].reranker_score == 0.0


@pytest.mark.asyncio
async def test_rerank_bad_score_does_not_affect_other_chunks():
    """A bad score for one chunk must not drop the other chunks in the same batch."""
    bad_id = "00000000-0000-0000-0000-000000000003"
    good_id = "00000000-0000-0000-0000-000000000004"
    candidates = [_make_candidate(bad_id), _make_candidate(good_id)]
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text=f'[{{"chunk_id": "{bad_id}", "score": null}}, {{"chunk_id": "{good_id}", "score": 0.9}}]'
        )
    ]

    with patch("app.rag.rerank._client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await rerank_collection(candidates, "grace", quota=3)

    result_ids = {r.chunk_id for r in result}
    assert bad_id in result_ids
    assert good_id in result_ids

    good_chunk = next(r for r in result if r.chunk_id == good_id)
    assert good_chunk.reranker_score == pytest.approx(0.9)
```

- [ ] **Step 2: Run the failing tests**

```bash
cd services/api && python -m pytest tests/test_rerank.py -v
```

Expected: `FAILED` — `test_rerank_null_score_defaults_to_zero_not_dropped` raises `TypeError: float() argument must be a string or a number, not 'NoneType'`.

- [ ] **Step 3: Apply the fix in rerank.py**

In `services/api/app/rag/rerank.py`, find the score assignment (~line 118):

```python
        score = float(item.get("score", 0.0))
```

Replace with:

```python
        try:
            score = float(item.get("score", 0.0))
        except (TypeError, ValueError):
            logger.warning(
                "rerank_collection: non-numeric score %r for chunk_id '%s'; defaulting to 0.0",
                item.get("score"),
                chunk_id,
            )
            score = 0.0
```

- [ ] **Step 4: Run tests (expect pass)**

```bash
cd services/api && python -m pytest tests/test_rerank.py -v
```

Expected:
```
PASSED tests/test_rerank.py::test_rerank_null_score_defaults_to_zero_not_dropped
PASSED tests/test_rerank.py::test_rerank_string_score_defaults_to_zero_not_dropped
PASSED tests/test_rerank.py::test_rerank_bad_score_does_not_affect_other_chunks
```

- [ ] **Step 5: Commit**

```bash
git add services/api/app/rag/rerank.py services/api/tests/test_rerank.py
git commit -m "fix(rerank): catch TypeError/ValueError on non-numeric LLM score; default to 0.0"
```

---

## Task 6: Add Error Handling to Sessions Route

**Bug fixed:**
- **#7 (Reliability)** — `sessions.py` is the only route file that has no `try/except` around `pool.acquire()` calls. Every other route returns a sanitized `503` on DB errors; `sessions.py` lets asyncpg exceptions propagate as unhandled `500` responses that may include internal connection details in the response body.

**File:** `services/api/app/routes/sessions.py`

The original `500, "Database not available"` status is also corrected to `503, "Service temporarily unavailable"` to match every other route.

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/test_sessions_routes.py`:

```python
"""Tests that DB errors in sessions routes return a sanitized 503."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.routes.sessions import router
from app.deps.auth import get_current_user
from app.models.auth import AuthUser


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/v1")

    async def _fake_user() -> AuthUser:
        return AuthUser(user_id="00000000-0000-0000-0000-000000000001")

    app.dependency_overrides[get_current_user] = _fake_user
    return app


def test_list_sessions_db_error_returns_503():
    app = _make_app()
    client = TestClient(app, raise_server_exceptions=False)

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(side_effect=Exception("asyncpg: pool exhausted"))
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("app.routes.sessions.get_pool") as mock_get_pool:
        mock_pool = MagicMock()
        mock_pool.acquire.return_value = mock_cm
        mock_get_pool.return_value = mock_pool

        response = client.get("/v1/sessions")

    assert response.status_code == 503
    body = response.json()
    assert body["detail"] == "Service temporarily unavailable"
    assert "asyncpg" not in response.text


def test_list_sessions_no_pool_returns_503():
    app = _make_app()
    client = TestClient(app, raise_server_exceptions=False)

    with patch("app.routes.sessions.get_pool", return_value=None):
        response = client.get("/v1/sessions")

    assert response.status_code == 503
```

- [ ] **Step 2: Run the failing tests**

```bash
cd services/api && python -m pytest tests/test_sessions_routes.py -v
```

Expected: `FAILED` — currently the DB error propagates as a raw 500 (or the test assertion for `asyncpg` not being in the response body fails).

- [ ] **Step 3: Replace sessions.py with error-handled version**

Replace the full content of `services/api/app/routes/sessions.py` with:

```python
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser

logger = logging.getLogger(__name__)

router = APIRouter()


class SessionSummary(BaseModel):
    id: str
    title: str | None
    updated_at: str


class SessionsResponse(BaseModel):
    sessions: list[SessionSummary]


class MessageItem(BaseModel):
    role: str
    content: str


class SessionMessagesResponse(BaseModel):
    messages: list[MessageItem]


@router.get("/sessions", response_model=SessionsResponse)
async def list_sessions(
    user: AuthUser = Depends(get_current_user),
) -> SessionsResponse:
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select id, title, updated_at
                from chat_sessions
                where user_id = $1
                order by updated_at desc
                limit 50
                """,
                user.user_id,
            )
    except Exception as exc:
        logger.error("list_sessions query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return SessionsResponse(
        sessions=[
            SessionSummary(
                id=str(r["id"]),
                title=r["title"],
                updated_at=r["updated_at"].isoformat(),
            )
            for r in rows
        ]
    )


@router.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_session_messages(
    session_id: UUID,
    user: AuthUser = Depends(get_current_user),
) -> SessionMessagesResponse:
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        async with pool.acquire() as conn:
            exists = await conn.fetchval(
                "select 1 from chat_sessions where id = $1 and user_id = $2",
                session_id,
                user.user_id,
            )
            if not exists:
                raise HTTPException(status_code=404, detail="Session not found")

            rows = await conn.fetch(
                """
                select role, content
                from chat_messages
                where session_id = $1
                order by created_at asc
                """,
                session_id,
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_session_messages query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    return SessionMessagesResponse(
        messages=[MessageItem(role=r["role"], content=r["content"]) for r in rows]
    )
```

- [ ] **Step 4: Run tests (expect pass)**

```bash
cd services/api && python -m pytest tests/test_sessions_routes.py -v
```

Expected:
```
PASSED tests/test_sessions_routes.py::test_list_sessions_db_error_returns_503
PASSED tests/test_sessions_routes.py::test_list_sessions_no_pool_returns_503
```

- [ ] **Step 5: Run all tests to confirm no regressions**

```bash
cd services/api && python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routes/sessions.py services/api/tests/test_sessions_routes.py
git commit -m "fix(sessions): wrap DB calls in try/except; return 503 on errors (not raw 500)"
```

---

## Task 7: Migration 0009 — Backfill canon-law into Existing User Preferences

**Bug fixed:**
- **#8 (Data correctness)** — Migration 0007 added `canon-law` to the `documents.collection` check constraint and updated the column DEFAULT for new `user_preferences` rows, but never backfilled existing rows. Every user who registered before migration 0007 was applied has `canon-law` absent from `default_collections` and will never see canon-law results unless they manually re-enable the toggle and have it save. The fix is a new migration that backfills only the rows that need it.

**Prerequisite:** Migration 0008 (`0008_documents_add_translation.sql`) must be applied before this one.

**File:** `supabase/migrations/0009_backfill_canon_law_preferences.sql`

- [ ] **Step 1: Create the migration file**

Create `supabase/migrations/0009_backfill_canon_law_preferences.sql`:

```sql
-- Backfill 'canon-law' into user_preferences rows that were created before
-- migration 0007 added it to the column DEFAULT. The WHERE clause makes this
-- idempotent: rows that already contain 'canon-law' are untouched.

UPDATE user_preferences
SET default_collections = array_append(default_collections, 'canon-law')
WHERE NOT ('canon-law' = ANY(default_collections));
```

- [ ] **Step 2: Verify correctness against the schema before applying**

The `user_preferences` table:
- `default_collections text[]` — array of collection name strings

The query:
1. `NOT ('canon-law' = ANY(default_collections))` — selects only rows that do not already include it (idempotent, safe to run multiple times)
2. `array_append(default_collections, 'canon-law')` — appends without creating duplicates (given the WHERE guard)

Test against a local database before applying to production:

```sql
-- Seed a test row that lacks canon-law
INSERT INTO user_preferences (user_id, default_collections)
VALUES ('00000000-0000-0000-0000-000000000001', '{bible,catechism}')
ON CONFLICT (user_id) DO UPDATE SET default_collections = EXCLUDED.default_collections;

-- Run the migration
UPDATE user_preferences
SET default_collections = array_append(default_collections, 'canon-law')
WHERE NOT ('canon-law' = ANY(default_collections));

-- Verify
SELECT default_collections
FROM user_preferences
WHERE user_id = '00000000-0000-0000-0000-000000000001';
-- Expected: {bible,catechism,canon-law}

-- Confirm idempotency (running again should update 0 rows)
UPDATE user_preferences
SET default_collections = array_append(default_collections, 'canon-law')
WHERE NOT ('canon-law' = ANY(default_collections));
-- Expected: UPDATE 0
```

- [ ] **Step 3: Apply the migration**

```bash
supabase db push
```

Or via the Supabase dashboard SQL editor: paste the migration SQL and run it.

- [ ] **Step 4: Post-apply verification**

```sql
SELECT COUNT(*)
FROM user_preferences
WHERE NOT ('canon-law' = ANY(default_collections));
```

Expected: `0` — every user preferences row now includes `canon-law`.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/0009_backfill_canon_law_preferences.sql
git commit -m "feat(db): migration 0009 — backfill canon-law into existing user_preferences rows"
```

---

## Task 8: Remove Duplicate Quota Persistence from SearchPage

**Bug fixed:**
- **#9 (Efficiency)** — `SearchPage.tsx` and `QuotaControl.tsx` both independently debounce-persist `default_quota` to `PUT /v1/preferences` when the quota changes. A single quota button press fires two identical API calls 500 ms later. `QuotaControl.tsx` is the correct owner of quota persistence (it is the component that renders the quota buttons and calls its own `onChange` prop). The duplicate effect in `SearchPage.tsx` should be deleted.

**File:** `apps/web/src/components/search/SearchPage.tsx`

- [ ] **Step 1: Delete the quota-persistence effect from SearchPage.tsx**

In `apps/web/src/components/search/SearchPage.tsx`, find and delete this entire block (~lines 73–86):

```typescript
  // ── Quota persistence (debounced, skip mount) ─────────────────────────────

  const quotaMounted = useRef(false);

  useEffect(() => {
    if (!quotaMounted.current) {
      quotaMounted.current = true;
      return;
    }
    if (!tokenRef.current) return;
    const timer = setTimeout(() => {
      updatePreferences(tokenRef.current!, { default_quota: quota }).catch(() => {});
    }, 500);
    return () => clearTimeout(timer);
  }, [quota]);
```

After deletion: `quota`, `setQuota`, and `handleQuotaChange` remain — they still control local UI state. Only the persistence side-effect is removed from this file.

- [ ] **Step 2: Remove `updatePreferences` from SearchPage's import**

`updatePreferences` is no longer called in `SearchPage.tsx` after the deletion above. `CollectionToggles.tsx` and `QuotaControl.tsx` each import it directly.

Find this import in `SearchPage.tsx`:

```typescript
import {
  streamSearch,
  getSearchResults,
  updatePreferences,
  type ChunkResult,
} from "@/lib/api";
```

Change to:

```typescript
import {
  streamSearch,
  getSearchResults,
  type ChunkResult,
} from "@/lib/api";
```

- [ ] **Step 3: TypeScript compile check**

```bash
cd apps/web && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Manual smoke test**

Run `npm run dev`. Open the search page. Open the browser Network tab. Click a quota button (e.g., 4 → 3). Wait 600 ms. Confirm exactly **one** `PUT /v1/preferences` request fires (not two).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/search/SearchPage.tsx
git commit -m "fix(search): remove duplicate quota persistence from SearchPage — QuotaControl owns it"
```

---

## Self-Review

### Spec Coverage Check

| CLAUDE.md Requirement | Covered? |
|---|---|
| POST /v1/chat contract unchanged | ✓ No chat routes modified |
| All V2 API endpoints under /v1/ | ✓ No route prefixes changed |
| Frontend never queries DB directly | ✓ No DB client in frontend |
| JWT verification unchanged | ✓ Auth deps untouched |
| RLS on all user-owned tables | ✓ Migration 0009 is a DML UPDATE; no DDL or policy changes |
| design system tokens (Sacred Night) | ✓ No UI styling changes |
| CSP headers (next.config.ts) | ✓ Untouched |
| V2 API response shapes | ✓ Response models unchanged; 400/429/503 status codes retained |
| Collections canonical source = constants.py | ✓ `_validate_collections` reads from `VALID_COLLECTIONS` imported from `constants.py` |
| SSE streaming contract unchanged | ✓ Pipeline generator unchanged except json.dumps at line 153 |
| No secrets in logs | ✓ Only exception class names are logged, never values |
| Docker / Railway deploy unchanged | ✓ Only pyproject.toml adds optional dev deps; production image unaffected |

### Placeholder Scan

No TBDs, "implement later", "fill in", "similar to Task N", or steps without code found.

### Type / Symbol Consistency

- `_validate_collections(body: SearchRequest) -> list[str]` — used as `valid_collections: list[str] = Depends(_validate_collections)` in both `check_search_rate_limit` and `search`. ✓
- `ChunkCandidate` constructor in `test_rerank.py` uses `rrf_score=0.5` — matches the `rrf_score: float` field in `retrieve.py`. ✓
- `AuthUser(user_id=...)` in test helpers matches `AuthUser.user_id: str` in `models/auth.py`. ✓
- `json.dumps(...)` in pipeline.py — `json` is explicitly imported in Step 1 of Task 2. ✓
- `datetime.datetime.now(datetime.timezone.utc)` in search.py — `datetime` is explicitly imported in Step 3a of Task 4. ✓
