# Reader Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the chunk-window reader with a professional, chapter-based continuous-scroll reader fed by clean passages, make the Sources list clickable into it, and deep-link Read More to the exact passage via `anchor`.

**Architecture:** Backend gains a TOC endpoint and a chapter-based reader endpoint that read the contract's clean passage columns; `/v1/sources` is simplified to real document ids (Bible is per-book documents). Search results carry `anchor` end-to-end. Frontend rewrites the reader package into a chapter scroller with book/chapter pickers + a Contents drawer, and routes Read More / Sources clicks into it.

**Tech Stack:** FastAPI/Pydantic + asyncpg (backend), Next.js/TypeScript (frontend, verified via `next build`).

**Depends on:** Foundation plan (contract models/types, migration 0013). For live data, the Dual Datapipeline plan should have re-ingested at least one collection; the endpoints work against any re-ingested document.
**Specs:** `docs/superpowers/specs/2026-06-13-reader-rework-design.md`, `…-passage-contract-design.md`.

**Note:** Implement on a feature branch off `master`.

---

### Task 1: Thread `anchor` from Qdrant payload to search results

**Files:**
- Modify: `services/api/app/rag/retrieve.py` (payload read, `ChunkCandidate`, `_rrf_merge`)
- Modify: `services/api/app/rag/rerank.py` (`RankedChunk` + pass-through, lines ~69, 184-188, 202-206, 225-229)
- Modify: `services/api/app/rag/pipeline.py:197-198` (result dict)
- Modify: `services/api/app/routes/search.py:238` (`ChunkSource(...)`)
- Test: `services/api/tests/test_anchor_threading.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/test_anchor_threading.py`:

```python
from app.rag.retrieve import ChunkCandidate
from app.rag.rerank import RankedChunk


def test_chunk_candidate_has_anchor():
    c = ChunkCandidate(
        chunk_id="c", content="x", reference="r", collection="bible",
        document_id="d", document_title="John", author=None, rrf_score=0.1,
        anchor="john/3/16",
    )
    assert c.anchor == "john/3/16"


def test_ranked_chunk_has_anchor():
    r = RankedChunk(
        chunk_id="c", content="x", reference="r", collection="bible",
        document_id="d", document_title="John", author=None, reranker_score=0.9,
        anchor="john/3/16",
    )
    assert r.anchor == "john/3/16"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && python -m pytest tests/test_anchor_threading.py -v`
Expected: FAIL (`ChunkCandidate`/`RankedChunk` have no `anchor`).

- [ ] **Step 3: Add `anchor` to `ChunkCandidate` + read it from the payload**

In `services/api/app/rag/retrieve.py`:
- Add `anchor: str | None` to the `ChunkCandidate` dataclass (after `author`).
- In `_search_vector`, add to each row dict: `"anchor": r.payload.get("anchor"),`.
- In `_search_fts`, add `c.anchor` to the SELECT column list and it will appear in the row dict.
- In `_rrf_merge`, add to the `metadata[chunk_id]` dict: `"anchor": row.get("anchor"),`.
- In `retrieve_candidates`, add `anchor=entry.get("anchor"),` to the `ChunkCandidate(...)` construction.

- [ ] **Step 4: Add `anchor` to `RankedChunk` and pass it through**

In `services/api/app/rag/rerank.py`:
- Add `anchor: str | None = None` to the `RankedChunk` model (near `document_title`).
- At each `RankedChunk(...)` construction (the reranked path ~line 184, the per-candidate path ~202, and `_fallback_ranked` ~225), add `anchor=candidate.anchor,` / `anchor=c.anchor,`.

- [ ] **Step 5: Pass `anchor` through the pipeline result dict and into `ChunkSource`**

In `services/api/app/rag/pipeline.py` (the result dict around line 197), add: `"anchor": chunk.anchor,`.
In `services/api/app/routes/search.py` at the `ChunkSource(...)` construction (line 238), add: `anchor=chunk.anchor,` (or `anchor=result["anchor"]` matching how the dict is accessed there — match the surrounding code).

- [ ] **Step 6: Run test + existing retrieve tests**

Run: `cd services/api && python -m pytest tests/test_anchor_threading.py tests/test_retrieve.py -v`
Expected: PASS (new tests pass; existing retrieve tests still pass — update `_row` helper in `test_retrieve.py` to include `"anchor": None` if a strict construction requires it).

