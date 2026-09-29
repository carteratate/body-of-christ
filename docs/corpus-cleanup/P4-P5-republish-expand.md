# Corpus cleanup, Phases 4 and 5: republish, reorganize, expand

**Before implementing any item in this file, follow `README.md` in this folder. It says to ask Carter the item's open questions first, record the answers, and update other specs only in the ways it allows.**

Work specifications for Phase 4 (republish) and Phase 5 (reorganize and expand) of `docs/2026-09-28-corpus-cleanup-plan.md`. Written 29 September 2026 and revised the same day to follow the plan's "Cross-cutting design decisions" (D1 to D11), which override anything here that disagrees with them. The plan and its Decision log are the source of truth. Nothing here reopens a decision; where a fact found while writing this bears on a decision, it is marked "Carter to note" and left for Carter.

## Overview and recommended order

1. P4 republishes the cleaned corpus built in P1 to P3 in one apply, through the stage-then-apply writer (2.2w, D2), behind the publish lock (0.4) and the Qdrant alias `chunks_live` (2.2b). There is no release column. The new corpus is built into the `staging` schema and a new Qdrant collection, compared against live in the release report, applied to the live tables in one transaction, and then made visible to vector search by switching `chunks_live`.
2. Passage ids follow D1. They are frozen in the 2.1 registry, so every unit that exists today keeps today's id, even where 2.1 rebuilds its anchor, and a fixed text is updated in place. Only genuinely new units get new ids. Only the few anchors that now name different text get a redirect, and only user rows on those are remapped (4.1a). Removed passages are retired and show a tombstone (D3); user rows that point at them stay where they are.
3. Order for P4:
   - 4.0 storage (the `VACUUM FULL` window and the Pro decision).
   - 4.1a user-data remap for redirects, with a local rehearsal of the whole 2.2w flow on a restored `pg_dump` (D8).
   - 4.1b step 1, staging build and new Qdrant collection.
   - 4.2 on staging.
   - The rest of the 4.1b cutover.
   - 4.2 again on production.
