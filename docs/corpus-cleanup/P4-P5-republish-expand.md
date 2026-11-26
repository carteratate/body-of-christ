# Corpus cleanup, Phases 4 and 5: republish, reorganize, expand

**Before implementing any item in this file, follow `README.md` in this folder. It says to ask Carter the item's open questions first, record the answers, and update other specs only in the ways it allows.**

Work specifications for Phase 4 (republish) and Phase 5 (reorganize and expand) of `docs/2026-09-28-corpus-cleanup-plan.md`. Written 29 September 2026 and revised the same day to follow the plan's "Cross-cutting design decisions" (D1 to D11), which override anything here that disagrees with them. The plan and its Decision log are the source of truth. Nothing here reopens a decision; where a fact found while writing this bears on a decision, it is marked "Carter to note" and left for Carter.

Finding IDs C-01 to C-30 refer to the 6 Oct 2026 corpus reviews, merged in `docs/research/2026-10-06-corpus-review-synthesis.md`; `REVIEW-GAPS-PLAN.md` in this folder routes each to its item. 4.0, 4.1a, 4.1b, 4.2 and RF were extended for them on 9 Oct 2026, and RF-1 was added.

## Overview and recommended order

1. P4 republishes the cleaned corpus built in P1 to P3 in one apply, through the stage-then-apply writer (2.2w, D2), behind the publish lock (0.4) and the Qdrant alias `chunks_live` (2.2b). There is no release column. The new corpus is built into the `staging` schema and a new Qdrant collection, compared against live in the release report, applied to the live tables in one transaction, and then made visible to vector search by switching `chunks_live`.
2. Passage ids follow D1. They are frozen in the 2.1 registry, so every unit that exists today keeps today's id, even where 2.1 rebuilds its anchor, and a fixed text is updated in place. Only genuinely new units get new ids. Only the few anchors that now name different text get a redirect, and only user rows on those are remapped (4.1a). Removed passages are retired and show a tombstone (D3); user rows that point at them stay where they are.
3. Order for P4:
   - 4.0 storage (the `VACUUM FULL` window, 2.2c's rewrite, and the Qdrant settings for the new collection).
   - 4.1a user-data remap for redirects, with a local rehearsal of the whole 2.2w flow on a restored `pg_dump` (D8).
   - 4.1b step 1, staging build and new Qdrant collection.
   - 4.2 on staging.
   - The rest of the 4.1b cutover.
   - 4.2 again on production.
4. 4.2 checks accuracy only: targeted assertions on staging and on production. There is no baseline to compare against, because Carter dropped 0.3 on 30 Oct 2026 (Decision log "Baseline eval (0.3)").
5. Storage facts for P4 (0.5 and 0.6, 30 Oct 2026). Supabase is on Pro, so neither the `VACUUM FULL` peak (near 600 MB) nor the apply's (490 to 590 MB, 4.0) meets a read-only limit; its disk was 36% used. Qdrant is a Free cluster with 1 GiB of RAM and no backups. The new collection keeps today's in-memory vector setting (4.0 step 5), and the old collection is the rollback path.
6. P5 starts only after the P4 cutover and its rollback window close. Every P5 publish goes through 2.2w, each with its own named apply in a reviewed change to the lock file. No P5 publish uses today's delete-based prune (`writers/reader_writer.py`).
7. 5.2 (rights inventory) can run in parallel from now, and every addition PR waits for its row. 5.0 (how Denzinger is handled) is decided before any addition starts.
8. Order for P5 code is 5.1a genre and issuer filters, then 5.1c, then the four 5.1b PRs in order (5.1b.1 to 5.1b.4).
9. 5.1b depends on 5.1a because the old key `encyclicals` becomes "papal documents of genre `encyclical`" after the merge.
10. Then 5.3a (Roman Curia, from the parked branch), 5.4, 5.5, 5.6a, 5.3b, 5.6b, and 5.6c one work at a time. 5.6c and the Roman Catechism in 5.5 reuse the OCR tool and gate built in Phase 1 as 1.2f (D9).
11. 5.9 (the verdict beside condemned texts) any time after 4.3's and 4.4's publishes. 5.7 (About page) goes last, once the content it describes exists. The Eastern code stays blocked. Retrieval follow-ups open after the republish.
12. Qdrant is the binding constraint for P5. Its Free cluster has 1 GiB of RAM and 4 GiB of disk, and each publish briefly holds two collections; Supabase Pro has room for every planned addition. Every addition PR carries a projection of both (see 5.2).

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

Supabase documentation (read 29 Sep) says Free plan projects enter read-only mode when database size exceeds 500 MB, and that branching (preview branches) requires the Pro plan and copies schema without production data ([database size](https://supabase.com/docs/guides/platform/database-size), [deployment and branching](https://supabase.com/docs/guides/deployment)). That is why rehearsals run locally (D8). The organization is on Pro (0.6, 30 Oct 2026), so the 500 MB limit does not apply to production; rehearsals stay local because branches copy no data.

Qdrant figures were re-read on 30 Oct 2026 (0.5). There is one collection, `chunks`, with 54,555 points at 1,536 dimensions, vectors in memory (335 MB) and payloads on disk (68 MB), no quantization, no alias and no snapshots, on a Free cluster with 1 GiB of RAM, 4 GiB of disk, 0.5 vCPU and no backups.

Figures that bear on the storage projection and the remap come from the other specs (29 Sep, estimates where marked):
- Retired rows at P4 are the rule A to G removals (about 2,100 passages) plus the Tanner council units and the 47 On the Incarnation passages that replacement texts supersede. Retired rows already exist in `chunks`, so retiring them adds no space.
- New units are restored verses, recovered prose (Vatican II continuations, Trent, Vatican I, the Summa's Q71 and Q72), split recensions and the replacement council and Incarnation texts. The master build is 54,778 passages against 54,568 live, and 0.6 puts the Vatican II and council repairs at about 0.9 MB of text. The replacement council texts are not yet built, so their size is unmeasured.
- Rows the apply updates in place are those whose text, citation or labels change. That is at least the 2,439 content differences under equal ids measured on 29 Sep, plus the split-piece citation fixes of 1.10c (every Summa passage and about 9,000 others), so roughly 35,000 to 40,000 rows (estimate).

## Prerequisites from earlier phases

P4 and P5 assume these have merged. Each spec below names the ones it needs.

| ID | What P4/P5 relies on |
|---|---|
| 0.1c | Release report produced from staging against live, with the remap outcomes (`same`, `moved`, `split`, `merged`, `renumbered`, `removed`, D5), `remap.jsonl` and `chapter_remap.jsonl`. It fails a build where an unchanged anchor's text similarity falls below its threshold without a redirect (D1) |
| 0.2 | Source hashes, manifests, rights inventory file |
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
| 2.4d, 3.4 | The rejected-voice role (C-01): 3.4's ranges in the registry, 2.4d's API and web handling, live before the P4 apply |
| 2.4f | Passage text labels (scanned edition, unofficial canon English) and the amended-canon Latin link in the API and on opened passages, live before the P4 apply |
| 2.2c | The `search_vector` migration (C-16), applied in 4.0's window before staging |
| 0.1d, R7 | The checks for the 6 Oct review findings; the Summa against an independent edition, which 1.7 waits for |
| R1, R6 | Rule A dating and Church-act checks; edition and provenance per planned source |

How D1 and D2 shape P4, stated once here so the items below can rely on it:

- Every unit that exists today keeps today's passage id, frozen in the 2.1 registry, even where 2.1 rebuilds its anchor from the source's structure. Rebuilding anchors does not re-key the corpus. If a unit's text changed (notes stripped, prose restored, label or citation fixed), the apply updates the row in place, so bookmarks and history keep pointing at it and gain the corrected text. No remap is needed.
- Only genuinely new units (restored verses, recovered prose, split recensions, replacement texts) get new ids. Where a fix changes which text an old anchor names (Joel and Malachi renumbering, a council rebuilt by session, a split recension), the old id gets a redirect to the new unit. 4.1a moves user rows along these redirects, which are few.
- A removed passage is retired with a tombstone. User rows keep pointing at it and show the tombstone. No remap.
- `chunks` never holds two copies of the corpus and nothing filters on a release. The only extra copy is `staging`, which exists from the build until it is dropped after the apply.

---

## Phase 4. Republish

### 4.0. Storage: compact `chunks`, project the apply, size the new Qdrant collection

- **Type:** ops
- **Depends on:** 0.5 (Qdrant limits), 0.6 (headroom snapshot). Runs before 4.1a's rehearsal measurement is final.
- **Goal:** Get back the space earlier rewrites left inside `chunks`, project the database size through the staging build and the apply, and confirm from those numbers and the rehearsal that the apply fits. Users see nothing, apart from search and the reader pausing during the `VACUUM FULL` lock.
- **Current state:**
  - **Plans (0.5 and 0.6, 30 Oct 2026).** Supabase: Pro, Micro compute (1 GB RAM), disk 36% used, daily backups; database 402 MiB and `chunks` 380 MiB, unchanged since 29 Sep. Pro has no read-only trigger at these sizes, so the peaks below are recorded, not decided on. Qdrant: Free cluster, 1 GiB RAM, 4 GiB disk, 0.5 vCPU, no backups and no snapshots.
  - Database 401 MB, `chunks` 380 MB, of which live row bytes are 123 MB (measured 29 Sep, table above). Dead tuples are 0, so the roughly 166 MB gap between live rows and heap plus TOAST is free space inside the files. Plain `VACUUM` already made it reusable for new inserts; only `VACUUM FULL` returns it to the database size figure.
  - The Decision log row "Storage (4.0)" says to compact `chunks` with `VACUUM FULL` in an approved quiet window, measure, and rehearse locally (D8). Supabase is on Pro, so there is no read-only limit to plan around. Qdrant is a Free cluster; the new collection keeps today's in-memory vector setting (step 5).
  - **Carter to note (the `VACUUM FULL` peak).** `VACUUM FULL` writes a complete new copy of the table and its indexes before dropping the old one. The new copy is estimated at 123 MB of rows plus 60 to 88 MB of rebuilt indexes, so the database may briefly reach about 590 to 610 MB. On Pro that is well inside the disk (8 GB included, 36% used on 30 Oct 2026). What matters is time: the rewrite runs on Micro compute, and search is down while it holds the lock (Production safety).
  - **Carter to note (projection with one staging copy, estimates).** D2 removes the doubled `chunks` table, and frozen passage ids (D1) mean the corpus is not re-keyed. What remains is one staging copy, the new units the apply inserts, and the old versions of rows it updates in place. At about 3.5 KB of database per passage (123 MB of rows plus about 70 MB of indexes over 54,568 passages):
    - After `VACUUM FULL`, about 230 MB (220 to 260 MB).
    - The staging copy needs today's indexes, including the full-text GIN index, because 4.2 searches it. That is about 123 MB of rows plus up to 88 MB of indexes, so about 210 MB. The peak while staged is about 440 MB.
    - The apply runs while staging still exists. Retiring about 2,100 removed passages and the superseded Tanner and Incarnation units adds nothing, since those rows already exist. New units are about 2,000 to 6,000 passages (the repairs' 0.9 MB of text plus the unbuilt replacement council texts), so about 7 to 21 MB.
    - The larger cost is the in-place updates. Postgres writes a new version of each updated row and keeps the old one as dead space until the next vacuum. With roughly 35,000 to 40,000 rows updated, that is about 40 to 130 MB, depending on how much of each row changes (a citation-only change reuses the stored content).
    - The peak during the apply is therefore about 490 to 590 MB before any P5 addition, well inside Pro's disk.
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
     Check the dashboard for disk use (36% on 30 Oct 2026).
  2. Disk check. If disk use plus the peak estimate would pass 85% of the provisioned disk, stop and ask Carter. It is not expected to trigger: 0.6 measured 36% on 30 Oct 2026, and the peak adds about 250 MiB. Do not work around it by dropping indexes, which would break full-text search during the window.
  3. Quiet window (Carter approves the time). It applies 2.2c's migration, `supabase/migrations/0045_search_vector_markers_and_reference.sql`, which redefines `search_vector` (C-16, decided by Carter on 9 Oct 2026), and then runs `VACUUM FULL` only if the measurement shows space left to reclaim. The migration rewrites `chunks` and rebuilds its indexes as `VACUUM FULL` does, so it comes first. Never run two rewrites back to back without measuring the size between them; each has the peak described above. The migration must be applied before 4.1b step 1. All in one `psql` session:
     1. Check that staging holds no publish, since step 3.3 drops it. Both must return 0 rows; if not, stop and ask Carter:
        ```sql
        select id from corpus_publishes where cleaned_up_at is null and discarded_at is null;
        select 'chunks' t, count(*) from staging.chunks having count(*) > 0
        union all select 'documents', count(*) from staging.documents having count(*) > 0;
        ```
     2. Apply the migration. It sets its own `lock_timeout = '5s'` and `statement_timeout = 0` for its transaction, drops the GIN index, rewrites the column (`SET EXPRESSION` on Postgres 17) and builds the index again:
        ```sql
        \timing on
        \i supabase/migrations/0045_search_vector_markers_and_reference.sql
        ```
        Run it as one transaction (`psql --single-transaction -f …`, or `begin;` … `\i` … `commit;`). If the lock is not acquired within 5 s, it fails and changes nothing; retry once a minute, and do not raise `lock_timeout`. Measured locally on 12 Nov 2026 (Postgres 16 on the Lenovo, a restore of the 31 Oct snapshot's 54,555 passages without `metadata`, drop-and-add path): 9.4 s, `chunks` 186 MB before and 181 MB after. Production's Micro compute is slower and its rows carry `metadata`, so expect several times that; search and the reader pause for all of it.
     3. Recreate staging, because 0043 created the staging tables with the old expression, `CREATE TABLE IF NOT EXISTS` would keep them, and 2.2w's shape check refuses a stage until they match:
        ```sql
        select drop_corpus_staging();
        select create_corpus_staging();
        analyze chunks;  -- the rewrite leaves search_vector without statistics
        ```
     4. Record the migration in the Supabase ledger (`supabase_migrations.schema_migrations`) the way 0042 and 0043 were recorded (`NEEDS-CARTER.md`, 2.2a).
     5. Measure with the step 1 queries. Then, only if heap plus TOAST is still well above the live row bytes:
        ```sql
        set lock_timeout = '5s';
        set statement_timeout = 0;
        vacuum (full, verbose, analyze) chunks;
        ```
     6. Check the rewrite, which must return 0, and that keyword search finds `canon 1055`, `ccc 2267` and `john 3` (4.2's keyword-search checks):
        ```sql
        select count(*) from chunks where search_vector is distinct from
          setweight(to_tsvector('english', regexp_replace(content, '\{\{v:\d+\}\}', ' ', 'g')), 'A')
          || setweight(to_tsvector('english', regexp_replace(coalesce(reference, ''), '[§:;,.()–—-]', ' ', 'g')), 'B');
        ```
     Rollback, if search misbehaves: apply 0004's expression the same way (`alter table chunks alter column search_vector set expression as (to_tsvector('english', content))`, with the index dropped first and built after, in one transaction), then step 3.3 again. Neither direction loses data.
  4. Measure again with the step 1 queries. Record duration, before and after sizes, and WAL size.
  5. Qdrant (settled from 0.5, 30 Oct 2026). From 4.1b step 1 until the old collection is deleted after the rollback window, the cluster holds two full collections (today's `chunks` and the new one, each with every passage). 4.1b creates the new collection with today's settings, `on_disk=False` for vectors and the HNSW graph in memory (decided by Carter on 30 Oct 2026). Two collections fit the Free cluster's 1 GiB: Qdrant stores in-memory vectors as `InRamChunkedMmap`, a file-backed mapping it loads up front, so their 335 MB is page cache the kernel can reclaim, and the memory Qdrant cannot give back is about 52 MB today (0.5). If both collections' vectors do not fit in the cache, the cost is page faults and slower search, not an out-of-memory restart. 4.2's pre-cutover run times searches on the new collection. If they are too slow, Carter chooses between a paid Qdrant tier for the cutover month and the slower search.
  6. Apply peak. After 4.1a's rehearsal reports the peak database size through staging and apply, record it next to the projection above. Nothing is decided unless it would fail step 2's disk check. P5's limits are 5.2's stop.
- **Acceptance checks:**
  - Ops log (kept in the issue, not in a repo file) has before and after sizes, duration, and WAL size.
  - `pg_database_size` after compaction is recorded; expected 220 to 260 MB (estimate, not measured).
  - The ops log states the projected peaks (staged and at apply) next to the rehearsal's measured peaks.
  - `/health/db` and `/health/search` return 200 after the window; one search per collection returns results.
- **Production safety:** `VACUUM FULL` takes an ACCESS EXCLUSIVE lock, so full-text search and the reader fail while it runs (the plan expects under a minute; GIN rebuild time on this compute is unverified). Vector search still reaches Qdrant but fetches from Postgres fail, so searches error rather than return partial results. `lock_timeout` prevents a stuck lock queue. There is no data change and nothing to roll back; if interrupted, Postgres discards the new copy. Supabase Pro has no read-only trigger at these sizes, so nothing lasts beyond the lock.
- **Needs Carter:**
  - Approve the window and the run, including 2.2c's migration.
  - Choose a paid Qdrant tier for the cutover month if search on the new collection is too slow in 4.2 (step 5).
- **As built (15 and 16 Nov 2026).** Steps 1 to 4 are done; step 5 needed nothing; step 6 is recorded below from 4.1a's rehearsal (16 Nov 2026). The ops log, with every query's output, is in #190.
  - Connection: `psql` from the Lenovo over Supavisor session mode (port 5432), which is not the transaction pooler (6543). Steps 1, 2 and 3.1 ran in read-only transactions.
  - Step 1 (15 Nov 21:09 UTC): Postgres 17.6. Database 403 MB. `chunks` 380 MB: heap 89, TOAST 200, indexes 88. Live row bytes 123 MB (content 42, `search_vector` 49, metadata 5). WAL 128 MB. 1,600 dead tuples. 0045's expression, computed read-only over all 54,555 rows, took 6.8 s and gave 56 MB of vectors.
  - Step 2: passed. The peak (one new copy of `chunks` plus its WAL, at most about 0.5 GB) puts disk use near 42% against the 30 Oct reading of 36% of 8 GB.
  - Step 3.1: 0 open publishes and empty staging, both on 15 Nov and again at the window.
  - Step 3 (16 Nov 2026, 00:27 UTC; Carter approved running at once instead of 20:30 UTC; 0045 only, 0044 left for #330):
    - 0045 ran in one transaction and acquired its lock on the first try. The rewrite (`SET EXPRESSION`, the first run of that path anywhere) took 18.1 s and the GIN index 3.0 s, so **search and the reader were locked out for about 21 s**.
    - Recreating staging took 0.16 s and `ANALYZE` 1.1 s.
    - Ledger row: `20261116002752` / `0045_search_vector_markers_and_reference`, the whole file as the one statement, `created_by` `claude-code, approved by Carter (4.0, #190)`.
    - `VACUUM FULL` was not run, because the rewrite left heap plus TOAST (148 MB) within 18 MB of live row bytes (130 MB).
    - The `IS DISTINCT FROM` check returned 0, and no passage keeps a marker token.
  - Step 4: database **403 → 210 MB** (the estimate was 220 to 260 MB). `chunks` **380 → 187 MB**: heap 82, TOAST 66, indexes 39. The search-vector index went from 26 to 17 MB. WAL 176 MB.
  - Index contents. John 3:1–21 held the numbers 2 to 21 from its verse markers; it now holds only 3, 1 and 21, all at weight B, from its reference. "CCC §2263–2267 (part)" adds ccc, 2263, 2267 and part. "Code of Canon Law, Can. 1055" adds code, canon, law and 1055.
  - Keyword step alone (production's `min_match` SQL, in-process), top results before → after:
    - "canon 1055": canon 1055 absent → first.
    - "ccc 2267": no hits → CCC §2263–2267 (part) first.
    - "psalm 23": Acts 1:12–26, Acts 13:13–52, Judith 16 and 1 Chronicles → Psalms 23:1–6 first.
    - "john 3": Acts, Matthew and 1 Maccabees → John 3:22–36 second and John 3:1–21 sixth.
    - "john 3 16": four Maccabees passages matched through markers → none; John 16 and John 3 lead.
  - Two results differ from what was expected. Neither is a marker match:
    - "psalm 23" still returns Acts 13:13–52 (6th) and Judith 16 (10th). Their text holds the word "psalm" (Acts 13:33 and 13:35, Judith 16:1), and min-match accepts one word of two.
    - "john 3 16" returns 1 Timothy 5:3–16 and 2 Kings 1:3–16, through the 3 and 16 their references print. That is the citation-number side of 0045.
  - Known limits, as designed: a number inside a printed range is not indexed (CCC 2265, John 3:16), and text matches (weight A) rank above reference-only matches (B).
  - Step 6, from 4.1a's rehearsal (16 Nov 2026, a restored copy of production at 199 MB; 4.1a As built, part 2). Sizes are `pg_database_size` in `pg_size_pretty` units, as above:

    | Point | Projected (this item) | Measured |
    |---|---|---|
    | After the staging build | about 440 MB | 397 MB |
    | Peak of the apply | 490 to 590 MB (the report's own projection: 467 MiB) | **720 MB** |
    | After staging is dropped | 280 to 380 MB | 523 MB |
    | Peak of a rollback | not projected | 764 MB |

    The apply peak is above the projection because the apply writes most rows of `chunks` about twice (2.2w moves live anchors to `~<anchor>` and back), leaving about 109,000 dead row versions beside 58,000 live ones until the next vacuum; the projection counted one new version per changed row. Production starts 11 MB larger, so expect about 730 MB at the apply peak. Step 2's check still passes (under 1 GB more on an 8 GB disk at 36%), so nothing is decided. The apply transaction took about 36 s locally; the 0045 window ran 2.3 times slower on production than on the Lenovo (21.8 s against 9.4 s), so expect one to two minutes there, during which user writes to the six user tables wait for the commit (4.1a's `EXCLUSIVE` locks).
  - Ordinary questions, keyword step:
    - "the dignity of human labor" (encyclicals): the same 10, reordered.
    - "grace and free will" (church-fathers): 8 of 10 the same.
    - "whether God exists" (summa): only 4 of 10 the same, because Summa references carry the article titles, whose words now count at weight B. Q2 A3 "Whether God exists?" entered the keyword top 10.
  - Acceptance:
    - `/health`, `/health/db` and `/health/search` return 200.
    - One production-pipeline search per collection, in-process (`runner.run`, which writes nothing), returned results in all ten. The Summa search still ranks Q2 A3 first.
    - Projected peaks next to the rehearsal's measured ones wait for step 6.
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
  - Expected remap volume (estimate). Redirects come only from fixes that change which text an old anchor names: Joel and Malachi renumbering, councils rebuilt by session, split recensions, and Tanner units where a replacement unit is named as successor. That is at most a few hundred to about 2,000 old ids, most in `councils`. The user rows on them are likely in the tens. Split pieces add to this (C-10): under 2.1's rule a live piece whose opening paragraph no longer opens a piece redirects to the piece that now holds it. With numbered pieces, 1.10b alone would have moved 558 Fathers pieces carrying 99 saved rows, and about 700 saved rows sit on pieces in all, so the rows to move may reach the low hundreds. That is still small enough for exact rules. For comparison, 0.1c's 29 Sep report found 12 live passages with no successor in the master build, carrying 19 `retrievals` and 2 `guest_trial_retrievals` rows, and the plan counted 50 retrievals and 0 bookmarks on passages the rules remove. The release report's user-impact section gives the exact count before the apply.
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
  3. The ledger. Every repointed, merged, dropped or rewritten row is written with its table, primary key, prior values, the values `forward` wrote, and the rule applied. `reverse` works only from these entries, never from the redirects alone, so a row that was already on a redirect target before the apply, or that a user created there afterwards, is never moved.
     - The private form is a local file on Carter's Mac, next to the 4.1b step 4 backup, and it is what `reverse` reads. It holds note text and user ids, so it is never committed and is deleted when the rollback window closes.
     - The public form is counts only, per table and per rule (repointed, merged, dropped, notes joined, notes kept apart, reading positions moved to a first chapter). It goes into the release report and the PR. It carries no ids, queries or note text, since the repo is public.
  4. `reverse`, which 2.2w's `rollback` calls inside its transaction (4.1b step 12 runs only that command). It runs during the rollback window (up to 14 days), so users will have changed rows since the apply. Its rule: **undo only what the ledger recorded, and never overwrite or recreate anything a user changed since the apply.**
     - **Repointed rows.** Move a row back to its old id only if it still exists and still holds the values `forward` wrote. A row the user deleted stays deleted. A row the user changed (a bookmark note, a reading position with a later `updated_at`) keeps the user's version.
     - **Merged survivors.** Restore a survivor's prior values (for example, split a joined note back into the earlier bookmark's note) only if the survivor still exists and still holds the values `forward` wrote. Otherwise leave it as the user has it.
     - **Dropped rows.** Re-insert a dropped row only if all of these hold: the survivor it was merged into still exists unchanged (so a merged bookmark the user deleted, or whose joined note they edited, does not come back); every parent row still exists (`auth.users` for `user_id`, `searches` for `retrievals` and `retrieval_labels`, `guest_trials` for `guest_trial_retrievals`); a guest row's trial has not been claimed since the apply (`guest_trials.claimed_at` is NULL or before the apply), since `POST /v1/guest/claim` has already copied it into `retrievals`; and no row now holds its unique key.
     - **Skipping is never an error.** Each skipped row is counted per table and per reason (deleted by user, changed by user, parent deleted, guest claimed, unique key taken) in the public ledger counts, and the transaction continues. A deleted search, account or guest trial must never abort a corpus rollback. Only a genuine fault (a ledger entry that does not parse, a database error other than these checked conditions) aborts it.
     - Rows created after the apply that the ledger does not name are left alone and counted, whether their id exists only in the new corpus or also existed before.
  5. Tests in `datapipeline/tests/test_remap_user_data.py` using an in-memory fake store:
     - One test per collision rule above.
     - Every repointed, merged or dropped row appears in the ledger, and with no user activity in between, `reverse` restores the exact prior rows.
     - Changes made between `forward` and `reverse`, one test each: the user deletes the surviving bookmark of a merge (the dropped bookmark is not recreated); the user edits a joined note (the note is kept, the dropped bookmark is not recreated); the user deletes a search whose retrievals were deduplicated (the dropped retrieval is skipped and `reverse` returns without error); the user deletes their account; a guest trial is claimed; the user advances a reading position that `forward` moved (the newer position is kept); the user bookmarks a redirect target that already existed before the apply (that bookmark is not moved). Each asserts the skip counts.
     - `test_reverse_skip_never_aborts`: a `reverse` with every skip condition present completes, and the surrounding transaction commits.
     - `test_impl_satisfies_2_2w_protocol`: `UserDataRemapImpl` type-checks against 2.2w's `UserDataRemap`.
     - Rows on retired passages without a redirect are untouched.
     - Rows on an id whose text changed but whose anchor did not are untouched.
     - The tool refuses to run if a redirect's target id is missing from `chunks`.
  6. Rehearsal (D8), local only.
     - Carter approves taking a `pg_dump` of production's `public` schema, schema and data (auth users only as ids, enough for the foreign keys).
     - Restore it into a local Postgres (`supabase start`, with the committed migrations and 2.2a applied), and run a local Qdrant (`docker run qdrant/qdrant` at the production server version) holding a copy of `chunks` with the alias `chunks_live`.
     - Run the full 2.2w flow against it exactly as 4.1b will: stage, release report, apply with this remap inside the transaction, outline refresh, alias switch. Then run 2.2w's `rollback`, which calls `reverse` in the same transaction, and check that the user tables match the dump.
     - Run the cycle a second time with user activity between apply and rollback, made through the API code paths against the local database: delete a merged bookmark, edit a joined note, delete a search with deduplicated retrievals, delete a test account, claim a guest trial, move a reading position. The rollback must commit, and each affected row must end as the rules in step 4 say. If 2.2w's own rehearsal already filled the embedding cache on this Mac, this stage pays only for inputs changed since; otherwise it is the first full stage and fills it. Record its token count either way (2.2w stage step 6).
     - Measure `pg_database_size` after the staging build, at the peak of the apply, and after staging is dropped. These are the numbers 4.0 step 6 uses. Also time the apply transaction.
     - The dump contains user data. It stays on Carter's Mac, is never committed, and is deleted after the rehearsal along with the local database.
- **Acceptance checks:**
  - `python3 -m pytest tests/test_remap_user_data.py -q` passes in GitHub Actions (no sources needed).
  - The rehearsal report in the PR (counts only) shows zero user rows pointing at an id that has a redirect. Bookmark count before equals count after plus merged rows, and every merged or dropped row is in the ledger.
  - After 2.2w's `rollback` with no user activity in between, the rehearsal's user tables match the dump row for row (checksums per table).
  - After the second cycle, with user activity in between, the rollback committed, and the PR lists each scripted action with the row's end state and the skip counts.
  - The PR description states the three measured database sizes, the apply peak next to 4.0's projection, and the apply's duration.
  - The PR description confirms the dump and the local database were deleted.
- **Production safety:** The PR adds the implementation 2.2w calls, a read-only CLI and tests; nothing runs against production on merge, and the lock still refuses every live apply. The tool never deletes a `chunks` row. Rollback of the merge is a revert.
- **Needs Carter:** Approve taking the production `pg_dump` for the local rehearsal (it holds user data; it stays on his Mac and is deleted afterwards). Approve the collision rules above and the reverse rules in step 4. Answered 15 Nov 2026: both approved as written, with the two rules the As-built notes record (the first live chapter for a reading position whose chapter is gone, with or without a redirect; a label keeps its rank).
- **Out of scope:** Deleting retired rows (4.1b, after the rollback window). Rows on removed passages (they keep their row and show the tombstone). Any change to how saved searches render.
- **As built, part 1 (14 Nov 2026):** the remap code and its tests (steps 1 to 5). Step 6, the rehearsal, is part 2 below. The facts the code showed differently:
  - `datapipeline/remap_user_data.py` holds `UserDataRemapImpl(root=SNAPSHOT_ROOT)`. `publish.py apply` and `rollback` pass it to 2.2w's `apply` and `rollback`, and print its public counts. The CLI is `python3 -m remap_user_data --dry-run [--rows] [--redirects <file.jsonl>]`; `--dry-run` is required, it runs in a read-only transaction, by default it reads the staged publish's redirects, and it plans against the corpus the staged publish will leave (`staging.chunks` for the staged documents, live rows for the rest), so its plan equals what the apply then does. `--rows` lists each row's key and target, never note text.
  - Input. 2.2w passes `staging.corpus_redirects` rows, not 0.1c's files: `redirects` are its `passage`, `anchor` and `document` rows and `chapter_remap` its `chapter` rows, which 2.2w built from `chapter_remap.jsonl`. A `chapter` row's `old_anchor` and `new_anchor` hold chapter keys.
  - The ledger's private form is `user_remap_ledger.jsonl` in the publish's before-snapshot folder (`datapipeline/releases/snapshots/<release>-before/`, gitignored, owner-only file mode), on the machine that runs `publish.py`, and its sha256 is added to `corpus_publishes.snapshot_sha256` in the apply's commit. So `rollback`'s snapshot check also checks it, and it is deleted with the snapshot when the window closes (4.1b step 13). A publish whose `snapshot_sha256` has no ledger was applied without the remap, and `reverse` moves nothing for it. A ledger that differs from its hash or does not parse aborts the rollback.
  - Each entry holds the row before and the row forward left, as `to_jsonb` reads them, so `reverse` compares the whole row: any change by a user counts as "changed". A dropped row's entry holds its survivor as forward left it.
  - Public counts are keyed `<table>.<rule>`: forward `repointed`, `merged` (groups), `dropped`, `notes_joined`, `notes_kept_apart`, and for reading positions `rewritten` and `first_chapter`; reverse `restored`, `reinserted`, `skipped_<reason>` (`deleted_by_user`, `changed_by_user`, `parent_deleted`, `guest_claimed`, `unique_key_taken`) and `untouched_made_after_apply` (rows made since the apply on a redirect target, or on a passage the rollback has just retired, that the ledger does not name).
  - Rules the spec left open, settled by the code: a bookmark merge with only one non-empty note keeps that note; notes equal after trimming are not doubled; more than two bookmarks join every distinct note in `created_at` order. Ties fall to `created_at`, then the row ID. A reading position whose chapter has no live passage after the apply goes to its document's first live chapter even with no redirect, since 2.2w writes no chapter redirect for a chapter removed outright (`retirements.chapter_redirects`); this also covers a position whose chapter was already gone before the publish. A reading position whose anchor has a redirect takes the target's document and live chapter; one whose document has a `document` redirect and no chapter or anchor redirect goes to the new document's first live chapter; a target document with no live chapter refuses the apply. A redirect target that is missing from `chunks` or retired refuses the apply.
  - `forward` and `reverse` lock the six user tables in `EXCLUSIVE` mode for the rest of the transaction: reads continue, and user writes wait for the commit (the apply's 2-second `lock_timeout` applies).
  - `retrieval_labels.rank` is left as it is when a search's duplicate result is dropped, as step 2 says, so a label can name a rank its search no longer holds. Production had 3 labels on 14 Nov 2026, none on a redirected ID.
  - Tests are `datapipeline/tests/test_remap_user_data.py` on a real local PostgreSQL (`tests/pg_corpus.py`, whose new `use_production_user_tables` gives a test database production's user tables) instead of an in-memory fake store, with synthetic users only; one test runs the whole 2.2w apply and rollback with the remap.
  - Volume (read-only counts against production, 14 Nov 2026, against the registry's 2,571 open passage redirects and 38,672 changed anchors on master): 202 of 4,296 retrievals and 4 of 96 guest results point at redirected IDs, and 6 searches would hold one passage twice; 0 of 25 bookmarks, 0 of 3 labels, no feedback with a passage, and 0 of 35 reading positions on a changed anchor (2.2w's 4 Nov report found 10 through chapter redirects). The release report gives the count at P4.
- **As built, part 2: the rehearsal (step 6, 16 Nov 2026).** Carter approved on 15 Nov 2026 a `pg_dump` of production's `public` schema, schema and data, with auth users as IDs only; the whole rehearsal on the Lenovo, in place of D8's Mac as for 2.2w; and the embedding spend. Production was only read: the dump (12 s, 25 MB compressed, plus the 18 user IDs), a read-only scroll of Qdrant's 54,555 points with their vectors (2 min, in batches of 256), and version and size checks. Built at `99caf86` (master on 16 Nov 2026). The facts it showed:
  - Setup. PostgreSQL 17.12 from the PGDG apt repository (production runs 17.6) with pgvector, in a cluster of its own in an owner-only folder outside the repo. It held the dump's `public` and `staging` and stand-ins for what `public` refers to: `auth.users` with the 18 IDs, `auth.uid()`, `auth.role()`, and the roles `anon`, `authenticated`, `service_role` and `supabase_admin`. Qdrant 1.18.2 (production's version) ran from its release binary on 127.0.0.1, holding the copy of `chunks` with the alias `chunks_live`. Every command ran with `DATABASE_URL` and `QDRANT_URL` on 127.0.0.1, so the lock's loopback rule passed and nothing could reach production. `releases/snapshots/`, which receives the private ledger, pointed into the same owner-only folder; the ledger file was written owner-only. The restored copy was 199 MB (production 210 MB) and its user tables held production's counts.
  - Stage of all collections: 350 documents and 51,427 passages, 4,637 tombstones, redirects 2,092 passage, 36,679 anchor and 6,122 chapter; 589 passages move document. 12 min. 23,468 embedding inputs were not in the 4 Nov cache (about 7.8 million tokens, about $1.02 at $0.13 per million, counted before any call), and 27,959 came from it. A second stage of the same build took every vector from the cache (0 calls, 2 min). The stage prints "new IDs 0" because the registry already holds every ID; the report's 3,516 are IDs not live today.
  - Report: publish checks pass, 0 failing checks. Live IDs kept 47,911, retired 4,552, redirected 2,092; new 3,516. 85 documents retired: `awaiting-permission` 51, rule A 16, rule B 13, rule C 4, `translation-in-preparation` 1. User rows on retired IDs: retrievals 133 and reading positions 4; on redirected IDs: retrievals 194, guest results 4 and reading positions 12. 4 min. The report process uses about 2 GB of memory; it was killed once by the kernel while the machine also held three Qdrant collections, and ran cleanly when rerun.
  - Cycle 1, the flow as 4.1b runs it (`apply --no-switch`, the outline check, `switch`, `cleanup`, then `rollback`):
    - The dry run and the apply agreed. Public counts: retrievals repointed 185, merged 6 (six searches), dropped 6; guest results repointed 4; reading positions rewritten 12 and moved to a first chapter 1; bookmarks, labels and feedback 0; notes joined 0.
    - Apply: 435 documents touched, 3,516 passages inserted, 6,644 passages and 85 documents retired, 4,637 tombstones, 44,893 redirects. The transaction took about 36 s (about 8 s reading the before-snapshot, then about 28 s of writes), 37 s wall.
    - After it: 0 of 350 live documents with `chunk_count IS NULL`; 0 user rows on a redirected passage, anchor or chapter; retrievals 4,296 → 4,290, the six dropped rows. 4 reading positions stay on chapters with no live passage, all in documents retired outright (3 `awaiting-permission`, 1 rule A), so there is no first live chapter; they show the tombstone. The new collection holds 51,427 points, 48 of them `searchable = false`, equal to staging.
    - Rollback, 86 s wall: every user table equals the dump by checksum, and the 421 live documents, 54,555 live passages and 13,255 outline rows equal the dump field for field. The 14 documents and 3,516 passages the publish added are retired with `rolled-back` tombstones, and the alias is back on `chunks`.
  - Cycle 2, with user activity. No real bookmark or label is on a redirected ID, so before the apply two synthetic test accounts were given rows on eight redirect pairs no user row touched, one per collection: bookmarks meeting on one passage (three merges, each with two notes, and one plain repoint), searches holding a passage twice, two labels meeting in one search, a guest trial ready to transfer with two results meeting, and a reading position on a redirected anchor. The dry run and the apply agreed: bookmarks repointed 1, merged 3, dropped 3, notes joined 3; labels merged 1, dropped 1; guest results merged 1, dropped 1; retrievals merged 9 (6 of them real); the rest as cycle 1. This apply inserted 0 passages and un-retired cycle 1's 3,516. Then, through the API's routes in process against the local database, with the auth dependency set to the test account:
    - PATCH a joined note (200): the rollback kept the edited note on the target and did not re-add the merged bookmark (`skipped_changed_by_user`).
    - DELETE a merge's surviving bookmark (204): it stayed deleted, and the merged one was not re-added (`skipped_deleted_by_user`).
    - POST a bookmark on a redirect target that existed before the apply (201): left where it was (`untouched_made_after_apply`).
    - DELETE a search whose duplicate result was dropped (204): the dropped row was skipped (`skipped_parent_deleted`).
    - Delete the second test account. No route deletes an account, so its `auth.users` row was deleted, as Supabase Auth's admin delete does; its merged bookmarks and deduplicated results were skipped (`skipped_parent_deleted`).
    - POST `/guest/claim` (200, one search imported): the dropped guest result was not re-added (`skipped_guest_claimed`), the survivor was restored, and the claimed copy was left alone.
    - PUT a reading position that `forward` had moved (200): the newer position was kept (`skipped_changed_by_user`).
    - Carter's own reading-position saves in the preview (4 new rows) were left alone (`untouched_made_after_apply`).
    - Rollback committed, 91 s wall. Reverse counts: bookmarks restored 1, skipped changed by user 2, deleted by user 2, parent deleted 2, untouched made after apply 1; guest results restored 5, skipped guest claimed 1; reading positions restored 13, skipped changed by user 1, untouched made after apply 4; labels reinserted 1; retrievals restored 191, reinserted 7, skipped parent deleted 4, untouched made after apply 1. Every real user's row equals the dump field for field except Carter's 4 new reading positions, the corpus tables equal the dump again, and the test search nobody touched came back with both results and both labels.
  - Sizes, `pg_database_size` in 4.0's units: restored 199 MB (208,978,447 B); after staging 397 MB (416,036,531 B); apply peak **720 MB** (755,504,819 B); after `cleanup` 523 MB (548,148,915 B); rollback peak 764 MB (801,248,947 B). After the apply `chunks` was 469 MB, with 58,071 live and 109,110 dead row versions. 4.0's As built sets them beside its projection. Cycle 2's sizes start from cycle 1's dead space and are not used.
  - Differences from step 6 as written: the Lenovo instead of Carter's Mac; PGDG Postgres and Qdrant's binary instead of `supabase start` and Docker; test accounts seeded with SQL before the apply, since no real bookmark or label is on a redirected ID; an account deleted through `auth.users`, since no API route deletes one.
  - Preview: after cycle 2's apply and before its rollback, Carter used the app against the local stores (the API and a production build of the web on the Lenovo). One defect found there is outside this item and on production too: the Library's collection filter drops each collection's section (#392).
  - Deleted on 16 Nov 2026: the dump, the user-ID list, both local databases, the Qdrant copy, both before-snapshots with their ledgers, the reports and the logs. The embedding cache keeps the 23,468 new vectors, so 4.1b's stage pays only for inputs changed since.
  - #360 (the Summa Supplement) was open at the rehearsal. If it adds removals or redirects, rerun against the new build, on a fresh dump with Carter's approval: the stage and report (new totals and user impact), the remap dry run (rows on the new redirects), and the size and apply-time measurements; record both sets of figures here (Carter, 15 Nov 2026). The rollback checks need a rerun only if #360 changes the apply, rollback or remap code.
- **As built, part 3: the rerun at the frozen build (20 Nov 2026).** #360 added three removals and a restored reply, and #391 changed the apply and rollback code (`documents.form`), so the stage, report, remap dry run and measurements were rerun, and so was cycle 1's rollback check. Carter approved a fresh `pg_dump` of production's `public` schema (the same handling: `~/rehearsal-4.1a/`, mode 700, counts only), a read-only copy of Qdrant's 54,555 points (68 s) and Qdrant 1.18.2's release binary. Built at `549ba2f` (#406's freeze). Everything was deleted on 20 Nov 2026 once #408 merged: the dumps, the user-ID list, the databases, the Qdrant copy, both before-snapshots with their ledgers, the reports and the logs.
  - Embedding: 121 inputs missed the cache, all Summa Supplement passages (about 16,600 tokens, about $0.002, stated before the call). A second stage made 0 calls.
  - Stage: 350 documents and 51,486 passages (rehearsal 51,427); 4,639 tombstones; redirects 2,092 passage, 36,677 anchor and 6,122 chapter. 2.5 min.
  - Report: 0 failing checks. Kept 47,909, retired 4,554, redirected 2,092, new 3,577 (rehearsal: 47,911, 4,552, 2,092, 3,516). User rows on retired and redirected IDs were unchanged from the rehearsal: retrievals 133 and 194, guest results 0 and 4, reading positions 4 and 12.
  - Remap dry run and apply agreed, as in cycle 1: retrievals repointed 185, merged 6, dropped 6; guest results repointed 4; reading positions rewritten 12, moved to a first chapter 1.
  - Measurements (`pg_database_size`), both runs:

    | Point | Rehearsal (16 Nov) | Rerun (20 Nov) |
    |---|---|---|
    | Restored | 199 MB | 205 MB |
    | After the staging build | 397 MB | 402 MB |
    | Apply peak | 720 MB | 721 MB |
    | After `cleanup` | 523 MB | 524 MB |
    | Apply time (wall) | 37 s | 37 s |
    | Rollback peak | 764 MB | 964 MB |
    | Rollback time (wall) | 86 s | 84 s |

  - Rollback check (cycle 1): every user table and the live documents, passages, outlines and contents equalled the pre-apply copy, except `document_works`, which kept 40 rows the publish had added on 8 documents (Cyprian's epistles and treatises, two Hippolytus volumes, Caius, Apostolic Constitutions VIII, the Summa). #408 fixed the rollback (and two related parking bugs Sol found); rerun with its code on a fresh copy, every table equalled the pre-apply copy, `document_works` included. Guest trials differed only because the API's 30-day retention had removed three October trials meanwhile.
  - Cycle 2 (user activity between apply and rollback) was not rerun, since the remap code was unchanged.

### 4.1b. Production cutover runbook

- **Type:** ops, with one small PR (the lock-file change)
- **Depends on:** 4.0 (including 2.2c's migration), 4.1a (rehearsal passed), 4.2 pre-cutover run passed, 2.2w, 2.2b (API reads `chunks_live`), 2.4a, 2.4b, 2.4d and 2.4f live, P1 to P3 merged, 3.4 included, and #360 (the Summa Supplement corrections) merged (Carter, 15 Nov 2026).
- **Goal:** Switch production from the old corpus to the cleaned one in minutes, with a tested rollback. Users see the corrected corpus (Vatican II and Trent recovered, removals shown as tombstones, correct labels); bookmarks and history keep working.
- **Current state:**
  - After 2.2b the API reads Qdrant through the alias `chunks_live`, which points at `chunks` (2.2b ops steps). The datapipeline writer takes a target collection name from 2.2w.
  - `/sources` is cached in memory for one hour (`services/api/app/routes/sources.py:18`, `_SOURCES_TTL = 3600.0`).
  - Tracked `docs/eval/` holds no chunk ids (verified); ids live only in untracked local artifacts.
  - The apply is 2.2w's single transaction. It updates changed rows in place by id, inserts new ids, retires removed ids, writes tombstones and redirects, runs 4.1a's remap, and refreshes reader outlines.
- **Changes:** Runbook. Every numbered step that writes to production is a separate Carter approval.
  1. **Staging build, T minus 2 days (no user impact).**
     - Wait for #360. The staging build does not start until #360 (the Summa Supplement corrections) has merged, so its corrections go out with the republish (Carter, 15 Nov 2026). If it adds removals or redirects after 4.1a's rehearsal, 4.1a's remap dry run and size measurements are rerun against the new build first, and both sets of figures are recorded (4.1a As built, part 2).
     - Freeze the build. A reviewed PR names the commit the P4 build is made from. It also applies the 1.2e fallback (D9, D11; this step owns it): for any council that has not passed 1.2f's gate by then, the adapter emits nothing for it, and the PR adds removal-registry entries with reason `translation-in-preparation` for all of that council's Tanner passages, with 1.2e's tombstone. No adapter change merges after this PR until the cutover is done or abandoned. The same PR applies the rejected-voice fallback: if 2.4d is not deployed, it sets `searchable = false` on every row in 3.4's ranges (Decision log "Rejected voices (C-01)").
     - Lock-file change. A reviewed PR (it may be the same one) adds to `datapipeline/PUBLISH_LOCK.json` the entry `{"collection": "all", "release": "republish-2026-10", "steps": ["stage", "apply", "rollback"], ...}` in 0.4's format. It stays until the rollback window closes (step 13), and no other entry is added in between, so no other publish can run.
     - Run `publish.py stage --collection all --release republish-2026-10`. It writes every collection into the `staging` schema and into the new Qdrant collection `chunks-republish-2026-10` (D11).
     - The new collection uses `VectorParams(size=1536, distance=COSINE, on_disk=False)` (4.0 step 5) and `HnswConfigDiff(m=16, ef_construct=64)` (as today, `qdrant_schema.py:25`). Payload indexes are keyword on `collection`, `document_id`, `genre` and `issuer`, and boolean on `searchable`. 2.2w writes `collection`, `genre`, `issuer` and `searchable` into every point's payload.
     - Every staged passage is a point, searchable or not; non-searchable ones carry `searchable = false`. The point count equals the staged passage count. Retired passages have no point.
     - Record the embedding cost. 2.2w looks each vector up in the datapipeline's content-addressed cache first and sends only misses to OpenAI (D11). The cache was empty on 29 Sep, and the first full rehearsal stage on Carter's Mac fills it (about 11 million tokens, about $1.40 at $0.13 per million; check the current price). So this stage embeds only passages whose embedding input changed after the last rehearsal build: 0 tokens if the frozen build equals the rehearsed one, and at most the same 11 million if everything changed. The count is known before any call, from the cache misses, and is recorded.
     - The release report (0.1c, produced by 2.2w from staging against live) is attached to the tracking issue. It must pass D1's similarity check and D4's removal-registry check.
  2. **T minus 1 day.** 4.2 pre-cutover run against staging. Carter gives go or no-go.
  3. **Window start (quiet hour Carter chooses).** Freeze merges to `master` that touch `services/api`, `apps/web` or `supabase/migrations`.
  4. **Backups, and the disk.** First read disk use in the Supabase dashboard (Database → Disk) and stop unless it leaves room for the apply's peak plus its write-ahead log: about 1 GB of WAL for the whole corpus on top of the database's own growth (20 Nov 2026: the disk filled at the checkpoint after the apply; 4.1b's as-built note). Then:
     - `pg_dump` of the user-owned tables (`bookmarks`, `retrievals`, `retrieval_labels`, `searches`, `guest_trials`, `guest_trial_retrievals`, `reading_progress`, `product_feedback`, `user_preferences`) to Carter's Mac, kept private.
     - `pg_dump` of the corpus tables (`documents`, `chunks`, `document_chapters`, `document_works`, the tombstone and redirect tables) as they stand before the apply. This is a last-resort backup only, not a rollback path (D11). Step 12's rollback uses the before-snapshot that 2.2w's `apply` exports itself.
     - A Qdrant snapshot of `chunks` (`POST /collections/chunks/snapshots`, about 0.4 GB of the cluster's 4 GiB disk), downloaded to Carter's Mac and then deleted from the cluster. The cluster has no backups (0.5). The old collection is not modified, so this guards only against losing the cluster; without it, recovery is re-embedding every passage from Supabase (about $1.40).
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
  11. **4.2 post-cutover run.** Run 4.2's checks on production. Remap local untracked eval artifacts with the redirects only if they will be reused.
  12. **Rollback, available until the window closes (recommended 14 days).**
      - Run `publish.py rollback --release republish-2026-10` under the same lock entry (step `rollback`). This one command is the whole rollback (D11). In one transaction it restores the previous text and facts in place from 2.2w's before-snapshot, un-retires what the apply retired, retires what the apply inserted, and calls 4.1a's `reverse` to move user rows back and re-insert merged rows from the ledger. After commit it points `chunks_live` back at `chunks`.
      - Restart the API.
      Bookmarks made after cutover on passages that exist only in the new corpus stay attached to rows that are now retired and show as unavailable; the reverse report counts them.
  13. **After the window closes (separate approvals).**
      - Delete retired rows with no user references (D3) in batches of 1,000, after asserting zero references from every table in 4.1a (`publish.py purge-retired`, after the disk check of step 4). Retired rows that users still point at stay, with their tombstones, and so do texts held for their return (ADR 0001).
      - Plain `VACUUM (analyze) chunks`, after the same disk check. The freed space is reused by later inserts; the database size figure only falls after another `VACUUM FULL`, which is a separate 4.0-style decision.
      - Delete the Qdrant collection `chunks` (`publish.py drop-old-collection`). Irreversible; Carter approves it separately.
      - Delete the private ledger and the step 4 dumps (on the Lenovo for this republish).
      - A reviewed lock-file change removes the `republish-2026-10` entry, leaving `approved_applies` empty.
      - Measure the database size again.
- **Acceptance checks:**
  - Cutover log in the tracking issue records every step's time, counts before and after, the public ledger counts, smoke results and the 4.2 result.
  - Retrieval, bookmark, label and guest-result counts after equal counts before, minus merged rows in the ledger.
  - Point count in `chunks-republish-2026-10` equals the staged passage count (all passages, searchable or not; this republish stages every collection, so no points are copied, see 2.2w stage step 7), and the count with `searchable = false` equals the staged non-searchable count.
  - Zero documents with `chunk_count IS NULL` after step 7.
  - No error-level API log lines about missing chunks in the hour after cutover (filter `@logger:app.rag` in Railway).
- **Production safety:** Everything before step 6 is invisible to users (the `staging` schema, and a Qdrant collection not behind the alias). There is no release column and no second copy in `chunks`. Step 6 is one transaction, so users see the old corpus or the new one, never a mix. Step 8 is one alias switch with an inverse. The old Qdrant collection and every retired row stay until step 13, so rollback is always possible inside the window. Deletions happen only after an assertion of zero references, because every chunk foreign key cascades.
- **Needs Carter:**
  - Approve the build-freeze PR (step 1), including any council that falls back to a gap tombstone.
  - Approve the lock-file PR (step 1) and the one that removes the entry (step 13).
  - Approve steps 1 (staging build and embedding spend), 4, 6, 7 (only if an outline refresh has to be run by hand), 8, 9, 10 (the smoke checks and the `cleanup` that drops the staging tables in production), 12 (if used) and each part of 13.
  - Answered 4 Nov 2026: the rollback window is 14 days.
  - Choose the window. Give go or no-go at step 2.
  - Found by 4.1a's rehearsal (16 Nov 2026): step 10's check that "Nostra Aetate 4 and Gaudium et Spes open in full in the reader" cannot pass. All 16 Vatican II documents are excerpt-only (LEV text), on production today and in the build, so their reader answers 403 and links to vatican.va. Replace it with: Nostra Aetate §4 shows its whole paragraph in a search result and links to vatican.va, and the Council of Trent's Bull of Indiction (new) opens in full in the reader? Recommended: yes. Answered 20 Nov 2026: yes; both passed on production.
- **As built, step 1, the freeze (16 Nov 2026).** One PR does both of step 1's reviewed changes:
  - The build commit is that PR's merge commit into `master`. From that merge until the cutover is done or abandoned, no adapter change merges (the 5.2 rights thread holds its PRs; #381 stays unmerged).
  - The 1.2e fallback adds nothing. All eleven councils, Constantinople IV to Lateran V, have passed 1.2f's gate: every frozen text in `datapipeline/ocr/texts/` for them (`schroeder-*`, the four Deferrari council extracts and Giles's Lyons I) records `pass`. `HELD` in `ingest/councils_schroeder.py` stays empty, and no `translation-in-preparation` entry is added, so the IDs reserved for it (`rm-8001` upward) are unused.
  - The rejected-voice fallback is not needed: 2.4d is live, so 3.4's ranges stay searchable and carry their rejected-voice label (Decision log "Rejected voices (C-01)").
  - `datapipeline/PUBLISH_LOCK.json` gains the entry `{"collection": "all", "release": "republish-2026-10", "steps": ["stage", "apply", "rollback"]}` (#406).
- **As built, steps 1 and 2 (20 Nov 2026).**
  - #408 (merged before the stage) makes a rollback restore the snapshot's `document_works` exactly; #411 (merged before the window) gives the near-duplicate filter a line per collection for the republish's fingerprints (RF-1's as-built note). Both are needed at the cutover; neither changes the build.
  - Staging build (Carter approved it in the session): `publish.py stage --collection all --release republish-2026-10` from master `99600f5`, whose datapipeline equals `7ba49e9` (the freeze plus #408). 20:17 to 20:28 UTC, 11 min. 350 documents, 51,486 passages, 4,639 tombstones, redirects as in 4.1a's rerun. Every vector from the cache: $0.
  - Checks: `chunks-republish-2026-10` holds 51,486 points, 48 not searchable, equal to staging; green; vectors in memory; HNSW 16/64; keyword indexes on `collection`, `document_id`, `genre` and `issuer`, boolean on `searchable`. `chunks_live` still targets `chunks`. Database 210 → 408 MB.
  - Release report: publish checks pass (D1 similarity, D4 removal registry, 0 unexplained), figures equal to 4.1a's rerun except guest results on redirected IDs, 3 (the API's 30-day retention removed one trial). Recorded on #192.
  - Step 2, 4.2's pre-cutover run: every check passed (4.2's as-built note; `docs/eval/2026-11-20-republish-checks.md`).
  - Traffic for the window (production `search_costs`, 30 days to 20 Nov 2026): 22 searches, the latest on 14 Nov; none at all between 15:00 and 21:00 UTC. Proposed window: a weekday at 16:00 UTC (11:00 Eastern), when Carter can approve each step.
  - Step 10's Vatican II check: replaced as recommended (Carter, 20 Nov 2026).
- **As built, steps 3 to 11 (20 Nov 2026, the cutover).** Carter gave the go and approved running each step in the session; the cutover log with every time and count is on #192.
  - Before: Railway and Vercel production both on `8ecf6f8` (#410, #411). Counts: retrievals 4,296, bookmarks 25, labels 3, guest results 69, reading positions 35. Backups: the user and corpus tables (`pg_dump`) and the Qdrant `chunks` snapshot (459 MB, downloaded and deleted from the cluster), in an owner-only folder on the Lenovo in place of Carter's Mac, as for the rehearsals.
  - Apply (step 6) 23:34:30 to 23:37:40 UTC, 3 min 10 s wall. Remap: retrievals repointed 185, merged 6, dropped 6; guest results repointed 3; reading positions rewritten 12, first chapter 1. Switch (step 8) 12 s later. Outlines (step 7): 0 missing.
  - **Outage, 23:38:48 to 23:44:29 UTC (5 min 41 s).** The database disk filled at the checkpoint after the apply (`No space left on device` writing WAL); crash recovery failed on the same disk three more times until Supabase expanded it. Nothing was lost: the apply had committed, and every count, the publish row, the tombstones and redirects, and a full read of all passages checked out afterwards. Step 2's check (4.0) had relied on the 30 Oct reading; step 4 now measures the disk first.
  - Step 9: the API's pool reconnected by itself; the restart only clears the 1-hour `/sources` cache.
  - Step 10: a live guest search showed Nostra Aetate §4 in full with its LEV notice and source link; Trent's Bull of Indiction opened in full in the reader; one production search per collection, 10 of 10. `cleanup` dropped staging: 729 → 531 MB. Carter's signed-in checks recorded on #192.
  - Step 11: 4.2's post-cutover run (4.2's as-built note). The rollback window closes on 4 Dec 2026 (step 13).
- **Prepared, step 13 (21 Nov 2026).** Tooling built and tested; nothing run on production but dry runs. The checklist of every part, in order, is on #192.
  - `publish.py purge-retired --release republish-2026-10` (`datapipeline/retention.py`). A dry run by default, inside a read-only transaction. It reads the foreign keys into `chunks` and `documents` from the database, so a later table such as Studies is covered. A retired row stays when any row outside the corpus tables points at it (cascade or set null), when a corpus row's `superseded_by` names it, when it sits in the chapter a reading position names, or, for a document, when one of its passages stays. A live run (`--execute`) deletes in batches of 1,000, each its own transaction with `lock_timeout` under the publish lock; each batch locks its rows and checks references again, so a row someone points at after the plan stays. `publish.py rollback` now refuses once the window has closed, before touching the database, since step 13 may have deleted rows its snapshot cannot fully restore and the old collection. The purge refuses inside any publish's rollback window (14 days from `applied_at`, so from 4 Dec 2026 23:34 UTC), while a publish holds staging, and without an `all` lock entry with the `apply` step.
  - Deleting a passage fires 0037's trigger, which clears its document's `chunk_count`; each batch refreshes the outlines of the documents it touched.
  - The API's notice for an old reader link to a removed passage read the passage row (its anchor or chapter key). Each batch now copies both into the passage's tombstone snapshot before the delete, and `app/corpus_lifecycle.py` falls back to them when the row is gone. Without this, 1,083 removed passages in 117 documents that stay would have lost their notice: an old link would open the document's first chapter (anchor) or return 404 (chapter). The API change must deploy before the purge runs.
  - Held texts stay. ADR 0001 keeps documents held for permission "in the database, retired, never deleted", so they can return unchanged and their notice keeps its papalencyclicals.net link, which the API reads from the document row. The purge therefore keeps every retired row whose tombstone reason is `awaiting-permission` or `translation-in-preparation` (decided by Carter, 21 Nov 2026; recorded on #192).
  - Disk. The dry run estimates the WAL from the heap and toast pages each batch touches (one full-page image each, before compression; every value stored out of line counts) plus the outline rewrites per batch and the tombstone rewrites, and the `VACUUM` after it from the table's total size. A live run needs `--disk-free-gb`, read from the dashboard just before, of at least twice the estimate plus 1 GB.
  - Dry run on production, 21 Nov 2026: retired passages 6,646, of which 5,362 would be deleted and 1,284 stay (841 held for permission, 364 held for a translation, 98 in saved searches holding 133 results, 16 in chapters a reading position names). Retired documents 85, of which 18 would be deleted and 67 stay (51 held for permission, 1 for a translation, 4 with a reading position, the rest because some of their passages stay). 7 batches. WAL, estimated generously: 207 MB for the purge (needs 1.4 GB free) and 472 MB for the `VACUUM` (needs 1.9 GB free).
  - Early close (Carter, 21 Nov 2026; Decision log "Republish rollback window closed early"): the window ends on 21 Nov, not 4 Dec. Both commands take `--close-window-early "<who, when>"`, which lifts only the release's own window refusal and opens every output with an `EARLY CLOSE:` line; `rollback` refuses once the previous collection is gone. Step 13 runs in this order: delete `chunks` (after checking its snapshot on the Lenovo), purge, vacuum, then #415. The backups and the ledger stay on the Lenovo until 4 Dec as disaster recovery. Then only the files holding user data go (`user-tables.dump`, `user_remap_ledger.jsonl`), with the Qdrant snapshot; the corpus dump and the before-snapshot's corpus files are kept permanently with the archive of the purged rows in `~/corpus-archive/` (Carter, 22 Nov 2026; Decision log "Permanent archive of what step 13 deletes"). None of them is ever committed or published: some texts were removed for rights reasons.
  - `publish.py drop-old-collection --release republish-2026-10` deletes the collection the switch left (`previous_qdrant_collection`, `chunks`, 54,555 points), refusing while any alias or publish uses it or inside the window; `--execute` also needs `--confirm chunks`.
  - The ledger and backups are on the Lenovo, not Carter's Mac: the before-snapshot with `user_remap_ledger.jsonl` (24 MB, `datapipeline/releases/snapshots/republish-2026-10-before/` in the main checkout) and `~/cutover-republish-2026-10/` (463 MB: the user and corpus `pg_dump`s, the Qdrant `chunks` snapshot, the run logs).
- **Out of scope:** Collection renames (5.1b). Any new source. Any retrieval tuning (Retrieval follow-ups).

### 4.2. Accuracy checks on staging and production

- **Type:** ops
- **Depends on:** 4.1a, and the staging build from 4.1b step 1. Until 30 Oct 2026 it also compared judge scores against a judged baseline from 0.3; Carter dropped 0.3, so this item checks accuracy only and makes no judge calls (Decision log "Baseline eval (0.3)").
- **Goal:** Show, before and after cutover, that removed texts no longer appear, that recovered and fixed texts now do, and that every collection still answers. This is what Carter's go or no-go rests on.
- **Current state:** Production pipeline is `hyde_cohere_luna_seats10t80_ftsminmatch` (CLAUDE.md §5; #233 changed keyword matching on 13 Nov 2026). `services/api/scripts/run_eval_suite.py` runs the pipeline in process, not through an API server; its judge is not used here.
- **Changes:** Runbook, a check script and a report file.
  1. **Check script.** Add `services/api/scripts/republish_checks.py`. For each check below it runs a question through the production pipeline in process (as `run_eval_suite.py` does) and asserts over the returned passages; the database-only checks are single SELECTs. The questions are written fresh in neutral wording, never taken from users' stored searches, and Carter reviews the list in the PR. It also runs one ordinary question per collection and asserts it returns results with no error.
  2. **Pre-cutover run, on staging.** Run the script with `CORPUS_READ_SCHEMA=staging` and `QDRANT_READ_COLLECTION` set (2.2w). That is why 2.2w lets an in-process run use the override while the deployed API refuses to start with it. Its corpus reads go to the `staging` schema and its vector reads go to the new Qdrant collection (`QDRANT_READ_COLLECTION=chunks-<release>`, from 2.2b). It reads production data and writes nothing.
  3. **Targeted checks:**
     - Zero passages from Origen, Novatian, Tatian, Arnobius, Alexander of Lycopolis, the Apostolic Constitutions outside Book VIII's 85 canons, the six forged Ignatius letters, or Tertullian's excluded works.
     - Nostra Aetate 4, a Trent decree and the Vatican I constitutions retrievable by a direct question.
     - CCC 2267 returns the 2018 text.
     - "Canon 112" returns canon 112 alone.
     - Susanna (Daniel 13) and Bel and the Dragon (Daniel 14) findable.
     - No result shorter than 20 characters.
     - No Vatican II result starting with "Cf." or "See".
     - No result with `searchable = false`.
     - Added for the 6 Oct review findings: "What is an indulgence?" returns CCC 1471's definition (C-03); Psalm 51's first passage opens with its title (C-11); keyword search alone returns canon 1055, the passage holding CCC 2267 and a John 3 passage for those citations (C-16, 2.2c), and after cutover `search_vector IS DISTINCT FROM` 2.2c's expression counts 0; the explanation of a condemned proposition in Exsurge Domine, of a Summa objection and of a passage of Caecilius's speech says the position is rejected (C-01, 2.4d); no Summa result cites an article its text does not belong to (C-07); no card credits Firmilian's letter or Novatian's to Cyprian (C-02); a reference-style question per collection also succeeds through vector retrieval (the synthesis's open item, at no separate cost).
  4. **Post-cutover run.** The same script against production, after 4.1b step 10.
  5. **Report.** Add `docs/eval/2026-MM-DD-republish-checks.md`: each check's result on staging and on production, and the cost of the runs.
- **Acceptance checks:**
  - All targeted assertions pass, and every collection answers its ordinary question.
  - The report contains no user data.
- **Production safety:** The pre-cutover run reads the `staging` schema and a Qdrant collection no user reads, and writes nothing. The post-cutover run makes ordinary searches through the product path with an operator account and is rate limited like any user. It does not persist to other users' history.
- **Needs Carter:** Go or no-go after the pre-cutover run. Approve the spend (pipeline calls only, no judge; the report states the amount). Review the check questions.
- **As built, step 1 (15 Nov 2026):** the check script; steps 2 to 5 wait for 4.1b step 1 and Carter's go-ahead.
  - `services/api/scripts/republish_checks.py`, 115 checks: 59 searches through the production pipeline (`runner.run` with `_PRODUCTION_PIPELINE`, in process, persisting nothing; three also ask the explanation model about the passage they target), 49 database checks (one read-only SELECT each), 3 keyword searches (`retrieve_fts` alone, which is SQL), and 4 aggregates over every result the run's searches return. `--list` prints each check with its question and expected outcome and reads no setting. Without `--spend` only the free checks run; the searches are reported `NOT RUN`. `--json` writes each check's outcome, its question and the citations it returned, and nothing else.
  - The checks follow what was built, not the original plan: 3.1's removals as merged in #386 (the Hippolytus Refutation and undatable works, the Panegyric to Origen and the Phoenix besides the spec's list; To His Wife and On the Apparel of Women kept), 3.3's 45 passages and Ubi Lutetiam, 1.3d's 51 held documents and 84 held paragraphs, 1.5b's six withheld canons and nine labelled ones, 1.7's prologues and q. 71 and 72, 1.8d's Robertson text, 3.4's 15 ranges (passage counts per document, with the Summa's objections), 2.4f's scanned-text label, 3.2's labels as #388 registered them (each document's shown author and certainty, the labels and notes of works inside documents and that those works hold their passages, Diognetus's note, the 15 preservation notes, Quasten's dates and genres, and rule C's apostle lists), and a check for each other Phase 1 item and the contents trees (#253, #254). A test holds every expected label to `works.json`. The Muratorian Fragment's `notes` is an empty string, not NULL, which is what keeps Caius's preservation note off it in the API. Removal checks read their targets from `datapipeline/registry/removals.json` (open document and passage entries), so a check whose item has not merged fails as an error rather than passing on nothing. A search that degraded or failed is an error too, so an empty result never passes a removal check. Assertions judge each passage as the search returned it (text, citation, label, role), with the corpus adding only the card's facts and whether it is visible, and an explanation check gives the model the card production explains, a Summa objection with its stitched answer.
  - "Canon 112 returns canon 112 alone" is checked as: canon 112 first, no card of it holding canon 113, labelled unofficial English. "No result with `searchable = false`" is an aggregate over the run's results, read back from the corpus by ID, and also refuses a retired passage or one the corpus does not hold. "A reference-style question per collection also succeeds through vector retrieval" records the vector path's candidates during the same run (no extra call) and asks for the named passage among them and among the results. C-07 is checked twice: on every stored Summa passage, and on the citations the run's Summa results return.
  - The run prints and records the pipeline's cost (its `CostTracker`, plus the explanations') and, for 4.0 step 5, the median and slowest search and vector-search times. Production's `search_costs` put a one-collection search at $0.0062 on average and $0.0074 at most (30 days to 15 Nov 2026), so a paid run is about $0.35 to $0.45 and the staging and production runs together under $1. On staging, the script refuses to spend while `QDRANT_READ_COLLECTION` is still `chunks` or `chunks_live`.
  - Baseline, 15 Nov 2026, the free checks against production (read-only): every database and keyword check fails as expected, since the cleaned corpus is not published, except 3.1's kept works, which pass (rerun after #386 and #388 merged). The same free checks against the master build with #386 and #388 staged into a local Postgres by `reader_writer.write_staged_document` (migrated through 0045): all 52 pass.
- **As built, steps 2 and 5 (20 Nov 2026).** The pre-cutover run against production's staged publish (`CORPUS_READ_SCHEMA=staging`, `QDRANT_READ_COLLECTION=chunks-republish-2026-10`, in process on the Lenovo, read-only), approved by Carter: 113 PASS, 1 FAIL, 1 ERROR, then 4 PASS on a rerun of those two and the two slowest searches, so every one of the 115 checks has passed. The failure was the check's own wording (the explanation marked Exsurge Domine's proposition 31 condemned but did not name Leo X; the rerun's did); the error was the listwise reranker's malformed output, which the check counts as degraded. Cost $0.36 plus $0.02. Vector search on the new collection: median 0.27 s, slowest 0.54 s, so no paid Qdrant tier is needed (4.0 step 5). The run also recorded every similarity the near-duplicate filter computed: 98 drops in 36 of 59 searches at 0.9, which led to #411 (RF-1's as-built note); replayed with #411's lines, 32 in 14. A comparison run of the same searches against the live corpus was blocked by the agent's permission check and not run; the post-cutover run measures the filter live. The report is `docs/eval/2026-11-20-republish-checks.md`. Step 4, the post-cutover run on production (20 to 21 Nov 2026): 113 PASS and 2 FAIL, both passing on reruns. Summa q.2 a.3 objection 1 was missing from one draw of the five results; Exsurge §31's explanation named Leo X in one rerun of two. Both are run-to-run variation; the Leo X wording check is stricter than the spec and is a follow-up. The near-duplicate filter dropped 33 candidates in 15 searches live with #411. Cost $0.35 plus about $0.03 for the reruns.
- **Out of scope:** Measuring or tuning ranking quality. That belongs in Retrieval follow-ups, which may run a judged comparison on the republished corpus if one is wanted.

---

### 4.3. Held texts in their place in the reader and the Library (#394)

- **Type:** three PRs, merged in order: (a) the held-texts registry and its check; (b) the stage writes it and the report shows it; (c) the API and web. Then one ops step, a 2.2w publish of the collections that hold texts. Design written 15 Nov 2026; nothing is built until Carter says the Phase 4 cutover is done.
- **Depends on:** 4.1b done, including step 13: the lock entry `republish-2026-10` stays alone in `PUBLISH_LOCK.json` until the rollback window closes (4.1b step 1), so this item's publish cannot run before then. 4.1b step 1's build freeze also stops PRs (a) and (b) from merging until the cutover is done or abandoned. PR (c) is safe to merge earlier, since it renders nothing until the publish writes the list, but it waits too so the three are reviewed together. 2.2w, 2.4a and 2.4b live. Before any Phase 5 item (issue #394).
- **Publish order (Carter, 21 Nov 2026).** 4.4 publishes first, staged from master `bb1e541` (#419's merge), which holds 4.4's data and none of this item's. This item publishes second, staged from master after that (#417 merged as `353fb37`), once 4.4's rollback window has closed and its lock entry has been removed. Live then carries 4.4's `card_version`, `card_notes` and `card_translator`, so this publish's report must show `document.held_texts` and no other metadata key changing (the report's "other metadata" line).
- **Goal:** A reader browsing a council, or a papal document published in part, sees the whole document in order. Every held text appears in its place with a reader-facing heading, marked "Not on TheoCorpus at present", and a link that opens the text online in a new tab. Its text is never shown. The Library row says how many texts are read online. Search does not change.
- **Terms.** A **held text** is one text of a document (a sentence, a decree, a session's acts, a run of paragraphs) that the republish retires with reason `translation-in-preparation` in the `councils` collection (the gap register, G3 to G13, and pieces 1.2e's sources do not print) or `awaiting-permission` at passage scope (ADR 0001's partly published papal documents). One held text stands for one or more retired passages. Passages retired under any other reason (`rule-g-editorial`, `debris`, the rules A to C) are not held texts and are never listed: they were never the document's text, or were removed for good.
- **Current state (15 Nov 2026, master `4495a91`, read-only queries against production the same day):**
  - Production is still the old corpus: 0 tombstones, 0 retired passages, and no document has `metadata.held_text_url`. Everything below about retired rows is what the republish will produce.
  - The removal registry (`datapipeline/registry/removals.json`) holds 430 open passage entries in scope: 346 `translation-in-preparation` in 8 councils and 84 `awaiting-permission` in 10 encyclicals and Exsurge Domine. 400 of them name a passage that is live today; the other 30 name pieces 1.10c cut, which no publish carried, so they will never have a tombstone. Closed entries (`closed_by`, for example Lyons I's ten G4 passages, now redirected to Giles's text) are not held (`registry.open_removals`).

    | Document | Open entries (live today) | Held texts, grouped as below |
    |---|---|---|
    | Basel–Ferrara–Florence | 123 (97) | 28 |
    | Constance | 109 (107) | 17 |
    | Fifth Lateran | 59 (44) | 17 |
    | Vienne | 43 (39) | 2 |
    | Constantinople IV | 8 (7) | 1 |
    | Vatican I | 2 (2) | 2 |
    | Constantinople II, Lyons II | 1 (1) each | 1 each |
    | Ten encyclicals (Vix Pervenit, Cum Summi, Salutis Nostrae, Traditi Humilitati, Singulari Nos, Nostis et Nobiscum, Qui Nuper, Nullis Certe Verbis, Quanto Conficiamur Moerore, Levate) | 76 (72) | 28 runs of consecutive paragraphs |
    | Exsurge Domine | 8 (4) | the bull's closing, in 1 to 8 entries (the pieces lie inside `closing`; settled by PR (a)) |

    Grouping for the councils is by the entry's `detail` with the "(gap Gn)" tag and ", a piece the 1.10c build cut" removed, splitting a detail that names two texts ("X; Y"). 21 Florence passages straddle two texts that way; none elsewhere. About 70 council entries and about 30 papal ones in all.
  - Each entry has `document_id`, `anchor`, `passage_id`, `detail` and the tombstone sentence. `detail` is internal wording ("Session 15, the 58 articles of Wyclif condemned with the sentence (gap G6)") and is not a reader heading. No field records a passage's place in the document. Tanner anchors (`council-of-constance/sec-17/23-2`) give the Tanner section but not reliable order inside it.
  - The built Constance (`ingest/councils_schroeder.py`, checked by building it on the Lenovo) has 13 passages in four chapters, `council-of-constance/session-8`, `-13`, `-15` and `-43`, labelled "Session 8" and so on, no contents tree, and `metadata.held_text_url` = `https://www.papalencyclicals.net/councils/ecum16.htm`. Every council built by 1.2c to 1.2e, and every partly published papal document (`ingest/papal_printings.py:264`), carries `held_text_url`.
  - The reader outline is `document_chapters` (0037), built by `refresh_document_outline` from non-retired passages only; the contents tree is `document_contents` (0040), whose every node must open a chapter that exists (`_contents_tree`, `routes/documents.py:364`). Neither can hold an entry with no passages behind it.
  - `TocResponse` is `document`, `chapters`, `contents` (`app/models/documents.py:105`). The web reads it once per document through `lib/reader-cache.ts` for both the overview and the reader.
  - `/sources` returns each document's `metadata` whole (`routes/sources.py:139`); the Library's `DocRow` (`SourcesPage.tsx`) shows the title, attribution and translation, and links an excerpt-only document to its source in a new tab with an `ExternalLink` mark (#265).
  - 2.2w's stage writes `staging.documents.metadata` from `Document.metadata` (`reader_writer.write_staged_document`); the apply upserts documents by ID; the before-snapshot exports `documents` rows; the release report diffs document facts (2.3). The Qdrant payload and the embedding input carry no document metadata (`search_writer.build_point`, `build_embedding_input`).
- **Where the ordered list comes from.** Three sources were compared:

  | Source | Order | Heading | Durable | Verdict |
  |---|---|---|---|---|
  | Tombstone `snapshot` (`corpus_tombstones`) | None: it stores `collection, title, author, reference, chapter_label`, no position, chapter key or anchor. Adding them changes 2.2w's stage output, the build 4.1a rehearsed | None: one row per old passage, and `public_reason` is the same sentence for all | In production, but only after the apply; pieces 1.10c cut never get one, and no dry run can check it | Not used |
  | 2.2w's before-snapshot (`releases/snapshots/<release>-before/`) | Yes: live positions before the apply | None | No: local, gitignored, on one machine, per release, deleted when the window closes (4.1b step 13) | Not used. Its only job is rollback |
  | Removal registry (`removals.json`) | Partly: anchors give the Tanner section | No: `detail` is internal | Yes: in git, reviewed, and the list D4 already makes complete | The source, through a new file |

  **Recommended and specified:** the removal registry is the source of truth for *which* passages are held, and a new reviewed file groups them into texts and gives each its heading and place. The list is written once per document by hand-checked generation, and the build checks it against the registry on every run, so it can never drift from what retires.
- **Changes:**
  - **PR (a): the held-texts registry.**
    - New `datapipeline/registry/held_texts.json`, one entry per held text, in each document's reading order:

      ```json
      {"id": "ht-0042", "document_id": "bfcce97d-…", "label": "Session 8",
       "heading": "Sentence against John Wyclif, and the condemnation of his books",
       "after_anchor": "council-of-constance/session-8/wyclif-articles/from-p35",
       "removal_ids": ["rm-…", "rm-…"], "url": null,
       "added_by": "4.3", "added_on": "2026-…"}
      ```

      `label` is the place in the document's own numbering ("Session 8", "Florence, session 11", "Paragraphs 10–19"); `heading` is what the text is, in plain words, sentence case, from Tanner's table of contents as the gap register quotes it (council headings are not under copyright); `after_anchor` is the published passage it follows in the build, or null when it comes before every published passage. Entries with the same `after_anchor` keep their file order. `url` is null, meaning the document's link (below; Carter, 15 Nov 2026). IDs `ht-NNNN` are never reused, as for removals.
    - Papal documents: one entry per run of consecutive held paragraphs, labelled "Paragraph 9" or "Paragraphs 10–19" (the preamble as "The address"), with the heading "Not in the public-domain printing". Exsurge Domine's held pieces of the closing are one entry, "The rest of the bull, after the 41 propositions".
    - A generator, `datapipeline/scripts/held_texts.py --draft`, proposes entries from the open removals (grouping as under Current state, placement from session or paragraph numbers against the build), and writes a draft for review; the headings are then edited by hand. It never overwrites an existing entry.
    - `registry/__init__.py` gains `held_texts` on `WorkRegistry` and a check, run by `registry.validate` and by the build (dry runs included), that fails when: an open in-scope removal (as defined under Terms) belongs to no entry or to two (a straddling passage belongs to the first text it holds); an entry names a closed, out-of-scope or other-document removal; an `after_anchor` is not a passage the build emits for that document; or the entries' `after_anchor` positions go backwards. Closing a removal (a translation found) therefore fails the build until its held entry is removed or shrunk in the same PR.
  - **PR (b): the stage writes it.**
    - The councils, encyclicals and papal-documents adapters do nothing new. The stage (2.2w step 4) adds to each document's `metadata` a `held_texts` list, built from the registry: `{key, label, heading, after_anchor, after_chapter_key, url}`, with `after_chapter_key` filled from the built passage and `url` from the entry or null. Documents with no entry get no key. No table, column or migration is added: `documents.metadata` is already staged, applied, snapshotted for rollback and restored by it, so 2.2w's code changes only where it builds the row.
    - The release report adds a section `document.held_texts`: per document, the entries added, removed or changed since live. Its D1, D4, point and payload sections must show nothing else for this publish (below).
  - **PR (c): API and web.**
    - API models (`app/models/documents.py`): `HeldText {key, label, heading, after_anchor: Optional[str], after_chapter_key: Optional[str], url: Optional[str]}`. `TocResponse` gains `held_texts: list[HeldText] = []`. `DocumentResponse` and `SourceDocument` gain `held_count: int = 0`. `metadata.held_texts` is removed from every `metadata` the API returns (`/documents/{id}`, `/toc`, `/sources`), so the list is sent once, by `/toc`.
    - `/toc`: reads `metadata.held_texts`, resolves each `url` (null gives the document's `metadata.held_text_url`, else `metadata.url`, the rule `corpus_lifecycle` uses for `read_elsewhere_url`; an entry with no link at all is left out and logged), and checks it as `_contents_tree` checks a tree: every `after_chapter_key` is a chapter in `chapters`, in non-decreasing order. A stale list is dropped whole, with a warning, and the reader shows chapters only. The excerpt-only 403 and the removed-document 410 come first, unchanged.
    - `/sources`: `held_count` is `jsonb_array_length(metadata->'held_texts')`, or 0, in the cached query. It changes only at a publish, after which the API is restarted as in 4.1b step 9.
    - `/documents/{id}/reader` does not change.
    - Web types in `lib/api.ts` (`TocResponse.held_texts?`, `held_count?`), all optional.
    - New pure module `lib/held-texts.ts`: `placeHeldTexts(chapters, held)` returns the overview's entries in reading order (each held text after the chapter holding its `after_anchor`, the null ones first), and `heldAfter(anchor, held)` returns those to render after one passage. Unit-tested.
    - `DocumentOverview.tsx`, chapter grid: each held entry is a grid cell in its place, the same size as a chapter cell, with a dashed `border-brand-muted/40` border and no ordinal (ordinals still count chapters). It reads "<label> · <heading>" in `text-brand-muted`, and under it "Not on TheoCorpus at present · Read online" in `text-brand-accent` with the `ExternalLink` mark and the screen-reader text "(opens in a new tab)", as #265's Library rows do. The whole cell is an `<a target="_blank" rel="noopener noreferrer">`. The summary line reads "13 passages · 4 sessions · 17 texts read online". The chapter search also matches held headings. A document with a contents tree (none today has held texts) shows the held entries as a flat list under the tree, "Read online", until a tree-aware design is needed.
    - `ChapterSection.tsx`, reading flow: after a passage, the held texts whose `after_anchor` is that passage render as one muted, bordered line each, "<label>: <heading> — not on TheoCorpus at present. Read online", linking out in a new tab; the null ones render before the first chapter's first passage. Never any text.
    - `SourcesPage.tsx` `DocRow`: when `held_count > 0`, a muted "· 17 texts read online" after the translation. The row still opens the reader.
    - Guests and signed-in readers render the same components (`isGuest` changes nothing here); the guest reader's access rule (`require_document_access`) is unchanged.
  - **Search.** Nothing changes (Carter, 15 Nov 2026): held texts have no points and no `chunks` rows that are not retired, and the publish below writes the same passages and vectors.
  - **Docs.** CLAUDE.md §4's `documents` notes gain one line on `metadata.held_texts`, and §10's `/toc` and `/sources` rows name the new fields.
- **Publishing it (ops step, after 4.1b step 13).**
  1. A reviewed lock-file PR adds one `approved_applies` entry per collection the list touches, `councils`, `encyclicals` and `papal-documents`, each with release `held-texts-2026-12` and steps `stage`, `apply` and `rollback`, in 0.4's format. A follow-up PR removes them when this publish's window closes.
  2. `publish.py stage` for those collections. Every passage's embedding input is unchanged, so every vector comes from the cache or the aliased collection (2.2w stage step 6): no OpenAI call, cost $0. Other collections' points are copied. The new Qdrant collection is the only extra one on the cluster, since step 13 has deleted the old `chunks`.
  3. `publish.py report`. It must show, for the three collections: zero new, retired or redirected IDs, zero text changes, zero payload changes, `embed_sha256` equal for every point, and `document.held_texts` listing each document's entries. Anything else stops the publish.
  4. `apply`, `switch`, restart the API (for `/sources`), smoke checks below, `cleanup`. Rollback is 2.2w's `rollback`, which restores `metadata` from the before-snapshot.
  Users see the held entries at the apply; search sees an identical corpus behind a new collection name.
- **Acceptance checks:**
  - `datapipeline/tests/test_held_texts.py`: every open in-scope removal is in exactly one entry; a closed removal, an out-of-scope reason, an unknown `after_anchor` and backwards order each fail; a straddling Florence passage counts once; the 1.10c pieces need an entry like any other (their text is part of the held text). `test_stage_writes_held_texts_into_metadata`, and `test_held_texts_publish_changes_no_passage_or_point` (a stage whose only change is the list reports no ID, text, payload or `embed_sha256` change).
  - `services/api/tests/test_held_texts.py` (real Postgres, as `test_corpus_lifecycle.py`): `/toc` returns the held entries with their resolved links and no text; a null `url` falls back to `held_text_url`, then `url`; a list whose `after_chapter_key` is missing or out of order is dropped with a warning; `metadata` in `/documents/{id}`, `/toc` and `/sources` has no `held_texts`; `/sources` `held_count` is right and is 0 for a document without the key; an excerpt-only document still answers 403; a database without the key serves today's responses (golden JSON).
  - Web: `held-texts.test.ts` for placement; `DocumentOverview.test.tsx`, a held entry renders in its place as a link with `target="_blank"`, no ordinal, and the summary count, for a guest and a signed-in reader; `ChapterSection.test.tsx`, the held line after its passage; `SourcesPage.test.tsx`, the count on the row. `npm run lint` (0 errors), `npm test`, `npm run build`.
  - After the publish, on production: Constance's overview lists 13 published passages in 4 sessions and its 17 held texts in session order, Sessions 8, 15 and 21's sentences among them, each opening papalencyclicals.net's Constance page in a new tab and showing none of its text; every other document in the table above does the same; each Library row shows its count; 4.2's searches give the same results as before the publish, and no held text is returned or explained.
  - The PR (c) description has screenshots at 375 px and desktop, dark and light, of Constance's overview, a chapter with a held line, and its Library row.
- **Production safety:** PRs (a) and (b) change only the datapipeline. PR (c)'s fields are optional and empty until the publish, so it renders today's pages; its one other change, dropping `held_texts` from returned `metadata`, drops a key no document has yet. The publish touches `documents.metadata` only, and the report proves it. Rollback is 2.2w's.
- **Costs.** About 70 council headings to write and check (the bulk of the work, mostly Florence's 28 and Lateran V's 17), about 30 papal ones that follow a pattern, three small PRs, and one publish: no embedding spend, one Qdrant collection copy (minutes), and about 15 KB of `metadata` in all.
- **Needs Carter:**
  - Answered 15 Nov 2026: held texts stay out of search, unchanged (Decision log "Held texts in the reader (4.3)"). The alternatives, a search card with no text or searchable excerpts, are not built.
  - Answered 15 Nov 2026: every held text links to its document's online page, the link its tombstone already gives (`metadata.held_text_url`, else `metadata.url`). No per-text links: each registry entry's `url` is null, and the field stays only so a later decision needs no format change.
  - The approvals the publish needs: the lock-file PR, the stage, the apply and the switch (section A).
- **Out of scope:** Whole documents held for permission (ADR 0001's 51 retired encyclicals): they leave the Library, and listing them as "read online" rows is a separate decision. The canon-law and Church Fathers `translation-in-preparation` passages (amended canons with no English, rule E): they have no read-online link under 2.4a's rule. Any change to search, tombstones or the reader's 410 notice.
- **As built (21 Nov 2026, one PR for (a), (b) and (c); the publish waits for 4.1b step 13).**
  - `registry/held_texts.json` holds 94 entries: 69 in eight councils (Constance 18, Basel–Ferrara–Florence 30, Lateran V 14, Vienne 2, Vatican I 2, Constantinople II, Constantinople IV and Lyons II 1 each), 23 runs in the ten encyclicals, and 2 in Exsurge Domine. `scripts/held_texts.py --draft` proposed them; the headings and places were then written by hand against the build.
  - Constance has 18, not 17: Session 8's opening decree, which introduces Wyclif's 45 articles, comes before the published articles, and the session's later condemnations after them. A held text that is no longer held is closed (`closed_by`, `closed_on`), never deleted, so its ID is never reused.
  - Differences from the estimates above. Lateran V has 14, not 17: three of its details name a passage straddling two texts ("Sessions 3 and 4", "the bulls on peace and on reform", "the exhortation to peace and the preamble of Supernae dispositionis arbitrio"), and each belongs to the first text it holds. The encyclicals have 23 runs, not 28: the address joins the run of paragraphs after it ("The address and paragraphs 1–7"). Exsurge Domine has 2, its opening and its closing: its preamble is held as well as the closing.
  - A straddling passage belongs to the text it starts in, in reading order, not the one its detail names first (11 Florence passages name the later text first). Two texts lie wholly inside a passage another text owns (Florence's session 10, inside the end of session 9; Basel's session 8, inside session 7's passage; neither detail names them, which review found), so their entries name that passage in `shared_removal_ids`, which the check allows only for a passage another entry owns. Basel's session 18 opens the passage the details file under session 19, and owns it.
  - Where a bull is published as an extract (Laetentur caeli, Exultate Deo, Cantate Domino, Pastor aeternus gregem), its held parts are one entry, placed where the bull begins and headed "…: the parts not printed here", though they lie on both sides of the extract: every entry links to the same page, so one line serves the reader better than three.
  - Production, read-only on 21 Nov 2026: 374 of the 430 held removals have a tombstone, and every one of those 374 is in the list; the other 56 never had a live row (44 pieces 1.10c cut, and 12 others: four Vienne pieces, the paragraph 1 of four encyclicals, and four pieces of Exsurge Domine). The estimate above was 400 and 30. Every `after_anchor` is a current passage on production in the list's order; no document has `held_texts`; every listed document has a link (Exsurge Domine through `metadata.url`).
  - `/toc`'s check is the tree's, at chapter level, plus each `after_anchor` being a visible passage of its chapter. `held_count` is computed from the cached row's `metadata`, not in SQL. Held lines after a chapter's last passage come before the chapter's credit line.
  - Guests have no Library page; the guest reader shows the overview and reading flow as signed-in readers see them.

### 4.4. One system for the notes under an opened passage (#407)

- **Type:** two PRs and one publish: (a) web and API, (b) the data (registry, adapters, the check), then a 2.2w publish of the collections whose notes change. Designed 20 Nov 2026 from the republish preview; nothing is built until Carter says the Phase 4 cutover is done.
- **Depends on:** 4.1b done. PR (a) may deploy any time after the cutover, because it falls back to today's lines until the data arrives. PR (b) waits for the build freeze to lift, and its publish waits for the `republish-2026-10` lock entry to be removed when the rollback window closes (4.1b step 13), as 4.3's does. 4.3's and 4.4's publishes run one after the other, never overlapping: each stages from a reviewed commit that holds only its own unpublished data change, and the second stages only after the first's rollback window has closed and its lock entry has been removed (a later apply would block the first's rollback, and the first's report gate refuses changes it did not review).
- **Publish order (Carter, 21 Nov 2026).** 4.4 publishes first, staged from master `bb1e541`, the merge of PR (b) (#419), which holds 4.4's data and none of 4.3's (4.3's #417 merged after it, as `353fb37`). 4.3 publishes second, staged from master after that, once 4.4's rollback window has closed and its lock entry has been removed (see Depends on).
- **Goal:** Under an opened passage, each fact is said once, in the slot that matches what it is, so a caution about the text is never mistaken for a credit. Everything above the text (the header, the role label, the text and its footnotes) stays as it is, apart from the Supplement's header date.
- **Current state (measured on the republish build, 20 Nov 2026, 350 documents and 51,486 passages; the inventory of every line, with its counts, is in #407):**
  - `components/common/PassageFacts.tsx` renders every line under the text in one style (12px, muted, a paragraph each), in this order: language, kind and form (`formatKind`), translation ("Translation: …"), the 2.4f text labels (scanned edition, unofficial English), `factNotes` (the work's or document's `attribution_note`, `notes`, the passage's `note`), the superseded note, then the credit (`source_credit`, or the excerpt-only document's required notice from `app/reader_access.py`).
  - The translator lives in two fields: 301 documents in `translation` and their source in `source_credit` ("Sourced via CCEL.org"), 49 documents in `source_credit` alone ("Translated by H. J. Schroeder (1937)"), as the Decision log row "Source credits for document facts (2.3)" set. A council translated by two people names both on every passage.
  - 145 passages carry one of 16 `note` wordings, 86 of which name a translator the credit already names; 31 documents and 2 works carry one of 27 `notes` wordings; 13 documents and 7 works carry an `attribution_note`.
  - Repeats and conflicts found: the Exsurge Domine and Constance notes restate the rejected-voice label and the translator; the withheld-canons note sits on all 1,793 canon cards; the Bible's translation appears in the badge and again under the text; the Catechism's edition appears as "Translation: United States edition (1997)" and in the USCCB notice; canon 112 shows "Translation: Vatican English" over "Unofficial English translation (L'Osservatore Romano)"; the Supplement's header says "1265 to 1274" over "Compiled after Aquinas's death from his earlier writings."; "Written by Hegemonius" restates the header.
  - `registry.validate` requires a `source_credit` for every live document with facts (`registry/__init__.py`), and the reader shows it on the document overview (`DocumentOverview.tsx`) and under each chapter (`ChapterSection.tsx`).
  - CCEL's copyright page (checked 20 Nov 2026) asks for permission to republish and says nothing about where a credit goes. The USCCB requires its notice with every excerpt (§4, the Decision log row "Source credits").
- **The system (decided by Carter on 20 Nov 2026):**
  - At most three slots under the text, always in this order, each left out when it has nothing to say. Three slots is not three lines: slot 1 holds one sentence for each caution that applies, uncapped. On the build, 46,844 passages would carry no caution, 4,640 one and 2 two before the Supplement note moves to the header; 311 carry one after it.
    1. **Read with care** (TheoCorpus speaking): a caution about this passage, one sentence each, opened by its kind, `INCOMPLETE` (abridged, a summary, an extract, part left untranslated), `WORDING` (another chronicler's version, an unofficial English, a passage in another language), `AUTHORSHIP` (an attribution doubt the header cannot hold, a later addition by another hand) or `AUTHORITY` (not enacted, not adopted by the Church, superseded).
    2. **About this text** (the record): one line joined with " · ": kind and form, how the text survives, this passage's translator, and "scanned" for a text from page images.
    3. **Required notice** (the rights holder speaking): the USCCB and Vatican notices only, verbatim.
  - Rules: (1) nothing under the text repeats the header, the role label or another line; (2) only what is true of this passage, or of the unit a reader cites (a Summa article, a canon, a paragraph), and a document-wide fact goes to the document's overview; (3) the translator is named once, for this passage; (4) where the digital text came from ("Sourced via CCEL.org", "Public domain. Sourced via eBible.org", "Text: papalencyclicals.net", "Text: Wikisource") never shows on the result card: it stays in `source_credit`, where the reader's overview and chapter view already show it, and it is listed on the Sources page; (5) required notices stay verbatim and last, and travel with a copied passage; (6) each kind of note has one fixed wording; (7) the build checks it.
  - Look (`4.4-card-notes-look.html`, variant A): slot 1 is the brand primary text colour at the record line's size (12px) on a quiet panel (black at 22% in Slate Night, white at 42% in Ivory Vault; radius 6px, padding 8px 12px), with no left bar and never the gold accent, since the Encyclicals tint is gold; its kind word is 9.5px, bold, capitals, letter-spaced. Slot 2 is today's muted 12px line. Slot 3 is 11px fine print in `brand-muted` under a hairline, at full opacity: since #410 that grey reads at WCAG's 4.5:1 on every collection tint in both themes. The panel colours become tokens in both theme blocks of `globals.css` (§9).
  - "Text from a scanned edition" (approved on 12 Nov 2026) becomes "scanned" in slot 2.
  - The Supplement and its appendix show "Thomas Aquinas · compiled after 1274" in the header (their works' `date_display`), and their attribution note goes.
- **Changes:**
  - **PR (a), web and API.**
    - `PassageFacts` becomes the three slots. The API sends one optional `card` object per passage, `{cautions: [{kind, text, link?}], record: [..], notice}`, built in `rag/steps/document_facts.py` from the stored data below. Its absence means a response from before 4.4's data and renders today's lines and credit (the 2.4b fallback rule); its presence selects the new rendering even when every list is empty (Psalm 23 shows nothing under its text). `lib/search-stream.ts`, history restore and bookmarks carry it unchanged.
    - `notice` is only a required notice (`app/reader_access.py`'s USCCB or Vatican line); the card and the copied passage no longer show the stored `source_credit`, which the reader keeps showing.
    - The unofficial-English caution (`WORDING`) takes its link from 2.4f's `official_latin_url`, as today.
    - Overview notes show on the reader overview for a document the reader opens, and on the document's Library row (`SourcesPage.tsx`) for an excerpt-only one, whose overview answers 403 (the Code of Canon Law).
    - A Sources page, `/about/sources` and `/guest/about/sources` (the Library already uses `/sources`): each site the corpus takes text from (CCEL, eBible.org, vatican.va, papalencyclicals.net, Wikisource, the Internet Archive's scans, the USCCB), what is taken from it, on what basis, with the documents listed. It reads `rights_inventory.json` through the API, or a generated JSON.
    - The copied passage keeps its required notice and drops the "Sourced via" credit.
  - **PR (b), data.** Each note is stored with its kind and place, in passage and document `metadata` keys as 2.4f did (no migration): a passage's `note_kind`; a document's notes, and its works' (which have no metadata of their own), as `documents.metadata.card_notes` entries of `{kind, text, show: card | record | overview, work_key?}` (a `record` entry has no kind), resolved per passage in the facts lookup. `translation` and `source_credit` are left as 2.3 set them (`registry.validate` requires the credit, and the reader's overview shows both, so a translator in both would repeat there). Where the credit is the only place a document names its translator (the 49 documents whose `translation` is empty, such as Exsurge Domine's "Translated by Roy J. Deferrari (1957)"), `works.json` gains a `card_translator` ("Roy J. Deferrari (1957)"), written once from the credit line and reviewed in PR (b), and `document_facts.py` carries it to `documents.metadata.card_translator`. A document with two translators names each passage's own in a passage `translator` key. The record line takes the passage's `translator`, else `card_translator`, else `translation`, and leaves the translator out when the passage carries 2.4f's `text_status = unofficial_english`, whose caution already names it (canon 112 names L'Osservatore Romano once). A `card_notes` entry with `show: record` (how the text survives, such as "Preserved in Cyril of Jerusalem's Catechetical Lectures") joins the record line after the kind and form. Every document the publish writes carries `metadata.card_version = 1`, empty notes or not, and the API sends the `card` object only for a passage whose document has it, so a migrated document with nothing to say (Psalm 23) is told apart from one not yet migrated. The 43 note wordings are rewritten to the fixed templates without the translator, author or document. Rejected-voice notes that restate the label go. The Supplement's work date changes.
  - **Check** (`checks/card_notes.py`, run by every build and dry run): refuses a caution without a kind; a note naming the passage's translator, author or document title; the same passage note on every passage of a document (it belongs on the document as a `card_notes` entry, which may still show on every card, as the Pseudo-Justin caution does); a document whose `translation` is empty without a `card_translator` or passage `translator` keys.
- **Acceptance checks:**
  - The cards captured on the preview (#407) render as `4.4-card-notes-look.html` shows, in both themes and at phone width, and canon 112's caution links to the official Latin.
  - The check passes on the build, and the counts of passages with zero, one and two cautions are recorded against the ones above.
  - Every document the reader opens shows its overview notes and source line on its overview, an excerpt-only document shows its overview notes on its Library row, and `/about/sources` lists every site in `rights_inventory.json`.
  - A copied Catechism passage still ends with the USCCB notice, and a copied CCEL passage no longer ends with "Sourced via CCEL.org".
  - The fine print measures at least 4.5:1 on every collection tint in both themes.
- **Production safety:** PR (a) deploys before the data and changes nothing until it arrives. PR (b)'s publish is a normal 2.2w publish under its own lock entry, after the republish's is removed; it changes notes and metadata only, so passage IDs, embedding inputs and Qdrant vectors stay the same (notes are not embedded).
- **Needs Carter:** Answered 20 Nov 2026: the three slots and seven rules; the Sources page; "scanned" in slot 2; document-wide facts on the overview; the Supplement's header date; the look (variant A, the caution text at the record line's size, no left bar); timing after the cutover. Open: the fixed wording of each template, reviewed in PR (b). Answered 20 Nov 2026: the muted grey, which measured 2.1:1 at worst on the card tints in Slate Night and 3.3:1 in Ivory Vault, is raised app-wide to the minimum that passes (#410); the record line and the fine print use it.
- **Out of scope:** The header, the role label and the footnotes. Rewording rights holders' notices. The reader's own chapter view.
- **As built, PR (a) (21 Nov 2026).** The facts the code showed differently:
  - API. `app/card_notes.py` builds the card; `rag/steps/document_facts.py` reads only the card's keys of either `metadata` (`->>` for the string keys, so a decoded string is never mistaken for JSON text). `card_translator` stored as `""` names no translator; absent, the record falls back to the stored `translation`. The notice is `reader_access.source_credit` for every document a 4.4 publish wrote, not only excerpt-only ones, so a vatican.va text carries the LEV line. A caution link is `{label, href}` (the Latin) or `{label, document_id}` (the current text of a superseded document, which the client turns into its own reader path). Cautions are ordered by kind, then stored order. `/documents/{id}` and `/sources` send `overview_notes`: the document's own entries, whatever their place, never a work's. A document's entry may list `except_work_keys`, works whose passages it does not cover (Caius's preservation note leaves out the Muratorian Fragment, which 3.2 gave no such note).
  - Kind and form. The record names a papal document's kind when its collection badge does not (Evangelii Gaudium: "Apostolic exhortation" under Encyclicals), and with its form ("Apostolic constitution, issued as a bull"); a kind the badge names shows only with a form, and a Father's writer genre never.
  - Web. `lib/card-notes.ts` decodes the card and the overview notes; `CardNotes` and `OverviewNotes` are in `components/common/PassageFacts.tsx`. The panel and the hairline are `--color-brand-caution-panel` and `--color-brand-hairline`, in both theme blocks.
  - Sources page. `apps/web/src/lib/source-sites.json` is generated by `datapipeline/scripts/source_sites.py` (`--check`, and `tests/test_source_sites.py` fails when it is stale). It lists the 350 published documents under seven sites; planned rows and held documents are left out, so Project Gutenberg (planned rows only) is not listed. Each extract an `also_from` edition supplies is listed under its site. The basis is each row's status, the inventory's `excerpt_basis` where one is recorded (the Holy See's, 23 Vatican works), and for the Catechism a link to the USCCB's guidelines, whose word limit counts a whole work (read on usccb.org, 21 Nov 2026).
  - Screenshots: `docs/screenshots/2026-11-21-4.4/`, before (master) and after (this PR with PR (b)'s build), from guest searches against local copies of the corpus.
- **As built, PR (b) (21 Nov 2026).** The facts the code showed differently:
  - Where it runs. `card_notes.apply` and `checks/card_notes.py` run in `publication.prepare`, after the passage registry's overrides (where the councils' notes live), so every dry run and stage stores and checks the notes. Each note's rewrite is one table in `datapipeline/card_notes.py`, keyed by today's exact wording (`PASSAGE_NOTES` for passages, `FACT_NOTES` for a document's or work's stored `attribution_note` and `notes`, `DOCUMENT_NOTES` for a document note no stored fact holds). An unknown wording stops the build. The stored facts keep 2.3's and 3.2's wording; the card and the overview read the table's.
  - `card_translator` is written for every published document (not only the 49), from the credit line or the translation (`card_notes.card_translator`), so every translator a card names is reviewed data. `""` is only for the Bible (the badge) and the Catechism (the notice); a document with neither stops the generator before it writes. A council passage from a second scanned edition names its own translator (`SCAN_TRANSLATORS`, by `metadata.scan_id`, 38 passages).
  - Moved to the passage they are true of: the Canonical Epistle's later-addition note (canon XI); "This printing cuts the paragraph short with “&c.”" on Salutis Nostrae §2 and §8; "This printing gives only part of this paragraph." on Quanto Conficiamur Moerore §8, Qui Nuper §3 and Nullis Certe Verbis §3, 5, 7 and 8 (Levate, both of whose paragraphs are partial, says it on the document). The extract note leaves the passages of an encyclical whose own note says which extract is given.
  - A document note a work clears (3.2's Muratorian Fragment, `notes = ""`) lists that work in `except_work_keys`, which the API honours (PR (a)).
  - Counts on the build (51,486 passages): 51,226 with no caution, 257 with one, 3 with two (Salutis Nostrae §2's two pieces and §8: the French intermediary and the cut). Against the spec's 311: Exsurge Domine's 41 move to its overview, the "attribution is doubtful" notes go (the header's tag says it), canon XI's note is on one canon rather than eleven. Document notes: 11 on the card, 16 on the record line, 22 on the overview.

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
    - Papal: `encyclical`, `apostolic-exhortation`, `apostolic-letter`, `apostolic-constitution`, `motu-proprio`, `letter`.
    - A papal document's form (`bull`, `brief`, or none) is not a genre since 9 Nov 2026: it lives in `documents.form` (0044, lookup `corpus_forms`, values from `PAPAL_FORMS` in the same module). Whether form gets a filter of its own is the follow-up that carries it to live data.
    - Roman Curia: `declaration`, `instruction`, `doctrinal-note`, `note`, `response`, `norms`, `considerations`, `commentary`.
    - Catechisms and law: `catechism`, `compendium`, `code`, `law`.
    - Writers: `treatise`, `manual`, `sermon`, `commentary`, `poem`, `rule`.
- **Changes:**
  1. `services/api/app/rag/constants.py`. Add `GENRES_BY_COLLECTION: dict[str, frozenset[str]]` and `ISSUERS_BY_COLLECTION`. The API cannot import the datapipeline, so the genre values are a copy of 2.1's module with a CI test (`test_api_genres_match_registry_module`) that reads both files and fails on any difference.
     - The papal collections use the papal values plus `other`.
     - Roman Curia uses the Roman Curia values plus `compendium` (the social doctrine Compendium, 5.3b), `letter` and `other`.
     - Issuers are slugs in `documents.issuer`, and filters use only the slug; `issuer_label` is what users see (D11). Roman Curia issuers are the institution: `ddf` for both CDF and DDF (per the source memo; the name printed at publication goes in `issuer_label`), `pbc`, `pcjp`. Papal issuers are the pope, such as `pope-leo-xiii` with label "Pope Leo XIII". The filter shows `issuer_label` without its "Pope " prefix, under a heading that says Pope (Carter, 21 Nov 2026).
  2. New module `services/api/app/rag/collection_scope.py` with a frozen `CollectionScope(collection, genres, issuers)`. It has `to_qdrant_filter()` and `to_sql()` so retrieval does not hand-build filters. Semantics, per the plan's rule "filters exclude only explicit values":
     - A selection is stored as the set of values the user turned off.
     - Qdrant gets `must_not` on `genre` in the excluded set.
     - SQL gets `(d.genre IS NULL OR d.genre <> ALL($excluded))`. The explicit NULL branch is required, because `NOT (NULL = ANY(...))` is NULL and would silently drop documents without a genre.
     - "All" means no clause.
  3. `search_plan.py`. `SearchPlan` gains `scopes: tuple[CollectionScope, ...]`. `resolve_search_plan(collections, quota, scope_filters=None)` validates genres and issuers against the constants and raises `SearchPlanError("invalid_genre" | "invalid_issuer")`, which routes translate to 422 like the other codes (CLAUDE.md §18). Focused search still requires exactly one collection; a genre subset does not count as a collection.
  4. Request models in `routes/search.py` and `routes/guest_search.py`. Add optional `filters.scopes: {[collection]: {genres?: string[], issuers?: string[]}}`; absent means all. Additive to `/v1/search` and `/v1/search/guest`.
  5. `retrieve_vector.py` and `retrieve_fts.py`. Take a `CollectionScope` instead of a bare collection string and use its filters.
  6. `pipeline.py`. Persist the scope selection into `searches.filters` next to `collections` (`_saved_search_filters`, `services/api/app/rag/pipeline.py:161-178`), and into `guest_trials.filters`. Remember CLAUDE.md §4 (no `json.dumps` on jsonb from the API). `routes/search.py` returns it on restore.
  7. Qdrant check (read-only). Confirm that the collection behind `chunks_live` has keyword indexes on `genre` and `issuer` (created at 4.1b step 1) and that every papal point carries `genre`. If an index is missing, creating it is a live step for Carter to approve; it does not change points.
  8. Web PR.
     - `apps/web/src/lib/collections.ts` mirrors the genre and issuer vocabularies with display labels.
     - `lib/search-draft.ts` gains per-collection genre and issuer selections and events `genre-toggled` and `issuer-toggled`, unit-tested there (it owns draft transition rules, CLAUDE.md §18).
     - New `components/search/GenreFilter.tsx` is the panel (Decision log "Genre and issuer filter look (5.1a)"): a selected collection that has genres or issuers shows a caret in its `CollectionToggles` pill, behind a thin divider, as its name slides left (the pill keeps its width; unselecting slides it back). The caret opens a panel that grows out of it with a pointer, the same on phone and laptop: a Kind list (only where the collection has more than one genre) and an issuer list (headed Pope in the papal collections), all ticked to start, an "Only" button per row and an "All" button per list in the collection's colour. A press outside closes it; no footer, no count badge, and only opening animates. Labels: genres singular as the cards print them, popes without "Pope".
     - `lib/api.ts` sends `filters.scopes`.
     - The restore path in `lib/search-experience/useSearchPageExperience.ts:292-307` reads it back.
     - Guest and authenticated pages share the component through `isGuest` (CLAUDE.md §11).
  9. Docs. CLAUDE.md §5 (scopes), §10 (request shape), §14 if the stream changes (it should not), §18 (genre does not affect focused eligibility).
- **Acceptance checks:**
  - API tests. A document with NULL genre is returned under every genre selection (SQL and Qdrant). A request without `scopes` produces byte-identical Qdrant and SQL filters to today's. An invalid genre gives 422 with code `invalid_genre`. A restore returns the stored selection.
  - Web tests. Draft reducer toggling one, several and all; restore round trip.
  - `npm run lint` zero errors; no new warnings in touched files.
  - A read-only query after the P4 apply shows zero NULL genres in the papal collections, recorded in the PR.
  - PR includes screenshots of the filter (the caret and its open panel) in both themes.
- **Production safety:** The API change is additive and optional. Old web clients send no `scopes` and get today's behavior. The web PR deploys after the API PR, so it never sends a field the API rejects. The Qdrant indexes already exist from P4. Rollback is a revert of either PR.
- **Needs Carter:** Answered 21 Nov 2026: the labels and the look (step 8, and the Decision log). No Qdrant index was missing (step 7), so none was created.
- **Out of scope:** Saving genre selections in `user_preferences` (needs a migration; a follow-up if wanted). Genre-specific HyDE prompts (Retrieval follow-ups). Per-genre result guarantees (5.1c decided against them).

- **As built, API PR (21 Nov 2026).** The facts the code showed differently:
  - The request names what to search, not what to leave out: `filters.scopes: {[collection]: {genres?: string[], issuers?: string[]}}` lists the values searched, absent meaning all. `resolve_scopes` turns it into the excluded set `CollectionScope` holds (`excluded_genres`, `excluded_issuers`). An empty list, a value outside the vocabulary, or a genre or issuer for a collection that has none (or an unknown key) is refused (`invalid_genre`, `invalid_issuer`), whichever collections are selected; a valid scope for a collection the search does not include is ignored; a selection of every value adds no filter. The two new codes answer 422 with `detail: {code, message}`; the older codes keep their string detail.
  - Only the three papal collections (`encyclicals`, `apostolic-exhortations`, `papal-documents`) can be narrowed until 5.3a adds Roman Curia. Their issuers are one list, `PAPAL_ISSUERS` (21 popes, in order of pontificate), not one per collection; `test_papal_issuers_cover_the_registry` fails when `works.json` gives a papal collection a pope or genre the API does not know. `test_api_genres_match_registry_module` compares the four genre tuples and `other`.
  - `retrieve_vector.run` and `retrieve_fts.run` keep `collections` and take `scopes` (by collection); `_search_vector` and `_search_fts` take a `CollectionScope`. The scope's SQL binds from `$4`. Without scopes, the Qdrant filter and the SQL equal master's, checked against master's SQL in `tests/fixtures/fts_sql_before_scopes.json`.
  - `searches.filters.scopes` and `guest_trials.filters.scopes` hold the request's form, and only when a collection is narrowed. A guest claim copies it with the rest of the filters.
  - Step 7, read-only (21 Nov 2026): `chunks_live` → `chunks-republish-2026-10` has keyword indexes on `genre` (17,661 points) and `issuer` (13,001); every point of the three papal collections has both (5,237, 2,968 and 487 points). In Supabase, the live documents of those collections have no NULL genre or issuer (79, 30 and 14 documents; the 52 retired encyclicals held for permission have none and are not searched).
- **As built, web PR (22 Nov 2026).** The facts the code showed differently:
  - The values each collection offers come from `apps/web/src/lib/collection-scopes.json`, generated from `datapipeline/registry/works.json` by `collection-scopes.test.ts` (a file snapshot: `npx vitest run -u collection-scopes` rewrites it, and CI fails when it is stale), not from a hand-kept mirror in `collections.ts`. Only genres and popes with published documents are listed. The file holds the documents per genre and pope, so each list follows the other's ticks (Carter, 22 Nov 2026): choosing a pope narrows the Kind list to that pope's kinds, counting only his documents, and choosing kinds narrows the Pope list the same way; the last ticked value shown cannot be unticked. Lists are ordered: genres by count with Other last, popes by their first document (the order of pontificates). Apostolic Exhortations has one genre, so its panel has no Kind list.
  - `lib/search-draft.ts` holds `excluded` (per selected collection, the values turned off) and derives `scopes` for the request; events `genre-toggled`, `issuer-toggled`, `scope-only` and `scope-all`. One value of each list always stays ticked, deselecting a collection drops its filter, New Search clears every selection (`scopes-cleared`; collections, quota and translation stay, as before), and the selections are not saved as defaults.
  - `filters.scopes` is sent only when a collection is narrowed, and the runtime freezes it with the rest of the request, so a Retry after a failed search sends it again. A restored search (`savedSearchRequest`) and a guest's last search (sessionStorage) keep the selection in their request, as they keep its collections; neither re-seeds the draft, which restore never has.
  - The caret and the panel's All and Only buttons are drawn in 35% of the collection's colour mixed into the theme's text colour, which measures at least 4.5:1 on their tints for the three papal collections in both themes.
  - The caret lives in `CollectionToggles.tsx` (`CollectionToggles.module.css`); the panel is `GenreFilter.tsx`, portalled to the body and placed above the caret (below it when a long question has pushed the caret near the top), so the same panel serves phone and laptop. While a search runs, its request is frozen: the panel closes and the carets do nothing. "Only" shows on hover where there is a pointer and always on touch screens.
  - Screenshots: `docs/screenshots/2026-11-22-5.1a/`.

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
| Theology & Spirituality (label changed from "Theologians and spiritual writers" by Carter, 22 Nov 2026, in 5.1b.2) | `theologians` | `medieval` |

A fresh key `papal` is proposed rather than reusing `papal-documents`. Reusing it would make one stored value mean two different sets during the transition, and old clients could not be told apart from new ones.

**The four PRs, each deployable alone:**

1. 5.1b.1 API expand. Accept new keys. Old keys keep today's meaning. Results come back labeled in the vocabulary the request used.
2. 5.1b.2 Web switch. Offer only new keys and translate any old key it reads.
3. 5.1b.3 Data rewrite. Migration, datapipeline keys, a 2.2w publish that writes the new keys to `documents` and the Qdrant payload, and a script for the keys stored in user rows, run as one approved ops step.
4. 5.1b.4 Contract. Remove old keys from the API and the database constraint.

**Every hard-coded key location, re-verified on master `024d6ee` (22 Nov 2026; first verified on `5475c49`, 29 Sep).** Line numbers are master's before 5.1b.1. "PR" says which 5.1b PR changes it; "done in .1" marks what 5.1b.1 changed. Rows marked *new* were missing from the 29 Sep table.

| Location | What is there | PR |
|---|---|---|
| `services/api/app/rag/constants.py:1-12, 41-49` | `VALID_COLLECTIONS`, all 10 keys; `_PAPAL_COLLECTIONS`, the collections 5.1a's genre and issuer filters accept | .1 adds `CANONICAL_COLLECTIONS`, `LEGACY_COLLECTIONS` and `papal` to the filters (done in .1); .4 removes |
| `services/api/app/rag/collection_scope.py` (*new*, 5.1a) | the Qdrant filter and SQL read one stored value, the requested key | .1 adds `reads()`: which stored values a key reads (done in .1); .4 drops the old-key branch |
| `services/api/app/rag/steps/rrf.py` (*new*) | fuses each scope's paths separately | .1 keeps each passage under one key, which matters only while .3's rewrite has reached one store and not the other (done in .1) |
| `services/api/app/rag/steps/retrieve_fts.py:25, 83, 91` (*new*) | `d.collection = $1` in the three FTS queries | .1 makes it the scope's condition (done in .1) |
| `services/api/app/rag/qdrant_client.py` (*new*) | `searchable_indexed` reads the read collection's payload indexes | .1 adds `genre_indexed`, so an old papal key reads the new value only where `genre` is indexed (done in .1) |
| `services/api/app/rag/search_plan.py:9, 58, 173, 184` | validation against `VALID_COLLECTIONS` | .1 drops an old key beside its new key and logs `legacy_collection_key` (done in .1) |
| `services/api/app/rag/pipeline.py:289` | drops keys not in `VALID_COLLECTIONS` | no change; the set now holds both vocabularies |
| `services/api/app/models/preferences.py:28-36, 68-80` | preference validators reject unknown keys, including on GET (`routes/preferences.py:60-66` builds `PreferencesResponse` from stored rows, so one stored unknown key is a 500) | .1 tolerant read (`PreferencesResponse.from_stored`, also for a PUT's merge; done in .1), .4 |
| `services/api/app/routes/preferences.py:15-21` | `_DEFAULT_PREFERENCES` has `encyclicals`, `canon-law` (moved to `models/preferences.DEFAULT_COLLECTIONS` in .1) | .2 (after .1) |
| `services/api/app/routes/search.py:486` | restore filters `collection_outcomes` to `VALID_COLLECTIONS`; restored passages carry the stored `d.collection` | .1 labels each restored passage with the saved request's key that reads its stored value whole (`collection_scope.requested_label`; done in .1). After .3 an old papal key's passage (stored `papal`, read by genre) takes the saved old key its genre belongs to, or keeps `papal` if its facts are unavailable and several old papal keys were saved |
| `services/api/app/rag/steps/hyde_s25.py:151-251` | `_COLLECTION_HYDE_PROMPTS` for `encyclicals`, `medieval`, `canon-law`, `apostolic-exhortations`, `papal-documents` | .1 adds `church-law` and `theologians`; `papal` writes one passage per papal kind its genre filter leaves on, in the old keys' prompts (done in .1); .4 renames the papal prompts to kinds and removes the rest |
| `services/api/app/rag/steps/hyde_s25.py:315-325` | `_COLLECTION_MAX_TOKENS` (`encyclicals` 400, `medieval` 350, `canon-law` 350; unknown keys fall back to 300 at line 465) | .1 adds `church-law`, `theologians` 350 (done in .1), .4 |
| `services/api/app/rag/dedup.py:35-45` (*new*) | `_PREFIXED_THRESHOLDS`, the near-duplicate line per collection | .1 adds the new keys (done in .1); .3 measures `papal` on the merged collection |
| `services/api/app/rag/dedup.py:93-95` | `_CHAPTER_KEYED_COLLECTIONS` includes `canon-law` | .1 adds `church-law` (done in .1), .4 removes |
| `services/api/app/footnotes.py:33` (*new*) | `_SCRIPTURE_NOTE_COLLECTIONS` has `medieval` | .1 adds `theologians` (done in .1), .4 |
| `services/api/app/reader_access.py:34` (*new*) | `_COLLECTION_SOURCE_URLS` has `canon-law` | .1 adds `church-law` (done in .1), .4 |
| `services/api/app/corpus_lifecycle.py:63` (*new*) | Latin link for an amended canon, `collection == "canon-law"` | .1 accepts `church-law` too (done in .1), .4 |
| `services/api/app/card_notes.py:121` (*new*) | `_BADGE_KINDS` keyed by the stored collection, so a card does not repeat the kind its badge names | .3 (the `papal` badge names no kind, so the merged collection needs no entry; remove the old ones when the values are rewritten) |
| `services/api/app/routes/evaluate.py:51-174` | numbered collection descriptions with hard-coded counts ("131 papal encyclicals", "30 post-synodal", "14 historical") and weighting hints naming old keys | .2 (switch prompt to new keys once web shows new keys), counts updated in every addition PR |
| `services/api/scripts/run_eval_suite.py:41` (`COLLECTIONS`) | eval defaults include `encyclicals` | .4 |
| `services/api/scripts/republish_checks.py:886-914` and its cases (*new*) | republish check questions and expectations keyed by old collection | .3 (the publish that writes the new values runs them) |
| `services/api/app/config.py:138` and `tests/test_config_validation.py:29-45` | `cohere_concurrency` 10 and a test that it covers `len(VALID_COLLECTIONS)` | .1 changes the test to count scopes and HyDE calls per search (done in .1: 10 scopes, 13 calls) |
| `datapipeline/config.py:63-67, 142` | `PER_COLLECTION_OVERLAP` (`medieval` 200, `encyclicals` 250, `canon-law` 300); `overlap_for` | .3 (done: new keys added for new documents; registered ones keep their source's line, so nothing re-embeds) |
| `datapipeline/publication.py:45-` | `SOURCE_ADAPTERS` keyed by collection | .3 (done: eight published keys; `SOURCE_BUILDS` keeps the ten sources) |
| `datapipeline/stages/parse.py:9-24` | V5 `BUILDERS` keyed by collection | .3 (left by source: V5 builds and enriches by source) |
| `datapipeline/enrichment/prompts/classification.py:185-221`, `enrichment/prompts/generation/__init__.py:6-20` | V5 enrichment guidance keyed by collection | .3 (left by source, as above) |
| `datapipeline/scripts/vendor_sources.py`, `scripts/audit_sources.py:133-` | vendor and audit registries keyed by source directory | leave the source directory names; keys only if they double as collection keys (they do not after .3) |
| `datapipeline/ingest/*.py` (`papal_common.py`, which the three papal wrappers call with their `COLLECTION`, e.g. `encyclicals.py:9`; `canon_law.py:541, 605`; `medieval.py:129, 142`) | collection string used both as the emitted collection and as a `document_id()` input | .3 changes only the emitted collection; ids come from the 2.1 registry (done: `publication._published_as` relabels, adapters unchanged) |
| `datapipeline/registry/works.json` (`collection` on every work), `papal_genres.py`, `document_facts.py`, `rights_inventory.py`, `ingest/canon_overrides.py`, `checks/*.py` and their JSON baselines, `scripts/language_removals.py`, `scripts/medieval_registry.py`, `scripts/source_lock.py` (*new*) | old keys as registry values, check scopes and baselines | .3 (decided: they stay, as source names; checks judge sources) |
| `datapipeline/README.md` adapter table, `datapipeline/SOURCES.md` | docs | .3 (done) |
| `apps/web/src/lib/collections.ts:10-19` | `COLLECTIONS` with keys, labels, colors | .2 |
| `apps/web/src/lib/collection-scopes.ts:40`, `collection-scopes.json` (*new*, 5.1a) | `SCOPED_COLLECTIONS` (the three papal keys) and the genres and issuers each offers, generated from `works.json` by its test | .2 offers `papal`; the JSON follows `works.json` in .3 |
| `apps/web/src/lib/source-sites.json` (*new*) | `collection` per source site | .3 (generated) |
| `apps/web/src/app/globals.css:49-58` | `--color-collection-*` tokens | .2 adds, .4 removes |
| `apps/web/src/lib/search-draft.ts:48` | guest default collections include `encyclicals` | .2 |
| `apps/web/src/components/search/LoadingAnimation.tsx:24-34` | `PALETTE` keyed by collection with short codes | .2 |
| `apps/web/src/components/search/QuotaControl.tsx:9-10, 126` and `QuotaControl.module.css:59` | contrast sets for `apostolic-exhortations`, `canon-law`, `papal-documents`, and `.papalNumeral` | .2 |
| `apps/web/src/components/search/ChunkCard.tsx:85, 234` | `canon-law` citation shortening; author shown for `church-fathers` or `encyclicals` | .2 |
| `apps/web/src/components/reader/DocumentOverview.tsx:47`, `ReaderChrome.tsx:74` | `canon-law` reader wording | .2 |
| `apps/web/src/components/about/AboutPage.tsx:3-24` | descriptions keyed by collection | .2 (new keys, interim text), full rewrite in 5.7 |
| `apps/web/src/components/landing/LandingPage.tsx:14`, `app/page.tsx:6` (*new*) | copy naming "encyclicals, and papal documents"; the page description names encyclicals | .2 (wording only if the label changes the sense) |
| `apps/web/src/components/sources/SourcesPage.tsx:450, 482` | groups and filters by `COLLECTIONS` keys | .2 (group by translated key) |
| `user_preferences.default_collections` rows and column default (live default verified above; set by `supabase/migrations/0010_chunks_metadata.sql:23`) | stored keys | .3 |
| `searches.filters` (`collections` array, `collection_outcomes` object keys and, since 5.1a, `scopes` keys) | stored keys | .3 |
| `guest_trials.filters` | stored keys | .3 |
| `documents.collection` and `documents_collection_check` | stored keys and constraint | .3 widens (0046, built), .4 narrows |
| Qdrant payload field `collection` on every point | stored keys | .3 |
| Test fixtures (files naming an old key on `024d6ee`: API 22, datapipeline 51, web 22) | literal keys | each PR updates what it breaks |
| CLAUDE.md §15 ("10 collections"), §18 (chapter-keyed list), `apps/web/AGENTS.md` | docs | each PR (.1 updated §5, §15, §18) |

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
     - Add prompts for `papal` (merge the three current prompts, `hyde_s25.py:163-249`, into one covering encyclicals, exhortations, letters, constitutions and bulls; **superseded 22 Nov 2026**: Carter chose one passage per kind of papal document instead, each in today's prompt for that kind, and only for the kinds the genre filter leaves on, so there is no merged prompt), `church-law` (the `canon-law` prompt, unchanged until 5.4 adds universal laws) and `theologians` (the `medieval` prompt broadened past the medieval period, because the collection will hold writers to the 1930s).
     - Add `_COLLECTION_MAX_TOKENS` entries `papal` 400, `church-law` 350, `theologians` 350.
  6. `dedup.py:65-67`. Add `church-law` next to `canon-law`.
  7. Preferences. Make `PreferencesResponse` on GET tolerant: drop unknown stored keys and fall back to defaults if none remain, instead of raising. PUT validation stays strict.
  8. Concurrency test (`tests/test_config_validation.py:29-45`). Count the most scopes one search can have, which is `max(len(CANONICAL), len(legacy-era set))` after the both-keys dedup in step 4, rather than `len(VALID_COLLECTIONS)`. The current defaults (Cohere 10, HyDE 48) still cover it.
- **Acceptance checks:**
  - Tests, before the data rewrite (fixtures with old stored values), prove each of these:
    - `papal` returns rows from all three old values.
    - `encyclicals` returns today's rows.
    - Results are labeled with the requested key.
  - The same tests after the rewrite (fixtures with new stored values) prove each of these:
    - `encyclicals` returns only genre `encyclical`.
    - `canon-law` still returns canons.
  - A request without any new key returns the same results as today. Keys 5.1b leaves alone send byte-identical Qdrant filters and SQL. The old keys also read the new values (step 2), which hold no rows before 5.1b.3; an old papal key's genre branch is added only where genre can be read (Qdrant `genre` index, `documents.genre`), so a collection without the index gets today's filter exactly. (Reworded in 5.1b.1's review.)
  - GET preferences with a stored `saints` value returns 200.
  - `python3 -m pytest tests/` green.
  - PR description lists the table rows this PR changed.
- **Production safety:** Old keys keep identical behavior against today's data. New keys are only sent once 5.1b.2 ships. The tolerant GET removes an existing 500 risk. Rollback is a revert.
- **Needs Carter:** Confirm the three key names and their labels. Approve the merged papal HyDE prompt text.
  - Answered 22 Nov 2026: the keys and labels stand (`papal` Papal documents, `church-law` Church law, `theologians` Theologians and spiritual writers). No merged prompt: "when papal documents is selected, do one HyDE for each kind of papal document. When things are filtered, only do a HyDE for the ones that have been requested."
- **Out of scope:** Web changes, data changes, removing old keys.

### 5.1b.2. Web switches to the new keys

- **Type:** PR
- **Depends on:** 5.1b.1 deployed.
- **Goal:** Users see eight collections instead of ten (the plan said nine; nine includes Roman Curia, which 5.3a adds): Papal documents with a genre filter, Church law, and Theology & Spirituality. Saved preferences, history and bookmarks keep working.
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
- **Done (22 Nov 2026).** Decisions and corrections:
  - Carter: colours keep the old collections' (Papal documents gold `#e8c040` from Encyclicals, Church law red `#e84040`, Theology & Spirituality grey `#90a0a8`); every token passes §9's contrast rule in both themes. The label "Theologians and spiritual writers" became **Theology & Spirituality** (shorter; names the writing, so it fits every writer 5.6b adds); the key stays `theologians`. About and Discover wording approved with two edits (landing line says "the Summa", not "Aquinas"; the Theology & Spirituality About entry says "soon more writers will join").
  - Step 3: the debounced PUT runs only on a deliberate change, so a translated preference is not written back on load. It is translated on every read until 5.1b.3 rewrites the rows; no silent save was added.
  - Step 4: a restored search's genre selection is not displayed anywhere (5.1a shows no chips); it lives in the restored request, which a retry sends. The rule: per old papal key, the genres its own 5.1a selection named, or else the genres that key stands for; all three old keys without a selection are the whole collection; popes narrow only if every old papal key named some (`canonicalSearchFilters`). Old outcomes merge per new key (results if any had results, degraded if another failed; otherwise the most informative), and saved passages are relabelled.
  - Found on the way: the copied citation ended with the internal key ("(papal)", "(theologians)"); it now ends with the collection's name, on result cards and bookmarks. A copied reference that already starts with its author's name (a papal one can: "Pope Leo X — Exsurge Domine") no longer repeats it in brackets.
  - The genre filter's "no Kind list for a collection with one genre" test was removed: no collection has one genre now. The code path stays for Roman Curia (5.3a).
- **File list re-verified on master `658d44a` (22 Nov 2026)**, every web location that named an old key, and what 5.1b.2 did there:
  - `lib/collections.ts`: eight collections, `LEGACY_COLLECTIONS`, `canonicalCollectionKey`, `canonicalDocuments`; `getCollectionMeta` translates.
  - `app/globals.css`: three new tokens (old tokens stay until 5.1b.4; no light-theme override block exists).
  - `lib/collection-scopes.ts` and `.json` (*new since the table*): `SCOPED_COLLECTIONS` is `papal`; works group under their new key; `canonicalSearchFilters`.
  - `lib/search-draft.ts`: old keys translated; guest default ends with `papal`.
  - `lib/search-experience/useSearchPageExperience.ts`: restore and the guest's saved search translate collections, selections, outcomes and passages.
  - `components/search/LoadingAnimation.tsx`, `QuotaControl.tsx` and `.module.css` (`.papalNumeral` removed with its collection), `ChunkCard.tsx` (key checks compare the translated key; copy suffix), `components/bookmarks/BookmarkCard.tsx` (*new*: copy suffix), `components/reader/DocumentOverview.tsx`, `ReaderChrome.tsx`, `components/sources/SourcesPage.tsx` (one section per new key, by date), `components/landing/LandingPage.tsx`, `components/about/AboutPage.tsx`.
  - Left alone: `app/page.tsx:6` and `AboutPage.tsx:42` say "encyclicals" as content, which is still true; `lib/source-sites.json` (generated, 5.1b.3); `lib/attribution.ts` and `lib/corpus-lifecycle.ts` match only the site name "papalencyclicals.net".
  - API half: `models/preferences.py` default collections; `routes/evaluate.py` scores eight collections.


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
  1. Migration `supabase/migrations/00NN_collection_keys.sql` (next free number at merge time; 2.2a took 0042 and 0043, and 0039 is unused). One transaction:
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
  - Between the database apply and the alias switch, an old papal key can read a passage another old key also read (Evangelii Gaudium under `encyclicals` in one store and `apostolic-exhortations` in the other). The search keeps it under one key (`rrf._one_key_per_passage`), so for a search of both keys in that window, one of them can come back with fewer passages or `no_candidates`. Keep the window short.
  - Decide the eight searchable papal documents stored under one old key whose genre belongs to another (found in 5.1b.1's review, from `works.json` on 22 Nov 2026). Stored under `encyclicals` today: Evangelii Gaudium and Evangelii Nuntiandi (genre `apostolic-exhortation`), Graves Ac Diuturnae, In Supremo Apostolatus and Salutis Nostrae (`apostolic-letter`), Ineffabilis Deus and Munificentissimus Deus (`apostolic-constitution`), and the Syllabus of Errors (`other`). Once the rewrite stores them as `papal`, an old key reads them by genre (`LEGACY_COLLECTIONS`), so an old-key request, or a restored search that 5.1b.2 translates to a genre selection, finds Evangelii Gaudium under exhortations instead of encyclicals. Under the new keys they are simply papal documents of their genre. The 52 retired encyclicals without a genre are not searched.
- **Out of scope:** Removing old keys from code or the constraint (5.1b.4). Adding Pseudo-Dionysius (5.6a).
- **Built (23 Nov 2026; the live step is pending).**
  - Carter, 23 Nov: the eight papal documents stored under Encyclicals with another genre are filed by their kind (no extra machinery: the live web has read old papal keys by kind since 5.1b.2, so only a tab left open from before it notices). The live step is one apply with the switch, then the user-row script and the API restart, in one approved session.
  - **Window**, from `corpus_publishes` (read again 23 Nov, after Stromata III): recent applies switched the alias 38 s (Stromata III), 31 s and 131 s after the database commit (the Phase 4 republish, switched as a separate step, 199 s). During it today's site sees nothing: it sends new keys and the API reads both vocabularies in both stores.
  - **Sources keep their names.** `publication.SOURCE_BUILDS` builds each source (`sources/<key>/`) as before; `SOURCE_ADAPTERS` holds the eight published collections, assembled from them (`papal` from the three papal sources; `church-law` from `canon-law`; `theologians` from `medieval` without Boethius; `church-fathers` with Boethius, by his registry ID). `collection_keys.py` holds the rename map. The work registry, the 0.1a to 0.1c checks and their known defects, and the embedding overlap stay keyed by source (`collection_keys.source_of`, the registry entry's collection), so no ID moves, no check id changes, and no vector changes: the build was compared with master's, document by document, and all 239 documents of the affected collections keep their IDs, content and embedding inputs (17,738 passages, rechecked against master after Stromata III). This departs from step 2 in two places: the papal overlap stays per source (the spec's 250 for all papal would have re-embedded the 44 former exhortations and papal documents), and the V5 maps (`stages/parse.py`, the enrichment prompts) stay by source, as V5 builds by source.
  - **2.2w covers the old keys** (`collection_keys.live_keys`): a stage, report or apply of a new key also reads the live rows filed under each old key that becomes it, so they are compared by ID, not retired. The stage copies every unstaged collection's points under the key they are stored with, so a publish of another collection between this merge and the apply keeps them. A stage refuses a build holding a live document filed under a collection it does not cover, and `publish.py stage --collection` repeats. Boethius moves only in a stage of both `church-fathers` and `theologians`: a Fathers-only stage leaves him where live has him, and a stage of `theologians` alone refuses while he is live there (`place_boethius`). The `renames` field 2.2w had is gone; the map replaces it.
  - **The composite adapter emits 123 documents** (79 + 30 + 14), not 175: the 52 retired encyclicals held for permission are not built.
  - **Outcomes merge as the web merges them** (results if any had results), not "the worse outcome", which would report no results for a merged collection that had them. The papal selection follows the web's restore rule (`canonicalSearchFilters`), so a restored search reads the same before and after.
  - Not changed here: `services/api/scripts/republish_checks.py` keeps the old keys, which the API accepts until 5.1b.4; `card_notes._BADGE_KINDS` stays until 5.1b.4.
  - **Read-only counts (23 Nov 2026, after Stromata III).** Postgres (live, not retired): encyclicals 79 documents and 5,237 passages (52 more documents retired), apostolic-exhortations 30 and 2,968, papal-documents 14 and 487, canon-law 1 and 1,793, medieval 6 and 444 (Boethius 70 of them), church-fathers 109 and 6,809 (6,879 with Boethius). Qdrant `chunks_live` (→ `chunks-stromata-iii-2026-11`) has the same points per key, and none under `papal`, `church-law` or `theologians`. User rows (`rewrite_collection_keys.py` dry run): `user_preferences` 6 of 9 change, `searches` 255 of 336 (98 merged outcome entries, 108 Papal documents selections added), `guest_trials` 4 of 7 (4 selections added); no double-encoded filters; 15 searches still name `saints` and are left alone. Bookmarks hold no collection. The script also rekeys the 52 retired encyclicals (held for permission), which no build emits, so the publish cannot; it writes each row only over the value it read, so a concurrent edit aborts the run.
  - **Runbook for the live step** (each step needs Carter's approval):
    1. Merge timing: free. Until the cutover, every other publish keeps the renamed collections' old rows and points as stored, and a Fathers-only publish (Stromata) leaves Boethius where he is (`publication.place_boethius`); he moves only in a stage of both `church-fathers` and `theologians`. Staging any new key writes it, which needs 0046 applied first.
    1a. Before the apply, recount read-only the saved searches that show a Boethius passage without having selected Church Fathers (`retrievals` joined to his chunks, `filters->'collections'` lacking `church-fathers`): their restore would label those passages Church Fathers and hide them behind the result filter. On 23 Nov there were none (20 searches show him; all selected Church Fathers). If any appear, ship a web fix that makes a restored search's returned collections visible first.
    2. Apply `supabase/migrations/0046_collection_keys.sql` (widens the constraint in `public` and `staging`, sets the preference default).
    3. Lock-file PR: release `collection-keys-2026-11`, entries for `papal`, `church-law`, `theologians` and `church-fathers` with steps `stage` and `apply`, and `all` with step `repair`.
    4. `python3 publish.py stage --release collection-keys-2026-11 --collection papal --collection church-law --collection theologians --collection church-fathers`, then `publish.py report`: every passage `same`, zero retirements, zero new IDs, the vectors copied from the alias target (no embedding call).
    5. `publish.py apply --release collection-keys-2026-11` (applies and switches `chunks_live`).
    6. `python3 scripts/rewrite_collection_keys.py --apply --release collection-keys-2026-11` (first without `--apply`: it must report no live document still under an old key).
    7. Restart the API (the `/sources` cache).
    8. The acceptance checks above, read-only, and a smoke search per collection with old and new keys.

### 5.1b.4. Remove old collection keys (contract)

- **Type:** PR
- **Depends on:** 5.1b.3 applied, and 14 days with no `legacy_collection_key` log lines (Railway filter), or Carter's call on the remaining traffic.
- **Goal:** One vocabulary of nine keys in code and database. No visible change.
- **Current state:** After 5.1b.3 no stored value uses an old key. The code still carries the legacy branches.
- **Changes:**
  1. `constants.py`. Remove `LEGACY_COLLECTIONS` and the old keys from `VALID_COLLECTIONS`. `scope_for` loses the legacy union branch.
  2. `hyde_s25.py`, `dedup.py`, `scripts/run_eval_suite.py`. Remove the old keys.
  3. Migration `00NN_drop_legacy_collection_keys.sql`. Narrow `documents_collection_check` to the new keys. `ADD CONSTRAINT` validates existing rows and fails the whole migration if any old value remains, which is the intended guard.
  4. `globals.css`. Remove old color tokens.
  5. Web keeps `LEGACY_COLLECTION_KEYS` and `canonicalCollectionKey` for reading browser `localStorage` and old links only. Carter to note: the plan says "old keys removed". This PR removes them from the API, the database and every product surface, and keeps a five-line read-side translation in the browser so guests' saved drafts do not reset. Delete it too if Carter prefers.
  6. CLAUDE.md §15 ("9 collections"), §18, `apps/web/AGENTS.md`.
- **Acceptance checks:**
  - `git grep -nE '"(encyclicals|apostolic-exhortations|papal-documents|canon-law|medieval)"' -- services apps/web/src datapipeline` returns only the web legacy map, migrations and source-directory names.
  - Tests green.
  - Migration applied on a local database first.
- **Production safety:** Stored data no longer has old keys (5.1b.3 check). An old tab still open would send an old key, which `resolve_search_plan` drops, returning 400 only if nothing valid remains. The log check shows this traffic is gone. Rollback is a revert plus re-widening the constraint (additive).
- **Needs Carter:** Approve applying the migration. Decide on the web legacy map (step 5).
- **Out of scope:** Renaming source directories under `datapipeline/sources/`.
- **Built (23 Nov 2026), not merged.** Decisions and corrections:
  - Gate (Carter): no 14-day log wait. The PR merges and 0048 applies once 5.1b.3's user-row script (step 5) and acceptance checks (step 7) are done and the read-only count in the PR reads zero for documents (live and retired), preferences, searches, guest trials and the Qdrant payload.
  - 5.1b.3's rollback window: `publish.py rollback` would write the old keys back to `documents` (refused once 0048 is applied) and point `chunks_live` at a Qdrant collection carrying them (which this API would not search). So until that window closes, rolling 5.1b.3 back means reverting this PR and re-widening the constraint first (re-run 0046's statements). A retired row the publish does not rewrite keeps its old key and would also fail 0048; the count's first line includes retired rows, so it shows any.
  - Web legacy map kept (Carter): `LEGACY_COLLECTIONS`, `canonicalCollectionKey` and `canonicalSearchFilters` stay in `apps/web/src/lib/`, for keys a browser holds.
  - Eight keys, not nine: the count in "Goal" predates the papal merge.
  - `constants.py` drops `LEGACY_COLLECTIONS`; `VALID_COLLECTIONS` is `CANONICAL_COLLECTIONS`. The transition code 5.1b.1 added is reverted to its form before 5.1b.1 (`collection_scope.py`, `retrieve_fts.py`, `retrieve_vector.py`, `qdrant_client.py`, `search_plan.py`, `steps/rrf.py`), and a restored search's passages carry their stored key again (`routes/search.py`). There is no `scope_for`; its role was `collection_scope.reads`.
  - The papal HyDE kinds are keyed by kind (`_PAPAL_KINDS`: encyclical, apostolic exhortation, other), with the old prompts and lengths unchanged byte for byte; the medieval prompt and the `canon-law` entries go.
  - Also removed: `card_notes._BADGE_KINDS` (no badge names a kind now), the old keys in `corpus_lifecycle`, `footnotes`, `reader_access` and `dedup`, and `republish_checks.py`'s old keys (Papal documents asks one ordinary and one reference question per kind).
  - Migration `0048_drop_legacy_collection_keys.sql`, with its `-- non-additive:` reason; tested on a local database, including the refusal while an old key remains.
- **Done (24 Nov 2026).** #482 merged; 5.1b.3's rollback window had closed, so the rollback note above no longer applies. The read-only count read 0 for documents (live and retired), staging (absent), preferences, and the saved filters of searches and guest trials; `chunks_live` held 0 old-key points of 51,519. 0048 applied through the Supabase migration tool (ledger `20261125025359`); `documents_collection_check` lists the eight keys and is validated.

### 5.0. Decide how Denzinger is handled

- **Type:** decision, with research.
- **Depends on:** R9. Decided after the P4 cutover and before any addition (5.3a onward) starts.
- **Goal:** Settle for good how TheoCorpus uses *The Sources of Catholic Dogma*, Deferrari's 1957 English of Denzinger's *Enchiridion Symbolorum* (Decision log "Denzinger: extracts now, decide before expansion", Carter, 4 Nov 2026).
- **Current state:**
  - Used only as extracts placed in their own documents, decree text only (Decision log "Deferrari's Denzinger: decree text only (R9)"). Deferrari's row is approved. What the book holds and what it fills so far: `docs/research/R9-council-gap-leads.md`.
  - The book has over 2,300 numbered entries, from creeds and councils to papal and Holy Office documents, many of them outside the corpus today.
- **Changes:** Choose one, then open the items it needs:
  1. Denzinger as its own collection: the whole book, with its numbering and order, readable and citable as "Denz. 714".
  2. All its parts placed where they belong: every extract goes into its own document, and the book itself does not appear.
  3. Both.
- **Decided (Carter, 15 Nov 2026; Decision log "Denzinger in the expansion (5.0)"):** option 2 for search, with each placed passage carrying its D and DS numbers as citations. If the rights research allows it, also option 3's reading side: Denzinger as a book in the reader, in its own order and numbering, built from the same passages, so search shows no duplicates. The research below still runs first, and its map of entries proposes where each kind goes, for Carter to confirm.
- **Research first:** The rights position of the 1954 German edition's editorial work, since options 1 and 3 use the headings, notes, numbering and selection that 1.2e leaves out. Whether the book's modern papal texts can be used. A map of its entries to the corpus: which are duplicates, which fill a gap, and which are new. What each option costs in OCR, in Qdrant and in the 1.2e rule. A concordance from Deferrari's D numbers to the DS numbers modern documents cite.
- **Acceptance checks:** Carter's choice is in the Decision log, and the items it needs are in this plan.
- **Production safety:** Decision and research only.
- **Research (15–16 Nov 2026):** `docs/research/5.0-denzinger.md` (the map of entries, the D-to-DS concordance plan, the costs); the rights memo is kept privately.
- **Needs Carter:** Answered 15 Nov 2026 (above) and 16 Nov 2026 on the research: the book view is built, on the conditions in the Decision log row "Denzinger book view (5.0)"; entries go where the row "Where Denzinger's entries go (5.0)" says; post-1930 originals the corpus lacks are held (row "Denzinger entries issued after 1930 (5.0)"); a fuller text replaces Deferrari's extract where one exists (row "Fuller texts over Deferrari's extracts (5.0)"). Next: the items these need (the concordance, the placed entries, the book view) are written into this plan before any addition starts.
- **Out of scope:** Publishing anything. Each option's work is its own item.

---

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
    - R6 (5 Oct 2026) settled two: the *Golden Epistle* title page reads Sheed and Ward, London, MCMXXX, translated by Walter Shewring, edited by Justin McCann; the Stanbrook *Letters* are vol. I 1919, II 1921, III 1922, IV 1924. Tanquerey is not settled: both scans read "Second and revised edition" with a May 1930 imprimatur and no year. Marmion's *Christ in His Mysteries* is Sands and Herder, 1924. Bellarmine's *Ascent* is the 1616 "T. B." translation, first published by Burns Oates and Washbourne in 1928 with Brodrick's introduction. Open scans of all 12 Pohle-Preuss and all 5 Koch-Preuss volumes in printings of 1930 or earlier exist (1912 to 1928, some second or third revised editions). R6 added a draft row with `planned_for` for every other work in 5.3 to 5.6c (`docs/research/R6-editions.md`).
  - Every P5 publish goes through 2.2w (D2). Each one briefly holds a staging copy of the collections it publishes and a new Qdrant collection beside the one behind `chunks_live`, so its projection includes that transient peak, not only the lasting growth.
  - **Carter to note (storage).** Compacted, a passage costs roughly 3.5 KB of database (123 MB of rows plus about 70 MB of indexes over 54,568 passages; estimate). An average passage is about 770 characters (42 MB of content over 54,568). So one million words is about 7,700 passages and about 27 MB. The A1 CCEL list alone is about 3 million words (candidates memo sizes), so about 80 MB, before the Fathers volumes and the scans. After compaction (about 230 MB) the planned P5 additions very likely pass 500 MB, which Supabase Pro absorbs (8 GB of disk included). Qdrant grows about 6 KB of raw vector and about 1.3 KB of payload per passage, and its Free cluster (1 GiB RAM, 4 GiB disk, 0.5) is the tighter limit.
- **Changes:**
  1. One row per planned work in 5.3 to 5.6c. Columns:
     - Work, author, edition (translator, publisher, year, printing).
     - Source URL and format.
     - Public-domain basis: pre-1931 US publication, or a non-renewal search with the search date and the records searched (the Copyright Office's online catalog for post-1977 renewals, and the scanned Catalog of Copyright Entries for 1950 to 1977).
     - Site terms and the action taken: none, asked, or used only to check our own OCR.
     - Credit line text ("Sourced via CCEL.org", "Text: Libreria Editrice Vaticana").
     - Estimated words, passages and MB.
     - R6 status and rule A to H notes.
     - Status: cleared (full reader), excerpt-only, blocked or excluded.
     - For excerpt-only, an `excerpt_basis`: a published statement by the rights holder or the Holy See that allows the use without permission (URL, the wording, the date read) and every condition or limit it sets, such as a word limit per excerpt, a required notice, or no profit. Risk reduction is not a basis: a copyrighted work with no such statement is blocked until permission is granted (Decision log "Excerpt-only needs an allowed-use basis", 29 Oct 2026). The Catechism's basis is the USCCB notice (excerpts up to 5,000 words, with its notice shown). The LEV texts taken from vatican.va cite the 2011 *L'Osservatore Romano* article and its three conditions (Decision log "LEV texts from vatican.va"); the Pontifical Biblical Commission and the social-doctrine Compendium rows stay blocked until the LEV confirms them.
  2. A build check that every passage of an excerpt-only document stays within its basis's limits (for a word limit, the longest passage's word count), run in the release report. The `excerpt_basis` field and this check are code; the first PR that records a basis (1.3c) adds both. As built by 1.3c: the field's keys are `rights_inventory.EXCERPT_BASIS_FIELDS` (`statement`, `url`, `wording`, `read_on`, `conditions`, `word_limit`, `source_host`), and `release.excerpt_basis` fails a passage over `word_limit` words or a document whose `metadata.url` is not on `source_host`.
  3. The same determination for live documents that are `in-copyright` or `unknown`: each gets an `excerpt_basis` or is listed for Carter. None is retired without his decision.
  4. The full-reader step for LEV texts: a vatican.va document whose cleanup fix has passed the coverage checks moves to `permission`, with the article cited as the grant and the conditions as its scope. The PR that makes the move names the fix and attaches its coverage result.
  5. A running storage total at the top, for Supabase and Qdrant. Stop and ask Carter (a paid Qdrant tier, or reorder the additions) when a publish's Qdrant peak, the live collection plus the new one it builds, would pass 3.4 GB of the Free cluster's 4 GiB disk, or when Supabase disk use would pass 85%.
  6. Public facts only. Correspondence, and anything Carter has not sent, stays in the private memos.
- **Acceptance checks:** Every work named in 5.3 to 5.6c has a row with status cleared, or excerpt-only with an `excerpt_basis` its passages pass, before its PR merges. A blocked row blocks its PR. Each addition PR links its rows. The storage total is updated in each addition PR.
- **Recorded (16 Nov 2026):** rows for every planned work in 5.3a to 5.6c, with the spec's other columns and the running storage total, in `5.2-rights-records.md`. Measured then: the database is 210 MB after 4.0's rewrite (3.4 KB a passage); Qdrant holds one collection, `chunks`, 54,555 points, behind `chunks_live`; live passages average 1,055 characters (church-fathers 2,273, encyclicals 1,180). The last Phase 5 publish projects to about 1.8 GB of Qdrant disk, so step 5's stop is not expected to trigger. The R6 title-page questions above are settled, and Gregory the Great's translator in npnf212 is confirmed as James Barmby. Blocked: the two Biblical Commission documents and the social-doctrine Compendium (no basis yet), Tanquerey (until 1 January 2028), and More's *Dialogue of Comfort* (held, R6). The Imitation of Christ renewal search was run and accepted on 4 Oct 2026 (NEEDS-CARTER, 0.2 and R6); its row still awaits Carter's approval.
- **Production safety:** Documentation only.
- **Needs Carter:** All correspondence with rights holders (CCEL, ecatholic2000, NINS for the Newman Reader, the Aquinas Institute if SCG is taken from aquinas.cc). The Qdrant tier decision when the storage total reaches step 5's stop.
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
  2. Renumber the migration to the next free number. 2.2a took 0042 and 0043, and 0039 stays unused. Rebuild it from the constraint as it stands then (new keys plus `roman-curia`), not from the branch's old list.
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
- **Source files (decided by Carter, 5 Oct 2026):** Its approved R6 downloads are vendored in `datapipeline/sources/_incoming/`, under the path R6's "Vendored as" column gives (`_incoming/<path>`), where no adapter reads them. This PR moves each file it ingests, unchanged, to `sources/<path>` and runs `python3 scripts/source_lock.py --write`; the hash stays the same and the lock keeps the file's download date and URL. Its `rights_inventory.json` row already names `<path>` as `source_path`. Files: `roman-curia/compendium-of-the-social-doctrine-of-the-church.html`, `roman-curia/redemptionis-sacramentum.html`, `roman-curia/directory-on-popular-piety-and-the-liturgy.html`, `roman-curia/the-bible-and-morality.html`, `roman-curia/the-jewish-people-and-their-sacred-scriptures.html`.
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
- **Source files (decided by Carter, 5 Oct 2026):** Its approved R6 downloads are vendored in `datapipeline/sources/_incoming/`, under the path R6's "Vendored as" column gives (`_incoming/<path>`), where no adapter reads them. This PR moves each file it ingests, unchanged, to `sources/<path>` and runs `python3 scripts/source_lock.py --write`; the hash stays the same and the lock keeps the file's download date and URL. Its `rights_inventory.json` row already names `<path>` as `source_path`. Files: `apostolic-exhortations/a-new-hope-for-lebanon.html`, `church-law/universi-dominici-gregis.html`, `church-law/de-aliquibus-mutationibus.html`, `church-law/normas-nonnullas.html`. Its 2 page-image files (PDF) are approved per work later and are vendored to `_incoming/` the same way. The French A New Hope for Lebanon page (`_incoming/apostolic-exhortations/a-new-hope-for-lebanon.html`) replaces the empty English page at `apostolic-exhortations/a-new-hope-for-lebanon.html` when it moves; the replaced file's lock entry goes with it.
- **Goal:** Questions about how a pope is elected or what happens during a vacancy are answered from *Universi Dominici Gregis* as currently in force, with its earlier wording available as labeled history. Two vendored papal documents that never reached the corpus (Ubicumque et Semper, Amoris Laetitia) become searchable.
- **Current state:**
  - `datapipeline/sources/apostolic-exhortations/a-new-hope-for-lebanon.html` and `datapipeline/sources/papal-documents/ubicumque-et-semper.html` are vendored but in neither manifest nor the database (verified locally; plan Decision log).
  - `datapipeline/sources/apostolic-exhortations/amoris-laetitia.html` is in the same state. Carter scheduled it for this item on 4 Oct 2026 (plan, Decision log "Amoris Laetitia"); the Changes below do not yet name it.
  - R6 (5 Oct 2026): two of the three vendored files hold no text. `a-new-hope-for-lebanon.html` is vatican.va's English page, which offers the exhortation only in French and Italian; vatican.va publishes no English, and R6's searches found no English text elsewhere. `amoris-laetitia.html` holds only a link to the English PDF (1,330,556 bytes). `ubicumque-et-semper.html` has the full English text.
  - Manifest lists live in `scripts/vendor_sources.py:382` (`APOSTOLIC_EXHORTATIONS`) and `:447` (`PAPAL_DOCUMENTS`).
  - UDG is not vendored. Per the source memo, vatican.va's English page is the consolidated text current from 22 February 2013 and links the 1996 original, *De aliquibus mutationibus* (2007, Latin; replaced number 75) and *Normas nonnullas* (2013; modified numbers 35, 37, 43, 46 §1, 47 to 51 §2, 55 §3, 62, 64, 70 §2, 75, 87). The 30 April 2025 declaration on number 33 is a dispensation, not an amendment.
  - Rule F is current text only in search, superseded versions as labeled linked history.
  - The supersession link is `documents.superseded_by` (2.2a, D5): each older text points to the current text that replaces it.
- **Changes:**
  1. `vendor_sources.py`. Each new papal entry needs a row in `datapipeline/papal_genres.csv` first (genre, form, evidence; 1.3b), or the vendor run stops. Add Ubicumque et Semper (2010, motu proprio) to `PAPAL_DOCUMENTS`, and Amoris Laetitia (2016) to `APOSTOLIC_EXHORTATIONS` from its vatican.va English PDF with the text extracted (Decision log "Amoris Laetitia"), and regenerate manifests. They publish into `papal` with genres `motu-proprio` and `apostolic-exhortation`. A New Hope for Lebanon is not added (rule E, revised 29 Oct 2026).
  2. UDG.
     - New adapter `datapipeline/ingest/universal_law.py` emitting collection `church-law`.
     - Document "Universi Dominici Gregis (as amended 2013)" is searchable, with anchors by number and section and author "Pope John Paul II" with the amendment note.
     - Two history documents (1996 original, 2013 motu proprio) are stored with `searchable = false` on every one of their passages (`searchable` is a passage field), each with `documents.superseded_by` set to the current text, and named in its note, and labeled "superseded text, kept as history". Genre `apostolic-constitution` for the 1996 text and `motu-proprio` for the 2013 act (D5).
     - The 2007 act is Latin only, so under rule E (revised 29 Oct 2026) it is not added. The 2013 act's page notes that it amends the 2007 one, in English, with a link to the Latin on vatican.va.
     - The 2025 declaration is not ingested (application material, not law). Mention it in the document note with its link.
  3. HyDE. Broaden the `church-law` prompt from "a single canon of the 1983 Code" to "a provision of the Church's universal law, such as a canon of the 1983 Code or a numbered norm of an apostolic constitution".
  4. `dedup.py` chapter-keyed list already includes `church-law` (5.1b.1); confirm UDG passages carry `chapter_key` by chapter so the per-source cap works per chapter.
  5. Publish `papal` and `church-law` through 2.2w (stage, release report, one-transaction apply with the outline refresh, `chunks_live` switch) under a named apply in the lock file, never the delete-based prune. The history documents are Qdrant points with `searchable = false` (D5).
- **Acceptance checks:**
  - Release report shows 2 new papal documents (Ubicumque et Semper, Amoris Laetitia) and 3 UDG documents, of which 1 is searchable, and zero retirements.
  - A search for "how many votes are needed to elect a pope" returns UDG number 75 in its 2013 wording.
  - The 1996 wording never appears in search results and opens in the reader with the superseded label and a link to the current text.
  - `/sources` lists all three UDG documents with their status.
- **Production safety:** Additions only. `searchable = false` keeps superseded text out of search through the 2.2b filter. Rollback within the window is 2.2w's `rollback` command, which also points `chunks_live` back; later, a 2.2w apply that retires the documents, with tombstones for anyone who bookmarked them.
- **Needs Carter:** A New Hope for Lebanon has no English on vatican.va: reader only with a note under the Decision log row "Non-English with no usable English" (R6's recommendation, taking the French text), or leave it out. Amoris Laetitia's English exists only as a PDF: vendor the PDF and extract its text (R6's recommendation). Approve the lock-file PR and the 2.2w apply. Confirm UDG belongs in Church law rather than Papal documents (the plan's collection table puts it in Church law; this is a confirmation, not a reopening). Answered 5 Oct 2026: the French text, in the reader with a note, out of search. Revised 29 Oct 2026 (rule E): A New Hope for Lebanon is not added; the French download is not ingested.
- **Out of scope:** Other universal laws (for example *Praedicate Evangelium*, *Vos estis lux mundi*). Propose them as a follow-up.

### 5.5. Catechisms: Compendium of the CCC, Roman Catechism

- **Type:** PR per work, then ops publish
- **Depends on:** 2.2w, 5.2 rows, R6, and 1.2f's OCR tool and gate (D9) for the Roman Catechism if no clean text passes R6.
- **Source files (decided by Carter, 5 Oct 2026):** Its approved R6 downloads are vendored in `datapipeline/sources/_incoming/`, under the path R6's "Vendored as" column gives (`_incoming/<path>`), where no adapter reads them. This PR moves each file it ingests, unchanged, to `sources/<path>` and runs `python3 scripts/source_lock.py --write`; the hash stays the same and the lock keeps the file's download date and URL. Its `rights_inventory.json` row already names `<path>` as `source_path`. Files: `catechism/compendium-ccc.html`, `catechism/catechismofcounc0000jose/catechismofcounc0000jose_djvu.txt`. Its 1 page-image file (PDF) is approved per work later and is vendored to `_incoming/` the same way.
- **Goal:** Short question-and-answer entries from the Compendium of the Catechism (2005) linked to the full Catechism's paragraphs, and the Roman Catechism of the Council of Trent (McHugh and Callan, 1923) as a historical catechism, both in the Catechism collection.
- **Current state:**
  - The Catechism collection is one document, `document_id("catechism")` (`datapipeline/ingest/catechism.py:803`).
  - The Compendium is on vatican.va (`corpus-expansion-candidates.md`, gap 6), and the rights review covered it (Decision log).
  - McHugh and Callan was published 1923 (US, Wagner), so it is public domain in the US. A clean typed text is unverified; the scan-only memo did not cover it.
  - R6 (5 Oct 2026): of four open IA scans catalogued 1923, only `catechismofcounc0000jose` is the 1923 printing ("Copyright, 1923"); the others are printings of the 1934 "second revised edition" (no renewal found for it either). Fordham's clean text (`mod/romancat.asp`) is an "Unknown etext" whose printing is not stated, with Halsall's non-commercial notice.
  - The Catechism HyDE prompt is written for the CCC's style (`hyde_s25.py:152-161`).
- **Changes:**
  1. Compendium. New adapter `ingest/catechism_compendium.py`.
     - One passage per question with its answer, anchor the question number.
     - Keep the CCC paragraph references as a structured field so the reader can link to them. They are not part of passage text.
     - Credit: its rights row's line, "© Dicastery for Communication – Libreria Editrice Vaticana" (5.2's row; 2.3 sets `source_credit` from it).
     - Genre `compendium` (D5).
  2. Roman Catechism. R6 first looks for a clean typed 1923 text and confirms the edition against a scan.
     - If one exists, write an adapter over it.
     - If not, run it through 1.2f's OCR tool and gate, as its own PR, as 5.6c does.
     - Genre `catechism` (D5), year 1566 for the work and 1923 for the translation, note "Catechism of the Council of Trent, a historical catechism; for current teaching see the Catechism of the Catholic Church".
     - Strip McHugh and Callan's notes and introduction (rule G).
  3. HyDE. Leave the CCC prompt, but add a retrieval follow-up to test whether the Compendium's short Q&A form is found; do not tune here.
  4. Each work publishes `catechism` through 2.2w (stage, release report, one-transaction apply with the outline refresh, `chunks_live` switch) under a named apply in the lock file, never the delete-based prune. The existing CCC document must show every passage as `same` in the release report.
- **Acceptance checks:**
  - Compendium has 598 questions (count from the source; confirmed at build, 21 Nov 2026) and each answer is one passage.
  - Focused search on Catechism still returns 10 when asked (per-chapter cap, CLAUDE.md §18).
  - For the Roman Catechism, the 1.2f gate report if OCR was used.
  - Release report shows zero retirements in the CCC.
- **Production safety:** Additions to a released collection, visible together in one apply. Rollback within the window is 2.2w's `rollback` command, which also points `chunks_live` back; later, a 2.2w apply that retires the added documents.
- **Fordham's Roman Catechism (decided by Carter, 5 Oct 2026, NEEDS-CARTER 1.2e and 5.5):** used only to check the OCR of the 1923 scan, never as the text, because of its non-commercial notice.
- **Needs Carter:** Approve each lock-file PR and each 2.2w apply. Whether the Compendium's other parts join it: the motu proprio, the introduction, the appendix of prayers and formulas, and the texts printed between sections (the Apostles' and Nicene Creeds, the list of the seven sacraments, the Decalogue from Exodus and Deuteronomy with the catechetical formula, the Lord's Prayer, and Augustine's saying before question 2), several of which also print a Latin version that rule E keeps out. The Compendium PR builds the 598 questions only; the coverage check counts the rest as uncovered under a known-defect entry. Answered while building the Roman Catechism: NEEDS-CARTER 5.5 (22 Nov 2026; the correction ceiling, the vendored files and the notes), recorded in the Decision log.
- **As built (Compendium PR, 21 Nov 2026):**
  - `ingest/catechism_compendium.py`, registered after `catechism.py` in the `catechism` adapter, so the collection builds two documents. Document `800373b1-d6c8-5a26-8910-8d1485b224c2` (source key `catechism/compendium`, registered by `scripts/compendium_registry.py`), title "Compendium of the Catechism of the Catholic Church", no author, year 2005, excerpt-only (`in-copyright`, vatican.va basis).
  - A passage is the question as printed ("12. Why does man have a desire for God?"), its answer (list items each on a line), and the saints' sayings printed after it. Anchor `q/<n>`, reference "Compendium of the Catechism, Q. <n>", unit label "Q. <n>", no `§` anywhere, so the CCC's paragraph checks cannot count it. The CCC numbers are `metadata.ccc_references`, a list of `[first, last]` ranges. Question 39's line misprints "2112-213"; the build reads "212-213", as vatican.va's Italian and French pages print (`REFERENCE_FIXES`).
  - Chapters follow the page's headings: Part, Section, Chapter and up to two levels below (92 chapters). No contents tree yet (the document is excerpt-only, so `/toc` would refuse it).
  - Coverage reads the page through its own extractor (`checks/source_text.compendium_units`): 84.64% of its body text, everything uncovered being the parts listed under Needs Carter.
  - Release report against a stand-in snapshot of master's own catechism build (no snapshot of live after the republish exists, and each export needs Carter's approval): 788 CCC passages `same`, 598 `new`, nothing else. The live comparison is the publish's own `publish.py report`.
  - vatican.va text fragments (2.4e) checked from the build: 588 of 598 found; 10 keep the plain link (`source_link_misses.json`, `from_build`), among them questions printed alike (Q310 and Q319), since the check now takes a tie between two places as unresolved.
- **As built (Roman Catechism PR, 22 Nov 2026):**
  - Edition confirmed on the scan: "Copyright, 1923, by Joseph F. Wagner, New York", imprimatur of 3 January 1923 (`catechismofcounc0000jose`). No clean typed 1923 text passed R6, so the text came through 1.2f's tool (Decision log "Roman Catechism through the OCR tool (5.5)": a $6.00 correction ceiling, the scan's `_djvu.xml` and page map and Fordham's page vendored and locked, every note left out, scripture references included).
  - OCR work `mchugh-callan-roman-catechism`, pp. 1–590 (the translators' introduction, sermon programme, appendices and index are outside them). Its own `roman-catechism` units (`ocr/units.py`) strip the note calls, drop leaked notes and specks, and keep the translators' headings in the text so the check sees them; `note_start` (new in `ocr/work.py`) adds this book's note markers (a lettered note, a call read as a quotation mark, a reference with a lost call). XML leaf = page + 65, given as `leaf_pages` because the page map leaves out pp. 1–2.
  - Correction cost $5.11 (539 calls; 321 accepted, 187 unchanged, 31 rejected). 240 fixes, each checked against its page image or, for the note calls and marks left after the review, Fordham's transcription: page-foot notes run into the text (58), note calls the model left, misreadings ("1s", "stich", "recewe", the print's "coöperate" and "preëminently"), small-capital headings, headings set over two or three lines or run onto the paragraph before, OCR debris, two body texts the clean-up filed as notes, p. 1 whole and p. 4's first paragraph, and two headings its units dropped with a note or as a speck ("…Murder and Suicide", “Us”), all restored from the page. Unrecognized words 0.23%, against 0.39% for Fordham's transcription. Carter's check: 20 of 20 passages match (seed 294490620). Gate pass; frozen in `ocr/texts/mchugh-callan-roman-catechism.json`.
  - Adapter `ingest/roman_catechism.py`, registered after the CCC in the `catechism` adapter. Document `c6d78d5e-5f23-5f86-b0ca-97a741e186bf` (source key `catechism/roman-catechism`, `scripts/roman_catechism_registry.py`), title "Catechism of the Council of Trent", year 1566, credit "Translated by John A. McHugh and Charles J. Callan (1923)", the spec's note as the document's notes, which 4.4 shows on each card, shortened, as an `authority` caution ("A historical catechism; for current teaching see the Catechism of the Catholic Church."). 1,026 passages, one per translators' section, cut at paragraphs past 3,500 characters; the section heading is the unit label, never text. 42 chapters: the Introductory, each Part's opening, the twelve Articles, seven Sacraments, the Commandments, the opening words, the seven Petitions and the Amen (`CHAPTERS`, labels read off the page images). Each Commandment's and Petition's label carries its printed words ("The Fifth Commandment: “Thou shalt not kill”"), since the units read a short caption of them as a heading.
  - Release report against a stand-in snapshot of master's catechism build (no live snapshot since the republish): 788 CCC passages `same`, 1,026 `new`, nothing else, no failing check.
  - The reader's paragraph-range wording and number search (`ReaderChrome`, `DocumentOverview`) now follow the CCC by title (`readerSectionCollection`), so the Roman Catechism's reader says "Browse Sections".
- **Out of scope:** Other catechisms (Baltimore, Pius X).

### 5.6a. Church Fathers additions and the Pseudo-Dionysius addition

- **Type:** PR per author or volume group, then ops publish
- **Depends on:** P4, 2.2w, 1.8b (the NPNF editorial strip, reused), 2.1, 5.2 rows, R6, and R1 where a work's authorship is doubtful.
- **Source files (decided by Carter, 5 Oct 2026):** Its approved R6 downloads are vendored in `datapipeline/sources/_incoming/`, under the path R6's "Vendored as" column gives (`_incoming/<path>`), where no adapter reads them. This PR moves each file it ingests, unchanged, to `sources/<path>` and runs `python3 scripts/source_lock.py --write`; the hash stays the same and the lock keeps the file's download date and URL. Its `rights_inventory.json` row already names `<path>` as `source_path`. Files: the 12 text files R6's download list gives for 5.6a.
- **Goal:** The Fathers collection gains Basil, Cyril of Jerusalem, Gregory Nazianzen, Gregory the Great, John Chrysostom, Ambrose and Leo the Great, all Doctors of the Church, plus Pseudo-Dionysius, so common questions about the Holy Spirit, baptism, pastoral care and the priesthood reach their classic patristic sources.
- **Current state:**
  - None of the seven authors is in the corpus, and neither is Pseudo-Dionysius (verified 29 Sep). Pseudo-Dionysius is therefore an addition here, not a move; the only work that moves collection in P5 is Boethius (5.1b.3).
  - Vendored Fathers sources are 10 ThML files (`datapipeline/sources/church-fathers/`, for example `apostolic fathers.xml`, `third-century.xml`) plus the vendor list at `scripts/vendor_sources.py:62`.
  - ThML parsing is `datapipeline/ingest/thml_doc.py` (document id from collection, author and title at `:89`, replaced by registry lookup after 2.1).
  - NPNF volume identifiers on CCEL (confirmed by R6 on 5 Oct 2026, with title pages and sizes in `docs/research/R6-editions.md`; npnf213 also holds Ephraim Syrus and Aphrahat, which this item does not take):
    - Basil, npnf208.
    - Cyril of Jerusalem and Gregory Nazianzen, npnf207.
    - Leo the Great and Gregory the Great's *Pastoral Rule* and letters, npnf212.
    - Gregory the Great's remaining letters, npnf213.
    - Ambrose, npnf210.
    - Chrysostom, npnf109 to npnf114 (six volumes).
  - Pseudo-Dionysius comes from CCEL `dionysius/works` (Parker, 1897 and 1899; both *Hierarchies* are in the second volume), which the scan memo found clean apart from light OCR slips, header "Rights: public domain". Do not use CCEL's separate `dionysius/celestial` (unattributed translation).
  - Sizes (measured for 5.2 on 16 Nov 2026, body text without ThML notes): about 25 million characters across the 12 files, about 9,200 passages after the editorial strip. Chrysostom's six volumes are 14.7 million characters, about 5,400 passages, the largest single addition in P5.
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
- **As built, Basil (23 Nov 2026, first PR):**
  - `ingest/church_fathers.py` gains an NPNF path for the volumes this item adds: `NPNF_WORKS` names each work div with its author and title, and the editors' divs inside it (introductions, a translator's preface, a letter NPNF only summarizes in brackets). Only those divs are read, so title pages, prolegomena and indexes stay out; `checks.source_text.VOLUME_SCOPE` reads the same divs. Later volumes add entries.
  - The editors' head lines over each chapter, homily or letter ("Chapter V.", "Letter VIII." and the title under it) move into the label, read from the printed line, since CCEL garbled some div titles. A letter collection is one document with each letter a work (D6), as Cyprian's Epistles are. NPNF2-08 prints none of Basil's own headings, so no `metadata.headings` marks; the three documents are opted into H7 and H8, which pass.
  - Basil's NPNF2-08 builds three documents: *On the Holy Spirit* (72 passages), *The Hexaemeron* (78) and *Letters* (446, 309 letters as works), 596 passages and 1.32 million characters in all (5.2 estimated about 620). Translation line "Blomfield Jackson (1895)".
  - The examples in change 3 resolved for Basil (R1, 5.6a addendum): the Apollinaris correspondence is not printed in NPNF2-08 (only a note, which rule G drops), and Quasten now leans to its being genuine. Letters by Gregory of Nyssa (10, 16, 38, 189), Gregory of Nazianzus (47, 167, 169 to 171) and Antipater (187) are credited to them; spurious letters to "Pseudo-Basil"; Letter 360 stays under rule D. Basil is a Doctor, so rule A (limit 2) passes all his own letters, his earliest included; it leaves out Julian's two letters and Libanius's fourteen. Letter 8 stays credited to Evagrius Ponticus, and Letter 167, Gregory of Nazianzus's Letter 66, is retired as a duplicate of his own copy (Carter, 24 Nov 2026, Decision log). The Greek creed in Letter 125 is cut under rule E (Deferrari's English follows in its own PR, Decision log "Letter 125's creed (5.6a)"). The passages of Letters 2, 14, 90, 136, 138, 203 and 204 that NPNF2-08 gives in Newman's translation credit Newman and Jackson (`card_notes.PASSAGE_TRANSLATORS`, by anchor).
  - Removal IDs: 5.6a's blocks are rm-11501 to rm-11999 and then rm-13001 to rm-15999 (`scripts/npnf_registry.py`, which also splits the volume's rights row into one row per work; the second block given by Carter on 26 Nov 2026, when the first ran short, since rm-12001 to rm-12999 belong to 5.4 and 5.6c); Basil uses rm-11501 to rm-11551; rm-11522 to rm-11531 (Letter 8's) are retired and never given again. At merge, `sources/church-fathers/manifest.json` gains NPNF2-08's entry with the file (its lock hash changes with it), so the coverage report measures the file.
- **As built, Cyril of Jerusalem with Gregory of Nazianzus (24 Nov 2026, second PR, stacked on Basil's):**
  - NPNF2-07 builds three documents: *Catechetical Lectures* (183 passages; two works, the lectures to the candidates and the Mystagogical Lectures, the second labelled disputed), *Select Orations* (332; each oration a work) and *Select Letters* (108; 96 letters as works), 623 passages and 1.77 million characters (5.2 estimated about 805). Translation lines "Edwin Hamilton Gifford (1894)" and "Charles Gordon Browne and James Edward Swallow (1894)".
  - The NPNF path gains a head reader per volume style (`NpnfWork.style`). Cyril's Scripture reading under each lecture's title stays in the text, marked as an epigraph (#452), and his own headings inside Lectures IV and VI are marked at level 2; Gregory's texts print no headings of their own. The editors' introductions, datings and analyses above an oration or letter, and Gifford's appendix of variants to Lecture IX are cut (rule G, `editor-note` span entries); the letters' division heads go with the heading lines (the class entry counting them). The heading hook in `ingest/thml_doc.py` is #447's, ported line for line, with a heading of no level read as an epigraph.
  - Both authors are Doctors, so rule A removes nothing. Removal IDs rm-11552 to rm-11668. Gregory's Letter 66 is also Basil's Letter 167: Carter kept Gregory's copy here and retired Basil's in the Basil PR (Decision log "A letter of Gregory of Nazianzus in Basil's letters (5.6a)", 24 Nov 2026).
- **As built, Gregory the Great with Leo (26 Nov 2026, third PR, stacked on Cyril's):**
  - NPNF2-12 and NPNF2-13 build five documents: Leo's *Letters* (176 passages, 73 letters as works; built as "Letters of Leo the Great", since Basil's are "Letters") and *Sermons* (148; each sermon a work), Gregory's *The Book of Pastoral Rule* (142; labelled by Part and chapter) and his Register as *Register of Letters, Books I to VIII* (360; 273 letters) and *Books IX to XIV* (217; 146 letters). The Register is two documents because each volume is its own source file and a registry work has one. 1,043 passages and 2.43 million characters in all (5.2 estimated about 1,370). Translation lines "Charles Lett Feltoe (1895)" and "James Barmby (1895)" / "(1898)". NPNF2-13's Ephraim and Aphrahat are not read.
  - Three more head readers (`leo`, `pastoral`, `register`). Leo's chapter summaries (the Quesnel and Ballerini editions', printed as "I. Through the negligence…") and Feltoe's summaries in parentheses or brackets are cut (rule G, `editor-note` span entries); 93 of Leo's letters that NPNF2-12 gives only as such a summary or a pointer are not built (`_LEO_SUMMARIES`, listed in `editorial_divs.json`), among them the "Second Tome" (Letter CLXV). Letters LV to LVIII's div keeps Galla Placidia's Letter LVI, the one it prints. A Register letter's label carries its Book ("Book II, Letter III"); the Book's indiction line is cut, Gregory's salutation kept. The questions in the Book of Answers to Augustine of Canterbury are marked as headings, level 2. The five documents are opted into H7 and H8; three of Gregory's salutations the classifier takes for headings are listed in `not_headings`.
  - Both are Doctors (limit 2). The letters to Leo and Gregory their collections keep are credited to their senders (`_NPNF_SENDERS`: Flavian, Theodoret, Galla Placidia, Ceretius, Salonius and Veranus, the Council of Chalcedon, Anatolius, Licinianus, John of Ravenna, Recared, Columbanus, Felix of Messana). Eutyches's letter to Leo (Letter XXI) leaves under rule A (Constantinople II, anathema 11). From Barmby's notes (R1 addendum): Gregory's reply to Felix of Messana (Book XIV, 17) is "Pseudo-Gregory the Great"; Recared's letter (IX, 61) and the Autun privileges (XIII, 8 and 9) are disputed.
  - Leo's Tome (Letter XXVIII, Feltoe's translation) is also in the Councils collection in Bright's translation, as part of Chalcedon; both stay (Carter, 26 Nov 2026, Decision log "Leo's Tome in two collections (5.6a)").
  - Removal IDs rm-11669 to rm-11999 and rm-13001 to rm-13221 (552 entries, 540 of them spans for Leo's summaries and the other cut lines). `editorial_removals.plan` takes several blocks, used in order. `checks.content.letter_senders` now matches a sender by any name word of the editor's title line ("The first from Flavian…", "the Synod of Chalcedon"), or by the letter's own greeting where the title names the senders together ("From Three Gallic Bishops").
- **Acceptance checks:**
  - Release report per PR with passage counts, no editorial passages (coverage test from 0.1a), author labels, and zero retirements of existing passages.
  - Storage projection (including the transient staging copy) and actual growth recorded against 5.2's total.
  - Targeted questions answered from the new sources (Basil *On the Holy Spirit*, Cyril's *Catechetical Lectures* on baptism, Gregory's *Pastoral Rule*, Chrysostom *On the Priesthood*).
- **Production safety:** Additions behind the publish lock, each PR's documents visible together in one apply. Rollback within the window is 2.2w's `rollback` command, which also points `chunks_live` back; later, a 2.2w apply that retires the PR's documents.
- **Needs Carter:** Approve each lock-file PR and each 2.2w apply. Decide the Qdrant tier when the storage total reaches 5.2's stop.
- **Out of scope:** Replacing translations already in the corpus (P1.2 handles council sources; On the Incarnation moved in P1). Other Fathers not named in the plan (for example Bede and John Damascene, both before 750). Propose them later. The exception is the whole works 1.8e left for this item (Carter, 4 Nov 2026): each is added through `_WHOLE_WORK_DIVS` after its rule A to H check, or ruled out.

### 5.6b. Theologians and spiritual writers from CCEL ThML and Gutenberg text

- **Type:** PR per author or small group, then ops publish
- **Depends on:** 5.1b.4 (key `theologians`), 2.2a (`chunks.passage_author`, for the Catena), 2.2w, 1.9 (the medieval adapter fixes), 5.2 rows, R1 (rule A and Church-act checks, including the Pensées' Index status), R6.
- **Source files (decided by Carter, 5 Oct 2026):** Its approved R6 downloads are vendored in `datapipeline/sources/_incoming/`, under the path R6's "Vendored as" column gives (`_incoming/<path>`), where no adapter reads them. This PR moves each file it ingests, unchanged, to `sources/<path>` and runs `python3 scripts/source_lock.py --write`; the hash stays the same and the lock keeps the file's download date and URL. Its `rights_inventory.json` row already names `<path>` as `source_path`. Files: the 36 text files R6's download list gives for 5.6b.
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
       - Francis de Sales, *Introduction to the Devout Life* (Rivingtons 1876, per R6) and *Treatise on the Love of God* (Mackey).
       - Catherine, *Dialogue* (Thorold; confirm whether full 1896 or abridged 1907; if abridged, use the full edition from IA in 5.6c). R6: CCEL's file is the 1907 abridgement, so the 1896 edition goes to 5.6c.
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
       - Gaunilo, "In Behalf of the Fool", and Anselm, "Anselm's Apologetic", together, from the Appendix of the vendored `proslogium-monologium-and-cur-deus-homo.xml`, once Gaunilo has his rule check (1.9; Carter, 4 Nov 2026). This PR clears their `known_defects.json` entries.
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
     - Rickaby's abridged *Of God and His Creatures* (Carter chose the English Dominican SCG, 5.6c, on 16 Nov 2026).
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
- **Source files (decided by Carter, 5 Oct 2026):** Its approved R6 downloads are vendored in `datapipeline/sources/_incoming/`, under the path R6's "Vendored as" column gives (`_incoming/<path>`), where no adapter reads them. This PR moves each file it ingests, unchanged, to `sources/<path>` and runs `python3 scripts/source_lock.py --write`; the hash stays the same and the lock keeps the file's download date and URL. Its `rights_inventory.json` row already names `<path>` as `source_path`. Files: 86 of the 88 text files R6's download list gives for 5.6c. Its 87 page-image files (PDF) are approved per work later and are vendored to `_incoming/` the same way. Not yet vendored, because archive.org returned HTTP 500 on 5 Oct 2026: `theologians/exercisessaintg00gertgoog/exercisessaintg00gertgoog_djvu.txt`, `theologians/bwb_W9-CTR-079/bwb_W9-CTR-079_djvu.txt`.
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
       - Tanquerey 1930. Held until 1 January 2028: every open scan is the undated second edition, and the Library of Congress dates it 1932 (Decision log "Tanquerey held until 2028 (5.2)").
       - Marmion *Christ the Life of the Soul*.
       - Aquinas Rawes sermons (*Lord's Prayer*, *Commandments*).
       - Scupoli (Rivingtons 1875 clean text is a different edition; compare with Burns 1846). R6: Burns 1846 is also "for the use of members of the English Church"; a Catholic edition is Philadelphia, Dornin, 1817 (IA `spiritualcombat01scupgoog`).
       - The Alphonsus Centenary volumes (map volumes to titles first). R6 mapped them from each volume's title page; IA's volume labels differ from the series numbers (`docs/research/R6-editions.md`). Vols. XVI, XVII, XXIII and XXIV have no open scan.
       - Gertrude, Scheeben (credited "after Nieremberg"), Möhler, Knox, Chesterton *The Thing*, Fisher, Faber, Lallemant, William of St Thierry, John of Avila, Elizabeth of the Trinity (her own writings only), Vianney (labeled as recorded sayings).
       - Complete SCG, English Dominican, books 1 to 3 (chosen by Carter on 16 Nov 2026; Decision log "Summa contra Gentiles edition (5.6c)"). Book 2 from `summacontragenti0002unse`, the 1923 printing. R6: book 4 (1929) has no open scan.
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
- **Needs Carter:** Which *Spiritual Combat* edition, since both editions the memos named are Anglican (R6 recommends Dornin 1817). Tanquerey's printing date, which R6 could not settle (check the title-page verso before ingesting). Catherine of Genoa: the clean CCEL 1907 *Life and Doctrine* or OCR of the 1858 Burns *Treatise* (R6 recommends CCEL 1907). Approve each lock-file PR and each 2.2w apply. Send requests to ecatholic2000 where its text is used as more than a proofreading aid. Choose the SCG edition. Review time for the 20-passage checks (about 30 to 60 minutes per work, per the Decision log). Found by 2.4f (12 Nov 2026), open: whether the scanned books use 2.4f's label, "Text from a scanned edition", or the longer one in "Changes" (NEEDS-CARTER, 5.6c).
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
  - Rule E keeps untranslated text out of the corpus. The Decision log says no licence spending in this cleanup.
- **Changes:** None until unblocked. When unblocked:
  - A `church-law` adapter with genre `code` (D5) that distinguishes Eastern from Latin canons by issuer (for example `cceo`).
  - A publish through 2.2w like every other P5 addition.
  - Current text per rule F.
  - An anchor scheme that cannot collide with the 1983 Code's canon numbers.
- **Acceptance checks:** Not applicable while blocked.
- **Production safety:** Nothing changes.
- **Needs Carter:** Decide when to revisit licences (after the free phase ships, per the Decision log).
- **Out of scope:** Ingesting the Latin text as searchable.

### 5.9. The verdict beside condemned texts already in the corpus

- **Type:** two PRs, then one 2.2w publish: (a) Exsurge Domine's condemnation (#420); (b) Martin V's *Inter cunctas* questions on Wyclif and Hus (#422). Asked for by Carter on 21 Nov 2026; nothing is built yet.
- **Depends on:** 4.3 and 4.4 published and their rollback windows closed. (a) also edits 4.3's held-text list for Exsurge Domine's closing, so it is built on 4.3's. 5.2's rights rows for each source.
- **Goal:** Where the corpus holds propositions a document condemns, a reader can also find the condemnation, in the Church's own words. Today Exsurge Domine is 41 condemned propositions of Luther with no condemnation, and Constance's condemned articles of Wyclif and Hus come with a note that the council's sentence is not available.
- **Current state (checked on the republish build, 21 Nov 2026, against all 15 rejected-voice ranges, 3.4):**
  - **Exsurge Domine:** 41 passages, every one `voice = rejected`. The bull's introduction and closing are held for permission (ADR 0001: their only English is Carlen's 1981 translation). The condemnation is in the closing. Deferrari, *The Sources of Catholic Dogma* (1957, Loreto reprint, p. 243, n. 781), the edition the 41 come from (R9), prints it after proposition 41: "Censure of the Holy Pontiff: 'All and each of the above mentioned articles or errors, so to speak, as set before you, we condemn, disapprove, and entirely reject as respectively heretical, or scandalous, or false, or offensive to pious ears, or seductive of simple minds, and in opposition to Catholic truth.'" One sentence, about 50 words; Deferrari prints nothing else of the closing. The same public-domain basis as the 41 (`pd-us-non-renewal`).
  - **Constance:** Wyclif's 45 articles (session 8) and Hus's 30 (session 15) are `voice = rejected`; the council's sentences on them are on the gap register (G6). The one lead for those sentences, Foxe's *Acts and Monuments*, is not pursued (Carter, 4 Nov 2026). Deferrari prints Martin V's bull *Inter cunctas* (22 Feb 1418), "Questions to be proposed to the Wycliffites and Hussites" (pp. 215–218, n. 657–689), which states the council's verdict: question 7, that the condemnations of Wyclif, Hus and Jerome of Prague "have been duly and justly made"; question 8, that they "have been condemned as heretics by the sacred Council of Constance"; question 11, that the 45 and 30 articles "are not Catholic, but some of them are notedly heretical, some erroneous, others audacious and seditious, others offensive to the ears of the pious". Deferrari omits questions 1 to 4, 9 and 10 ("treat of communion with said heretics") and adds a note of his own on the council's authority, which is editorial (rule G).
  - **Not affected:** the Syllabus of Errors (each proposition names the document that condemned it), Ephesus (its Decree against Nestorius is published), the Acts of Archelaus and the Octavius (answered inside the document) and the Summa (replies attached; two articles' replies are missing in every public-domain English and carry 4.4's caution).
- **Changes:**
  - **PR (a).** A passage after Exsurge Domine §41, read from Deferrari's p. 243 through the OCR path the other Deferrari extracts use (`ocr/works/`, 1.2e), with its own frozen ID, not `rejected` (it is the bull speaking), and its `unit_label` "Censure". The rights row records the extract (`also_from`). The document's 4.4 overview note becomes "Only the condemned propositions and the censure are given; the rest of the bull is not available on TheoCorpus at present." 4.3's held entries for the closing stay, labelled so they do not claim the censure.
  - **PR (b) (#422).** A new, separate papal document, *Inter cunctas* (Martin V, 1418), in Papal Documents, from Deferrari n. 657–689; the Council of Constance document keeps its 13 passages, and only its four article passages' note changes: the questions Deferrari prints, an extract, with a 4.4 overview note naming the questions he omits. Its genre and form from 1.3b's evidence rules. A rights row. Constance's passage note for its condemned articles ("The council's sentence on these articles is not available on TheoCorpus at present", 4.4) names the bull: "The council's sentence is not available on TheoCorpus; Martin V's Inter cunctas (1418) states its verdict."
- **Acceptance checks:** A search for Luther's propositions on indulgences can return the censure; the censure's card carries no rejected label; a search for Wyclif's or Hus's articles can return *Inter cunctas*; the 4.4 check passes; the coverage check accounts for every new word against Deferrari's pages.
- **Production safety:** One new passage and one new document, through a normal 2.2w publish under its own lock entry; no existing passage changes text or ID.
- **Needs Carter:** Answered 21 Nov 2026: add Exsurge Domine's condemnation; add *Inter cunctas* as its own papal document, not as a section of the Constance document, which would credit the council with the pope's words (option A).
- **Out of scope:** Constance's own sentences (G6; Foxe not pursued). The allocutions the Syllabus cites. Linking each condemned proposition to the teaching that answers it.

### RF. Retrieval follow-ups (parent placeholder)

- **Type:** decision (tracking parent)
- **Depends on:** the republish (4.1b's cutover), and the P5 additions whose effects it measures.
- **Goal:** One place to collect retrieval changes that the cleanup made visible but deliberately did not make, so each is judged against a judged run on the republished corpus and the `hyde_cohere_luna_seats10t80_ftsminmatch_hydesample` noise floor.
- **Current state:** Nothing opened. Candidates gathered while writing these specs:
  - Genre-aware HyDE for Papal documents and Roman Curia (5.1a leaves one prompt per collection).
  - Whether the Compendium's Q&A form is found by the CCC-style prompt (5.5).
  - One HyDE prompt spanning 12th to 20th century writers in `theologians` (5.1b.1).
  - The same Father appearing twice, in his own work and in the Catena (Decision log weakness).
  - Authority-aware ranking for Roman Curia documents with papal approval (source memo).
  - The per-chapter cap for new chapter-keyed documents such as UDG (5.4).
  - RF-1, the dedup threshold for chapter-keyed collections (C-09), specified below; it ran as an arm in 4.2 until 0.3 was dropped (30 Oct 2026).
  - Archaic verb forms ("loveth", "saith") that the English text search configuration leaves unstemmed (C-16, Opus A-020).
  - Stitching that reads 1.7's `reply_targets`, so joint replies and replies to a sed contra attach to their arguments (C-14).
  - Verse-level citation lookup in keyword search ("John 3:16" inside the pericope "John 3:1–21"), which needs the query parsed as a citation; 2.2c finds such a verse only by its chapter (C-16).
- **Changes:** Open child issues from the list above, each with an eval plan before code.
- **Acceptance checks:** Each child shows its effect against a judged run on the republished corpus and the noise floor.
- **Production safety:** Each child ships as its own PR under the usual rules.
- **Needs Carter:** Prioritize the children.
- **Out of scope:** Anything that changes which texts are in the corpus.

### RF-1. Dedup threshold for chapter-keyed collections

- **Type:** PR (a pipeline setting, default unchanged), then a judged comparison on the republished corpus, then a decision.
- **Depends on:** 4.1b's cutover, for the comparison; the setting PR may merge any time, since it changes nothing. It ran as an arm in 4.2 until Carter dropped 0.3's baseline on 30 Oct 2026; with no judged comparison left in 4.2, it moves after the republish with the other retrieval follow-ups. 2.2w's staged report still gives `index.dedup_collision_rate` per collection.
- **Goal:** Know whether a higher near-duplicate threshold for chapter-keyed collections returns distinct neighbouring canons and Summa parts without letting true duplicates through, and change it only on that evidence.
- **Current state:**
  - `services/api/app/rag/dedup.py` drops the lower-ranked of two passages from the same document within two positions whose vectors have cosine above `_COSINE_THRESHOLD = 0.9`, a module constant.
  - A canon's vector is built from the canon plus 300 characters of each neighbour, so a short canon is mostly its neighbours' text. The Summa has no neighbour overlap (`datapipeline/config.py:60`), but all parts of an article share a prefix with its title. On the live vectors 35.7% of nearby canon-law pairs, 20.5% of Summa pairs (44% of objection pairs) and 8.9% of council pairs exceed 0.9; six pairs of short neighbours have byte-identical embedding inputs and can never both be shown (C-09, Opus A-004, A-019, Sol). Canons 872 to 874 and 892 to 893, for example, cannot appear together for "who may be a sponsor".
  - The republish keeps today's embedding input apart from 2.2w's neighbour fix, so this needs no second embedding run.
- **Changes:**
  - A per-pipeline setting, `RetrievalConfig.dedup_cosine_threshold` with collection overrides, defaulting to today's 0.9 everywhere, read by `dedup.py` in place of the constant, in the same way `rrf_k` is a per-pipeline axis (CLAUDE.md section 5). Production is unchanged.
  - A registry arm with a threshold of 0.97 for canon law, the Catechism, the Summa and the Bible, compared with production and its noise-floor arm by `run_eval_suite.py` on the republished corpus. It differs from production only in dedup, so it adds no rerank calls.
  - After that comparison, a one-line change to the production configuration only if the arm's judge scores sit within the noise floor or better and it shows fewer distinct neighbours dropped.
- **Acceptance checks:** `tests/test_dedup.py` covers the setting and the override; with the default, `apply_dedup` drops exactly what it drops today. The comparison report shows the arm's scores against production and the noise floor, and how many result pairs each drops.
- **Production safety:** The setting's default is today's value, so merging changes nothing. A later threshold change is its own reviewed PR.
- **Needs Carter:** Approve the comparison's spend, then decide whether to change the threshold (NEEDS-CARTER section B, RF-1).
- **As built, ahead of the cutover (20 Nov 2026, Carter's decision).** The republish's fingerprints prefix each passage with its author, title and chapter (2.2w, `embedding_prefix`), which neighbouring passages share, so at 0.9 the filter fired far more often on the staged collection: on 67.4% of neighbouring Summa pairs against 20.5% today, 23.6% against 8.9% in the councils, 20.5% against 4.3% in the encyclicals. In 4.2's pre-cutover run it dropped 98 candidates in 36 of 59 searches. `app/rag/dedup.py` now takes a line per collection when search reads a collection a publish built, chosen so the filter fires on the new fingerprints as often as 0.9 does on today's: summa 0.950, canon-law 0.912, councils 0.928, encyclicals 0.928, apostolic-exhortations 0.930, papal-documents 0.930, medieval 0.931, church-fathers 0.923, catechism 0.919; bible and any other keep 0.9. Measured on the build's cached fingerprints (no calls). Which line applies is read from the pair's own points: 2.2w marks every point it writes with `embed_sha256` and today's carry none (checked on production, 20 Nov 2026), so the lines apply exactly when search reads a publish's points, switching with the alias at 4.1b step 8 and back at a rollback, with no lookup or delay; a pair with an unmarked point keeps 0.9. Replayed on 4.2's recorded similarities, the drops fall from 98 in 36 searches to 32 in 14. This is a rate match, not the judged comparison this item specifies, which still decides any further change.
- **Out of scope:** Changing the embedding input or the neighbour window. A second, clean-text vector for dedup.
