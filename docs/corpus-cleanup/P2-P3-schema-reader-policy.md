# P2 and P3 work specifications for schema, writer, reader and content policy

29 September 2026, revised the same day to follow the plan's "Cross-cutting design decisions" (D1 to D10). Source of truth is `docs/2026-09-28-corpus-cleanup-plan.md`; its inclusion rules, Decision log and D1 to D10 are settled and are not reopened here. Where this file and D1 to D10 disagree, D1 to D10 win. Code references are to `master` at `5475c49` in `/Users/cartertate/repos/body-of-christ`. Live measurements are read-only SELECTs against Supabase project `hvmgffvimqgiejmxwhwq` on 29 Sep 2026.

## Overview and recommended order

Merge order follows the plan's "Phase and PR plan" table.

1. **2.4c** About page factual fix. Independent, ships first because the page is false today.
2. **2.2a** Migration 0039, additive only. Document facts, the work model (D6), a retired flag on passages and documents, tombstones, redirects, a publish log and a `staging` schema that mirrors the live corpus tables (D2). Nothing reads them yet. No unique key is dropped.
3. **2.2w** The stage-then-apply writer (D2). A publish builds into `staging` and a new Qdrant collection, produces the release report against live, applies in one transaction (with 4.1a's user-data remap inside it), then switches the `chunks_live` alias. Passage IDs come from the 2.1 registry, so every unit live today keeps its ID (D1). It also provides the rollback apply, a cleanup command that drops the staging tables, vector reuse when the embedding input is unchanged, and a read-only staging override for the pre-cutover eval. It replaces today's delete-based prune for every future publish. Rehearsed locally (D8).
4. **2.2b** API reads Qdrant through `QDRANT_READ_COLLECTION`, then the alias `chunks_live`. Search skips passages marked not searchable and passages that are retired.
5. **2.2c** Decision that `search_vector` needs no DDL rebuild. Close it alongside 2.2a.
6. **2.3** Document facts in the work registry, written by 2.2w into staging. No live backfill (D7).
7. **2.4a** API payloads carry document facts, tombstones and redirects; the reader, `/sources`, history and bookmarks hide retired rows or mark them.
8. **2.4b** Web cards, reader, bookmarks and history render the new fields, the source credit on opened passages, tombstones and redirects. Must be live before any tombstone exists.
9. **3.3** Non-English passages flagged not searchable in the registry. Takes effect at the Phase 4 apply.
10. **3.2** Labels, certainty and notes in the registry. Takes effect at the Phase 4 apply.
11. **3.1** Removals recorded by anchor in the removal registry (D4). Blocked by R1. Applied at 4.1b through 2.2w.

Every PR here deploys against today's schema and data. No item deletes a row. User rows that point at removed passages keep working because removed passages are retired, not deleted (D3). Nothing in P2 or P3 changes live corpus data before the Phase 4 apply (D7). The one exception Carter may approve is the early retirement of On the Incarnation's 47 passages (1.8d), specified at the end of 2.2w.

---

## Cross-cutting design for removals and user-owned rows

### What the database does today

Every table that points at a passage cascades when the passage row is deleted. Checked live with `pg_constraint` on 29 Sep.

| Table | Column | On delete of the target | Unique constraint that matters for remapping |
|---|---|---|---|
| `retrievals` | `chunk_id` → `chunks` | CASCADE | none |
| `bookmarks` | `chunk_id` → `chunks` | CASCADE | `(user_id, chunk_id)` |
| `retrieval_labels` | `chunk_id` → `chunks` | CASCADE | `(user_id, chunk_id, search_id)` |
| `guest_trial_retrievals` | `chunk_id` → `chunks` | CASCADE | `(guest_trial_id, chunk_id)` |
| `reading_progress` | `document_id` → `documents` | CASCADE | PK `(user_id, document_id)` |
| `product_feedback` | `chunk_id`, `document_id` | SET NULL | none |
| `document_chapters` | `document_id` → `documents` | CASCADE | PK `(document_id, ordinal)` |

Sources are `supabase/migrations/0005_v2_searches_retrievals.sql:23`, `0006_v2_bookmarks_feedback_prefs.sql:5`, `0022_retrieval_labels.sql:11`, `0026_guest_onboarding_continuity.sql:19`, `0027_reading_progress.sql:4`, `0028_product_feedback.sql:20-21`, `0037_document_outline.sql`.

The datapipeline deletes rows in two places, and both cascade. `datapipeline/writers/reader_writer.py:16-33` (`clear_collection`) deletes a whole collection. `reader_writer.py:36-59` (`prune_missing_chunks`) and `:62-81` (`prune_missing_documents`) delete rows the new build no longer emits. A removal published through today's writer would silently delete every saved retrieval, bookmark, label and guest result that points at a removed passage, and every restored search that contained one would come back short with `restore_status = "results_unavailable"` (`services/api/app/routes/search.py:380-385`). 2.2w removes both paths.

### The rule this plan adopts (D1, D3, D4)

- **A passage ID names one unit of text for good (D1).** Passage IDs are frozen in the 2.1 registry the way document IDs are. Every unit that exists today keeps its current passage ID, and that registry-frozen ID does not change. Structural anchors decide which unit a passage is, not what its ID is, so rebuilding anchors does not re-key the corpus. Only genuinely new units (restored verses, recovered prose, split recensions) get new IDs. Fixing a unit's text keeps its ID, so bookmarks and saved results stay valid and show the corrected text. When a fix changes which text an anchor names, the unit gets a new anchor and the old anchor gets a redirect.
- **Removed passages and documents are retired, never deleted, while any user row points at them (D3).** A retired row stays in `chunks` or `documents` with `retired_at` set. Search, the reader's chapter lists and `/sources` hide it. A tombstone row records why it left and what to show instead. Cascades therefore never fire, and every user row keeps a valid foreign key.
- **Every removal is explained by one registry (D4).** The removal registry owned by 2.1 lists every removed unit by anchor, with its reason and tombstone text. The 2.2w writer refuses to retire an ID the registry does not explain, unless a redirect explains it.

How each user surface behaves after the Phase 4 apply:

| Surface | Passage renumbered, moved, split or merged (a redirect exists) | Passage removed (a tombstone exists) |
|---|---|---|
| Saved search restore | 4.1a remaps `retrievals.chunk_id` to the new ID; until then 2.4a follows the redirect | Card shows the tombstone in place of the passage; `restore_status` stays `complete` |
| Bookmarks | 4.1a remaps, with its merge policy for `(user_id, chunk_id)` | Bookmark card shows the tombstone; the note is kept |
| Retrieval labels | 4.1a remaps, merge policy for `(user_id, chunk_id, search_id)` | Kept as is; labels are evaluation data about what was shown |
| Guest results and claim | 4.1a remaps, merge policy for `(guest_trial_id, chunk_id)` | Claim still copies the row; the restored card shows the tombstone |
| Reading progress | Anchor and chapter redirects rewrite `anchor` and `chapter_key` in 4.1a | Whole document removed, so the progress row is kept, the "continue reading" entry shows the tombstone and drops out of lists |
| Reader deep link | API returns the redirect; web replaces the URL | API returns 410 with the tombstone; web shows a removal page |

A passage whose text was corrected under an unchanged anchor needs none of this. It keeps its ID and every user row sees the new text.

Retired rows cost storage. After the rollback window that Carter sets in 4.1b, retired passages that no user row references can be hard-deleted in an ops step, because deleting them cascades nothing. Tombstones are kept.

### How many user rows the removals touch (measured 29 Sep 2026)

Totals at the time were 54,568 passages, 421 documents, 3,029 retrievals, 25 bookmarks, 3 retrieval labels, 274 guest trial retrievals, 25 reading progress rows.

| Removal (plan rule) | Passages | Docs | Bookmarks | Retrievals (searches, users) | Labels | Guest rows | Feedback |
|---|---|---|---|---|---|---|---|
| A Origen, 3 works | 932 | 3 | 0 | 35 (27, 7) | 0 | 1 | 0 |
| A Tertullian, 7 works | 192 | 7 | 0 | 7 (6, 3) | 0 | 2 | 0 |
| A Tertullian, 2 provisional keeps (not removed) | 50 | 2 | 0 | 1 (1, 1) | 0 | 0 | 0 |
| A Novatian, 2 works | 79 | 2 | 0 | 1 (1, 1) | 0 | 0 | 0 |
| A Novatian, Treatises I and III in pseudo-Cyprian | 16 | part of 1 | 0 | 0 | 0 | 0 | 0 |
| A Tatian | 44 | 1 | 0 | 2 (2, 1) | 0 | 0 | 0 |
| A Arnobius | 392 | 1 | 0 | 2 (2, 1) | 0 | 1 | 0 |
| A Alexander of Lycopolis | 27 | 1 | 0 | 0 | 0 | 0 | 0 |
| B Apostolic Constitutions, all but Book VIII positions 35 to 43 | 178 | 8 (7 whole) | 0 | 6 (5, 5) | 0 | 1 | 0 |
| B Six forged Ignatius letters | 59 | 6 | 0 | 0 | 0 | 0 | 0 |
| B Sectional Confession, positions 0 to 23 | 24 | part of 1 | 0 | 0 | 0 | 1 | 0 |
| B Long recension inside the 7 "Shorter and Longer" documents | part of 97 | 7 | 0 | 0 | 0 | 0 | 0 |
| C Pfaff fragments XXXVI to XXXIX (positions 37 to 40) | 4 | part of 1 | 0 | 1 (1, 1) | 0 | 0 | 0 |
| C Four medieval Latin Ignatius letters | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| **A to C total** | **1,951** | | **0** | **54** | **0** | **6** | **0** |
| G editorial (heuristic, see 3.1) | about 144 | | 0 | 3 | 0 | 0 | 0 |

Positions in this table locate the passages in today's data. The removal registry records them by anchor (D4).

No reading progress or product feedback rows point at documents to be removed. The plan recorded 50 retrievals on 28 Sep; the count had grown to 54 a day later, so 4.1b must re-measure at cutover.

The query that produced this table is kept in 3.1's Acceptance checks so it can be rerun at cutover.

---

### 2.2a. Additive migration for document facts, works, retirement, tombstones, redirects and staging

- **Type:** PR
- **Depends on:** none to merge. 2.1 (work registry and removal registry) defines the values that later fill these columns. Applying to the live database needs Carter.
- **Goal:** Give the database the places to hold what the cleanup decides, without changing anything a user sees. After this, a document can carry its genre, issuer, display date, certainty label, notes, source credit and supersession link; a passage can be marked not searchable, tagged with its language, its work (D6) and a quoted author; a passage or document can be retired; removed units leave a tombstone; moved units leave a redirect; and a publish can be built in a `staging` schema with the live tables' shape before it is applied (D2).
- **Current state:**
  - `documents` columns live: `id, collection, title, author, year, metadata, created_at, translation (NOT NULL DEFAULT ''), chunk_count`. `chunks` columns live: `id, document_id, content, position, reference, content_embedding, search_vector, annotation, annotation_embedding, created_at, metadata, anchor, chapter_key, chapter_label, unit_label, annotation_vector` (information_schema, 29 Sep).
  - Unique keys on `chunks`: `chunks_document_id_position_key UNIQUE (document_id, position)` and partial `chunks_document_anchor_uniq (document_id, anchor) WHERE anchor IS NOT NULL` (pg_indexes, 29 Sep). Both stay. Under D2 the live tables only ever hold one copy of the corpus, so neither key blocks anything; 2.2w moves retired rows' positions out of the live range so they never collide with new ones.
  - Today passage IDs are computed from the anchor (`reader_writer.py:47` and `:114`, `passage_id(doc.id, p.anchor)`), and the writer upserts `ON CONFLICT (id) DO UPDATE` (`reader_writer.py:121`). Under D1 the ID comes instead from 2.1's passage registry, which freezes every current unit's ID, and `passage_id()` is used only for genuinely new units. A unit whose text is fixed keeps its ID and is updated in place at the apply.
  - `document_type` lives only in `documents.metadata` (16 documents). Metadata keys in use: `url` 211, `pope` 175, `source_file` 135, `testament` 73, `council_number` 20, `year` 16, `council` 16, `document_type` 16, `source_url` 6, `source` 2.
  - `year` is NULL for all 128 Fathers documents, the Summa and all 73 Bible books; `translation` is '' everywhere except the 73 Bible books (`WEB-C`); `author` is NULL for all 36 council documents and all 73 Bible books.
  - `refresh_document_outline` (0037) is pinned to `search_path = public` and counts every chunk of a document (`0037_document_outline.sql`, the function body after the `document_chapters` table). Trigger `chunks_invalidate_outline_on_restructure` fires `AFTER UPDATE OF document_id, position, chapter_key, chapter_label`.
  - The API already tolerates a missing column for 0037 (`services/api/app/routes/documents.py:123-132`, `routes/sources.py:73-76`).
  - The Supabase migration ledger does not list every committed migration (for example 0015, 0016, 0019, 0023, 0026, 0033 are absent from `list_migrations`, though their objects exist). Inspect the live schema, not the ledger, before applying 0039.
  - The parked branch `feat/roman-curia-collection` also numbers a migration 0039. It must renumber when it lands in P5.
- **Changes:**
  - New file `supabase/migrations/0039_corpus_facts_retirement_staging.sql`. Every statement is additive, and no constraint or index is dropped. `SET LOCAL lock_timeout = '2s'` at the top, as in 0037, so a waiting `ALTER TABLE` fails rather than queues searches. Adding a nullable column, or one with a constant default, is a catalog-only change on Postgres 11 and later, so neither table is rewritten. CHECK and foreign-key constraints on existing tables are added `NOT VALID` and then validated, so validation takes a `SHARE UPDATE EXCLUSIVE` lock that does not block reads or writes.

    ```sql
    SET LOCAL lock_timeout = '2s';

    -- Genre vocabulary (D5). A lookup table, so adding a genre later is an INSERT,
    -- not a constraint change.
    CREATE TABLE corpus_genres (
        key text PRIMARY KEY CHECK (key ~ '^[a-z]+(-[a-z]+)*$')
    );
    INSERT INTO corpus_genres (key) VALUES
        -- Papal
        ('encyclical'), ('apostolic-exhortation'), ('apostolic-letter'),
        ('apostolic-constitution'), ('motu-proprio'), ('bull'), ('letter'),
        -- Roman Curia
        ('declaration'), ('instruction'), ('doctrinal-note'), ('note'), ('response'),
        ('norms'), ('considerations'), ('commentary'),
        -- Catechisms and law
        ('catechism'), ('compendium'), ('code'), ('law'),
        -- Writers ('commentary' is listed once, above)
        ('treatise'), ('manual'), ('sermon'), ('poem'), ('rule'),
        -- Anything else
        ('other');

    -- Document facts.
    ALTER TABLE documents
        ADD COLUMN retired_at       timestamptz,
        ADD COLUMN genre            text,
        ADD COLUMN issuer           text,   -- 'Pope Leo XIII', 'Second Vatican Council'
        ADD COLUMN date_display     text,   -- 'c. 375-380', '1077-78', '1265-1274'
        ADD COLUMN certainty        text,   -- the attribution label
        ADD COLUMN attribution_note text,   -- 'Heimgartner (2001) assigns it to Athenagoras.'
        ADD COLUMN notes            text,   -- reader note, e.g. the Apostolic Canons note
        ADD COLUMN source_credit    text,   -- 'Text: Libreria Editrice Vaticana'
        ADD COLUMN clavis_ref       text,   -- 'CPG 1083'
        ADD COLUMN superseded_by    uuid,   -- rule F: links an older text to the current one (D5)
        ADD COLUMN superseded_note  text;   -- 'Superseded by the 2023 text of canon 295.'
    ALTER TABLE documents
        ADD CONSTRAINT documents_genre_fk FOREIGN KEY (genre) REFERENCES corpus_genres(key) NOT VALID,
        ADD CONSTRAINT documents_certainty_check
            CHECK (certainty IN ('genuine', 'disputed', 'pseudonymous', 'anonymous')) NOT VALID,
        ADD CONSTRAINT documents_superseded_by_fk
            FOREIGN KEY (superseded_by) REFERENCES documents(id) ON DELETE SET NULL NOT VALID;

    -- Works inside one document (D6). ANF volumes hold several works per document
    -- ("Dubious or Spurious Writings." holds the Sectional Confession, the Twelve Topics
    -- and four homilies), and each carries its own attribution.
    CREATE TABLE document_works (
        document_id      uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        work_key         text NOT NULL CHECK (char_length(work_key) BETWEEN 1 AND 200),
        ordinal          integer NOT NULL CHECK (ordinal > 0),
        title            text NOT NULL,
        author           text,
        certainty        text CHECK (certainty IN ('genuine', 'disputed', 'pseudonymous', 'anonymous')),
        attribution_note text,
        notes            text,
        date_display     text,
        year             integer,
        genre            text REFERENCES corpus_genres(key),
        clavis_ref       text,
        PRIMARY KEY (document_id, work_key),
        UNIQUE (document_id, ordinal)
    );

    -- Passage fields.
    ALTER TABLE chunks
        ADD COLUMN retired_at     timestamptz,
        ADD COLUMN searchable     boolean NOT NULL DEFAULT true,
        ADD COLUMN language       text,   -- NULL means English
        ADD COLUMN work_key       text,
        ADD COLUMN passage_author text,   -- 'Chrysostom, quoted in Aquinas''s Catena Aurea'
        ADD COLUMN note           text;
    ALTER TABLE chunks
        ADD CONSTRAINT chunks_language_check
            CHECK (language IS NULL OR language ~ '^[a-z]{2,3}$') NOT VALID,
        -- Retired rows sit below every live and temporary position (see 2.2w).
        ADD CONSTRAINT chunks_retired_position_range
            CHECK (retired_at IS NULL OR position <= -1000000) NOT VALID,
        ADD CONSTRAINT chunks_work_fk FOREIGN KEY (document_id, work_key)
            REFERENCES document_works (document_id, work_key) NOT VALID;

    ALTER TABLE documents VALIDATE CONSTRAINT documents_genre_fk;
    ALTER TABLE documents VALIDATE CONSTRAINT documents_certainty_check;
    ALTER TABLE documents VALIDATE CONSTRAINT documents_superseded_by_fk;
    ALTER TABLE chunks VALIDATE CONSTRAINT chunks_language_check;
    ALTER TABLE chunks VALIDATE CONSTRAINT chunks_retired_position_range;
    ALTER TABLE chunks VALIDATE CONSTRAINT chunks_work_fk;

    -- One row per publish (D2). Written by 2.2w.
    CREATE TABLE corpus_publishes (
        id                         text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9-]{2,62}$'),
        collections                text[] NOT NULL,
        report_sha256              text,
        qdrant_collection          text NOT NULL,
        previous_qdrant_collection text,
        staged_at                  timestamptz,
        applied_at                 timestamptz,
        alias_switched_at          timestamptz,
        rolled_back_at             timestamptz
    );

    -- Tombstones outlive the rows they describe, so no foreign keys to chunks or documents.
    CREATE TABLE corpus_tombstones (
        entity        text NOT NULL CHECK (entity IN ('document', 'passage')),
        id            uuid NOT NULL,
        document_id   uuid NOT NULL,
        retired_at    timestamptz NOT NULL,
        publish_id    text NOT NULL REFERENCES corpus_publishes(id),
        removal_key   text NOT NULL,  -- the D4 removal registry entry that explains it
        rule          text NOT NULL CHECK (rule IN ('A', 'B', 'C', 'G', 'other')),
        reason_code   text NOT NULL,  -- vocabulary in 3.1
        public_reason text NOT NULL,  -- one plain sentence shown to users
        church_act    text,           -- 'Second Council of Constantinople (553), anathema 11'
        snapshot      jsonb NOT NULL, -- {collection, title, author, reference, chapter_label}
        PRIMARY KEY (entity, id)
    );
    CREATE INDEX corpus_tombstones_document_idx ON corpus_tombstones (document_id);

    -- Redirects from old identities to new ones. The kind column uses the remap
    -- vocabulary of 0.1c (D5) word for word.
    CREATE TABLE corpus_redirects (
        id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        entity          text NOT NULL CHECK (entity IN ('document', 'passage', 'anchor')),
        old_id          uuid,          -- document or passage ID; NULL for anchor rows
        old_document_id uuid NOT NULL,
        old_anchor      text,
        new_id          uuid,
        new_document_id uuid NOT NULL,
        new_anchor      text,
        kind            text NOT NULL
            CHECK (kind IN ('same', 'moved', 'split', 'merged', 'renumbered', 'removed')),
        publish_id      text NOT NULL REFERENCES corpus_publishes(id),
        created_at      timestamptz NOT NULL DEFAULT now(),
        CHECK ((entity = 'anchor') = (old_id IS NULL))
    );
    CREATE UNIQUE INDEX corpus_redirects_id_uniq
        ON corpus_redirects (old_id) WHERE entity IN ('document', 'passage');
    CREATE UNIQUE INDEX corpus_redirects_anchor_uniq
        ON corpus_redirects (old_document_id, old_anchor) WHERE entity = 'anchor';

    -- Staging (D2). Same names, columns, defaults, constraints, generated columns and
    -- indexes as the live corpus tables (LIKE ... INCLUDING ALL), but no foreign keys,
    -- so nothing in staging can reach a user table. The full-text GIN index is included
    -- because the pre-cutover eval (4.2) searches staging. The tables are created by a
    -- function, so 2.2w can drop them after an apply and recreate them for the next
    -- publish with the live tables' shape at that moment.
    CREATE SCHEMA staging;

    CREATE FUNCTION public.create_corpus_staging() RETURNS void
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
    BEGIN
        CREATE TABLE IF NOT EXISTS staging.documents         (LIKE public.documents         INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS staging.chunks            (LIKE public.chunks            INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS staging.document_chapters (LIKE public.document_chapters INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS staging.document_works    (LIKE public.document_works    INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS staging.corpus_tombstones (LIKE public.corpus_tombstones INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS staging.corpus_redirects  (LIKE public.corpus_redirects  INCLUDING ALL);
    END $$;

    CREATE FUNCTION public.drop_corpus_staging() RETURNS void
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
    BEGIN
        DROP TABLE IF EXISTS staging.corpus_redirects, staging.corpus_tombstones,
            staging.document_works, staging.document_chapters, staging.chunks, staging.documents;
    END $$;

    -- The reader outline for staged documents. Same body as public.refresh_document_outline
    -- (below), resolved against staging.
    CREATE FUNCTION staging.refresh_document_outline(p_document_id uuid) RETURNS void
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = staging AS $$ /* 0037 body */ $$;

    SELECT public.create_corpus_staging();
    ```

    The staged redirect `id` values are local to staging; the apply inserts redirects into the live table without them, so the live identity column numbers them.
  - Same file, the reader outline counts only what readers see. Replace `refresh_document_outline` with `CREATE OR REPLACE FUNCTION`, identical except that both chunk subqueries add `AND c.retired_at IS NULL`. Replace `chunks_invalidate_outline_on_restructure` (drop and create in the same transaction) so its column list and `WHEN` clause also include `retired_at`. With no row retired, the function returns the same outline as today.
  - Same file, grants as in 0037. `ENABLE ROW LEVEL SECURITY` with no policies on `corpus_genres`, `document_works`, `corpus_publishes`, `corpus_tombstones` and `corpus_redirects`; `create_corpus_staging()` does the same for each `staging` table it creates. `REVOKE ALL ... FROM PUBLIC, anon, authenticated` on those tables, on schema `staging`, and on the three new functions and the replaced one. FastAPI and the datapipeline use the service role.
  - Because `create_corpus_staging()` copies the live tables' shape when it runs, a later migration that adds a corpus column needs no staging change; 2.2w drops and recreates the staging tables around each publish. `stage` refuses to reuse existing staging tables whose columns differ from live.
  - No API or web change in this PR.
- **Acceptance checks:**
  - New test `services/api/tests/test_corpus_facts_migration.py` using `tests/pg_cluster.py` (as `test_document_outline_migration.py` does). Apply the 0004-era corpus schema, 0037, 0038, then 0039. Assert:
    - `test_existing_rows_are_live_and_searchable`: every seeded chunk has `retired_at IS NULL` and `searchable = true`; every document `retired_at IS NULL`.
    - `test_genre_accepts_only_the_d5_vocabulary`: all 25 D5 values are present and accepted; `apostolic exhortation` and `essay` are rejected.
    - `test_outline_excludes_retired_rows`: a document with 3 chunks, one retired and moved to position -1000000, gives `chunk_count = 2` and no chapter made only of the retired row.
    - `test_retiring_a_row_invalidates_the_outline`: setting `retired_at` sets that document's `chunk_count` to NULL.
    - `test_retired_row_must_leave_the_live_position_range`: setting `retired_at` on a row at position 5 fails the CHECK.
    - `test_redirect_kind_uses_remap_vocabulary`: `rewritten` is rejected; each of the six D5 words is accepted.
    - `test_redirect_anchor_rows_have_no_old_id`.
    - `test_staging_mirrors_live_tables`: for `documents`, `chunks`, `document_chapters` and `document_works`, the columns, generated expressions, CHECK constraints and indexes in `staging` equal those in `public`, and staging has no foreign keys.
    - `test_staging_can_be_dropped_and_recreated`: `drop_corpus_staging()` then `create_corpus_staging()` leaves the same shape, and neither touches a `public` table.
    - `test_staging_outline_reads_staging`: `staging.refresh_document_outline` builds `staging.document_chapters` from `staging.chunks` and leaves `public.document_chapters` unchanged.
    - `test_no_unique_key_dropped`: `chunks_document_id_position_key` and `chunks_document_anchor_uniq` still exist.
    - `test_new_objects_are_closed_to_client_roles`: `anon` and `authenticated` cannot SELECT from the new tables or use schema `staging`.
  - Existing suites unchanged: `python3 -m pytest tests/` in `services/api` and `python3 -m pytest` in `datapipeline`.
  - Timing rehearsal on a local Postgres restored from a `pg_dump` of production (D8), recording the time and lock of each statement. The dump stays on Carter's Mac and is deleted afterwards.
  - PR description must include the full SQL, the lock each statement takes, the local rehearsal timings, and the sentence "This PR changes no API or web behavior."
- **Production safety:** Merging deploys nothing to the database; migrations in this repo are applied by hand. Once 0039 is applied, today's API ignores every new column, table and schema, and the defaults leave all 54,568 passages live and searchable as now. Today's datapipeline cannot write while the publish lock (0.4) holds; if it could, its inserts would take the defaults. The replaced `refresh_document_outline` returns the same outline as before while nothing is retired. Empty `staging` tables and their indexes cost a few kilobytes. If 2.2b or 2.4a deploy before 0039 is applied, their schema probe finds no columns and runs today's SQL.
- **Needs Carter:** Approval of the `pg_dump` for the local timing rehearsal (D8), then approval to apply 0039 to the live database.
- **Out of scope:** Filling any column (2.2w, 2.3, 3.1 to 3.3). Changing foreign keys from CASCADE to RESTRICT (a possible later hardening, not additive). The collection merge and its CHECK constraint (5.1b). The user-data remap (4.1a). Hard-deleting retired rows (ops after 4.1b's rollback window).

---

### 2.2w. Stage-then-apply writer

- **Type:** PR, plus one optional ops step (the On the Incarnation early retirement, at the end of this item)
- **Depends on:** 0.4 (publish lock), 0.1c (release report and remap, D5 vocabulary), 2.1 (document and passage registries and the removal registry), 2.2a (0039 merged; applied before any staging into production). 4.1a later supplies the user-data remap that the apply calls (below).
- **Goal:** One writer for the republish and for every publish after it (D2). A publish never writes straight into live tables. It builds into `staging` and a new Qdrant collection, produces the release report against live, applies in one database transaction that updates, inserts and retires but never deletes, then switches the `chunks_live` alias. Users see nothing until the apply, then see the whole new corpus at once, and no bookmark, saved search, label or guest result is lost.
- **Current state:**
  - `publication.py:121-187` (`CollectionPublicationRunner.publish`) writes each document straight into the live reader store (`reader.write(..., prune=True)`, `:150-154`), then deletes live documents the build no longer emits (`reader.prune_documents`, `:155-158`), then upserts Qdrant points and deletes stale ones (`search.write`, `search.prune`, `:172-177`). `--wipe-reader` calls `clear_collection` (`:148-149`, `:265-266`) and `--reset-search-index` deletes a collection's points (`:170-171`, `:288-291`).
  - `_validate_build` (`publication.py:224-248`) refuses more than 10% shrink or 10% identity churn per collection; it is the only size check.
  - `writers/reader_writer.py:84-132` (`write_document`) upserts the document (`:97-107`), flips positions below zero (`:108-111`) so re-positioned passages do not collide on `UNIQUE (document_id, position)`, prunes (`:112`), upserts passages on `id` (`:113-130`), and refreshes the outline last in the same transaction (`:131`). `clear_collection` (`:16-33`), `prune_missing_chunks` (`:36-59`) and `prune_missing_documents` (`:62-81`) issue `DELETE`, which cascades into user tables.
  - `writers/qdrant.py:15` hard-codes `QDRANT_COLLECTION = "chunks"`. `ensure_collection` (`:28-59`) creates `chunks` if missing. `delete_collection_points` (`:62-67`) and `prune_missing_points` (`:88-108`) delete live points. `upsert_points` (`:111-122`) retries 4 times.
  - `qdrant_schema.py:12` hard-codes `CHUNKS = "chunks"`, and `recreate_chunks` (`:17-29`) deletes and recreates it, with one keyword payload index on `collection`.
  - Passage IDs are computed from the anchor in three places, `publication.py:128-132`, `reader_writer.py:114` and `search_writer.py:41`, all through `identity.passage_id` (`identity.py:40`). Under D1 they come from 2.1's passage registry instead.
  - `writers/search_writer.py:39-63` (`build_point`) writes the payload `collection, document_id, document_title, author, content, reference, anchor, chapter_label, chapter_key, unit_label`. There is no `genre`, `issuer` or `searchable`. `write_document` (`:83-101`) re-embeds every passage of a document on every run.
  - `run_collection.py:62-86` calls `production_runner().publish(...)`; 0.4 adds the lock guard, `--cutover` and `--dry-run` in front of it.
  - Qdrant holds one collection, `chunks`, 54,568 points of 1,536 dimensions, no alias (plan, 28 Sep).
  - The database is 401 MB against the Free plan's 500 MB read-only trigger, and `chunks` holds about 100 MB of live column data (P4 file, "Facts measured"; plan, 4.0).
  - `services/api/app/db.py:42-52` creates the API's asyncpg pool with no `search_path` setting. `services/api/scripts/run_eval_suite.py` runs the pipeline in process with no HTTP server, so it persists no searches.
- **Changes:**
  - **CLI.** New `datapipeline/publish.py` with subcommands, each taking `--publish-id <id>` (the value `corpus_publishes.id` and the lock file's `cutover_release` share):
    - `stage --collection <name>|all`
    - `report`
    - `apply` (switches the alias right after commit unless `--no-switch`)
    - `switch`
    - `rollback` (the rollback apply, below)
    - `cleanup` (drops the staging tables once the apply is checked)
    - `discard` (abandons a publish that was never applied, drops the staging tables and records its Qdrant collection for deletion; deleting a Qdrant collection is always a separate ops step)
    - `status`
  - `run_collection.py` keeps only `--dry-run` (0.4). A live invocation exits 2 with a message pointing at `publish.py`. `--wipe-reader`, `--confirm-reader-wipe` and `--reset-search-index` are removed, since each deletes live rows or points.
  - **Lock gates (0.4).** Every subcommand except `report`, `status` and `stage --dry-run` calls `assert_live_write_allowed(f"publish {subcommand}", publish_id)`, so it runs only when `PUBLISH_LOCK.json` names this publish ID in `cutover_release`, which takes a reviewed PR. This PR adds one rule to `publish_lock.py`. When both `DATABASE_URL` and `QDRANT_URL` resolve to a loopback host (`localhost`, `127.0.0.1`, `::1`), the gate passes without a lock change, so rehearsals against a local restore (D8) and a local Qdrant need no production unlock. Any other host fails closed. After a production apply and its rollback window, a follow-up PR sets `cutover_release` back to `null`.
  - **Stage** (`publication.py`, reworked). `CollectionPublicationRunner.publish` becomes `stage`. It no longer acquires a live reader store or search index.
    1. Refuse if `staging` holds a different publish that is neither cleaned up nor discarded (`corpus_publishes`). Call `create_corpus_staging()` (2.2a) if the staging tables are absent, and refuse if existing ones differ in shape from live.
    2. Build documents with `SOURCE_ADAPTERS` (`publication.py:32-45`). Adapters take frozen document IDs, anchors, document facts, work keys, `searchable`, `language` and `passage_author` from the 2.1 registry, and skip every unit the removal registry marks removed.
    3. Take each passage's ID from 2.1's passage registry (D1). `Passage` gains an `id` field, filled by the registry's lookup from `(document_id, structural anchor)`. A unit that exists today gets its current passage ID, whatever its anchor now looks like. Only a unit the registry does not know (a restored verse, recovered prose, a split recension) gets a new ID from `identity.passage_id`, and the stage lists every such new ID. The writers use `Passage.id` and never recompute it, so `publication.py:128-132`, `reader_writer.py:114` and `search_writer.py:41` stop calling `passage_id()`. A passage with no ID stops the stage.
    4. Delete the staged rows of the collections being staged (staging tables only), then insert `staging.documents`, `staging.document_works` and `staging.chunks`. Positions are the build's positions (0 and up). `search_vector` is generated, and the staged GIN index is built, as in live. Call `staging.refresh_document_outline` for every staged document, so `staging.document_chapters` and `chunk_count` exist for the pre-cutover eval.
    5. Compute retirements and redirects against live. Every live ID in the staged collections that the build does not emit needs either a removal-registry entry (D4), which yields a `staging.corpus_tombstones` row with the tombstone snapshot taken from the live row, or a 0.1c remap outcome of `moved`, `split`, `merged` or `renumbered`, which yields a `staging.corpus_redirects` row. An ID with neither stops the stage and names the ID. Anchor redirects come from 0.1c's `chapter_remap.jsonl`.
    6. Create a new Qdrant collection `chunks-<publish id>` (overridable with `QDRANT_WRITE_COLLECTION` for local runs) with `qdrant_schema.create_chunks_collection` (below). Write one point for every staged passage, searchable or not (D5). Vectors are reused when the embedding input is unchanged. For each staged passage the writer computes `embed_sha256`, the sha256 of the embedding input text (`search_writer.build_embedding_input`, `:27-36`), the model and the dimensions, and stores it in the payload. When the collection the alias targets holds a point with the same ID and the same `embed_sha256`, the vector is copied from it (`retrieve(..., with_vectors=True)`) and no embedding call is made. Live points lack the field today, and the inputs they were embedded from are not recorded, so the first publish (P4) embeds every passage, about 11 million tokens (4.1b's estimate). Every later publish embeds only passages whose input changed. Collections not being staged are copied point for point, vectors and payloads, from the collection the alias targets, so the new collection is complete on its own.
    7. Check that the new collection's point count equals the staged passage count, and record `staged_at` and the collection name in `corpus_publishes`.
  - **Report.** `publish.py report` runs 0.1c's report in a staged mode that reads `staging` instead of building. On top of 0.1c's sections it adds these checks:
    - Every retirement is explained by the removal registry or a redirect (D4).
    - Every passage live today keeps its ID (D1). Each live ID in the staged collections is either present in staging under the same ID or explained by a removal-registry entry or a redirect. The report prints the three counts and fails on any live ID that is none of these. It also lists every new ID with its reason from the registry.
    - The D1 check. Any passage whose ID is unchanged and whose text similarity to live falls below 0.1c's threshold, with no redirect, fails the report.
    - Qdrant point count and payload facts (`collection`, `genre`, `issuer`, `searchable`) equal the staged values for every passage.
    - The document-facts diff that 2.3 specifies.
    - User impact, which lists the user rows that point at retired and redirected IDs.
    - The added storage in `staging` and the projected database size after apply.
    The report's sha256 and a hash of the staged content go into `corpus_publishes.report_sha256`. `apply` refuses when the staged content no longer matches the reported hash.
  - **Snapshot for rollback.** Right before the apply transaction, `apply` exports the live corpus rows of the staged collections (`documents`, `chunks` without `search_vector`, `document_works`, `document_chapters`) in one read-only transaction to a local, gitignored folder `datapipeline/releases/snapshots/<publish id>-before/`, with a sha256 per file recorded in `corpus_publishes`. The files hold corpus text only, no user data. The apply refuses to start if the export fails. This is the corpus dump that 4.1b's rollback step stages.
  - **Apply** (new `datapipeline/writers/apply.py`). One transaction, with `SET LOCAL lock_timeout = '2s'`, for all staged collections:
    1. Upsert `documents` from `staging.documents` by ID, setting `retired_at = NULL` for any document present in staging. Retire documents of the staged collections that staging lacks, which the stage step has already shown are explained. Upsert `document_works`.
    2. Per document, move live passages to temporary positions (`position = -position - 1`, which stays inside -1 to -999,999), as `reader_writer.py:108-111` does today, but only for rows with `retired_at IS NULL`.
    3. Upsert `chunks` from `staging.chunks` by ID. Changed text under an unchanged anchor updates in place and keeps its ID (D1). New IDs insert. A staged ID that matches a retired row un-retires it.
    4. Retire live passages that staging lacks. Set `retired_at = now()` and move each to a position below every existing retired position of its document, starting at -1,000,000, so repeated publishes never collide on `UNIQUE (document_id, position)`. No `DELETE` is issued anywhere.
    5. Insert tombstones and redirects from staging into `corpus_tombstones` and `corpus_redirects`, tagged with the publish ID.
    6. Call 4.1a's `remap_user_rows(conn, redirects, chapter_remap)` inside the same transaction, after the redirects are written, so bookmarks, history results, labels, guest results, reading positions and feedback move to the new IDs in the same commit. Its `RemapLedger` counts go into the publish log. 2.2w ships the call site behind a small protocol, `UserDataRemap`, and 4.1a supplies the implementation. Until 4.1a merges, `apply` refuses any publish whose redirects are referenced by a user row, naming the tables and counts. A publish with no such redirects, such as the On the Incarnation retirement below, runs without it.
    7. Call `refresh_document_outline` for every document touched, last, as `reader_writer.py:131` does today.
    8. Record `applied_at`.
  - **Switch.** Right after commit, one `update_collection_aliases` call deletes `chunks_live` from the old collection and creates it on the new one. Qdrant applies the listed alias actions atomically. The old target is stored in `corpus_publishes.previous_qdrant_collection`. Between commit and switch (seconds), a vector hit on a now-retired passage is dropped by 2.2b's Postgres guard, and new passages are found by full-text search only.
  - **Rollback apply.** `publish.py rollback --publish-id <id>` undoes an applied publish within the rollback window, with the same lock gate. It is an apply in reverse, built from the same code.
    1. Recreate the staging tables if `cleanup` dropped them, and load the publish's before-snapshot into them. The snapshot's sha256s must match `corpus_publishes`.
    2. In one transaction, run apply steps 1 to 4 with the snapshot as the staged content. This restores the previous text and facts in place by ID and un-retires every row the publish retired.
    3. In the same transaction, retire every row the publish inserted, with a tombstone whose `reason_code` is `rolled_back`. These rows exist in live and are absent from the snapshot, and that absence is their D4 explanation. None is deleted, since users may have bookmarked them during the window.
    4. Still in the same transaction, delete this publish's rows from `corpus_redirects` and `corpus_tombstones` (neither table is referenced by user rows), call 4.1a's reverse remap (`--reverse`) for its redirects, and refresh the outline of every touched document.
    5. After commit, switch `chunks_live` back to `corpus_publishes.previous_qdrant_collection` and record `rolled_back_at`.
    The previous Qdrant collection and the snapshot are kept until the rollback window closes (4.1b).
  - **Cleanup.** `publish.py cleanup --publish-id <id>` calls `drop_corpus_staging()` (2.2a), which drops every staging table and returns its space at once (about 210 MB for the full corpus, per 4.0's projection). It runs after the apply and its smoke checks (4.1b step 10) and needs the same lock gate. Rollback stays possible afterwards, because it rebuilds staging from the snapshot. Deleting the previous Qdrant collection and the snapshot, after the window, is a separate ops step.
  - **Staging read override, for the pre-cutover eval (4.2).** A new API setting `CORPUS_READ_SCHEMA` (`services/api/app/config.py`, default `public`). When it is `staging`, `app/db.py:42-52` creates the pool with `server_settings={"search_path": "staging, public", "default_transaction_read_only": "on"}`. The corpus tables in `staging` have the live names, so every unqualified query reads the staged corpus and every user table still resolves to `public`, and the session cannot write. `corpus_schema` (2.2b) probes columns in `current_schema()`. Paired with `QDRANT_READ_COLLECTION=chunks-<publish id>` (2.2b), the in-process eval harness (`services/api/scripts/run_eval_suite.py`, which persists nothing) searches the staged corpus exactly as production will. The deployed API refuses to start when the setting is anything but `public` (a check in the `app/main.py` lifespan), so production can never read staging.
  - **Writer code.**
    - `writers/reader_writer.py`: delete `clear_collection`, `prune_missing_chunks` and `prune_missing_documents`. `write_document` becomes `write_staged_document(conn, doc)` and writes only into `staging.*`, with the new document facts, works and passage fields.
    - `publication.py`: the `ReaderStore` and `SearchIndex` protocols (`:85-102`) lose `wipe`, `prune_documents`, `reset` and `prune`. `PostgresReaderStore` (`:251-276`) and `QdrantSearchIndex` (`:279-301`) become staging stores. `_validate_build` (`:224-248`) moves into the report as a warning section, since retirements are now explained one by one rather than capped at 10%.
    - `writers/qdrant.py`: remove `QDRANT_COLLECTION` (`:15`); every function takes the collection name. Remove `delete_collection_points` (`:62-67`) and `prune_missing_points` (`:88-108`) from the publish path. Add `alias_target(client, alias)`, `copy_points(client, source, target, ids=None)` (scroll with vectors and payload, then upsert) and `switch_alias(client, alias, new, old)`.
    - `qdrant_schema.py`: replace `CHUNKS` and `recreate_chunks` (`:12`, `:17-29`) with `create_chunks_collection(client, name)`. It refuses with `SystemExit` when `name` already exists or is an alias, creates the collection with today's vector and HNSW settings (`:21-27`), and creates payload indexes `collection`, `genre`, `issuer`, `document_id` (keyword) and `searchable` (boolean, D5). `on_disk` vectors follow 4.0's decision.
    - `writers/search_writer.py:build_point` (`:39-63`): the point ID is `Passage.id`. Add `genre`, `issuer`, `searchable` and `embed_sha256` to the payload. `author` becomes the author shown to users, which is `passage_author` when set, then the work's author, then the document's. `write_document` (`:83-101`) takes the target collection and a vector-reuse lookup.
    - `datapipeline/model.py`: `Document` gains the 2.2a document facts and `works`; `Passage` gains `id` (from the passage registry), `searchable` (default `True`), `language`, `work_key`, `passage_author`, `note`.
    - `datapipeline/config.py`: add `QDRANT_WRITE_COLLECTION` (default unset, meaning `chunks-<publish id>`) and `QDRANT_LIVE_ALIAS` (default `chunks_live`).
  - **Docs.** Rewrite `datapipeline/README.md` ("Publish one collection", "Narrow repair commands") and `datapipeline/SOURCES.md` ("Publishing a collection") around stage, report, apply, switch, rollback and cleanup. Update the datapipeline line in the repo `CLAUDE.md` Quick Commands, which today shows `run_collection.py --target both`.
- **Acceptance checks:**
  - New `datapipeline/tests/test_stage_apply.py`, run against a throwaway local Postgres with 0037, 0038 and 0039 applied, the way `datapipeline/tests/test_reader_writer_outline.py` starts one, and against an in-memory Qdrant (`AsyncQdrantClient(location=":memory:")`; whether local mode supports aliases is unverified, and a fake alias store is the fallback):
    - `test_stage_writes_only_staging_and_a_new_collection`: a statement log shows no INSERT, UPDATE or DELETE on `public` tables, and the aliased collection is unchanged.
    - `test_apply_issues_no_delete`: the statement log of an apply that retires rows contains no DELETE on `chunks` or `documents`.
    - `test_changed_text_keeps_its_id`: a bookmark and a retrieval on a passage whose text changed under the same anchor still point at it, and it returns the new text (D1).
    - `test_rebuilt_anchor_keeps_the_frozen_id`: a unit whose anchor changes from a label slug to a structural anchor keeps the ID the passage registry holds; no redirect and no retirement is produced (D1).
    - `test_every_live_id_is_kept_or_explained`: a build that drops a live ID with no registry entry and no redirect fails the report, and one that re-keys a known unit fails it too.
    - `test_only_unknown_units_get_new_ids`: a restored verse gets a new ID from `identity.passage_id`, and the stage lists it.
    - `test_new_ids_are_inserted` and `test_removed_ids_are_retired_with_tombstones`, with the user rows still present.
    - `test_unexplained_retirement_stops_the_stage` (D4), and `test_failed_apply_leaves_live_untouched`, which forces a failure after step 4 and asserts live rows are byte-identical to before.
    - `test_redirects_written_for_renumbered_and_split`.
    - `test_retired_positions_never_collide`: two successive publishes that each retire rows of the same document, and a third that adds passages, all succeed.
    - `test_reappearing_id_is_unretired`.
    - `test_outline_refreshed_in_the_same_transaction`: no reader query between commit and refresh can see a stale `chunk_count`.
    - `test_every_passage_is_a_point_with_payload_facts`: the new collection has one point per staged passage, with `collection`, `genre`, `issuer` and `searchable` equal to staging, including `searchable = false` points.
    - `test_create_collection_refuses_existing_name_and_alias`.
    - `test_unchanged_passage_copies_its_vector`: no embedding call for a passage whose `embed_sha256` matches.
    - `test_apply_calls_user_remap_in_the_transaction`: a fake `UserDataRemap` sees the same connection and transaction, and a failure inside it rolls the whole apply back.
    - `test_apply_refuses_referenced_redirects_without_remap`.
    - `test_single_collection_publish_copies_other_collections`.
    - `test_alias_switch_is_one_call`.
    - `test_rollback_apply_restores_rows_alias_and_outline`: after apply, cleanup and rollback, every corpus row equals the before-snapshot except the rows the publish inserted, which are retired with `rolled_back` tombstones; the alias points at the previous collection.
    - `test_cleanup_drops_staging_only`: after `cleanup`, the staging tables are gone, every `public` table is unchanged, and the next `stage` recreates them.
    - `services/api/tests/test_staging_read_override.py`: with `CORPUS_READ_SCHEMA=staging` the pool's `search_path` is `staging, public`, a write raises a read-only error, and the app lifespan refuses to start.
    - `test_apply_refuses_without_lock_match`, `test_loopback_targets_pass_the_lock`, `test_apply_refuses_stale_report`.
  - `datapipeline/tests/test_run_collection.py::test_live_publish_points_to_publish_py`, and the removed flags are rejected.
  - Existing tests that exercised `clear_collection`, the prune functions, `--wipe-reader` or `--reset-search-index` are removed or rewritten against staging, and the PR lists each one.
  - Local rehearsal (D8). On a local Postgres restored from a production `pg_dump` and a local Qdrant seeded by copying the production points read-only, run stage, report, apply, cleanup and rollback for one collection (catechism, about 809 passages), then for all collections. Run the eval harness once against staging through the read override. Record the apply transaction's duration, the peak database size, and the report's count of live IDs kept, retired and redirected. Then stage the same build a second time and confirm it makes no embedding call. The counts of `retrievals`, `bookmarks`, `retrieval_labels`, `guest_trial_retrievals` and `reading_progress` are equal before apply, after apply and after rollback. The dump is deleted afterwards.
  - PR description must include the rehearsal timings and sizes, the apply duration for all collections, the list of removed CLI flags, and the sentence "No code path left in the datapipeline deletes a live chunk or document row."
- **Production safety:** Merging changes no live data, and the publish lock holds every live path. After this PR no datapipeline path can delete a live chunk or document, so the cascade into user tables cannot fire from a publish. A stage into production writes only the `staging` schema and a Qdrant collection no alias points at, which users never read. But staging carries the live indexes, including the full-text index the eval needs, so it adds about 210 MB (4.0's projection) to a database already at 401 MB of a 500 MB Free plan limit, and 4.0 puts the apply's peak at 490 to 590 MB. So no production stage runs before 4.0's compaction and its Pro decision, and `cleanup` runs as soon as the apply is checked. The read override cannot reach production, because the deployed API refuses to start with it. The apply is one transaction. Readers keep seeing the old rows until commit (MVCC). Moving positions takes row locks that make a concurrent bookmark or retrieval insert on the same passage wait until commit, so the apply runs in 4.1b's quiet window, and its duration from the rehearsal decides whether that is acceptable. The alias switch is atomic, and the rollback apply is one command within the window.
- **Needs Carter:**
  - Approval of the `pg_dump` for the local rehearsal (D8).
  - For each production stage and apply, a reviewed change to `PUBLISH_LOCK.json` naming the publish ID. The first is P4's 4.1b.
  - The first production stage waits for 4.0 (storage and the Pro decision); approve its embedding cost (about 11 million tokens).
  - The rollback window length (4.1b).
  - Whether to do the On the Incarnation early retirement below.
- **Out of scope:** The user-data remap's rules and merge policy (4.1a supplies the implementation this item calls). The cutover runbook, backups and smoke checks (4.1b). The V5 `stages/` engine, which stays behind the lock (0.4). Hard-deleting retired rows and deleting old Qdrant collections (ops after the rollback window). Genre and issuer filters in the API (5.1a).

#### Optional ops step: early retirement of On the Incarnation (D7 exception, 1.8d)

- **What:** D7 allows one change to live data before Phase 4, if Carter approves it. Lawson's 1944 translation of On the Incarnation is under copyright (1.8d), so its 47 passages and its document (`cf235300-e37d-5a7a-a421-f50efff38355`) may be retired early. They are retired, not deleted (D3). 1.8d's earlier recommendation of a deletion is replaced by this step.
- **How:** A removal-registry entry for the document and its 47 passage anchors, with `rule = 'other'`, `reason_code = 'translation_in_preparation'` and a public reason such as "This translation is being replaced with a public-domain one; the text returns when it is ready." Then `publish.py apply --retire-only --publish-id incarnation-withdraw`, which stages nothing new. In one transaction it retires the document and its 47 passages, writes their tombstones and refreshes the outline. It then sets `searchable = false` on the 47 points in the collection `chunks_live` targets, so each stays a point (D5), and switches no alias. Restart the API to clear the one-hour `/sources` cache.
- **Requires:** 0039 applied; 2.2b deployed with the alias in use; 2.4a and 2.4b deployed, so the reader shows the removal page and history shows the tombstone; a reviewed lock-file change naming `incarnation-withdraw`.
- **User impact (29 Sep):** 1 retrieval and 0 bookmarks point at the document's passages. The retrieval row is kept and restores as a tombstone.
- **At Phase 4:** The apply un-retires the document under the same ID with Robertson's text (1.8d), and the old passages get redirects to the new sections by 1.8d's mapping.

---

### 2.2b. Qdrant alias, searchable flag and retired filtering on the search path

- **Type:** PR, plus two ops steps
- **Depends on:** none to merge. Its Postgres filters take effect once 2.2a's 0039 is applied. The alias ops step needs Carter. 2.2w adds the datapipeline's `QDRANT_WRITE_COLLECTION` and the alias-aware collection creation.
- **Goal:** Make every publish, and its rollback, a single alias switch, and make search skip anything marked not searchable or retired. Users see no change today.
- **Current state:**
  - The Qdrant collection name is a constant, `QDRANT_COLLECTION = "chunks"` (`services/api/app/rag/qdrant_client.py:10`). It is used by vector search (`rag/steps/retrieve_vector.py:30-39`), the near-duplicate check that fetches embedding neighbors (`rag/dedup.py:199-205`, `client.retrieve(..., with_vectors=True)`) and the health check (`app/main.py:88-93`, `client.get_collection`).
  - Vector search filters only on `collection` (`retrieve_vector.py:33-35`).
  - Full-text search filters only on `collection` (`rag/steps/retrieve_fts.py:16-26`).
  - Summa stitching loads every passage of an article from Postgres with no visibility filter (`rag/steps/fetch_context.py:37-45`). Position backfill reads `chunks` by ID (`rag/steps/fetch_positions.py:59-60`) and is skipped on the degraded path, so it cannot be the only guard.
  - Qdrant holds one collection, `chunks`, 54,568 points of 1,536 dimensions, no alias (plan, 28 Sep). Payload fields written by `datapipeline/writers/search_writer.py:39-62` are `collection, document_id, document_title, author, content, reference, anchor, chapter_label, chapter_key, unit_label`. No `searchable` field exists.
  - An alias cannot share a name with a collection, so the alias is named `chunks_live` (D5).
  - Unverified whether the Qdrant server version accepts an alias name in `get_collection`. Search, retrieve and upsert accept aliases in current Qdrant documentation; the health call must be tested.
- **Changes:**
  - `services/api/app/config.py`: add `qdrant_read_collection: str = Field(default="chunks", validation_alias="QDRANT_READ_COLLECTION")`. The datapipeline's matching setting is `QDRANT_WRITE_COLLECTION` (2.2w); the two stay separate so the API never reads a collection that is still being built.
  - `rag/qdrant_client.py`: replace the constant with `def read_collection() -> str: return settings.qdrant_read_collection`. Update `retrieve_vector.py`, `dedup.py` and `main.py` to call it. Log the name at startup in `init_qdrant`.
  - `main.py` health check: resolve the name with `client.get_collection(read_collection())`; if the Qdrant test shows aliases are not accepted there, first map alias to collection with `client.get_collection_aliases` or `client.get_aliases`, then call `get_collection` on the target. Report `{"qdrant_read": <alias or name>, "qdrant_target": <collection>}` in `/health/search`.
  - New module `services/api/app/corpus_schema.py`, the one place that knows which 0039 objects exist:

    ```python
    @dataclass(frozen=True)
    class CorpusSchema:
        retired: bool       # chunks.retired_at and documents.retired_at exist
        searchable: bool    # chunks.searchable exists
        facts: bool         # documents.genre ... superseded_by exist
        works: bool         # document_works exists
        tombstones: bool    # corpus_tombstones exists
        redirects: bool     # corpus_redirects exists

    async def current() -> CorpusSchema   # one information_schema query, cached 300 s
    def visible(alias: str) -> str        # "AND <alias>.retired_at IS NULL", or "" without 0039
    def invalidate() -> None              # called on UndefinedColumnError / UndefinedTableError
    ```

    Probe once at startup (in the lifespan, after the pool) and lazily after the TTL. Any query that fails with `asyncpg.UndefinedColumnError` or `UndefinedTableError` calls `invalidate()` and retries once with the legacy SQL, as `routes/documents.py:123-132` does.
  - `retrieve_fts.py`: build `_SQL` from the schema. With `searchable`, add `AND c.searchable`. With `retired`, add `AND c.retired_at IS NULL AND d.retired_at IS NULL`. Without 0039, the SQL is byte-identical to today's.
  - `retrieve_vector.py`: add `must_not=[FieldCondition(key="searchable", match=MatchValue(value=False))]` to the filter. Points without the field do not match `must_not`, so they stay searchable. Every passage is a point (D5); a non-searchable passage is a point with `searchable = false`. Retired passages are either absent from the collection (2.2w never writes them into a new one) or carry `searchable = false` (the On the Incarnation early retirement), so this one filter covers both in Qdrant.
  - `fetch_context.py` (stitch): add `AND c.searchable` and the retired predicate when present. A stitched part that is hidden is dropped; when no part is left, the card has no attachment, which is today's behavior on a stitch failure.
  - `fetch_positions.py`: select `searchable` and `retired_at` when present and return which IDs are hidden. `pipelines/runner.py` drops a vector candidate whose Postgres row is hidden or missing. This is defense in depth for a Qdrant point that disagrees with Postgres, including the seconds between a 2.2w apply and its alias switch. On the degraded path it is skipped and the Qdrant filter alone applies.
  - Ops step 1 (Carter), after the PR is deployed with the default `chunks`: create the alias `chunks_live` pointing at `chunks` with `update_collection_aliases([CreateAliasOperation(create_alias=CreateAlias(collection_name="chunks", alias_name="chunks_live"))])`. Create the boolean payload index on `searchable` on `chunks` (builds an index; deletes nothing).
  - Ops step 2 (Carter): set `QDRANT_READ_COLLECTION=chunks_live` in the API's Railway environment and restart. Check `/health/search` reports the alias and the `chunks` target.
- **Acceptance checks:**
  - `services/api/tests/test_retrieve.py`: `test_search_vector_excludes_only_explicit_unsearchable` asserts the filter has `must` on collection and `must_not` on `searchable == False`, and nothing else. `test_search_vector_uses_configured_read_collection` sets `QDRANT_READ_COLLECTION=chunks_live` and asserts `collection_name == "chunks_live"`.
  - New `tests/test_retrieve_fts_sql.py`: with a schema lacking 0039 the SQL equals today's text exactly; with 0039 it contains the searchable and retired predicates. A real-SQL variant on `pg_cluster` seeds a searchable row, a `searchable = false` row, a retired row and a row in a retired document, all matching the same term, and asserts only the first returns.
  - `tests/test_stitch.py`: `test_unsearchable_parts_are_not_attached` and `test_retired_parts_are_not_attached`.
  - `tests/test_dedup.py`: `test_neighbor_fetch_reads_configured_collection`.
  - `tests/test_startup_wiring.py`: health reports alias and target.
  - A runner test that a vector hit whose Postgres row is retired is dropped.
  - Alias behavior against a real server: a test marked `qdrant_live` (skipped unless `QDRANT_TEST_URL` is set) runs against `docker run qdrant/qdrant` at the production server version, creates `chunks` with 3 points (one `searchable=false`, one without the field), creates alias `chunks_live`, and asserts `query_points`, `retrieve` and the health call all work through the alias, and that the `must_not` filter returns the two expected points. The PR records the server version tested.
  - PR description must state the rollout order (merge, ops 1, ops 2), the rollback (unset `QDRANT_READ_COLLECTION`), and the result of the live-Qdrant test.
- **Production safety:** With the default `chunks`, the API reads exactly the collection it reads today. No live point has a `searchable` field, so the `must_not` clause matches nothing. Before 0039 is applied, `corpus_schema` reports nothing and the SQL is unchanged. After 0039 is applied, every row is searchable and none is retired, so the predicates keep every row. Creating an alias changes nothing for a client that does not use it. Switching the env var to the alias reads the same collection. From then on, 2.2w's apply switches `chunks_live` to its new collection, and rollback switches it back. If 2.4a deploys before this item, 2.4a still works, because each item adds its own predicates through the same `corpus_schema` module; whichever merges second reuses it.
- **Needs Carter:** Ops step 1 (create the alias and the `searchable` payload index) and ops step 2 (Railway env var and restart). Both touch live infrastructure.
- **Out of scope:** Building new collections, on-disk vectors and quantization (2.2w, 4.0, 4.1b). Genre and issuer filters in the API (5.1a); 2.2w writes and indexes the payload fields. The `facets` and `questions` collections, which the API does not read.

---

### 2.2c. search_vector rebuild

- **Type:** decision
- **Depends on:** 2.2a (for the searchable and retired columns the decision relies on)
- **Goal:** Decide whether the full-text index needs rebuilding for the cleanup, and record why, so nobody runs a 380 MB table rewrite without cause.
- **Current state:**
  - `chunks.search_vector` is `tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED` with a GIN index (`supabase/migrations/0004_v2_documents_chunks.sql:26-27, 40`). Postgres recomputes it on every insert and every update of `content`.
  - It is the only FTS column the API queries (`retrieve_fts.py:23-24`). `annotation_vector` (0019) is written by enrichment only.
  - Storage on 28 Sep: `search_vector` about 49 MB of 380 MB; TOAST 203 MB (plan).
  - The plan gives no rationale for 2.2c. The likely concerns are listed below with what already handles each.
- **Changes:** Recommended decision, no DDL:
  - Text fixes in P1 (joined paragraphs, stripped notes) reach FTS at the 2.2w apply, because the apply updates `content` in place (D1) and the column is generated from it.
  - Non-English passages leave FTS through the `searchable` predicate (2.2b), not through the tsvector. Making the generated expression depend on `searchable` would need `DROP COLUMN` and `ADD COLUMN`, which rewrites the table under an exclusive lock.
  - Retired passages leave FTS through the retired predicate (2.2b).
  - `staging.chunks` is created with the live shape, including the generated `search_vector` and its GIN index (2.2a), because the pre-cutover eval searches staging. `cleanup` (2.2w) drops it after the apply.
  - Space left by earlier rewrites is reclaimed by 4.0's `VACUUM FULL`, which also rebuilds the GIN index.
  - A post-cutover check is added to the 4.2 comparison: `SELECT count(*) FROM chunks WHERE search_vector IS DISTINCT FROM to_tsvector('english', content)` must return 0.
  - If Carter wants title or author weighting in FTS later, that is a retrieval follow-up with its own eval, not part of the cleanup.
- **Acceptance checks:** The decision is recorded in the plan's Decision log by Carter. The post-cutover query above is added to the 4.2 checklist.
- **Production safety:** Nothing changes.
- **Needs Carter:** Confirm the no-DDL decision, or name the missing concern this item was meant to cover.
- **Out of scope:** Changing the text search configuration, weighting, or `annotation_vector`.

---

### 2.3. Document facts in the registry

- **Type:** PR (registry fields, validation, and the facts section of the release report)
- **Depends on:** 2.1 (work registry with frozen IDs), 0.2 (rights inventory, for source credits), 2.2a (columns), 2.2w (the writer that stages them). 1.3b decides corrected papal genres; this item carries whatever 1.3b decides.
- **Goal:** Every document gets its real genre, issuer, display date, translation, source credit and, where a rule F text is superseded, its supersession link, so cards and the reader can show them and 5.1a can filter on genre and issuer. The values are written by 2.2w into staging and reach users at the Phase 4 apply (D7).
- **Current state:**
  - Empty fields measured 29 Sep, by collection:

    | Collection | Docs | No year | No translation | No author |
    |---|---|---|---|---|
    | apostolic-exhortations | 30 | 0 | 30 | 0 |
    | bible | 73 | 73 | 0 (WEB-C) | 73 |
    | canon-law | 1 | 0 | 1 | 0 |
    | catechism | 1 | 0 | 1 | 0 |
    | church-fathers | 128 | 128 | 128 | 0 |
    | councils | 36 | 0 | 36 | 36 |
    | encyclicals | 131 | 0 | 131 | 0 |
    | medieval | 6 | 0 | 6 | 0 |
    | papal-documents | 14 | 0 | 14 | 0 |
    | summa | 1 | 1 | 1 | 0 |

  - `document_type` exists in `metadata` for 16 documents only. `pope` is in `metadata` for 175.
  - Today's writer upserts `id, collection, title, translation, author, year, metadata` only (`datapipeline/writers/reader_writer.py:99-106`).
  - Anselm's three works all carry `year = 1099`; the plan corrects them to 1076, 1077-78 and 1098 (that fix belongs to 1.9; this item carries the values).
- **Changes:**
  - Registry (2.1's tracked file): add per-document fields `genre, issuer, year, date_display, translation, source_credit, certainty, attribution_note, notes, clavis_ref, superseded_by`, and per-work entries `{work_key, ordinal, title, author, certainty, attribution_note, notes, date_display, year, genre, clavis_ref, anchors: [first, last]}`. Work boundaries are anchor ranges, never positions (D4, D6). Validation in the registry loader:
    - `certainty` is one of the four values.
    - `genre` is one of the D5 words seeded in `corpus_genres` (papal, Roman Curia, catechisms and law, writers, and `other`), lowercase and hyphenated, or null where no genre applies.
    - `source_credit` is present for every document (source from 0.2).
    - `year` is an integer or null.
    - `superseded_by` names a registered document.
  - Value rules:
    - `translation`: the edition or translator shown to users, for example `Ante-Nicene Fathers (1885-1896)`, `Nicene and Post-Nicene Fathers, Series I`, `Vatican English`, `WEB-C` kept for the Bible (the web maps codes to names, `apps/web/src/components/sources/SourcesPage.tsx:12`). The `(collection, title, translation, author)` unique key allows this.
    - `issuer`: the pope for papal documents (from `metadata.pope`), the council for council documents, `Holy See` for the Catechism and the Code.
    - `year` stays the sortable integer; `date_display` carries ranges and "c.".
    - `source_credit`: exactly the wording 0.2's rights inventory records per source. If 0.2 agrees, vatican.va texts get `Text: Libreria Editrice Vaticana` and CCEL ThML texts get `Sourced via CCEL.org`. Never derived from a ThML `<description>`.
  - `datapipeline/model.py` fields and the staging writer are 2.2w's; this item fills them from the registry in each adapter's document construction.
  - Release report (0.1c, staged mode in 2.2w): a "Document facts" section with a per-field, per-collection count of values that differ from live, and the list of documents whose `author` changes. This replaces the backfill script an earlier draft proposed; there is no separate live write (D7).
- **Acceptance checks:**
  - Registry validation tests: every document has `source_credit`; every `genre` is a D5 word; every work's anchor range resolves in a build; no `<description>` text appears in any registry field (checked against the extracted blurbs of the vendored ThML files).
  - `datapipeline/tests/test_stage_apply.py` (2.2w) gains `test_document_facts_reach_staging_and_live_after_apply`.
  - Locally, the staged report against a fresh snapshot shows the facts diff. The PR description pastes the counts per field and per collection.
- **Production safety:** Nothing reaches live data before the Phase 4 apply. At the apply, the new columns are filled in the same transaction as the text, and the Qdrant payload carries the same author, genre and issuer, so Postgres and Qdrant agree from the first second. If 2.4a is not yet deployed, the new columns are simply unread.
- **Needs Carter:** The source credit wording where 0.2 has not settled it.
- **Out of scope:** Author corrections such as "Tertullian: Part Fourth." (1.10a, 1.8c), council authors (1.2), Anselm's date values (1.9), labels and certainty values themselves (3.2), genre and issuer filters (5.1a).

---

### 2.4a. API payloads, tombstones and redirects

- **Type:** PR
- **Depends on:** 2.2a merged (applied or not; the API tolerates both). Shares `corpus_schema.py` with 2.2b; whichever merges first creates it.
- **Goal:** The API sends each result's translation, date, attribution, certainty, notes, language, quoted author and source credit. Retired passages and documents come back as tombstones instead of disappearing, and moved ones come back as redirects. The reader, `/sources`, history restore and bookmarks hide retired rows or mark them.
- **Current state:**
  - The SSE `chunk` event's `source` carries `collection, document_title, author, reference, document_id, anchor, chapter_key, unit_label` only (`services/api/app/rag/pipeline.py:369-403`). The Pydantic mirror is `ChunkSource` (`app/models/search.py:21-35`), the TS mirror `ChunkSource` (`apps/web/src/lib/search-stream.ts:1-20`), which declares an optional `metadata` the API never sends.
  - History restore joins `retrievals → chunks → documents` (`routes/search.py:330-343`) and reports `results_unavailable` when rows are missing (`:380-385`). Bookmarks join the same way (`routes/bookmarks.py:161-167`).
  - The reader reads `documents`, `document_chapters` and `chunks` with no visibility filter (`routes/documents.py:28-70, 227-243`); a missing document is a 404 "Document not found" (`:130-131`). Guest reader access joins `guest_trial_retrievals → chunks` (`:91-101`).
  - `/sources` lists every document (`routes/sources.py:21-36`) and caches for 1 hour (`:16-18`). Reading progress joins `chunks` for the chapter label (`routes/reading_progress.py:33-45`).
  - `DocumentResponse` has `id, collection, title, author, year, translation, metadata, chunk_count` (`app/models/documents.py:5-13`). `ReaderPassage` has no language or note (`:36-43`).
- **Changes:**
  - Models (`app/models/search.py`, `app/models/documents.py`, `app/models/bookmarks.py`), all new fields optional with default `None`:

    ```python
    class DocumentFacts(BaseModel):
        year: Optional[int] = None
        date_display: Optional[str] = None
        translation: Optional[str] = None
        genre: Optional[str] = None
        issuer: Optional[str] = None
        certainty: Optional[Literal["genuine", "disputed", "pseudonymous", "anonymous"]] = None
        attribution_note: Optional[str] = None
        notes: Optional[str] = None
        source_credit: Optional[str] = None
        superseded_by: Optional[str] = None
        superseded_note: Optional[str] = None
        work_title: Optional[str] = None   # from document_works when the passage has a work_key

    class Tombstone(BaseModel):
        entity: Literal["document", "passage"]
        rule: str
        reason_code: str
        public_reason: str
        church_act: Optional[str] = None
        retired_at: datetime
        title: Optional[str] = None
        author: Optional[str] = None
        reference: Optional[str] = None

    class Redirect(BaseModel):
        kind: Literal["moved", "split", "merged", "renumbered"]
        document_id: str
        anchor: Optional[str] = None
        chunk_id: Optional[str] = None
    ```

    `ChunkSource` and `BookmarkSource` gain `facts: Optional[DocumentFacts]`, `language: Optional[str]`, `passage_note: Optional[str]`, `passage_author: Optional[str]`. `ChunkResult` and `BookmarkResponse` gain `status: Literal["current", "moved", "removed"] = "current"`, `tombstone: Optional[Tombstone]`, `redirect: Optional[Redirect]`. `DocumentResponse` gains `facts`, `works: list[WorkInfo]` and `status`. `ReaderPassage` gains `language`, `note`, `work_key`, `passage_author`.
  - Work-level fields override document-level ones in `DocumentFacts` when a passage has a `work_key` (author and certainty for "Dubious or Spurious Writings." come from the work, not the document). A passage's `passage_author` overrides both for the author shown.
  - New step `rag/steps/document_facts.py`, called from `pipeline.py` after ranking and before the chunk events. One query per search: `SELECT ... FROM documents d WHERE d.id = ANY($1)` plus `document_works` for the `(document_id, work_key)` pairs and `chunks.language, note, work_key, passage_author` for the result IDs. The card's author comes from this query, not from the Qdrant payload. Timeout 1 s; on failure it records via `degradation.record_recovery` (as `fetch_context` does) and events go out without `facts`. Guest search uses the same pipeline (`routes/guest_search.py:359`), so guests get the fields too.
  - Chunk event `source` adds `facts`, `language`, `passage_note`, `passage_author`. The event shape change is additive.
  - Visibility predicate. `corpus_schema.visible(alias)` returns `AND <alias>.retired_at IS NULL`, or an empty fragment when 0039 is absent. Apply it to:
    - `routes/documents.py`: `_DOCUMENT_SQL` and fallbacks, the legacy TOC, first chapter and chapter key queries, the anchor lookup at `:227-229` and the passage query at `:239-243`. `document_chapters` is already built from non-retired rows by 2.2a's function.
    - `routes/sources.py`: hide retired documents. The one-hour cache is cleared by the API restart in 4.1b (and after the On the Incarnation early retirement).
    - `routes/reading_progress.py`: the chapter label lateral join uses visible rows; a progress row whose document is retired is left out of `GET /reading-progress` lists and returns `status: "removed"` with the tombstone on the single-document GET.
    - History restore and bookmarks do **not** filter; they join retired rows on purpose and mark them.
  - Tombstone and redirect resolution, in a new `app/corpus_lifecycle.py`:
    - `async def resolve_passages(conn, ids) -> dict[str, Resolution]`, where `Resolution` is `current`, `moved(redirect)` or `removed(tombstone)`. Order of checks: a row with `retired_at IS NULL` in a document with `retired_at IS NULL` is `current`; else a `corpus_redirects` row for the ID, following at most 3 hops, is `moved`; else a `corpus_tombstones` row is `removed`; else `current` (a retired row with no record is treated as today's behavior and logged as a warning, since 2.2w's D4 check should make it impossible).
    - `async def resolve_document(conn, doc_id, anchor) -> Resolution` with the same order, and for anchors the `entity = 'anchor'` redirects.
  - `routes/search.py:get_search_results`: after the existing join, call `resolve_passages`. `moved` results carry the redirect and the new passage's content and source; `removed` results carry `status: "removed"` and the tombstone and **no content** (see Needs Carter). `restore_status` counts moved and removed results as present, so a restore with removals is still `complete`.
  - `routes/bookmarks.py:list_bookmarks`: same resolution.
  - `routes/documents.py`: for a document that is not visible, `get_document`, `get_document_toc` and `get_document_reader` return HTTP 410 with body `{"detail": "removed", "tombstone": {...}}` when a document tombstone exists, HTTP 404 with body `{"detail": "moved", "redirect": {...}}` when a redirect exists, and today's 404 otherwise. An anchor that is no longer visible in a visible document returns the chapter from the anchor redirect with `highlight_anchor` set to the new anchor and a `redirected_from` field.
  - `require_document_access` for guests: keep the join, but also allow a document reached through a redirect from a passage the guest retrieved.
  - Explanations persisted in `retrievals.explanation` are returned unchanged for moved and removed results; the web decides whether to show them.
- **Acceptance checks:**
  - `tests/test_search_routes.py`: `test_restore_marks_removed_passage_with_tombstone_and_no_content`, `test_restore_follows_redirect_to_new_passage`, `test_restore_with_removal_is_complete`, `test_restore_without_0039_is_unchanged` (golden JSON of today's response), `test_restore_shows_corrected_text_for_same_id` (D1).
  - `tests/test_bookmarks.py`: removed and moved bookmarks, note preserved.
  - `tests/test_reader_chapter_endpoint.py` and `test_reader_outline_endpoints.py`: retired passages are not in the chapter; a retired document returns 410 with the tombstone; a redirected document returns 404 with `redirect`; an old anchor returns the new chapter and `redirected_from`; outline and fallback paths agree when some rows are retired.
  - `tests/test_sources_endpoint.py`: retired documents hidden.
  - `tests/test_reading_progress.py`: removed document leaves the list.
  - `tests/test_pipeline_persistence.py` or a new `test_document_facts.py`: chunk events include `facts` when 0039 exists; the author shown comes from Postgres when the payload disagrees; a failing facts query still yields chunk events without `facts` and records a recovery, not a degradation.
  - `tests/test_document_access_and_failures.py`: guest access through a redirect.
  - `tests/test_contract_models.py`: every new field optional; an event without them validates.
  - PR description must include before-and-after JSON for one search event, one restore and one reader response, and state that every added field is optional.
- **Production safety:** Before 0039 is applied, `corpus_schema` reports nothing, the facts step is skipped, no predicates are added and no resolution queries run, so every response is today's. After 0039 with nothing retired and no tombstones or redirects, every row is `current`, and the only change is that responses carry the extra optional fields; today's web ignores unknown fields. The 410 and redirect bodies can only occur after a 2.2w apply creates tombstones and redirects, and 2.4b must be live by then. Adding one query per search adds a few milliseconds (unverified; measure p95 before and after on the eval set).
- **Needs Carter:** Whether a removed passage shows its text anywhere after removal. Recommended is no text, with title, author, reference and one plain sentence of reason, with the Church act where one exists. The alternative keeps showing the text with a "removed from TheoCorpus" banner, which keeps the user's history intact but keeps excluded text on screen.
- **Out of scope:** Rewriting user rows to new IDs (4.1a). Changing any SSE event type or the `/v1/chat` contract. Genre filters (5.1a).

---

### 2.4b. Web cards, reader, bookmarks, history and the source credit

- **Type:** PR
- **Depends on:** 2.4a deployed (the web reads optional fields and works without them)
- **Goal:** Users see the translation, date and attribution of what they read, including labels such as "Pseudo-Justin" and "disputed", a quoted Father's name on a Catena Aurea passage, and any note (for example, that the Apostolic Canons reached the Latin West only as canons 1 to 50). The source credit shows only when a passage is opened, as the Decision log's "Source credits" row settles, which means the expanded search card after a click, the bookmark detail and the reader. It never shows on a collapsed result card. Removed and moved passages are explained instead of failing.
- **Current state:**
  - `ChunkCard` has a collapsed header (`apps/web/src/components/search/ChunkCard.tsx:249-305`, fixed height 96 px mobile and 68 px desktop) and an expanded body with the passage text (`:307-397`). The Bible translation badge reads `source.metadata?.translation` (`:227-230`), which the API never sends, so it never shows.
  - `BookmarkCard` always shows the passage text (`apps/web/src/components/bookmarks/BookmarkCard.tsx:151-153`); it is the bookmark detail view.
  - Reader: `DocumentOverview` shows `author · year · translation` (`apps/web/src/components/reader/DocumentOverview.tsx:186`); `ReaderChrome` shows the title (`ReaderChrome.tsx:77`); `ChapterSection` and `Passage` render headings and text with no metadata (`ChapterSection.tsx`, `Passage.tsx`).
  - `SourcesPage` shows author, year and translation per document (`SourcesPage.tsx:236-252`).
  - Reader load errors show a generic failure (`DocumentReader.tsx:197`, "Failed to load").
  - Restore status handling lives in `lib/search-experience/useSearchPageExperience.ts`.
- **Changes:**
  - `apps/web/src/lib/search-stream.ts` (the only SSE decoder): add `facts?: DocumentFacts | null`, `language?: string | null`, `passage_note?: string | null`, `passage_author?: string | null` to `ChunkSource`, and `status?`, `tombstone?`, `redirect?` to `ChunkResult`. Remove the unused `metadata` field. Types in `lib/api.ts` for `DocumentInfo`, `ReaderPassage`, `BookmarkChunkInfo`, `Bookmark`, `SearchResultsResponse` gain the same optional fields.
  - New pure module `apps/web/src/lib/attribution.ts` with unit tests:
    - `formatAttribution(author, facts, passageAuthor)` returns e.g. `Pseudo-Justin`, `Justin Martyr (authorship disputed)`, `Anonymous`, `Chrysostom, quoted in Aquinas's Catena Aurea`. `passageAuthor` wins when present.
    - `formatDate(facts, fallbackYear)` prefers `date_display`, then `year`.
    - `formatTranslation(code)` maps `WEB-C` and similar codes to names (move the map from `SourcesPage.tsx:12`).
    - `certaintyTag(certainty)` returns `null` for `genuine`, else a short tag (`disputed`, `pseudonymous`, `anonymous`).
  - `ChunkCard.tsx`:
    - Collapsed header, which is the result card. The author line uses `formatAttribution`, and a small certainty tag appears beside it when not genuine. Add the date after the author when it fits (`Augustine · 397-400`). No source credit, no notes, no translation in the header. Keep the fixed heights; truncate as today.
    - Fix the Bible badge to use `facts.translation`.
    - Expanded body, shown after a click. Below the text and above "Why this is relevant", one muted line for the translation, then the notes (`attribution_note`, document `notes`, `passage_note`, `superseded_note` with a link to the current text), then the source credit as the last line in `text-xs text-brand-muted`. Use tokens only, no new hex.
    - A passage with `language` other than English shows "This passage is in Latin; it is not included in search." in the expanded body. Search should never return one after 3.3, so this matters for bookmarks and history.
    - `status === "removed"`: render a tombstone card with title, author, reference, `public_reason` and `church_act`, no content, no bookmark or feedback buttons, and a "Why was this removed?" link to the About page anchor (5.7 fills it; until then link to `/about`).
    - `status === "moved"`: render normally from the new content, with a muted line "This passage was renumbered in a corpus update."
    - Copy action: citation uses `formatAttribution` so a copied Pseudo-Justin passage is not credited to Justin.
  - `BookmarkCard.tsx`: same notes, translation and source credit under the text; tombstone and moved states; keep the user's note editable in both.
  - Reader:
    - `DocumentOverview.tsx`: attribution line becomes `formatAttribution · formatDate · formatTranslation`; show certainty, notes, supersession and the list of works with their own labels when `works` is non-empty; source credit at the bottom of the header section.
    - `ChapterSection.tsx`: source credit once at the end of each loaded chapter section. When a chapter's passages belong to a work whose attribution differs from the document's, show the work's label under the chapter heading.
    - `Passage.tsx`: non-English passages get the language note above the text; `note` renders as a small muted paragraph after the passage; a `passage_author` renders as a small label above the passage.
    - `DocumentReader.tsx` and `lib/api.ts` reader fetchers: on 410 with a tombstone, show a removal page (title, author, reason, Church act, back button). On 404 with `redirect`, `router.replace` to the new document and anchor, keeping `from` and `returnKey`. On `redirected_from`, highlight the new anchor.
    - Guest reader shares these components (`isGuest`); no guest fork.
  - `SourcesPage.tsx`: use `formatAttribution` and `formatDate`; show a certainty tag.
  - History restore: `useSearchPageExperience.ts` treats `removed` and `moved` results as present; no "results unavailable" notice for them.
- **Acceptance checks:**
  - `ChunkCard.test.tsx`: the collapsed header shows attribution and certainty tag and never the source credit; the expanded body shows translation, notes and credit in that order; the Bible translation badge renders from `facts`; a Catena passage shows its quoted author; removed status renders the tombstone without content and without bookmark buttons; moved status shows the renumbered line; copy text uses the attributed author; a result with no `facts` renders exactly as today (snapshot).
  - `BookmarkCard.test.tsx`: credit under the text; tombstone keeps the note.
  - `DocumentReader.test.tsx`: 410 shows the removal page; 404 with redirect replaces the URL; credit appears once per chapter section.
  - `lib/attribution.test.ts` for each formatter.
  - `SearchPage.test.tsx`: a restore with a removed result shows no unavailable notice.
  - `npm run lint` (0 errors, no new warnings in touched files), `npm test`, `npm run build`.
  - PR description must include screenshots at 375 px and desktop, dark and light themes, of a collapsed card, an expanded card with a credit, a tombstone card, the reader overview with works, and the removal page.
- **Production safety:** Every new field is optional. Before 2.4a deploys, or before 0039 is applied, all fields are absent and the components render today's output, which the snapshot tests hold. Tombstones and redirects cannot exist until a 2.2w apply (the Phase 4 apply, or the On the Incarnation early retirement if Carter approves it), and this PR must be live before either (4.1b checklist item).
- **Needs Carter:** Confirm the tombstone wording pattern. Where the credit shows is settled by the Decision log.
- **Out of scope:** The About page rewrite (5.7). Genre and issuer filter controls (5.1a). Any change to search lifecycle state in `lib/search-experience/` beyond counting moved and removed results as present.

---

### 2.4c. About page factual fix

- **Type:** PR
- **Depends on:** none
- **Goal:** The About page stops naming authors who are not in the corpus.
- **Current state:**
  - `apps/web/src/components/about/AboutPage.tsx:14-15` (church-fathers) names "Ignatius of Antioch, Justin Martyr, Origen, Athanasius, Augustine, and John Chrysostom". `:16-17` (medieval) names "Anselm of Canterbury, Bonaventure, Hildegard of Bingen, and Duns Scotus" and says "roughly 9th through 15th centuries".
  - Live, 29 Sep: Chrysostom, Bonaventure, Hildegard and Duns Scotus have no documents. **Origen is in the corpus today** (3 documents, 932 passages) and leaves under rule A at P4; his name goes anyway because the removal is decided. Ignatius (21 docs), Justin Martyr (9), Athanasius (1), Augustine (5), Irenaeus (6) and Anselm (3) are present.
  - The medieval collection holds 6 documents: Boethius, Consolation of Philosophy (524); Anselm, Proslogium, Monologium, Cur Deus Homo; Bernard of Clairvaux, On Loving God (1128); Thomas à Kempis, Imitation of Christ (1441). So "9th through 15th centuries" excludes Boethius.
  - `:42` reads "church counsels" (should be councils).
  - The apostolic exhortations text cites Evangelii Gaudium, which is filed today under encyclicals (plan, 1.3 moves it). The claim about the document is true; leave it.
  - Both `/about` and `/guest/about` render this component (`apps/web/src/app/about/page.tsx`, `app/guest/about/page.tsx`).
- **Changes:** In `AboutPage.tsx` only:
  - church-fathers: "including Ignatius of Antioch, Justin Martyr, Irenaeus, Athanasius and Augustine."
  - medieval: "Works from Boethius (6th century) through the late Middle Ages, including Anselm of Canterbury, Bernard of Clairvaux and Thomas à Kempis." Adjust the period sentence to match.
  - Fix "counsels" to "councils".
  - Do not add counts; the full rewrite with counts from `/sources` is 5.7.
- **Acceptance checks:**
  - New `apps/web/src/components/about/AboutPage.test.tsx`: the rendered text contains none of "Origen", "Chrysostom", "Bonaventure", "Hildegard", "Scotus", "counsels".
  - `npm run lint`, `npm test`, `npm run build`.
  - PR description must list each removed name with the live query result showing it absent (or, for Origen, scheduled for removal under rule A).
- **Production safety:** Copy change in one static component. Nothing depends on the text.
- **Needs Carter:** Approve the replacement names. Nothing else.
- **Out of scope:** The "What's in TheoCorpus and why" rewrite (5.7). Collection renames (5.1b).

---

### 3.1. Removals under rules A to C and G

- **Type:** PR (removal-registry entries and adapter changes). Applied at the 4.1b cutover through the 2.2w apply.
- **Depends on:** R1 (rule A dating and Church-act check; decides Tertullian's To His Wife and On the Apparel of Women), 2.1 (the removal registry, D4), 2.2a, 2.2w (the writer that retires), 1.8a, 1.8b and 1.8c (editorial strips and the recension split, which share this item's registry entries). 2.4a and 2.4b must be deployed before the cutover. It does not depend on 4.1a; removed passages keep their rows, so no user row needs remapping for them.
- **Goal:** After the Phase 4 apply, the works the rules exclude are gone from search and the reader, each leaves a tombstone that says why in one sentence, and no user loses a saved search, bookmark, label or guest result.
- **Current state:**
  - Removal targets and their live document IDs (29 Sep). Positions locate partial targets in today's data; the registry records them by anchor.

    | Rule | Target | Document IDs (prefix) | Scope |
    |---|---|---|---|
    | A | Origen: Against Celsus, De Principiis, Letter to Gregory | `5a05852b`, `4c96eac3`, `9c052574` | whole |
    | A | Tertullian: De Fuga, Exhortation to Chastity, On Fasting, On Modesty, On Monogamy, On the Pallium, On the Veiling of Virgins | `d2b71f9f`, `e5d235f3`, `89201a06`, `6b70b67f`, `01abb5ad`, `d7f29587`, `17b7747f` | whole |
    | A | Tertullian: To His Wife, On the Apparel of Women | `3717ce05`, `e73bb326` | kept provisionally, pending R1 |
    | A | Novatian: On the Trinity, On the Jewish Meats | `0f23bbcf`, `2f22d9b5` | whole |
    | A | Novatian inside "Treatises Attributed to Cyprian on Questionable Authority." | `5d75dc92` | the works Treatise I and Treatise III (today positions 1 to 8 and 25 to 32) |
    | A | Tatian, Address to the Greeks | `356b9c9b` | whole |
    | A | Arnobius, Against the Heathen | `85e7153f` | whole |
    | A | Alexander of Lycopolis, Of the Manichaeans | `0d274c4c` | whole |
    | B | Apostolic Constitutions Books I to VII | `d72938c6`, `df17e279`, `df6fd2f7`, `aab0848e`, `49437294`, `f04e045b`, `fd6550b9` | whole |
    | B | Apostolic Constitutions Book VIII | `10d8d7c6` | everything before "The Ecclesiastical Canons of the Same Holy Apostles" (today positions 0 to 34); the canons (today 35 to 43) stay |
    | B | Six forged Ignatius letters (Maria of Cassobelae, Mary at Neapolis, Tarsians, Philippians, Antiochians, Hero) | `7073bae0`, `4fe41814`, `56add0dd`, `567be8a5`, `0311d705`, `5553da19` | whole |
    | B | Sectional Confession of Faith (Apollinaris, CPG 3645) | `44fd52c3` | the work Sectional Confession (today positions 0 to 23) |
    | B | Long recension text in the 7 "Shorter and Longer Versions" documents | `89853cef`, `c1bcdc39`, `bb72e2f6`, `fa2cd483`, `995d76f9`, `f9e64ef8`, `fc317c73` | text inside passages; split by 1.8c |
    | C | Pfaff fragments of Irenaeus XXXVI to XXXIX | `0066869a` | fragments XXXVI to XXXIX (today positions 37 to 40) |
    | C | Four medieval Latin Ignatius letters (CPG 1028) | `76b8b853`, `63e7f0b7`, `830a2c63`, `1a0a016b` | whole |
    | G | Editorial passages (Elucidations, translators' introductions and notices, "Argument" summaries that are editorial) | many | about 120 by the plan; a label heuristic finds 144 (chapter labels matching Elucidation, Translator, Introductory Note or Notice, Biographical, Argument); 1.8a to 1.8c settle the exact list |

  - User rows touching each target are in the table in the Cross-cutting design section. In total 54 retrievals, 6 guest rows, 0 bookmarks, 0 labels, 0 reading progress rows and 0 feedback rows for rules A to C; 3 retrievals for the rule G heuristic.
  - Today's writer deletes what a build no longer emits, which cascades (`reader_writer.py:36-81`); `clear_collection` deletes a whole collection (`:16-33`). 2.2w removes both.
  - CCEL `<description>` blurbs sit in the ThML header of the vendored files (for example `datapipeline/sources/medieval/consolation-of-philosophy.xml:11`). The adapters iterate `div1` elements in the body (`datapipeline/ingest/church_fathers.py:59`, `ingest/medieval.py:45`), and a live search for the four medieval blurbs' opening sentences found 0 passages. Checked for the 4 medieval files only; the Fathers files were not checked passage by passage.
- **Changes:**
  - Removal registry (2.1's file, D4): one entry per target, by document ID and anchor or anchor range, never by position, with `rule`, `reason_code`, `public_reason` and `church_act`. Whole-document targets list the document. `reason_code` vocabulary:
    - `condemned_by_name` (A, limit 1): Origen (Constantinople II, 553, anathema 11), Novatian (Roman synod under Pope Cornelius, 251, as reported by Eusebius, Church History 6.43).
    - `outside_communion_or_undated` (A, limit 3): Tertullian's 7 works (Benedict XVI, general audience of 30 May 2007, for the break), Tatian (Irenaeus, Against Heresies 1.28.1; Eusebius, Church History 4.28-29).
    - `before_baptism` (A): Arnobius (Jerome, Chronicle).
    - `non_christian_author` (A): Alexander of Lycopolis (van Oort 2012).
    - `forgery_heterodox` (B): Apostolic Constitutions (Council in Trullo, canon 2, confirmed by Nicaea II, canon 1), six Ignatius letters and the long recension (majority of standard scholarship), Sectional Confession (Caspari 1879, Lietzmann 1904).
    - `late_fabrication` (C): Pfaff fragments (Harnack 1900), medieval Latin Ignatius letters (CPG 1028).
    - `editorial` (G).
    - `translation_in_preparation` and `rolled_back` are used by 2.2w and D9, not by this item.
  - `public_reason` drafts, one sentence each, for Carter to approve. For Origen, "Removed because the Second Council of Constantinople (553) condemned Origen by name, and TheoCorpus excludes authors the Church has condemned by name." For rule G, "Removed because this text was written by a modern editor, not the author."
  - Adapters (`datapipeline/ingest/church_fathers.py`, `medieval.py`, `thml_doc.py`): skip every unit the removal registry lists. The adapter asks the registry; no author or title string matching in adapter code.
  - No writer change. 2.2w's stage step turns each registry entry into a staged tombstone, with its snapshot (`collection, title, author, reference, chapter_label`) taken from the live row, and its apply retires the rows. An ID that leaves the build with no registry entry and no redirect stops the stage (D4).
  - A regression check keeps ThML `<description>` text out of content. New `datapipeline/tests/test_thml_description_excluded.py` builds each ThML adapter's documents from fixtures containing a `<description>` and asserts no passage contains it. For vendored sources, the 0.1a coverage checks gain a rule that fails when any passage contains 40 or more consecutive characters of a file's `<description>`.
  - The release report (0.1c, staged mode in 2.2w) lists every retired ID with its registry entry and tombstone, and every user row pointing at one.
- **Acceptance checks:**
  - `datapipeline/tests/test_church_fathers.py`: building with the registry emits none of the removed units; Book VIII emits exactly the 9 canon passages; "Treatises Attributed to Cyprian" emits Treatises II and IV only (plus nothing editorial).
  - Registry test: every entry resolves to anchors present in today's snapshot, and none is keyed by position.
  - Local rehearsal (D8, with 2.2w): after stage and apply on a local restore of production, the counts of `retrievals`, `bookmarks`, `retrieval_labels`, `guest_trial_retrievals` and `reading_progress` are unchanged, except merges documented by 4.1a, and the removed IDs return tombstones through `/searches/{id}/results`.
  - The measurement query, to rerun at cutover and paste into the PR and the 4.1b log:

    ```sql
    -- rm: one row per passage to remove, grouped by rule target (build from the registry)
    SELECT grp,
           count(DISTINCT rm.id) AS passages,
           (SELECT count(*) FROM bookmarks b WHERE b.chunk_id IN (SELECT id FROM rm r WHERE r.grp = rm.grp)) AS bookmarks,
           (SELECT count(*) FROM retrievals x WHERE x.chunk_id IN (SELECT id FROM rm r WHERE r.grp = rm.grp)) AS retrievals,
           (SELECT count(*) FROM retrieval_labels x WHERE x.chunk_id IN (SELECT id FROM rm r WHERE r.grp = rm.grp)) AS labels,
           (SELECT count(*) FROM guest_trial_retrievals x WHERE x.chunk_id IN (SELECT id FROM rm r WHERE r.grp = rm.grp)) AS guest_rows,
           (SELECT count(*) FROM product_feedback x WHERE x.chunk_id IN (SELECT id FROM rm r WHERE r.grp = rm.grp)) AS feedback
    FROM rm GROUP BY grp ORDER BY grp;
    ```

  - Baseline eval (0.3) targeted questions for each removed author return no passage from them after cutover (4.2).
  - PR description must include the registry diff, the per-target counts, the tombstone wordings, and the R1 outcome for the two Tertullian works.
- **Production safety:** Merging changes only the registry and adapters; the publish lock (0.4) keeps them away from production until the Phase 4 apply. At the apply, removed rows are retired and stay in the tables, so every user foreign key survives, and 2.4a returns tombstones for them. 2.2w's rollback un-retires them with nothing lost. If this merged before 2.4a and 2.4b were deployed, nothing would happen, because nothing is applied until P4; the 4.1b checklist blocks cutover until both are live.
- **Needs Carter:** R1's result for To His Wife and On the Apparel of Women. Approval of each `public_reason` sentence. The display policy for removed text (2.4a). The rule G final list after 1.8a to 1.8c.
- **Out of scope:** Label changes for works that stay (3.2). The split of the Shorter and Longer documents and the Ignatius greetings (1.8c). Hard-deleting retired rows (post-cutover ops). The About page section on excluded authors (5.7).

---

### 3.2. Labels, certainty and notes for works that stay

- **Type:** PR (registry values; written by 2.2w; displayed by 2.4b). Takes effect at the Phase 4 apply.
- **Depends on:** 2.1, 2.2a, 2.3 (the registry fields), 2.2w (the writer), 2.4a and 2.4b (to be visible). R1 (rule A) and R4 (book contents) for the Refutation of All Heresies.
- **Goal:** Doubtful works say so. A user reading the Hortatory Address sees "Pseudo-Justin"; a user reading the Twelve Topics sees it is not Gregory's; a user reading the Didache sees it is anonymous; the Summa Supplement says it was compiled after Aquinas died.
- **Current state:**
  - Every document has only `author` for attribution; no certainty or note exists anywhere. Authors live: Justin Martyr for the Hortatory Address (`3f1d7ed1`, 41 passages), On the Sole Government of God (`dd54c7cc`, 6), The Discourse to the Greeks (`abd0e330`, 5), On the Resurrection, Fragments (`24b54b57`, 12); "Gregory Thaumaturgus." for Dubious or Spurious Writings (`44fd52c3`, 80); Barnabas (`1d83b302`); Mathetes for Diognetus (`abf69de0`, 13); "Hippolytus." for the Appendix of dubious pieces (`a2b36c64`, 57); Ignatius for The Martyrdom of Ignatius (`841b4e0a`, 8); Victorinus (`e847b8bb`, 39); Methodius for Oration on the Palms and the homily fragments (`5f210d1e`); Pamphilus (Exposition of the Acts, today positions 2 to 5).
  - In ANF volumes, one document holds several works, and chapter keys repeat across works ("Section I" occurs at positions 0 and 43 of `44fd52c3`). Work boundaries are therefore anchor ranges, which is why 2.2a adds `chunks.work_key` and `document_works` (D6).
  - Unverified which document holds the Refutation of All Heresies (CPG 1899), the Muratorian fragment, On the Glory of Martyrdom, Exhortation to Repentance, Canons of Hippolytus, the Acts of Archelaus and the Lactantius Poem on the Passion. 2.1's registry must locate each by CPG number before this PR.
- **Changes:** Registry values, per the plan's "Labels for works that stay" and D10, using 2.2a's fields. `author` is the rule H credit shown to users; `certainty` is the label; `clavis_ref` the CPG number. Where the table names a work inside a document, the values go on the `document_works` entry.

  | Work | author | certainty | attribution_note or notes | clavis_ref |
  |---|---|---|---|---|
  | Hortatory Address to the Greeks | Pseudo-Justin | pseudonymous | "Not by Justin Martyr. Riedweg (1994) proposes Marcellus of Ancyra, with a question mark." | CPG 1083 |
  | On the Sole Government of God | Pseudo-Justin | pseudonymous | "Not by Justin Martyr; date uncertain." | CPG 1084 |
  | Discourse to the Greeks | Pseudo-Justin | pseudonymous | "Not by Justin Martyr." | CPG 1082 |
  | On the Resurrection, Fragments | Justin Martyr | disputed | "Authorship disputed; Heimgartner (2001) assigns it to Athenagoras." | CPG 1081 |
  | Twelve Topics on the Faith (work in `44fd52c3`) | Pseudo-Gregory Thaumaturgus | pseudonymous | "Not by Gregory Thaumaturgus." | CPG 1772 |
  | On the Subject of the Soul, to Tatian | Gregory Thaumaturgus | disputed | | CPG 1773 |
  | Four Homilies, On All the Saints (works in `44fd52c3`) | Pseudo-Gregory Thaumaturgus | pseudonymous | | CPG 1775 to 1777 |
  | Refutation of All Heresies | Hippolytus | disputed | "Attributed to Hippolytus in modern times; the attribution is disputed." Held until R1 settles rule A for its author and R4 settles which book contents are authorial. | CPG 1899 |
  | Appendix pieces of Hippolytus | Pseudo-Hippolytus | pseudonymous | | per piece |
  | Didache | Anonymous | anonymous | | |
  | Epistle to Diognetus | Anonymous | anonymous | work note on chapters 11 and 12: "Chapters 11 and 12 are a later addition by another hand." | CPG 1112 |
  | Muratorian fragment | Anonymous | anonymous | | |
  | On the Glory of Martyrdom; Exhortation to Repentance | Anonymous | anonymous | | |
  | Canons of Hippolytus | Anonymous | anonymous | "An Egyptian church order, about 336 to 340." | CPG 1742 |
  | Epistle of Barnabas | Pseudo-Barnabas | pseudonymous | | |
  | Acts of Archelaus | Hegemonius | genuine | | |
  | Oration on the Palms; homily on the Cross fragments (Methodius) | Methodius | disputed | "Doubtful." | |
  | Poem on the Passion (Lactantius) | Lactantius | disputed | "Doubtful." | |
  | Exposition of the Chapters of the Acts (Pamphilus) | Pamphilus | disputed | "Doubtful." | |
  | Martyrdom of Ignatius | unchanged (today's author label is kept, D10) | not set | "A legendary account." | |
  | Seventh Council of Carthage under Cyprian | Cyprian | genuine | "Its ruling on rebaptizing heretics was not adopted by the Church." | |
  | Summa Supplement and its appendix | Thomas Aquinas | genuine | "Compiled after Aquinas's death from his earlier writings." Applied as a work over the Supplement's 4,084 and the appendix's 82 passages. | |
  | Victorinus, Commentary on the Apocalypse | Victorinus of Pettau | genuine | Two works, the original and "Jerome's recension", labeled separately. | |
  | Apostolic Canons (the canons of Book VIII, a work in `10d8d7c6`) | Attributed to the Apostles | pseudonymous | A received work under rule D (D10). "Attributed to the Apostles; compiled about 380. The Latin West received canons 1 to 50 through Dionysius Exiguus; all 85 were confirmed by the Council in Trullo (canon 2) and Nicaea II (canon 1)." | |
  | Cyprian's two anonymous treatises in `5d75dc92` (Treatises II and IV) | Anonymous | anonymous | | |
  | On Loving God | Bernard of Clairvaux | genuine | translation: "translator unknown (via Paul Halsall's Internet Medieval Sourcebook)" | |

  Wording in the notes follows the research memo; Carter approves the final sentences. Works with CPG numbers take them from the research memo's confirmed list only.
  - Authenticity judgments copied from editorial text before rule G deletes it (plan rule G) go into `attribution_note`, except where this plan overrides them.
  - No code change beyond registry values and their validation test.
- **Acceptance checks:**
  - Registry validation test: every entry in the table exists, has a `certainty` (except the Martyrdom of Ignatius, which keeps its label and sets none), and every `Pseudo-` author has `certainty = pseudonymous`. The Apostolic Canons entry's author is not "Anonymous".
  - The staged release report (2.2w, with 2.3's facts section) shows exactly the listed documents and works changing.
  - After the Phase 4 apply, `GET /v1/documents/3f1d7ed1-...` returns `author: "Pseudo-Justin"` and `facts.certainty: "pseudonymous"`, and a search for "true religion of the Greeks" shows the Pseudo-Justin label on the card (manual check, screenshot in the 4.1b log).
  - PR description must list each label with its source line in the research memo, and the R1 and R4 outcomes for the Refutation.
- **Production safety:** Values only. Nothing changes before the Phase 4 apply. At the apply, 2.2w writes the new `author` and facts into Postgres and the Qdrant payload in the same publish, so cards, the reader and `/sources` agree from the first second. The `(collection, title, translation, author)` unique key has no collision because no two documents share the new labels with the same title.
- **Needs Carter:** Approval of every label and note sentence, including the Apostolic Canons wording.
- **Out of scope:** Author cleanup of malformed names such as "Tertullian: Part Fourth." and trailing periods (1.10a, 1.8c). Moving Boethius to Church Fathers (P5). The Catena Aurea's per-quotation attribution (P5; it uses 2.2a's `passage_author`).

---

### 3.3. Non-English passages: keep in the reader, remove from search

- **Type:** PR (registry values). Takes effect at the Phase 4 apply.
- **Depends on:** 2.1, 2.2a, 2.2w (writes `searchable`, `language` and `note` to staging and the Qdrant payload), 2.2b (its FTS and Qdrant filters), 2.4b (the language note).
- **Goal:** Latin and Italian passages stop appearing in search results. They stay readable in the reader with a note saying they are not in English and not searched. Where a public-domain or licensed English translation exists, it replaces them instead.
- **Current state:**
  - Plan counts: Clement, Stromata III, Latin, 33; Clement, The Instructor II.10, Latin, 4; Lactantius, Divine Institutes VI and On the Workmanship of God, Latin, 5; Ubi Lutetiam (Pius VI), Italian, 17. Total 59.
  - A Latin-stopword heuristic on 29 Sep found 33 in the Stromata (`3a68ef3f`), 5 in The Instructor (`96584290`), 3 in the Divine Institutes (`9e03c96d`), 1 in On the Workmanship of God (`f913305f`), and all 17 of Ubi Lutetiam (`ba74d920`). The small differences from the plan mean the final list must be fixed by anchor in the registry, checked by eye.
  - User rows: 1 retrieval points at one of these passages (Divine Institutes); 0 bookmarks, labels or guest rows.
  - Canon law's Latin (canons 111, 579, 695, 700, and paragraphs of 535 and 868) is handled by 1.5 under the plan's rule 6 and rule E; it uses the same `language` and `searchable` fields when no unofficial English exists.
- **Changes:**
  - Research step inside this item, before code. For each of the four works, record whether a public-domain or licensed English translation of the missing sections exists (0.2's rights inventory holds the answer). The plan's default when none exists is reader-only; TheoCorpus makes no translations of its own.
  - Registry: per passage anchor (or anchor range), `language` (`la` or `it`), `searchable: false`, and a passage `note`, for example "Left in Latin by the Ante-Nicene Fathers translators; no public-domain English translation is available." When an English translation is adopted, the adapter substitutes it (a separate adapter change under 1.8a or 1.3a) and the passage stays searchable.
  - No writer change. 2.2w carries `Passage.searchable`, `language` and `note` into `staging.chunks` and writes `searchable = false` into each point's payload; every such passage stays a Qdrant point (D5).
  - No early live apply (D7). The earlier draft's `apply_passage_flags.py` script is dropped.
  - No change to the reader, which already shows every passage of a chapter; 2.4b adds the language note.
- **Acceptance checks:**
  - Registry test: exactly the approved anchors carry `searchable: false`, each with `language` and `note`.
  - `datapipeline/tests/test_stage_apply.py` (2.2w) covers a `searchable = false` passage reaching staging, live and the Qdrant payload.
  - After the Phase 4 apply: each ID is absent from an FTS query on a distinctive Latin word and from a vector query using the passage's own vector, and `/v1/documents/9e03c96d-.../reader` for the affected chapter still returns those passages with `language: "la"`.
  - PR description must include the final anchor list per work with the first 80 characters of each passage, and the translation research result.
- **Production safety:** Values only; nothing changes before the Phase 4 apply. At the apply, the 59 passages leave search results and stay in the reader. The one retrieval pointing at one of them still restores, because history restore does not filter on `searchable`. 2.2w's rollback restores the previous flags.
- **Needs Carter:** Approval of the anchor list and the note wording.
- **Out of scope:** Canon law Latin (1.5). Writing or commissioning translations. Removing any non-English passage from the reader.
