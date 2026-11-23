# Project Rules & Invariants

> This file is the repo-wide source of agent guidance. The root `AGENTS.md` is a
> symlink to it — edit this file, never a copy. (They were separate files until
> 2026-09-17; the fork drifted 18 migrations out of date and is why they are one file now.)
>
> One scoped file exists below the root: **`apps/web/AGENTS.md`**, a real file covering
> frontend-only rules. It points back at the sections here rather than restating them —
> when a rule in §1, §9, §10–§14 or §18 changes, check whether it needs updating too.

This repository (body-of-christ) implements a Catholic theology RAG search application.
The user-facing product name is **TheoCorpus**.
All changes MUST respect the following architectural, security, and design constraints.

---

## 0. Quick Commands

```bash
# Frontend (apps/web)
npm run dev            # dev server on :3000
npm run build          # production build
npm run lint           # ESLint — the repo baseline is ZERO errors
npm test               # vitest run

# Backend (services/api) — deps in pyproject.toml; `python3` on this machine
uvicorn app.main:app --reload   # dev server on :8000
python3 -m pytest tests/

# Datapipeline. run_collection.py only dry-runs (builds and checks, writes nothing).
# Publishing is publish.py stage -> report -> apply -> cleanup, with rollback the only
# undo (2.2w); every live step needs a PUBLISH_LOCK.json entry and --release
cd datapipeline && python3 run_collection.py --collection bible --dry-run
cd datapipeline && python3 publish.py stage --collection bible --release <name>

# Datapipeline tests, in parallel (pytest-xdist). `-n auto` sizes the workers by free
# memory, not CPU count (tests/conftest.py); loadscope builds each module's fixtures once.
# With the sources about 6 min on the Lenovo, against 22 serially. A serial run
# (`python3 -m pytest tests`) is still fine and gives the same results.
cd datapipeline && python3 -m pytest tests -n auto --dist loadscope

# Docker (prod-like)
docker build -t theocorpus-api services/api
docker run --env-file services/api/.env -p 8000:8000 theocorpus-api
```

For a publish, a rollback or a store repair, read `datapipeline/README.md` before running
commands.

---

## 1. Fixed Architecture (DO NOT CHANGE)

- Monorepo with separate deploy targets:
  - `apps/web`            → Next.js (TypeScript), deployed on Vercel
  - `services/api`        → Python FastAPI, Docker
  - `supabase/migrations` → SQL migrations only
  - `datapipeline/`       → standalone Python scripts (run locally/CI, not deployed)

- **Supabase** — Postgres (RLS, FTS via `search_vector` GIN index) + Auth
- **Qdrant** — vector store for cosine-similarity search (HNSW). Embeddings live here, NOT in pgvector.
- The frontend NEVER talks directly to the database.
- ALL client data access goes through FastAPI.
- **The frontend NEVER calls the API host directly from the browser.** All API calls go through the Vercel proxy at `apps/web/src/app/v1/[...path]/route.ts`, which forwards using the server-side `API_URL` env var. This is intentional — it avoids CORS, keeps the API host private, and allows `x-internal-secret` to be added server-side.
- **`const API_URL = ""` in `apps/web/src/lib/api.ts` is correct and intentional.** The empty string causes all fetch calls to use relative paths (`/v1/...`), which hit the Vercel proxy. Keep it empty. The env var that matters is server-side `API_URL` (no `NEXT_PUBLIC_` prefix), used only by the proxy route.
- **`NEXT_PUBLIC_API_URL` is used only in `next.config.ts` for CSP headers.** It does NOT control where API calls are routed. Keep it out of `api.ts`.

---

## 2. Authentication & Authorization (CRITICAL)

- Auth via Supabase Auth; frontend sends JWT as `Authorization: Bearer <token>`.
- Backend verifies the Supabase JWT (signature, expiration, issuer) and extracts `user_id` from `sub`. Implementation is the `app/auth/` package — `jwks.py` (key cache) and `verify.py`.
- RLS MUST be enabled on all user-owned tables.
- Supabase service role key MUST NEVER appear in frontend code.
- **Guests** are a separate audience with no Supabase user: a guest session token grants a limited search trial, and guest work is claimed into a real account on signup (`POST /v1/guest/claim`). Guest state lives in `guest_trials` and the guest continuity/transfer columns; it is never a JWT identity.

---

## 3. API Design (STABILITY REQUIRED)

All endpoints under `/v1/...`. The routes are listed in §10.

The V1 chat API (`POST /v1/chat`, `/chat/stream`, `/sessions`) had no live caller and was
removed in October 2026, with its browser client. The `/chat` page still redirects old
links to `/search`.

---

## 4. Data Model

SQL migrations ONLY. Schema changes must be additive. RLS on all user-owned tables.

### Core (V1)
- `user_usage` — the search rate-limit counters
- `chat_sessions`, `chat_messages` — no longer written since the V1 chat API was removed;
  the tables and rows stay until a migration drops them

### Search corpus & activity (V2)
- `documents` (id, collection, title, author, year, translation, metadata jsonb)
- `chunks` (id, document_id, content, position, anchor, chapter_key, chapter_label, unit_label, reference, search_vector tsvector, annotation, annotation_vector tsvector, content_embedding vector, annotation_embedding)
- `searches`, `retrievals`, `bookmarks`, `user_preferences`
  (`chunk_feedback` was dropped and replaced by `retrieval_labels` in 0022)

### Later additions
- `compare_runs` — runs of the removed HTTP retrieval lab (0018, 0020, 0026); no longer
  written. `scripts/run_eval_suite.py` writes its results to JSONL files instead
- `retrieval_labels` — human relevance labels (0022, 0024)
- `guest_trials` — guest session quota + continuity + transfer readiness (0023, 0025, 0026, 0027)
- `guest_trial_retrievals` — guest results, held apart from `retrievals` until
  `POST /v1/guest/claim` transfers them (0026_guest_onboarding_continuity). Read by
  `routes/guest_search.py` and the guest reader path in `routes/documents.py`.
