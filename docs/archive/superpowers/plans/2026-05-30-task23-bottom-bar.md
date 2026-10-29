# Task 23 — Search Page Bottom Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "Code of Canon Law" to all infrastructure layers and build the five bottom-bar components (CollectionToggles, TranslationSelector, QuotaControl, SearchBar, BottomBar) for the V2 search page.

**Architecture:** Canon Law is added to the backend allowlists and a new DB migration file before any frontend work. Frontend components are built leaf-first (TranslationSelector → QuotaControl → SearchBar → CollectionToggles → BottomBar), each a self-contained "use client" component. State lives in the parent (BottomBar/SearchPage); children call `useAppContext()` for the token and debounce preference saves internally.

**Tech Stack:** Next.js 16, React 19, TypeScript (strict), Tailwind CSS v4, FastAPI (Python), Supabase Postgres

---

## File Map

| Action | Path |
|--------|------|
| CREATE | `supabase/migrations/0007_add_canon_law_collection.sql` |
| MODIFY | `services/api/app/routes/search.py` |
| MODIFY | `services/api/app/routes/preferences.py` |
| MODIFY | `services/api/app/rag/pipeline.py` |
| CREATE | `apps/web/src/lib/collections.ts` |
| CREATE | `apps/web/src/components/search/TranslationSelector.tsx` |
| CREATE | `apps/web/src/components/search/QuotaControl.tsx` |
| CREATE | `apps/web/src/components/search/SearchBar.tsx` |
| CREATE | `apps/web/src/components/search/CollectionToggles.tsx` |
| CREATE | `apps/web/src/components/search/BottomBar.tsx` |
| CREATE | `apps/web/src/components/search/index.ts` |

---

## Task 1: Canon Law Infrastructure

**Files:**
- Create: `supabase/migrations/0007_add_canon_law_collection.sql`
- Modify: `services/api/app/routes/search.py`
- Modify: `services/api/app/routes/preferences.py`
- Modify: `services/api/app/rag/pipeline.py`

- [ ] **Step 1: Create the migration file**

Create `supabase/migrations/0007_add_canon_law_collection.sql` with this exact content:

```sql
-- Expand the documents.collection allowlist to include canon-law.
-- PostgreSQL auto-named the inline constraint 'documents_collection_check'.

alter table documents drop constraint if exists documents_collection_check;

alter table documents
  add constraint documents_collection_check
  check (collection in ('bible', 'catechism', 'church-fathers', 'encyclicals', 'canon-law', 'saints'));

-- Update default for new user_preferences rows (existing rows keep their stored value).
alter table user_preferences
  alter column default_collections
  set default '{bible,catechism,church-fathers,encyclicals,canon-law,saints}';
```

> **Note:** This file is ready to apply to Supabase (via the dashboard SQL editor or `supabase db push`). The migration only affects the schema allowlist and the default for new preference rows — no existing data is changed.

- [ ] **Step 2: Update `routes/search.py` — add canon-law to allowlist**

Open `services/api/app/routes/search.py`. Line 26 currently reads:
```python
_VALID_COLLECTIONS = {"bible", "catechism", "church-fathers", "encyclicals", "saints"}
```
Change it to:
```python
_VALID_COLLECTIONS = {"bible", "catechism", "church-fathers", "encyclicals", "canon-law", "saints"}
```

- [ ] **Step 3: Update `routes/preferences.py` — two lines**

Open `services/api/app/routes/preferences.py`.

Line 14 currently reads:
```python
_VALID_COLLECTIONS = {"bible", "catechism", "church-fathers", "encyclicals", "saints"}
```
Change to:
```python
_VALID_COLLECTIONS = {"bible", "catechism", "church-fathers", "encyclicals", "canon-law", "saints"}
```

Line 19 currently reads:
```python
    default_collections=["bible", "catechism", "church-fathers", "encyclicals", "saints"],
```
Change to:
```python
    default_collections=["bible", "catechism", "church-fathers", "encyclicals", "canon-law", "saints"],
```

- [ ] **Step 4: Update `rag/pipeline.py` — add canon-law to allowlist**

