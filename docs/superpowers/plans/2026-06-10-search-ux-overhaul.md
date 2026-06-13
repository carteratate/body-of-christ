# Search UX Overhaul + Staggered Explanations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the search interface into a chat-style UX where the search bar disappears after submission, results are filterable by collection via a post-search bottom bar, and LLM explanations are staggered to prevent rate-limit failures.

**Architecture:** SearchPage gains two new state slices — `submittedCollections` (locked at search time) and `visibleCollections` (user-toggleable post-search filter). BottomBar becomes mode-aware: pre-search shows the existing search bar + collection pickers; post-search shows only a `ResultFilterBar` with slightly larger filter pills. SearchResults receives the full result set and `visibleCollections`, filters internally, and emits per-collection threshold notices. The backend pipeline staggers explanation task starts at 600 ms intervals in score order.

**Tech Stack:** React/TypeScript (Next.js), FastAPI/asyncio, Tailwind CSS, existing `COLLECTIONS` from `collections.ts`

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `services/api/app/rag/pipeline.py` | Stagger explanation task starts by 600ms × index |
| Modify | `apps/web/src/components/search/ChunkCard.tsx` | Rename "Explore more" button |
| Modify | `apps/web/src/components/search/SearchPage.tsx` | Add `submittedCollections`, `visibleCollections` state; thread new props |
| Modify | `apps/web/src/components/search/BottomBar.tsx` | Two-mode: pre-search vs post-search |
| Create | `apps/web/src/components/search/ResultFilterBar.tsx` | Post-search filter pills |
| Modify | `apps/web/src/components/search/SearchResults.tsx` | Accept `visibleCollections` + `submittedCollections`, filter internally, show threshold notices |
| Create | `apps/web/src/components/search/NoResultsScreen.tsx` | Full explanation when all collections return 0 results |

---

### Task 1: Stagger explanation requests (backend)

**Files:**
- Modify: `services/api/app/rag/pipeline.py:209-221`

The inner `_stream_one` function currently fires all tasks at once. Add a `stagger` parameter so each task sleeps before starting. `final_results` is already sorted by `reranker_score` descending (step 5), so index 0 is the top result.

- [ ] **Step 1: Add stagger sleep to `_stream_one`**

Replace the existing `_stream_one` and task-creation block (lines 209–221) with:

```python
        EXPLAIN_STAGGER_SEC = 0.6

        async def _stream_one(chunk: RankedChunk, stagger: float) -> None:
            if stagger > 0:
                await asyncio.sleep(stagger)
            try:
                async for delta in stream_explanation(
                    chunk.content, chunk.reference, chunk.collection, query
                ):
                    accumulated[chunk.chunk_id] += delta
                    await queue.put(("delta", chunk.chunk_id, delta))
            except Exception as exc:
                logger.warning("_stream_one error for %s: %s", chunk.chunk_id, exc)
            finally:
                await queue.put(("done", chunk.chunk_id, ""))

        tasks = [
            asyncio.create_task(_stream_one(c, i * EXPLAIN_STAGGER_SEC))
            for i, c in enumerate(final_results)
        ]
```

- [ ] **Step 2: Verify no Python syntax errors**

```bash
cd services/api && python -c "import app.rag.pipeline" && echo OK
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add services/api/app/rag/pipeline.py
git commit -m "fix(rag): stagger explanation requests 600ms apart in score order to prevent rate-limit failures"
```

---

### Task 2: Rename "Explore more" button

**Files:**
- Modify: `apps/web/src/components/search/ChunkCard.tsx:230-236`

- [ ] **Step 1: Change button text**

In `ChunkCard.tsx`, find the explore-more button and update it:

```tsx
        {/* Explore more */}
        <button
          onClick={handleExploreMore}
          aria-label="Query more sources like this"
          className="px-2 py-1 rounded text-xs text-brand-muted border border-brand-surface hover:text-brand-primary hover:border-brand-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
        >
          Query more sources like this
        </button>
```