- `reading_progress` — per-document reader position (0027)
- `product_feedback` — in-app feedback, including anonymous (0028–0030)
- `user_preferences.last_standard_quota` — remembers the pre-focused quota (0034); see §18
- `search_costs` — per-search provider cost, written best-effort from the SSE generator's
  `finally` in `rag/pipeline.py`, so it covers every exit including a client leaving
  mid-explanations (`completed = false`), for authenticated and guest searches (0036).
  No user_id, no query text; RLS on with no policies. Numbered 0036 to stay clear of the
  0035 studies draft. The API tolerates the table being absent until it is applied.
- `documents.chunk_count`, `document_chapters` — the precomputed **reader outline**
  (0037 schema, 0038 backfill). `/toc`, `/reader`, `/documents/{id}` and `/sources` read
  it instead of deriving chapter lists and counts from `chunks` per request.
  `chunk_count IS NULL` means "no current outline" and the routes fall back to the old
  derivation. `refresh_document_outline(doc)` builds it; 2.2w's apply calls it last for every
  document it touches, and a stage builds
  staged outlines with `staging.refresh_document_outline`
  (`reader_writer.write_staged_document`). Row triggers on `chunks` reset
  `chunk_count` to NULL on any structural change (chunk set, position, chapter key or
  label, or TRUNCATE; annotations are ignored), so a writer that skips the refresh can
  only make a document slower, never stale, unless it bypasses triggers
  (`session_replication_role = replica`). Anything that rewrites chunks should still
  call the refresh afterwards. The API also tolerates a database without 0037.