Open `services/api/app/rag/pipeline.py`. Line 38 currently reads:
```python
    VALID_COLLECTIONS = {"bible", "catechism", "church-fathers", "encyclicals", "saints"}
```
Change to:
```python
    VALID_COLLECTIONS = {"bible", "catechism", "church-fathers", "encyclicals", "canon-law", "saints"}
```

- [ ] **Step 5: Verify Python syntax on all three modified files**

Run from the repo root:
```bash
python3 -c "import ast, sys; [ast.parse(open(f).read()) for f in sys.argv[1:]]" \
  services/api/app/routes/search.py \
  services/api/app/routes/preferences.py \
  services/api/app/rag/pipeline.py && echo "OK — no syntax errors"
```
Expected output: `OK — no syntax errors`

- [ ] **Step 6: Commit**

```bash
git add supabase/migrations/0007_add_canon_law_collection.sql \
        services/api/app/routes/search.py \
        services/api/app/routes/preferences.py \
        services/api/app/rag/pipeline.py
git commit -m "feat: add canon-law collection to allowlists and migration 0007"
```

---

## Task 2: Collection Metadata Constants

**Files:**
- Create: `apps/web/src/lib/collections.ts`

- [ ] **Step 1: Create `collections.ts`**

Create `apps/web/src/lib/collections.ts` with this exact content:

```typescript
export interface CollectionMeta {
  key: string;
  label: string;
  color: string;
}

export const COLLECTIONS: CollectionMeta[] = [
  { key: "bible",          label: "📖 Bible",         color: "#4caf50" },
  { key: "catechism",      label: "⛪ Catechism",      color: "#4a6fa5" },
  { key: "church-fathers", label: "✝ Church Fathers", color: "#7c6fa5" },
  { key: "encyclicals",    label: "📜 Encyclicals",    color: "#b5892a" },
  { key: "canon-law",      label: "⚖️ Canon Law",      color: "#9e4a4a" },
  { key: "saints",         label: "👼 Saints",         color: "#4a9a8a" },
];

export const ALL_COLLECTION_KEYS: string[] = COLLECTIONS.map((c) => c.key);

export function getCollectionMeta(key: string): CollectionMeta | undefined {
  return COLLECTIONS.find((c) => c.key === key);
}
```

- [ ] **Step 2: Type-check**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -30
```
Expected: no output (zero errors). If errors appear, fix before continuing.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/lib/collections.ts
git commit -m "feat: add collection metadata constants (keys, labels, colors)"
```

---

## Task 3: TranslationSelector Component

**Files:**
- Create: `apps/web/src/components/search/TranslationSelector.tsx`

- [ ] **Step 1: Create component**

Create `apps/web/src/components/search/TranslationSelector.tsx`:

```typescript
"use client";

import { useEffect, useRef } from "react";

const TRANSLATIONS = [
  { value: "CPDV",         label: "CPDV (default)" },
  { value: "douay-rheims", label: "Douay-Rheims" },
];

interface TranslationSelectorProps {
  value: string;
  onChange: (translation: string) => void;
  onClose: () => void;
}

export function TranslationSelector({
  value,
  onChange,
  onClose,
}: TranslationSelectorProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleMouseDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleMouseDown);
    return () => document.removeEventListener("mousedown", handleMouseDown);
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute bottom-[calc(100%+6px)] left-0 z-20 min-w-[160px] overflow-hidden rounded-lg border border-brand-surface bg-brand-surface shadow-lg"
    >
      {TRANSLATIONS.map((t) => (
        <button
          key={t.value}
          onClick={() => {
            onChange(t.value);
            onClose();
          }}
          className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-brand-primary transition-colors hover:bg-brand-bg"
        >
          <span className={value === t.value ? "text-brand-accent" : "invisible"}>
            ✓
          </span>
          {t.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -30
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/search/TranslationSelector.tsx
git commit -m "feat(search): TranslationSelector dropdown component"
```

---

## Task 4: QuotaControl Component

**Files:**
- Create: `apps/web/src/components/search/QuotaControl.tsx`

- [ ] **Step 1: Create component**

Create `apps/web/src/components/search/QuotaControl.tsx`:

