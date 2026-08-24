# Codebase Issue Inventory

> **Superseded inventory.** Paths and operational conclusions below describe the
> repository on 2026-06-10. Use [`datapipeline/README.md`](../datapipeline/README.md)
> for current collection publication and repair guidance.

Date: 2026-06-10

This file lists possible issues found during a senior-engineer read of the repository. It is intentionally an inventory, not a fix plan. Severity reflects likely product or maintenance impact.

## High Priority

### Bible Translation Contract Is Not End-To-End

- Frontend exposes `CPDV` and `douay-rheims` as Bible translation choices.
- API validates only `CPDV` and `douay-rheims`.
- Current Bible ingestion defaults to `WEB-C`.
- Retrieval filters by collection only and does not filter `documents.translation` or chunk metadata.
- User impact: changing Bible translation may not change search results.

Relevant files:
- `apps/web/src/components/search/TranslationSelector.tsx`
- `services/api/app/routes/search.py`
- `services/api/app/routes/preferences.py`
- `services/api/app/rag/retrieve.py`
- `datapipeline/ingest/bible.py`

### Search Quota May Be Exceeded After Reranking

- Search accepts quota values of 3, 4, or 5 per source.
- Retrieval fetches `quota * candidate_multiplier` candidates.
- Reranking returns all scored chunks.
- Pipeline keeps every included chunk after reranking and does not cap results back to quota per collection.
- User impact: result counts and LLM explanation costs can exceed the UI contract.

Relevant files:
- `services/api/app/rag/pipeline.py`
- `services/api/app/rag/retrieve.py`
- `services/api/app/rag/rerank.py`

### Existing User Preferences Can Drift From Current Collections

- Migration `0010` removes `saints` and adds `summa` to the default collection list.
- It updates the default for new rows only.
- Existing `user_preferences.default_collections` rows may still contain `saints` and may not include `summa`.
- User impact: older users can have stale or invalid source selections.

Relevant files:
- `supabase/migrations/0010_chunks_metadata.sql`
- `services/api/app/routes/preferences.py`
- `apps/web/src/lib/collections.ts`

### Production Example Env Files Contain Concrete-Looking Values

- Production example files include a real-looking Supabase project URL/ref and anon key.
- They also contain a real-looking `INTERNAL_API_SECRET` value.
- Even if intended as example data, this increases the chance of accidentally reusing committed credentials.
- Operational impact: any value ever used from these files should be rotated.

Relevant files:
- `apps/web/.env.production.example`
- `services/api/.env.production.example`

## Medium Priority

### JWKS Cache Can Stampede On Stale Cache

- `get_jwks()` checks cache staleness before acquiring the lock.
- The remote fetch happens outside the lock.
- Multiple concurrent requests can all observe stale cache and fetch JWKS simultaneously.
- Operational impact: unnecessary load and possible latency spikes during key refresh.

Relevant file:
- `services/api/app/auth/jwks.py`

### V1 Chat And V2 Search Share Rate-Limit Counters

- Chat and search both use `user_usage.rate_count` and `quota_count`.
- V1 and V2 have different configured limits.
- Existing TODO notes this cross-contamination.
- User impact: chat use can consume search quota and search use can consume chat quota.

Relevant files:
- `services/api/app/deps/rate_limit.py`
- `services/api/app/routes/search.py`
- `supabase/migrations/0003_user_usage.sql`

### Documentation Drift

- `CLAUDE.md` still describes some items as pending or planned that are present in migrations/code.
- `PROGRESS.md` and current git history indicate later work than parts of `CLAUDE.md`.
- Datapipeline README still mentions migration `0008` as a current gate even though later migrations exist.
- Maintenance impact: future agents or engineers can make bad decisions from stale architecture notes.

Relevant files:
- `CLAUDE.md`
- `PROGRESS.md`
- `datapipeline/README.md`

### Sources And Search Metadata Are Not Fully Consistent