- [ ] **Step 2: TypeScript check**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -20
```
Expected: no output (clean).

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/search/ChunkCard.tsx
git commit -m "feat(search): rename explore-more button to 'Query more sources like this'"
```

---

### Task 3: Add `submittedCollections` and `visibleCollections` state to SearchPage

**Files:**
- Modify: `apps/web/src/components/search/SearchPage.tsx`

Two new state slices:
- `submittedCollections` — snapshot of `activeCollections` at the moment search fires (used by BottomBar and SearchResults to know what was searched)
- `visibleCollections` — user-toggleable filter; initialized to `submittedCollections` on each search; mutated by post-search filter buttons

- [ ] **Step 1: Add state declarations**

After the `const [isRestoring, setIsRestoring] = useState(false);` line (currently line 74), add:

```typescript
  const [submittedCollections, setSubmittedCollections] = useState<string[]>([]);
  const [visibleCollections, setVisibleCollections] = useState<string[]>([]);
```

- [ ] **Step 2: Snapshot collections when search fires**

Inside `handleSearch`, right after `setResults([]);` (currently line 198), add:

```typescript
      const snapshot = [...activeCollections];
      setSubmittedCollections(snapshot);
      setVisibleCollections(snapshot);
```

- [ ] **Step 3: Reset on New Search**

Inside the `useEffect` for `searchKey` (the reset block, currently lines 119–138), after `setIsRestoring(false);`, add:

```typescript
    setSubmittedCollections([]);
    setVisibleCollections([]);
```

- [ ] **Step 4: Add `handleToggleVisible` handler**

After the existing `handleToggleCollection` function (currently line 271):

```typescript
  function handleToggleVisible(c: string) {
    setVisibleCollections((prev) =>
      prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]
    );
  }
```

- [ ] **Step 5: Thread new props to BottomBar**

Update the `<BottomBar ... />` JSX (currently lines 368–382) to add:

```tsx
      <BottomBar
        activeCollections={activeCollections}
        onToggleCollection={handleToggleCollection}
        translation={translation}
        onTranslationChange={setTranslation}
        quota={quota}
        onQuotaChange={handleQuotaChange}
        searchValue={searchValue}
        onSearchChange={(val) => {
          exploreTimerRef.current && clearTimeout(exploreTimerRef.current);
          setSearchValue(val);
        }}
        onSearch={() => handleSearch(searchValue)}
        loading={loading}
        isSearchActive={submittedQuery !== null}
        submittedCollections={submittedCollections}
        visibleCollections={visibleCollections}
        onToggleVisible={handleToggleVisible}
      />
```

- [ ] **Step 6: Thread new props to SearchResults**

Update the `<SearchResults ... />` JSX (currently lines 336–346) to pass `submittedCollections` and `visibleCollections`:

```tsx
          <SearchResults
            results={results}
            loading={loading}
            searchId={searchId}
            token={token ?? ""}
            onExploreMore={handleExploreMore}
            phase={searchPhase}
            submittedCollections={submittedCollections}
            visibleCollections={visibleCollections}
            isRestoring={isRestoring}
          />
```

- [ ] **Step 7: Remove the old all-zero-results inline message**

Remove lines 360–365 (the current `<p>No passages found...</p>` paragraph) — this will be replaced by `NoResultsScreen` in Task 6.

- [ ] **Step 8: TypeScript check**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -20
```
Expected: errors about `BottomBar` and `SearchResults` missing new props — those are resolved in Tasks 4 and 6. If other errors appear, fix them before continuing.

---

### Task 4: Create `ResultFilterBar` component

**Files:**
- Create: `apps/web/src/components/search/ResultFilterBar.tsx`

This is the post-search bottom bar content: slightly larger pills, one per searched collection, showing active/inactive state for `visibleCollections`. No quota control, no search bar.

- [ ] **Step 1: Create the file**

```tsx
"use client";

import { COLLECTIONS, getCollectionMeta } from "@/lib/collections";