4. 4.2 compares against a baseline that 0.3 judged. 0.3 must therefore run with judging (the plan's P0 row says so; a `--no-judge` baseline cannot be compared), and it must run before any live change (D7).
5. Two storage facts need Carter before P4. A `VACUUM FULL` of `chunks` on today's 401 MB database may briefly peak near 600 MB, above the Free plan's 500 MB read-only trigger. The apply itself, with one staging copy loaded, new units inserted and old versions of updated rows not yet vacuumed, is estimated at 490 to 590 MB at its peak (4.0), so it may cross 500 MB briefly. Both lead to the same choice, run anyway or buy a month of Pro, and the local rehearsal measures the real apply peak first.
6. P5 starts only after the P4 cutover and its rollback window close. Every P5 publish goes through 2.2w, each with its own named apply in a reviewed change to the lock file. No P5 publish uses today's delete-based prune (`writers/reader_writer.py`).
7. 5.2 (rights inventory) can run in parallel from now, and every addition PR waits for its row.
8. Order for P5 code is 5.1a genre and issuer filters, then 5.1c, then the four 5.1b PRs in order (5.1b.1 to 5.1b.4).
9. 5.1b depends on 5.1a because the old key `encyclicals` becomes "papal documents of genre `encyclical`" after the merge.
10. Then 5.3a (Roman Curia, from the parked branch), 5.4, 5.5, 5.6a, 5.3b, 5.6b, and 5.6c one work at a time. 5.6c and the Roman Catechism in 5.5 reuse the OCR tool and gate built in Phase 1 as 1.2f (D9).
11. 5.7 (About page) goes last, once the content it describes exists. The Eastern code stays blocked. Retrieval follow-ups open after the new baseline.
12. Storage is the binding constraint for P5. The planned additions are likely to push the database past 500 MB, so every addition PR carries a storage projection (see 5.2).

Every live-data step below (anything that writes to production Supabase or Qdrant, restarts the API, or deletes anything) needs Carter's explicit approval for that step, given in chat or on the PR, at the time it runs. Approval of a PR is not approval of its live-data step.

## Facts measured for this document (29 Sep 2026, read-only)

Queries were read-only against the production Supabase project (`body-of-christ-dev`, `hvmgffvimqgiejmxwhwq`, which serves production per Carter's memory notes).

| Fact | Value |
|---|---|
| Database size | 401 MB |
| `chunks` total | 380 MB (heap 89 MB, TOAST 203 MB, indexes 88 MB) |
| `chunks` live row bytes (`sum(pg_column_size)`) | 123 MB. The plan rounds this to "about 120 MB"; its older "about 100 MB of live column data" counted only content, search_vector and metadata. The figures in this section and in 4.0 are the ones every other spec cites |
| `chunks` dead tuples | 0 (the free space is inside the files, reusable by new rows) |
| Largest `chunks` indexes | `chunks_document_chapter_pos_idx` 27 MB, `chunks_search_vector_idx` 26 MB, `chunks_document_anchor_uniq` 26 MB |
| Passages / documents | 54,568 / 421 |
| Documents per collection | bible 73, catechism 1, church-fathers 128, councils 36, encyclicals 131, apostolic-exhortations 30, papal-documents 14, canon-law 1, summa 1, medieval 6 |
| User-owned rows | searches 263, retrievals 3,029, bookmarks 25, retrieval_labels 3, guest_trials 18, guest_trial_retrievals 274, reading_progress 25, user_preferences 9, product_feedback rows with a chunk 0 |
| `user_preferences.default_collections` keys | bible 8, catechism 7, summa 7, church-fathers 6, councils 6, encyclicals 6, apostolic-exhortations 3, papal-documents 3, medieval 3, canon-law 2 (9 rows, none at quota 10) |
| `searches.filters->collections` keys | bible 242, catechism 229, church-fathers 205, summa 195, encyclicals 185, councils 161, medieval 131, canon-law 127, papal-documents 109, apostolic-exhortations 107, `saints` 15 (a key retired long ago) |
| `guest_trials.filters->collections` keys | bible, catechism, church-fathers, councils, encyclicals, summa 17 each; papal-documents 1 |
| `searches` rows carrying `collection_outcomes` | 36 |
| Column default of `user_preferences.default_collections` | `{bible,catechism,church-fathers,encyclicals,canon-law,summa}`, set by `supabase/migrations/0010_chunks_metadata.sql:23` |
| `documents` constraints | `documents_collection_check` (the 10 keys), `UNIQUE (collection, title, translation, author)` |
| Title collisions if the three papal collections merge | none |
| Pseudo-Dionysius in the corpus | absent. The two "Dionysius." documents in `church-fathers` are Dionysius of Alexandria. So Pseudo-Dionysius is an addition (5.6a), not a move. Boethius is the only work that moves collection |
| Basil, Cyril of Jerusalem, Gregory Nazianzen, Gregory the Great, Chrysostom, Ambrose, Leo | none present |
| Supabase migration ledger | records only 30 of the repo's migrations (0015, 0016, 0019, 0026, 0031 to 0033 and others were applied outside the ledger). Inspect live schema, not the ledger, before any migration |
| Tracked `docs/eval/` gold data | `eval80-round3-final.jsonl` holds 0 chunk UUIDs (results carry collection and reference only). The 9,492 distinct chunk ids live in untracked local folders such as `docs/eval/eval80-round3-final-artifacts/` |

Supabase documentation (read 29 Sep) says Free plan projects enter read-only mode when database size exceeds 500 MB, and that branching (preview branches) requires the Pro plan and copies schema without production data ([database size](https://supabase.com/docs/guides/platform/database-size), [deployment and branching](https://supabase.com/docs/guides/deployment)). That is why rehearsals run locally (D8).

Qdrant figures come from the plan (28 Sep) and were not re-measured. There is one collection, `chunks`, with 54,568 points at 1,536 dimensions, no quantization and no alias, about 335 MB of raw vectors.

Figures that bear on the storage projection and the remap come from the other specs (29 Sep, estimates where marked):
- Retired rows at P4 are the rule A to G removals (about 2,100 passages) plus the Tanner council units and the 47 On the Incarnation passages that replacement texts supersede. Retired rows already exist in `chunks`, so retiring them adds no space.
- New units are restored verses, recovered prose (Vatican II continuations, Trent, Vatican I, the Summa's Q71 and Q72), split recensions and the replacement council and Incarnation texts. The master build is 54,776 passages against 54,568 live, and 0.6 puts the Vatican II and council repairs at about 0.9 MB of text. The replacement council texts are not yet built, so their size is unmeasured.
- Rows the apply updates in place are those whose text, citation or labels change. That is at least the 2,439 content differences under equal ids measured on 29 Sep, plus the split-piece citation fixes of 1.10c (every Summa passage and about 9,000 others), so roughly 35,000 to 40,000 rows (estimate).

## Prerequisites from earlier phases

P4 and P5 assume these have merged. Each spec below names the ones it needs.

| ID | What P4/P5 relies on |
|---|---|
| 0.1c | Release report produced from staging against live, with the remap outcomes (`same`, `moved`, `split`, `merged`, `renumbered`, `removed`, D5), `remap.jsonl` and `chapter_remap.jsonl`. It fails a build where an unchanged anchor's text similarity falls below its threshold without a redirect (D1) |
| 0.2 | Source hashes, manifests, rights inventory file |
| 0.3 | Baseline eval run with judging, before any live change, and its output format |
| 0.4 | Publish lock (`datapipeline/PUBLISH_LOCK.json`). A datapipeline write to production passes only when a reviewed PR has added an `approved_applies` entry naming the collection, the release and the step (`stage`, `apply`, `rollback` or `repair`), and the CLI passes the same `--collection` and `--release`. Runs whose database and Qdrant are both local are exempt. Hand-run ops steps are outside the lock and approved one by one |
| 0.5 | Qdrant plan memory and disk limits |
| 0.6 | Storage headroom snapshot |
| 1.2f | OCR clean-up tool and quality gate (D9), reused by 5.5 and 5.6c |
| 2.1 | Work registry with frozen document ids and frozen passage ids (each unit that exists today keeps its current id; structural anchors decide which unit is which, not its id), rule A fields and the removal registry (D4). After 2.1, a document's id no longer depends on its collection key (today every adapter passes the collection string into `document_id()`, for example `datapipeline/ingest/encyclicals.py:172`) |
| 2.2a | Additive migration: document facts (genre in the D5 vocabulary, issuer, attribution, notes, source credit), the work model (`chunks.work_key`, `document_works`, D6), the retired flag, `searchable`, tombstones, redirects, and the `staging` schema. No release column |
| 2.2w | The stage-then-apply writer (D2). It builds into `staging` and a new Qdrant collection, produces the release report, applies in one transaction (update changed rows in place by id, insert new ids, retire removed ids, write tombstones and redirects, `refresh_document_outline`), then switches `chunks_live`. It writes `collection`, `genre`, `issuer` and `searchable` to the Qdrant payload, and refuses to retire an id the removal registry does not explain |
| 2.2b | API reads Qdrant through the alias `chunks_live`; boolean `searchable` payload index; filter that excludes only `searchable = false` |
| 2.3 | Document metadata, including genre and issuer for every document, in the registry and staging (applied at the P4 apply, not early, D7) |
| 2.4a, 2.4b | API payloads and web rendering for tombstones and redirects. Both must be live before the P4 apply |
| R1, R6 | Rule A dating and Church-act checks; edition and provenance per planned source |

How D1 and D2 shape P4, stated once here so the items below can rely on it:

- Every unit that exists today keeps today's passage id, frozen in the 2.1 registry, even where 2.1 rebuilds its anchor from the source's structure. Rebuilding anchors does not re-key the corpus. If a unit's text changed (notes stripped, prose restored, label or citation fixed), the apply updates the row in place, so bookmarks and history keep pointing at it and gain the corrected text. No remap is needed.
- Only genuinely new units (restored verses, recovered prose, split recensions, replacement texts) get new ids. Where a fix changes which text an old anchor names (Joel and Malachi renumbering, a council rebuilt by session, a split recension), the old id gets a redirect to the new unit. 4.1a moves user rows along these redirects, which are few.
- A removed passage is retired with a tombstone. User rows keep pointing at it and show the tombstone. No remap.
- `chunks` never holds two copies of the corpus and nothing filters on a release. The only extra copy is `staging`, which exists from the build until it is dropped after the apply.

---

## Phase 4. Republish

### 4.0. Storage: compact `chunks`, project the apply, decide on Pro

- **Type:** ops
- **Depends on:** 0.5 (Qdrant limits), 0.6 (headroom snapshot). Runs before 4.1a's rehearsal measurement is final.
- **Goal:** Get back the space earlier rewrites left inside `chunks`, project the database size through the staging build and the apply, and decide from those numbers and the rehearsal whether Supabase Pro is needed for the republish. Users see nothing, apart from search and the reader pausing during the `VACUUM FULL` lock.
- **Current state:**
  - Database 401 MB, `chunks` 380 MB, of which live row bytes are 123 MB (measured 29 Sep, table above). Dead tuples are 0, so the roughly 166 MB gap between live rows and heap plus TOAST is free space inside the files. Plain `VACUUM` already made it reusable for new inserts; only `VACUUM FULL` returns it to the database size figure.
  - The Decision log row "Storage (4.0)" says to compact `chunks` with `VACUUM FULL` in an approved quiet window, measure, and rehearse locally (D8). Because compaction and the Phase 4 apply may each briefly pass the 500 MB Free-plan limit, Carter chooses between running anyway and a month of Supabase Pro after the rehearsal measures the real peak. If Qdrant memory is tight, the new collection keeps its vectors on disk.
  - **Carter to note (the `VACUUM FULL` peak).** `VACUUM FULL` writes a complete new copy of the table and its indexes before dropping the old one. The new copy is estimated at 123 MB of rows plus 60 to 88 MB of rebuilt indexes, so the database may briefly reach about 590 to 610 MB. Supabase documents that Free projects enter read-only mode above 500 MB. How quickly that is enforced is unverified (the same page says disk metrics update daily). If it triggers, writes fail (searches cannot be saved, bookmarks cannot be added) until usage drops. This is a decision for Carter (step 2).
  - **Carter to note (projection with one staging copy, estimates).** D2 removes the doubled `chunks` table, and frozen passage ids (D1) mean the corpus is not re-keyed. What remains is one staging copy, the new units the apply inserts, and the old versions of rows it updates in place. At about 3.5 KB of database per passage (123 MB of rows plus about 70 MB of indexes over 54,568 passages):
    - After `VACUUM FULL`, about 230 MB (220 to 260 MB).
    - The staging copy needs today's indexes, including the full-text GIN index, because 4.2 searches it. That is about 123 MB of rows plus up to 88 MB of indexes, so about 210 MB. The peak while staged is about 440 MB.
    - The apply runs while staging still exists. Retiring about 2,100 removed passages and the superseded Tanner and Incarnation units adds nothing, since those rows already exist. New units are about 2,000 to 6,000 passages (the repairs' 0.9 MB of text plus the unbuilt replacement council texts), so about 7 to 21 MB.
    - The larger cost is the in-place updates. Postgres writes a new version of each updated row and keeps the old one as dead space until the next vacuum. With roughly 35,000 to 40,000 rows updated, that is about 40 to 130 MB, depending on how much of each row changes (a citation-only change reuses the stored content).
    - The peak during the apply is therefore about 490 to 590 MB, near or above 500 MB, before any P5 addition.
    - Dropping the staging tables after the apply returns their space at once (about 210 MB). During the rollback window the database is then about 280 to 380 MB, and the next vacuum makes the dead space reusable.
    - The local rehearsal (4.1a) measures the real figures.
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
  2. Peak decision (Carter). If `pg_database_size + live rows + index size` exceeds 480 MB, stop. Carter chooses between (a) running anyway and accepting a possible read-only period, or (b) a month of Pro covering both the `VACUUM FULL` and the P4 apply. Do not work around it by dropping indexes, which would break full-text search during the window.
  3. Quiet window (Carter approves the time). In one `psql` session:
     ```sql
     set lock_timeout = '5s';        -- fail fast instead of queueing every search behind the lock
     set statement_timeout = 0;
     \timing on
     vacuum (full, verbose, analyze) chunks;
     ```
     If the lock is not acquired within 5 s, retry once a minute; do not raise `lock_timeout`.
  4. Measure again with the step 1 queries. Record duration, before and after sizes, and WAL size.
  5. Qdrant. Read 0.5's numbers. From 4.1b step 1 until the old collection is deleted after the rollback window, the cluster holds two full collections (today's `chunks` and the new one, each with every passage). If the plan's memory cannot hold both (about 2 x 335 MB raw plus HNSW), note that 4.1b must create the new collection with `on_disk=True` for vectors (and `HnswConfigDiff(on_disk=True)` if 0.5 shows the graph also does not fit).
  6. Pro decision for the apply (Carter). After 4.1a's rehearsal reports the peak database size through staging and apply, compare it with the projection above. If the peak exceeds 500 MB, Carter chooses between a month of Pro and running the apply anyway, accepting a possible brief read-only period. The longer-term Pro decision for P5 is 5.2's 450 MB stop.
- **Acceptance checks:**
  - Ops log (kept in the issue, not in a repo file) has before and after sizes, duration, and WAL size.
  - `pg_database_size` after compaction is recorded; expected 220 to 260 MB (estimate, not measured).
  - The ops log states the projected peaks (staged and at apply) next to the rehearsal's measured peaks.
  - `/health/db` and `/health/search` return 200 after the window; one search per collection returns results.
- **Production safety:** `VACUUM FULL` takes an ACCESS EXCLUSIVE lock, so full-text search and the reader fail while it runs (the plan expects under a minute; GIN rebuild time on this compute is unverified). Vector search still reaches Qdrant but fetches from Postgres fail, so searches error rather than return partial results. `lock_timeout` prevents a stuck lock queue. There is no data change and nothing to roll back; if interrupted, Postgres discards the new copy. The only lasting risk is read-only mode from the peak, handled in step 2.
- **Needs Carter:**
  - Decide step 2 (run `VACUUM FULL` anyway, or a month of Pro) if the peak estimate exceeds 480 MB.
  - Approve the window and the run.
  - Make the step 6 decision for the apply after the rehearsal.
- **Out of scope:** Dropping `content_embedding` or `annotation_embedding` (CLAUDE.md §4: all-NULL, reclaims nothing). Qdrant quantization. Any change to autovacuum settings.

### 4.1a. User-data remap for redirects, rehearsed locally

- **Type:** PR
- **Depends on:** 0.1c, 2.1, 2.2a, 2.2w, 2.4a, P3 (the corpus to publish exists and passes its checks), 4.0 steps 1 to 4.
- **Goal:** When the apply writes a redirect from an old id to a new unit (D1), every user row that pointed at the old id moves to the new one: bookmarks, history results, labels, guest results, reading position and feedback. Where a move collides with a unique constraint, rows are merged by a fixed rule and every merged or dropped row is recorded, never removed silently. A local rehearsal of the whole 2.2w flow proves it on a copy of production. Users keep their bookmarks and history across the republish.
- **Current state:**
  - Tables that reference `chunks(id)` (verified in migrations):
    - `bookmarks` `UNIQUE (user_id, chunk_id)`, `note` up to 3,000 characters, `ON DELETE CASCADE` (`supabase/migrations/0006_v2_bookmarks_feedback_prefs.sql:1-8`, `0016_bookmarks_add_note.sql`).
    - `retrieval_labels` `UNIQUE (user_id, chunk_id, search_id)`, `label` up or down, `rank`, `ON DELETE CASCADE` (`0022_retrieval_labels.sql:8-18`).
    - `guest_trial_retrievals` `UNIQUE (guest_trial_id, chunk_id)`, `rank`, `ON DELETE CASCADE` (`0026_guest_onboarding_continuity.sql:17-25`).
    - `retrievals` has no unique constraint, `ON DELETE CASCADE` (`0005_v2_searches_retrievals.sql:21-29`).
    - `product_feedback.chunk_id` `ON DELETE SET NULL` (`0028_product_feedback.sql:20`); 0 rows with a chunk today.
  - `reading_progress` has primary key `(user_id, document_id)`, references `documents(id)`, and stores text `chapter_key` (NOT NULL) and `anchor` (`0027_reading_progress.sql:2-9`). Document ids are frozen by 2.1, but chapter keys and anchors can change, and if Carter approves 1.8b's split, chapters of the two Augustine volumes move to other documents, so a progress row can change document and collide with the user's existing row there.
  - Under D1 and D2 almost every user row needs nothing. Passage ids are frozen in the 2.1 registry, so every unit that exists today keeps its id even where its anchor is rebuilt, and a passage whose text was fixed keeps its id and row. A removed passage keeps its row, retired, with a tombstone (D3), so user rows stay pointed at it. Only rows on an id with a redirect move.
  - Expected remap volume (estimate). Redirects come only from fixes that change which text an old anchor names: Joel and Malachi renumbering, councils rebuilt by session, split recensions, and Tanner units where a replacement unit is named as successor. That is at most a few hundred to about 2,000 old ids, most in `councils`. The user rows on them are likely in the tens. For comparison, 0.1c's 29 Sep report found 12 live passages with no successor in the master build, carrying 19 `retrievals` and 2 `guest_trial_retrievals` rows, and the plan counted 50 retrievals and 0 bookmarks on passages the rules remove. The release report's user-impact section gives the exact count before the apply.
  - Every chunk foreign key cascades on delete, which is why 2.2w retires instead of deleting and why this tool never deletes a `chunks` row.
  - Supabase branching needs Pro and copies schema only (docs, 29 Sep), so the rehearsal runs on a local Postgres restored from a `pg_dump` of production (D8).
  - Rows at risk are few (25 bookmarks, 3,029 retrievals, 274 guest results, 3 labels, 25 reading positions), so the rules must be exact rather than fast.
- **Changes:**
  1. New module `datapipeline/remap_user_data.py`.
     - A class `UserDataRemapImpl` implementing 2.2w's `UserDataRemap` interface (D11). 2.2w defines the interface and calls it inside its apply transaction (`forward`) and its rollback transaction (`reverse`); this PR supplies the implementation and registers it with 2.2w. It adds no call site of its own and contains none of 2.2w's apply code.
     - A CLI `python3 -m remap_user_data --dry-run` that prints what `forward` would do for a set of redirects against a database, for review and for the rehearsal. It never writes. The only paths that write user rows are 2.2w's `apply` and `rollback`, under their lock gates (0.4).
     - Input is the passage and anchor redirects the apply writes (old id to new id, kind in the D5 words `moved`, `split`, `merged`, `renumbered`), plus 0.1c's `chapter_remap.jsonl`. For a split, the redirect already points at the first new piece (2.2a), so this tool follows it and makes no choice of its own.
  2. One pass per table, in this order, each ending with an assertion that no user row still points at an id that has a redirect:
     - `bookmarks`. Repoint. When two rows for one user land on the same new id, keep the row with the earliest `created_at`. If both notes are non-empty and differ, join them with a blank line when the result fits 3,000 characters. Otherwise keep the earlier note and record the other in the ledger.
     - `retrieval_labels`. Repoint. On a `(user_id, chunk_id, search_id)` collision keep the row with the latest `created_at`, since a later label is the user's current judgement; record the other.
     - `guest_trial_retrievals`. Repoint. On a `(guest_trial_id, chunk_id)` collision keep the lowest `rank` with its `explanation` and `reranker_score`; record the other.
     - `retrievals`. Repoint. There is no unique constraint, but a search that now holds the same passage twice would show it twice on restore. Keep the lowest `rank`, record the other, and leave the remaining ranks as they are (restore sorts by rank; gaps are harmless).
     - `product_feedback`. Repoint where a redirect exists. No unique constraint, so nothing merges.
     - `reading_progress`. Rewrite `document_id` and `chapter_key` through `chapter_remap.jsonl` (which carries the new document ID) and `anchor` through the anchor redirects. When the new `(user_id, document_id)` already has a row, keep the row with the later `updated_at` and record the other. If the chapter is retired, keep the row, point it at the document's first live chapter with `anchor = NULL`, and record the change.
  3. The ledger. Every merged, dropped or rewritten row is written with its table, primary key, prior values and the rule applied.
     - The private form is a local file on Carter's Mac, next to the 4.1b step 4 backup, and it is what `reverse` reads. It holds note text and user ids, so it is never committed and is deleted when the rollback window closes.
     - The public form is counts only, per table and per rule (repointed, merged, dropped, notes joined, notes kept apart, reading positions moved to a first chapter). It goes into the release report and the PR. It carries no ids, queries or note text, since the repo is public.
  4. `reverse`, which 2.2w's `rollback` calls inside its transaction (4.1b step 12 runs only that command). It maps new ids back to old ones through the same redirects and re-inserts every dropped row from the ledger with its prior values. Rows created after the apply on ids that exist only in the new corpus are left alone and counted.
  5. Tests in `datapipeline/tests/test_remap_user_data.py` using an in-memory fake store:
     - One test per collision rule above.
     - Every merged or dropped row appears in the ledger, and `reverse` restores the exact prior rows.
     - `test_impl_satisfies_2_2w_protocol`: `UserDataRemapImpl` type-checks against 2.2w's `UserDataRemap`.
     - Rows on retired passages without a redirect are untouched.
     - Rows on an id whose text changed but whose anchor did not are untouched.
     - The tool refuses to run if a redirect's target id is missing from `chunks`.
  6. Rehearsal (D8), local only.
     - Carter approves taking a `pg_dump` of production's `public` schema, schema and data (auth users only as ids, enough for the foreign keys).
     - Restore it into a local Postgres (`supabase start`, with the committed migrations and 2.2a applied), and run a local Qdrant (`docker run qdrant/qdrant` at the production server version) holding a copy of `chunks` with the alias `chunks_live`.
     - Run the full 2.2w flow against it exactly as 4.1b will: stage, release report, apply with this remap inside the transaction, outline refresh, alias switch. Then run 2.2w's `rollback`, which calls `reverse` in the same transaction, and check that the user tables match the dump. If 2.2w's own rehearsal already filled the embedding cache on this Mac, this stage pays only for inputs changed since; otherwise it is the first full stage and fills it. Record its token count either way (2.2w stage step 6).
     - Measure `pg_database_size` after the staging build, at the peak of the apply, and after staging is dropped. These are the numbers 4.0 step 6 uses. Also time the apply transaction.
     - The dump contains user data. It stays on Carter's Mac, is never committed, and is deleted after the rehearsal along with the local database.
- **Acceptance checks:**
  - `python3 -m pytest tests/test_remap_user_data.py -q` passes in GitHub Actions (no sources needed).
  - The rehearsal report in the PR (counts only) shows zero user rows pointing at an id that has a redirect. Bookmark count before equals count after plus merged rows, and every merged or dropped row is in the ledger.
  - After 2.2w's `rollback`, the rehearsal's user tables match the dump row for row (checksums per table).
  - The PR description states the three measured database sizes, whether the apply peak is above 500 MB, and the apply's duration.
  - The PR description confirms the dump and the local database were deleted.
- **Production safety:** The PR adds the implementation 2.2w calls, a read-only CLI and tests; nothing runs against production on merge, and the lock still refuses every live apply. The tool never deletes a `chunks` row. Rollback of the merge is a revert.
- **Needs Carter:** Approve taking the production `pg_dump` for the local rehearsal (it holds user data; it stays on his Mac and is deleted afterwards). Approve the collision rules above.
- **Out of scope:** Deleting retired rows (4.1b, after the rollback window). Rows on removed passages (they keep their row and show the tombstone). Any change to how saved searches render.

### 4.1b. Production cutover runbook

- **Type:** ops, with one small PR (the lock-file change)
- **Depends on:** 4.0, 4.1a (rehearsal passed), 4.2 pre-cutover run passed, 2.2w, 2.2b (API reads `chunks_live`), 2.4a and 2.4b live, P1 to P3 merged.
- **Goal:** Switch production from the old corpus to the cleaned one in minutes, with a tested rollback. Users see the corrected corpus (Vatican II and Trent recovered, removals shown as tombstones, correct labels); bookmarks and history keep working.
- **Current state:**
  - After 2.2b the API reads Qdrant through the alias `chunks_live`, which points at `chunks` (2.2b ops steps). The datapipeline writer takes a target collection name from 2.2w.
  - `/sources` is cached in memory for one hour (`services/api/app/routes/sources.py:18`, `_SOURCES_TTL = 3600.0`).
  - Tracked `docs/eval/` holds no chunk ids (verified); ids live in untracked local artifacts and in 0.3's output.
  - The apply is 2.2w's single transaction. It updates changed rows in place by id, inserts new ids, retires removed ids, writes tombstones and redirects, runs 4.1a's remap, and refreshes reader outlines.
- **Changes:** Runbook. Every numbered step that writes to production is a separate Carter approval.
  1. **Staging build, T minus 2 days (no user impact).**
     - Freeze the build. A reviewed PR names the commit the P4 build is made from. It also applies the 1.2e fallback (D9, D11; this step owns it): for any council that has not passed 1.2f's gate by then, the adapter emits nothing for it, and the PR adds removal-registry entries with reason `translation-in-preparation` for all of that council's Tanner passages, with 1.2e's tombstone. No adapter change merges after this PR until the cutover is done or abandoned.
     - Lock-file change. A reviewed PR (it may be the same one) adds to `datapipeline/PUBLISH_LOCK.json` the entry `{"collection": "all", "release": "republish-2026-10", "steps": ["stage", "apply", "rollback"], ...}` in 0.4's format. It stays until the rollback window closes (step 13), and no other entry is added in between, so no other publish can run.
     - Run `publish.py stage --collection all --release republish-2026-10`. It writes every collection into the `staging` schema and into the new Qdrant collection `chunks-republish-2026-10` (D11).
     - The new collection uses `VectorParams(size=1536, distance=COSINE, on_disk=<per 4.0 step 5>)` and `HnswConfigDiff(m=16, ef_construct=64)` (as today, `qdrant_schema.py:25`). Payload indexes are keyword on `collection`, `document_id`, `genre` and `issuer`, and boolean on `searchable`. 2.2w writes `collection`, `genre`, `issuer` and `searchable` into every point's payload.
     - Every staged passage is a point, searchable or not; non-searchable ones carry `searchable = false`. The point count equals the staged passage count. Retired passages have no point.
     - Record the embedding cost. 2.2w looks each vector up in the datapipeline's content-addressed cache first and sends only misses to OpenAI (D11). The cache was empty on 29 Sep, and the first full rehearsal stage on Carter's Mac fills it (about 11 million tokens, about $1.40 at $0.13 per million; check the current price). So this stage embeds only passages whose embedding input changed after the last rehearsal build: 0 tokens if the frozen build equals the rehearsed one, and at most the same 11 million if everything changed. The count is known before any call, from the cache misses, and is recorded.
     - The release report (0.1c, produced by 2.2w from staging against live) is attached to the tracking issue. It must pass D1's similarity check and D4's removal-registry check.
  2. **T minus 1 day.** 4.2 pre-cutover run against staging. Carter gives go or no-go.
  3. **Window start (quiet hour Carter chooses).** Freeze merges to `master` that touch `services/api`, `apps/web` or `supabase/migrations`.
  4. **Backups.**
     - `pg_dump` of the user-owned tables (`bookmarks`, `retrievals`, `retrieval_labels`, `searches`, `guest_trials`, `guest_trial_retrievals`, `reading_progress`, `product_feedback`, `user_preferences`) to Carter's Mac, kept private.
     - `pg_dump` of the corpus tables (`documents`, `chunks`, `document_chapters`, `document_works`, the tombstone and redirect tables) as they stand before the apply. This is a last-resort backup only, not a rollback path (D11). Step 12's rollback uses the before-snapshot that 2.2w's `apply` exports itself.
     - A Qdrant snapshot of `chunks` if 0.5 shows the plan allows it (the old collection is not modified anyway).
  5. **Counts.** Read and record counts of each user table above (the plan requires counts at cutover, not the 28 Sep ones).
  6. **Apply.** Run `publish.py apply --collection all --release republish-2026-10 --no-switch` under the lock entry. One transaction does the in-place updates, inserts, retirements, tombstones, redirects, 4.1a's remap and the outline refresh. Record the public ledger counts.
  7. **Reader outline check.** Confirm `refresh_document_outline` ran for every document the apply touched. Zero documents have `chunk_count IS NULL`, and `/v1/documents/{id}/toc` for one document per collection returns the new chapter list. If any document is NULL, run the refresh for it (the reader falls back to the slower derivation until then, so this is not urgent).
  8. **Switch Qdrant.** `publish.py switch --release republish-2026-10`: one `update_collection_aliases` call that deletes `chunks_live` on `chunks` and creates it on `chunks-republish-2026-10`. Qdrant applies the listed alias actions atomically. Between steps 6 and 8 (seconds to a minute) vector search still reads the old collection. It can return an id the apply has just retired, which the API shows as a tombstone or follows through its redirect. Full-text search already reads the new rows. Keep the gap under one minute.
  9. **Restart the API** on Railway to clear the `/sources` cache.
  10. **Smoke checks and cleanup of staging.**
      - `/health/db` and `/health/search` return 200.
      - One authenticated and one guest search per collection return results.
      - Nostra Aetate 4 and Gaudium et Spes open in full in the reader.
      - Restore a pre-cutover saved search from history.
      - A test account's bookmarks page loads, and a bookmark on a removed passage shows the tombstone.
      - Then drop the `staging` tables (`publish.py cleanup --release republish-2026-10`) and record `pg_database_size`.
  11. **Eval ids and 4.2 post-cutover run.** Remap 0.3's output with the redirects and commit the result (ids only, no user data). Remap local untracked artifacts only if they will be reused. Then run 4.2 on production.
  12. **Rollback, available until the window closes (recommended 14 days).**
      - Run `publish.py rollback --release republish-2026-10` under the same lock entry (step `rollback`). This one command is the whole rollback (D11). In one transaction it restores the previous text and facts in place from 2.2w's before-snapshot, un-retires what the apply retired, retires what the apply inserted, and calls 4.1a's `reverse` to move user rows back and re-insert merged rows from the ledger. After commit it points `chunks_live` back at `chunks`.
      - Restart the API.
      Bookmarks made after cutover on passages that exist only in the new corpus stay attached to rows that are now retired and show as unavailable; the reverse report counts them.
  13. **After the window closes (separate approvals).**
      - Delete retired rows with no user references (D3) in batches of 1,000, after asserting zero references from every table in 4.1a. Retired rows that users still point at stay, with their tombstones.
      - Plain `VACUUM (analyze) chunks`. The freed space is reused by later inserts; the database size figure only falls after another `VACUUM FULL`, which is a separate 4.0-style decision.
      - Delete the Qdrant collection `chunks`. Irreversible; Carter approves it separately.
      - Delete the private ledger and the step 4 dumps from Carter's Mac.
      - A reviewed lock-file change removes the `republish-2026-10` entry, leaving `approved_applies` empty.
      - Measure the database size again.
- **Acceptance checks:**
  - Cutover log in the tracking issue records every step's time, counts before and after, the public ledger counts, smoke results and the 4.2 result.
  - Retrieval, bookmark, label and guest-result counts after equal counts before, minus merged rows in the ledger.
  - Point count in `chunks-republish-2026-10` equals the staged passage count (all passages, searchable or not), and the count with `searchable = false` equals the staged non-searchable count.
  - Zero documents with `chunk_count IS NULL` after step 7.
  - No error-level API log lines about missing chunks in the hour after cutover (filter `@logger:app.rag` in Railway).
- **Production safety:** Everything before step 6 is invisible to users (the `staging` schema, and a Qdrant collection not behind the alias). There is no release column and no second copy in `chunks`. Step 6 is one transaction, so users see the old corpus or the new one, never a mix. Step 8 is one alias switch with an inverse. The old Qdrant collection and every retired row stay until step 13, so rollback is always possible inside the window. Deletions happen only after an assertion of zero references, because every chunk foreign key cascades.
- **Needs Carter:**
  - Approve the build-freeze PR (step 1), including any council that falls back to a "translation in preparation" tombstone.
  - Approve the lock-file PR (step 1) and the one that removes the entry (step 13).
  - Approve steps 1 (staging build and embedding spend), 4, 6, 7 (only if an outline refresh has to be run by hand), 8, 9, 10 (the smoke checks and the `cleanup` that drops the staging tables in production), 12 (if used) and each part of 13.
  - Set the rollback window (14 days recommended).
  - Choose the window. Give go or no-go at step 2.
- **Out of scope:** Collection renames (5.1b). Any new source. Any retrieval tuning (Retrieval follow-ups).

### 4.2. Comparison against the baseline

- **Type:** ops
- **Depends on:** 0.3, run with judging before any live change (this item compares judge scores, so a baseline run with `--no-judge` cannot serve), 4.1a, and the staging build from 4.1b step 1.
- **Goal:** Show, before and after cutover, that the cleaned corpus answers the baseline questions at least as well, that removed texts no longer appear, and that recovered texts now do. This is what Carter's go or no-go rests on.
- **Current state:** 0.3 defines the harness and question sets (the 80-question set plus about 30 targeted questions, no stored user queries). Production pipeline is `hyde_cohere_luna` (CLAUDE.md §5). The noise floor for any retrieval change is the `hyde_cohere_luna_hydesample` arm (CLAUDE.md §5). The eval judge is `claude-opus-5-5`.
- **Changes:** Runbook plus a report file.
  1. **Pre-cutover run, on staging.** Run the 0.3 harness, the in-process `services/api/scripts/run_eval_suite.py`, with `CORPUS_READ_SCHEMA=staging` and `QDRANT_READ_COLLECTION` set (2.2w). It runs the pipeline in process, not through an API server, which is why 2.2w lets it use the override while the deployed API refuses to start with it. Its corpus reads go to the `staging` schema and its vector reads go to the new Qdrant collection (`QDRANT_READ_COLLECTION=chunks-<release>`, from 2.2b). It reads production data and writes nothing. Run the same questions with the noise-floor arm, and judge both.
  2. **Targeted checks,** scripted as assertions over the returned passages:
     - Zero passages from Origen, Novatian, Tatian, Arnobius, Alexander of Lycopolis, the Apostolic Constitutions outside Book VIII's 85 canons, the six forged Ignatius letters, or Tertullian's excluded works.
     - Nostra Aetate 4, a Trent decree and the Vatican I constitutions retrievable by a direct question.
     - CCC 2267 returns the 2018 text.
     - "Canon 112" returns canon 112 alone.
     - Susanna (Daniel 13) and Bel and the Dragon (Daniel 14) findable.
     - No result shorter than 20 characters.
     - No Vatican II result starting with "Cf." or "See".
     - No result with `searchable = false`.
  3. **Post-cutover run.** The same harness against production, after 4.1b step 10.
  4. **Report.** Add `docs/eval/2026-MM-DD-republish-comparison.md`. It gives judge scores per dimension against the judged baseline with the noise floor, the targeted checks, the cost of the run, and the reason for each regression larger than the noise floor (an intended removal explains a lost baseline passage; nothing else does).
- **Acceptance checks:**
  - All targeted assertions pass.
  - Mean judge score within the noise floor of the judged baseline or better.
  - Every regression larger than the noise floor is explained in the report.
  - The report contains no user data.
- **Production safety:** The pre-cutover run reads the `staging` schema and a Qdrant collection no user reads, and writes nothing. The post-cutover run makes ordinary searches through the product path with an operator account and is rate limited like any user. It does not persist to other users' history.
- **Needs Carter:** Go or no-go after the pre-cutover run. Approve the eval spend (judge and pipeline calls; the report states the amount). Confirm 0.3 was run with judging.
- **Out of scope:** Tuning anything to improve scores. That belongs in Retrieval follow-ups.

---

## Phase 5. Reorganize and expand

### 5.1a. Genre and issuer filters

- **Type:** PR (one API PR, one web PR; both deploy safely alone)
- **Depends on:** 2.2a, 2.3 (every document has `genre` and, where relevant, `issuer`), 2.2w, 2.2b, P4 complete.
- **Goal:** Inside a collection, a user can search one genre, several, or all (for example only encyclicals, or encyclicals and apostolic letters), and filter Roman Curia and papal documents by issuer. Nothing changes for a user who leaves the filters alone.
- **Current state:**
  - The search request carries `filters: {collections, translation}` and `quota` (`apps/web/src/lib/api.ts:286-299`); the plan resolves collections only (`services/api/app/rag/search_plan.py:76-96`).
  - Vector search filters Qdrant on `collection` alone (`services/api/app/rag/steps/retrieve_vector.py:31-35`); full-text search filters on `d.collection = $1` (`services/api/app/rag/steps/retrieve_fts.py:16-26`).
  - Today's Qdrant collection has a keyword index on `collection` only (`datapipeline/qdrant_schema.py:28-29`). After P4, the collection behind `chunks_live` carries `genre` and `issuer` in every point's payload, written by 2.2w (D5), with keyword indexes created at 4.1b step 1. This item needs no payload writer of its own.
  - Genre is currently in `documents.metadata` for 16 documents only (plan, "Corrections"). 2.3 puts real values in the registry and the P4 apply writes them to `documents.genre` and `documents.issuer`.
  - The genre vocabulary is defined once, in 2.1's Python genre module `datapipeline/registry/genres.py` (D5, D11), lowercase and hyphenated everywhere, with `other` for anything unlisted. 2.2a's `corpus_genres` table is seeded from it. Adding a value is a normal PR that changes the module and adds the row by migration.
    - Papal: `encyclical`, `apostolic-exhortation`, `apostolic-letter`, `apostolic-constitution`, `motu-proprio`, `bull`, `letter`.
    - Roman Curia: `declaration`, `instruction`, `doctrinal-note`, `note`, `response`, `norms`, `considerations`, `commentary`.
    - Catechisms and law: `catechism`, `compendium`, `code`, `law`.
    - Writers: `treatise`, `manual`, `sermon`, `commentary`, `poem`, `rule`.
- **Changes:**
  1. `services/api/app/rag/constants.py`. Add `GENRES_BY_COLLECTION: dict[str, frozenset[str]]` and `ISSUERS_BY_COLLECTION`. The API cannot import the datapipeline, so the genre values are a copy of 2.1's module with a CI test (`test_api_genres_match_registry_module`) that reads both files and fails on any difference.
     - The papal collections use the papal values plus `other`.
     - Roman Curia uses the Roman Curia values plus `compendium` (the social doctrine Compendium, 5.3b), `letter` and `other`.
     - Issuers are slugs in `documents.issuer`, and filters use only the slug; `issuer_label` is what users see (D11). Roman Curia issuers are the institution: `ddf` for both CDF and DDF (per the source memo; the name printed at publication goes in `issuer_label`), `pbc`, `pcjp`. Papal issuers are the pope, such as `pope-leo-xiii` with label "Pope Leo XIII". The filter chips show `issuer_label`.
  2. New module `services/api/app/rag/collection_scope.py` with a frozen `CollectionScope(collection, genres, issuers)`. It has `to_qdrant_filter()` and `to_sql()` so retrieval does not hand-build filters. Semantics, per the plan's rule "filters exclude only explicit values":
     - A selection is stored as the set of values the user turned off.
     - Qdrant gets `must_not` on `genre` in the excluded set.
     - SQL gets `(d.genre IS NULL OR d.genre <> ALL($excluded))`. The explicit NULL branch is required, because `NOT (NULL = ANY(...))` is NULL and would silently drop documents without a genre.
     - "All" means no clause.
  3. `search_plan.py`. `SearchPlan` gains `scopes: tuple[CollectionScope, ...]`. `resolve_search_plan(collections, quota, scope_filters=None)` validates genres and issuers against the constants and raises `SearchPlanError("invalid_genre" | "invalid_issuer")`, which routes translate to 422 like the other codes (CLAUDE.md §18). Focused search still requires exactly one collection; a genre subset does not count as a collection.
  4. Request models in `routes/search.py` and `routes/guest_search.py`. Add optional `filters.scopes: {[collection]: {genres?: string[], issuers?: string[]}}`; absent means all. Additive to `/v1/search` and `/v1/search/guest`; the `/v1/chat` contract (CLAUDE.md §3) is untouched.
  5. `retrieve_vector.py` and `retrieve_fts.py`. Take a `CollectionScope` instead of a bare collection string and use its filters.
  6. `pipeline.py`. Persist the scope selection into `searches.filters` next to `collections` (`_saved_search_filters`, `services/api/app/rag/pipeline.py:161-178`), and into `guest_trials.filters`. Remember CLAUDE.md §4 (no `json.dumps` on jsonb from the API). `routes/search.py` returns it on restore.
  7. Qdrant check (read-only). Confirm that the collection behind `chunks_live` has keyword indexes on `genre` and `issuer` (created at 4.1b step 1) and that every papal point carries `genre`. If an index is missing, creating it is a live step for Carter to approve; it does not change points.
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
  - A read-only query after the P4 apply shows zero NULL genres in the papal collections, recorded in the PR.
  - PR includes screenshots of the chips in both themes.
- **Production safety:** The API change is additive and optional. Old web clients send no `scopes` and get today's behavior. The web PR deploys after the API PR, so it never sends a field the API rejects. The Qdrant indexes already exist from P4. Rollback is a revert of either PR.
- **Needs Carter:** Confirm the display labels for the D5 genre values. Approve a Qdrant index creation only if step 7 finds one missing.
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
3. 5.1b.3 Data rewrite. Migration, datapipeline keys, a 2.2w publish that writes the new keys to `documents` and the Qdrant payload, and a script for the keys stored in user rows, run as one approved ops step.
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
| `user_preferences.default_collections` rows and column default (live default verified above; set by `supabase/migrations/0010_chunks_metadata.sql:23`) | stored keys | .3 |
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
  - Document ids are frozen by the registry (2.1) and passage ids depend only on document id and anchor (D1), so a key change keeps every id. The 2.2w apply therefore updates `documents.collection` in place.
  - D5 makes 2.2w the writer of the Qdrant `collection` payload, so the payload changes through a 2.2w publish (new collection, alias switch), not through `set_payload` on the live collection.
  - Embedding inputs contain author and title, not the collection key (`datapipeline/writers/search_writer.py:82-93`), so a key change needs no re-embed. 2.2w takes each vector from the embedding cache or copies it from the alias target when the embedding input is unchanged (2.2w stage step 6), so no embedding call is made for these. The overlap change in step 2 may still re-embed the 44 former exhortation and papal-document documents, which costs cents.
- **Changes:**
  1. Migration `supabase/migrations/00NN_collection_keys.sql` (next free number at merge time; 0039 is taken by 2.2a). One transaction:
     - Widen `documents_collection_check` to old plus new keys.
     - Change the `user_preferences.default_collections` column default to `{bible,catechism,church-fathers,papal,church-law,summa}`.
     - Nothing else. Data rewrites are not in the migration, so applying it is safe at any time.
  2. Datapipeline, same PR. So that the next publication writes new keys and cannot write old ones back:
     - Adapters emit the new collection.
     - `SOURCE_ADAPTERS` gets a composite `papal` adapter that builds encyclicals, apostolic exhortations and papal documents together, and removes the three old entries. Publishing only one of them under `papal` would make 2.2w try to retire the other two, which the removal registry (D4) refuses because nothing explains those removals.
     - `SOURCE_ADAPTERS` renames `canon-law` to `church-law` and `medieval` to `theologians`.
     - Boethius moves into the Fathers build.
     - `PER_COLLECTION_OVERLAP` gets `papal` 250, `church-law` 300, `theologians` 200. Carter to note that the 44 former exhortation and papal-document documents were embedded with 200-character overlap. `reembed_drifted_vectors.py` may flag them as drifted on a later run. That is harmless (a re-embed costs cents) but should not be mistaken for a defect.
     - Update `stages/parse.py`, the enrichment prompt maps, README and SOURCES.
     - `vendor_sources.py` keeps its source-directory names.
  3. Corpus publish through 2.2w (live step), under a named apply set in a reviewed lock-file change.
     - Build every affected collection (`papal`, `church-law`, `theologians`, and `church-fathers` for Boethius) into `staging` and a new Qdrant collection `chunks-<release>` whose payload carries the new `collection` values.
     - The stage takes a rename map, `{encyclicals, apostolic-exhortations, papal-documents: papal; canon-law: church-law; medieval: theologians}`, so the live rows under an old key count as part of the staged collection. They are compared with the build by ID, not treated as retirements.
     - Copying excludes collections being renamed. 2.2w copies the points of collections that are not staged from the alias target; the three old papal keys, `canon-law` and `medieval` count as staged, so none of their old points is copied into the new collection. Without this, staging `papal` would carry every papal passage twice, once under the new key and once under the old.
     - The release report must show every passage as `same` (same id, same text) with only the collection changed, and zero retirements.
     - Apply: `documents.collection` changes in place by id, including Boethius (`church-fathers`, by his registry id). Outlines are refreshed. Then switch `chunks_live` to the new collection.
  4. Script `datapipeline/scripts/rewrite_collection_keys.py` for the keys stored in user rows, dry run by default, `--apply` to write, refusing production unless the lock entry for the same release lists the step `repair` (0.4). One transaction:
     - `user_preferences.default_collections`. Map each element, then de-duplicate keeping first occurrence. Cardinality can only fall, so the focused-quota constraint (`0034_focused_quota_preferences.sql`) still holds.
     - `searches.filters` and `guest_trials.filters`. Rebuild `collections` as the mapped, de-duplicated array. Rename `collection_outcomes` keys; when two old keys merge, keep the worse outcome. Add a `scopes` genre selection equal to the legacy subset, so a restore reproduces the old search. Only rows where `jsonb_typeof(filters) = 'object'` are touched, and the 0033 repair is re-checked first.
     - Leave the 15 `saints` rows alone; restore already ignores them.
  5. Restart the API afterwards to clear the `/sources` cache.
- **Acceptance checks:**
  - Dry-run output of the script (counts per table and per key, no user content) and the release report of the 2.2w build in the PR.
  - After apply, read-only checks:
    - Zero `documents` rows with old keys.
    - Zero old keys in `user_preferences`, `searches.filters->collections` (except `saints`) and `guest_trials.filters`.
    - Qdrant count by `collection` equals the Postgres count of non-retired passages per collection, searchable or not. Retired passages have no point in the new collection, so they are left out of both sides.
    - Zero points in the new collection carry an old collection key.
    - Boethius's passages carry `church-fathers` in both stores.
  - Datapipeline tests. The composite adapter emits 175 documents (131, 30 and 14 today, plus any added by then). A 2.2w build of `papal` into a local database's `staging` schema writes `papal`, and its new Qdrant collection has exactly one point per non-retired papal passage (no copied old-key points).
  - Smoke search per collection with old and new keys.
- **Production safety:** 5.1b.1 made both old and new stored values readable under both key vocabularies, so the database apply, the alias switch and the user-row script can land seconds or hours apart without breaking search. The corpus side rolls back with 2.2w's `rollback` command, which also points `chunks_live` at the previous collection. The user-row script has no reverse and needs none, so there is no second rollback path (D11): after 5.1b.1 the API reads both key vocabularies, so rows carrying new keys keep working whether or not the corpus publish is rolled back. Preference and filter de-duplication loses only duplicate keys, which changes nothing. The publish lock stops any other publication between the merge and the ops step.
- **Needs Carter:** Approve applying the migration. Approve the lock-file PR naming the apply, the 2.2w apply and alias switch, the script's `--apply`, and the API restart.
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
  - Every P5 publish goes through 2.2w (D2). Each one briefly holds a staging copy of the collections it publishes and a new Qdrant collection beside the one behind `chunks_live`, so its projection includes that transient peak, not only the lasting growth.
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
- **Depends on:** P4, 2.2w, 5.1a (genre and issuer), 5.1b.4 (so the collection list changes once more, not interleaved), 5.2 rows for the 60 documents.
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
     - `genre` from the page, in D5's Roman Curia values (`declaration`, `instruction`, `doctrinal-note`, `note`, `response` for a responsum, `norms`, `considerations`, `commentary`), `letter` for letters, and `other` for anything else.
     - `issuer = ddf` for filters, and `issuer_label` set to the name printed at publication, "Congregation for the Doctrine of the Faith" before 5 June 2022 and "Dicastery for the Doctrine of the Faith" after (source memo; D11).
     - Date, and papal approval wording where the text has it.
     - AAS citation where the index gives one.
     - Credit line "Text: Libreria Editrice Vaticana".
  4. Register the 60 documents in the 2.1 registry with frozen ids.
  5. Drop the branch's Cohere concurrency change if the scope count still fits 10 (nine canonical keys plus `roman-curia` makes 10). Keep the test from 5.1b.1.
  6. Release switch in the same PR, dormant until data exists: keep `roman-curia` in `UNRELEASED_COLLECTIONS`. A second tiny PR moves it into `COLLECTIONS` and adds it to the `/evaluate` prompt after the ops publish (branch's CLAUDE.md §15 note).
  7. Ops publish (live step) through 2.2w, never the delete-based prune. A reviewed lock-file change names the apply. 2.2w builds `roman-curia` into `staging` and a new Qdrant collection (with `collection`, `genre`, `issuer` and `searchable` in the payload), produces the release report, applies in one transaction with the outline refresh, then switches `chunks_live`. Attach the release report.
- **Acceptance checks:**
  - `datapipeline` tests including `test_roman_curia.py` pass locally (sources needed; the report goes in the PR template section).
  - Release report shows 60 documents, no passage under 20 characters, no endnote cards, and genre set on every document.
  - After publish, targeted questions are answered from the collection (Dignitas Personae on embryo adoption, Dignitas Infinita on human dignity, Iura et Bona on end-of-life care, Dominus Iesus on salvation outside the Church).
  - Storage total in 5.2 updated.
- **Production safety:** The collection is accepted but not offered until the release PR. The migration is additive. The apply adds only `roman-curia` rows. Rollback within the window is 2.2w's `rollback` command, which also points `chunks_live` back. Later, a 2.2w apply retires the documents with a reason in the removal registry (D4). The reader wipe and `--reset-search-index` are not used.
- **Needs Carter:** Approve the migration, the lock-file PR naming the apply, the 2.2w apply and alias switch, and the release PR.
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
  2. Reuse `ingest/roman_curia.py`'s parser. Add issuer slugs `pbc`, `pcjp` or the worship dicastery's slug per document, each with its `issuer_label` ("Pontifical Biblical Commission", "Pontifical Council for Justice and Peace"; D11), and genre `compendium` for the social doctrine Compendium (D5). Its numbered paragraphs become anchors.
  3. Each liturgical document gets a translation check recorded in 5.2 (Vatican English, or ICEL and therefore dropped).
  4. Each family publishes through 2.2w (stage, release report, one-transaction apply with the outline refresh, `chunks_live` switch) under a named apply in the lock file, never the delete-based prune.
- **Acceptance checks:** Same as 5.3a, per family. Issuer filter isolates Biblical Commission documents.
- **Production safety:** As 5.3a. Each family's documents become visible together, in one apply. Rollback is 2.2w's `rollback` command, which also points `chunks_live` back, or later a 2.2w apply that retires the documents.
- **Needs Carter:** Approve each lock-file PR and each 2.2w apply. Decide on the International Theological Commission.
- **Out of scope:** Missal, Lectionary or Liturgy of the Hours texts.

### 5.4. Papal and universal law

- **Type:** PR, then ops publish
- **Depends on:** 5.1b.4 (keys `papal`, `church-law`), 2.2a (`searchable`, notes, `documents.superseded_by`), 2.2w, 5.2 rows.
- **Goal:** Questions about how a pope is elected or what happens during a vacancy are answered from *Universi Dominici Gregis* as currently in force, with its earlier wording available as labeled history. Two vendored papal documents that never reached the corpus become searchable.
- **Current state:**
  - `datapipeline/sources/apostolic-exhortations/a-new-hope-for-lebanon.html` and `datapipeline/sources/papal-documents/ubicumque-et-semper.html` are vendored but in neither manifest nor the database (verified locally; plan Decision log).
  - Manifest lists live in `scripts/vendor_sources.py:382` (`APOSTOLIC_EXHORTATIONS`) and `:447` (`PAPAL_DOCUMENTS`).
  - UDG is not vendored. Per the source memo, vatican.va's English page is the consolidated text current from 22 February 2013 and links the 1996 original, *De aliquibus mutationibus* (2007, Latin; replaced number 75) and *Normas nonnullas* (2013; modified numbers 35, 37, 43, 46 §1, 47 to 51 §2, 55 §3, 62, 64, 70 §2, 75, 87). The 30 April 2025 declaration on number 33 is a dispensation, not an amendment.
  - Rule F is current text only in search, superseded versions as labeled linked history.
  - The supersession link is `documents.superseded_by` (2.2a, D5): each older text points to the current text that replaces it.
- **Changes:**
  1. `vendor_sources.py`. Add A New Hope for Lebanon (1997, post-synodal apostolic exhortation) to `APOSTOLIC_EXHORTATIONS` and Ubicumque et Semper (2010, motu proprio) to `PAPAL_DOCUMENTS`. Regenerate manifests. Both publish into `papal` with genres `apostolic-exhortation` and `motu-proprio`.
  2. UDG.
     - New adapter `datapipeline/ingest/universal_law.py` emitting collection `church-law`.
     - Document "Universi Dominici Gregis (as amended 2013)" is searchable, with anchors by number and section and author "Pope John Paul II" with the amendment note.
     - Three history documents (1996 original, 2007 motu proprio, 2013 motu proprio) are stored with `searchable = false` on every one of their passages (`searchable` is a passage field), each with `documents.superseded_by` set to the current text, and named in its note, and labeled "superseded text, kept as history". Genre `apostolic-constitution` for the 1996 text and `motu-proprio` for the other two (D5).
     - The 2007 act is Latin only. Per rule E it stays in the reader with a note and out of search, which `searchable = false` already gives.
     - The 2025 declaration is not ingested (application material, not law). Mention it in the document note with its link.
  3. HyDE. Broaden the `church-law` prompt from "a single canon of the 1983 Code" to "a provision of the Church's universal law, such as a canon of the 1983 Code or a numbered norm of an apostolic constitution".
  4. `dedup.py` chapter-keyed list already includes `church-law` (5.1b.1); confirm UDG passages carry `chapter_key` by chapter so the per-source cap works per chapter.
  5. Publish `papal` and `church-law` through 2.2w (stage, release report, one-transaction apply with the outline refresh, `chunks_live` switch) under a named apply in the lock file, never the delete-based prune. The history documents are Qdrant points with `searchable = false` (D5).
- **Acceptance checks:**
  - Release report shows 2 new papal documents and 4 UDG documents, of which 1 is searchable, and zero retirements.
  - A search for "how many votes are needed to elect a pope" returns UDG number 75 in its 2013 wording.
  - The 1996 wording never appears in search results and opens in the reader with the superseded label and a link to the current text.
  - `/sources` lists all four UDG documents with their status.
- **Production safety:** Additions only. `searchable = false` keeps superseded text out of search through the 2.2b filter. Rollback within the window is 2.2w's `rollback` command, which also points `chunks_live` back; later, a 2.2w apply that retires the documents, with tombstones for anyone who bookmarked them.
- **Needs Carter:** Approve the lock-file PR and the 2.2w apply. Confirm UDG belongs in Church law rather than Papal documents (the plan's collection table puts it in Church law; this is a confirmation, not a reopening).
- **Out of scope:** Other universal laws (for example *Praedicate Evangelium*, *Vos estis lux mundi*). Propose them as a follow-up.

### 5.5. Catechisms: Compendium of the CCC, Roman Catechism

- **Type:** PR per work, then ops publish
- **Depends on:** 2.2w, 5.2 rows, R6, and 1.2f's OCR tool and gate (D9) for the Roman Catechism if no clean text passes R6.
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
     - Genre `compendium` (D5).
  2. Roman Catechism. R6 first looks for a clean typed 1923 text and confirms the edition against a scan.
     - If one exists, write an adapter over it.
     - If not, run it through 1.2f's OCR tool and gate, as its own PR, as 5.6c does.
     - Genre `catechism` (D5), year 1566 for the work and 1923 for the translation, note "Catechism of the Council of Trent, a historical catechism; for current teaching see the Catechism of the Catholic Church".
     - Strip McHugh and Callan's notes and introduction (rule G).
  3. HyDE. Leave the CCC prompt, but add a retrieval follow-up to test whether the Compendium's short Q&A form is found; do not tune here.
  4. Each work publishes `catechism` through 2.2w (stage, release report, one-transaction apply with the outline refresh, `chunks_live` switch) under a named apply in the lock file, never the delete-based prune. The existing CCC document must show every passage as `same` in the release report.
- **Acceptance checks:**
  - Compendium has 598 questions (count from the source; confirm at build) and each answer is one passage.
  - Focused search on Catechism still returns 10 when asked (per-chapter cap, CLAUDE.md §18).
  - For the Roman Catechism, the 1.2f gate report if OCR was used.
  - Release report shows zero retirements in the CCC.
- **Production safety:** Additions to a released collection, visible together in one apply. Rollback within the window is 2.2w's `rollback` command, which also points `chunks_live` back; later, a 2.2w apply that retires the added documents.
- **Needs Carter:** Approve each lock-file PR and each 2.2w apply.
- **Out of scope:** Other catechisms (Baltimore, Pius X).

### 5.6a. Church Fathers additions and the Pseudo-Dionysius addition

- **Type:** PR per author or volume group, then ops publish
- **Depends on:** P4, 2.2w, 1.8b (the NPNF editorial strip, reused), 2.1, 5.2 rows, R6, and R1 where a work's authorship is doubtful.
- **Goal:** The Fathers collection gains Basil, Cyril of Jerusalem, Gregory Nazianzen, Gregory the Great, John Chrysostom, Ambrose and Leo the Great, all Doctors of the Church, plus Pseudo-Dionysius, so common questions about the Holy Spirit, baptism, pastoral care and the priesthood reach their classic patristic sources.
- **Current state:**
  - None of the seven authors is in the corpus, and neither is Pseudo-Dionysius (verified 29 Sep). Pseudo-Dionysius is therefore an addition here, not a move; the only work that moves collection in P5 is Boethius (5.1b.3).
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
  6. Each PR publishes `church-fathers` through 2.2w (stage, release report, one-transaction apply with the outline refresh, `chunks_live` switch) under a named apply in the lock file, never the delete-based prune. Existing Fathers passages must show as `same` in the release report.
- **Acceptance checks:**
  - Release report per PR with passage counts, no editorial passages (coverage test from 0.1a), author labels, and zero retirements of existing passages.
  - Storage projection (including the transient staging copy) and actual growth recorded against 5.2's total.
  - Targeted questions answered from the new sources (Basil *On the Holy Spirit*, Cyril's *Catechetical Lectures* on baptism, Gregory's *Pastoral Rule*, Chrysostom *On the Priesthood*).
- **Production safety:** Additions behind the publish lock, each PR's documents visible together in one apply. Rollback within the window is 2.2w's `rollback` command, which also points `chunks_live` back; later, a 2.2w apply that retires the PR's documents.
- **Needs Carter:** Approve each lock-file PR and each 2.2w apply. Decide the Pro upgrade when the storage total passes 450 MB (5.2).
- **Out of scope:** Replacing translations already in the corpus (P1.2 handles council sources; On the Incarnation moved in P1). Other Fathers not named in the plan (for example Bede and John Damascene, both before 750). Propose them later.

### 5.6b. Theologians and spiritual writers from CCEL ThML and Gutenberg text

- **Type:** PR per author or small group, then ops publish
- **Depends on:** 5.1b.4 (key `theologians`), 2.2a (`chunks.passage_author`, for the Catena), 2.2w, 1.9 (the medieval adapter fixes), 5.2 rows, R1 (rule A and Church-act checks, including the Pensées' Index status), R6.
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
     - Each document records genre, the translation's year on the card, and the credit line ("Sourced via CCEL.org" where applicable). Genre comes from D5's writer values (`treatise`, `manual`, `sermon`, `commentary`, `poem`, `rule`), `letter` for letter collections, and `other` for autobiographies, apologetics and anything else. Adding a value such as `autobiography` is a normal PR change to 2.1's genre module plus its `corpus_genres` row.
  4. Catena Aurea (decided: each quotation attributed to the Father quoted).
     - One passage per quotation, because grouping several quotations would put one Father's words under another's name.
     - Passage-level author is the Father (map CCEL's abbreviations such as "Chrys.", "Aug.", "Greg." to full names with a tested table).
     - Display is "Chrysostom, quoted in Aquinas's Catena Aurea". The document author is "Thomas Aquinas (compiler)".
     - Short quotations fall under `MIN_CHUNK_LENGTH` 50 (`datapipeline/config.py:54`). Exempt Catena passages rather than merge across Fathers, and merge only consecutive quotations from the same Father on the same verse.
     - The passage-level author is `chunks.passage_author` (2.2a, D5), set to the quoted Father on each Catena passage.
     - **Carter to note (unverified, research before this PR).** The Catena often quotes "Pseudo-Chrysostom", the *Opus imperfectum in Matthaeum*, whose author most scholarship identifies as Arian. R1 should decide under rules A and B whether those quotations stay, labeled "Pseudo-Chrysostom (Opus imperfectum)", or go. The Glossa quotations need an attribution too.
     - Luke and John are only on IA or ecatholic2000, so they go to 5.6c.
  5. Pensées. Carry the "Index status still to be checked (R1)" note; if R1 finds a prohibition, rule A removes it before publish.
  6. Each PR publishes `theologians` through 2.2w (stage, release report, one-transaction apply with the outline refresh, `chunks_live` switch) under a named apply in the lock file, never the delete-based prune. Existing passages must show as `same` in the release report.
- **Acceptance checks:**
  - Per PR, the release report shows no editorial passages (coverage test), author and translation labels, genre set, and zero retirements of existing passages.
  - Storage projection (including the transient staging copy) against 5.2's total.
  - Catena. 100% of passages carry a quoted-author label; a unit test covers the abbreviation table; no passage mixes two Fathers.
  - Targeted questions per work (for example "dryness in prayer" returns Teresa or Julian; "the little way" returns Thérèse).
- **Production safety:** Additions behind the publish lock, each PR's documents visible together in one apply. Rollback within the window is 2.2w's `rollback` command, which also points `chunks_live` back; later, a 2.2w apply that retires the PR's documents.
- **Needs Carter:** Approve each lock-file PR and each 2.2w apply. Choose between Rickaby's abridged SCG and the complete English Dominican SCG (5.6c). Decide the Pseudo-Chrysostom question after R1.
- **Out of scope:** Scanned works (5.6c). Anything in the candidates memo's list B (needs payment). Retrieval tuning for the enlarged collection.

### 5.6c. Scanned works, one PR per work

- **Type:** PR per work, then ops publish
- **Depends on:** 1.2f (the OCR clean-up tool and gate, built in Phase 1, D9), 2.2w, 5.6b's Gutenberg adapter pattern, 5.2 rows, R6, and 5.1b.4.
- **Goal:** Recover important works that exist only as page scans (John of the Cross in Lewis's translation, Teresa's *Foundations*, *Letters* and *Way of Perfection*, Tanquerey, Marmion and others) with text accurate enough to quote, each labeled as scanned.
- **Current state:**
  - The OCR tool and its quality gate are built and tested in Phase 1 as 1.2f (D9), so councils 8 to 18 (1.2e) can be replaced before Phase 4. This item reuses that tool and adds nothing to it except per-work configuration. The earlier plan had 1.2e depend on tooling built here, which made the two items wait on each other; with 1.2f first, the dependency runs one way only.
  - The decided method (Decision log, "OCR and scanned works"), which 1.2f implements:
    - Use a clean typed text where one exists, after confirming it is the planned edition. 19 of the 48 scan-only works have one (scan-only memo).
    - Where the clean copy's site claims copyright (ecatholic2000.com), ask the site or use it only to check our own OCR.
    - For the rest (23 works plus the missing parts of 6), a script strips page furniture and rejoins broken words, and a language model fixes character-level errors under hard limits. An edit changing more than about 2% of a passage's words is rejected, and the raw OCR is kept.
    - Gate before ingestion. The unrecognized-word rate on body text must be within 1 point of the clean baseline, and 20 random passages are checked against the page images.
    - Scanned passages carry a source label.
  - John of the Cross (*Ascent*, *Dark Night*, *Living Flame*) and Teresa (*Foundations*, *Letters*, *Way of Perfection*) go first.
- **Changes:**
  1. Use 1.2f's tool as built (fetch, furniture strip, model correction under the 2% limit, gate and review sheet). A work that needs a behavior the tool lacks gets a change to 1.2f's code in its own small PR with tests, not a second tool.
  2. Clean baseline per work. Prefer a clean text by the same translator and period, such as Lewis's typed *Spiritual Canticle* on CCEL for John of the Cross. Otherwise use the corpus's own ThML texts of the same decade. Record which baseline in the PR.
  3. One PR per work, each with:
     - The IA item id and the title-page date (5.2).
     - The strip list (introductions, notes, Wiseman's introduction for Lewis's John of the Cross, Faber's preface).
     - A structure config (chapters and numbered paragraphs).
     - The gate report.
     - The completed 20-passage review sheet.
     - Source label "From a scanned edition (Internet Archive <id>); errors possible".
     - A publish through 2.2w (stage, release report, one-transaction apply with the outline refresh, `chunks_live` switch) under a named apply in the lock file, never the delete-based prune.
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
  - 1.2f's gate passes (rate within 1 point of baseline; 20 of 20 passages match the page images after correction, with any mismatch fixed and the sheet re-run).
  - Raw OCR kept alongside (gitignored).
  - Release report (zero retirements of existing passages) and storage projection per PR.
  - Model cost stated in the PR.
  - The PR template's local source-check section filled in.
- **Production safety:** Each work is an addition behind the publish lock, visible in one apply. A work that fails the gate is not published. Rollback within the window is 2.2w's `rollback` command, which also points `chunks_live` back; later, a 2.2w apply that retires the work's documents.
- **Needs Carter:** Approve each lock-file PR and each 2.2w apply. Send requests to ecatholic2000 where its text is used as more than a proofreading aid. Choose the SCG edition. Review time for the 20-passage checks (about 30 to 60 minutes per work, per the Decision log).
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
  - A `church-law` adapter with genre `code` (D5) that distinguishes Eastern from Latin canons by issuer (for example `cceo`).
  - A publish through 2.2w like every other P5 addition.
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