- Search result `ChunkSource` has optional metadata on the frontend type.
- Backend search result construction does not consistently include chunk metadata.
- Bible translation badge logic expects `source.metadata.translation`, but search results may not provide it.
- User impact: source badges and translation labels can be incomplete or misleading.

Relevant files:
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/search/ChunkCard.tsx`
- `services/api/app/models/search.py`
- `services/api/app/rag/pipeline.py`
- `services/api/app/routes/search.py`

### Search Progress Hardcodes Corpus Size

- Search progress displays `Searching 30,325 passages`.
- This value is not derived from the database.
- User impact: UI can become inaccurate as ingestion changes.

Relevant file:
- `apps/web/src/components/search/SearchProgress.tsx`

### Frontend Has No Test Coverage

- No frontend test files were found.
- Critical behavior such as SSE parsing, search state, restore flow, and preference persistence is untested.
- Maintenance impact: UI regressions are likely as state interactions grow.

Relevant area:
- `apps/web/src`

### Backend Tests Are Narrow

- Existing API tests cover selected helper/error behavior.
- There is little coverage of full `/v1/search` streaming, persistence, translation filtering, rate limits, or reader/bookmark flows.
- Maintenance impact: cross-route contract bugs can survive refactors.

Relevant area:
- `services/api/tests`

## Lower Priority / Polish

### Core UI Controls Use Emoji

- Bookmark, copy, feedback, search, and source labels use emoji directly.
- This can be acceptable for a prototype but is less controlled than an icon system.
- Product impact: inconsistent rendering across platforms and weaker accessibility/polish.

Relevant areas:
- `apps/web/src/components/search`
- `apps/web/src/components/reader`
- `apps/web/src/components/bookmarks`
- `apps/web/src/lib/collections.ts`

### Hardcoded Hex Values Remain In Frontend Auth Styling

- Most components use Tailwind brand tokens.
- `LoginForm` hardcodes hex colors for Supabase Auth UI.
- This is a small violation of the design-system invariant.

Relevant file:
- `apps/web/src/components/auth/LoginForm.tsx`

### Mobile Layout Looks Underdeveloped

- Sidebar is fixed-width and always rendered inside `AppShell`.
- Several result/reader layouts assume desktop space.
- Product impact: mobile usability may be poor even if pages technically render.

Relevant files:
- `apps/web/src/components/layout/AppShell.tsx`
- `apps/web/src/components/layout/Sidebar.tsx`
- `apps/web/src/components/search/SearchPage.tsx`
- `apps/web/src/components/reader/DocumentReader.tsx`

### Datapipeline Is Script-Like Rather Than Package-Like

- Ingestion scripts use `sys.path.insert` to import local modules.
- This is workable for scripts but brittle for tooling and reuse.
- Maintenance impact: imports and test setup are more fragile than a package layout.

Relevant area:
- `datapipeline`

### Datapipeline Includes A Removed `saints` Ingestion Script

- Migration `0010` removes `saints` from the collection constraint and deletes saints data.
- `datapipeline/ingest/saints.py` still exists and writes `collection="saints"`.
- `run_all.py` no longer runs it, but the standalone script can still be invoked and fail against current schema.

Relevant files:
- `datapipeline/ingest/saints.py`
- `datapipeline/run_all.py`
- `supabase/migrations/0010_chunks_metadata.sql`

### Summa Metadata Is Parsed But Not Persisted By Summa Ingest

- `parse_thml()` produces metadata for Summa chunks.
- `datapipeline/ingest/summa.py` ignores `_meta` when upserting chunks.
- Search may still work, but richer reader/source behavior loses structured metadata.

Relevant files:
- `datapipeline/ingest/common.py`
- `datapipeline/ingest/summa.py`

## Open Questions

- Should Bible translation support be `WEB-C`, `CPDV`, `douay-rheims`, or all three?
- Should `quota` mean max per selected collection or only a retrieval/ranking hint?
- Should old user preferences be normalized on read, by migration, or both?
- Should `/sources` be public/authenticated-only? It currently requires auth.
- Is V1 chat still a supported product surface, or should it remain hidden behind `/chat -> /search`?
