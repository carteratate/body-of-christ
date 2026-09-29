# Corpus cleanup, Phases 4 and 5: republish, reorganize, expand

Work specifications for Phase 4 (republish) and Phase 5 (reorganize and expand) of `docs/2026-09-28-corpus-cleanup-plan.md`. Written 29 September 2026. The plan and its Decision log are the source of truth. Nothing here reopens a decision; where a fact found while writing this bears on a decision, it is marked "Carter to note" and left for Carter.

## Overview and recommended order

1. P4 republishes the cleaned corpus built in P1 to P3 as one release, behind the publish lock (0.4), the release column (2.2a) and the Qdrant alias (2.2b).
2. Order for P4 is 4.0 storage, then 4.1a remap tooling and rehearsal, then 4.2 run against the staged release, then the 4.1b cutover, then 4.2 again on production.
3. Two new facts affect P4. Supabase branching needs the Pro plan and copies schema only, and a `VACUUM FULL` of `chunks` on today's 401 MB database may peak near 600 MB, above the Free plan's 500 MB read-only trigger (see 4.0).
4. P5 starts only after the P4 cutover and its rollback window close.
5. 5.2 (rights inventory) can run in parallel from now, and every addition PR waits for its row.
6. Order for P5 code is 5.1a genre and issuer filters, then 5.1c, then the four 5.1b PRs in order (5.1b.1 to 5.1b.4).
7. 5.1b depends on 5.1a because the old key `encyclicals` becomes "papal documents of genre encyclical" after the merge.
8. Then 5.3a (Roman Curia, from the parked branch), 5.4, 5.5, 5.6a, 5.3b, 5.6b, and 5.6c one work at a time.
9. 5.7 (About page) goes last, once the content it describes exists. The Eastern code stays blocked. Retrieval follow-ups open after the new baseline.
10. Storage is the binding constraint for P5. The planned additions are likely to push the database past 500 MB, so every addition PR carries a storage projection (see 5.2).

Every live-data step below (anything that writes to production Supabase or Qdrant, restarts the API, or deletes anything) needs Carter's explicit approval for that step, given in chat or on the PR, at the time it runs. Approval of a PR is not approval of its live-data step.

## Facts measured for this document (29 Sep 2026, read-only)