- [ ] **Step 7: Commit**

```bash
git add services/api/app/rag/retrieve.py services/api/app/rag/rerank.py services/api/app/rag/pipeline.py services/api/app/routes/search.py services/api/tests/test_anchor_threading.py
git commit -m "feat(api): thread passage anchor into search results"
```

---

### Task 2: TOC endpoint — `GET /v1/documents/{id}/toc`

**Files:**
- Modify: `services/api/app/routes/documents.py` (add handler)
- Test: `services/api/tests/test_toc_endpoint.py`

- [ ] **Step 1: Write the failing test (pool mocked, like test_retrieve)**

Create `services/api/tests/test_toc_endpoint.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch
from app.models.auth import AuthUser
from app.routes.documents import get_document_toc

_DOC = "11111111-1111-1111-1111-111111111111"


def test_toc_returns_ordered_chapters():
    pool = AsyncMock()
    pool.fetchrow.return_value = {"id": _DOC, "collection": "bible", "title": "John",
                                  "author": None, "year": None, "metadata": None, "cnt": 2}
    pool.fetch.return_value = [
        {"chapter_key": "john/1", "chapter_label": "John 1"},
        {"chapter_key": "john/2", "chapter_label": "John 2"},
    ]
    with patch("app.routes.documents.get_pool", return_value=pool):
        resp = asyncio.run(get_document_toc(_DOC, user=AuthUser(user_id="u", email=None)))
    assert [c.chapter_label for c in resp.chapters] == ["John 1", "John 2"]
    assert resp.document.title == "John"
```