- `document_contents` — a document's **contents tree** (0040, issue #250): the hierarchy
  of its headings (Part > Question > Article), one pre-ordered row per node, each opening
  a chapter (`chapter_key`) and optionally a passage (`anchor`). Distinct from the reader
  outline above, which stays the flat list of load units. A source adapter emits it as
  `Document.contents`; `contents.check` refuses a broken tree in the build (dry runs
  included), and a stage writes it into `staging.document_contents` with the chunks
  (`reader_writer.write_staged_document`), for the apply to carry into live. `/toc`
  returns it as `contents` only when every node's chapter and anchor still exist in
  reading order (`_contents_tree` in `routes/documents.py`), so a writer that rewrites
  chunks without the tree degrades the reader to the flat list. The API tolerates the
  table being absent. The Summa adapter builds its tree (Part > Treatise > Question >
  Article, keyed by div id; `build_contents` in `ingest/summa.py`, #254); it reached
  readers with the Phase 4 republish (20 Nov 2026, 3,775 nodes), and the stopgap that
  derived a tree from chapter labels before then (`app/derived_contents.py`) is removed.
  The Catechism adapter emits its tree (`catechism.build_contents`, #253): the source's
  contents shape, labelled with the US headings the passages print. It is stored since
  the republish (566 nodes), but while the Catechism is excerpt-only `/toc` refuses it (403).
  The overview renders trees with
  `components/reader/ContentsTree.tsx`; the logic is `lib/contents-tree.ts`.
- `documents.reader_access` — **excerpt-only documents** (0041, issue #265): `full` or
  `excerpt`, default `full`. An `excerpt` document's rights are not cleared: its passages
  stay in search, but `/documents/{id}/reader` and `/toc` return **403** with
  `detail.code = "reader_restricted"` (guests and signed-in alike), and every surface that
  would open the reader (search cards, bookmarks, history restore, the Library) links to
  the official source instead. Derived from `datapipeline/rights_inventory.json` (rows
  found by document ID, not by title), never edited by hand: every stage sets it in
  `staging.documents`, 2.2w's apply re-derives it for each document it
  touches (Carter, 2 Nov 2026), and
  `datapipeline/reader_access.py --apply` re-syncs all live documents after an inventory
  change (the unblock path). API side is `app/reader_access.py`: passage sources carry
  `reader_access`, `source_url` and `source_credit`, reading progress is neither written
  nor listed for an excerpt document, and `/sources` reads the column fresh past its 1h
  cache. The API treats a database without 0041 as all `full`.
  **Held for permission, not removed for content:** older papal documents whose only English is
  Carlen's registered 1981 translation (via papalencyclicals.net) are retired by 1.3d with removal
  reason `awaiting-permission`: kept in the database, never shown or searched, with a link to the
  site. Partial documents publish the public-domain extract and hold only the missing paragraphs.
  The list, the places searched and how to bring them back (permission from Pierian Press) are in
  `docs/adr/0001-retire-papal-documents-without-public-domain-english.md` (Carter, 1 Nov 2026).
  `source_credit` is the rights holder's line, shown directly after an excerpt passage and
  included when it is copied: the USCCB's required notice, verbatim, for the Catechism of
  the Catholic Church (whose `source_url` is the USCCB's online edition), the LEV line for
  a vatican.va source, and null otherwise. The USCCB requires its notice on any use, so an
  unblocked Catechism must keep it and show it in the reader.
  A Catechism **passage's** `source_url` opens the USCCB flipbook on the page where its
  first paragraph starts, not the cover: `app/catechism_pages.py` keys
  `app/catechism_pages.json` on the passage's `unit_label` (`§1127`). The table is
  generated by OCR of the flipbook's page images (`scripts/build_catechism_pages.py`,
  which checks every number against our text) and holds page numbers only. It is valid
  for one flipbook publication (its GUID): the API checks the live GUID once a day in the
  background and links to the cover on a mismatch until the table is rebuilt. Document
  metadata, `/sources` and the 403 keep the cover URL.
  A **vatican.va** passage's `source_url` carries a text fragment (`#:~:text=`) of its
  opening words, so a supporting browser scrolls to it (2.4e, `app/source_links.py`); so
  does the reader's 403 when its request names an anchor. Only documents whose own
  `metadata.url` is the vatican.va page get one (not Canon Law's index). Passages the
  check `datapipeline/checks/source_links.py` cannot place on the vendored page keep the
  plain URL through `app/source_link_misses.json`, which it generates; rerun it after a
  publish that changes those passages.
- `documents.metadata.held_texts` — **held texts in their place** (item 4.3, #394; no
  migration). The texts a document holds back (a council's gap text, a run of a papal
  document's paragraphs awaiting permission) as `{key, label, heading, after_anchor,
  after_chapter_key, url}`, in reading order. Source of truth is
  `datapipeline/registry/held_texts.json`, checked against the removal registry by
  `registry.validate` and placed against the build by `build()`, which writes the list;
  a stage carries it and the release report lists it. `/toc` returns it as `held_texts`
  with each link resolved (the entry's, else `held_text_url`, else `url`) and drops a stale
  list whole; `/documents/{id}` and `/sources` return only `held_count`; no returned
  `metadata` carries it. Held texts never reach search. Live has no list until 4.3's publish.
- `chunks.metadata.headings` — **headings inside a passage** (issue #445; no migration).
  Headings stay in `content`; the build marks each as `{at, end, role, level?, pairs_next?,
  chapter_title?}`, offsets of one whole paragraph, `role` `heading` (level 1–3) or
  `epigraph`. Contract and adapter helper: `datapipeline/headings.py` (`MarkedText`,
  `prepend`; `hold_headings` and `split_marks` carry marks through a cut). Block rule H6
  refuses a malformed mark anywhere; H7 (heading-like paragraph unmarked) and H8 (chapter
  repeat without `chapter_title`) run only in collections listed under
  `H7_unmarked_heading` in `health_patterns.json`, which a collection joins when its adapter
  marks. The API sends `headings` with chunk events (only when non-empty), restored
  results, bookmarks and reader passages (`app/headings.py`); the web draws them with
  `components/common/PassageBlocks.tsx` and draws an unmarked passage as before. No live
  passage carries marks yet.
- **Corpus-cleanup schema** (0042 schema, 0043 validation and staging; item 2.2a, #178;
  **applied to production 2 Nov 2026**).
  Places for what the cleanup decides. 2.2w's writer fills them, and every existing row
  is live and searchable. Search skips a passage that is not searchable, retired or in a
  retired document (2.2b): full-text search, Summa stitching and the position lookup
  filter in SQL, and vector search filters on the Qdrant payload's `searchable`. The API's
  results, reader, history restore, bookmarks, `/sources` and reading progress do (2.4a):
  `app/corpus_schema.py` says which objects exist and builds today's SQL without them, and
  `app/corpus_lifecycle.py` turns a retired row into `moved` (redirect) or `removed`
  (tombstone, shown without its text). The reader answers a removed document or passage
  with 410 `{"detail": "removed", "tombstone"}` and a moved one with 404
  `{"detail": "moved", "redirect"}`. After a publish's rollback window,
  `publish.py purge-retired` (4.1b step 13, `datapipeline/retention.py`) deletes retired
  rows nothing points at, keeping held texts (ADR 0001); a deleted passage's tombstone
  `snapshot` keeps its `anchor` and `chapter_key`, which the reader's notice reads. Document facts on `documents` (`genre` → the
  `corpus_genres` lookup, seeded from `datapipeline/registry/genres.py`; `issuer` slug and
  `issuer_label`; `date_display`, `certainty`, `attribution_note`, `notes`,
  `source_credit`, `clavis_ref`, `superseded_by`/`superseded_note`). Works inside one
  document (D6): `document_works`, and `chunks.work_key`. Passage fields on `chunks`:
  `searchable` (default true), `language` (NULL = English), `passage_author`, `voice`
  (NULL or `rejected`), `note`, and `superseded_by` for a history passage, which is never
  searchable. **Retirement** (D3): `retired_at` on both tables; a retired passage must sit
  at position ≤ −1,000,000, and `refresh_document_outline` and the outline trigger now
  ignore and react to retired rows. `corpus_tombstones` (reason CHECK = registry
  `REMOVAL_REASONS` + `rolled-back`; tests read the Python list), `corpus_redirects`
  (`moved`/`split`/`merged`/`renumbered`) and `corpus_publishes` (one row per 2.2w
  publish). The **`staging` schema** mirrors `documents`, `chunks`, `document_chapters`,
  `document_contents`, `document_works`, `corpus_tombstones` and `corpus_redirects`
  (`LIKE … INCLUDING ALL`, no foreign keys), made by `create_corpus_staging()` and removed
  by `drop_corpus_staging()`; `staging.refresh_document_outline` builds staged outlines.
  The stage-then-apply writer (2.2w) is what fills it. `CORPUS_READ_SCHEMA=staging` makes an
  in-process run read it, read-only (`app/db.py`); the API server refuses to start with
  anything but `public`. All new objects: RLS on, no
  policies, revoked from `anon`/`authenticated`. A `documents.source_credit` column now
  exists beside the API's derived `source_credit` (`app/reader_access.py`). The derived
  one stays the top-level field; `facts.source_credit` carries the column, except that an
  excerpt-only document's required notice replaces it (2.4a). Apply 0043 right after 0042: 0042 is catalog-only (milliseconds under
  ACCESS EXCLUSIVE), 0043 validates under locks that do not block reads.
- `documents.form`, `corpus_forms` — a papal document's **form** (0044, Carter 9 Nov 2026):
  `bull` or `brief`, how the papal chancery issued it, NULL where none is recorded. It sits
  beside `documents.genre`, which is the document's kind (Ineffabilis Deus: genre
  `apostolic-constitution`, form `bull`); `bull` left `corpus_genres` in 0044. The values come
  from `PAPAL_FORMS` in `datapipeline/registry/genres.py`. Issue #330 carries it: `works.json`'s
  `form` (2.3's generator, from `papal_genres.csv`), `Document.form`, staged and applied by 2.2w,
  and shown as "Apostolic constitution · issued as a bull" (`formatKind` in `lib/attribution.ts`)
  in the reader overview and an opened card. A stage refuses a database without the column; the
  API reads it only where it exists (`CorpusSchema.form`). **Applied to production on 16 Nov 2026**
  (ledger `20261116020501`; ops log on #330). Live rows stay NULL until the republish writes them.
- `chunks.search_vector` **redefined** (0045, item 2.2c, #181): content with Bible `{{v:N}}`
  markers stripped at weight A, plus the reference with its punctuation turned into spaces at
  weight B, so "canon 1055", "ccc 2267" and "john 3" find their passages. **Applied to
  production on 16 Nov 2026** in 4.0's window, by hand (it rewrites `chunks` under an exclusive
  lock; about 21 s), followed by `drop_corpus_staging(); create_corpus_staging();` and recorded
  in the Supabase ledger (runbook in `docs/corpus-cleanup/P4-P5-republish-expand.md`, 4.0 step 3;
  ops log in #190). Only numbers a reference prints are indexed, so `2265` inside `§2263–2267`
  is not. `retrieve_fts.py` works with either definition.
- `studies`, `study_blocks` — **drafted, not yet in the repo.** A `0035_studies.sql`
  migration and a `test_study_schema.py` exist on at least one working tree but are
  committed to no branch, so `git log` will not find them and a fresh clone will not have
  them. `CONTEXT.md` already carries the vocabulary (Study, Study block, My Passages,
  Published version). The design point: a Study block is either authored writing or a
  Passage occurrence carrying a private source snapshot, so corpus pruning can remove the
  live chunk without erasing authored work. Update this entry when the migration lands.

Migrations 0001–0034, 0036–0038 and 0040–0046 are committed (0044 and 0045 were applied on 16 Nov 2026; 0046, which widens `documents_collection_check` to the new keys for 5.1b.3, awaits Carter's approval); `0035_studies.sql` is drafted only (see above). **0039 is unused:** it was reserved for corpus-cleanup item 2.2a (#178), which landed as 0042/0043 so that it runs after the tables staging mirrors (Carter, 2 Nov 2026); the parked `feat/roman-curia-collection` branch's own 0039 still renumbers when it lands. **Two identity collisions exist — `0026_compare_runs_pricing` / `0026_guest_onboarding_continuity`, and `0027_reading_progress` / `0027_guest_transfer_readiness`.** All four hold live schema, and the two members of each pair touch disjoint tables, so order within a pair does not matter. Audit the Supabase migration ledger before renaming any of them.

`chunks.content_embedding` and `chunks.annotation_embedding` exist but are **unused** —
NULL in every row, and no pgvector operator (`<=>`, `<->`, `<#>`) appears anywhere in the
repo. Qdrant owns all vector search. Production holds two Qdrant collections: `chunks-republish-2026-10`, which is live, and `chunks`,
the pre-republish corpus, kept for rollback until 4.1b step 13 deletes it. The
V5 `facets` and `questions` collections exist only if a V5 `embed` run creates them.
The API reads the collection or alias `QDRANT_READ_COLLECTION` names (default `chunks`;
production reads the alias `chunks_live` since 10 Nov 2026, which targets `chunks-republish-2026-10` since the Phase 4 cutover on 20 Nov 2026; a 2.2w publish switches it), and
`/health/search` reports it and its target. Production's Qdrant runs in **strict mode**: it
refuses a filter on a payload field with no index, so the API filters on `searchable`
only once the read collection has that boolean index (`qdrant_client.searchable_indexed`).
The 237 MB HNSW index over `content_embedding` was dropped in 0033's sibling, 0032. Leave
the columns themselves alone: all-NULL columns cost zero bytes, and `DROP COLUMN` does not
rewrite the table, so removing them would reclaim nothing.

**`app/db.py` registers a jsonb codec (`encoder=json.dumps`), so asyncpg serialises jsonb
parameters itself. Never call `json.dumps` on a value bound to a jsonb column from the API** —
that double-encodes it into a jsonb *string*, which reads back fine through the app but makes
the column unqueryable from SQL. 0033 repaired 205 such rows. The datapipeline pools register
no codec, so `json.dumps` there is correct.

---

## 5. RAG Pipeline

Two layers, and the split is the point:

- `rag/pipeline.py` owns the **SSE contract and DB side-effects only**.
- `rag/pipelines/runner.py` owns the **compute**; `rag/pipelines/registry.py` names the configurations.

Production runs the `hyde_cohere_luna_seats10t80_ftsminmatch` config (`_PRODUCTION_PIPELINE` in `pipeline.py`): HyDE → embed → Qdrant vector retrieval, with Supabase FTS running alongside from the start → RRF merge → **Cohere rerank per collection → one global listwise LLM call** → dedup → collection guarantee → quota cap → `min_floor` (only if everything else emptied). Steps live in `rag/steps/`. The collection guarantee is per collection, never per genre (5.1c): a genre selection adds no slots.

**How many Cohere candidates reach the listwise call is a per-pipeline seat rule**,
`RerankConfig.terminal_seats` (`budget.TerminalSeats`, issue #235). Production seats
`clamp(80 // collections-with-candidates, 10, 25)` per collection with no global trim, so
a 1–3 collection search sends 25 each and a 10-collection search 10 each (pool ≤ 100).
`None` keeps the pre-#235 sizing: quota + `COHERE_KEEP_EXTRA` per collection under the
40-seat `LLM_POOL_GLOBAL_CAP`. A focused plan's `terminal_candidate_budget` (25) still wins.
Seats add listwise latency roughly linearly (about 0.07–0.1 s per candidate), which the
`LoadingAnimation` gate-2 wait absorbs only partly.

**`rag/search_plan.py` resolves one validated `SearchPlan` before the pipeline runs.** It
is the single place that normalizes collections and enforces the focused-search invariant,
and it hands the runner three derived values: `focused`, `terminal_candidate_budget`, and
`max_passages_per_source`. `SearchPlanError` carries a stable `code` so routes translate
failures consistently. See §18.

**HyDE writes one passage per collection, except** the Bible (its genres, above) and `papal`
(5.1b.1), which writes one per kind of papal document its genre filter leaves on, in the
prompt of that kind's old key (`hyde_s25.papal_hyde_kinds`; Carter, 22 Nov 2026).

**A plan can narrow a collection to some genres and issuers** (item 5.1a, `SearchPlan.scopes`,
`rag/collection_scope.py`). The request lists what to search; a `CollectionScope` holds the
complement, and retrieval excludes only those values (Qdrant `must_not`, SQL
`genre IS NULL OR genre <> ALL(...)`), so a document without a genre or issuer is searched
under every selection. Only the papal collections can be narrowed (`GENRES_BY_COLLECTION`,
`ISSUERS_BY_COLLECTION` in `constants.py`, `papal` included, the genres a copy of `datapipeline/registry/genres.py`
kept equal by a test). A search without scopes sends master's exact Qdrant filter and SQL
(`tests/test_collection_scope.py`); keep it that way.

The registry also holds evaluation arms (no-HyDE, Cohere-only, Haiku instead of Luna, no-lexical, Luna 6 and reasoning effort, seat rules). **Every pipeline runs Cohere**, alone or followed by one listwise LLM call; the single-stage pointwise LLM reranker (`llm_only`) was removed in October 2026. Changing which pipeline is production is a one-line change to `_PRODUCTION_PIPELINE`; changing a *step* affects every config that uses it.

**Comparing pipelines is `services/api/scripts/run_eval_suite.py`** (in-process, writes
nothing to the database). It retrieves once per query, replays each named pipeline over
the same candidates (`rag/compare/shared_runner.py`), and has the judge
(`rag/compare/judge.py`) score them. Its default arms are production and
`hyde_cohere_luna_seats10t80_ftsminmatch_hydesample`; add any registry name with `--pipelines`. A new
model or setting to test is one new registry entry pinning it. The HTTP lab
(`/search/compare`) and `compare_batch/` were removed in October 2026.

**Keyword search's match is a per-pipeline axis**, `RetrievalConfig.fts_mode` (issue
#233, modes in `steps/retrieve_fts.py`). `"and"` is `plainto_tsquery`, which ANDs every
term and matched nothing for 92% of eval (question, collection) pairs. Production uses
`"min_match"`: passages holding at least ⌈n/2⌉ of the question's distinct lexemes, most
first, falling back to the most-matched when none reaches half. It was made production
without a judged run (Carter, 13 Nov 2026). The mode is part of `shared_runner.py`'s pool
shape. Keyword search needs only the question, so the runner and the eval capture start it
as a task before embed and await it where RRF reads it; an earlier failure cancels it.

**RRF `k` is a per-pipeline axis, not a constant.** It defaults to `settings.rrf_k`
(env `RRF_K`, 20) and is overridden per pipeline by `RetrievalConfig.rrf_k`, so an eval
arm can pin another `k` to test it. One consequence to respect when touching fusion:
`compare/shared_runner.py` caches candidate pools by retrieval **shape**, and `rrf_k` is
part of that key — omit it and two arms differing only in `k` silently share one pool.
The harness records the default `k` in its fingerprint for unpinned arms.

**The pipeline spans three LLM providers** — do not assume Anthropic-only. Defaults in `config.py`: HyDE passages and the Bible genre pick on `gpt-5.6-luna` with reasoning `none` (`HYDE_LUNA_MODEL` and `HYDE_GENRE_LUNA_MODEL` are separate settings; `HYDE_*_PROVIDER=haiku` falls back to `claude-haiku-4-5`), LLM rerank `claude-haiku-4-5` (`hyde_*_haiku`) or `gpt-5.6-luna` at reasoning `medium` (`*_luna`, pinned in `openai_provider.REASONING_EFFORT`), the Cohere rerank path, embeddings OpenAI `text-embedding-3-large`, explanations `gpt-6-luna` with reasoning `none`. The eval judge is `claude-opus-5-5` via structured outputs (forced tool_choice is a 400 on 5.5). Every one is env-overridable; read `config.py` before naming a model.

**Luna model and reasoning effort are also per-pipeline axes**, for evaluation arms:
`RetrievalConfig.hyde_luna_model` / `hyde_genre_luna_model` / `hyde_sample` and
`RerankConfig.llm_model` / `llm_reasoning_effort` (`None` = the production default).
`compare/shared_runner.py` draws HyDE once per distinct (passage model, genre model,
`hyde_sample`) and includes that key in its pool shape, so arms with different HyDE never
share a candidate pool; `SharedArtifacts.hyde_costs` records each arm's own draw cost. `hyde_cohere_luna_seats10t80_ftsminmatch_hydesample` is production with its own HyDE draw
— the noise floor any HyDE change must clear. Cost is always recorded against the model
actually called.

Streaming order: `chunk` events fire as soon as ranking completes, then the search and its retrievals persist, then `done`, then explanations stream per chunk via `explanation_delta`. Explanations arriving after `done` is normal and the frontend depends on it.

No LangGraph or agent frameworks. No pgvector for retrieval.

---

## 6. Deployment

- Backend: Docker image; same image runs locally and in prod.
- Frontend: Vercel.
- Config via environment variables only.
- Health endpoints: GET /health, GET /health/db, and GET /health/search, which reports
  retrieval-provider readiness and returns 503 when a dependency is missing. Model-provider
  credentials are configuration-checked only — validating them costs a billable request.

---

## 7. Coding Standards

- Backend: FastAPI + Pydantic, structured logging, no secrets logged.
- API logs go to **stdout** as one JSON object per line (`app/logging_setup.py`), which Railway
  parses: `level` sets severity, other fields are filterable (`@logger:app.rag.pipeline`). Railway
  labels anything on stderr an error, so do not add handlers that write there. `LOG_FORMAT`
  (`auto` | `json` | `text`) defaults to text in a terminal and JSON otherwise. This covers
  the process that imports the app, which is the only one in production's single-process
  `uvicorn` CMD. With `--workers` or `--reload`, uvicorn's supervisor never imports the app
  and still logs to stderr.
- Frontend: TypeScript, HTTP calls centralized in `src/lib/api.ts`, no DB SDK in frontend.
- Lint baseline is zero errors. Leave no new warnings in files you touch.

---

## 8. Non-Goals

- No direct DB queries from frontend
- No serverless backend (Lambda, Supabase Edge Functions)
- No Kubernetes, no agent frameworks, no premature microservices

---

## 9. Design System

Tokens are defined in `apps/web/src/app/globals.css` under `@theme`. Use the Tailwind `brand` namespace (`bg-brand-surface`, `text-brand-muted`, …) and `var(--color-collection-*)` for collection accents. **No hardcoded hex in components.**

Two themes, selected by `data-theme` on `<html>` and persisted in `user_preferences.theme`:

| Token | Slate Night (dark, default) | Ivory Vault (light) |
|---|---|---|
| `brand-bg` | `#0D1828` | `#f0e8d8` |
| `brand-surface` | `#172232` | `#e3dbc8` |
| `brand-accent` | `#C4972A` | `#C4972A` |
| `brand-primary` | `#EAE6DC` | `#1a1610` |
| `brand-muted` | `#BBBECB` | `#534B3F` |

Any new color must be added to **both** theme blocks.

`brand-muted` is secondary text, and it must read at WCAG's 4.5:1 on every collection card
tint (`rgba(<collection>, 0.32)` over `brand-bg`) and on `brand-bg` and `brand-surface` in both
themes. Both values above are the minimum of their hue that does (Carter, 20 Nov 2026).
Recheck when a collection colour or a background changes.

The brand heading font is `font-brand` (`--font-brand`): **Judson, set in capitals** (rules in
`globals.css`). Use the `font-brand` class, never an inline `fontFamily`. Cinzel was removed in
October 2026 and must not come back.

---

## 10. Routes

### Frontend

Authenticated pages live at the bare path; the guest mirror is a sibling under `/guest/` or `/search/guest`. Both must be updated together when shared behavior changes.

| Route | Notes |
|---|---|
| `/` | Redirects to /search when authed; otherwise renders `LandingPage` |
| `/search`, `/search/guest` | Main search interface — both render `SearchPage` |
| `/reader/[docId]`, `/reader/guest/[docId]` | Document reader (chapter-based) |
| `/history` | Search history |
| `/bookmarks` | Saved passages |
| `/sources` | Corpus document browser |
| `/discover` | AI collection scorer (evaluate endpoint) |
| `/settings` | User preferences |
| `/about`, `/guest/about` | Product info |
| `/feedback`, `/guest/feedback` | Product feedback form |
| `/login`, `/signup`, `/update-password`, `/auth/callback` | Auth flows |
| `/chat` | `redirect` to /search — keeps old links working |
| `/onboarding-preview` | Development-only landing-page preview (404 in production) |
| `/v1/[...path]` | The proxy route — see §1 |

### API (all under `/v1/`)

| Method | Path | Notes |
|---|---|---|
| GET | `/me` | Current user |
| POST | `/search` | SSE stream; 5/min, 30/day. Quota 10 is focused — see §18. Optional `filters.scopes: {collection: {genres?, issuers?}}` narrows a papal collection (§5); `invalid_genre`/`invalid_issuer` are 422 with `detail.code` |
| POST | `/search/guest` | SSE stream; guest session token, trial-limited; same optional `filters.scopes` |
| POST | `/guest/claim` | Transfer guest work into a new account |
| GET | `/searches`, `/searches/{id}/results` | History; restore a past search |
| DELETE | `/searches/{id}` | Retrievals cascade |
| GET | `/documents/{id}`, `/{id}/toc`, `/{id}/reader` | Reader: metadata, chapter list, one chapter. `/toc` also returns `held_texts` and the document `held_count` (§4, 4.3). `/toc` and `/reader` return 403 `reader_restricted` for an excerpt-only document (§4); all three return 410 with a tombstone or 404 with a redirect for a retired one (§4, 2.4a) |
| GET/PUT | `/reading-progress`, `/reading-progress/{doc_id}` | Reader position |
| GET | `/sources` | All documents with chunk counts, `reader_access` and `held_count` (4.3); the list is cached 1h in memory, reader access is read fresh |
| POST | `/evaluate`, `/evaluate/explain` | Collection scoring; 10/day |
| POST/GET/PATCH/DELETE | `/bookmarks`, `/bookmarks/{id}` | PATCH body is `{note}` |
| POST | `/product-feedback` | In-app feedback; allows anonymous |
| POST | `/labels` | Human relevance labels (retrieval lab) |
| GET/PUT | `/preferences` | User preferences |

Authenticated searches persist `outcome` and `collection_outcomes` in the
`searches.filters` jsonb alongside the submitted filters, and `scopes` only when a
collection was narrowed. The saved-results endpoint
returns them as optional fields so restored searches reproduce their original notices.
Older rows return `null`; the frontend keeps its result-count fallback instead of
inventing degradation details.

---

## 11. Frontend Layout

Components are grouped by feature under `apps/web/src/components/<feature>/` (search, reader, history, bookmarks, sources, discover, settings, feedback, landing, auth, common, layout). Read the directory rather than a list here.

What is **not** discoverable by looking:

- **Search lifecycle does not live in `components/search/`.** It lives in `apps/web/src/lib/search-experience/` — see §12.
- **`lib/search-stream.ts` is the sole SSE protocol module** — see §14.
- `components/layout/` holds three shells: `AppShell` (authenticated), `GuestShell` (guest), and `AuthenticatedRouteShell`, which picks between them by pathname against its own `AUTHENTICATED_ROUTES` list — **add new authenticated routes there or they render in the guest shell.** Guest and authenticated pages share components by receiving an `isGuest` prop, not by forking.

---

## 12. Search-experience runtime (`lib/search-experience/`)

**The search and restore lifecycle has one owner.** `createSearchExperience()` in `runtime.ts` exposes exactly three operations:

```ts
read:      () => SearchExperienceSnapshot   // immutable current state
subscribe: (listener) => unsubscribe
send:      (command: SearchExperienceCommand) => void
```

It owns run identity, `AbortController` lifecycle, stale-event rejection, frozen submitted requests, passage/explanation buffering, terminal rules, retry, rate limits, guest continuity, pending-history ownership, and animation milestones.

Everything it touches externally is an injected port: `audience` (a discriminated authenticated/guest search adapter), plus `credentials`/`savedSearch` for authenticated and `guestAccess`/`guestContinuity` for guest, and `pendingHistory`, `analytics`, `time`. Wiring lives in `useSearchPageExperience.ts`; React subscription is `useSearchExperience.ts` (`useSyncExternalStore`, no transitions).

Rules when working here:

- `SearchPage.tsx` renders snapshots and forwards commands. Keep AbortControllers, run generations, stream buffers, terminal flags, and animation timers out of it. Draft query/collection/translation/quota controls, route translation, result filtering, hints, and DOM measurement stay in the page — except the draft *transition rules*, which live in `lib/search-draft.ts` (§18).
- Next routing and React stay outside the runtime.
- Test through `read`/`subscribe`/`send` with scripted in-memory adapters. Do not assert on private reducer state.
- `LoadingAnimation` owns visual timing and emits semantic milestones (`filters-ready` at 3.2s, ready-to-reveal, fade-complete). Passages stay buffered until ready-to-reveal. Do not reintroduce a page-side timer.
- **The signed-in runtime outlives the page.** `AppShell` holds it in `searchExperienceSlot`, so leaving `/search` (opening the reader, History) does not abort a search or its explanation stream. `SearchPage` reattaches on mount and sends `resume-presentation`, which reveals ready results instead of replaying the animation. New Search resets it through `AppShell.newSearch`; sign-out and `AppShell` unmount dispose it. The guest runtime still lives and dies with the page; guest continuity is sessionStorage.
- **`/search?restore=<id>` names what the page holds** (`routeSearchId` in `view.ts`): `useAuthenticatedSearchRoute` rewrites it once a live search is saved, and drops it while a new one runs, so Back and reload return to the right search. The write keeps Next's history state (`__NA`), so Next does not sync it: a synced write dispatches a router restore that cancels any navigation in flight. `useSearchParams` therefore misses these writes; compare against `location`, and don't read `?restore=` as "came from History". A `restore` of the search the runtime already holds is a no-op, so Back to that URL never aborts the run.

---

## 13. AppContext

- Provided by `AppShell`; consumed via `useAppContext()`.
- **ALL authenticated pages MUST be wrapped in AppShell.** `GuestShell` supplies the guest equivalent.
- Holds: auth (`token`, `userId`, `ready`), preferences, search history (`searches` with `searchHistoryCursor`/`searchHistoryLoadedAt`, `refreshSearches`, `removeSearch`, `restoreSearch`), the pending-search slot, `activeSearchId`/`searchKey`/`newSearch`, `searchExperienceSlot` (§12), the cached source corpus, `bookmarkIds`, and mobile navigation state.

`activeSearchId` is History's "Current" marker: the saved search the search page holds,
the one you get back on returning to Search. It is derived (`currentSearchId` in
`lib/search-experience/view.ts`, pushed by the page's subscription), never set by hand;
it is null while a search is in flight, restoring, failed, unsaved, or after New Search.

`searches` is the first page of history, and `searchHistoryLoadedAt` says when it last
loaded. `HistoryPage` opens on it (with `searchHistoryCursor`) instead of a skeleton, and
refreshes it in the background unless it is only seconds old — AppShell renders no page
until its first load finishes, so on a full load of /history that list is already current.

**`clearPendingSearch(expectedId?: string)` is generation-guarded** — it no-ops when `expectedId` does not match the current pending entry, so a stale aborted run cannot clear its replacement's row. Always pass the owning entry id.

Auto-save on toggle/quota/translation change is debounced `PUT /v1/preferences` in `SearchPage.tsx` and `CollectionToggles.tsx` — NOT in AppShell.

---

## 14. SSE Streaming

- **`lib/search-stream.ts` is the only SSE decoder.** `consumeSearchStream(body, callbacks, signal)` owns buffering, event decoding, terminal rules, and abort. `streamSearch` (authenticated) and `streamGuestSearch` (guest) are request adapters over it and differ only in endpoint and credential.
- Add a new event field **once**, in `search-stream.ts`.
- **Backend event types:** `chunk`, `status`, `explanation_delta`, `done`, `error`, and `results_ready` (guest only — ranked passages are ready; guest `done` is a later completion/transfer milestone).
- **Callbacks:** `onChunk`, `onExplanationDelta`, `onStatus?`, `onResultsReady?`, `onRateLimit(retryAfter, "per_minute" | "daily")`, plus:
  - `onDone(searchId, resultCount, outcome, collectionOutcomes, persisted, deliveryOutcome?)` — `persisted: false` means results are usable but not saved to history. `deliveryOutcome` is focused-search only (§18) and absent otherwise.
  - `onError(message, code?, stage?, collectionOutcomes?)`
- `outcome` is `success | degraded_success | no_candidates`. **Only an explicit `no_candidates` means an empty corpus result** — an error is not a no-results screen.
- Cleanup: pass an `AbortController.signal` and abort on unmount.

---

## 15. Collections — Canonical Source

- **Single source of truth:** `services/api/app/rag/constants.py` (`VALID_COLLECTIONS`). It holds
  two vocabularies while corpus cleanup 5.1b runs: the eight `CANONICAL_COLLECTIONS` (with
  `papal`, `church-law` and `theologians`) and the five old keys in `LEGACY_COLLECTIONS`, which
  map to them (`encyclicals`, `apostolic-exhortations` and `papal-documents` to genres of
  `papal`; `canon-law` to `church-law`; `medieval` to `theologians`). Since 5.1b.2 the web
  offers only the eight new keys (labels: Papal documents, Church law, Theology &
  Spirituality) and translates any old key it reads (`canonicalCollectionKey` in
  `lib/collections.ts`; a restored old papal search becomes a Papal documents genre
  selection, `canonicalSearchFilters`). `collection_scope.reads` decides which stored values a key reads,
  so both vocabularies work whether or not 5.1b.3 has rewritten the stored values, and a
  search's results are labelled with the key it sent. A plan drops an old key named beside
  its new one and logs `legacy_collection_key`; 5.1b.4 removes the old keys.
- **Frontend mirror:** `apps/web/src/lib/collections.ts` (label + CSS var per collection, and
  `LEGACY_COLLECTIONS`, the old keys' meaning, mirroring the API's).
- **Datapipeline (5.1b.3):** `publication.SOURCE_ADAPTERS` builds the eight published
  collections; `SOURCE_BUILDS` builds the ten sources (`sources/<key>/`, the old names),
  which the work registry, the 0.1a to 0.1c checks, their known defects and the embedding
  overlap stay keyed by (`collection_keys.source_of`). Until 5.1b.3's publish is applied,
  live rows carry the old keys, and 2.2w reads them as part of the new key
  (`collection_keys.live_keys`). Boethius moves from `theologians` to `church-fathers` only
  in a stage of both (`publish.py stage --collection` repeats); a Fathers-only stage
  before then leaves him where he is (`publication.place_boethius`).
- **To add one:** update `constants.py`, sync `collections.ts`, add a `--color-collection-*` token in `globals.css`, and add a migration extending the DB collection constraint.

---

## 16. CSP Headers

- Defined in `apps/web/next.config.ts`.
- **`script-src` and `default-src` are intentionally omitted** — nonce-based CSP is deferred, and `unsafe-inline` is required for Next.js hydration in the interim, so these directives are excluded rather than creating a false sense of security.
- **`connect-src` includes:** `'self'`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `https://app.posthog.com`, `https://eu.posthog.com`
- **NEVER add `unsafe-eval` to `script-src`.**

---

## 17. Known Issues & Deferred Work

### 1. Do not delete `rag/steps/dedup.py`

**`rag/steps/dedup.py` is NOT dead — do not delete it.** `pipelines/runner.py` imports it
in the parenthesized `from app.rag.steps import (...)` block, which is easy to miss with a
single-line grep. It is the step that carries `per_source_cap`, so focused search (§18)
depends on it.

Lint warnings are 2 total, 0 errors, both in `components/common/ErrorBoundary.tsx`.

---

## 18. Focused search (quota 10)

Quota is one of `3, 4, 5, 10`. **Quota 10 is "focused": it requires exactly one
collection**, and it changes retrieval shape rather than just raising the result count.

**The invariant is enforced in one place** — `resolve_search_plan()` in
`rag/search_plan.py`. Do not re-derive "is this focused?" from a raw quota int anywhere
else; take `SearchPlan.focused`. `SearchPlanError.code` is stable and routes translate it:
`no_valid_collections` → 400, everything else (`invalid_quota`, `duplicate_collections`,
`invalid_collections`, `focused_collection_count`, and 5.1a's `invalid_genre` and
`invalid_issuer`, whose detail is `{code, message}`) → 422. (The guest route answers 422 for
all of them.) A genre or issuer selection is not a collection: it never changes focused
eligibility, and a focused search may narrow its one collection.

What focused changes, all derived from the plan:

| | Standard | Focused |
|---|---|---|
| Collections | 1–8 (the API also accepts the five old keys until 5.1b.4) | exactly 1 |
| `terminal_candidate_budget` | `settings.llm_pool_global_cap` | 25 |
| `max_passages_per_source` | 2 | 4 | *(per **chapter** for chapter-keyed collections — see below)* |
| Bible HyDE | genre-selected subset | all genres, fused as one retrieval family (`hyde_s25.run(..., all_bible_genres=True)`) |

`max_passages_per_source` is passed as `per_source_cap` to `steps/dedup.py`. `min_floor`
takes no cap; it is bounded by `min(quota, _FLOOR_N)` and spreads across sources itself.

**The cap is per *source*, and a source is the reader chapter for the chapter-keyed
collections** in `rag/dedup.py` (`summa`, `catechism`, `canon-law` and `church-law`, `bible`) — see
`dedup.source_key`. Those four are each stored as a single document (the Bible as one per
book), so an earlier per-*document* cap limited a focused search to 4 results in total
however many distinct articles or psalms ranked, which made issue #28's "return exactly
ten" unreachable for exactly the collections focused search is most used on. Issue #105 is
that defect reported from production; keying the cap per chapter fixed it.
`FOCUSED_MAX_PASSAGES_PER_SOURCE` / `STANDARD_MAX_PASSAGES_PER_SOURCE` in `search_plan.py`
name what they now limit.

**Focused search also keys `church-fathers` per chapter**
(`dedup._FOCUSED_CHAPTER_KEYED_COLLECTIONS`, selected by `focused=True` from the runner,
in both `dedup` and `min_floor`). It holds 128 works, so standard search keeps the
per-work cap to stop one Father taking a mixed search. A focused search about one
work, though, otherwise stopped at 4 (Augustine's Confessions, 2026-10-13).

### delivery_outcome

Focused searches report how well the quota was filled: `complete` | `underfilled` |
`minimum_floor` (`_delivery_outcome()` in `pipelines/runner.py`). It reaches the client as
the optional 6th argument to `onDone` (§14), and it is persisted into the `searches.filters`
jsonb **only when quota is 10** (`pipeline.py`), so a restored focused search can explain
its own delivery. Standard searches never set it; treat `undefined` as "not applicable",
not as a failure.

### Preferences

`user_preferences` carries both `default_quota` and `last_standard_quota` (0034).
`last_standard_quota` remembers where to return when the person leaves focused mode, so
toggling 10 → back does not strand them on an arbitrary default. DB constraints mirror the
API invariant: `default_quota IN (3,4,5,10)`, `last_standard_quota IN (3,4,5)`, and
`default_quota <> 10 OR exactly one default_collection`. Keep all three in step when
changing quota rules.

### Frontend

**`lib/search-draft.ts` owns draft quota/collection state and focused eligibility** —
`SearchQuota`, `StandardQuota`, `focusedEligible`, and the draft reducer. It also owns the
genre and issuer selections (5.1a: `excluded`, `scopes`, and the `genre-toggled`,
`issuer-toggled`, `scope-only` and `scope-all` events), which never change focused
eligibility. `lib/collection-scopes.json`, the values each papal collection offers, is
generated from `datapipeline/registry/works.json` by its test. This is the one
exception to §12's "draft controls stay in the page": the page renders it, but the
transition rules live here and are unit-tested directly. `QuotaControl.tsx` and
`BottomBar.tsx` render it. `LoadingAnimation` takes `quota` as a prop and scales its
winner count to it, so ten works without a special case.

---

## Active work: corpus cleanup

The corpus is being fixed and republished before any collection is added or reorganized.
The Phase 4 republish went live on 20 Nov 2026 (`republish-2026-10`, #192); its rollback window
runs to 4 Dec 2026, and until its lock entry is removed then (4.1b step 13) no other publish can run.
A rollback in that window restores a corpus with no stored Summa tree, and the Summa reader would
fall back to its flat chapter list.
Start from the "Start here" section of `docs/2026-09-28-corpus-cleanup-plan.md`; detailed
work specifications are in `docs/corpus-cleanup/`. The plan's Decision log is settled.
The findings of the 6 Oct 2026 corpus reviews (C-01 to C-30) are routed to their items in
`docs/corpus-cleanup/REVIEW-GAPS-PLAN.md`; the order after 2.1 is 0.1d (their checks), then Phase 1,
with 1.7 waiting for research item R7.

---

## Agent skills

### Issue tracker

Issues and specifications are tracked in GitHub Issues for `carteratate/body-of-christ`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default Matt Pocock triage labels. See `docs/agents/triage-labels.md`.

### Domain docs

Use the single-context documentation layout. See `docs/agents/domain.md`.

### Architecture review

The August 2026 production architecture review is `docs/architecture/architecture-review-2026-08-23.html`. Items 1–3, 7 (the retrieval lab, removed rather than separated) and 8 (relics) are implemented; items 4–6 are open.