interface ResultFilterBarProps {
  submittedCollections: string[];
  visibleCollections: string[];
  onToggleVisible: (c: string) => void;
}

export function ResultFilterBar({
  submittedCollections,
  visibleCollections,
  onToggleVisible,
}: ResultFilterBarProps) {
  const ordered = COLLECTIONS.filter((c) => submittedCollections.includes(c.key));

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[10px] font-medium uppercase tracking-widest text-brand-muted">
        Filter:
      </span>
      {ordered.map((col) => {
        const isVisible = visibleCollections.includes(col.key);
        return (
          <button
            key={col.key}
            onClick={() => onToggleVisible(col.key)}
            aria-pressed={isVisible}
            className={[
              "rounded-full px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent",
              isVisible
                ? "bg-brand-accent text-brand-bg"
                : "border border-brand-surface bg-brand-surface text-brand-muted hover:text-brand-primary",
            ].join(" ")}
          >
            {col.label}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -20
```
Expected: no new errors from this file.

---

### Task 5: Update `BottomBar` to be mode-aware

**Files:**
- Modify: `apps/web/src/components/search/BottomBar.tsx`

When `isSearchActive` is true, hide the search bar and quota control, show `ResultFilterBar` instead.

- [ ] **Step 1: Rewrite BottomBar**

Replace the entire file with:

```tsx
"use client";

import { CollectionToggles } from "./CollectionToggles";
import { QuotaControl } from "./QuotaControl";
import { SearchBar } from "./SearchBar";
import { ResultFilterBar } from "./ResultFilterBar";

interface BottomBarProps {
  // Pre-search
  activeCollections: string[];
  onToggleCollection: (c: string) => void;
  translation: string;
  onTranslationChange: (t: string) => void;
  quota: number;
  onQuotaChange: (q: number) => void;
  searchValue: string;
  onSearchChange: (v: string) => void;
  onSearch: () => void;
  loading: boolean;
  // Post-search
  isSearchActive: boolean;
  submittedCollections: string[];
  visibleCollections: string[];
  onToggleVisible: (c: string) => void;
}

export function BottomBar({
  activeCollections,
  onToggleCollection,
  translation,
  onTranslationChange,
  quota,
  onQuotaChange,
  searchValue,
  onSearchChange,
  onSearch,
  loading,
  isSearchActive,
  submittedCollections,
  visibleCollections,
  onToggleVisible,
}: BottomBarProps) {
  if (isSearchActive) {
    return (
      <div className="border-t border-brand-surface bg-brand-bg px-4 py-4 pb-5">
        <ResultFilterBar
          submittedCollections={submittedCollections}
          visibleCollections={visibleCollections}
          onToggleVisible={onToggleVisible}
        />
      </div>
    );
  }

  return (
    <div className="border-t border-brand-surface bg-brand-bg px-4 py-3 pb-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <CollectionToggles
          activeCollections={activeCollections}
          onToggle={onToggleCollection}
          translation={translation}
          onTranslationChange={onTranslationChange}
        />
        <QuotaControl value={quota} onChange={onQuotaChange} />
      </div>
      <SearchBar
        value={searchValue}
        onChange={onSearchChange}
        onSubmit={onSearch}
        loading={loading}
        disabled={activeCollections.length === 0}
      />
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -20
```
Expected: clean (the new props were already added in Task 3 Step 5).

- [ ] **Step 3: Commit Tasks 2–5 together**

```bash
git add apps/web/src/components/search/
git commit -m "feat(search): post-search filter bar, query bubble UX, rename explore-more button"
```

---

### Task 6: `NoResultsScreen` + threshold notices in `SearchResults`

**Files:**
- Create: `apps/web/src/components/search/NoResultsScreen.tsx`
- Modify: `apps/web/src/components/search/SearchResults.tsx`

Two cases:
1. **All-zero**: every searched collection returned 0 results → show `NoResultsScreen` (full explanation)
2. **Per-collection zero**: some collections have results but one or more do not → inline notice card per empty collection, rendered after the result cards

- [ ] **Step 1: Create `NoResultsScreen`**

```tsx
"use client";

import { getCollectionMeta } from "@/lib/collections";

interface NoResultsScreenProps {
  submittedCollections: string[];
  allFiltered: boolean; // true if user toggled all collections off
}

export function NoResultsScreen({ submittedCollections, allFiltered }: NoResultsScreenProps) {
  if (allFiltered) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
        <p className="text-brand-muted text-sm">
          Select at least one collection in the filter bar below to see results.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center max-w-lg mx-auto">
      <p className="text-brand-primary text-base font-medium mb-3">No passages met the threshold</p>
      <p className="text-brand-muted text-sm leading-relaxed mb-4">
        The relevance filter removes passages that don't closely match your query. None of the
        passages across{" "}
        {submittedCollections.length === 1
          ? getCollectionMeta(submittedCollections[0])?.label ?? submittedCollections[0]
          : `the ${submittedCollections.length} selected collections`}{" "}
        scored high enough to be shown.
      </p>
      <p className="text-brand-muted text-sm leading-relaxed">
        Try rephrasing your question, enabling additional collections, or increasing the
        passages-per-source quota.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Create `CollectionThresholdNotice` (inline, rendered per empty collection)**

Add this component to the top of `SearchResults.tsx` (before the main export):

```tsx
function CollectionThresholdNotice({ collectionKey }: { collectionKey: string }) {
  const meta = getCollectionMeta(collectionKey);
  return (
    <div className="rounded-lg border border-brand-surface bg-brand-surface/50 px-4 py-3 text-sm text-brand-muted">
      No passages from{" "}
      <span className="text-brand-primary font-medium">{meta?.label ?? collectionKey}</span>{" "}
      met the relevance threshold for this query.
    </div>
  );
}
```

- [ ] **Step 3: Rewrite `SearchResults`**

Replace the entire `SearchResults.tsx` with:

```tsx
"use client";

import { type ChunkResult } from "@/lib/api";
import { getCollectionMeta } from "@/lib/collections";
import { ChunkCard } from "./ChunkCard";
import { ResultsSkeleton } from "./ResultsSkeleton";
import { SearchProgress } from "./SearchProgress";
import { NoResultsScreen } from "./NoResultsScreen";

interface SearchResultsProps {
  results: ChunkResult[];
  loading: boolean;
  searchId: string | null;
  token: string;
  onExploreMore: (content: string, label: string) => void;
  phase?: "searching" | "ranking" | null;
  submittedCollections: string[];
  visibleCollections: string[];
  isRestoring?: boolean;
}

function CollectionThresholdNotice({ collectionKey }: { collectionKey: string }) {
  const meta = getCollectionMeta(collectionKey);
  return (
    <div className="rounded-lg border border-brand-surface bg-brand-surface/50 px-4 py-3 text-sm text-brand-muted">
      No passages from{" "}
      <span className="text-brand-primary font-medium">{meta?.label ?? collectionKey}</span>{" "}
      met the relevance threshold for this query.
    </div>
  );
}

export function SearchResults({
  results,
  loading,
  searchId,
  token,
  onExploreMore,
  phase = null,
  submittedCollections,
  visibleCollections,
  isRestoring = false,
}: SearchResultsProps) {
  if (loading && results.length === 0) {
    return isRestoring
      ? <ResultsSkeleton />
      : <SearchProgress phase={phase} collections={submittedCollections} />;
  }

  // Collections that were searched but returned 0 results (threshold filtered them all out)
  const collectionsWithResults = new Set(results.map((r) => r.source.collection));
  const emptyCollections = !loading
    ? submittedCollections.filter((c) => !collectionsWithResults.has(c))
    : [];

  // Filter to what the user wants to see
  const visibleResults = results.filter((r) => visibleCollections.includes(r.source.collection));

  // All-zero: no results at all from any searched collection (search is done)
  if (!loading && results.length === 0 && submittedCollections.length > 0) {
    return <NoResultsScreen submittedCollections={submittedCollections} allFiltered={false} />;
  }

  // User toggled all collections off
  if (!loading && results.length > 0 && visibleCollections.length === 0) {
    return <NoResultsScreen submittedCollections={submittedCollections} allFiltered={true} />;
  }

  return (
    <div className="space-y-3">
      {visibleResults.map((result, index) => (
        <ChunkCard
          key={result.chunk_id}
          result={result}
          index={index}
          searchId={searchId}
          token={token}
          onExploreMore={onExploreMore}
        />
      ))}
      {emptyCollections.map((col) => (
        <CollectionThresholdNotice key={col} collectionKey={col} />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -20
```
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/search/NoResultsScreen.tsx apps/web/src/components/search/SearchResults.tsx
git commit -m "feat(search): threshold notices, no-results screen, per-collection visibility filtering"
```

---

## Self-Review Checklist

### Spec coverage

| Requirement | Task |
|---|---|
| Search bar disappears after search starts | Task 5 — BottomBar `isSearchActive` hides SearchBar |
| Query becomes bubble at top | Already rendered in SearchPage (query bubble JSX exists); hiding the bar makes it the natural focus |
| Buttons slightly larger at bottom | Task 4 — `px-4 py-1.5 text-sm` vs old `px-3 py-1 text-xs` |
| Only searched-collection buttons at bottom post-search | Task 4 — `ResultFilterBar` uses `submittedCollections` |
| "Sources" label → conveys filtering functionality | Task 4 — label is `"Filter:"` |
| Toggle buttons to control which sources are visible | Tasks 3+4+6 — `visibleCollections` state + `handleToggleVisible` + `SearchResults` filters |
| Default: all sources that were requested appear | Task 3 — `visibleCollections` initializes to `submittedCollections` |
| Threshold notice for collection with no results | Task 6 — `CollectionThresholdNotice` + `emptyCollections` logic |
| No-results screen when all collections return 0 | Task 6 — `NoResultsScreen` with `allFiltered=false` |
| No-results when user toggles all collections off | Task 6 — `NoResultsScreen` with `allFiltered=true` |
| "Query more sources like this" (no emoji) | Task 2 — ChunkCard button text |
| Staggered explanation requests (600ms, score order) | Task 1 — pipeline.py stagger |

### Potential issues to watch

- **`collections` prop removed from `SearchResults`**: `SearchProgress` now receives `submittedCollections` instead of `activeCollections` — this is correct since during loading those are the same value.
- **Restore flow**: When restoring a past search (`isRestoring=true`), `submittedCollections` will be `[]` (never set). The restore flow sets `submittedQuery`, which makes `isSearchActive=true`, meaning the filter bar shows with 0 pills. Fix: in the restore flow (SearchPage `getSearchResults.then()`), also set `submittedCollections` from the restored `filters.collections` if available, otherwise from `ALL_COLLECTION_KEYS`. Add this to Task 3.

### Restore flow fix (add to Task 3 Step 2 area)

In `SearchPage.tsx`, inside the `.then((data) => { ... })` callback of the restore flow (around line 158), after `setSubmittedQuery(data.query)`, add:

```typescript
        const restoredCols: string[] =
          Array.isArray((data as any).filters?.collections)
            ? (data as any).filters.collections
            : ALL_COLLECTION_KEYS;
        setSubmittedCollections(restoredCols);
        setVisibleCollections(restoredCols);
```

Note: `SearchResultsResponse` doesn't currently include `filters`. Check `getSearchResults` return type. If `filters` is not on the type, use `ALL_COLLECTION_KEYS` as fallback — the restore will show all collection filter buttons, which is acceptable. The safe fallback is:

```typescript
        setSubmittedCollections(ALL_COLLECTION_KEYS);
        setVisibleCollections(ALL_COLLECTION_KEYS);
```

Add this after `setSubmittedQuery(data.query)` in the restore then-block.