(If `AuthUser` requires different fields, match its real constructor in `app/models/auth.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && python -m pytest tests/test_toc_endpoint.py -v`
Expected: FAIL (`get_document_toc` missing).

- [ ] **Step 3: Implement the TOC handler**

In `services/api/app/routes/documents.py`, import the new models and add the handler:

```python
from app.models.documents import (
    DocumentResponse, ReaderChunk, ReaderResponse,
    ReaderPassage, ReaderChapter, TocEntry, TocResponse,
)


@router.get("/documents/{doc_id}/toc", response_model=TocResponse)
async def get_document_toc(
    doc_id: str,
    user: AuthUser = Depends(get_current_user),
) -> TocResponse:
    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid doc_id: must be a UUID")
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    doc_row = await pool.fetchrow(
        """SELECT d.id, d.collection, d.title, d.author, d.year, d.metadata,
                  (SELECT count(*) FROM chunks c WHERE c.document_id = d.id) AS cnt
           FROM documents d WHERE d.id = $1""",
        doc_uuid,
    )
    if doc_row is None:
        raise HTTPException(status_code=404, detail="Document not found")

    chapter_rows = await pool.fetch(
        """SELECT chapter_key, chapter_label
           FROM chunks WHERE document_id = $1 AND chapter_key IS NOT NULL
           GROUP BY chapter_key, chapter_label
           ORDER BY min(position)""",
        doc_uuid,
    )
    document = DocumentResponse(
        id=str(doc_row["id"]), collection=doc_row["collection"], title=doc_row["title"],
        author=doc_row["author"], year=doc_row["year"], metadata=doc_row["metadata"],
        chunk_count=doc_row["cnt"],
    )
    chapters = [TocEntry(chapter_key=r["chapter_key"], chapter_label=r["chapter_label"])
                for r in chapter_rows]
    return TocResponse(document=document, chapters=chapters)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && python -m pytest tests/test_toc_endpoint.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/routes/documents.py services/api/tests/test_toc_endpoint.py
git commit -m "feat(api): document TOC endpoint"
```

---

### Task 3: Chapter reader endpoint — `GET /v1/documents/{id}/reader`

**Files:**
- Modify: `services/api/app/routes/documents.py` (replace `get_document_reader` body with chapter logic)
- Test: `services/api/tests/test_reader_chapter_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/test_reader_chapter_endpoint.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch
from app.models.auth import AuthUser
from app.routes.documents import get_document_reader

_DOC = "11111111-1111-1111-1111-111111111111"


def test_reader_returns_chapter_with_neighbors_and_highlight():
    pool = AsyncMock()
    pool.fetchrow.side_effect = [
        # document row
        {"id": _DOC, "collection": "bible", "title": "John", "author": None,
         "year": None, "metadata": None, "cnt": 3},
        # anchor → chapter_key resolution
        {"chapter_key": "john/3"},
    ]
    pool.fetch.side_effect = [
        # passages in chapter john/3
        [{"id": "p1", "anchor": "john/3/16", "chapter_key": "john/3", "chapter_label": "John 3",
          "unit_label": "16", "reference": "John 3:16", "content": "For God so loved…"}],
        # ordered chapter keys for prev/next
        [{"chapter_key": "john/2"}, {"chapter_key": "john/3"}, {"chapter_key": "john/4"}],
    ]
    with patch("app.routes.documents.get_pool", return_value=pool):
        resp = asyncio.run(get_document_reader(
            _DOC, anchor="john/3/16", chapter=None, user=AuthUser(user_id="u", email=None)))
    assert resp.chapter_key == "john/3"
    assert resp.prev_chapter_key == "john/2"
    assert resp.next_chapter_key == "john/4"
    assert resp.highlight_anchor == "john/3/16"
    assert resp.passages[0].unit_label == "16"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && python -m pytest tests/test_reader_chapter_endpoint.py -v`
Expected: FAIL (old `get_document_reader` signature/return differ).

- [ ] **Step 3: Replace `get_document_reader` with chapter logic**

In `services/api/app/routes/documents.py`, replace the existing `get_document_reader` handler with:

```python
@router.get("/documents/{doc_id}/reader", response_model=ReaderChapter)
async def get_document_reader(
    doc_id: str,
    anchor: str | None = Query(default=None, description="Deep-link passage anchor"),
    chapter: str | None = Query(default=None, description="chapter_key to load directly"),
    user: AuthUser = Depends(get_current_user),
) -> ReaderChapter:
    try:
        doc_uuid = uuid.UUID(doc_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid doc_id: must be a UUID")
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    doc_row = await pool.fetchrow(
        """SELECT d.id, d.collection, d.title, d.author, d.year, d.metadata,
                  (SELECT count(*) FROM chunks c WHERE c.document_id = d.id) AS cnt
           FROM documents d WHERE d.id = $1""",
        doc_uuid,
    )
    if doc_row is None:
        raise HTTPException(status_code=404, detail="Document not found")

    # Resolve target chapter_key.
    chapter_key = chapter
    if chapter_key is None and anchor:
        row = await pool.fetchrow(
            "SELECT chapter_key FROM chunks WHERE document_id=$1 AND anchor=$2", doc_uuid, anchor)
        chapter_key = row["chapter_key"] if row else None
    if chapter_key is None:
        row = await pool.fetchrow(
            "SELECT chapter_key FROM chunks WHERE document_id=$1 AND chapter_key IS NOT NULL "
            "ORDER BY position LIMIT 1", doc_uuid)
        if row is None:
            raise HTTPException(status_code=404, detail="Document has no readable passages")
        chapter_key = row["chapter_key"]

    passage_rows = await pool.fetch(
        """SELECT id, anchor, chapter_key, chapter_label, unit_label, reference, content
           FROM chunks WHERE document_id=$1 AND chapter_key=$2 ORDER BY position""",
        doc_uuid, chapter_key,
    )
    if not passage_rows:
        raise HTTPException(status_code=404, detail="Chapter not found")

    key_rows = await pool.fetch(
        """SELECT chapter_key FROM chunks WHERE document_id=$1 AND chapter_key IS NOT NULL
           GROUP BY chapter_key ORDER BY min(position)""",
        doc_uuid,
    )
    keys = [r["chapter_key"] for r in key_rows]
    idx = keys.index(chapter_key) if chapter_key in keys else 0
    prev_key = keys[idx - 1] if idx > 0 else None
    next_key = keys[idx + 1] if idx + 1 < len(keys) else None

    document = DocumentResponse(
        id=str(doc_row["id"]), collection=doc_row["collection"], title=doc_row["title"],
        author=doc_row["author"], year=doc_row["year"], metadata=doc_row["metadata"],
        chunk_count=doc_row["cnt"],
    )
    passages = [
        ReaderPassage(
            id=str(r["id"]), anchor=r["anchor"], chapter_key=r["chapter_key"],
            chapter_label=r["chapter_label"], unit_label=r["unit_label"],
            reference=r["reference"], content=r["content"],
        ) for r in passage_rows
    ]
    return ReaderChapter(
        document=document, chapter_key=chapter_key,
        chapter_label=passage_rows[0]["chapter_label"], passages=passages,
        prev_chapter_key=prev_key, next_chapter_key=next_key, highlight_anchor=anchor,
    )
```

Remove the now-unused old `ReaderChunk`/`ReaderResponse` import usage from this handler (the models can stay in `models/documents.py` until no longer referenced).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && python -m pytest tests/test_reader_chapter_endpoint.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/routes/documents.py services/api/tests/test_reader_chapter_endpoint.py
git commit -m "feat(api): chapter-based reader endpoint with prev/next + highlight"
```

---

### Task 4: Simplify `/v1/sources` (real ids; drop synthetic CF logic)

**Files:**
- Rewrite: `services/api/app/routes/sources.py`
- Test: `services/api/tests/test_sources_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/test_sources_endpoint.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch
from app.models.auth import AuthUser
from app.routes.sources import get_sources


def test_sources_returns_real_document_ids():
    pool = AsyncMock()
    pool.fetch.return_value = [
        {"id": "d-john", "collection": "bible", "title": "John", "author": None,
         "year": None, "translation": "WEB-C", "metadata": None, "chunk_count": 21},
        {"id": "d-clement", "collection": "church-fathers",
         "title": "First Epistle to the Corinthians", "author": "Clement of Rome",
         "year": None, "translation": None, "metadata": None, "chunk_count": 65},
    ]
    with patch("app.routes.sources.get_pool", return_value=pool):
        resp = asyncio.run(get_sources(user=AuthUser(user_id="u", email=None)))
    ids = {s.id for s in resp.sources}
    assert ids == {"d-john", "d-clement"}
    # church-fathers id is a plain document id (no synthetic "id:author:work")
    cf = [s for s in resp.sources if s.collection == "church-fathers"][0]
    assert ":" not in cf.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd services/api && python -m pytest tests/test_sources_endpoint.py -v`
Expected: FAIL (current code special-cases church-fathers with synthetic ids).

- [ ] **Step 3: Rewrite `sources.py` to a single document-level query**

Replace `services/api/app/routes/sources.py` with:

```python
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_pool
from app.deps.auth import get_current_user
from app.models.auth import AuthUser

logger = logging.getLogger(__name__)
router = APIRouter()


class SourceDocument(BaseModel):
    id: str
    collection: str
    title: str
    author: Optional[str] = None
    year: Optional[int] = None
    translation: Optional[str] = None
    metadata: Optional[dict] = None
    chunk_count: int


class SourcesResponse(BaseModel):
    sources: list[SourceDocument]


@router.get("/sources", response_model=SourcesResponse)
async def get_sources(user: AuthUser = Depends(get_current_user)) -> SourcesResponse:
    pool = get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    try:
        rows = await pool.fetch(
            """
            SELECT d.id::text AS id, d.collection, d.title, d.author, d.year,
                   NULLIF(d.translation, '') AS translation, d.metadata,
                   COUNT(c.id)::int AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            GROUP BY d.id
            ORDER BY d.collection, d.year NULLS LAST, d.title
            """
        )
    except Exception as exc:
        logger.error("get_sources query failed (%s)", exc.__class__.__name__)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    sources = [
        SourceDocument(
            id=r["id"], collection=r["collection"], title=r["title"],
            author=r["author"] or None, year=r["year"], translation=r["translation"],
            metadata=dict(r["metadata"]) if r["metadata"] else None,
            chunk_count=r["chunk_count"],
        ) for r in rows
    ]
    return SourcesResponse(sources=sources)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd services/api && python -m pytest tests/test_sources_endpoint.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/routes/sources.py services/api/tests/test_sources_endpoint.py
git commit -m "feat(api): simplify /v1/sources to real document ids"
```

---

### Task 5: Frontend API client — TOC + chapter reader functions

**Files:**
- Modify: `apps/web/src/lib/api.ts` (replace `getReader`; add `getToc`, `getReaderChapter`)

- [ ] **Step 1: Replace the reader client functions**

In `apps/web/src/lib/api.ts`, find the existing `getReader` function (around line 333) and replace it with the two contract functions (the `ReaderChapter`/`TocResponse` interfaces already exist from the Foundation plan):

```ts
export async function getToc(token: string, docId: string): Promise<TocResponse> {
  const res = await fetch(`${API_URL}/v1/documents/${docId}/toc`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<TocResponse>;
}

export async function getReaderChapter(
  token: string,
  docId: string,
  opts: { anchor?: string; chapter?: string },
): Promise<ReaderChapter> {
  const params = new URLSearchParams();
  if (opts.anchor) params.set("anchor", opts.anchor);
  if (opts.chapter) params.set("chapter", opts.chapter);
  const qs = params.toString();
  const res = await fetch(`${API_URL}/v1/documents/${docId}/reader${qs ? `?${qs}` : ""}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<ReaderChapter>;
}
```

- [ ] **Step 2: Verify build**

Run: `cd apps/web && npm run build`
Expected: build succeeds (any remaining references to the removed `getReader` will fail the build — they are fixed in Task 7, so this task may be committed together with Task 7 if the build needs both; see note).

> If `npm run build` fails only because `DocumentReader.tsx` still imports `getReader`, proceed to Task 7 and run the build at the end of Task 7. Commit this step's change together with Task 7's.

- [ ] **Step 3: Commit (with Task 7 if build requires it)**

```bash
git add apps/web/src/lib/api.ts
git commit -m "feat(web): TOC + chapter reader API client functions"
```

---

### Task 6: Read More by anchor + clickable Sources

**Files:**
- Modify: `apps/web/src/components/search/ChunkCard.tsx:94-100` (Read More → anchor)
- Modify: `apps/web/src/components/sources/SourcesPage.tsx` (clickable rows; Bible book grid)

- [ ] **Step 1: Read More navigates by anchor**

In `apps/web/src/components/search/ChunkCard.tsx`, update `handleReadMore` to use the anchor from the result source:

```tsx
function handleReadMore() {
  if (!UUID_RE.test(document_id)) return;
  trackDocumentOpened({ documentId: document_id, collection, source: "chunk_card" });
  const anchor = source.anchor;
  const qs = anchor ? `?anchor=${encodeURIComponent(anchor)}` : "";
  router.push(`/reader/${document_id}${qs}`);
}
```

(`source` is already destructured in the component; `source.anchor` is typed from the Foundation plan.)

- [ ] **Step 2: Make Sources rows clickable + Bible book grid**

In `apps/web/src/components/sources/SourcesPage.tsx`:
- Import `useRouter` from `next/navigation` and create `const router = useRouter();` in `SourcesPage`.
- In `DocRow`, wrap the row in a button/link that calls `router.push(\`/reader/${doc.id}\`)` and add hover affordance (cursor-pointer, a `›` chevron). Pass `router` (or use a module-level navigate helper) so `DocRow` can navigate.
- In `BibleSection`, change each translation `<li>` into an expandable control: clicking it toggles an inline book grid built from that translation's `docs` (each `doc` is a book). Each book chip calls `router.push(\`/reader/${book.id}\`)`.

Concrete `DocRow`:

```tsx
function DocRow({ doc, onOpen }: { doc: SourceDocument; onOpen: (id: string) => void }) {
  const parts: string[] = [];
  if (doc.author) parts.push(doc.author);
  if (doc.year) parts.push(String(doc.year));
  const attribution = parts.join(", ");
  return (
    <li>
      <button
        onClick={() => onOpen(doc.id)}
        className="w-full flex items-start justify-between gap-4 px-3 py-2 rounded bg-brand-surface text-left hover:bg-brand-surface/70 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
      >
        <div className="min-w-0">
          <span className="text-brand-primary text-sm">{doc.title}</span>
          {attribution && <span className="text-brand-muted text-xs ml-2">{attribution}</span>}
        </div>
        <span className="shrink-0 text-xs text-brand-accent">›</span>
      </button>
    </li>
  );
}
```

Wire `onOpen={(id) => router.push(`/reader/${id}`)}` from `SourcesPage` where `DocRow` is rendered. For `BibleSection`, replace its translation `<li>` with a `useState`-driven expandable that renders book chips (each `book` in `books`) as buttons calling the same navigate.

- [ ] **Step 3: Verify build**

Run: `cd apps/web && npm run build`
Expected: succeeds (pending Task 7 for the reader page itself).

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/search/ChunkCard.tsx apps/web/src/components/sources/SourcesPage.tsx
git commit -m "feat(web): Read More by anchor + clickable Sources with Bible book grid"
```

---

### Task 7: Reader component rewrite — chapter scroller

**Files:**
- Rewrite: `apps/web/src/components/reader/DocumentReader.tsx`
- Create: `apps/web/src/components/reader/ReaderChrome.tsx`
- Create: `apps/web/src/components/reader/ContentsDrawer.tsx`
- Create: `apps/web/src/components/reader/ChapterSection.tsx`
- Create: `apps/web/src/components/reader/Passage.tsx`
- Delete: `apps/web/src/components/reader/ReaderToolbar.tsx`, `apps/web/src/components/reader/ReaderChunk.tsx`
- Modify: `apps/web/src/components/reader/index.ts`

- [ ] **Step 1: Build the Passage + ChapterSection presentational components**

Create `apps/web/src/components/reader/Passage.tsx`:

```tsx
"use client";
import type { ReaderPassage } from "@/lib/api";

export function Passage({ passage, highlighted }: { passage: ReaderPassage; highlighted: boolean }) {
  return (
    <p
      id={`anchor-${passage.anchor}`}
      className="text-[15px] leading-[1.9] text-brand-primary mb-3"
      style={{ fontFamily: "Georgia, serif", ...(highlighted ? { background: "rgba(196,151,42,0.16)", borderRadius: 4 } : {}) }}
    >
      {passage.unit_label && (
        <sup className="text-brand-muted mr-1" style={{ fontSize: 10 }}>{passage.unit_label}</sup>
      )}
      {passage.content}
    </p>
  );
}
```

Create `apps/web/src/components/reader/ChapterSection.tsx`:

```tsx
"use client";
import { forwardRef } from "react";
import type { ReaderChapter } from "@/lib/api";
import { Passage } from "./Passage";

interface Props { chapter: ReaderChapter; highlightAnchor: string | null; }

export const ChapterSection = forwardRef<HTMLDivElement, Props>(function ChapterSection(
  { chapter, highlightAnchor }, headingRef,
) {
  return (
    <section data-chapter-key={chapter.chapter_key} className="max-w-[640px] mx-auto px-6 py-6">
      <h2 ref={headingRef} data-chapter-key={chapter.chapter_key}
          className="text-xl font-semibold text-brand-primary mb-4" style={{ fontFamily: "Georgia, serif" }}>
        {chapter.chapter_label}
      </h2>
      {chapter.passages.map((p) => (
        <Passage key={p.id} passage={p} highlighted={p.anchor === highlightAnchor} />
      ))}
    </section>
  );
});
```

- [ ] **Step 2: Build the chrome (pickers) and contents drawer**

Create `apps/web/src/components/reader/ReaderChrome.tsx`:

```tsx
"use client";
import { useRouter } from "next/navigation";
import type { DocumentInfo, TocEntry } from "@/lib/api";

interface Props {
  document: DocumentInfo;
  toc: TocEntry[];
  currentChapterKey: string | null;
  onToggleContents: () => void;
  onJump: (chapterKey: string) => void;
}

export function ReaderChrome({ document, toc, currentChapterKey, onToggleContents, onJump }: Props) {
  const router = useRouter();
  const current = toc.find((t) => t.chapter_key === currentChapterKey);
  return (
    <div className="sticky top-0 z-10 bg-brand-bg border-b border-brand-surface px-4 py-2 flex items-center gap-2">
      <button onClick={() => router.back()} className="text-brand-muted text-sm hover:text-brand-primary">←</button>
      <button onClick={onToggleContents} className="text-brand-muted text-sm hover:text-brand-primary">☰ Contents</button>
      <span className="text-brand-primary text-sm font-medium truncate">{document.title}</span>
      <select
        value={currentChapterKey ?? ""}
        onChange={(e) => onJump(e.target.value)}
        className="ml-auto bg-brand-surface text-brand-primary text-sm rounded px-2 py-1 border border-brand-surface"
      >
        {toc.map((t) => (
          <option key={t.chapter_key} value={t.chapter_key}>{t.chapter_label}</option>
        ))}
      </select>
    </div>
  );
}
```

Create `apps/web/src/components/reader/ContentsDrawer.tsx`:

```tsx
"use client";
import type { TocEntry } from "@/lib/api";

interface Props {
  open: boolean; toc: TocEntry[]; currentChapterKey: string | null;
  onJump: (chapterKey: string) => void; onClose: () => void;
}

export function ContentsDrawer({ open, toc, currentChapterKey, onJump, onClose }: Props) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-20 flex">
      <div className="w-72 max-w-[80vw] bg-brand-surface h-full overflow-y-auto p-4">
        <p className="text-brand-muted text-xs uppercase tracking-wide mb-3">Contents</p>
        <ul className="space-y-1">
          {toc.map((t) => (
            <li key={t.chapter_key}>
              <button
                onClick={() => { onJump(t.chapter_key); onClose(); }}
                className={`text-sm text-left w-full px-2 py-1 rounded hover:bg-brand-bg ${
                  t.chapter_key === currentChapterKey ? "text-brand-accent" : "text-brand-primary"
                }`}
              >
                {t.chapter_label}
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex-1 bg-black/40" onClick={onClose} />
    </div>
  );
}
```

- [ ] **Step 3: Rewrite `DocumentReader.tsx` — chapter buffer + lazy scroll + deep-link**

Replace `apps/web/src/components/reader/DocumentReader.tsx`:

```tsx
"use client";
import { useEffect, useRef, useState, Suspense, useCallback } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useAppContext } from "@/components/layout/AppShell";
import { getToc, getReaderChapter, type ReaderChapter, type TocEntry, type DocumentInfo } from "@/lib/api";
import { ReaderChrome } from "./ReaderChrome";
import { ContentsDrawer } from "./ContentsDrawer";
import { ChapterSection } from "./ChapterSection";

function Inner({ docId }: { docId: string }) {
  const { token } = useAppContext();
  const router = useRouter();
  const params = useSearchParams();
  const initialAnchor = params.get("anchor");
  const initialChapter = params.get("chapter");

  const [doc, setDoc] = useState<DocumentInfo | null>(null);
  const [toc, setToc] = useState<TocEntry[]>([]);
  const [chapters, setChapters] = useState<ReaderChapter[]>([]); // ordered buffer
  const [currentKey, setCurrentKey] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<string | null>(initialAnchor);
  const [contentsOpen, setContentsOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Initial load: TOC + first/target chapter.
  useEffect(() => {
    if (!token) return;
    let alive = true;
    (async () => {
      try {
        setLoading(true);
        const [tocResp, chapter] = await Promise.all([
          getToc(token, docId),
          getReaderChapter(token, docId, {
            anchor: initialAnchor ?? undefined, chapter: initialChapter ?? undefined,
          }),
        ]);
        if (!alive) return;
        setDoc(tocResp.document);
        setToc(tocResp.chapters);
        setChapters([chapter]);
        setCurrentKey(chapter.chapter_key);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, docId]);

  // Scroll the highlighted passage into view after first render.
  useEffect(() => {
    if (highlight && chapters.length === 1) {
      document.getElementById(`anchor-${highlight}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [chapters, highlight]);

  const loadChapter = useCallback(async (key: string, mode: "append" | "replace") => {
    if (!token) return;
    const chapter = await getReaderChapter(token, docId, { chapter: key });
    setChapters((prev) => mode === "replace" ? [chapter] : [...prev, chapter]);
    setCurrentKey(key);
  }, [token, docId]);

  const jump = useCallback((key: string) => {
    setHighlight(null);
    loadChapter(key, "replace");
    scrollRef.current?.scrollTo({ top: 0 });
  }, [loadChapter]);

  // Infinite scroll: when near the bottom, append the next chapter.
  function onScroll(e: React.UIEvent<HTMLDivElement>) {
    const el = e.currentTarget;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 600) {
      const last = chapters[chapters.length - 1];
      if (last?.next_chapter_key && !chapters.some((c) => c.chapter_key === last.next_chapter_key)) {
        loadChapter(last.next_chapter_key, "append");
      }
    }
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-brand-bg gap-4">
        <p className="text-brand-muted text-sm">This document couldn&apos;t be loaded.</p>
        <button onClick={() => router.back()} className="text-brand-accent text-sm hover:underline">← Back</button>
      </div>
    );
  }
  if (loading && !doc) {
    return (
      <div className="flex flex-col h-full bg-brand-bg px-6 pt-8 space-y-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="animate-pulse bg-brand-surface rounded h-4" style={{ width: `${70 + (i % 3) * 10}%` }} />
        ))}
      </div>
    );
  }
  if (!doc) return null;

  return (
    <div className="flex flex-col h-full bg-brand-bg">
      <ReaderChrome
        document={doc} toc={toc} currentChapterKey={currentKey}
        onToggleContents={() => setContentsOpen((v) => !v)} onJump={jump}
      />
      <ContentsDrawer
        open={contentsOpen} toc={toc} currentChapterKey={currentKey}
        onJump={jump} onClose={() => setContentsOpen(false)}
      />
      <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto">
        {chapters.map((ch) => (
          <ChapterSection key={ch.chapter_key} chapter={ch} highlightAnchor={highlight} />
        ))}
      </div>
    </div>
  );
}

export function DocumentReader({ docId }: { docId: string }) {
  return <Suspense><Inner docId={docId} /></Suspense>;
}
```

- [ ] **Step 4: Delete old components + fix the barrel export**

Delete `apps/web/src/components/reader/ReaderToolbar.tsx` and `apps/web/src/components/reader/ReaderChunk.tsx`. Update `apps/web/src/components/reader/index.ts` to export `DocumentReader` (and the new subcomponents if it re-exports them); remove references to the deleted files.

```bash
git rm apps/web/src/components/reader/ReaderToolbar.tsx apps/web/src/components/reader/ReaderChunk.tsx
```

- [ ] **Step 5: Verify the whole frontend builds**

Run: `cd apps/web && npm run build`
Expected: build succeeds. Fix any remaining import of the removed `getReader`/`ReaderResponse`/old components.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/reader/ apps/web/src/lib/api.ts
git commit -m "feat(web): chapter-based continuous-scroll reader with pickers + contents"
```

---

### Task 8: Manual end-to-end verification

**Files:** none (manual).

- [ ] **Step 1: Run the app and verify the reader**

With the API running and at least one collection re-ingested (Dual Datapipeline plan), use the `/run` or `/verify` workflow (or `npm run dev` + the API) to confirm:
- Search a query → a result's **Read More** opens the reader at the right chapter with the passage highlighted and scrolled into view.
- Scrolling to the end of a chapter appends the next chapter; the chapter `<select>` tracks position.
- ☰ Contents jumps between chapters.
- **Sources** list: a church-fathers work row opens its reader; the Bible translation expands to a book grid; a book opens at chapter 1.

- [ ] **Step 2: Commit any fixes found**

```bash
git add -A && git commit -m "fix(web): reader e2e adjustments"
```

---

## Self-Review

**Spec coverage (reader-rework spec):**
- §2 reader reads clean passages via TOC + chapter endpoints → Tasks 2, 3.
- §3 hybrid scroll, one chapter/section, pickers tracking position, contents drawer, deep-link highlight → Task 7 (`DocumentReader`, `ReaderChrome`, `ContentsDrawer`, `ChapterSection`).
- §4 entry points: Read More by anchor → Tasks 1 (anchor on result) + 6; Sources clickable + Bible book grid → Task 6.
- §5 component package rewrite → Task 7 (+ deletions). §6 per-collection presentation → `unit_label`/`chapter_label` rendering in `Passage`/`ChapterSection`.
- §7 states (loading/error) → Task 7.
- Backend `/v1/sources` simplification (contract §6) → Task 4.

**Placeholder scan:** none — concrete code/SQL/commands. The chrome uses a `<select>` chapter picker (functional); a fancier dual book+chapter dropdown is a presentation refinement on top of the same `onJump`/TOC data and can be done in Task 7 polish without contract changes.

**Type consistency:** `ReaderChapter`/`ReaderPassage`/`TocEntry`/`TocResponse`/`ChunkSource.anchor` match the Foundation types and backend models. `chapter_key`/`chapter_label`/`anchor`/`unit_label`/`prev_chapter_key`/`next_chapter_key`/`highlight_anchor` consistent across backend handler, client functions, and components. `getReaderChapter(token, docId, {anchor?, chapter?})` and `getToc(token, docId)` signatures match their call sites in `DocumentReader`.

**Cross-plan dependency note:** Task 1 (anchor threading) requires Qdrant points to carry `anchor` (Dual Datapipeline Task 8). Until a collection is re-ingested, `source.anchor` is null and Read More falls back to opening the document at its first chapter (handled in Task 6).
```