Queries were read-only against the production Supabase project (`body-of-christ-dev`, `hvmgffvimqgiejmxwhwq`, which serves production per Carter's memory notes).

| Fact | Value |
|---|---|
| Database size | 401 MB |
| `chunks` total | 380 MB (heap 89 MB, TOAST 200 MB, indexes 88 MB) |
| `chunks` live row bytes (`sum(pg_column_size)`) | 123 MB |
| `chunks` dead tuples | 0 (the free space is inside the files, reusable by new rows) |
| Largest `chunks` indexes | `chunks_document_chapter_pos_idx` 27 MB, `chunks_search_vector_idx` 26 MB, `chunks_document_anchor_uniq` 26 MB |
| Passages / documents | 54,568 / 421 |
| Documents per collection | bible 73, catechism 1, church-fathers 128, councils 36, encyclicals 131, apostolic-exhortations 30, papal-documents 14, canon-law 1, summa 1, medieval 6 |
| User-owned rows | searches 263, retrievals 3,029, bookmarks 25, retrieval_labels 3, guest_trials 18, guest_trial_retrievals 274, reading_progress 25, user_preferences 9, product_feedback rows with a chunk 0 |
| `user_preferences.default_collections` keys | bible 8, catechism 7, summa 7, church-fathers 6, councils 6, encyclicals 6, apostolic-exhortations 3, papal-documents 3, medieval 3, canon-law 2 (9 rows, none at quota 10) |
| `searches.filters->collections` keys | bible 242, catechism 229, church-fathers 205, summa 195, encyclicals 185, councils 161, medieval 131, canon-law 127, papal-documents 109, apostolic-exhortations 107, `saints` 15 (a key retired long ago) |
| `guest_trials.filters->collections` keys | bible, catechism, church-fathers, councils, encyclicals, summa 17 each; papal-documents 1 |
| `searches` rows carrying `collection_outcomes` | 36 |
| Column default of `user_preferences.default_collections` | `{bible,catechism,church-fathers,encyclicals,canon-law,summa}` |
| `documents` constraints | `documents_collection_check` (the 10 keys), `UNIQUE (collection, title, translation, author)` |
| Title collisions if the three papal collections merge | none |
| Pseudo-Dionysius in the corpus | absent. The two "Dionysius." documents in `church-fathers` are Dionysius of Alexandria. So "Pseudo-Dionysius moves to the Fathers" is an addition (5.6a), not a move |
| Basil, Cyril of Jerusalem, Gregory Nazianzen, Gregory the Great, Chrysostom, Ambrose, Leo | none present |
| Supabase migration ledger | records only 30 of the repo's migrations (0015, 0016, 0019, 0026, 0031 to 0033 and others were applied outside the ledger). Inspect live schema, not the ledger, before any migration |
| Tracked `docs/eval/` gold data | `eval80-round3-final.jsonl` holds 0 chunk UUIDs (results carry collection and reference only). The 9,492 distinct chunk ids live in untracked local folders such as `docs/eval/eval80-round3-final-artifacts/` |

Supabase documentation (read 29 Sep) says Free plan projects enter read-only mode when database size exceeds 500 MB, and that branching (preview branches) requires the Pro plan and copies schema without production data ([database size](https://supabase.com/docs/guides/platform/database-size), [deployment and branching](https://supabase.com/docs/guides/deployment)).

Qdrant figures come from the plan (28 Sep) and were not re-measured: one collection `chunks`, 54,568 points, 1,536 dimensions, no quantization, no alias, about 335 MB of raw vectors.

## Prerequisites from earlier phases

P4 and P5 assume these have merged. Each spec below names the ones it needs.

| ID | What P4/P5 relies on |
|---|---|
| 0.1c | Release report with the old-to-new passage id remap |
| 0.2 | Source hashes, manifests, rights inventory file |
| 0.3 | Baseline eval run and its gold file format |
| 0.4 | Publish lock. `run_collection` refuses production writes without an explicit cutover flag |
| 0.5 | Qdrant plan memory and disk limits |
| 2.1 | Work registry with frozen document ids, structural anchors and rule A fields. After 2.1, a document's id no longer depends on its collection key (today every adapter passes the collection string into `document_id()`, for example `datapipeline/ingest/encyclicals.py:172`) |
| 2.2a | Release column, tombstones, redirects, document fields (genre, issuer, attribution, notes), `searchable` |
| 2.2b | API reads Qdrant through an alias; `searchable` filter that excludes only `searchable = false` |
| 2.3 | Metadata backfill, including genre and issuer for every document |
| 2.4a | API payload for tombstones and redirects |
| R1, R6 | Rule A dating and Church-act checks; edition and provenance per planned source |

One open question inside 2.2a decides how 4.1a works, so it is repeated here. Passage ids are deterministic from document id and anchor (`datapipeline/identity.py:40`). An unchanged passage therefore has the same id in the old and new releases, and `chunks.id` is the primary key. 2.2a must say how a passage whose id is unchanged but whose text changed is stored while both releases exist. The specs below assume 2.2a's answer is "unchanged ids keep their row; only new, changed-anchor and removed passages differ", and mark the places that change if it is not.

---

## Phase 4. Republish

### 4.0. Storage: compact `chunks`, measure, decide on Pro

- **Type:** ops
- **Depends on:** 0.5 (Qdrant limits). Runs before 4.1a's rehearsal measurement is final.
- **Goal:** Get back the space earlier rewrites left inside `chunks`, so the republish fits under the Free plan's 500 MB limit, and decide from a measurement whether Supabase Pro is needed. Users see nothing, apart from search and the reader pausing during the lock.
- **Current state:**
  - Database 401 MB, `chunks` 380 MB, of which live row bytes are 123 MB (measured 29 Sep, table above). Dead tuples are 0, so the roughly 166 MB gap between live rows and heap plus TOAST is free space inside the files. Plain `VACUUM` already made it reusable for new inserts; only `VACUUM FULL` returns it to the database size figure.
  - Decision log row "Storage (4.0)": `VACUUM FULL` in an approved quiet window, measure, buy Pro only if a rehearsal exceeds about 350 MB or V5 enrichment is scheduled; new Qdrant collection with vectors on disk if memory is tight.
  - **Carter to note (peak risk).** `VACUUM FULL` writes a complete new copy of the table and its indexes before dropping the old one. Estimated new copy is 123 MB of rows plus 60 to 88 MB of rebuilt indexes, so the database may briefly reach about 590 to 610 MB. Supabase documents that Free projects enter read-only mode above 500 MB. How quickly that is enforced is unverified (the same page says disk metrics update daily). If it triggers, writes fail (searches cannot be saved, bookmarks cannot be added) until usage drops.
  - **Carter to note (reuse).** Because the free space is reusable, loading the new release next to the old one may grow the database far less than a naive "twice the rows" estimate. 4.1a's rehearsal measures this.
- **Changes:** No code. Runbook, run from Carter's machine with `psql` over a direct (session-mode) connection, not the transaction pooler and not the dashboard SQL editor, which may time out.
  1. Pre-check (read-only). Record in the ops log:
     ```sql
     select pg_size_pretty(pg_database_size(current_database()));
     select pg_size_pretty(pg_relation_size('chunks')) heap,
            pg_size_pretty(pg_relation_size(reltoastrelid)) toast,
            pg_size_pretty(pg_indexes_size('chunks')) idx
       from pg_class where relname = 'chunks';
     select pg_size_pretty(sum(pg_column_size(c.*))::bigint) from chunks c;
     select pg_size_pretty(sum(size)) from pg_ls_waldir();
     ```
     Check the dashboard's Database Settings page for disk size and whether the project is already near read-only.
  2. Peak decision. If `pg_database_size + live rows + index size` exceeds 480 MB, stop and ask Carter to choose between (a) running anyway and accepting a possible read-only period, or (b) upgrading to Pro for the republish month, which also unlocks branching for 4.1a. Do not work around it by dropping indexes; that breaks full-text search during the window.
  3. Quiet window (Carter approves the time). In one `psql` session:
     ```sql
     set lock_timeout = '5s';        -- fail fast instead of queueing every search behind the lock
     set statement_timeout = 0;
     \timing on
     vacuum (full, verbose, analyze) chunks;
     ```
     If the lock is not acquired within 5 s, retry once a minute; do not raise `lock_timeout`.
  4. Measure again with the step 1 queries. Record duration, before and after sizes, and WAL size.
  5. Qdrant. Read 0.5's numbers. If the plan's memory cannot hold two copies of the vectors (about 2 x 335 MB raw plus HNSW), note that 4.1b must create the new collection with `on_disk=True` for vectors (and `HnswConfigDiff(on_disk=True)` if 0.5 shows the graph also does not fit).
  6. Pro decision, as decided. After 4.1a's rehearsal (next item) reports the peak size with both releases loaded, buy Pro only if that peak exceeds about 350 MB or V5 enrichment is scheduled.
- **Acceptance checks:**
  - Ops log (kept in the issue, not in a repo file) has before and after sizes, duration, and WAL size.
  - `pg_database_size` after compaction is recorded; expected 220 to 260 MB (estimate, not measured).
  - `/health/db` and `/health/search` return 200 after the window; one search per collection returns results.
- **Production safety:** `VACUUM FULL` takes an ACCESS EXCLUSIVE lock, so full-text search and the reader fail while it runs (the plan expects under a minute; GIN rebuild time on this compute is unverified). Vector search still reaches Qdrant but fetches from Postgres fail, so searches error rather than return partial results. `lock_timeout` prevents a stuck lock queue. There is no data change and nothing to roll back; if interrupted, Postgres discards the new copy. The only lasting risk is read-only mode from the peak, handled in step 2.
- **Needs Carter:** Approve the window and the run. Decide step 2 if the peak estimate exceeds 480 MB. Make the Pro decision in step 6.
- **Out of scope:** Dropping `content_embedding` or `annotation_embedding` (CLAUDE.md §4: all-NULL, reclaims nothing). Qdrant quantization. Any change to autovacuum settings.

### 4.1a. Remap tooling with a merge policy, rehearsed

- **Type:** PR
- **Depends on:** 0.1c, 2.1, 2.2a, 2.4a, P3 (the release to publish exists and passes its checks), 4.0 steps 1 to 4.
- **Goal:** A tool that moves every user's saved work (bookmarks, history results, labels, guest results, reading position) from old passage ids to new ones, merging duplicates without losing notes, and a rehearsal that proves it on a copy of production. Users keep their bookmarks and history across the republish.
- **Current state:**
  - Tables that reference `chunks(id)` (verified in migrations):
    - `bookmarks` `UNIQUE (user_id, chunk_id)`, `note` up to 3,000 characters, `ON DELETE CASCADE` (`supabase/migrations/0006_v2_bookmarks_feedback_prefs.sql:1-8`, `0016_bookmarks_add_note.sql`).
    - `retrieval_labels` `UNIQUE (user_id, chunk_id, search_id)`, `label` up or down, `rank`, `ON DELETE CASCADE` (`0022_retrieval_labels.sql:8-18`).
    - `guest_trial_retrievals` `UNIQUE (guest_trial_id, chunk_id)`, `rank`, `ON DELETE CASCADE` (`0026_guest_onboarding_continuity.sql:17-25`).
    - `retrievals` has no unique constraint, `ON DELETE CASCADE` (`0005_v2_searches_retrievals.sql:21-29`).
    - `product_feedback.chunk_id` `ON DELETE SET NULL` (`0028_product_feedback.sql:20`); 0 rows with a chunk today.
  - `reading_progress` references `documents(id)` with text `chapter_key` (NOT NULL) and `anchor` (`0027_reading_progress.sql:2-9`). Document ids are frozen by 2.1, but chapter keys and anchors can change.
  - Every chunk foreign key cascades on delete, so deleting an old-release row before remapping would silently delete users' bookmarks and history.
  - Supabase branching needs Pro and copies schema only, not data (docs, 29 Sep). The plan's "rehearsed on a Supabase branch" therefore needs Pro plus a data load, or a local rehearsal.
  - Rows at risk are few (25 bookmarks, 3,029 retrievals, 274 guest results, 3 labels, 25 reading positions), so the policy must be exact rather than fast.
- **Changes:**
  1. New module `datapipeline/remap_user_data.py` (CLI `python3 -m remap_user_data`), dry run by default, `--apply` to write, refusing production writes without the 0.4 cutover flag. Input is the remap produced by 0.1c's tool for the two releases, as rows of `(old_chunk_id, new_chunk_id | null, kind)` where kind is `same`, `moved`, `split`, `merged` or `removed`. For a split (one old passage became several), map to the new passage containing the old passage's first sentence; 0.1c must emit that choice, not this tool.
  2. One transaction per table, in this order, each ending with an assertion that no row still points at a chunk id outside the new release (except removed passages, step 3):
     - `bookmarks`. Repoint. When two rows for one user land on the same new chunk, keep the earliest `created_at`. If both notes are non-empty and differ, join them with a blank line when the result fits 3,000 characters; otherwise keep the earlier note and count the dropped note in the report (count only, never the text).
     - `retrieval_labels`. Repoint. On a `(user_id, chunk_id, search_id)` collision keep the row with the latest `created_at`, since a later label is the user's current judgement.
     - `guest_trial_retrievals`. Repoint. On a `(guest_trial_id, chunk_id)` collision keep the lowest `rank` and its `explanation` and `reranker_score`.
     - `retrievals`. Repoint. Where one search now holds the same chunk twice, keep the lowest `rank`, delete the other, and leave remaining ranks as they are (restore sorts by rank; gaps are harmless).
     - `product_feedback`. Repoint where a mapping exists; leave the rest.
     - `reading_progress`. Map `(document_id, chapter_key, anchor)` through the registry's anchor map from 2.1. If the chapter no longer exists, set the document's first chapter key and `anchor = NULL`.
  3. Removed passages (rules A to C and G). Do not delete. Point the reference at the tombstone form 2.2a defines, so the reader and history show "this passage was removed" with the reason (2.4a). The plan counted 50 of 2,967 retrievals and 0 bookmarks on removed passages on 28 Sep; recount at rehearsal and at cutover.
  4. Report, written to the local ops folder and pasted into the PR as counts only: rows per table repointed, merged, dropped duplicates, tombstoned, notes joined, notes dropped. No ids, queries or note text, since the repo is public.
  5. Inverse mode `--reverse` for rollback (4.1b), mapping new ids back to old ids. New-release rows with no old counterpart are left alone and reported.
  6. Tests in `datapipeline/tests/test_remap_user_data.py` using an in-memory fake store, one test per collision rule above, plus the cascade guard (the tool refuses to run if any old-release chunk it would need has already been deleted).
  7. Rehearsal. Carter chooses one:
     - (a) Pro plan, a Supabase branch, then load the production data into the branch with `pg_dump --data-only` of `public` (auth users included only as ids) from the production database, and apply the tool there.
     - (b) Local rehearsal with `supabase start`, migrations applied, and the same `pg_dump` restored. The dump contains user data, so it stays on Carter's machine, is never committed, and is deleted after the rehearsal.
     In either case load the new release next to the old one exactly as 4.1b will, run the tool, and measure `pg_database_size` at the peak. That number is the one the 4.0 Pro decision uses.
- **Acceptance checks:**
  - `python3 -m pytest tests/test_remap_user_data.py -q` passes in GitHub Actions (no sources needed).
  - Rehearsal report in the PR (counts only) shows zero rows left pointing outside the new release except tombstoned ones; bookmark count before equals after plus merged duplicates; every note either kept or counted as dropped.
  - PR description states the peak database size during the rehearsal and whether it is above 350 MB.
  - PR description confirms the dump used for rehearsal was deleted.
- **Production safety:** The PR adds a tool and tests only; nothing runs against production on merge. The tool is dry run by default and refuses production writes without the publish lock's cutover flag. Rollback of the merge is a revert.
- **Needs Carter:** Choose rehearsal (a) or (b). Approve taking a `pg_dump` of production for the rehearsal. If (a), the Pro upgrade.
- **Out of scope:** Cleaning up old-release rows (4.1b, after the rollback window). Any change to how saved searches render.

### 4.1b. Production cutover runbook

- **Type:** ops
- **Depends on:** 4.0, 4.1a (rehearsal passed), 4.2 pre-cutover run passed, 2.2b (API reads the alias), P1 to P3 merged.
- **Goal:** Switch production from the old corpus to the cleaned one in minutes, with a one-step rollback. Users see the corrected corpus (Vatican II and Trent recovered, removals gone, correct labels); bookmarks and history keep working.
- **Current state:**
  - Qdrant collection name is a constant, `QDRANT_COLLECTION = "chunks"` (`services/api/app/rag/qdrant_client.py:10`), and the datapipeline writes to `CHUNKS = "chunks"` (`datapipeline/qdrant_schema.py:12`). 2.2b changes the API to read an alias; the datapipeline writer also needs a target collection name for building the new collection. Confirm 2.2b includes that; if not, it is a small prerequisite PR.
  - `/sources` is cached in memory for one hour (`services/api/app/routes/sources.py:18`, `_SOURCES_TTL = 3600.0`).
  - Tracked `docs/eval/` holds no chunk ids (verified); ids live in untracked local artifacts and in 0.3's gold file.
- **Changes:** Runbook. Every numbered step that writes to production is a separate Carter approval.
  1. **T minus 2 days, staging (no user impact).**
     - Publish the new release into the reader store with the publish lock's cutover flag, marked with the new release value so the release filter keeps it invisible (2.2a).
     - Create the new Qdrant collection, for example `chunks_r2`, with `VectorParams(size=1536, distance=COSINE, on_disk=<per 4.0 step 5>)`, `HnswConfigDiff(m=16, ef_construct=64)` (same as today, `qdrant_schema.py:25`), and keyword payload indexes on `collection`, `document_id`, `genre`, `issuer` and `searchable`. Fill it with `run_collection.py --target search` per collection, pointed at `chunks_r2`.
     - Record embedding cost. About 11 million tokens at OpenAI's published price for `text-embedding-3-large` (unverified at writing; check the current price).
     - Point count in `chunks_r2` equals the new release's searchable passage count; recorded in the release report.
  2. **T minus 1 day.** 4.2 pre-cutover run against the staged release. Carter gives go or no-go.
  3. **Window start (quiet hour Carter chooses).** Freeze merges to `master` that touch `services/api`, `apps/web` or `supabase/migrations`.
  4. **Backup.** `pg_dump` of the user-owned tables (`bookmarks`, `retrievals`, `retrieval_labels`, `searches`, `guest_trials`, `guest_trial_retrievals`, `reading_progress`, `product_feedback`, `user_preferences`) to Carter's machine, kept private. Take a Qdrant snapshot of `chunks` if 0.5 shows the plan allows it (the old collection is not modified anyway).
  5. **Counts.** Read and record counts of each table above (the plan requires counts at cutover, not the 28 Sep ones).
  6. **Remap and switch the database.** Run `remap_user_data --apply` and, in the same maintenance minute, flip the active-release pointer defined in 2.2a to the new release.
  7. **Switch Qdrant.** `update_collection_aliases` in one call with a delete of the alias on `chunks` and a create of the alias on `chunks_r2`. Qdrant applies the listed alias actions atomically. Between steps 6 and 7 (seconds), vector hits may be dropped by the release filter; full-text search still works. Keep the gap under one minute.
  8. **Restart the API** on Railway to clear the `/sources` cache.
  9. **Smoke checks.**
     - `/health/db` and `/health/search` return 200.
     - One authenticated and one guest search per collection return results.
     - Nostra Aetate 4 and Gaudium et Spes open in full in the reader.
     - Restore a pre-cutover saved search from history.
     - A test account's bookmarks page loads, and a bookmark on a removed passage shows the tombstone.
  10. **Eval ids.** Remap 0.3's gold file with 0.1c's remap and commit the result (ids only, no user data). Remap local untracked artifacts only if they will be reused.
  11. **4.2 post-cutover run.**
  12. **Rollback, available until the window closes (recommended 14 days).**
      - Point the alias back at `chunks`.
      - Flip the release pointer back.
      - Run `remap_user_data --reverse --apply`.
      - Restart the API.
      Bookmarks made after cutover on passages that exist only in the new release stay attached to hidden rows and show as unavailable; the reverse report counts them.
  13. **After the window closes (separate approval).**
      - Delete old-release-only chunk rows in batches of 1,000, after asserting zero references from every table in 4.1a.
      - Plain `VACUUM (analyze) chunks`.
      - Delete the Qdrant collection `chunks`. Irreversible; Carter approves it separately.
      - Measure the database size again.
- **Acceptance checks:**
  - Cutover log in the tracking issue records every step's time, counts before and after, the remap report, smoke results and the 4.2 result.
  - Retrieval, bookmark, label and guest-result counts after equal counts before, minus reported merges.
  - No error-level API log lines about missing chunks in the hour after cutover (filter `@logger:app.rag` in Railway).
- **Production safety:** Everything before step 6 is invisible to users (release filter, new Qdrant collection not behind the alias). Steps 6 and 7 are each one switch with an inverse. The old corpus rows and old Qdrant collection stay untouched until step 13, so rollback is always possible inside the window. Deletions happen only after an assertion of zero references, because every chunk foreign key cascades.
- **Needs Carter:** Approve each of steps 1, 4, 6, 7, 8, 12 (if used) and 13. Choose the window. Give go or no-go at step 2.
- **Out of scope:** Collection renames (5.1b). Any new source. Any retrieval tuning (Retrieval follow-ups).

### 4.2. Comparison against the baseline

- **Type:** ops
- **Depends on:** 0.3 (baseline and harness), 4.1a, the staged release from 4.1b step 1.
- **Goal:** Show, before and after cutover, that the cleaned corpus answers the baseline questions at least as well, that removed texts no longer appear, and that recovered texts now do. This is what Carter's go or no-go rests on.
- **Current state:** 0.3 defines the harness and gold sets (the `docs/eval/` gold sets plus targeted questions, no stored user queries). Production pipeline is `hyde_cohere_luna` (CLAUDE.md §5). The noise floor for any retrieval change is the `hyde_cohere_luna_hydesample` arm (CLAUDE.md §5). The eval judge is `claude-opus-5-5`.
- **Changes:** Runbook plus a report file.
  1. **Pre-cutover run.** Run the 0.3 harness against a local API process configured to read `chunks_r2` and the new release. This needs whatever read overrides 2.2a and 2.2b provide (an environment variable for the alias name and one for the release). It reads production data and writes nothing. Run the same questions with the noise-floor arm.
  2. **Targeted checks,** scripted as assertions over the returned passages:
     - Zero passages from Origen, Novatian, Tatian, Arnobius, Alexander of Lycopolis, the Apostolic Constitutions outside Book VIII's 85 canons, the six forged Ignatius letters, or Tertullian's excluded works.
     - Nostra Aetate 4, a Trent decree and the Vatican I constitutions retrievable by a direct question.
     - CCC 2267 returns the 2018 text.
     - "Canon 112" returns canon 112 alone.
     - Susanna (Daniel 13) and Bel and the Dragon (Daniel 14) findable.
     - No result shorter than 20 characters.
     - No Vatican II result starting with "Cf." or "See".
  3. **Post-cutover run.** The same harness against production, after 4.1b step 9.
  4. **Report.** Add `docs/eval/2026-MM-DD-republish-comparison.md`: judge scores per dimension against baseline with the noise floor, the targeted checks, cost of the run, and the rationale for each regression larger than the noise floor (an intended removal explains a lost gold passage; nothing else does).
- **Acceptance checks:**
  - All targeted assertions pass.
  - Mean judge score within the noise floor of baseline or better.
  - Every regression larger than the noise floor is explained in the report.
  - The report contains no user data.
- **Production safety:** The pre-cutover run is read-only. The post-cutover run makes ordinary searches through the product path with an operator account and is rate limited like any user. It does not persist to other users' history.
- **Needs Carter:** Go or no-go after the pre-cutover run. Approve the eval spend (judge and pipeline calls; the report states the amount).
- **Out of scope:** Tuning anything to improve scores. That belongs in Retrieval follow-ups.

---

## Phase 5. Reorganize and expand

### 5.1a. Genre and issuer filters

- **Type:** PR (one API PR, one web PR; both deploy safely alone)
- **Depends on:** 2.2a, 2.3 (every document has `genre` and, where relevant, `issuer`), 2.2b, P4 complete.
- **Goal:** Inside a collection, a user can search one genre, several, or all (for example only encyclicals, or encyclicals and apostolic letters), and filter Roman Curia and papal documents by issuer. Nothing changes for a user who leaves the filters alone.
- **Current state:**
  - The search request carries `filters: {collections, translation}` and `quota` (`apps/web/src/lib/api.ts:286-299`); the plan resolves collections only (`services/api/app/rag/search_plan.py:76-96`).
  - Vector search filters Qdrant on `collection` alone (`services/api/app/rag/steps/retrieve_vector.py:31-35`); full-text search filters on `d.collection = $1` (`services/api/app/rag/steps/retrieve_fts.py:16-26`).
  - Qdrant has a keyword index on `collection` only (`datapipeline/qdrant_schema.py:28-29`). Genre and issuer payload fields and indexes come from 2.2b and 2.3 (not yet built; unverified).
  - Genre is currently in `documents.metadata` for 16 documents only (plan, "Corrections"). 2.3 backfills real fields.
- **Changes:**
  1. `services/api/app/rag/constants.py`. Add `GENRES_BY_COLLECTION: dict[str, frozenset[str]]` and `ISSUERS_BY_COLLECTION`, with the vocabulary 2.3 used. Minimum for the papal collections: `encyclical`, `apostolic-exhortation`, `apostolic-letter`, `apostolic-constitution`, `bull`, `motu-proprio`, `letter`. For Roman Curia: `declaration`, `instruction`, `doctrinal-note`, `note`, `letter`, `responsum`, `notification`, `compendium`. Issuer for Roman Curia is the institution (`ddf` for both CDF and DDF, per the source memo; the printed name stays on the document), `pbc`, `pcjp`. Issuer for papal documents is the pope.
  2. New module `services/api/app/rag/collection_scope.py` with a frozen `CollectionScope(collection, genres, issuers)`. It has `to_qdrant_filter()` and `to_sql()` so retrieval does not hand-build filters. Semantics, per the plan's rule "filters exclude only explicit values":
     - A selection is stored as the set of values the user turned off.
     - Qdrant gets `must_not` on `genre` in the excluded set.
     - SQL gets `(d.genre IS NULL OR d.genre <> ALL($excluded))`. The explicit NULL branch is required, because `NOT (NULL = ANY(...))` is NULL and would silently drop documents without a genre.
     - "All" means no clause.
  3. `search_plan.py`. `SearchPlan` gains `scopes: tuple[CollectionScope, ...]`. `resolve_search_plan(collections, quota, scope_filters=None)` validates genres and issuers against the constants and raises `SearchPlanError("invalid_genre" | "invalid_issuer")`, which routes translate to 422 like the other codes (CLAUDE.md §18). Focused search still requires exactly one collection; a genre subset does not count as a collection.
  4. Request models in `routes/search.py` and `routes/guest_search.py`. Add optional `filters.scopes: {[collection]: {genres?: string[], issuers?: string[]}}`; absent means all. Additive to `/v1/search` and `/v1/search/guest`; the `/v1/chat` contract (CLAUDE.md §3) is untouched.
  5. `retrieve_vector.py` and `retrieve_fts.py`. Take a `CollectionScope` instead of a bare collection string and use its filters.
  6. `pipeline.py`. Persist the scope selection into `searches.filters` next to `collections` (`_saved_search_filters`, `services/api/app/rag/pipeline.py:161-178`), and into `guest_trials.filters`. Remember CLAUDE.md §4 (no `json.dumps` on jsonb from the API). `routes/search.py` returns it on restore.
  7. Qdrant ops (live step). `create_payload_index` for `genre` and `issuer` (keyword) on the collection behind the alias, if 2.2b did not already. Index creation does not change points.
  8. Web PR.
     - `apps/web/src/lib/collections.ts` mirrors the genre and issuer vocabularies with display labels.
     - `lib/search-draft.ts` gains per-collection genre and issuer selections and events `genre-toggled` and `issuer-toggled`, unit-tested there (it owns draft transition rules, CLAUDE.md §18).
     - New `components/search/GenreFilter.tsx` renders chips under `CollectionToggles` for each selected collection that has genres.
     - `lib/api.ts` sends `filters.scopes`.
     - The restore path in `lib/search-experience/useSearchPageExperience.ts:292-307` reads it back.
     - Guest and authenticated pages share the component through `isGuest` (CLAUDE.md §11).
  9. Docs. CLAUDE.md §5 (scopes), §10 (request shape), §14 if the stream changes (it should not), §18 (genre does not affect focused eligibility).
- **Acceptance checks:**
  - API tests. A document with NULL genre is returned under every genre selection (SQL and Qdrant). A request without `scopes` produces byte-identical Qdrant and SQL filters to today's. An invalid genre gives 422 with code `invalid_genre`. A restore returns the stored selection.
  - Web tests. Draft reducer toggling one, several and all; restore round trip.
  - `npm run lint` zero errors; no new warnings in touched files.
  - A read-only query after 2.3 shows zero NULL genres in the papal and Roman Curia collections, recorded in the PR.
  - PR includes screenshots of the chips in both themes.
- **Production safety:** The API change is additive and optional. Old web clients send no `scopes` and get today's behavior. The web PR deploys after the API PR, so it never sends a field the API rejects. The Qdrant index is additive. Rollback is a revert of either PR; the index can stay.
- **Needs Carter:** Approve the Qdrant index creation (step 7). Confirm the genre vocabulary labels.
- **Out of scope:** Saving genre selections in `user_preferences` (needs a migration; a follow-up if wanted). Genre-specific HyDE prompts (Retrieval follow-ups). Per-genre result guarantees (5.1c decided against them).

### 5.1c. One guaranteed slot per collection, no per-genre guarantee

- **Type:** PR
- **Depends on:** 5.1a.
- **Goal:** Lock in the decided behavior. Every selected collection still gets up to one guaranteed result slot, and selecting several genres inside one collection does not add slots.
- **Current state:** `collection_guarantee.run` injects the best above-threshold chunk for each selected collection absent after dedup (`services/api/app/rag/steps/collection_guarantee.py:8-39`). It keys on `r.collection`, so it already gives one slot per collection. After 5.1a the candidates it chooses from are already genre-filtered at retrieval.
- **Changes:**
  1. Tests in `services/api/tests/test_collection_guarantee.py` (create if absent).
     - With one collection and three genres selected, and no result from that collection after dedup, exactly one injected chunk.
     - An injected chunk never has an excluded genre.
     - With several collections selected, one slot each.
  2. A short docstring line in `collection_guarantee.py` stating that guarantees are per collection by decision (5.1c), with no genre logic.
  3. CLAUDE.md §5 pipeline description gains "collection guarantee is per collection, never per genre".
- **Acceptance checks:** New tests pass in GitHub Actions; no behavior change in existing tests.
- **Production safety:** Tests and comments only; no runtime change.
- **Needs Carter:** nothing.
- **Out of scope:** Changing `guarantee_min_score`. Guarantee changes for the merged papal collection beyond what 5.1b does.

### 5.1b. Collection-key migration (overview for the four PRs)

The plan merges `encyclicals`, `apostolic-exhortations` and `papal-documents` into one papal collection, renames `canon-law` to Church law and `medieval` to Theologians and spiritual writers, and moves Boethius to the Fathers. Pseudo-Dionysius is not in the corpus today (verified), so it is added directly to the Fathers in 5.6a.

**Proposed keys** (Carter confirms in 5.1b.1):

| Collection label (decided) | Proposed key | Replaces |
|---|---|---|
| Papal documents | `papal` | `encyclicals`, `apostolic-exhortations`, `papal-documents` |
| Church law | `church-law` | `canon-law` |
| Theologians and spiritual writers | `theologians` | `medieval` |

A fresh key `papal` is proposed rather than reusing `papal-documents`. Reusing it would make one stored value mean two different sets during the transition, and old clients could not be told apart from new ones.

**The four PRs, each deployable alone:**

1. 5.1b.1 API expand. Accept new keys. Old keys keep today's meaning. Results come back labeled in the vocabulary the request used.
2. 5.1b.2 Web switch. Offer only new keys and translate any old key it reads.
3. 5.1b.3 Data rewrite. Migration plus Qdrant payload rewrite plus datapipeline keys, run as one approved ops step.
4. 5.1b.4 Contract. Remove old keys from the API and the database constraint.

**Every hard-coded key location, verified on master `5475c49` (29 Sep).** "PR" says which 5.1b PR changes it.

| Location | What is there | PR |
|---|---|---|
| `services/api/app/rag/constants.py:1-12` | `VALID_COLLECTIONS`, all 10 keys | .1 adds, .4 removes |
| `services/api/app/rag/search_plan.py:42, 81-83` | validation against `VALID_COLLECTIONS` | .1 |
| `services/api/app/rag/pipeline.py:236` | drops keys not in `VALID_COLLECTIONS` | .1 |
| `services/api/app/models/preferences.py:28-36, 68-80` | preference validators reject unknown keys, including on GET (`routes/preferences.py:59-65` builds `PreferencesResponse` from stored rows, so one stored unknown key is a 500) | .1 tolerant read, .4 |
| `services/api/app/routes/preferences.py:15-21` | `_DEFAULT_PREFERENCES` has `encyclicals`, `canon-law` | .2 (after .1) |
| `services/api/app/routes/search.py:415-420` | restore filters `collection_outcomes` to `VALID_COLLECTIONS` | .1 |
| `services/api/app/rag/steps/hyde_s25.py:151-251` | `_COLLECTION_HYDE_PROMPTS` for `encyclicals`, `medieval`, `canon-law`, `apostolic-exhortations`, `papal-documents` | .1 adds new, .4 removes old |
| `services/api/app/rag/steps/hyde_s25.py:315-325` | `_COLLECTION_MAX_TOKENS` (`encyclicals` 400, `medieval` 350, `canon-law` 350; unknown keys fall back to 300 at line 465) | .1, .4 |
| `services/api/app/rag/dedup.py:65-67` | `_CHAPTER_KEYED_COLLECTIONS` includes `canon-law` | .1 adds `church-law`, .4 removes |
| `services/api/app/routes/evaluate.py:51-174` | numbered collection descriptions with hard-coded counts ("131 papal encyclicals", "30 post-synodal", "14 historical") and weighting hints naming old keys | .2 (switch prompt to new keys once web shows new keys), counts updated in every addition PR |
| `services/api/app/routes/compare.py:152` | retrieval-lab viewer `COLLECTIONS` list | .1 add, .4 remove |
| `services/api/compare_batch/runner.py:19-21`, `services/api/run_compare_batch.py:42-44` | batch defaults | .4 |
| `services/api/compare_batch/queries.py` (31 references) | lab query set collections | .4 (lab data, not product) |
| `services/api/scripts/run_eval_suite.py:42`, `scripts/run_all_pipelines.py:30` | eval defaults include `encyclicals` | .4; also re-point 0.3's harness |
| `services/api/app/config.py:132` and `tests/test_config_validation.py:29-45` | `cohere_concurrency` 10 and a test that it covers `len(VALID_COLLECTIONS)` | .1 changes the test to count scopes per search (see 5.1b.1) |
| `datapipeline/config.py:58-67` | `PER_COLLECTION_OVERLAP` (`medieval` 200, `encyclicals` 250, `canon-law` 300); `overlap_for` at `:137` | .3 |
| `datapipeline/publication.py:33-43` | `SOURCE_ADAPTERS` keyed by collection | .3 |
| `datapipeline/stages/parse.py:4-19` | V5 `BUILDERS` keyed by collection | .3 |
| `datapipeline/enrichment/prompts/classification.py:185-221`, `enrichment/prompts/generation/__init__.py:6-20` | V5 enrichment guidance keyed by collection | .3 |
| `datapipeline/scripts/vendor_sources.py:629-636`, `scripts/audit_sources.py:148-151` | vendor and audit registries keyed by source directory | leave the source directory names; keys only if they double as collection keys (they do not after .3) |
| `datapipeline/ingest/*.py` (`encyclicals.py:172`, `apostolic_exhortations.py:155`, `papal_documents.py:155`, `canon_law.py:86`, `thml_doc.py:89`) | collection string used both as the emitted collection and as a `document_id()` input | .3 changes only the emitted collection; ids come from the 2.1 registry |
| `datapipeline/README.md` adapter table, `datapipeline/SOURCES.md` | docs | .3 |
| `apps/web/src/lib/collections.ts:10-19` | `COLLECTIONS` with keys, labels, colors | .2 |
| `apps/web/src/app/globals.css:33-42` | `--color-collection-*` tokens | .2 adds, .4 removes |
| `apps/web/src/lib/search-draft.ts:33-37` | guest default collections include `encyclicals` | .2 |
| `apps/web/src/components/search/LoadingAnimation.tsx:24-34` | `PALETTE` keyed by collection with short codes | .2 |
| `apps/web/src/components/search/QuotaControl.tsx:9-10, 126` and `QuotaControl.module.css:59` | contrast sets for `apostolic-exhortations`, `canon-law`, `papal-documents`, and `.papalNumeral` | .2 |
| `apps/web/src/components/search/ChunkCard.tsx:53, 118` | `canon-law` citation shortening; author shown for `church-fathers` or `encyclicals` | .2 |
| `apps/web/src/components/reader/DocumentOverview.tsx:24`, `ReaderChrome.tsx:67` | `canon-law` reader wording | .2 |
| `apps/web/src/components/about/AboutPage.tsx:3-24` | descriptions keyed by collection | .2 (new keys, interim text), full rewrite in 5.7 |
| `apps/web/src/components/landing/LandingPage.tsx:14` | copy naming "encyclicals, and papal documents" | .2 |
| `apps/web/src/components/sources/SourcesPage.tsx:361, 432-444` | groups and filters by `COLLECTIONS` keys | .2 (group by translated key) |
| `apps/web/src/app/icon-preview/*` | dead design draft (CLAUDE.md §17) | leave |
| `user_preferences.default_collections` rows and column default (live default verified above; set in `0007_add_canon_law_collection.sql:11-13`) | stored keys | .3 |
| `searches.filters` (`collections` array and `collection_outcomes` object keys) | stored keys | .3 |
| `guest_trials.filters` | stored keys | .3 |
| `documents.collection` and `documents_collection_check` | stored keys and constraint | .3 widens, .4 narrows |
| Qdrant payload field `collection` on every point | stored keys | .3 |
| Test fixtures (API 10 files, datapipeline 15, web 6 files by `git grep -c`) | literal keys | each PR updates what it breaks |
| CLAUDE.md §15 ("10 collections"), §18 (chapter-keyed list), `apps/web/AGENTS.md` | docs | each PR |

### 5.1b.1. API accepts new collection keys (expand)

- **Type:** PR
- **Depends on:** 5.1a, 5.1c.
- **Goal:** The API understands both old and new keys and works whether or not stored data has been rewritten, so the web and the data can switch later in any order. No visible change.
- **Current state:** See the table above. Retrieval runs one scope per requested collection. Results carry the stored collection from the Qdrant payload (`retrieve_vector.py:52`) or `d.collection` (`retrieve_fts.py:19`). `GET /v1/preferences` raises on any stored key not in `VALID_COLLECTIONS`.
- **Changes:**
  1. `constants.py`.
     - `CANONICAL_COLLECTIONS` holds the target set: `bible`, `catechism`, `councils`, `papal`, `church-law`, `church-fathers`, `summa`, `theologians`, plus `roman-curia` once 5.3a lands.
     - `LEGACY_COLLECTIONS` maps each old key to `(new_key, genre_subset | None)`. `encyclicals` maps to `(papal, {encyclical})`. `apostolic-exhortations` maps to `(papal, {apostolic-exhortation})`. `papal-documents` maps to `(papal, every papal genre except those two)`. `canon-law` maps to `(church-law, None)`. `medieval` maps to `(theologians, None)`.
     - `VALID_COLLECTIONS = CANONICAL | LEGACY keys`.
  2. `collection_scope.py` (from 5.1a).
     - `scope_for(requested_key)` returns the stored values a scope reads, so it works before and after 5.1b.3. For a new key, it reads the new value and every legacy value mapped to it. For a legacy key, it reads its own old value, or the new value restricted to its genre subset. The subset clause means that after the rewrite `encyclicals` still returns only encyclicals, and before it the new value simply has no rows.
     - Qdrant expresses this as a `should` of two nested filters; SQL as `(d.collection = ANY($old) OR (d.collection = $new AND <genre clause>))`.
     - Requires genre on every papal document (5.1a acceptance).
  3. Label results with the requested key. After retrieval, set each row's `collection` to the scope key it was retrieved under. Then collection guarantee, `collection_outcomes`, dedup and the SSE `chunk` events all use the vocabulary the client sent. Old web clients keep seeing old keys, and new clients see new keys.
  4. `resolve_search_plan`. If a request names both a legacy key and the new key it maps to, drop the legacy key (no double retrieval). Log a structured field `legacy_collection_key` for every legacy key received, so Railway shows when old clients stop.
  5. HyDE.
     - Add prompts for `papal` (merge the three current prompts, `hyde_s25.py:163-249`, into one covering encyclicals, exhortations, letters, constitutions and bulls), `church-law` (the `canon-law` prompt, unchanged until 5.4 adds universal laws) and `theologians` (the `medieval` prompt broadened past the medieval period, because the collection will hold writers to the 1930s).
     - Add `_COLLECTION_MAX_TOKENS` entries `papal` 400, `church-law` 350, `theologians` 350.
  6. `dedup.py:65-67`. Add `church-law` next to `canon-law`.
  7. Preferences. Make `PreferencesResponse` on GET tolerant: drop unknown stored keys and fall back to defaults if none remain, instead of raising. PUT validation stays strict.
  8. Concurrency test (`tests/test_config_validation.py:29-45`). Count the most scopes one search can have, which is `max(len(CANONICAL), len(legacy-era set))` after the both-keys dedup in step 4, rather than `len(VALID_COLLECTIONS)`. The current defaults (Cohere 10, HyDE 48) still cover it.
  9. `compare.py:152`. Add the new keys.
- **Acceptance checks:**
  - Tests, before the data rewrite (fixtures with old stored values), prove each of these:
    - `papal` returns rows from all three old values.
    - `encyclicals` returns today's rows.
    - Results are labeled with the requested key.
  - The same tests after the rewrite (fixtures with new stored values) prove each of these:
    - `encyclicals` returns only genre `encyclical`.
    - `canon-law` still returns canons.
  - A request without any new key produces the same Qdrant and SQL filters as today.
  - GET preferences with a stored `saints` value returns 200.
  - `python3 -m pytest tests/` green.
  - PR description lists the table rows this PR changed.
- **Production safety:** Old keys keep identical behavior against today's data. New keys are only sent once 5.1b.2 ships. The tolerant GET removes an existing 500 risk. Rollback is a revert.
- **Needs Carter:** Confirm the three key names and their labels. Approve the merged papal HyDE prompt text.
- **Out of scope:** Web changes, data changes, removing old keys.

### 5.1b.2. Web switches to the new keys

- **Type:** PR
- **Depends on:** 5.1b.1 deployed.
- **Goal:** Users see nine collections instead of ten: Papal documents with a genre filter, Church law, and Theologians and spiritual writers. Saved preferences, history and bookmarks keep working.
- **Current state:** See the web rows of the 5.1b table. Web drops unknown keys in drafts (`lib/search-draft.ts:45-52`) and in restore (`useSearchPageExperience.ts:296-301`), and falls back to defaults or result collections.
- **Changes:**
  1. `lib/collections.ts`.
     - `COLLECTIONS` lists the new keys and labels, with `papal` taking one color.
     - `LEGACY_COLLECTION_KEYS` maps old key to new key.
     - `canonicalCollectionKey(key)` translates old keys to new ones.
     - `getCollectionMeta` translates first, so bookmarks, reader pages and `/sources` rows that still carry old stored values show the new label.
  2. `globals.css`. Add `--color-collection-papal`, `--color-collection-church-law` and `--color-collection-theologians`. Check whether collection colors have a light-theme override block; if one exists, add them there too (CLAUDE.md §9).
  3. `search-draft.ts`. `normalizeCollections` translates legacy keys, so preferences and guest `localStorage` drafts carrying old keys become new keys, then the existing debounced PUT saves them. The guest default becomes `bible, catechism, church-fathers, summa, councils, papal`.
  4. Restore path. Translate stored `filters.collections` and `collection_outcomes` keys, and turn a stored legacy key's genre subset into the draft's genre selection (a restored "encyclicals" search reopens as Papal documents with only encyclicals on).
  5. `LoadingAnimation.tsx`, `QuotaControl.tsx` and `.module.css`, `ChunkCard.tsx:53,118`, `DocumentOverview.tsx:24`, `ReaderChrome.tsx:67`, `SourcesPage.tsx` (group by translated key), `LandingPage.tsx:14`, `AboutPage.tsx`. Re-key to the new keys; each check that compares a key compares the translated key.
  6. API default preferences `routes/preferences.py:17`. Switch to `papal` and `church-law` in this PR's API half (tiny, safe after 5.1b.1).
  7. `routes/evaluate.py`. Switch the prompt to nine new keys with updated descriptions and counts. The Discover page renders from `COLLECTIONS`, so both change together here.
- **Acceptance checks:**
  - Vitest. Draft normalization of old keys; restore of an old-key search including the genre subset; `getCollectionMeta("encyclicals")` returns the Papal documents entry; QuotaControl's contrast tests re-keyed.
  - Manual check in both themes. Search, restore an old history item, open a bookmark in each renamed collection, view `/sources`, and view the guest mirror (`/search/guest`).
  - Lint zero errors.
  - PR includes screenshots.
- **Production safety:** The web sends only keys the API accepts since 5.1b.1. Stored data still carries old keys and is translated on read. Rollback is a Vercel rollback or revert; the API accepts both.
- **Needs Carter:** Approve colors and the interim About page and Discover wording.
- **Out of scope:** Data rewrite. The full About rewrite (5.7).

### 5.1b.3. Rewrite stored collection keys (migration plus Qdrant payload)

- **Type:** PR plus ops (one approved live step)
- **Depends on:** 5.1b.2 deployed. Registry (2.1) makes document ids independent of the collection key.
- **Goal:** Every stored value uses the new keys, including Boethius moving to the Fathers, with no re-embedding and no id changes. Users see no change except Boethius now appearing under Church Fathers.
- **Current state:**
  - Live key counts are in the facts table.
  - No `(collection, title, translation, author)` collision would result (verified 29 Sep for the papal merge; recheck at run time).
  - Qdrant payload rewrites without re-embedding already have a precedent in `datapipeline/scripts/reconcile_qdrant_payloads.py` (uses `set_payload`).
  - Embedding inputs contain author and title, not the collection key (`datapipeline/writers/search_writer.py:82-93`), so a key change needs no re-embed.
- **Changes:**
  1. Migration `supabase/migrations/00NN_collection_keys.sql` (next free number at merge time; do not reuse 0039, which 2.2a takes). One transaction:
     - Widen `documents_collection_check` to old plus new keys.
     - Change the `user_preferences.default_collections` column default to `{bible,catechism,church-fathers,papal,church-law,summa}`.
     - Nothing else. Data rewrites are not in the migration, so applying it is safe at any time.
  2. Script `datapipeline/scripts/rewrite_collection_keys.py`, dry run by default, `--apply` to write, refusing production without the 0.4 cutover flag. In Postgres, one transaction:
     - `documents.collection`. Map old to new.
     - Boethius. `UPDATE documents SET collection = 'church-fathers' WHERE id = <registry id for Consolation of Philosophy>`.
     - `user_preferences.default_collections`. Map each element, then de-duplicate keeping first occurrence. Cardinality can only fall, so the focused-quota constraint (`0034_focused_quota_preferences.sql`) still holds.
     - `searches.filters` and `guest_trials.filters`. Rebuild `collections` as the mapped, de-duplicated array. Rename `collection_outcomes` keys; when two old keys merge, keep the worse outcome. Add a `scopes` genre selection equal to the legacy subset, so a restore reproduces the old search. Only rows where `jsonb_typeof(filters) = 'object'` are touched, and the 0033 repair is re-checked first.
     - Leave the 15 `saints` rows alone; restore already ignores them.
  3. Same script, Qdrant, after the Postgres commit. `set_payload` with a filter selector per old value (`collection = encyclicals` gets `{"collection": "papal"}`, and so on), and one by `document_id` for Boethius. Run on the collection behind the alias.
  4. Datapipeline, same PR. So that the next publication cannot write old keys back:
     - Adapters emit the new collection.
     - `SOURCE_ADAPTERS` gets a composite `papal` adapter that builds encyclicals, apostolic exhortations and papal documents together, and removes the three old entries. Publishing only one of them under `papal` would let collection-wide pruning delete the other two.
     - `SOURCE_ADAPTERS` renames `canon-law` to `church-law` and `medieval` to `theologians`.
     - Boethius moves into the Fathers build.
     - `PER_COLLECTION_OVERLAP` gets `papal` 250, `church-law` 300, `theologians` 200. Carter to note that the 44 former exhortation and papal-document documents were embedded with 200-character overlap. `reembed_drifted_vectors.py` may flag them as drifted on a later run. That is harmless (a re-embed costs cents) but should not be mistaken for a defect.
     - Update `stages/parse.py`, the enrichment prompt maps, README and SOURCES.
     - `vendor_sources.py` keeps its source-directory names.
  5. Restart the API afterwards to clear the `/sources` cache.
- **Acceptance checks:**
  - Dry-run output (counts per table and per key, no user content) in the PR.
  - After apply, read-only checks:
    - Zero `documents` rows with old keys.
    - Zero old keys in `user_preferences`, `searches.filters->collections` (except `saints`) and `guest_trials.filters`.
    - Qdrant count by `collection` equals Postgres passage count per collection.
    - Boethius's passages carry `church-fathers` in both stores.
  - Datapipeline tests. The composite adapter emits 175 documents (131, 30 and 14 today, plus any added by then). `run_collection --collection papal --target reader --limit 1` against a local database writes `papal`.
  - Smoke search per collection with old and new keys.
- **Production safety:** 5.1b.1 made both old and new stored values readable under both key vocabularies, so the database commit and the Qdrant rewrite can land seconds or hours apart without breaking search. The rewrite is reversible with the same script's `--reverse`, which maps new values back. Boethius goes back by id; merged papal documents go back by their genre, and every papal document has one (5.1a check). Preference and filter de-duplication is not reversible, but losing a duplicate key changes nothing. The publish lock stops any publication between the merge and the ops step.
- **Needs Carter:** Approve applying the migration, approve `--apply` (Postgres and Qdrant), approve the API restart.
- **Out of scope:** Removing old keys from code or the constraint (5.1b.4). Adding Pseudo-Dionysius (5.6a).

### 5.1b.4. Remove old collection keys (contract)

- **Type:** PR
- **Depends on:** 5.1b.3 applied, and 14 days with no `legacy_collection_key` log lines (Railway filter), or Carter's call on the remaining traffic.
- **Goal:** One vocabulary of nine keys in code and database. No visible change.
- **Current state:** After 5.1b.3 no stored value uses an old key. The code still carries the legacy branches.
- **Changes:**
  1. `constants.py`. Remove `LEGACY_COLLECTIONS` and the old keys from `VALID_COLLECTIONS`. `scope_for` loses the legacy union branch.
  2. `hyde_s25.py`, `dedup.py`, `compare.py`, `compare_batch/*`, `run_compare_batch.py`, `scripts/run_eval_suite.py`, `scripts/run_all_pipelines.py`. Remove the old keys.
  3. Migration `00NN_drop_legacy_collection_keys.sql`. Narrow `documents_collection_check` to the new keys. `ADD CONSTRAINT` validates existing rows and fails the whole migration if any old value remains, which is the intended guard.
  4. `globals.css`. Remove old color tokens.
  5. Web keeps `LEGACY_COLLECTION_KEYS` and `canonicalCollectionKey` for reading browser `localStorage` and old links only. Carter to note: the plan says "old keys removed". This PR removes them from the API, the database and every product surface, and keeps a five-line read-side translation in the browser so guests' saved drafts do not reset. Delete it too if Carter prefers.
  6. CLAUDE.md §15 ("9 collections"), §18, `apps/web/AGENTS.md`.
- **Acceptance checks:**
  - `git grep -nE '"(encyclicals|apostolic-exhortations|papal-documents|canon-law|medieval)"' -- services apps/web/src datapipeline` returns only the web legacy map, migrations, source-directory names and dead `icon-preview` code.
  - Tests green.
  - Migration applied on a local database first.
- **Production safety:** Stored data no longer has old keys (5.1b.3 check). An old tab still open would send an old key, which `resolve_search_plan` drops, returning 400 only if nothing valid remains. The log check shows this traffic is gone. Rollback is a revert plus re-widening the constraint (additive).
- **Needs Carter:** Approve applying the migration. Decide on the web legacy map (step 5).
- **Out of scope:** Renaming source directories under `datapipeline/sources/`.

### 5.2. Rights inventory completed for every planned source

- **Type:** ops (research, recorded in a tracked file)
- **Depends on:** 0.2 (inventory file format), R6.
- **Goal:** Before any work is ingested, its row records the edition, why it is public domain or licensed, the source site's terms, and the credit line. The corpus stays legally defensible, and each addition PR can point at its row.
- **Current state:**
  - The rights review of 28 Sep is done and its memos are private (Decision log, "Rights review").
  - 0.2 creates the inventory. Research exists in `docs/research/2026-09-28-theologians-spiritual-writers-candidates.md` (lists A1, A2, B, C) and `docs/research/2026-09-28-scan-only-works-text-sources.md`.
  - Known open rights items:
    - Imitation of Christ renewal search (plan, Open items).
    - CCEL's request for permission to republish its editions (candidates memo, question 10).
    - ecatholic2000.com's copyright claim over transcriptions.
    - Newman Reader's claim.
    - aquinas.cc with no licence statement.
    - Sensus Fidelium not naming its editions.
    - Title-page dates still to confirm: Tanquerey 1930 printing (IA `spirituallife0000atan` and `MN41530ucmf_5`), Marmion *Christ in His Mysteries* (1923 or 1924), William of St Thierry *Golden Epistle* (1930), Bellarmine *Ascent of the Mind* (1928), Teresa's Stanbrook *Letters* volumes (all dated 1930 or earlier?), and every Pohle-Preuss and Koch-Preuss volume (not in the candidate memo; printings run past 1930, unverified).
  - **Carter to note (storage).** Compacted, a passage costs roughly 3.5 KB of database (123 MB of rows plus about 70 MB of indexes over 54,568 passages; estimate). An average passage is about 770 characters (42 MB of content over 54,568). So one million words is about 7,700 passages and about 27 MB. The A1 CCEL list alone is about 3 million words (candidates memo sizes), so about 80 MB, before the Fathers volumes and the scans. After compaction (about 230 MB) the planned P5 additions very likely pass 500 MB. Qdrant grows about 6 KB of raw vector per passage.
- **Changes:**
  1. One row per planned work in 5.3 to 5.6c. Columns:
     - Work, author, edition (translator, publisher, year, printing).
     - Source URL and format.
     - Public-domain basis: pre-1931 US publication, or a non-renewal search with the search date and the records searched (the Copyright Office's online catalog for post-1977 renewals, and the scanned Catalog of Copyright Entries for 1950 to 1977).
     - Site terms and the action taken: none, asked, or used only to check our own OCR.
     - Credit line text ("Sourced via CCEL.org", "Text: Libreria Editrice Vaticana").
     - Estimated words, passages and MB.
     - R6 status and rule A to H notes.
     - Status: cleared, blocked or excluded.
  2. A running storage total at the top. When the projected database size passes 450 MB, stop and ask Carter (Pro, or reorder the additions).
  3. Public facts only. Correspondence, and anything Carter has not sent, stays in the private memos.
- **Acceptance checks:** Every work named in 5.3 to 5.6c has a row with status cleared before its PR merges. Each addition PR links its rows. The storage total is updated in each addition PR.
- **Production safety:** Documentation only.
- **Needs Carter:** All correspondence with rights holders (CCEL, ecatholic2000, NINS for the Newman Reader, the Aquinas Institute if SCG is taken from aquinas.cc). The Pro decision when the storage total passes 450 MB.
- **Out of scope:** Paid licences (Decision log, "Licences": no spending in this cleanup). Any TheoCorpus translation (Decision log, "Rights review").

### 5.3a. Roman Curia: DDF doctrinal documents (from the parked branch)

- **Type:** PR, then an ops publish
- **Depends on:** P4, 5.1a (genre and issuer), 5.1b.4 (so the collection list changes once more, not interleaved), 5.2 rows for the 60 documents.
- **Goal:** A new Roman Curia collection with the Dicastery for the Doctrine of the Faith's doctrinal documents (1966 to 2026), so questions such as IVF, end-of-life care or human dignity reach the Church's most direct answers. Filterable by genre (declaration, instruction, note and so on) and issuer.
- **Current state:**
  - Local branch `feat/roman-curia-collection` (worktree `/Users/cartertate/repos/boc-roman-curia`, commits `6645a8b` and `2cba1b1` on master `5475c49`). It adds:
    - `datapipeline/ingest/roman_curia.py` (367 lines) and `datapipeline/tests/test_roman_curia.py` (176 lines).
    - A vendor list in `scripts/vendor_sources.py`.
    - `roman-curia` in `VALID_COLLECTIONS`, a HyDE prompt and `_COLLECTION_MAX_TOKENS` 350, Cohere concurrency 11, and the retrieval-lab list.
    - A web label and color in an `UNRELEASED_COLLECTIONS` list, so there is no toggle yet. `getCollectionMeta` falls back to it.
    - An About entry and a LoadingAnimation palette entry.
    - Migration `0039_add_roman_curia_collection.sql` widening `documents_collection_check`.
  - After review it keeps 60 documents; the Fatima dossier and the Professio fidei preliminaries are dropped. The vendored sources exist locally (`datapipeline/sources/roman-curia/`, 61 files).
  - The branch predates the planned document fields, the registry and the new keys.
- **Changes:**
  1. Rebase onto master after 5.1b.4. Resolve against the new `constants.py` shape (`CANONICAL_COLLECTIONS`), `collection_scope.py` and the nine-key web list.
  2. Renumber the migration to the next free number. The plan reserves 0039 for 2.2a. Rebuild it from the constraint as it stands then (new keys plus `roman-curia`), not from the branch's old list.
  3. Emit document fields through 2.2a and 2.3:
     - `genre` from the page (declaration, instruction, doctrinal note, note, letter, responsum).
     - `issuer = ddf`, with the name printed at publication in the issuer display field (CDF before 5 June 2022, DDF after; source memo).
     - Date, and papal approval wording where the text has it.
     - AAS citation where the index gives one.
     - Credit line "Text: Libreria Editrice Vaticana".
  4. Register the 60 documents in the 2.1 registry with frozen ids.
  5. Drop the branch's Cohere concurrency change if the scope count still fits 10 (nine canonical keys plus `roman-curia` makes 10). Keep the test from 5.1b.1.
  6. Release switch in the same PR, dormant until data exists: keep `roman-curia` in `UNRELEASED_COLLECTIONS`. A second tiny PR moves it into `COLLECTIONS` and adds it to the `/evaluate` prompt after the ops publish (branch's CLAUDE.md §15 note).
  7. Ops publish (live step). `run_collection.py --collection roman-curia --target both` with the cutover flag. Attach the release report.
- **Acceptance checks:**
  - `datapipeline` tests including `test_roman_curia.py` pass locally (sources needed; the report goes in the PR template section).
  - Release report shows 60 documents, no passage under 20 characters, no endnote cards, and genre set on every document.
  - After publish, targeted questions are answered from the collection (Dignitas Personae on embryo adoption, Dignitas Infinita on human dignity, Iura et Bona on end-of-life care, Dominus Iesus on salvation outside the Church).
  - Storage total in 5.2 updated.
- **Production safety:** The collection is accepted but not offered until the release PR. The migration is additive. The publish writes only `roman-curia` rows. Rollback before release is to delete the collection's rows with the reader wipe (`--wipe-reader --confirm-reader-wipe roman-curia`; no user data can point at unoffered passages) and `--reset-search-index`.
- **Needs Carter:** Approve the migration, the publish, and the release PR.
- **Out of scope:** Pontifical Biblical Commission, the social doctrine Compendium, liturgical norms (5.3b). Rulings on individual theologians, apparition cases, procedural norms, press material (excluded by the branch's scope).

### 5.3b. Roman Curia: Pontifical Biblical Commission, social doctrine Compendium, liturgical norms

- **Type:** PR per source family, then ops publishes
- **Depends on:** 5.3a, 5.2 rows, R6.
- **Goal:** Complete the Roman Curia collection as the plan defines it. Biblical Commission documents appear under their own issuer, not as DDF teaching, and the Compendium of the Social Doctrine of the Church answers social-teaching questions by numbered paragraph.
- **Current state:**
  - Not vendored.
  - The source memo says Biblical Commission and International Theological Commission texts need their own authorship and authority metadata (*Praedicate Evangelium* art. 77).
  - The Compendium of the Social Doctrine is on vatican.va with an analytical index (`corpus-expansion-candidates.md`, gap 2).
  - Liturgical norms in ICEL English are dropped (Decision log, "Editions"). The GIRM's English is ICEL (unverified per document); Redemptionis Sacramentum and the Directory on Popular Piety need a per-document translation check.
  - The International Theological Commission is not named in the plan's Roman Curia row; leave it out unless Carter adds it.
- **Changes:**
  1. Vendor lists in `scripts/vendor_sources.py` for each family, stored under `datapipeline/sources/roman-curia/`.
  2. Reuse `ingest/roman_curia.py`'s parser. Add issuer `pbc`, `pcjp` (Pontifical Council for Justice and Peace) or the worship dicastery per document, and genre `compendium` for the social doctrine Compendium. Its numbered paragraphs become anchors.
  3. Each liturgical document gets a translation check recorded in 5.2 (Vatican English, or ICEL and therefore dropped).
- **Acceptance checks:** Same as 5.3a, per family. Issuer filter isolates Biblical Commission documents.
- **Production safety:** As 5.3a. Additions to a released collection become visible document by document; each document is written in one reader transaction (`reader_writer.write_document`, CLAUDE.md §4).
- **Needs Carter:** Approve each publish. Decide on the International Theological Commission.
- **Out of scope:** Missal, Lectionary or Liturgy of the Hours texts.

### 5.4. Papal and universal law

- **Type:** PR, then ops publish
- **Depends on:** 5.1b.4 (keys `papal`, `church-law`), 2.2a (`searchable`, notes, supersession links), 5.2 rows.
- **Goal:** Questions about how a pope is elected or what happens during a vacancy are answered from *Universi Dominici Gregis* as currently in force, with its earlier wording available as labeled history. Two vendored papal documents that never reached the corpus become searchable.
- **Current state:**
  - `datapipeline/sources/apostolic-exhortations/a-new-hope-for-lebanon.html` and `datapipeline/sources/papal-documents/ubicumque-et-semper.html` are vendored but in neither manifest nor the database (verified locally; plan Decision log).
  - Manifest lists live in `scripts/vendor_sources.py:382` (`APOSTOLIC_EXHORTATIONS`) and `:447` (`PAPAL_DOCUMENTS`).
  - UDG is not vendored. Per the source memo, vatican.va's English page is the consolidated text current from 22 February 2013 and links the 1996 original, *De aliquibus mutationibus* (2007, Latin; replaced number 75) and *Normas nonnullas* (2013; modified numbers 35, 37, 43, 46 §1, 47 to 51 §2, 55 §3, 62, 64, 70 §2, 75, 87). The 30 April 2025 declaration on number 33 is a dispensation, not an amendment.
  - Rule F is current text only in search, superseded versions as labeled linked history.
- **Changes:**
  1. `vendor_sources.py`. Add A New Hope for Lebanon (1997, post-synodal apostolic exhortation) to `APOSTOLIC_EXHORTATIONS` and Ubicumque et Semper (2010, motu proprio) to `PAPAL_DOCUMENTS`. Regenerate manifests. Both publish into `papal` with genres `apostolic-exhortation` and `motu-proprio`.
  2. UDG.
     - New adapter `datapipeline/ingest/universal_law.py` emitting collection `church-law`.
     - Document "Universi Dominici Gregis (as amended 2013)" is searchable, with anchors by number and section and author "Pope John Paul II" with the amendment note.
     - Three history documents (1996 original, 2007 motu proprio, 2013 motu proprio) are stored with `searchable = false`, linked from the current text's note (2.2a fields), and labeled "superseded text, kept as history".
     - The 2007 act is Latin only. Per rule E it stays in the reader with a note and out of search, which `searchable = false` already gives.
     - The 2025 declaration is not ingested (application material, not law). Mention it in the document note with its link.
  3. HyDE. Broaden the `church-law` prompt from "a single canon of the 1983 Code" to "a provision of the Church's universal law, such as a canon of the 1983 Code or a numbered norm of an apostolic constitution".
  4. `dedup.py` chapter-keyed list already includes `church-law` (5.1b.1); confirm UDG passages carry `chapter_key` by chapter so the per-source cap works per chapter.
- **Acceptance checks:**
  - Release report shows 2 new papal documents and 4 UDG documents, of which 1 is searchable.
  - A search for "how many votes are needed to elect a pope" returns UDG number 75 in its 2013 wording.
  - The 1996 wording never appears in search results and opens in the reader with the superseded label.
  - `/sources` lists all four UDG documents with their status.
- **Production safety:** Additions only. `searchable = false` keeps superseded text out of search through the 2.2b filter. Rollback is to remove the documents with a targeted publish and prune, or a tombstone if anyone bookmarked them.
- **Needs Carter:** Approve the publishes. Confirm UDG belongs in Church law rather than Papal documents (the plan's collection table puts it in Church law; this is a confirmation, not a reopening).
- **Out of scope:** Other universal laws (for example *Praedicate Evangelium*, *Vos estis lux mundi*). Propose them as a follow-up.

### 5.5. Catechisms: Compendium of the CCC, Roman Catechism

- **Type:** PR per work, then ops publish
- **Depends on:** 5.2 rows, R6, and 5.6c's OCR tooling for the Roman Catechism if no clean text passes R6.
- **Goal:** Short question-and-answer entries from the Compendium of the Catechism (2005) linked to the full Catechism's paragraphs, and the Roman Catechism of the Council of Trent (McHugh and Callan, 1923) as a historical catechism, both in the Catechism collection.
- **Current state:**
  - The Catechism collection is one document, `document_id("catechism")` (`datapipeline/ingest/catechism.py:256`).
  - The Compendium is on vatican.va (`corpus-expansion-candidates.md`, gap 6), and the rights review covered it (Decision log).
  - McHugh and Callan was published 1923 (US, Wagner), so it is public domain in the US. A clean typed text is unverified; the scan-only memo did not cover it.
  - The Catechism HyDE prompt is written for the CCC's style (`hyde_s25.py:152-161`).
- **Changes:**
  1. Compendium. New adapter `ingest/catechism_compendium.py`.
     - One passage per question with its answer, anchor the question number.
     - Keep the CCC paragraph references as a structured field so the reader can link to them. They are not part of passage text.
     - Credit "Text: Libreria Editrice Vaticana".
     - Genre `compendium`.
  2. Roman Catechism. R6 first looks for a clean typed 1923 text and confirms the edition against a scan.
     - If one exists, write an adapter over it.
     - If not, follow 5.6c's method and gate, as its own PR.
     - Genre `catechism`, year 1566 for the work and 1923 for the translation, note "Catechism of the Council of Trent, a historical catechism; for current teaching see the Catechism of the Catholic Church".
     - Strip McHugh and Callan's notes and introduction (rule G).
  3. HyDE. Leave the CCC prompt, but add a retrieval follow-up to test whether the Compendium's short Q&A form is found; do not tune here.
- **Acceptance checks:**
  - Compendium has 598 questions (count from the source; confirm at build) and each answer is one passage.
  - Focused search on Catechism still returns 10 when asked (per-chapter cap, CLAUDE.md §18).
  - For the Roman Catechism, the 5.6c gate if OCR was used.
- **Production safety:** Additions to a released collection; per-document transactions. Rollback by pruning the documents.
- **Needs Carter:** Approve each publish.
- **Out of scope:** Other catechisms (Baltimore, Pius X).

### 5.6a. Church Fathers additions and the Pseudo-Dionysius addition

- **Type:** PR per author or volume group, then ops publish
- **Depends on:** P4, 1.8b (the NPNF editorial strip, reused), 2.1, 5.2 rows, R6, and R1 where a work's authorship is doubtful.
- **Goal:** The Fathers collection gains Basil, Cyril of Jerusalem, Gregory Nazianzen, Gregory the Great, John Chrysostom, Ambrose and Leo the Great, all Doctors of the Church, plus Pseudo-Dionysius, so common questions about the Holy Spirit, baptism, pastoral care and the priesthood reach their classic patristic sources.
- **Current state:**
  - None of the seven authors is in the corpus, and neither is Pseudo-Dionysius (verified 29 Sep).
  - Vendored Fathers sources are 10 ThML files (`datapipeline/sources/church-fathers/`, for example `apostolic fathers.xml`, `third-century.xml`) plus the vendor list at `scripts/vendor_sources.py:62`.
  - ThML parsing is `datapipeline/ingest/thml_doc.py` (document id from collection, author and title at `:89`, replaced by registry lookup after 2.1).
  - NPNF volume identifiers on CCEL (from memory of CCEL's catalogue; confirm each in R6):
    - Basil, npnf208.
    - Cyril of Jerusalem and Gregory Nazianzen, npnf207.
    - Leo the Great and Gregory the Great's *Pastoral Rule* and letters, npnf212.
    - Gregory the Great's remaining letters, npnf213.
    - Ambrose, npnf210.
    - Chrysostom, npnf109 to npnf114 (six volumes).
  - Pseudo-Dionysius comes from CCEL `dionysius/works` (Parker, 1897 and 1899; both *Hierarchies* are in the second volume), which the scan memo found clean apart from light OCR slips, header "Rights: public domain". Do not use CCEL's separate `dionysius/celestial` (unattributed translation).
  - Sizes are unmeasured. Chrysostom's six volumes are the largest addition in P5 (estimate in the millions of words; measure before building).
- **Changes:**
  1. Vendor list entries per volume. Split into PRs in this order:
     - Basil.
     - Cyril of Jerusalem with Gregory Nazianzen.
     - Gregory the Great with Leo.
     - Ambrose.
     - Pseudo-Dionysius.
     - Chrysostom, one PR per volume, each gated on the 5.2 storage total.
  2. Reuse the NPNF editorial strip from 1.8b (prolegomena, introductions, notes, bracketed comments, "Argument" summaries) under rule G, copying authenticity judgments into attribution labels first.
  3. Attribution per rule H, and rules B to D per work. Examples to research in R1 and R6, all unverified:
     - Letters in Basil's corpus judged spurious (for example the Apollinaris correspondence).
     - Spurious homilies in the Chrysostom volumes.
     - Ambrose volume items of doubtful authorship.
     Label each work genuine, disputed, pseudonymous or anonymous from the Clavis Patrum Graecorum or Latinorum.
  4. Pseudo-Dionysius. Author label "Pseudo-Dionysius (about 500), writing under the name of Dionysius the Areopagite" (candidates memo, section 4). Strip Parker's prefaces and notes. Fix OCR slips found by the dictionary check ("St.. Paul", "Dipnysius"). Rule D applies (received work). Collection `church-fathers` directly.
  5. HyDE. The Fathers prompt already fits (`hyde_s25.py:174-184`); no change.
- **Acceptance checks:**
  - Release report per PR with passage counts, no editorial passages (coverage test from 0.1a), and author labels.
  - Storage projection and actual growth recorded against 5.2's total.
  - Targeted questions answered from the new sources (Basil *On the Holy Spirit*, Cyril's *Catechetical Lectures* on baptism, Gregory's *Pastoral Rule*, Chrysostom *On the Priesthood*).
- **Production safety:** Additions, with per-document transactions, behind the publish lock. Rollback per PR by pruning its documents.
- **Needs Carter:** Approve each publish. Decide the Pro upgrade when the storage total passes 450 MB (5.2).
- **Out of scope:** Replacing translations already in the corpus (P1.2 handles council sources; On the Incarnation moved in P1). Other Fathers not named in the plan (for example Bede and John Damascene, both before 750). Propose them later.

### 5.6b. Theologians and spiritual writers from CCEL ThML and Gutenberg text

- **Type:** PR per author or small group, then ops publish
- **Depends on:** 5.1b.4 (key `theologians`), 1.9 (the medieval adapter fixes), 5.2 rows, R1 (rule A and Church-act checks, including the Pensées' Index status), R6.
- **Goal:** The Theologians and spiritual writers collection gains the classic Catholic spiritual writers and later theologians whose texts are already clean (CCEL ThML or Project Gutenberg): Teresa, Francis de Sales, Catherine, Julian, Thérèse, Ignatius, Alphonsus, Newman's Catholic works, more Bernard, Aquinas outside the Summa, Chesterton's Catholic works and others.
- **Current state:**
  - Collection has 6 documents today (Anselm 3, Boethius, the Imitation, On Loving God; verified).
  - Candidate works, editions and strip notes are in the candidates memo sections 2.3 and 2.4. Decisions in the plan fix the editions:
    - No Peers.
    - Lewis 1864 for the Spiritual Canticle, so the Canticle goes to 5.6c, not CCEL's typed file.
    - Gutenberg 13871 for Brother Lawrence.
    - Catena in, attributed per quotation.
    - Manuals all in.
    - Dante out.
    - Pensées in (Trotter 1910), Provincial Letters out.
    - Orthodoxy, the Parochial and Plain Sermons and Stein's pre-1922 works out.
    - Newman's *Development* in the 1878 edition he revised as a Catholic.
- **Changes:**
  1. Works in this item (text sources only; scans go to 5.6c). Each is one PR or grouped by author. Each needs its 5.2 row and R6 check.
     - CCEL ThML:
       - Teresa, *Interior Castle* (Stanbrook 1921) and *Life* (Lewis 1904).
       - Francis de Sales, *Introduction to the Devout Life* (confirm the Rivingtons year) and *Treatise on the Love of God* (Mackey).
       - Catherine, *Dialogue* (Thorold; confirm whether full 1896 or abridged 1907; if abridged, use the full edition from IA in 5.6c).
       - Julian, *Revelations* (Warrack 1901).
       - Thérèse, *Story of a Soul* (Taylor 1912).
       - Ignatius, *Spiritual Exercises* (Mullan 1914) and *Autobiography* (O'Conor 1900).
       - *Cloud of Unknowing* (Underhill 1912).
       - Hilton, *Scale of Perfection* and the *Treatise to a Devout Man* (1901).
       - *Cell of Self-Knowledge* (Gardner 1910, without the Margery Kempe extracts).
       - Rolle, *Fire of Love* and *Mending of Life* (Comper 1914).
       - Ruusbroec (Wynschenk Dom 1916).
       - Tauler, *Inner Way* (Hutton 1901).
       - Suso, *Little Book of Eternal Wisdom* (1910) and *Life* (Knox 1865).
       - Bernard, *Letters* (Eales 1904).
       - Anselm, *Devotions* (Webb 1903).
       - Chesterton, *The Everlasting Man* (1925).
       - Newman, *Dream of Gerontius* (1865).
       - Pascal, *Pensées* (Trotter 1910).
       - Aquinas, *Catena Aurea* on Matthew and Mark (Oxford 1841 to 1842).
     - Gutenberg:
       - Alphonsus, *Glories of Mary* (72411).
       - Caussade, *Abandonment* (52057, labeled as Ramière's edition).
       - Brother Lawrence (13871).
       - Newman, *Apologia* (19690 or 22088), *Development* (35110; R6 confirms it reproduces the 1878 revision), *Idea of a University* (24526) and *Grammar of Assent* (34022, 1874 edition).
       - Catherine, *Letters* (Scudder, 7403, commentary stripped).
       - Mechthild extracts (35811, labeled selections).
       - Chesterton, *St. Francis of Assisi* (63084) and *The Catholic Church and Conversion* (76305).
       - Francis de Sales, *Maxims and Counsels* (73661).
  2. Excluded here by decision or by the memos' rights flags. Do not ingest:
     - Dante.
     - Pascal's *Provincial Letters*.
     - Fénelon's *Maxims of the Saints* and *Spiritual Progress*.
     - Guyon, Molinos, Eckhart.
     - Chesterton's *Orthodoxy* and *St. Thomas Aquinas* (1933).
     - CCEL's Peers files.
     - CCEL's Stevens *Dialogue of Comfort*, Tobin *Uniformity*, Epworth Brother Lawrence and Heritage *Little Flowers*.
     - Gutenberg 5657.
     - *On Cleaving to God* under Albert's name.
     - Tauler's *Following of Christ*.
     - *Theologia Germanica* unless R1 clears it.
     - Rickaby's abridged *Of God and His Creatures* unless Carter chooses it over the complete English Dominican SCG (5.6c).
  3. Adapters.
     - ThML goes through `ingest/thml_doc.py` with collection `theologians`, a per-work strip list (the memo's "Strip" notes, rule G), and CCEL staff descriptions never indexed (Decision log).
     - Gutenberg needs a new `ingest/gutenberg_text.py` that removes the Project Gutenberg header and licence block, splits by the work's own chapter headings (per-work config), and records the ebook number as provenance.
     - Each document records genre (`treatise`, `letters`, `autobiography`, `sermons`, `commentary`, `apologetics`), the translation's year on the card, and the credit line ("Sourced via CCEL.org" where applicable).
  4. Catena Aurea (decided: each quotation attributed to the Father quoted).
     - One passage per quotation, because grouping several quotations would put one Father's words under another's name.
     - Passage-level author is the Father (map CCEL's abbreviations such as "Chrys.", "Aug.", "Greg." to full names with a tested table).
     - Display is "Chrysostom, quoted in Aquinas's Catena Aurea". The document author is "Thomas Aquinas (compiler)".
     - Short quotations fall under `MIN_CHUNK_LENGTH` 50 (`datapipeline/config.py:53`). Exempt Catena passages rather than merge across Fathers, and merge only consecutive quotations from the same Father on the same verse.
     - This needs a passage-level author field. Confirm 2.2a provides it; if not, it is a small additive migration in this PR.
     - **Carter to note (unverified, research before this PR).** The Catena often quotes "Pseudo-Chrysostom", the *Opus imperfectum in Matthaeum*, whose author most scholarship identifies as Arian. R1 should decide under rules A and B whether those quotations stay, labeled "Pseudo-Chrysostom (Opus imperfectum)", or go. The Glossa quotations need an attribution too.
     - Luke and John are only on IA or ecatholic2000, so they go to 5.6c.
  5. Pensées. Carry the "Index status still to be checked (R1)" note; if R1 finds a prohibition, rule A removes it before publish.
- **Acceptance checks:**
  - Per PR, the release report shows no editorial passages (coverage test), author and translation labels, and genre set.
  - Storage projection against 5.2's total.
  - Catena. 100% of passages carry a quoted-author label; a unit test covers the abbreviation table; no passage mixes two Fathers.
  - Targeted questions per work (for example "dryness in prayer" returns Teresa or Julian; "the little way" returns Thérèse).
- **Production safety:** Additions behind the publish lock, per-document transactions. Rollback per PR by pruning.
- **Needs Carter:** Approve each publish. Choose between Rickaby's abridged SCG and the complete English Dominican SCG (5.6c). Decide the Pseudo-Chrysostom question after R1.
- **Out of scope:** Scanned works (5.6c). Anything in the candidates memo's list B (needs payment). Retrieval tuning for the enlarged collection.

### 5.6c. Scanned works, one PR per work

- **Type:** PR per work, then ops publish
- **Depends on:** 5.6b's Gutenberg adapter pattern, 5.2 rows, R6, and 5.1b.4.
- **Goal:** Recover important works that exist only as page scans (John of the Cross in Lewis's translation, Teresa's *Foundations*, *Letters* and *Way of Perfection*, Tanquerey, Marmion and others) with text accurate enough to quote, each labeled as scanned.
- **Current state:** Decided method (Decision log, "OCR and scanned works"):
  - Use a clean typed text where one exists, after confirming it is the planned edition. 19 of the 48 scan-only works have one (scan-only memo).
  - Where the clean copy's site claims copyright (ecatholic2000.com), ask the site or use it only to check our own OCR.
  - For the rest (23 works plus the missing parts of 6):
    - A script strips page furniture and rejoins broken words.
    - A language model fixes character-level errors under hard limits. An edit changing more than about 2% of a passage's words is rejected, and the raw OCR is kept.
  - Gate before ingestion. The unrecognized-word rate on body text must be within 1 point of the clean baseline, and 20 random passages are checked against the page images.
  - Scanned passages carry a source label.
  - John of the Cross (*Ascent*, *Dark Night*, *Living Flame*) and Teresa (*Foundations*, *Letters*, *Way of Perfection*) go first.
- **Changes:**
  1. Shared tooling PR first (no publish).
     - New package `datapipeline/ocr/` with:
       - `fetch.py`, which downloads IA djvu text and page images for an item id into gitignored `sources/scans/<item>/`.
       - `furniture.py`, which removes running heads, page numbers, signature marks and margin notes by repeated-line and position rules, and rejoins hyphenated line breaks.
       - `correct.py`, which runs the model pass with the 2% word-change limit per passage, keeps raw text, and caches results in `datapipeline/cache.db` keyed by input hash.
       - `gate.py`, which computes the unrecognized-word rate on body text against a dictionary plus a per-work allow-list of names and archaisms, compares it to the clean baseline, and draws 20 random passages with their page image references into a review sheet.
     - The model is a config setting in `datapipeline/config.py`, env-overridable, with cost recorded per work.
     - Unit tests for `furniture.py` and the 2% limit run in GitHub Actions on fixture text.
  2. Clean baseline per work. Prefer a clean text by the same translator and period, such as Lewis's typed *Spiritual Canticle* on CCEL for John of the Cross. Otherwise use the corpus's own ThML texts of the same decade. Record which baseline in the PR.
  3. One PR per work, each with:
     - The IA item id and the title-page date (5.2).
     - The strip list (introductions, notes, Wiseman's introduction for Lewis's John of the Cross, Faber's preface).
     - A structure config (chapters and numbered paragraphs).
     - The gate report.
     - The completed 20-passage review sheet.
     - Source label "From a scanned edition (Internet Archive <id>); errors possible".
  4. Order after the six priority works:
     - The clean-text group, where the only work is an edition check and possibly a request to the site:
       - Bernard's Canticle sermons (Mount Melleray), *On Consideration* and *Grace and Free Will* (ecatholic2000; ask, or check our OCR against it).
       - Bonaventure's *Life of St Francis* (Sensus Fidelium).
       - Bellarmine's *Art of Dying Well* and *Eternal Happiness*.
       - Luis of Granada, *Sinner's Guide* (Wikisource Noonan 1884).
       - Liguori's *Preparation for Death*.
       - Montfort (compare with the 1863 scan, since many copies are the 1941 revision).
       - Catena on Luke and John.
       - Robinson's *Writings of St Francis*.
     - Then OCR-only works by value:
       - Tanquerey 1930.
       - Marmion *Christ the Life of the Soul*.
       - Aquinas Rawes sermons (*Lord's Prayer*, *Commandments*).
       - Scupoli (Rivingtons 1875 clean text is a different edition; compare with Burns 1846).
       - The Alphonsus Centenary volumes (map volumes to titles first).
       - Gertrude, Scheeben (credited "after Nieremberg"), Möhler, Knox, Chesterton *The Thing*, Fisher, Faber, Lallemant, William of St Thierry, John of Avila, Elizabeth of the Trinity (her own writings only), Vianney (labeled as recorded sayings).
       - Complete SCG (English Dominican 1923 to 1929) if Carter chooses it.
       - Pohle-Preuss and Koch-Preuss per volume once 5.2 confirms pre-1931 printings.
     - Adaptations are credited with the adapter ("Joseph Pohle, adapted by Arthur Preuss").
  5. Excluded by flags. Middle English Birgitta (EETS 1929), unless Carter wants it.
- **Acceptance checks:**
  - Gate passes (rate within 1 point of baseline; 20 of 20 passages match the page images after correction, with any mismatch fixed and the sheet re-run).
  - Raw OCR kept alongside (gitignored).
  - Release report and storage projection per PR.
  - Model cost stated in the PR.
  - The PR template's local source-check section filled in.
- **Production safety:** Tooling PR changes nothing in production. Each work is an addition behind the publish lock. A work that fails the gate is not published. Rollback per work by pruning its documents.
- **Needs Carter:** Approve each publish. Send requests to ecatholic2000 where its text is used as more than a proofreading aid. Choose the SCG edition. Review time for the 20-passage checks (about 30 to 60 minutes per work, per the Decision log).
- **Out of scope:** Any TheoCorpus translation. Peers editions. Buying clean texts.

### 5.7. About page: "What's in TheoCorpus and why"

- **Type:** PR
- **Depends on:** 5.1b.4, and the additions it describes (5.3 to 5.6c) published, or at least the ones Carter wants described. 2.4c's factual fix has already shipped.
- **Goal:** The About page explains what is in the corpus and why:
  - Each collection and what it holds.
  - The inclusion rules in plain language.
  - Who is excluded and the Church act behind each exclusion.
  - Translations, rights and credits.
  - How to report an error.
  The curation becomes auditable.
- **Current state:**
  - `apps/web/src/components/about/AboutPage.tsx` renders `COLLECTION_DESCRIPTIONS` keyed by collection (`:3-24`). Its descriptions name authors not in the corpus (Origen, Chrysostom, Bonaventure, Hildegard, Duns Scotus; the plan's "Product copy"), and 2.4c fixes that first.
  - Guest mirror is `/guest/about` (CLAUDE.md §10).
  - Counts should come from `/sources` (Decision log, "About page").
- **Changes:**
  1. Rewrite `AboutPage.tsx` into sections.
     - **Collections.** Nine collections, what each holds and why. Counts come from the `/sources` response the app already caches (AppContext holds the cached source corpus, CLAUDE.md §13), not hard-coded numbers.
     - **Rules.** Rules A to H in plain language.
     - **Excluded, with the act cited.** Exclusions by a Church act, with author, act and date:
       - Origen (Constantinople II, 553).
       - Novatian (Roman synod under Cornelius, 251).
       - Tatian (testimony of Irenaeus, *Against Heresies* 1.28.1, and Eusebius 4.28-29).
       - Arnobius (written before baptism, Jerome's *Chronicle*).
       - Tertullian's later works (Benedict XVI, general audience of 30 May 2007).
       - The Apostolic Constitutions outside the canons (Trullo canon 2).
       - The forged Ignatius letters.
       - Alexander of Lycopolis (not a Christian).
       - For the theologians list, Pascal's Provincial Letters (Index, 1657), Fénelon's *Maxims*, Molinos and others R1 confirmed.
       Scope decisions (Dante, bishops' conferences, the Eastern code until licensed) are listed separately as "not included, and why", not as condemnations.
     - **Translations and rights.** Public-domain editions, sources credited when a passage is opened, no translations of our own.
     - **Report an error.** Link to `/feedback` and `/guest/feedback`.
  2. Keep the page's text in one data module (for example `components/about/aboutContent.ts`) so a rule-change PR edits one file. Add a PR-template checklist item "About page updated if a rule changed" (Decision log, "About page").
  3. Update `LandingPage.tsx:14` to match.
- **Acceptance checks:**
  - Every excluded name on the page has a citation that matches the plan or R1.
  - No author named on the page is absent from `/sources` unless listed as excluded.
  - Vitest renders both the authenticated and guest routes.
  - Lint clean.
  - Screenshots in both themes.
  - Carter reads the final text.
- **Production safety:** Copy change only; rollback is a revert.
- **Needs Carter:** Approve the final wording, especially the excluded list.
- **Out of scope:** A separate per-document provenance page.

### 5.8. Eastern Catholic code (blocked)

- **Type:** decision (blocked)
- **Depends on:** A licence for an English translation.
- **Goal:** Add the *Codex Canonum Ecclesiarum Orientalium* (1990) to Church law when an English text can be used legally.
- **Current state:**
  - The Holy See publishes it in Latin (`corpus-expansion-candidates.md`, gap 5).
  - The Canon Law Society of America sells a Latin-English edition updated in 2024.
  - Rule E keeps untranslated text out of search. The Decision log says no licence spending in this cleanup.
- **Changes:** None until unblocked. When unblocked:
  - A `church-law` adapter distinguishing Eastern from Latin canons (issuer or genre `cceo`).
  - Current text per rule F.
  - An anchor scheme that cannot collide with the 1983 Code's canon numbers.
- **Acceptance checks:** Not applicable while blocked.
- **Production safety:** Nothing changes.
- **Needs Carter:** Decide when to revisit licences (after the free phase ships, per the Decision log).
- **Out of scope:** Ingesting the Latin text as searchable.

### RF. Retrieval follow-ups (parent placeholder)

- **Type:** decision (tracking parent)
- **Depends on:** 4.2's post-cutover baseline, and the P5 additions whose effects it measures.
- **Goal:** One place to collect retrieval changes that the cleanup made visible but deliberately did not make, so each is judged against the new baseline and the `hyde_cohere_luna_hydesample` noise floor.
- **Current state:** Nothing opened. Candidates gathered while writing these specs:
  - Genre-aware HyDE for Papal documents and Roman Curia (5.1a leaves one prompt per collection).
  - Whether the Compendium's Q&A form is found by the CCC-style prompt (5.5).
  - One HyDE prompt spanning 12th to 20th century writers in `theologians` (5.1b.1).
  - The same Father appearing twice, in his own work and in the Catena (Decision log weakness).
  - Authority-aware ranking for Roman Curia documents with papal approval (source memo).
  - The per-chapter cap for new chapter-keyed documents such as UDG (5.4).
- **Changes:** Open child issues from the list above, each with an eval plan before code.
- **Acceptance checks:** Each child shows its effect against the baseline and noise floor.
- **Production safety:** Each child ships as its own PR under the usual rules.
- **Needs Carter:** Prioritize the children.
- **Out of scope:** Anything that changes which texts are in the corpus.