```typescript
"use client";

import { useEffect } from "react";
import { useAppContext } from "@/components/layout/AppShell";
import { updatePreferences } from "@/lib/api";

const QUOTA_OPTIONS = [3, 4, 5] as const;

interface QuotaControlProps {
  value: number;
  onChange: (quota: number) => void;
}

export function QuotaControl({ value, onChange }: QuotaControlProps) {
  const { token } = useAppContext();

  useEffect(() => {
    if (!token) return;
    const timer = setTimeout(() => {
      updatePreferences(token, { default_quota: value }).catch(() => {});
    }, 500);
    return () => clearTimeout(timer);
  }, [value, token]);

  return (
    <div className="flex shrink-0 items-center gap-2">
      <span className="text-[10px] font-medium uppercase tracking-widest text-brand-muted">
        Per source:
      </span>
      <div className="flex overflow-hidden rounded-md border border-brand-surface">
        {QUOTA_OPTIONS.map((q, i) => (
          <button
            key={q}
            onClick={() => onChange(q)}
            className={[
              "px-3 py-1 text-xs transition-colors",
              i < QUOTA_OPTIONS.length - 1 ? "border-r border-brand-surface" : "",
              value === q
                ? "bg-brand-accent font-semibold text-brand-bg"
                : "bg-brand-surface text-brand-muted hover:text-brand-primary",
            ].join(" ")}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -30
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/search/QuotaControl.tsx
git commit -m "feat(search): QuotaControl segmented [3|4|5] component"
```

---

## Task 5: SearchBar Component

**Files:**
- Create: `apps/web/src/components/search/SearchBar.tsx`

- [ ] **Step 1: Create component**

Create `apps/web/src/components/search/SearchBar.tsx`:

```typescript
"use client";

import type { KeyboardEvent } from "react";

interface SearchBarProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  loading: boolean;
  disabled: boolean;
}

export function SearchBar({
  value,
  onChange,
  onSubmit,
  loading,
  disabled,
}: SearchBarProps) {
  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !loading && !disabled) {
      onSubmit();
    }
  }

  const isDisabled = disabled || loading;
  const placeholder = disabled
    ? "Select at least one source to search."
    : "Ask a question or explore a theme…";

  return (
    <div className="flex gap-2">
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={isDisabled}
        className="flex-1 rounded-lg border border-brand-surface bg-brand-surface px-4 py-2.5 text-sm text-brand-primary placeholder:text-brand-muted outline-none focus:border-brand-accent transition-colors disabled:opacity-50"
      />
      <button
        onClick={onSubmit}
        disabled={isDisabled}
        title={disabled ? "Select at least one source to search." : undefined}
        className="flex items-center gap-2 rounded-lg bg-brand-accent px-5 py-2.5 text-sm font-semibold text-brand-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {loading ? (
          <>
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-brand-bg border-t-transparent" />
            Searching…
          </>
        ) : (
          "Search"
        )}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -30
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/search/SearchBar.tsx
git commit -m "feat(search): SearchBar component with loading and disabled states"
```

---

## Task 6: CollectionToggles Component

**Files:**
- Create: `apps/web/src/components/search/CollectionToggles.tsx`

- [ ] **Step 1: Create component**

Create `apps/web/src/components/search/CollectionToggles.tsx`:

```typescript
"use client";

import { useEffect, useState } from "react";
import { useAppContext } from "@/components/layout/AppShell";
import { updatePreferences } from "@/lib/api";
import { COLLECTIONS } from "@/lib/collections";
import { TranslationSelector } from "./TranslationSelector";

interface CollectionTogglesProps {
  activeCollections: string[];
  onToggle: (collection: string) => void;
  translation: string;
  onTranslationChange: (t: string) => void;
}

export function CollectionToggles({
  activeCollections,
  onToggle,
  translation,
  onTranslationChange,
}: CollectionTogglesProps) {
  const { token } = useAppContext();
  const [translationOpen, setTranslationOpen] = useState(false);

  // Debounced sync: when activeCollections changes, persist after 500ms
  useEffect(() => {
    if (!token) return;
    const timer = setTimeout(() => {
      updatePreferences(token, { default_collections: activeCollections }).catch(() => {});
    }, 500);
    return () => clearTimeout(timer);
  }, [activeCollections, token]);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-[10px] font-medium uppercase tracking-widest text-brand-muted">
        Sources:
      </span>

      {COLLECTIONS.map((col) => {
        const isActive = activeCollections.includes(col.key);
        const isBible = col.key === "bible";

        if (isBible) {
          return (
            <div key={col.key} className="relative">
              {/* Split-button pill: left = toggle, right = translation dropdown */}
              <div
                className={[
                  "flex items-center rounded-full text-xs font-medium transition-colors",
                  isActive
                    ? "bg-brand-accent text-brand-bg"
                    : "border border-brand-surface bg-brand-surface text-brand-muted",
                ].join(" ")}
              >
                <button
                  onClick={() => onToggle(col.key)}
                  className="flex items-center gap-1 py-1 pl-3 pr-1.5"
                >
                  {col.label}
                </button>
                <button
                  onClick={() => setTranslationOpen((o) => !o)}
                  aria-label="Select Bible translation"
                  className="py-1 pr-2 text-[9px] transition-opacity hover:opacity-70"
                >
                  ▾
                </button>
              </div>

              {translationOpen && (
                <TranslationSelector
                  value={translation}
                  onChange={(t) => {
                    onTranslationChange(t);
                    if (token) {
                      updatePreferences(token, { preferred_translation: t }).catch(() => {});
                    }
                  }}
                  onClose={() => setTranslationOpen(false)}
                />
              )}
            </div>
          );
        }

        return (
          <button
            key={col.key}
            onClick={() => onToggle(col.key)}
            className={[
              "rounded-full px-3 py-1 text-xs font-medium transition-colors",
              isActive
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

- [ ] **Step 2: Type-check**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -30
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/search/CollectionToggles.tsx
git commit -m "feat(search): CollectionToggles pill row with Bible translation dropdown"
```

---

## Task 7: BottomBar Component + Barrel Export

**Files:**
- Create: `apps/web/src/components/search/BottomBar.tsx`
- Create: `apps/web/src/components/search/index.ts`

- [ ] **Step 1: Create BottomBar**

Create `apps/web/src/components/search/BottomBar.tsx`:

```typescript
"use client";

import { CollectionToggles } from "./CollectionToggles";
import { QuotaControl } from "./QuotaControl";
import { SearchBar } from "./SearchBar";

interface BottomBarProps {
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
}: BottomBarProps) {
  const noCollections = activeCollections.length === 0;

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
        disabled={noCollections}
      />
    </div>
  );
}
```

- [ ] **Step 2: Create barrel export**

Create `apps/web/src/components/search/index.ts`:

```typescript
export { BottomBar } from "./BottomBar";
export { CollectionToggles } from "./CollectionToggles";
export { QuotaControl } from "./QuotaControl";
export { SearchBar } from "./SearchBar";
export { TranslationSelector } from "./TranslationSelector";
```

- [ ] **Step 3: Final type-check**

```bash
cd apps/web && npx tsc --noEmit 2>&1 | head -30
```
Expected: no output.

- [ ] **Step 4: Full build check**

```bash
cd apps/web && npm run build 2>&1 | tail -20
```
Expected: build completes successfully (the new components are never imported by any page yet, so Next.js may report them as unused — that is fine; look for zero TypeScript errors and zero build failures).

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/search/BottomBar.tsx \
        apps/web/src/components/search/index.ts
git commit -m "feat(search): BottomBar wrapper + barrel export — Task 23 complete"
```

---

## Post-Task Verification Checklist

After all tasks are committed, confirm the following before closing Task 23:

- [ ] `git log --oneline -7` shows 7 clean commits for this task (Tasks 1–7)
- [ ] `cd apps/web && npx tsc --noEmit` exits with no errors
- [ ] `apps/web/src/components/search/` contains: `index.ts`, `BottomBar.tsx`, `CollectionToggles.tsx`, `QuotaControl.tsx`, `SearchBar.tsx`, `TranslationSelector.tsx`
- [ ] `apps/web/src/lib/collections.ts` exists with all 6 collection entries including `canon-law`
- [ ] `supabase/migrations/0007_add_canon_law_collection.sql` exists
- [ ] All three backend `_VALID_COLLECTIONS` sets include `"canon-law"`
- [ ] Security agent review complete (no new vulnerabilities introduced)
- [ ] PROGRESS.md updated: Task 23 marked complete, Task 24 marked as next
