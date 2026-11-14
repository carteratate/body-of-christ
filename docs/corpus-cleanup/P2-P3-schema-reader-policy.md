# P2 and P3 work specifications for schema, writer, reader and content policy

**Before implementing any item in this file, follow `README.md` in this folder. It says to ask Carter the item's open questions first, record the answers, and update other specs only in the ways it allows.**

29 September 2026, revised the same day to follow the plan's "Cross-cutting design decisions" (D1 to D11). Source of truth is `docs/2026-09-28-corpus-cleanup-plan.md`; its inclusion rules, Decision log and D1 to D11 are settled and are not reopened here. Where this file and D1 to D11 disagree, D1 to D11 win. Code references are to `master` at `5475c49` in `/Users/cartertate/repos/body-of-christ`. Live measurements are read-only SELECTs against Supabase project `hvmgffvimqgiejmxwhwq` on 29 Sep 2026.

Finding IDs C-01 to C-30 refer to the 6 Oct 2026 corpus reviews, merged in `docs/research/2026-10-06-corpus-review-synthesis.md`; `REVIEW-GAPS-PLAN.md` in this folder routes each to its item. The items below were extended for them on 9 Oct 2026, 2.2c became a migration, and 2.4d and 3.4 were added.

## Overview and recommended order

Merge order follows the plan's "Phase and PR plan" table.

1. **2.4c** About page factual fix. Independent, ships first because the page is false today.
2. **2.2a** Migrations 0042 and 0043 (not 0039, which stays unused), additive only. Document facts, the work model (D6), a retired flag on passages and documents, tombstones, redirects, a publish log and a `staging` schema that mirrors the live corpus tables (D2). Nothing reads them yet. No unique key is dropped.
3. **2.2w** The stage-then-apply writer (D2). A publish builds into `staging` and a new Qdrant collection `chunks-<release>`, produces the release report against live, applies in one transaction (calling the `UserDataRemap` interface that 4.1a implements), then switches the `chunks_live` alias. Passage IDs come from the 2.1 registry, so every unit live today keeps its ID (D1). It also provides `rollback`, the only rollback path (D11), a cleanup command that drops the staging tables, vector reuse when the embedding input is unchanged, and a read-only staging override for the pre-cutover eval. It replaces today's delete-based prune for every future publish. Rehearsed locally (D8).
4. **2.2b** API reads Qdrant through `QDRANT_READ_COLLECTION`, then the alias `chunks_live`. Search skips passages marked not searchable and passages that are retired.
5. **2.2c** Migration that rebuilds `search_vector` without Bible verse markers and with each passage's reference (C-16, decided by Carter on 9 Oct 2026). Merged early; applied by hand in 4.0's window.
6. **2.3** Document facts in the work registry, written by 2.2w into staging. No live backfill (D7).
7. **2.4a** API payloads carry document facts, tombstones and redirects; the reader, `/sources`, history and bookmarks hide retired rows or mark them.
8. **2.4b** Web cards, reader, bookmarks and history render the new fields, the source credit on opened passages, tombstones and redirects. Must be live before any tombstone exists.
9. **2.4d** The rejected-voice role (C-01) reaches the rerankers, the explanation model, the card and the reader. Must be live before the Phase 4 apply.
9a. **2.4f** Passage text labels (scanned edition, unofficial canon English) and the amended-canon Latin link, carried by the API and shown on opened passages. Must be live before the Phase 4 apply.
10. **3.3** Non-English passages flagged not searchable in the registry. Takes effect at the Phase 4 apply.
11. **3.2** Labels, certainty and notes in the registry. Takes effect at the Phase 4 apply.
12. **3.1** Removals recorded by anchor in the removal registry (D4). Blocked by R1. Applied at 4.1b through 2.2w.
13. **3.4** Rejected-voice ranges in the passage registry (C-01). Takes effect at the Phase 4 apply.

Every PR here deploys against today's schema and data. No item deletes a row. User rows that point at removed passages keep working because removed passages are retired, not deleted (D3). Nothing in P2 or P3 changes live corpus data before the Phase 4 apply (D7). The one exception D7 allows, the early retirement of On the Incarnation's 47 passages (1.8d, specified at the end of 2.2w), was not taken up (Carter, 4 Nov 2026).

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

Retired rows cost storage. After the rollback window that Carter sets in 4.1b, retired passages that no user row references can be hard-deleted in an ops step, because deleting them cascades nothing. Tombstones are kept. The exception is a `councils` passage retired with reason `translation-in-preparation`: it is never hard-deleted, because 1.2a's gap texts stay available to us while out of search (Carter, 4 Nov 2026).

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
- **Depends on:** 2.1, whose genre module seeds `corpus_genres` and whose work model and removal reasons this migration stores (D11). 2.1 also defines the values that later fill these columns. Applying to the live database needs Carter.
- **Goal:** Give the database the places to hold what the cleanup decides, without changing anything a user sees. After this, a document can carry its genre, issuer (a slug for filters plus a display label), display date, certainty label, notes, source credit and supersession link; a passage can be marked not searchable, tagged with its language, its work (D6) and a quoted author; an older text of a passage can be kept as a non-searchable history passage linked to the current one; a passage or document can be retired; removed units leave a tombstone; moved units leave a redirect; and a publish can be built in a `staging` schema with the live tables' shape before it is applied (D2).
- **Current state:**
  - `documents` columns live: `id, collection, title, author, year, metadata, created_at, translation (NOT NULL DEFAULT ''), chunk_count`, and since 0041 `reader_access (NOT NULL DEFAULT 'full')` (information_schema, 2 Nov 2026). 0040 added `document_contents`, the contents tree, which the writer replaces with the chunks. `chunks` columns live: `id, document_id, content, position, reference, content_embedding, search_vector, annotation, annotation_embedding, created_at, metadata, anchor, chapter_key, chapter_label, unit_label, annotation_vector` (information_schema, 29 Sep).
  - Unique keys on `chunks`: `chunks_document_id_position_key UNIQUE (document_id, position)` and partial `chunks_document_anchor_uniq (document_id, anchor) WHERE anchor IS NOT NULL` (pg_indexes, 29 Sep). Both stay. Under D2 the live tables only ever hold one copy of the corpus, so neither key blocks anything; 2.2w moves retired rows' positions out of the live range so they never collide with new ones.
  - Today passage IDs are computed from the anchor (`reader_writer.py:47` and `:114`, `passage_id(doc.id, p.anchor)`), and the writer upserts `ON CONFLICT (id) DO UPDATE` (`reader_writer.py:121`). Under D1 the ID comes instead from 2.1's passage registry, which freezes every current unit's ID, and `passage_id()` is used only for genuinely new units. A unit whose text is fixed keeps its ID and is updated in place at the apply.
  - `document_type` lives only in `documents.metadata` (16 documents). Metadata keys in use: `url` 211, `pope` 175, `source_file` 135, `testament` 73, `council_number` 20, `year` 16, `council` 16, `document_type` 16, `source_url` 6, `source` 2.
  - `year` is NULL for all 128 Fathers documents, the Summa and all 73 Bible books; `translation` is '' everywhere except the 73 Bible books (`WEB-C`); `author` is NULL for all 36 council documents and all 73 Bible books.
  - `refresh_document_outline` (0037) is pinned to `search_path = public` and counts every chunk of a document (`0037_document_outline.sql`, the function body after the `document_chapters` table). Trigger `chunks_invalidate_outline_on_restructure` fires `AFTER UPDATE OF document_id, position, chapter_key, chapter_label`.
  - The API already tolerates a missing column for 0037 (`services/api/app/routes/documents.py:123-132`, `routes/sources.py:73-76`).
  - The Supabase migration ledger does not list every committed migration (for example 0015, 0016, 0019, 0023, 0026, 0033 are absent from `list_migrations`, though their objects exist). Inspect the live schema, not the ledger, before applying 0042. (2 Nov 2026: the ledger lists 0036 to 0038, 0040 and 0041; production is Postgres 17.6 with 54,555 passages and 421 documents, and has no `staging` schema and none of the new table names.)
  - The parked branch `feat/roman-curia-collection` numbers a migration 0039. It must renumber when it lands in P5; 0039 itself stays unused.
- **Changes:**
  - Two new files (decided by Carter on 2 Nov 2026): `supabase/migrations/0042_corpus_facts_retirement_staging.sql` and `0043_validate_corpus_facts.sql`. Every statement is additive, and no constraint or index is dropped. `SET LOCAL lock_timeout = '2s'` at the top of each, as in 0037, so a waiting `ALTER TABLE` fails rather than queues searches. Adding a nullable column, or one with a constant default, is a catalog-only change on Postgres 11 and later, so neither table is rewritten. CHECK and foreign-key constraints on existing tables are added `NOT VALID` in 0042 and validated in 0043. A migration is one transaction, so validating in 0042 would hold its ADD COLUMNs' ACCESS EXCLUSIVE locks, which block every search, through the scans; in 0043 validation takes only `SHARE UPDATE EXCLUSIVE`, which blocks neither reads nor writes.

    **As built (2 Nov 2026).** The SQL below is the design; the two files are authoritative. They differ from it in these ways:
    - 0042 holds everything that is a catalog change: the new tables, the `staging` schema and its functions, the columns and `NOT VALID` constraints, the replaced outline function and trigger, and the grants. 0043 holds the `VALIDATE CONSTRAINT` statements, one index and the first `SELECT public.create_corpus_staging()`, so staging copies the finished shape.
    - `chunks_voice_check` is validated too; the list below omitted it.
    - 0043 adds `chunks_superseded_by_idx ON chunks (superseded_by) WHERE superseded_by IS NOT NULL`. `chunks_superseded_by_fk` is `ON DELETE SET NULL`, so without it every deleted chunk scans `chunks`, and today's prune deletes passages one statement at a time. Built in 0043 because `CREATE INDEX` blocks writes, not reads.
    - `corpus_publishes` also has `embed_model`, `embed_dimensions`, `snapshot_sha256` (a jsonb object, file to sha256), `cleaned_up_at` and `discarded_at`, which 2.2w writes (decided by Carter on 2 Nov 2026).
    - Staging also mirrors `document_contents` (0040). `create_corpus_staging()` loops over the seven tables with `format()`, and enables RLS and revokes client access on each. `staging.documents` carries `reader_access` (0041) because `LIKE` copies the live columns.
    - The trigger is replaced with `CREATE OR REPLACE TRIGGER` (Postgres 14 and later), so nothing is dropped. `staging.refresh_document_outline` has the public function's body, and a test holds the two equal.


    ```sql
    SET LOCAL lock_timeout = '2s';

    -- Genre vocabulary (D5). A lookup table, so adding a genre later is an INSERT,
    -- not a constraint change. The rows are exactly registry/genres.py ALL_GENRES (2.1, D11);
    -- a test fails if the two differ.
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
        ADD COLUMN issuer           text,   -- slug for filters: 'pope-leo-xiii', 'ddf', 'holy-see'
        ADD COLUMN issuer_label     text,   -- display: 'Pope Leo XIII', 'Dicastery for the Doctrine of the Faith'
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
        ADD CONSTRAINT documents_issuer_slug_check
            CHECK (issuer IS NULL OR issuer ~ '^[a-z0-9]+(-[a-z0-9]+)*$') NOT VALID,
        ADD CONSTRAINT documents_superseded_by_fk
            FOREIGN KEY (superseded_by) REFERENCES documents(id) ON DELETE SET NULL NOT VALID;

    -- Works inside one document (D6). The shape is 2.1's Work model (D11); this is its
    -- database side. ANF volumes hold several works per document
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

    -- Passage fields. searchable, language, passage_author, voice and work_key are Passage
    -- model fields defined in 2.1 (D11); adapters may set them and the registry overrides.
    ALTER TABLE chunks
        ADD COLUMN retired_at     timestamptz,
        ADD COLUMN searchable     boolean NOT NULL DEFAULT true,
        ADD COLUMN language       text,   -- NULL means English
        ADD COLUMN work_key       text,
        ADD COLUMN passage_author text,   -- 'Chrysostom, quoted in Aquinas''s Catena Aurea'
        ADD COLUMN voice          text,   -- NULL, or 'rejected' (C-01, D5)
        ADD COLUMN note           text,
        ADD COLUMN superseded_by  uuid;   -- a history passage (<anchor>/history-<year>) points at
                                          -- the current passage it was replaced by (rule F, D11)
    ALTER TABLE chunks
        ADD CONSTRAINT chunks_language_check
            CHECK (language IS NULL OR language ~ '^[a-z]{2,3}$') NOT VALID,
        ADD CONSTRAINT chunks_voice_check
            CHECK (voice IS NULL OR voice = 'rejected') NOT VALID,
        -- Retired rows sit below every live and temporary position (see 2.2w).
        ADD CONSTRAINT chunks_retired_position_range
            CHECK (retired_at IS NULL OR position <= -1000000) NOT VALID,
        ADD CONSTRAINT chunks_work_fk FOREIGN KEY (document_id, work_key)
            REFERENCES document_works (document_id, work_key) NOT VALID,
        ADD CONSTRAINT chunks_superseded_by_fk FOREIGN KEY (superseded_by)
            REFERENCES chunks (id) ON DELETE SET NULL NOT VALID,
        -- A history passage is never searchable.
        ADD CONSTRAINT chunks_history_not_searchable
            CHECK (superseded_by IS NULL OR NOT searchable) NOT VALID;

    ALTER TABLE documents VALIDATE CONSTRAINT documents_genre_fk;
    ALTER TABLE documents VALIDATE CONSTRAINT documents_certainty_check;
    ALTER TABLE documents VALIDATE CONSTRAINT documents_superseded_by_fk;
    ALTER TABLE documents VALIDATE CONSTRAINT documents_issuer_slug_check;
    ALTER TABLE chunks VALIDATE CONSTRAINT chunks_language_check;
    ALTER TABLE chunks VALIDATE CONSTRAINT chunks_voice_check;
    ALTER TABLE chunks VALIDATE CONSTRAINT chunks_retired_position_range;
    ALTER TABLE chunks VALIDATE CONSTRAINT chunks_work_fk;
    ALTER TABLE chunks VALIDATE CONSTRAINT chunks_superseded_by_fk;
    ALTER TABLE chunks VALIDATE CONSTRAINT chunks_history_not_searchable;

    -- One row per publish (D2). Written by 2.2w. The id is the release name, the same
    -- value as the lock entry's "release" and the --release flag (D11).
    CREATE TABLE corpus_publishes (
        id                         text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9-]{2,62}$'),
        collections                text[] NOT NULL,
        report_sha256              text,
        qdrant_collection          text NOT NULL,
        previous_qdrant_collection text,
        embed_model                text,
        embed_dimensions           integer CHECK (embed_dimensions > 0),
        snapshot_sha256            jsonb CHECK (jsonb_typeof(snapshot_sha256) = 'object'),
        staged_at                  timestamptz,
        applied_at                 timestamptz,
        alias_switched_at          timestamptz,
        rolled_back_at             timestamptz,
        cleaned_up_at              timestamptz,
        discarded_at               timestamptz
    );

    -- Tombstones outlive the rows they describe, so no foreign keys to chunks or documents.
    CREATE TABLE corpus_tombstones (
        entity        text NOT NULL CHECK (entity IN ('document', 'passage')),
        id            uuid NOT NULL,
        document_id   uuid NOT NULL,
        retired_at    timestamptz NOT NULL,
        publish_id    text NOT NULL REFERENCES corpus_publishes(id),
        removal_key   text,           -- the D4 removal-registry entry id; NULL only for rolled-back
        rule          text NOT NULL CHECK (rule IN ('A', 'B', 'C', 'G', 'other')),  -- derived from reason_code by 2.2w
        reason_code   text NOT NULL CHECK (reason_code IN (
                          'rule-a', 'rule-b', 'rule-c', 'rule-g-editorial', 'note-split-off',
                          'duplicate', 'debris', 'other-author', 'superseded-translation',
                          'translation-in-preparation', 'not-current-law', 'awaiting-permission',
                          'rolled-back')),
                                      -- 2.1's reason list (D11), plus 2.1's reserved 'rolled-back'
        public_reason text NOT NULL,  -- the registry entry's tombstone sentence, shown to users
        CHECK ((reason_code = 'rolled-back') = (removal_key IS NULL)),
        church_act    text,           -- 'Second Council of Constantinople (553), anathema 11'
        snapshot      jsonb NOT NULL, -- {collection, title, author, reference, chapter_label}
        PRIMARY KEY (entity, id)
    );
    CREATE INDEX corpus_tombstones_document_idx ON corpus_tombstones (document_id);

    -- Redirects from old identities to new ones. Kinds are the four redirect words of
    -- 0.1c's vocabulary (D5, D11); 'same' and 'removed' are release-report outcomes only.
    CREATE TABLE corpus_redirects (
        id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        entity          text NOT NULL CHECK (entity IN ('document', 'passage', 'anchor', 'chapter')),
        old_id          uuid,          -- document or passage ID; NULL for anchor and chapter rows
        old_document_id uuid NOT NULL,
        old_anchor      text,          -- the old anchor, or for chapter rows the old chapter_key
        new_id          uuid,
        new_document_id uuid NOT NULL,
        new_anchor      text,          -- the new anchor, or for chapter rows the new chapter_key
        kind            text NOT NULL
            CHECK (kind IN ('moved', 'split', 'merged', 'renumbered')),
                        -- an anchor or chapter that only changed its string uses 'moved'
        publish_id      text NOT NULL REFERENCES corpus_publishes(id),
        created_at      timestamptz NOT NULL DEFAULT now(),
        CHECK ((entity IN ('anchor', 'chapter')) = (old_id IS NULL))
    );
    CREATE UNIQUE INDEX corpus_redirects_id_uniq
        ON corpus_redirects (old_id) WHERE entity IN ('document', 'passage');
    CREATE UNIQUE INDEX corpus_redirects_anchor_uniq
        ON corpus_redirects (entity, old_document_id, old_anchor) WHERE entity IN ('anchor', 'chapter');

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
        CREATE TABLE IF NOT EXISTS staging.document_contents (LIKE public.document_contents INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS staging.document_works    (LIKE public.document_works    INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS staging.corpus_tombstones (LIKE public.corpus_tombstones INCLUDING ALL);
        CREATE TABLE IF NOT EXISTS staging.corpus_redirects  (LIKE public.corpus_redirects  INCLUDING ALL);
    END $$;

    CREATE FUNCTION public.drop_corpus_staging() RETURNS void
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
    BEGIN
        DROP TABLE IF EXISTS staging.corpus_redirects, staging.corpus_tombstones,
            staging.document_works, staging.document_contents, staging.document_chapters,
            staging.chunks, staging.documents;
    END $$;

    -- The reader outline for staged documents. Same body as public.refresh_document_outline
    -- (below), resolved against staging.
    CREATE FUNCTION staging.refresh_document_outline(p_document_id uuid) RETURNS void
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = staging AS $$ /* 0037 body */ $$;

    SELECT public.create_corpus_staging();  -- in 0043, after validation
    ```

    The staged redirect `id` values are local to staging; the apply inserts redirects into the live table without them, so the live identity column numbers them.
  - Same file, the reader outline counts only what readers see. Replace `refresh_document_outline` with `CREATE OR REPLACE FUNCTION`, identical except that both chunk subqueries add `AND c.retired_at IS NULL`. Replace `chunks_invalidate_outline_on_restructure` (drop and create in the same transaction) so its column list and `WHEN` clause also include `retired_at`. With no row retired, the function returns the same outline as today.
  - Same file, grants as in 0037. `ENABLE ROW LEVEL SECURITY` with no policies on `corpus_genres`, `document_works`, `corpus_publishes`, `corpus_tombstones` and `corpus_redirects`; `create_corpus_staging()` does the same for each `staging` table it creates. `REVOKE ALL ... FROM PUBLIC, anon, authenticated` on those tables, on schema `staging`, and on the three new functions and the replaced one. FastAPI and the datapipeline use the service role.
  - Because `create_corpus_staging()` copies the live tables' shape when it runs, a later migration that adds a corpus column needs no staging change; 2.2w drops and recreates the staging tables around each publish. `stage` refuses to reuse existing staging tables whose columns differ from live.
  - No API or web change in this PR.
- **Acceptance checks:**
  - New test `services/api/tests/test_corpus_facts_migration.py` using `tests/pg_cluster.py` (as `test_document_outline_migration.py` does). Apply the corpus schema as production has it (information_schema, 2 Nov 2026, without the two unused pgvector columns), with Supabase's default grants to `anon` and `authenticated`, then 0037, 0038, 0040, 0041, 0042 and 0043. Assert:
    - `test_existing_rows_are_live_and_searchable`: every seeded chunk has `retired_at IS NULL` and `searchable = true`; every document `retired_at IS NULL`.
    - `test_voice_accepts_only_rejected`: `voice` is NULL on every seeded chunk, accepts `rejected` and rejects any other value (C-01, D5).
    - `test_genre_accepts_only_the_d5_vocabulary`: every value in 2.1's `registry/genres.py` `ALL_GENRES` is present and accepted; `apostolic exhortation` and `essay` are rejected.
    - `test_genre_seed_matches_registry_module`: the migration's `INSERT INTO corpus_genres` list equals `ALL_GENRES`, read from the Python module (a plain file read, so the API test suite needs no datapipeline import). Since 0044 (9 Nov 2026) the list compared is 0042's seed less the genres 0044 deletes: `bull` moved to `corpus_forms`, with `documents.form` beside `documents.genre`.
    - `test_issuer_is_a_slug_and_label_is_free_text`: `pope-leo-xiii` is accepted in `issuer`, `Pope Leo XIII` is rejected there and accepted in `issuer_label`.
    - `test_history_passage_links_and_is_not_searchable`: a chunk with `superseded_by` set to another chunk's ID and `searchable = true` fails the CHECK; with `searchable = false` it passes.
    - `test_tombstone_reason_uses_registry_list`: every 2.1 reason and `rolled-back` are accepted; `condemned_by_name` is rejected; `rolled-back` requires a NULL `removal_key` and every other reason requires one.
    - `test_outline_excludes_retired_rows`: a document with 3 chunks, one retired and moved to position -1000000, gives `chunk_count = 2` and no chapter made only of the retired row.
    - `test_retiring_a_row_invalidates_the_outline`: setting `retired_at` sets that document's `chunk_count` to NULL.
    - `test_retired_row_must_leave_the_live_position_range`: setting `retired_at` on a row at position 5 fails the CHECK.
    - `test_redirect_kind_uses_remap_vocabulary`: `moved`, `split`, `merged` and `renumbered` are accepted; `same`, `removed` and `rewritten` are rejected.
    - `test_redirect_anchor_and_chapter_rows_have_no_old_id`.
    - `test_staging_mirrors_live_tables`: for `documents`, `chunks`, `document_chapters`, `document_contents`, `document_works`, `corpus_tombstones` and `corpus_redirects`, the columns, generated expressions, CHECK constraints and indexes in `staging` equal those in `public`, and staging has no foreign keys.
    - `test_staging_can_be_dropped_and_recreated`: `drop_corpus_staging()` then `create_corpus_staging()` leaves the same shape, and neither touches a `public` table.
    - `test_staging_outline_reads_staging`: `staging.refresh_document_outline` builds `staging.document_chapters` from `staging.chunks` and leaves `public.document_chapters` unchanged.
    - `test_no_unique_key_dropped`: `chunks_document_id_position_key` and `chunks_document_anchor_uniq` still exist.
    - `test_new_objects_are_closed_to_client_roles`: `anon` and `authenticated` cannot SELECT from the new tables or use schema `staging`.
    - Added as built: `test_staging_covers_the_contents_tree_and_reader_access`, `test_tombstone_check_lists_exactly_the_registry_reasons` (the CHECK's list equals `REMOVAL_REASONS` plus `ROLLED_BACK`, read from `registry/__init__.py` as text), `test_the_schema_migration_validates_nothing` (every constraint on `documents` and `chunks` is unvalidated after 0042 alone and validated after 0043), `test_validation_takes_no_lock_that_blocks_reads`, `test_the_outline_is_unchanged_while_nothing_is_retired`, `test_no_column_or_index_of_an_existing_table_changes`, `test_the_history_link_is_indexed_for_deletes`, `test_publish_records_embedding_model_snapshot_and_cleanup`, and the work, certainty, language and supersession checks. 38 tests.
  - Existing suites unchanged: `python3 -m pytest tests/` in `services/api` and `python3 -m pytest` in `datapipeline`.
  - Timing rehearsal on a local Postgres restored from a `pg_dump` of production (D8), recording the time and lock of each statement. The dump stays on Carter's Mac and is deleted afterwards.
  - PR description must include the full SQL, the lock each statement takes, the local rehearsal timings, and the sentence "This PR changes no API or web behavior."
- **Production safety:** Merging deploys nothing to the database; migrations in this repo are applied by hand. Once 0042 and 0043 are applied, today's API ignores every new column, table and schema, and the defaults leave all 54,555 passages (2 Nov 2026) live and searchable as now. Today's datapipeline cannot write while the publish lock (0.4) holds; if it could, its inserts would take the defaults. The replaced `refresh_document_outline` returns the same outline as before while nothing is retired. Empty `staging` tables and their indexes cost a few kilobytes. If 2.2b or 2.4a deploy before 0042 is applied, their schema probe finds no columns and runs today's SQL.
- **Needs Carter:** Approval of the `pg_dump` for the local timing rehearsal (D8), then approval to apply 0042 and 0043 to the live database.
  - **As built (2 Nov 2026):** both approved and done. The rehearsal used a read-only copy of the four corpus tables (no user data) rather than a full `pg_dump`, which could not be restored on the Lenovo (no pgvector, no version 17 client); timings are in PR #309. 0042 and 0043 were applied to production on 2 Nov 2026 and recorded in the Supabase ledger (`NEEDS-CARTER.md` has the details). Applied from the Lenovo, each statement costs a ~40 ms round trip, so a lock held to commit lasts (statements after it) × 40 ms: 0042's read-blocking locks lasted about 0.55 s, not the rehearsed 30 ms. Later migrations that take such locks should put those statements last, as 0042 does, or be sent as one round trip.
- **Out of scope:** Filling any column (2.2w, 2.3, 3.1 to 3.3). Changing foreign keys from CASCADE to RESTRICT (a possible later hardening, not additive). The collection merge and its CHECK constraint (5.1b). The user-data remap (4.1a). Hard-deleting retired rows (ops after 4.1b's rollback window).

---

### 2.2w. Stage-then-apply writer

- **Type:** three PRs, merged in order, each based on master after the one before it merged (decided by Carter on 2 Nov 2026): (a) the CLI with `stage`, `report`, `status` and `discard`, the lock gates, stage, report, and the removal of every delete path; (b) the before-snapshot, apply, switch, rollback and cleanup, the `UserDataRemap` interface, `--retire-only` and the local rehearsal; (c) the `CORPUS_READ_SCHEMA` read override, the other writers and the full docs rewrite. Plus one optional ops step (the On the Incarnation early retirement, at the end of this item).
- **Depends on:** 0.4 (publish lock), 0.1c (release report and remap, D5 vocabulary), 2.1 (document and passage registries and the removal registry), 2.2a (0042 and 0043 merged; applied before any staging into production). 4.1a later supplies the user-data remap that the apply calls (below).
- **Goal:** One writer for the republish and for every publish after it (D2). A publish never writes straight into live tables. It builds into `staging` and a new Qdrant collection, produces the release report against live, applies in one database transaction that updates, inserts and retires but never deletes, then switches the `chunks_live` alias. Users see nothing until the apply, then see the whole new corpus at once, and no bookmark, saved search, label or guest result is lost.
- **Current state:**
  - `publication.py:121-187` (`CollectionPublicationRunner.publish`) writes each document straight into the live reader store (`reader.write(..., prune=True)`, `:150-154`), then deletes live documents the build no longer emits (`reader.prune_documents`, `:155-158`), then upserts Qdrant points and deletes stale ones (`search.write`, `search.prune`, `:172-177`). `--wipe-reader` calls `clear_collection` (`:148-149`, `:265-266`) and `--reset-search-index` deletes a collection's points (`:170-171`, `:288-291`).
  - `_validate_build` (`publication.py:224-248`) refuses more than 10% shrink or 10% identity churn per collection; it is the only size check.
  - `writers/reader_writer.py:84-132` (`write_document`) upserts the document (`:97-107`), flips positions below zero (`:108-111`) so re-positioned passages do not collide on `UNIQUE (document_id, position)`, prunes (`:112`), upserts passages on `id` (`:113-130`), and refreshes the outline last in the same transaction (`:131`). `clear_collection` (`:16-33`), `prune_missing_chunks` (`:36-59`) and `prune_missing_documents` (`:62-81`) issue `DELETE`, which cascades into user tables.
  - `writers/qdrant.py:15` hard-codes `QDRANT_COLLECTION = "chunks"`. `ensure_collection` (`:28-59`) creates `chunks` if missing. `delete_collection_points` (`:62-67`) and `prune_missing_points` (`:88-108`) delete live points. `upsert_points` (`:111-122`) retries 4 times.
  - `qdrant_schema.py:12` hard-codes `CHUNKS = "chunks"`, and `recreate_chunks` (`:17-29`) deletes and recreates it, with one keyword payload index on `collection`.
  - Passage IDs are computed from the anchor in three places, `publication.py:128-132`, `reader_writer.py:114` and `search_writer.py:41`, all through `identity.passage_id` (`identity.py:40`). Under D1 they come from 2.1's passage registry instead.
  - `writers/search_writer.py:39-63` (`build_point`) writes the payload `collection, document_id, document_title, author, content, reference, anchor, chapter_label, chapter_key, unit_label`. There is no `genre`, `issuer` or `searchable`. `write_document` (`:83-101`) re-embeds every passage of a document on every run.
  - `run_collection.py:62-86` calls `production_runner().publish(...)`; 0.4 adds the lock guard, `--release` and `--dry-run` in front of it.
  - Qdrant holds one collection, `chunks`, 54,568 points of 1,536 dimensions, no alias (plan, 28 Sep).
  - The database is 401 MB (402 MiB on 30 Oct 2026, on Supabase Pro, which has no read-only trigger at this size; 0.6), and `chunks` holds about 123 MB of live row data (4.0, which is the source for every storage figure in these specs).
  - Other code that writes to the corpus or Qdrant, verified on master 29 Sep: `stages/reader.py` (calls `clear_collection`), `stages/embed.py` (upserts and deletes points), `stages/bm25_index.py` (`update_vectors` on `QDRANT_COLLECTION`), `stages/enrich_io.py` (`UPDATE chunks SET annotation`), and the three repair scripts `scripts/backfill_missing_vectors.py`, `scripts/reembed_drifted_vectors.py` and `scripts/reconcile_qdrant_payloads.py` (each on `QDRANT_COLLECTION`). The modules `backfill_vectors.py`, `reconcile.py` and `reembed.py` make no store writes themselves; they are libraries those scripts call.
  - The embedding cache (`cache.py`, table `embeddings`) is keyed on the sha256 of the exact embedding input plus model and dimensions. Only the V5 `stages/embed.py` reads or writes it; today's publish path (`search_writer.write_document`) does not. On Carter's Mac `datapipeline/cache.db` is empty (0 bytes, 29 Sep).
  - `services/api/app/db.py:42-52` creates the API's asyncpg pool with no `search_path` setting. `services/api/scripts/run_eval_suite.py` runs the pipeline in process with no HTTP server, so it persists no searches.
  - Also found by the 6 Oct reviews:
    - Neighbour text (C-21, Opus-2 B-012). `build_embedding_input` (`writers/search_writer.py:27-36`) adds the end of the previous and the start of the next passage in the same chapter key (canon law 300 characters, Catechism 200, default 200) and ignores `searchable`. Every history passage (CCC 2267's 1997 text, superseded canons), Latin canon and 3.3 passage is a point in the same build list (D5), so its text would be embedded into the current passage beside it.
    - The embedding prefix (C-15, Opus-2 B-003) is `<doc.author> — <doc.title>, <label>`, so a relabel or a work credit changes the payload `author` but not the vector.
    - Provenance (C-23). Live points carry no record of the text or model that produced them. The `embed_sha256` this item adds covers the input; the model and dimensions are recorded nowhere.
    - Dedup collisions (C-09, Opus A-004). The API's dedup (`services/api/app/rag/dedup.py`, `_COSINE_THRESHOLD = 0.9`) drops the lower-ranked of two passages from one document within two positions whose vectors exceed the threshold. A short canon's vector is mostly its neighbours' text (canon law's overlap is 300 characters each side), and the Summa, whose overlap is 0 (`datapipeline/config.py:60`), shares a prefix with the article title across all its parts; so 35.7% of nearby canon pairs, 20.5% of Summa pairs and 8.9% of council pairs collide on the live vectors, and six pairs of short neighbours have byte-identical inputs. 1.7's new labels and citations change the Summa prefix in any case. Carter decided on 9 Oct 2026 to keep today's input except for the neighbour fix and the display-author prefix below, and to test the threshold separately (RF-1), so the republish embeds once.
    - Docs (C-28, Opus A-023). CLAUDE.md section 4 says Qdrant holds the V5 `facets` and `questions` collections; production holds only `chunks`, and `stages/embed.py` deletes from both on every run.
- **Changes:**
  - **CLI.** New `datapipeline/publish.py` with subcommands, each taking `--release <name>`. The release name is the publish ID: it is `corpus_publishes.id`, the `release` of the lock entry, and the suffix of the staging Qdrant collection `chunks-<release>` (D11):
    - `stage --collection <name>|all`
    - `report`
    - `apply` (switches the alias right after commit unless `--no-switch`)
    - `switch`
    - `rollback` (below; the only rollback path, D11)
    - `cleanup` (drops the staging tables once the apply is checked)
    - `discard` (abandons a publish that was never applied, drops the staging tables and records its Qdrant collection for deletion; deleting a Qdrant collection is always a separate ops step)
    - `status`
  - `run_collection.py` keeps only `--dry-run` (0.4). A live invocation exits 2 with a message pointing at `publish.py`. `--wipe-reader`, `--confirm-reader-wipe` and `--reset-search-index` are removed, since each deletes live rows or points.
  - **Lock gates (0.4).** Every subcommand except `report` and `status`, which only read, calls 0.4's `assert_live_write_allowed(f"publish {subcommand}", collection, release, step)`, with step `stage` for `stage` and `discard`, `apply` for `apply`, `switch` and `cleanup`, and `rollback` for `rollback`. It runs only when `PUBLISH_LOCK.json` has an `approved_applies` entry for that collection and release whose `steps` include the step, which takes a reviewed PR. 0.4's loopback exemption covers local rehearsals (D8); this item adds no rule of its own to `publish_lock.py`. The entry stays until the release's rollback window closes, and a follow-up PR removes it.
  - **Stage** (`publication.py`, reworked). `CollectionPublicationRunner.publish` becomes `stage`. It no longer acquires a live reader store or search index.
    1. Refuse if `staging` holds a different publish that is neither cleaned up nor discarded (`corpus_publishes.cleaned_up_at` and `discarded_at`). Call `create_corpus_staging()` (2.2a) if the staging tables are absent, and refuse if existing ones differ in shape from live.
    2. Build documents with `SOURCE_ADAPTERS` (`publication.py:32-45`). Adapters take frozen document IDs, anchors, document facts and work keys from the 2.1 registry, and skip every unit the removal registry marks removed. `searchable`, `language`, `passage_author` and `voice` are `Passage` fields (2.1): the stage reads the adapter's value first, then applies the passage registry's override where a row sets one (3.3, 3.4, which also overrides `unit_label`), so the registry wins (D11). It also resolves each history passage's `superseded_by_anchor` to the current passage's ID for `chunks.superseded_by`, and stops if the anchor is not in the same document.
    3. Take each passage's ID from 2.1's passage registry (D1). `Passage` gains an `id` field, filled by the registry's lookup from `(document_id, structural anchor)`. A unit that exists today gets its current passage ID, whatever its anchor now looks like. Only a unit the registry does not know (a restored verse, recovered prose, a split recension) gets a new ID from `identity.passage_id`, and the stage lists every such new ID. The writers use `Passage.id` and never recompute it, so `publication.py:128-132`, `reader_writer.py:114` and `search_writer.py:41` stop calling `passage_id()`. A passage with no ID stops the stage.
    4. Delete the staged rows of the collections being staged (staging tables only), then insert `staging.documents`, `staging.document_works`, `staging.chunks` and each document's contents tree into `staging.document_contents` (decided by Carter on 2 Nov 2026). Each staged document's `reader_access` is derived from the rights inventory (D12, decided by Carter on 2 Nov 2026), so the report and the staging eval see it. Positions are the build's positions (0 and up). `search_vector` is generated, and the staged GIN index is built, as in live. Call `staging.refresh_document_outline` for every staged document, so `staging.document_chapters` and `chunk_count` exist for the pre-cutover eval.
    5. Compute retirements and redirects against live. Every live ID in the staged collections that the build does not emit needs either a removal-registry entry (D4), which yields a `staging.corpus_tombstones` row, or a 0.1c remap outcome of `moved`, `split`, `merged` or `renumbered`, which yields a `staging.corpus_redirects` row. An ID with neither stops the stage and names the ID. Two more kinds of redirect keep old links working (2.4a resolves them):
       - Anchor redirects (`entity = 'anchor'`, kind `moved` unless a passage redirect says otherwise): one for every passage-registry row in the staged collections whose current `anchor`, or document, differs from its `live_anchor` and live document. A row whose status is `redirected` points its anchor redirect at its open passage redirect's `new_anchor`, never at its own `anchor`: that is a piece name the build no longer emits, or, for a piece whose text moved (Decision log "A piece whose text moved keeps no ID", 1.10b), `<anchor>#moved-<item>`, which no passage carries. That is about 37,000 rows at P4, because 2.1 rebuilt ThML and Summa anchors, and a few MB of table.
       - Chapter redirects (`entity = 'chapter'`, kind `moved`): one for every row of 0.1c's `chapter_remap.jsonl` whose `document_id` or `chapter_key` changed.

       A live passage that the build emits under another document ID (a passage moved between documents, as in 1.8b's split) is not a retirement: it keeps its ID and moves at the apply (below).
       Tombstone rows from registry entries (D11). Only `document` and `passage` entries produce a row; `span` and `class` entries are audit records and produce none. For each retired ID:
       - `removal_key` is the entry's `id`, and `reason_code` is its `reason`, from 2.1's list.
       - `public_reason` is its `tombstone` sentence, unchanged.
       - `church_act` is null, or the entry's `church_act` object rendered as "<act>, <issuer>, <date>", for example "Second Council of Constantinople, anathema 11, 553".
       - `rule` is derived from the reason and never stored in the registry: `rule-a` gives `A`, `rule-b` gives `B`, `rule-c` gives `C`, `rule-g-editorial` and `note-split-off` give `G`, and every other reason gives `other`.
       - `snapshot` is `{collection, title, author, reference, chapter_label}` taken from the live row.
       A `document` entry yields one document tombstone plus one passage tombstone per live passage of the document, all with the same reason and sentence.
    6. Refuse when the alias `chunks_live` does not exist; the stage never falls back to `chunks` (decided by Carter on 2 Nov 2026; 2.2b's ops step creates the alias). Create a new Qdrant collection `chunks-<release>` (D11; `QDRANT_WRITE_COLLECTION` overrides the name for local runs) with `qdrant_schema.create_chunks_collection` (below). Write one point for every staged passage, searchable or not (D5). Each point's vector comes from the first of these that has it (D11):
       1. The content-addressed embedding cache (`cache.py`, `get_embedding(input_hash, model, dims)`), keyed on the sha256 of the exact embedding input (`search_writer.build_embedding_input`, `:27-36`), the model and the dimensions.
       2. The collection the alias targets, when it holds a point with the same ID and the same `embed_sha256` payload field (`retrieve(..., with_vectors=True)`). Such a vector is also written to the cache.
       3. OpenAI, for cache misses only, in batches. Each new vector is written to the cache before the point is upserted, so an interrupted stage never pays twice.
       The payload stores `embed_sha256` so the next publish can use step 2.
       Expected hit rate, and both bounds (measured 29 Sep). The cache on Carter's Mac is empty, today's publish path never wrote to it, and live points carry no `embed_sha256`. Live vectors were also built from a different input shape than today's writer produces (a `[chapter_label]` prefix instead of the author and title prefix; `backfill_vectors.py` docstring), so they cannot be matched. The first full stage therefore misses on every passage: about 55,000 passages and about 11 million tokens, about $1.40 at $0.13 per million tokens (price unverified; check before the run). The first full stage run on Carter's Mac pays this once and fills the cache, whichever rehearsal it is (this item's or 4.1a's, D8); every later stage on that Mac pays only for inputs that changed since. The production stage in 4.1b step 1 then misses only on passages whose embedding input changed after the last rehearsal build: 0 tokens if the build is unchanged, up to the same 11 million if every input changed. Every later publish embeds only passages whose input changed.
       Collections not being staged are copied point for point, vectors and payloads, from the collection the alias targets, so the new collection is complete on its own. A collection being renamed by this publish (5.1b.3) counts as staged under its old key too, so its old points are never copied (see 5.1b.3).
    7. Check the new collection's point counts per collection. For each staged collection, the count equals its staged passage count. For each copied collection, it equals the source collection's count for that collection. The total equals staged passages plus copied points. Then record `staged_at` and the collection name in `corpus_publishes`.
  - **Report.** `publish.py report` runs 0.1c's report in a staged mode that reads `staging` instead of building. On top of 0.1c's sections it adds these checks:
    - Every retirement is explained by the removal registry or a redirect (D4).
    - Every passage live today keeps its ID (D1). Each live ID in the staged collections is either present in staging under the same ID or explained by a removal-registry entry or a redirect. The report prints the three counts and fails on any live ID that is none of these. It also lists every new ID with its reason from the registry.
    - The D1 check. Any passage whose ID is unchanged and whose text similarity to live falls below 0.1c's threshold, with no redirect, fails the report.
    - Qdrant point count and payload facts (`collection`, `genre`, `issuer`, `searchable`) equal the staged values for every passage.
    - The document-facts diff that 2.3 specifies.
    - User impact, which lists the user rows that point at retired and redirected IDs.
    - The added storage in `staging` and the projected database size after apply.
    - `index.embedding_input_hash`: every point's `embed_sha256` equals the hash of its staged passage's embedding input, and every point names its model (C-23).
    - `index.dedup_collision_rate:<collection>`: the share of same-document passage pairs within two positions whose new vectors exceed the API's dedup threshold, per collection, with the previous publish's figure beside it; flagged above 5% (C-09). It informs RF-1 and changes nothing by itself.
    The report's sha256 and a hash of the staged content go into `corpus_publishes.report_sha256`. `apply` refuses when the staged content no longer matches the reported hash.
  - **Snapshot for rollback.** Right before the apply transaction, `apply` exports the live corpus rows of the staged collections (`documents`, `chunks` without `search_vector`, `document_works`, `document_chapters`, `document_contents`, and every `corpus_redirects` and `corpus_tombstones` row the apply will delete: an un-retired ID's earlier tombstone, or the redirect of a split piece that reclaims its ID) in one read-only transaction to a local, gitignored folder `datapipeline/releases/snapshots/<release>-before/`, with a sha256 per file recorded in `corpus_publishes.snapshot_sha256`. The files hold corpus text only, no user data. The apply refuses to start if the export fails. `rollback` reads this snapshot itself. The `pg_dump` 4.1b takes before an apply is a last-resort backup, not a rollback path (D11).
  - **Apply** (new `datapipeline/writers/apply.py`). One transaction, with `SET LOCAL lock_timeout = '2s'`, for all staged collections:
    1. Upsert `documents` from `staging.documents` by ID, setting `retired_at = NULL` for any document present in staging. Each touched document's `reader_access` is derived again from the rights inventory as it stands at the apply; when that differs from the staged value the apply refuses, rather than write a stale one (D12, decided by Carter on 2 Nov 2026). Replace each touched document's `document_contents` rows with the staged ones. Retire documents of the staged collections that staging lacks, which the stage step has already shown are explained. Upsert `document_works`.
    2. Per document, move live passages to temporary positions (`position = -position - 1`, which stays inside -1 to -999,999), as `reader_writer.py:108-111` does today, but only for rows with `retired_at IS NULL`.
    3. Upsert `chunks` from `staging.chunks` by ID. Changed text under an unchanged anchor updates in place and keeps its ID (D1). New IDs insert. A staged ID that matches a retired row un-retires it, and its old tombstone row (for example a `rolled-back` one) is deleted in the same transaction, so a live passage never also shows a removal notice. Likewise, when 2.1 has closed a redirect because its unit reappeared (a split piece reclaiming its ID), that ID's `corpus_redirects` row is deleted in the same transaction, so 2.4a resolves the ID as current. A staged ID that is live under another document moves by updating its `document_id` in place, so it keeps its ID and every user row on it (D11; needed if Carter approves 1.8b's split). Step 2 has already moved the live rows of both documents out of the live position range, so the move cannot collide.
    4. Retire live passages that staging lacks. Set `retired_at = now()` and move each to a position below every existing retired position of its document, starting at -1,000,000, so repeated publishes never collide on `UNIQUE (document_id, position)`. No `DELETE` is issued anywhere.
    5. Insert tombstones and redirects from staging into `corpus_tombstones` and `corpus_redirects`, tagged with the publish ID.
    6. Call the user-data remap inside the same transaction, after the redirects are written, so bookmarks, history results, labels, guest results, reading positions and feedback move to the new IDs in the same commit. This item defines the interface and calls it; 4.1a implements it (D11). Neither item contains the other's code:
       ```python
       class UserDataRemap(Protocol):
           async def forward(self, conn, release: str, redirects, chapter_remap) -> RemapLedger: ...
           async def reverse(self, conn, release: str) -> RemapLedger: ...
       ```
       `forward` moves user rows along this publish's redirects; `reverse` undoes only what `forward`'s ledger recorded, skipping (and counting) any row a user has deleted or changed since, or whose parent row is gone. A skipped row never raises, so a user's deletion during the window cannot abort a rollback (4.1a step 4). The ledger's public counts go into the publish log. Until 4.1a merges, `apply` refuses any publish whose redirects are referenced by a user row, naming the tables and counts. A publish with no such redirects, such as the On the Incarnation retirement below, runs without it.
    7. Call `refresh_document_outline` for every document touched, last, as `reader_writer.py:131` does today.
    8. Record `applied_at`.
  - **Switch.** Right after commit, one `update_collection_aliases` call deletes `chunks_live` from the old collection and creates it on the new one. Qdrant applies the listed alias actions atomically. The old target is stored in `corpus_publishes.previous_qdrant_collection`. Between commit and switch (seconds), a vector hit on a now-retired passage is dropped by 2.2b's Postgres guard, and new passages are found by full-text search only.
  - **Rollback.** `publish.py rollback --release <name>` undoes an applied publish within the rollback window, under the lock step `rollback`. It is the only rollback path (D11), and the runbook (4.1b step 12) calls this command and nothing else. It is an apply in reverse, built from the same code.
    1. Recreate the staging tables if `cleanup` dropped them, and load the publish's before-snapshot into them. The snapshot's sha256s must match `corpus_publishes`.
    2. In one transaction, run apply steps 1 to 4 with the snapshot as the staged content. This restores the previous text, facts and contents trees in place by ID and un-retires every row the publish retired. `reader_access` is the stricter of the snapshot's value and the rights inventory's verdict at the rollback, so a permission withdrawn during the window cannot reopen a text, and an older edition is not opened under its replacement's row (D12; Carter, 6 Nov 2026, revising the rollback rule decided by Carter on 2 Nov 2026).
    3. In the same transaction, call `UserDataRemap.reverse(conn, release)` while this publish's redirects still exist. Then delete the rows the forward apply wrote to `corpus_redirects` and `corpus_tombstones` (neither table is referenced by user rows), and re-insert from the before-snapshot the rows the forward apply deleted, so a reclaimed piece's earlier redirect and an un-retired ID's earlier tombstone come back with the rows they belong to. There is no separate reverse-remap step to run.
    4. Still in the same transaction, and only after step 3's delete, retire every row the publish inserted, with a new tombstone whose `reason_code` is `rolled-back` (2.1's reserved reason), rule `other`, no `removal_key`, and the sentence "This passage was added in a corpus update that has been undone." These tombstones are written after the delete, so they survive it, and bookmarks made during the window show them. These rows exist in live and are absent from the snapshot, and that absence is their D4 explanation. None is deleted, since users may have bookmarked them during the window. Then refresh the outline of every touched document.
    5. After commit, switch `chunks_live` back to `corpus_publishes.previous_qdrant_collection` and record `rolled_back_at`.
    The previous Qdrant collection and the snapshot are kept until the rollback window closes (4.1b).
  - **Cleanup.** `publish.py cleanup --release <name>` calls `drop_corpus_staging()` (2.2a), which drops every staging table and returns its space at once (about 210 MB for the full corpus, per 4.0's projection). It runs after the apply and its smoke checks (4.1b step 10) and needs the same lock gate. Rollback stays possible afterwards, because it rebuilds staging from the snapshot. Deleting the previous Qdrant collection and the snapshot, after the window, is a separate ops step.
  - **Staging read override, for the pre-cutover checks (4.2).** A new API setting `CORPUS_READ_SCHEMA` (`services/api/app/config.py`, default `public`). When it is `staging`, `app/db.py` sets `search_path` to `staging, public` and `default_transaction_read_only` to `on` inside the session on every pool acquire, and reads them back (decided by Carter on 4 Nov 2026; Supabase's pooler drops the second as a startup setting). The corpus tables in `staging` have the live names, so every unqualified query reads the staged corpus and every user table still resolves to `public`, and the session cannot write. `corpus_schema` (2.2b) probes columns in `current_schema()`. Paired with `QDRANT_READ_COLLECTION=chunks-<release>` (2.2b), the in-process eval harness (`services/api/scripts/run_eval_suite.py`, which persists nothing) searches the staged corpus exactly as production will. The deployed API refuses to start when the setting is anything but `public` (a check in the `app/main.py` lifespan), so production can never read staging.
  - **Writer code.**
    - `writers/reader_writer.py`: delete `clear_collection`, `prune_missing_chunks` and `prune_missing_documents`. `write_document` becomes `write_staged_document(conn, doc)` and writes only into `staging.*`, with the new document facts, works and passage fields.
    - `publication.py`: the `ReaderStore` and `SearchIndex` protocols (`:85-102`) lose `wipe`, `prune_documents`, `reset` and `prune`. `PostgresReaderStore` (`:251-276`) and `QdrantSearchIndex` (`:279-301`) become staging stores. `_validate_build` (`:224-248`) moves into the report as a warning section, since retirements are now explained one by one rather than capped at 10%.
    - `writers/qdrant.py`: remove `QDRANT_COLLECTION` (`:15`); every function takes the collection name. Remove `delete_collection_points` (`:62-67`) and `prune_missing_points` (`:88-108`) from the publish path. Add `alias_target(client, alias)`, `copy_points(client, source, target, ids=None)` (scroll with vectors and payload, then upsert) and `switch_alias(client, alias, new, old)`.
    - `qdrant_schema.py`: replace `CHUNKS` and `recreate_chunks` (`:12`, `:17-29`) with `create_chunks_collection(client, name)`. It refuses with `SystemExit` when `name` already exists or is an alias, creates the collection with today's vector and HNSW settings (`:21-27`), and creates payload indexes `collection`, `genre`, `issuer`, `document_id` (keyword) and `searchable` (boolean, D5). Vectors stay in memory, `on_disk=False` as today (4.0 step 5).
    - `writers/search_writer.py:build_point` (`:39-63`): the point ID is `Passage.id`. Add `genre`, `issuer`, `searchable`, `voice` (C-01), `embed_sha256` and `embed_model` to the payload. `author` becomes the author shown to users, which is `passage_author` when set, then the work's author, then the document's. `write_document` (`:83-101`) takes the target collection and a vector-reuse lookup.
    - `writers/search_writer.py:build_embedding_input`: when it picks the previous and next neighbour, it skips passages with `searchable = false` and takes the nearest searchable passage in the same chapter key instead, or none (C-21). Its prefix uses the same resolved display author as the payload `author`, not `doc.author` (C-15). Nothing else in the input changes (Decision log "Dedup and the republish's embeddings").
    - Each publish records the embedding model and dimensions in `corpus_publishes` (`embed_model`, `embed_dimensions`) and each point carries `embed_model`, so the text and model behind every vector can be audited (C-23).
    - `datapipeline/model.py`: `Document` gains the 2.2a document facts (`genre`, `issuer`, `issuer_label` and the rest). `works`, `Passage.work_key`, `searchable`, `language`, `passage_author`, `voice` and `superseded_by_anchor` already exist from 2.1 (D11). `Passage` gains `id` (from the passage registry) and `note`.
    - `datapipeline/config.py`: add `QDRANT_WRITE_COLLECTION` (default unset, meaning `chunks-<release>`) and `QDRANT_LIVE_ALIAS` (default `chunks_live`).
  - **Other writers (D11).** Every other script that writes to the corpus or Qdrant (the list verified under Current state) either writes through `QDRANT_WRITE_COLLECTION` and the lock, or is retired:
    - `stages/reader.py`: retired. It clears and rewrites a live collection, which D2 forbids. `pipeline.py` drops its `reader` stage; a V5 run that needs the reader store runs `publish.py stage` instead.
    - `stages/embed.py` and `stages/bm25_index.py`: take the target collection from `QDRANT_WRITE_COLLECTION`, which is required for them (no default, so they can never fall back to `chunks` or to the alias), and keep 0.4's `repair` gate. `stages/embed.py` already uses the embedding cache.
    - `stages/enrich_io.py`: keeps 0.4's `repair` gate. It writes only `annotation` and `annotation_vector`, which no publish writes, so it needs no collection setting.
    - `scripts/backfill_missing_vectors.py`, `scripts/reembed_drifted_vectors.py` and `scripts/reconcile_qdrant_payloads.py`: replace `QDRANT_COLLECTION` with `QDRANT_WRITE_COLLECTION` (required when `--apply` is set) and keep 0.4's `repair` gate. Their libraries `backfill_vectors.py`, `reconcile.py` and `reembed.py` make no writes and name no collection, so they do not change. These scripts exist because Postgres and Qdrant used to be written by separate runs. After P4 a 2.2w publish writes both from one staging build, so retiring them is a follow-up once one steady-state publish has shipped.
    - `qdrant_schema.recreate_chunks`: removed (above).

    A test, `test_no_writer_names_the_chunks_collection`, searches the datapipeline source for a hard-coded `"chunks"` Qdrant collection name outside tests and fails on any hit, apart from `writers/qdrant.PRE_ALIAS_COLLECTION`, the one definition the stage's two refusals use.
  - **Docs.** Rewrite `datapipeline/README.md` ("Publish one collection", "Narrow repair commands") and `datapipeline/SOURCES.md` ("Publishing a collection") around stage, report, apply, switch, rollback and cleanup. Update the datapipeline line in the repo `CLAUDE.md` Quick Commands, which today shows `run_collection.py --target both`, and correct CLAUDE.md section 4's claim that Qdrant holds `facets` and `questions` collections (C-28).
- **Acceptance checks:**
  - New `datapipeline/tests/test_stage_apply.py`, run against a throwaway local Postgres with 0037, 0038, 0040, 0041, 0042 and 0043 applied, the way `datapipeline/tests/test_reader_writer_outline.py` starts one, and against an in-memory Qdrant (`AsyncQdrantClient(location=":memory:")`; whether local mode supports aliases is unverified, and a fake alias store is the fallback):
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
    - `test_single_collection_publish_copies_other_collections`, `test_point_count_check_includes_copied_collections` (a one-collection stage passes, and a missing copied point fails it), and `test_renamed_collection_old_points_are_not_copied`.
    - `test_rollback_keeps_its_rolled_back_tombstones`: after rollback, every row the publish inserted is retired and has a `rolled-back` tombstone, and none of the forward apply's tombstones or redirects remain.
    - `test_unretired_row_loses_its_tombstone`.
    - `test_embedding_cache_hit_skips_openai` and `test_cache_miss_is_written_to_cache_before_upsert`.
    - `test_tombstone_row_from_registry_entry`: a `passage` entry yields `reason_code`, `public_reason`, the rendered `church_act` and the derived `rule`; a `span` entry yields no row.
    - `test_passage_moved_between_documents_keeps_its_id`.
    - `test_registry_override_beats_adapter_searchable`.
    - `test_history_passage_gets_superseded_by`.
    - `test_rollback_calls_reverse_remap_in_the_same_transaction`.
    - `test_rollback_restores_deleted_redirects_and_tombstones`: publish A redirects a split piece, publish B reclaims it (deleting A's redirect row) and un-retires another ID (deleting its tombstone), then B is rolled back. A's redirect and the tombstone are back, the piece is retired again, its old URL resolves through the redirect to the absorbing piece as after A, and the user-table counts equal those before B.
    - `test_alias_switch_is_one_call`.
    - `test_neighbour_window_skips_unsearchable` (`index.no_unsearchable_neighbour_text`): a current passage between a history passage and a Latin canon is embedded with neither's text.
    - `test_embedding_prefix_uses_display_author`: a passage whose work is credited to Firmilian is embedded with "Firmilian", not the document author.
    - `test_voice_reaches_staging_and_payload` and `test_publish_records_embedding_model`.
    - `test_report_dedup_collision_rate` on synthetic vectors.
    - `test_rollback_apply_restores_rows_alias_and_outline`: after apply, cleanup and rollback, every corpus row equals the before-snapshot except the rows the publish inserted, which are retired with `rolled-back` tombstones; the alias points at the previous collection.
    - `test_cleanup_drops_staging_only`: after `cleanup`, the staging tables are gone, every `public` table is unchanged, and the next `stage` recreates them.
    - `services/api/tests/test_staging_read_override.py`: with `CORPUS_READ_SCHEMA=staging` the pool's `search_path` is `staging, public`, a write raises a read-only error, and the app lifespan refuses to start.
    - `test_apply_refuses_without_lock_match`, `test_each_subcommand_asks_for_its_step` (stage, apply or rollback), `test_apply_refuses_stale_report`. The loopback exemption itself is tested in 0.4.
  - `datapipeline/tests/test_run_collection.py::test_live_publish_points_to_publish_py`, and the removed flags are rejected.
  - Existing tests that exercised `clear_collection`, the prune functions, `--wipe-reader` or `--reset-search-index` are removed or rewritten against staging, and the PR lists each one.
  - Local rehearsal (D8). On a local Postgres restored from a production `pg_dump` and a local Qdrant seeded by copying the production points read-only, run stage, report, apply, cleanup and rollback for one collection whose release report shows no redirect that a user row points at (until 4.1a merges, `apply` refuses any other; pick it from the report, since P1 may already have added redirects to Catechism pieces). Then run stage and report, without apply, for all collections. The full apply and rollback of every collection, with 4.1a's remap inside, is rehearsed in 4.1a. No eval runs against staging in this item (decided by Carter on 4 Nov 2026); the read override's first use on a staged corpus is 4.2. Record the apply transaction's duration, the peak database size, and the report's count of live IDs kept, retired and redirected. If this is the first full stage on Carter's Mac, it fills the embedding cache; record the token count. Then stage the same build a second time and confirm it makes no embedding call. The counts of `retrievals`, `bookmarks`, `retrieval_labels`, `guest_trial_retrievals` and `reading_progress` are equal before apply, after apply and after rollback. The dump is deleted afterwards.
  - PR description must include the rehearsal timings and sizes, the apply duration for all collections, the list of removed CLI flags, and the sentence "No code path left in the datapipeline deletes a live chunk or document row."
- **Production safety:** Merging changes no live data, and the publish lock holds every live path. After this PR no datapipeline path can delete a live chunk or document, so the cascade into user tables cannot fire from a publish. A stage into production writes only the `staging` schema and a Qdrant collection no alias points at, which users never read. But staging carries the live indexes, including the full-text index the eval needs, so it adds about 210 MB (4.0's projection) to a database at 402 MiB, and 4.0 puts the apply's peak at 490 to 590 MB. Supabase Pro holds that easily (0.6), and the Free Qdrant cluster's 1 GiB holds two collections because their vectors are reclaimable page cache (4.0 step 5). No production stage runs before 4.0's window, and `cleanup` runs as soon as the apply is checked. The read override cannot reach production, because the deployed API refuses to start with it. The apply is one transaction. Readers keep seeing the old rows until commit (MVCC). Moving positions takes row locks that make a concurrent bookmark or retrieval insert on the same passage wait until commit, so the apply runs in 4.1b's quiet window, and its duration from the rehearsal decides whether that is acceptable. The alias switch is atomic, and `rollback` is one command within the window.
- **Needs Carter:**
  - Approval of the `pg_dump` for the local rehearsal (D8).
  - For each production stage and apply, a reviewed change to `PUBLISH_LOCK.json` adding an entry for the collection and release, and a second one removing it after the rollback window. The first is P4's 4.1b.
  - The first production stage waits for 4.0 (storage and the `VACUUM FULL` window). Approve the embedding spend, about 11 million tokens (about $1.40) at the first full local rehearsal stage, which fills the cache, then between 0 and that amount at the production stage, depending on how much changed in between.
  - Answered 4 Nov 2026: the rollback window is 14 days (4.1b).
  - Answered 4 Nov 2026: the On the Incarnation early retirement below is not taken up (1.8d).
  - Found by 2.2a (2 Nov 2026): whether the writer stages, snapshots, applies and rolls back the contents tree (`staging.document_contents`) with the chunks. Decided by Carter on 2 Nov 2026: yes (stage step 4, the snapshot, apply step 1 and rollback step 2 above).
  - Found by 2.2w (2 Nov 2026): whether the apply and rollback derive `reader_access` again for every document they touch. Decided by Carter on 2 Nov 2026: yes, and the apply refuses on a difference from the staged value (stage step 4, apply step 1, rollback step 2 above).
  - Found by 2.2w (2 Nov 2026): what the stage does while 2.2b has not yet created the alias. Decided by Carter on 2 Nov 2026: it refuses (stage step 6).
- **As built, part (a) (2 Nov 2026).** PR (a) builds the CLI's `stage`, `report`, `status` and `discard`, the stage, the report and every removal above; the spec's facts that the code showed differently:
  - Files: `publish.py` (the CLI), `publication.py` (`build`, `prepare`, `StageRunner`), `retirements.py` (stage step 5, pure functions), `release/staged.py` (the report), `writers/reader_writer.py` (`ensure_staging`, `clear_staged_collections`, `write_staged_document`, `copy_live_annotations`, `write_staged_retirements`), `writers/search_writer.py` (`VectorSource`, `display_author`, `embedding_prefix`) and `writers/qdrant.py` (`alias_target`, `copy_points`, `clear_staged_points`, `check_vectors`; every function takes the collection name). `switch_alias` arrives with the apply in part (b).
  - Skipping what the removal registry retires is done once, in `publication.build` (`registry.drop_removed`, `registry.removed_document_ids`), rather than in each adapter; a dry run applies it too. Overrides and IDs are `registry.apply_overrides` and `registry.assign_ids`. A registry row's `note` now sets `Passage.note` (the `chunks.note` column) instead of `metadata["note"]`.
  - `church_act` is rendered "<issuer>, <act>, <year>", which is what the example above shows ("Second Council of Constantinople, anathema 11, 553"); the template "<act>, <issuer>, <date>" disagreed with its own example.
  - Passage redirects point at the target in the old passage's own document first, then the earliest by position, as 0.1c orders them; anchor redirects of a redirected row use the same target. An old anchor or chapter key that a staged passage of the same document still carries gets no redirect, since it resolves directly.
  - A document the build no longer emits is explained by a `document` removal entry, or by a `works.json` `supersedes` naming a staged document, which yields a `document` redirect.
  - The stage copies each staged passage's live `annotation` and `annotation_vector` into staging by ID. No publish writes annotations, so this makes staging read as live will after the apply; the apply in part (b) leaves the live columns alone.
  - The report exports live read-only with `scripts/export_live_snapshot.read_live` (retired rows left out) into its own folder and runs 0.1c's `release.report.run` with the staged corpus as the build. Its one write is `corpus_publishes.report_sha256`, stored as `<sha256 of report.json and publish.json>:<sha256 of every staging row>`, and only when every check passes; that write asks the lock for the `stage` step the stage needed. The 10% shrink and churn checks are its warnings section.
  - A renamed collection (5.1b.3) is `StageRequest.renames` (new key to old key); 5.1b.3 adds its CLI flag.
  - `run_collection.py` keeps `--limit` for dry runs. The V5 `reader` stage (`stages/reader.py`) is removed in part (a), since it called `clear_collection`. `writers/qdrant.QDRANT_COLLECTION` stays, named only by the V5 stages and the repair scripts, until part (c) moves them to `QDRANT_WRITE_COLLECTION`.
  - Tests removed with the code they tested: `tests/test_reader_writer_outline.py` and `tests/test_reader_writer_contents.py` (live `write_document`; replaced by the staged outline and contents tests), the old-runner tests in `tests/test_collection_publication.py`, and the prune and `write_document` tests in `tests/test_reader_writer.py`.
- **As built, part (b) (4 Nov 2026).** PR (b) builds `apply` (with `--no-switch` and `--retire-only`), `switch`, `rollback` and `cleanup` in `publish.py`, the snapshot, apply, switch, rollback, cleanup and retire-only code in `writers/apply.py` (with `UserDataRemap` and `RemapLedger`), and `tests/test_apply_rollback.py`. The spec's facts that the code showed differently:
  - The before-snapshot is one gzipped JSONL file per table (`documents`, `chunks` without `search_vector`, `document_works`, `document_contents`, `document_chapters`, and the `corpus_tombstones` and `corpus_redirects` rows the apply deletes), with `{file: sha256}` in `corpus_publishes.snapshot_sha256`. It is read inside the apply transaction, under the publish lock and before any write (not in a separate transaction before it), so a concurrent apply of the same release cannot overwrite it with applied rows; it is written only for an unapplied publish, and an applied publish's snapshot is never overwritten. `--retire-only` takes its snapshot the same way. `chunk_count` is not in it, since the outline refresh recomputes it.
  - `chunks` has a unique key on `(document_id, anchor)` that covers retired rows. When a staged passage carries an anchor a retired row still holds (a returning text, 1.8d) or a retiring row's anchor (a piece whose text moved, 1.10b), the retired row keeps its anchor with the suffix `#retired-<release>` (accepted by Carter on 4 Nov 2026; 2.4a checks such a link). Live rows move to `~<anchor>` during the transaction, and the apply refuses if any temporary anchor is left. An old anchor does not reach its new passage through a redirect until 2.4a reads `corpus_redirects`, and saved rows do not move until 4.1a; both must be live before the Phase 4 apply.
  - The apply refuses while a user row points at a passage redirect, or a `reading_progress` row at an anchor or chapter redirect, and no remap is passed (`referenced_redirects`). It also refuses any retirement that is not explained by a staged tombstone or passage redirect (D4).
  - The rollback loads the snapshot into staging and leaves it there, so it clears `cleaned_up_at`; run `cleanup` again after a rollback. It also refuses while staging holds another publish. The alias moves back (or a retire-only publish's points become searchable again) after the commit; if that step fails, running `rollback` again finishes it instead of refusing. A rollback refuses while a publish applied after it is still in place (roll that one back first), and it re-reads the publish under the lock, so an overlapping rollback refuses instead of deleting the first one's `rolled-back` tombstones. The retry runs only while no other publish has been applied or rolled back since this rollback. A rollback holds the publish lock from its first read to the alias restore, so no cleanup or other rollback runs in between. `switch` and `rollback` hold that lock as a session-level advisory lock across several statements, so the datapipeline's `DATABASE_URL` must be a direct or session-mode connection (Supabase's pooler on port 5432, as today), never transaction mode (port 6543), where the lock could stay held on a pooled connection. `switch` holds the publish lock throughout, refuses a release a later publish superseded, and records the old target before moving the alias, so a retry after a lost reply keeps it. Every row the publish inserted is retired with a `rolled-back` tombstone, and a row the publish un-retired is retired again under the tombstone or redirect the snapshot puts back.
  - `--retire-only` is built as the spec's On the Incarnation procedure describes, and records `flipped_points.json` in the snapshot folder. Only points that were searchable are flipped and recorded, so its rollback never makes a point searchable that was not before. Carter left On the Incarnation until the Phase 4 apply (4 Nov 2026), so nothing calls it yet.
  - Local rehearsal (4 Nov 2026, on the Lenovo, decided by Carter on 4 Nov 2026 in place of D8's `pg_dump` on his Mac). Postgres 17 held a read-only export of production's corpus tables, with the user tables cut to keys and placeholder IDs (export 2.4 s). A file-based local Qdrant held a read-only copy of production's 54,555 points (copied in batches of 128 with pauses, 9 min, in an hour with no searches), plus the alias `chunks_live`, which production does not have yet. The driver pointed `DATABASE_URL` and Qdrant at the machine itself, so the lock's loopback rule passed and nothing could reach production. Results:
    - A stage with no `chunks_live` refused and wrote nothing.
    - Stage of all collections: 421 documents and 54,303 passages; 0 new IDs, 0 tombstones; redirects 1,515 passage, 38,603 anchor and 6,366 chapter. 85 min, 832 embedding calls and 15,619,257 tokens (about $2.03 at $0.13 per million, checked 4 Nov 2026), throttled to about 250,000 tokens a minute because the key's limit is shared with live search. That is about 40% more than the 11 million tokens estimated above. The cache holds 54,294 vectors (749 MB), since nine passages share their input with another.
    - Report of all collections: publish checks pass; 53,040 live IDs kept, 0 retired, 1,515 redirected, 1,263 new. 0.1c's two failing checks are both known defects (`anchor_reuse`). Redirects that user rows point at: 109 retrievals, 1 guest retrieval and 10 reading positions, in bible, church-fathers, councils, medieval and summa. 4 min.
    - Second stage of the same build: every vector from the cache, 0 embedding calls, 15 min.
    - apostolic-exhortations, whose redirects no user row points at: stage 30 documents and 3,053 passages, copying the other nine collections from the alias target (6 min); report: 3,004 kept, 0 retired, 20 redirected, 49 new. Apply: the transaction took 1.8 s (27 s with the snapshot and the local Qdrant load), touched 30 documents, inserted 49 passages, retired 20 and wrote 388 redirects, then switched the alias. Cleanup dropped staging. Rollback: the transaction took 2.4 s; afterwards all 3,024 live passages equalled the snapshot field for field, the 49 inserted passages were retired with `rolled-back` tombstones, the redirects were gone, the outlines matched, and the alias pointed at `chunks` again.
    - `retrievals` 4,266, `bookmarks` 25, `retrieval_labels` 3, `guest_trial_retrievals` 88 and `reading_progress` 35 were equal before apply, after apply, after cleanup and after rollback.
    - Peak database size 537 MiB (about 189 MiB before staging), during a stage of all collections. Production is 403 MB, and the local copy leaves out the pgvector columns and user content.
    - The export, the local database and the Qdrant copy were deleted afterwards. The apply duration for all collections was not measured: the rehearsal applies one collection, and 4.1a rehearses the full apply with its remap. The eval against staging moves to part (c).
- **As built, part (c) (4 Nov 2026).** PR (c) builds `CORPUS_READ_SCHEMA`, moves the other writers to `QDRANT_WRITE_COLLECTION` and rewrites the docs. The spec's facts that the code showed differently, and what it adds:
  - `app/db.py` also refuses a connection whose `search_path` or `default_transaction_read_only` does not read back as set, and a database with no `staging.chunks`, where `search_path` falls through to `public` (after `cleanup`, say) and every query would still succeed. The settings go in through `set_config` in the pool's `init` and `setup` hooks, since the pooler dropped `default_transaction_read_only` at startup and asyncpg's `RESET ALL` clears a `SET` on release. Checked through production's pooler on 4 Nov 2026: read-only held across a reuse of the connection and `CREATE TEMP TABLE` was refused.
  - The lifespan's refusal runs before `init_pool` and outside its `try`, which would have swallowed it. Any value but `public` or `staging` also refuses at `init_pool`, so a typo cannot read live in process.
  - `QDRANT_COLLECTION` is gone. The stage's refusals (`publication.py`, `writers/qdrant.clear_staged_points`) keep their protection of the pre-alias collection through `PRE_ALIAS_COLLECTION`, which matters once `chunks` is no longer the alias target but is still a rollback target.
  - `writers/qdrant.write_collection()` is the required name. `scan_collection()` is what a dry-running repair script reads: `QDRANT_WRITE_COLLECTION` if set, otherwise `QDRANT_LIVE_ALIAS`, so a dry run on production waits for 2.2b's alias or must name a collection. Explicitly naming a live collection stays possible behind the `repair` gate, or the scripts could not repair anything.
  - `pipeline.py` names the collection too (`_run_embed`), and `_guard_live_writes` refuses `embed` and `bm25-index` with none named before any stage runs.
  - The eval against staging is not run (decided by Carter on 4 Nov 2026), so 2.2b's `QDRANT_READ_COLLECTION` is not needed by this PR, and this part's only production reads were the two pooler connections above, which read no table.
- **Out of scope:** The user-data remap's rules and merge policy (4.1a supplies the implementation this item calls). The cutover runbook, backups and smoke checks (4.1b). The V5 `stages/` engine, which stays behind the lock (0.4). Hard-deleting retired rows and deleting old Qdrant collections (ops after the rollback window). Genre and issuer filters in the API (5.1a).

#### Optional ops step: early retirement of On the Incarnation (D7 exception, 1.8d)

- **What:** D7 allows one change to live data before Phase 4, if Carter approves it. He decided on 4 Nov 2026 not to take it up, so this procedure stays only in case he reopens it. Lawson's 1944 translation of On the Incarnation is under copyright (1.8d), so its 47 passages and its document (`cf235300-e37d-5a7a-a421-f50efff38355`) may be retired early. They are retired, not deleted (D3). This is the one procedure for it (D11); 1.8d points here.
- **How:**
  1. A PR adds a `document`-scope removal-registry entry for `cf235300…` with reason `translation-in-preparation` (rule `other`, derived) and the tombstone "This translation is being replaced with a public-domain one; the text returns when it is ready." The same PR adds a lock entry `{"collection": "church-fathers", "release": "incarnation-withdraw", "steps": ["apply", "rollback"], ...}`.
  2. `publish.py apply --retire-only --collection church-fathers --release incarnation-withdraw`, which stages nothing new and creates no Qdrant collection. Its `corpus_publishes` row sets both `qdrant_collection` and `previous_qdrant_collection` to the collection `chunks_live` targets. It takes the before-snapshot as any apply does. In one transaction it retires the document and its 47 passages, writes their tombstones from the registry entry (as in stage step 5) and refreshes the outline. It then sets `searchable = false` on the 47 points in that collection, so each stays a point (D5), records their point IDs in the before-snapshot folder (`flipped_points.json`), and switches no alias.
  3. Restart the API to clear the one-hour `/sources` cache.
  4. If it must be undone within the window, `publish.py rollback --release incarnation-withdraw` restores the rows from the before-snapshot, deletes this release's tombstones, sets `searchable = true` again on the points listed in `flipped_points.json`, and switches no alias, because none was switched. The removal-registry entry is then closed (`closed_by`, 2.1) in a PR.
  5. After the rollback window, a PR removes the lock entry.
- **Requires, in this order:** 2.2a's 0042 and 0043 applied; 2.2b deployed with the alias in use; 2.4a and 2.4b deployed, so the reader shows the removal page and history shows the tombstone. Then the reviewed lock-file change above.
- **User impact (29 Sep):** 1 retrieval and 0 bookmarks point at the document's passages. The retrieval row is kept and restores as a tombstone.
- **At Phase 4:** 1.8d's PR closes the document-scope entry (`closed_by: "1.8d"`, 2.1; entries are never deleted), and the P4 build carries Robertson's text. The apply un-retires the document under the same ID, and the 47 old passage IDs get redirects to the new sections by 1.8d's mapping. 2.4a checks redirects before tombstones, so old links reach Robertson's text.

---

### 2.2b. Qdrant alias, searchable flag and retired filtering on the search path

- **Type:** PR, plus two ops steps
- **Depends on:** none to merge. Its Postgres filters take effect once 2.2a's 0042 is applied. The alias ops step needs Carter. 2.2w adds the datapipeline's `QDRANT_WRITE_COLLECTION` and the alias-aware collection creation.
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
  - New module `services/api/app/corpus_schema.py`, the one place that knows which 0042 objects exist:

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
    def visible(alias: str) -> str        # "AND <alias>.retired_at IS NULL", or "" without 0042
    def invalidate() -> None              # called on UndefinedColumnError / UndefinedTableError
    ```

    Probe once at startup (in the lifespan, after the pool) and lazily after the TTL. Any query that fails with `asyncpg.UndefinedColumnError` or `UndefinedTableError` calls `invalidate()` and retries once with the legacy SQL, as `routes/documents.py:123-132` does.

    Built by 2.4a (#183), which merged first: `services/api/app/corpus_schema.py` has `current()`, `invalidate()`, `visible` as a method (`schema.visible("c")`), `probe()`, `run_with_fallback(fn)` (the invalidate-and-retry, with `LEGACY` as the schema without 0042) and `CorpusSchema.lifecycle` (retired rows and tombstones or redirects exist). `facts` also covers the passage columns `chunks.language, note, passage_author, work_key, superseded_by`. The probe reads `information_schema` over `current_schemas(false)`, so under `CORPUS_READ_SCHEMA=staging` it describes the staged tables. 2.2b adds the search-path uses.
  - `retrieve_fts.py`: build `_SQL` from the schema. With `searchable`, add `AND c.searchable`. With `retired`, add `AND c.retired_at IS NULL AND d.retired_at IS NULL`. Without 0042, the SQL is byte-identical to today's.
  - `retrieve_vector.py`: add `must_not=[FieldCondition(key="searchable", match=MatchValue(value=False))]` to the filter once the read collection has the boolean payload index on `searchable` (decided by Carter on 10 Nov 2026: production's Qdrant runs in strict mode and refuses a filter on an unindexed field; `qdrant_client.searchable_indexed()` reads the collection's payload schema at startup and every five minutes). Points without the field do not match `must_not`, so they stay searchable. Every passage is a point (D5); a non-searchable passage is a point with `searchable = false`. Retired passages are either absent from the collection (2.2w never writes them into a new one) or carry `searchable = false` (the On the Incarnation early retirement), so this one filter covers both in Qdrant.
  - `fetch_context.py` (stitch): add `AND c.searchable` and the retired predicate when present. A stitched part that is hidden is dropped; when no part is left, the card has no attachment, which is today's behavior on a stitch failure.
  - `fetch_positions.py`: select `searchable` and `retired_at` when present and return which IDs are hidden. `pipelines/runner.py` drops a vector candidate whose Postgres row is hidden or missing. This is defense in depth for a Qdrant point that disagrees with Postgres, including the seconds between a 2.2w apply and its alias switch. On the degraded path it is skipped and the Qdrant filter alone applies.
  - Ops step 1 (Carter), before or after the PR is deployed with the default `chunks` (the filter waits for the index it creates): create the alias `chunks_live` pointing at `chunks` with `update_collection_aliases([CreateAliasOperation(create_alias=CreateAlias(collection_name="chunks", alias_name="chunks_live"))])`. Create the boolean payload index on `searchable` on `chunks` (builds an index; deletes nothing).
  - Ops step 2 (Carter): set `QDRANT_READ_COLLECTION=chunks_live` in the API's Railway environment and restart. Check `/health/search` reports the alias and the `chunks` target.
- **Acceptance checks:**
  - `services/api/tests/test_retrieve.py`: `test_search_vector_excludes_only_explicit_unsearchable` asserts the filter has `must` on collection and `must_not` on `searchable == False`, and nothing else. `test_search_vector_uses_configured_read_collection` sets `QDRANT_READ_COLLECTION=chunks_live` and asserts `collection_name == "chunks_live"`.
  - New `tests/test_retrieve_fts_sql.py`: with a schema lacking 0042 the SQL equals today's text exactly; with 0042 it contains the searchable and retired predicates. A real-SQL variant on `pg_cluster` seeds a searchable row, a `searchable = false` row, a retired row and a row in a retired document, all matching the same term, and asserts only the first returns.
  - `tests/test_stitch.py`: `test_unsearchable_parts_are_not_attached` and `test_retired_parts_are_not_attached`.
  - `tests/test_dedup.py`: `test_neighbor_fetch_reads_configured_collection`.
  - `tests/test_startup_wiring.py`: health reports alias and target.
  - A runner test that a vector hit whose Postgres row is retired is dropped.
  - Alias behavior against a real server: a test marked `qdrant_live` (skipped unless `QDRANT_TEST_URL` is set) runs against `docker run qdrant/qdrant` at the production server version, creates `chunks` with 3 points (one `searchable=false`, one without the field), creates alias `chunks_live`, and asserts `query_points`, `retrieve` and the health call all work through the alias, and that the `must_not` filter returns the two expected points. The PR records the server version tested.
  - PR description must state the rollout order (merge, ops 1, ops 2), the rollback (unset `QDRANT_READ_COLLECTION`), and the result of the live-Qdrant test.
- **As built (#340, 10 Nov 2026):**
  - Production's Qdrant is version 1.18.2 with strict mode on (`unindexed_filtering_retrieve: false`), one collection `chunks` of 54,555 points, a keyword index on `collection` only and no alias (read 9 Nov 2026). Strict mode is why the filter waits for the index (Decision log "Searchable filter waits for its index (2.2b)"); the first deploy without the guard would have failed every vector search with a 400. `/health/search` also reports `qdrant_searchable_filter`, whether the filter is on.
  - The health check maps the read name to its collection with `get_aliases` (`qdrant_client.resolve_read_target`) and calls `get_collection` on the target, so it does not depend on `get_collection` accepting an alias. Production's 1.18.2 server accepts an alias in `get_collection` too (checked at ops step 1).
  - The predicates are one method, `CorpusSchema.searchable_sql(chunk, document)`, used by `retrieve_fts.build_sql`, `fetch_context.build_sql` and `fetch_positions.build_sql`. The position lookup selects a `hidden` flag and `fetch_positions` drops a hidden vector candidate itself, beside its existing orphan drop, rather than `pipelines/runner.py`. The drop is logged, not recorded as a degradation.
  - The stitch and runner acceptance checks are in `tests/test_retrieve_fts_sql.py` with the real-SQL checks, since they share its database (`test_unsearchable_parts_are_not_attached`, `test_retired_parts_are_not_attached`, `test_runner_drops_a_vector_hit_whose_row_is_hidden`). The alias test is `tests/test_qdrant_alias.py`: it runs in qdrant-client's local mode always, and against a server, including one in strict mode, when `QDRANT_TEST_URL` is set. This machine has no Docker, and downloading the Qdrant server binary was refused, so the server variant was not run.
  - Both ops steps ran on 10 Nov 2026, after the merge: the `searchable` index and the alias `chunks_live` → `chunks`, then `QDRANT_READ_COLLECTION=chunks_live` on Railway. Search reads through the alias with the filter on; the 12-query comparison through it matched the code before 2.2b.
  - Production had never analyzed the 0042 columns, so the planner misjudged the predicates (a nested loop, 46 ms instead of 13 ms on church-fathers) and a different top 40 among passages tied on score came back for 5 of 12 sample queries. Carter approved `ANALYZE` of `public.chunks` and `public.documents`, run on 10 Nov 2026. Afterwards the plans matched today's, and retrieval for the 12 queries matched the code before the change exactly: vector hits, full-text rows in order, candidates after the position lookup, and stitched articles.
- **Production safety:** With the default `chunks`, the API reads exactly the collection it reads today. No live point has a `searchable` field, so the `must_not` clause matches nothing. Before 0042 is applied, `corpus_schema` reports nothing and the SQL is unchanged. After 0042 is applied, every row is searchable and none is retired, so the predicates keep every row. Creating an alias changes nothing for a client that does not use it. Switching the env var to the alias reads the same collection. From then on, 2.2w's apply switches `chunks_live` to its new collection, and rollback switches it back. If 2.4a deploys before this item, 2.4a still works, because each item adds its own predicates through the same `corpus_schema` module; whichever merges second reuses it.
- **Needs Carter:** Ops step 1 (create the alias and the `searchable` payload index) and ops step 2 (Railway env var and restart). Both touch live infrastructure.
- **Out of scope:** Building new collections, on-disk vectors and quantization (2.2w, 4.0, 4.1b). Genre and issuer filters in the API (5.1a); 2.2w writes and indexes the payload fields. The `facets` and `questions` collections, which the API does not read.

---

### 2.2c. search_vector rebuild

- **Type:** PR (a migration, written and tested now), then ops: the migration is applied by hand in 4.0's approved window, before 4.1b step 1. It was a decision item until Carter chose the rebuild on 9 Oct 2026 (Decision log "Keyword search (2.2c, C-16)").
- **Depends on:** 2.2a (the staging schema copies the live column definition), 2.2b (the searchable and retired predicates). Applied inside 4.0's window.
- **Goal:** Keyword search stops treating Bible verse markers as words and can find a passage by its citation: "canon 1055" finds canon 1055, "CCC 2267" finds the passage holding that paragraph, and "John 3" or "Psalm 23" finds the chapter's passages. A verse inside a pericope ("John 3:16" in "John 3:1–21") is found by its chapter only; verse-level lookup needs the query parsed as a citation, which is a retrieval follow-up.
- **Current state:**
  - `chunks.search_vector` is `tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED` with a GIN index (`supabase/migrations/0004_v2_documents_chunks.sql:26-27, 40`). Postgres recomputes it on every insert and every update of `content`.
  - It is the only FTS column the API queries: `retrieve_fts.py` matches `plainto_tsquery('english', <the user's question>)` and orders by `ts_rank`. `annotation_vector` (0019) is written by enrichment only.
  - Storage on 28 Sep: `search_vector` about 49 MB of 380 MB; TOAST 203 MB (plan).
  - Found by the 6 Oct reviews (C-16, Opus A-007), on a local Postgres loaded from the snapshot with the 0004 column: `{{v:4}}` becomes the tokens `v` and `4`, so a search for "John 3:16" returns 1 and 2 Maccabees passages that contain "John" and the markers 3 and 16; "psalm 23" returns Acts and Judith; "canon 1055" returns nothing. References and titles are in no `search_vector`, and `plainto_tsquery` requires every word of the question, so "CCC 2267" needs a token "ccc" that no content holds. Postgres's default parser also keeps a reference's punctuated forms whole: `to_tsvector('english', 'John 3:1–21')` holds `'1–21'`, and `'CCC §2267'` holds `'§2267'`, so indexing the reference as it is would match "canon 1055" but not "ccc 2267" (checked on Postgres 14 by the branch review, 9 Oct 2026).
  - The other parts of C-16 are owned elsewhere: ligatures and line-end hyphens (1.10a), the 18 canons with corrupted spellings (1.5a), and archaic verb forms such as "loveth", left to a retrieval follow-up.
  - Changing a generated column's expression rewrites the table under an exclusive lock, as `VACUUM FULL` does. Postgres 17 can do it with `ALTER TABLE … ALTER COLUMN … SET EXPRESSION`; older servers need `DROP COLUMN` and `ADD COLUMN … GENERATED`. The production server is Postgres 17.6 (checked by 2.2a, 2 Nov 2026), so `SET EXPRESSION` is available; the migration still checks it.
- **Changes:**
  - A migration, numbered when it merges (2.2a took 0042 and 0043; 0039 is unused), that redefines the column as `setweight(to_tsvector('english', regexp_replace(content, '\{\{v:\d+\}\}', ' ', 'g')), 'A') || setweight(to_tsvector('english', regexp_replace(coalesce(reference, ''), '[§:;,.()–—-]', ' ', 'g')), 'B')` and recreates its GIN index. The second `regexp_replace` turns the reference's punctuation into spaces, so "CCC §2266–2267" indexes `ccc`, `2266` and `2267`, and "John 3:1–21" indexes `john`, `3`, `1` and `21`. Content keeps the higher weight, so a passage matched by its text ranks above one matched only by its citation. Both functions are immutable, as a generated column requires. This is the one migration in the cleanup that is not purely additive; Carter approved it because it changes a derived column only and loses no data.
  - It does not run on merge. The migration file is applied by hand in 4.0's window, with the `VACUUM FULL`, before 4.1b step 1 builds staging. 0043 creates the staging tables at migration time (`create_corpus_staging()`, `CREATE TABLE IF NOT EXISTS`), so they would keep the old expression: the same window runs `drop_corpus_staging(); create_corpus_staging();` right after the rewrite, and 2.2w's shape check compares generation expressions as well as columns. Its Supabase ledger entry is recorded when it is applied, not at merge. Because the rewrite also compacts the table, 4.0 measures whether the window then needs a separate `VACUUM FULL`.
  - Non-English and retired passages still leave FTS through the `searchable` and retired predicates (2.2b), not through the tsvector.
  - No API change. `retrieve_fts.py` keeps its query; the weights only change `ts_rank` order.
  - The post-cutover check in 4.2 becomes: `SELECT count(*) FROM chunks WHERE search_vector IS DISTINCT FROM <the new expression>` returns 0.
- **Acceptance checks:**
  - A migration test on `tests/pg_cluster.py`: after the migration, a Bible passage's vector holds no lexeme produced by a `{{v:N}}` marker (`fts.no_marker_tokens`); "canon 1055" returns `can/1055`, "ccc 2267" returns the passage whose reference cites CCC 2267, "john 3" and "psalm 23" return passages of those chapters, and a content-only match ranks above a reference-only match (`fts.reference_lookup`).
  - After the rewrite, the recreated `staging.chunks.search_vector` has the new generation expression.
  - The same test runs the migration on the server versions the repo supports (`SET EXPRESSION` and drop-and-add) or fails clearly.
  - A local timing of the rewrite on a restore of the snapshot's `chunks` (or the D8 dump), recorded for 4.0's window.
  - 4.2's keyword-search checks (canon 1055, CCC 2267, John 3) pass on staging and on production. 4.2 compares no rankings since 0.3 was dropped (30 Oct 2026).
- **As built (12 Nov 2026):**
  - The migration is `supabase/migrations/0045_search_vector_markers_and_reference.sql` (0044 was the last on master when it was written; check again at merge). It drops `chunks_search_vector_idx`, changes the expression with `SET EXPRESSION` on Postgres 17 or drops and re-adds the column on 12 to 16, and builds the index once afterwards; older servers fail with a message. It sets `lock_timeout = '5s'` (4.0's value) and `statement_timeout = 0` for its own transaction.
  - 2.2w's shape check did not compare generation expressions. `reader_writer.staging_shape_problems` now does, and compares each column's rank instead of its attribute number, because the drop-and-add path leaves a gap in live's numbering that `LIKE` closes in staging, which made the check refuse every stage.
  - Tests: `services/api/tests/test_search_vector_migration.py` (`fts.no_marker_tokens`, `fts.reference_lookup`, the content-over-reference ranking, the recreated staging, the post-cutover check) and `datapipeline/tests/test_stage_apply.py::test_stage_refuses_staging_made_before_a_generated_column_changed`. This machine has Postgres 16 only, so they ran the drop-and-add path; the `SET EXPRESSION` path has not been run (downloading a Postgres 17 build was refused).
  - Local timing (12 Nov 2026, Postgres 16 on the Lenovo, the 31 Oct snapshot's 54,555 passages without `metadata`): 9.4 s; `chunks` 186 MB before and 181 MB after (heap 74 to 80 MB, indexes 56 to 38 MB, the GIN index 18 to 16 MB); recreating staging 0.05 s, `ANALYZE` 0.4 s. On the same restore, keyword search restricted to the collection, as `retrieve_fts.py` runs it, returns canon 1055 for "canon 1055", `CCC §2263–2267 (part)` for "ccc 2267", John 3:1–21 and 3:22–36 among the first six for "john 3" (with Luke 3, 1 John 3 and 3 John, which also hold both words), and Psalms 23:1–6 first for "psalm 23". Before the rewrite the first two returned nothing. "john 3:16" now returns no Bible passage instead of Maccabees.
  - The marker pattern covers every marker in the snapshot: all 32,171 have the form `{{v:N}}`. The 2,535 lexemes `v` left after the rewrite come from text (roman numerals such as "Book V"), not markers.
- **Production safety:** Merging changes nothing. The rewrite runs only in 4.0's window with Carter's approval (NEEDS-CARTER section A); search and the reader pause while it runs, as for `VACUUM FULL`. Rollback is the previous expression applied the same way. The API works with either definition. Between 4.0 and the cutover, production keyword search already uses the new definition, before 4.2 has checked it; the change only removes marker tokens and adds reference matches at a lower weight, and the migration test plus a free rerun of 4.2's keyword-search checks on the restored dump are the check before the window.
- **Needs Carter:** Answered 9 Oct 2026: rebuild, in 4.0's window (Decision log). The run itself is approved with 4.0's window.
- **Out of scope:** Changing the text search configuration, synonyms for archaic forms, title or author weighting, and `annotation_vector`.

---

### 2.3. Document facts in the registry

- **Type:** PR (registry fields, validation, and the facts section of the release report)
- **Depends on:** 2.1 (work registry with frozen IDs), 0.2 (rights inventory, for source credits), 2.2a (columns), 2.2w (the writer that stages them). 1.3b decides corrected papal genres, in `datapipeline/papal_genres.csv` and each papal document's `metadata["genre"]`; this item carries whatever 1.3b decides. 1.3b also records each papal document's form (`metadata["form"]`), which a follow-up carries to `documents.form`.
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
  - Cum Sancta Mater Ecclesia is stored as 1858, but its dating line reads 27 April 1859, in the thirteenth year of Pius IX (elected June 1846), so the year is 1859 (C-05, Opus-2 B-008). It is the only mismatch among the 164 papal documents with a dating line; Salutis Nostrae's source prints "1744" for 1774, and its metadata already has 1774.
- **Changes:**
  - Registry (2.1's tracked file): add per-document fields `genre, issuer, issuer_label, year, date_display, translation, source_credit, certainty, attribution_note, notes, clavis_ref, superseded_by`. Works use the `works` shape 2.1 already defines (D6, D11); this item fills their values. Which passages belong to a work is recorded per passage as `work_key` in 2.1's passage registry, never by anchor or position range. Validation in the registry loader:
    - `certainty` is one of the four values.
    - `genre` is a value of 2.1's genre module (`registry/genres.py`), or null where no genre applies.
    - `issuer` is a lowercase hyphenated slug and `issuer_label` is present whenever `issuer` is (D11).
    - `source_credit` is present for every document (source from 0.2).
    - `year` is an integer or null.
    - `superseded_by` names a registered document.
  - Value rules:
    - `translation`: the edition or translator shown to users, for example `Ante-Nicene Fathers (1885-1896)`, `Nicene and Post-Nicene Fathers, Series I`, `Vatican English`, `WEB-C` kept for the Bible (the web maps codes to names, `apps/web/src/components/sources/SourcesPage.tsx:12`). The `(collection, title, translation, author)` unique key allows this.
    - `issuer` and `issuer_label` (D11): for papal documents the pope, from `metadata.pope`, as `pope-leo-xiii` and "Pope Leo XIII"; for council documents the council, as `second-vatican-council` and "Second Vatican Council"; for the Catechism and the Code, `holy-see` and "Holy See". Filters use `issuer`; cards and the reader show `issuer_label`.
    - `year` stays the sortable integer; `date_display` carries ranges and "c.". Cum Sancta Mater Ecclesia's year is 1859 (C-05).
    - `source_credit`: exactly the wording 0.2's rights inventory records per source (decided by Carter on 13 Nov 2026, Decision log "Source credits for document facts (2.3)"): vatican.va texts get `© Dicastery for Communication – Libreria Editrice Vaticana`, CCEL ThML texts `Sourced via CCEL.org`, the Bible `Public domain. Sourced via eBible.org`, Trent `Translated by J. Waterworth (1848). Text: papalencyclicals.net`, and a document still showing papalencyclicals.net's text of unknown rights `Text: papalencyclicals.net`. A document holding texts of a second edition names both in one line. Never derived from a ThML `<description>`.
    - `translation` is empty where the credit line already names the translation ("Translated by …", "Translation from …"), so an opened passage does not show it twice (Carter, 13 Nov 2026).
  - `datapipeline/model.py` fields and the staging writer are 2.2w's; this item fills them from the registry in each adapter's document construction.
  - Release report (0.1c, staged mode in 2.2w): a "Document facts" section with a per-field, per-collection count of values that differ from live, and the list of documents whose `author` changes. This replaces the backfill script an earlier draft proposed; there is no separate live write (D7).
- **As built (14 Nov 2026):** facts recorded by the implementing PR.
  - Registry. The facts sit flat on each `works.json` entry, `registry.FACT_FIELDS`: `genre, issuer, issuer_label, year, date_display, translation, source_credit, attribution_note, notes, superseded_by, superseded_note`. `certainty` and `clavis_ref` are not held twice: the build takes them from the entry's `attribution.certainty` and `attribution.clavis` (2.1), which 3.2 fills. `registry.validate` checks the rules above on every entry that carries facts (`_validate_facts`). A document an open `document` removal holds (the 51 papal documents awaiting permission) builds nothing, carries no facts and needs no credit; 384 of the 435 entries carry facts.
  - Where they are set. Not in each adapter's document construction: `publication.build` sets them on every Document after the removals (`registry.apply_document_facts`), so the registry wins over the adapter, and a dry run and a stage see the same values. An entry with no facts leaves the adapter's values.
  - Generated. `scripts/document_facts_registry.py` writes them from a build (`document_facts.derive`), the rights inventory and the entry; it changes only `works.json` and is idempotent. The rules are in `document_facts.py`: the translation line by source file, the corrected years (Cum Sancta Mater Ecclesia 1859; the Summa 1265, shown "1265 to 1274"), and `COMBINED_CREDITS` for the seven councils holding a second edition. A value already set for `attribution_note`, `superseded_by` or `superseded_note` is kept. `tests/source_checks/test_document_facts_sources.py` fails when `works.json` differs from what the script would write, so an adapter's year or notes, a papal genre or a credit line cannot change without a rerun.
  - Rights inventory. The credit lines Carter set on 13 Nov 2026 are written into `rights_inventory.json`: 177 vatican.va rows (planned rows included) take the © line, the 73 Bible rows, Trent, and Ubi Lutetiam's papalencyclicals.net row (Haerent Animo and Menti Nostrae, rebuilt from their printings by 1.3d before this merged, carry the credits Carter approved for those). `tests/test_document_facts.py` checks that every `source_credit` is its row's `credit_line`, or starts with it where the row has `also_from` editions.
  - Values. genre: `encyclical` 72, `apostolic-exhortation` 32, `apostolic-letter` 14, `apostolic-constitution` 4, `motu-proprio` 1, `other` 1 (1.3b's 124 built papal documents, checked against `papal_genres.csv`), `catechism` 1, `code` 1, none 258. issuer: 162 documents, 44 issuers (each pope, each council, `second-vatican-council`, `holy-see`). translation: empty for the 49 whose credit names the translation (any credit but a source-only one: "Sourced via …", the © line, "Public domain. …", "Text: …", the USCCB notice) and for Ubi Lutetiam; "Vatican English" for the vatican.va texts; "Ante-Nicene Fathers (1885-1896)", "Nicene and Post-Nicene Fathers, Series I" or "Series II", or the translator for the rest; `WEB-C` kept for the Bible.
  - Not filled. No Church Fathers work (142) and no Bible book has a year or date, and none has a genre; council documents have no genre (D5 lists none for councils). 215 documents have no year.
  - Dating lines. `checks/dating_lines.py` reads each papal manifest page's last dating line ("Given at/in …", "From the Vatican, …", an editor's "[Dated: …]", the Italian "Dato a Roma …"), with inline markup joined and ordinal years read ("the 1826th year of the Incarnation"): 168 of the 175 pages print one (164 was an earlier count). Only Cum Sancta Mater Ecclesia (fixed to 1859) and two misprints of the source disagree, listed in `MISPRINTS` with their reasons: Salutis Nostrae ("1744" for 1774) and Peregrinantes ("1149" for 1749, the ninth year of Benedict XIV). Quo Graviora's page prints "the 1826th year", which its year matches; the 13 March 1825 date 1.3b found on vatican.va is not checked.
  - Release report. The staged report's markdown gains "Document facts (2.3)" (`release/staged.facts_md`): the per-field, per-collection count of documents whose value differs from live, new documents counted apart, and every author change. The staged report against a fresh snapshot was not run, since it needs a database seeded from live; the PR gives the same counts computed from the build against the 31 Oct snapshot.
- **Acceptance checks:**
  - A vendored check that every papal document's `year` equals the year of its dating line where the source prints one, with a reviewed exception list for source misprints (Salutis Nostrae).
  - Registry validation tests: every document has `source_credit`; every `genre` is in 2.1's genre module; every `issuer` is a slug with an `issuer_label`; every work has at least one passage whose `work_key` names it in a build; no `<description>` text appears in any registry field (checked against the extracted blurbs of the vendored ThML files).
  - `datapipeline/tests/test_stage_apply.py` (2.2w) gains `test_document_facts_reach_staging_and_live_after_apply`.
  - Locally, the staged report against a fresh snapshot shows the facts diff. The PR description pastes the counts per field and per collection.
- **Production safety:** Nothing reaches live data before the Phase 4 apply. At the apply, the new columns are filled in the same transaction as the text, and the Qdrant payload carries the same author, genre and issuer, so Postgres and Qdrant agree from the first second. If 2.4a is not yet deployed, the new columns are simply unread.
- **Needs Carter:** The source credit wording where 0.2 has not settled it. Answered 13 Nov 2026: the wording above, every recommendation accepted.
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
        issuer: Optional[str] = None        # slug, for filters
        issuer_label: Optional[str] = None  # shown to users
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
        read_elsewhere_url: Optional[str] = None
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

    `Tombstone.read_elsewhere_url` is set only for a retired document (or a passage of one) whose removal entry is `document`-scope with reason `translation-in-preparation` or `awaiting-permission`, or for a passage whose `passage`-scope entry has reason `awaiting-permission` or, in the `councils` collection, `translation-in-preparation` (1.2a's gap register and 1.2e's fallback; Carter, 4 Nov 2026): it is the document's `metadata.held_text_url` when set (a partly rebuilt document, 1.3d step 6, or a rebuilt council with gaps, 1.2c to 1.2e), otherwise its `metadata.url`, so the removal page can say where the text can still be read (1.3d; Carter, 31 Oct and 1 Nov 2026; ADR 0001). It is null otherwise.

    `ChunkSource` and `BookmarkSource` gain `facts: Optional[DocumentFacts]`, `language: Optional[str]`, `passage_note: Optional[str]`, `passage_author: Optional[str]`. `ChunkResult` and `BookmarkResponse` gain `status: Literal["current", "moved", "removed"] = "current"`, `tombstone: Optional[Tombstone]`, `redirect: Optional[Redirect]`. `DocumentResponse` gains `facts`, `works: list[WorkInfo]` and `status`. `ReaderPassage` gains `language`, `note`, `work_key`, `passage_author` and `superseded_by` (the current passage's ID, set only on a history passage).
  - Superseded text in the reader (rule F, D11). The chapter query returns history passages (`superseded_by IS NOT NULL`) with the chapter, so the reader can show them as "earlier text" beside the current passage. They are never search results, because `searchable` is false. A history passage is not retired; the visibility predicate below does not hide it.
  - Work-level fields override document-level ones in `DocumentFacts` when a passage has a `work_key` (author and certainty for "Dubious or Spurious Writings." come from the work, not the document). A passage's `passage_author` overrides both for the author shown.
  - New step `rag/steps/document_facts.py`, called from `pipeline.py` after ranking and before the chunk events. One query per search: `SELECT ... FROM documents d WHERE d.id = ANY($1)` plus `document_works` for the `(document_id, work_key)` pairs and `chunks.language, note, work_key, passage_author` for the result IDs. The card's author comes from this query, not from the Qdrant payload. Timeout 1 s; on failure it records via `degradation.record_recovery` (as `fetch_context` does) and events go out without `facts`. Guest search uses the same pipeline (`routes/guest_search.py:359`), so guests get the fields too.
  - Chunk event `source` adds `facts`, `language`, `passage_note`, `passage_author`. The event shape change is additive.
  - Visibility predicate. `corpus_schema.visible(alias)` returns `AND <alias>.retired_at IS NULL`, or an empty fragment when 0042 is absent. Apply it to:
    - `routes/documents.py`: `_DOCUMENT_SQL` and fallbacks, the legacy TOC, first chapter and chapter key queries, the anchor lookup at `:227-229` and the passage query at `:239-243`. `document_chapters` is already built from non-retired rows by 2.2a's function.
    - `routes/sources.py`: hide retired documents. The one-hour cache is cleared by the API restart in 4.1b (and after the On the Incarnation early retirement).
    - `routes/reading_progress.py`: the chapter label lateral join uses visible rows; a progress row whose document is retired is left out of `GET /reading-progress` lists and returns `status: "removed"` with the tombstone on the single-document GET.
    - History restore and bookmarks do **not** filter; they join retired rows on purpose and mark them.
  - Tombstone and redirect resolution, in a new `app/corpus_lifecycle.py`:
    - `async def resolve_passages(conn, ids) -> dict[str, Resolution]`, where `Resolution` is `current`, `moved(redirect)` or `removed(tombstone)`. Order of checks: a row with `retired_at IS NULL` in a document with `retired_at IS NULL` is `current`; else a `corpus_redirects` row for the ID, following at most 3 hops, is `moved`; else a `corpus_tombstones` row is `removed`; else `current` (a retired row with no record is treated as today's behavior and logged as a warning, since 2.2w's D4 check should make it impossible).
    - `async def resolve_document(conn, doc_id, anchor=None, chapter=None) -> Resolution` with the same order, using the `entity = 'anchor'` redirects for an old `?anchor=` and the `entity = 'chapter'` redirects for an old `?chapter=`. Either may point to another document (1.8b's split).
  - `routes/search.py:get_search_results`: after the existing join, call `resolve_passages`. `moved` results carry the redirect and the new passage's content and source; `removed` results carry `status: "removed"` and the tombstone and **no content** (decided by Carter on 9 Nov 2026): `content` is the empty string, since the field stays required for today's web, with no footnotes, context or facts. `restore_status` counts moved and removed results as present, so a restore with removals is still `complete`.
  - `routes/bookmarks.py:list_bookmarks`: same resolution.
  - `routes/documents.py`: for a document that is not visible, `get_document`, `get_document_toc` and `get_document_reader` return HTTP 410 with body `{"detail": "removed", "tombstone": {...}}` when a document tombstone exists, HTTP 404 with body `{"detail": "moved", "redirect": {...}}` when a redirect exists, and today's 404 otherwise. An anchor or chapter key that no longer exists in a visible document returns the chapter from the anchor or chapter redirect, with `highlight_anchor` set to the new anchor, a `redirected_from` field, and the new `document_id` when the redirect points to another document.
  - `require_document_access` for guests: keep the join, but also allow a document reached through a redirect from a passage the guest retrieved.
  - Explanations persisted in `retrievals.explanation` are returned unchanged for moved and removed results; the web decides whether to show them.
  - Hard-coded Bible title (C-24, Opus-2 B-015). `routes/evaluate.py:44` names "Song of Solomon" in its prompt. 1.4a renames the book "Song of Songs", which reaches users at the Phase 4 apply, after this item deploys. The prompt names the book "Song of Songs (Song of Solomon)", so it reads correctly before and after.
- **Acceptance checks:**
  - `tests/test_search_routes.py`: `test_restore_marks_removed_passage_with_tombstone_and_no_content`, `test_restore_follows_redirect_to_new_passage`, `test_restore_with_removal_is_complete`, `test_restore_without_0042_is_unchanged` (golden JSON of today's response, plus the new fields at their defaults), `test_restore_shows_corrected_text_for_same_id` (D1).
  - `tests/test_bookmarks.py`: removed and moved bookmarks, note preserved.
  - `tests/test_reader_chapter_endpoint.py` and `test_reader_outline_endpoints.py`: retired passages are not in the chapter; a retired document returns 410 with the tombstone; a redirected document returns 404 with `redirect`; an old anchor returns the new chapter and `redirected_from`; outline and fallback paths agree when some rows are retired.
  - `tests/test_sources_endpoint.py`: retired documents hidden.
  - Retired-anchor suffix (decided by Carter on 4 Nov 2026). When a retired passage's anchor is taken by a current passage, 2.2w's apply keeps the retired row's anchor as `<anchor>#retired-<release>`. `test_reader_chapter_endpoint.py`: `?anchor=<anchor>%23retired-<release>` opens that passage's tombstone notice cleanly, not a 404 and not the current passage's chapter. Web: a bookmark or history card on such a passage builds its link with `readerHref`, which must encode the `#` as `%23` so it is not read as a URL fragment, and the reader must send the anchor back to the API unchanged and find its element by ID (`getElementById`, never a CSS selector). Checked by reading the code on 4 Nov 2026 (`URLSearchParams` in `readerHref` and `getReaderChapter`, the proxy forwarding `url.search`, `getElementById` in `DocumentReader`); the tests make it binding.
  - `tests/test_reading_progress.py`: removed document leaves the list.
  - `tests/test_pipeline_persistence.py` or a new `test_document_facts.py`: chunk events include `facts` when 0042 exists; the author shown comes from Postgres when the payload disagrees; a failing facts query still yields chunk events without `facts` and records a recovery, not a degradation.
  - `tests/test_document_access_and_failures.py`: guest access through a redirect.
  - `tests/test_contract_models.py`: every new field optional; an event without them validates.
  - The evaluate prompt test names both "Song of Songs" and "Song of Solomon".
  - PR description must include before-and-after JSON for one search event, one restore and one reader response, and state that every added field is optional.
- **As built (#183, 9 Nov 2026):**
  - The shared models are in `app/models/corpus.py` (`DocumentFacts`, `WorkInfo`, `Tombstone`, `Redirect`, `RedirectedFrom`). `Redirect` also has `chapter_key`, set for a chapter redirect. `ReaderChapter.redirected_from` is a `RedirectedFrom` (`document_id`, `anchor`, `chapter_key`) naming what the request asked for; `document` is then where it moved to. `ReadingProgressItem` gains `status` (`current` or `removed`) and `tombstone`.
  - A moved result keeps its saved `chunk_id`; `redirect.chunk_id` is the passage it moved to, whose content and source it carries.
  - Source credit. `ChunkSource.source_credit` stays the API's derived credit for excerpt-only documents (`reader_access.py`). `facts.source_credit` is `documents.source_credit`, except that an excerpt-only document's required notice (the USCCB's, the LEV line) replaces it, so the legally required wording is never replaced by the registry's.
  - A tombstone's removal scope is not stored (`corpus_tombstones` has `removal_key` only). For `read_elsewhere_url`, a passage counts as document-scope when its document has a `document` tombstone, as 2.2w writes for every passage of a removed document.
  - The reader answers an anchor that names a removed passage of a live document, suffixed or not, with 410 and the passage's tombstone, as for a removed document. An anchor or chapter with no visible passage and no record keeps today's behavior (the first chapter, or "Chapter not found").
  - The facts query is one statement (`chunks` joined to `documents` and `document_works`). On production it executes in 0.2 ms; from the Lenovo the round trip is about 250 ms (median of 20 reads, 9 Nov 2026), so the live pipeline runs it beside the reader-access and footnote lookups. Not measured from Railway.
  - The acceptance checks run against a real Postgres migrated through 0043 in `tests/test_corpus_lifecycle.py` (restore, bookmarks, reader, outline and fallback, sources, reading progress, guests, the HTTP bodies and the suffixed anchor), with `tests/test_corpus_schema.py`, `tests/test_document_facts.py`, `test_contract_models.py`, `test_search_routes.py::test_restore_without_0042_is_unchanged` and `test_evaluate.py`. The web checks are in `readerNavigation.test.ts`, `api.test.ts` and `DocumentReader.test.tsx`.
- **Production safety:** Before 0042 is applied, `corpus_schema` reports nothing, the facts step is skipped, no predicates are added and no resolution queries run, so every response is today's. After 0042 with nothing retired and no tombstones or redirects, every row is `current`, and the only change is that responses carry the extra optional fields; today's web ignores unknown fields. The 410 and redirect bodies can only occur after a 2.2w apply creates tombstones and redirects, and 2.4b must be live by then. Adding one query per search adds a few milliseconds (unverified; measure p95 before and after on the eval set).
- **Needs Carter:** Answered 9 Nov 2026: a removed passage shows no text. It shows the title, author, reference and one plain sentence of reason, with the Church act where one exists, and the "Read it at <site>" link where `read_elsewhere_url` is set (Decision log "Removed passages in saved searches and bookmarks").
- **Out of scope:** Rewriting user rows to new IDs (4.1a). Changing any SSE event type. Genre filters (5.1a).

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
  - Also found by the 6 Oct reviews:
    - Citations the card parses (Opus-2 B-003, B-011). `ChunkCard.tsx:mobileCitation` takes "Question N … Article N" out of the Summa reference, and strips the author from a citation only when it starts with the payload author. 1.7's new Summa citation ("Summa Theologiae II-II, q. 64, a. 6, co.: Whether …") no longer matches that regex, so mobile would show the raw string. On desktop, `primaryReference` prepends the document title to Fathers references that already hold it ("City of God, Augustine — City of God, Book I · Chapter 1"); after 1.10c drops the author from ThML references (C-15) the title still doubles.
    - A hard-coded title (C-24, Opus-2 B-015). `SourcesPage.tsx` sorts the Bible by `BOOK_ORDER`, which names "Song of Solomon" and puts unknown titles last; 1.4a's rename reaches users at the Phase 4 apply, after this item deploys.
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
    - `status === "removed"`: render a tombstone card with title, author, reference, `public_reason` and `church_act`, no content, no bookmark or feedback buttons, and a "Why was this removed?" link to the About page anchor (5.7 fills it; until then link to `/about`). The card is collapsed like its neighbours, in its collection's colours, with "Removed" or "Not available" where the score would be; the notice shows when it is opened (Decision log "Removal notice wording (2.4b)").
    - `status === "moved"`: render normally from the new content, with a muted line "This passage was renumbered in a corpus update."
    - Copy action: citation uses `formatAttribution` so a copied Pseudo-Justin passage is not credited to Justin.
    - Citations (Opus-2 B-003, B-011). `mobileCitation` parses both Summa forms, today's ("Question 19 … Article 9 - Whether …") and 1.7's ("q. 19, a. 9, ad 1: Whether …"), and never shows a raw string. `primaryReference` does not prepend the title when the reference already starts with it, for any collection.
  - `BookmarkCard.tsx`: same notes, translation and source credit under the text; tombstone and moved states; keep the user's note editable in both.
  - Reader:
    - `DocumentOverview.tsx`: attribution line becomes `formatAttribution · formatDate · formatTranslation`; show certainty, notes, supersession and the list of works with their own labels when `works` is non-empty; source credit at the bottom of the header section.
    - `ChapterSection.tsx`: source credit once at the end of each loaded chapter section. When a chapter's passages belong to a work whose attribution differs from the document's, show the work's label under the chapter heading.
    - `Passage.tsx`: no language note (rule E, revised 29 Oct 2026, leaves no non-English passage); `note` renders as a small muted paragraph after the passage; a `passage_author` renders as a small label above the passage.
    - Earlier text (rule F, D11). A passage with `superseded_by` set is not rendered in the reading flow. It renders as a collapsed "Earlier text (<year>)" control under the current passage it points to; opening it shows the older wording in muted text with the label "No longer in force". The year comes from the history anchor. Test: `ChapterSection.test.tsx::test_history_passage_shows_as_earlier_text_under_current`.
    - As built by 2.4a: a moved result keeps its saved `chunk_id` and carries the new passage in `redirect.chunk_id`; `redirected_from` is an object (`document_id`, `anchor`, `chapter_key`); a chapter redirect sets `redirect.chapter_key`; `ReadingProgressItem` has `status` and `tombstone`; a removed result's `content` is the empty string.
    - `DocumentReader.tsx` and `lib/api.ts` reader fetchers: on 410 with a tombstone, show a removal page (title, author, reason, Church act, back button, and "Read it at <site>" linking to `read_elsewhere_url` when set; the tombstone card shows the same link). On 404 with `redirect`, `router.replace` to the new document and anchor, keeping `from` and `returnKey`. On `redirected_from`, highlight the new anchor.
    - Guest reader shares these components (`isGuest`); no guest fork.
  - `SourcesPage.tsx`: use `formatAttribution` and `formatDate`; show a certainty tag. `BOOK_ORDER` lists "Song of Songs" and "Song of Solomon" at the same rank (C-24).
  - History restore: `useSearchPageExperience.ts` treats `removed` and `moved` results as present; no "results unavailable" notice for them.
- **Acceptance checks:**
  - `ChunkCard.test.tsx`: the collapsed header shows attribution and certainty tag and never the source credit; the expanded body shows translation, notes and credit in that order; the Bible translation badge renders from `facts`; a Catena passage shows its quoted author; removed status renders the tombstone without content and without bookmark buttons; moved status shows the renumbered line; copy text uses the attributed author; a result with no `facts` renders exactly as today (snapshot).
  - `BookmarkCard.test.tsx`: credit under the text; tombstone keeps the note.
  - `DocumentReader.test.tsx`: 410 shows the removal page; 404 with redirect replaces the URL; credit appears once per chapter section.
  - `lib/attribution.test.ts` for each formatter.
  - `SearchPage.test.tsx`: a restore with a removed result shows no unavailable notice.
  - `ChunkCard.test.tsx` also covers both Summa citation forms on mobile, and a Fathers card whose reference starts with its title (no doubled title).
  - `SourcesPage.test.tsx`: every Bible title `/sources` can return, including both names of the Song of Songs, has a rank in `BOOK_ORDER`.
  - `npm run lint` (0 errors, no new warnings in touched files), `npm test`, `npm run build`.
  - PR description must include screenshots at 375 px and desktop, dark and light themes, of a collapsed card, an expanded card with a credit, a tombstone card, the reader overview with works, and the removal page.
- **Production safety:** Every new field is optional. Before 2.4a deploys, or before 0042 is applied, all fields are absent and the components render today's output, which the snapshot tests hold. Tombstones and redirects cannot exist until a 2.2w apply (the Phase 4 apply, or the On the Incarnation early retirement if Carter approves it), and this PR must be live before either (4.1b checklist item).
- **As built (10 Nov 2026):**
  - Formatters are in `apps/web/src/lib/attribution.ts`; the removal and redirect wording, and the tombstone and redirect parsers, in `lib/corpus-lifecycle.ts`; the shared facts block and removal notice in `components/common/PassageFacts.tsx`; the reader's removal page in `components/reader/ReaderRemovedNotice.tsx`. `formatAttribution` takes an options argument (`work`, for "quoted in <author>'s <work>", and `certainty: false` where a certainty tag sits beside the line). The registry already writes "Pseudo-Justin" and "Anonymous" as the author (3.2), so only `disputed` adds words.
  - Live data on 10 Nov 2026: `facts` carries only the Bible's `WEB-C` translation and 219 document years; no tombstone or redirect exists. Until the Phase 4 apply the visible change is the Bible badge ("Bible · WEB-C") and the full translation name in the opened card.
  - The no-facts snapshots in `ChunkCard.corpus.test.tsx` were recorded by running the same test against master's `ChunkCard`, so they hold today's output, not this item's. The Fathers citation fix (Opus-2 B-011) changes one thing on today's data: a desktop Fathers card no longer prints its title twice.
  - The reader's 410 and 404-with-redirect become `ReaderRemovedError` and `ReaderMovedError` in `lib/api.ts`. A chapter answered with `redirected_from` naming another document replaces the URL with that document (`movedReaderHref` in `lib/readerNavigation.ts`), so later chapter loads read from it.
  - `/v1/sources` sends no `facts`, so the Library's formatters fall back to today's author and year until it does.
- **Needs Carter:** Answered 10 Nov 2026: the tombstone wording pattern (Decision log "Removal notice wording (2.4b)"). Where the credit shows is settled by the Decision log. Found by this item, open: the scanned-text label (1.2f), the canon-law text labels and the amended-canon Latin link (1.5a) reach no API field, so they are not shown; item 2.4f carries them (Carter, 10 Nov 2026).
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
  - Also found by the 6 Oct reviews (C-25, Opus A-015), claims this fix left standing: the Fathers text says "roughly the 1st through 8th centuries", though the corpus ends with Augustine and the Apostolic Constitutions (about 430); the medieval text names "canonists", and no canonist is in the corpus; the exhortations text calls them all "post-synodal", though Haerent Animo, Menti Nostrae, Evangelica Testificatio, Gaudete in Domino, Marialis Cultus, Signum Magnum, Redemptionis Donum, Redemptoris Custos, Gaudete et Exsultate, Laudate Deum, C'est la confiance and Dilexi te are not; the papal-documents text cites "defining dogmas (such as the Immaculate Conception)" and "reforming Church structures", but Ineffabilis Deus is filed under encyclicals and nothing in that collection reforms structures.
  - Both `/about` and `/guest/about` render this component (`apps/web/src/app/about/page.tsx`, `app/guest/about/page.tsx`).
- **Changes:** In `AboutPage.tsx` only:
  - church-fathers: "including Ignatius of Antioch, Justin Martyr, Irenaeus, Athanasius and Augustine."
  - medieval: "Works from Boethius (6th century) through the late Middle Ages, including Anselm of Canterbury, Bernard of Clairvaux and Thomas à Kempis." Adjust the period sentence to match.
  - Fix "counsels" to "councils".
  - Correct the four claims above (C-25): the Fathers period ends with the 5th century; drop "canonists"; call the exhortations "apostolic exhortations", without "post-synodal"; describe the papal-documents collection by what it holds (bulls, apostolic letters, a motu proprio). Carter approves the wording with the names.
  - Do not add counts; the full rewrite with counts from `/sources` is 5.7.
- **Acceptance checks:**
  - New `apps/web/src/components/about/AboutPage.test.tsx`: the rendered text contains none of "Origen", "Chrysostom", "Bonaventure", "Hildegard", "Scotus", "counsels", "8th centuries", "canonists", "post-synodal".
  - `npm run lint`, `npm test`, `npm run build`.
  - PR description must list each removed name with the live query result showing it absent (or, for Origen, scheduled for removal under rule A).
- **Production safety:** Copy change in one static component. Nothing depends on the text.
- **Needs Carter:** Approve the replacement names. Nothing else.
- **Out of scope:** The "What's in TheoCorpus and why" rewrite (5.7). Collection renames (5.1b).

---

### 2.4d. Rejected-voice role in the API and web

- **Type:** PR
- **Depends on:** 2.1 (the `voice` field, D5, D11), 2.2a (`chunks.voice`), 2.2w (writes it to staging and the Qdrant payload), 2.2b (`corpus_schema`, which says whether the column exists), 2.4a (the chunk event it extends), 2.4b (the card it extends). Must be deployed before 4.1b (Decision log "Rejected voices (C-01)", decided by Carter on 9 Oct 2026).
- **Goal:** A passage that states a position its document rejects reaches the rerankers, the explanation model, the result card and the reader with that role, so a condemned proposition or a pagan's argument is never presented as the Church's or a Father's teaching, and the condemnations stay findable.
- **Current state:**
  - The models learn a passage's role only from `unit_label`, through `services/api/app/rag/steps/passage_role.py:display_role`, which `rerank_docs` (the Cohere document and the listwise card) and `steps.explain` call. (The pointwise reranker that also called it was removed in October 2026.) `display_role` suppresses a label that the reference already contains. A comment in `rag/steps/rerank.py` (above `LLM_RERANK_CONTRACT_VERSION`) notes that an "Objection N" label marks a position the author states in order to refute it; nothing tells the models this about any other passage.
  - The card and the reader show no role.
  - 3.4 records 150 such passages (C-01; about 270 before the council texts were rebuilt): Exsurge Domine §1 to §41, the Syllabus §1 to §80, Constance's condemned articles, Nestorius's letter at Ephesus, Caecilius in the Octavius, and Mani's teaching in the Acts of Archelaus. 1.7 also sets `voice` on every Summa objection (10,527 bold objection markers in the source).
- **Changes:**
  - Carry `voice` from retrieval, the same way `unit_label` travels today, so the rerankers see it. 2.4a's facts query runs after ranking and only for the final results, so it is too late for the rerankers and is not the source. The path, in `pipelines/runner.py` order (`:391-402`):
    1. `ChunkCandidate` gains `voice: str | None = None` (`rag/steps/types.py`).
    2. Vector path: `retrieve_vector.py` reads `payload.get("voice")`, which 2.2w writes on every point.
    3. Keyword path: `retrieve_fts.py` selects `c.voice` when `corpus_schema` reports the column, so candidates found only by keyword search carry it. Without 0042 the SQL stays byte-identical to today's (2.2b's rule).
    4. `rrf.py` carries `voice` with first-writer-wins, as it does `unit_label` (`:54-59`).
    5. `fetch_positions.py` selects `voice` with `unit_label` when the column exists, and backfills any candidate whose value is missing, before reranking. On the degraded path, where `fetch_positions` is skipped, the payload value stands.
    6. `RankedChunk` gains the same field, and every constructor copies it from the candidate: `rerank_cohere.py:180` and `llm_rerank/listwise.py:55`. Stitched parts read it in `fetch_context.py`'s query and constructor (`:49`). `explain`, the chunk event and the judge then read it from `RankedChunk`.
    7. `compare/shared_runner.py` caches candidate pools, and the cached `ChunkCandidate`s carry `voice` like any other field.
  - `passage_role.py` gains `rejected_note(voice, unit_label) -> str | None`. For `voice == "rejected"` it returns one fixed line built from the label, for example "Rejected position (Condemned proposition 10): the document states this in order to reject it." Every caller of `display_role` adds it to that passage's card only: `rerank_docs`, `steps.explain`, and the eval judge in `rag/compare/judge.py`, so 4.2's judge sees what production's models see. Bump `LLM_RERANK_CONTRACT_VERSION`, as the comment above it in `rag/steps/rerank.py` asks whenever the rerank inputs change. The instruction explaining rejected positions is added to a prompt only when at least one card in the request carries the role. Until the Phase 4 apply gives any passage the field, every prompt stays byte-identical to today's.
  - Summa objections keep their label and also get the note once 1.7 sets `voice`. Stitching (`fetch_context`) is unchanged.
  - Web. `apps/web/src/lib/search-stream.ts`, the only SSE decoder, adds `voice?: string | null` to `ChunkSource`. When `voice === "rejected"`, the passage is marked only where its text shows (Decision log "Rejected-voice look (2.4d)"): `ChunkCard.tsx`'s opened body, `BookmarkCard.tsx` and the reader's `Passage.tsx` set the text off as a quotation, a rule down its left side and in italics, under a muted caption "<unit_label> · a position the document rejects". The collapsed card header shows the author line and the reference only: the Summa role tag that sat beside the reference moves to a muted caption above the opened text. The copied citation adds the label in brackets. Tokens only, no new colour. Guest pages share the components (`isGuest`).
- **Acceptance checks:**
  - `services/api/tests/test_passage_role.py`: `rejected_note` returns the line for a rejected passage and `None` otherwise.
  - Golden prompt tests for the Cohere document, the listwise card and the explanation input: a request with no rejected passage produces exactly today's text; a request with one adds the note to that card and the instruction once.
  - A runner-level test (`roles.voice_reaches_model_inputs`) through `pipelines/runner.py` with fake retrievers, rerankers and explainer, not prompt builders fed hand-filled fields. Three rejected candidates go in: one found only by vector search (voice from the payload), one found only by keyword search (voice from the SQL), and one whose payload lacks the field (backfilled by `fetch_positions`). Each reaches the Cohere document, the listwise card, the explanation input and the chunk event with its note. With the degraded path forced, the payload value still reaches the rerankers. The test runs every rerank mode the registry's pipelines use (Cohere alone, Cohere then listwise) on its scored path and on its RRF fallback path, and asserts `voice` survives to the explanation input, the chunk event and the judge input in each.
  - A structural test lists every `RankedChunk(` construction under `app/rag` and fails if one does not pass `voice`, so a new constructor cannot drop it.
  - Web: `ChunkCard.test.tsx`, `BookmarkCard.test.tsx` and `Passage.test.tsx` show the caption and the quotation for `voice: "rejected"` (and the collapsed header without either), and render exactly as today without it (snapshot).
  - 4.2's targeted questions check, on staging, the explanation of a condemned proposition, a Summa objection and a passage of Caecilius's speech.
  - `python3 -m pytest tests/`, `npm run lint` (0 errors, no new warnings in touched files), `npm test`, `npm run build`.
- **Production safety:** Every new field is optional, and no live passage has `voice` before the Phase 4 apply, so production prompts, cards and the reader stay as they are until then. 4.1b's checklist requires this item deployed before the apply. If it has not deployed when the Phase 4 build is frozen, that freeze PR marks 3.4's ranges `searchable = false` instead (Decision log).
- **As built (12 Nov 2026):**
  - `corpus_schema` reports `chunks.voice` as one of the `facts` passage columns (0042 adds them together), so `CorpusSchema` gained no new flag. The keyword SQL, the position lookup and the stitch query select `c.voice` when `facts` is set; without 0042 all three are byte-identical to before (`test_retrieve_fts_sql.py::test_without_0042_the_sql_is_todays`).
  - `passage_role.py` has `rejected_note`, `REJECTED_INSTRUCTION` (one text for every model) and `any_rejected`. The note is built from `unit_label` even where `display_role` suppresses the label; a rejected passage with no label gets "Rejected position: the document states this in order to reject it."
  - Where the note and the instruction go. Cohere document: the note is its own line after the `[reference] [role]` header, before the annotation. Listwise card: a line after the header. Listwise system prompt: the instruction as its own paragraph after the role rules, before the scoring bands (`listwise.system_prompt`). Explanation: the note on the line above "Passage (...)", outside the passage text, and the instruction appended to the system prompt for that request only (each explanation is one passage). Judge: the note on the line after `ref=... role=...`, and the instruction as a second system block after the cached rubric, so the cache prefix does not move.
  - Both contract versions moved: `LLM_RERANK_CONTRACT_VERSION = "structured-positional-v3-rejected-voice"` and `COHERE_RERANK_CONTRACT_VERSION = "cohere-doc-v3-rejected-voice"`, because the Cohere document changes too and the comment above the two constants keeps them separate.
  - The chunk event sends `source.voice` only when it is set, so no event changes before the Phase 4 apply. Saved searches and bookmarks read `voice` with the document facts (`document_facts.PassageFacts.voice`), and the reader with the passage fields (`ReaderPassage.voice`); `ChunkSource`, `BookmarkSource` and `ReaderPassage` type it as `Literal["rejected"]`. `routes/search.py:_as_chunk`, which rebuilds rows only for stitching, does not carry it.
  - The runner-level test is `tests/test_roles.py::test_voice_reaches_model_inputs` (five modes: Cohere scored and on its RRF fallback; Cohere then listwise, scored, on the listwise fallback, and on the Cohere fallback) and `test_degraded_path_keeps_the_payload_voice`. It drives `run_search_pipeline` and the real runner against a Postgres migrated through 0043, with fakes only for Qdrant, Cohere, the listwise provider and the explanation client. The golden prompt tests and the structural `RankedChunk(` check are in `tests/test_rejected_voice_prompts.py`; the system prompts are pinned by their SHA-256 on master.
  - Web: `PassageVoice` and `passageVoice()` in `lib/search-stream.ts`; `rejectedLabel()` in `lib/passageRole.ts`; the caption and quotation are `components/common/RejectedVoice.tsx`, which renders its children untouched when there is no label. The Summa role tag left the collapsed header for `RoleCaption`, above the opened text, which a rejected passage's caption replaces; the header's accessible name still includes the role. This part changes today's Summa cards on deploy. In the reader the caption replaces the inline superscript label. The no-voice snapshots in `ChunkCard.test.tsx`, `BookmarkCard.test.tsx` and `Passage.test.tsx` were recorded against master's components.
- **Needs Carter:** Answered 12 Nov 2026: the look (Decision log "Rejected-voice look (2.4d)") and the sentence given to the models, approved as drafted (Decision log "Rejected-voice note to the models (2.4d)").
- **Out of scope:** The ranges themselves (3.4). Stitching by reply targets (a retrieval follow-up). Any change to scoring, weights or candidate pools; the note is the only change to what the rerankers read.

---

### 2.4e. Passage links into vatican.va

- **Type:** PR
- **Depends on:** none (works against today's schema and data)
- **Goal:** An excerpt-only passage from vatican.va links to that passage on the vatican.va page, not the top of a long document, as Catechism passages already open the USCCB flipbook on their page.
- **Current state:**
  - `services/api/app/reader_access.py`: `source_url()` returns the document's `metadata.url`; `access_fields()` makes a passage-level link only for the Catechism (`catechism_pages.page_url`).
  - vatican.va paragraph anchors are not dependable: on 29 Oct 2026 Laudato Si' had 73 numbered `<a name>` anchors, Evangelium Vitae 2, Gaudium et Spes and Dignitas Personae none.
  - Text fragments (`#:~:text=`) work there: Gaudium et Spes opened with `#:~:text=only in the mystery of the incarnate Word` scrolled to §22 in headless Chromium (29 Oct 2026). Chrome, Edge, Safari 16.1+ and Firefox 131+ support them; other browsers open the page at the top, as today.
- **Changes:**
  1. In `access_fields()`, for a `source_url` on `vatican.va` or a subdomain, append `#:~:text=` and the passage's first words: about eight words of its content, stopping before any character the page may render differently (a footnote marker, a bracket), percent-encoded. A passage whose content starts with its own paragraph number keeps the number out of the fragment. `access_fields()` takes the passage content for this; its callers pass it.
  2. A datapipeline check (`checks/source_links.py`) that, for every vatican.va passage, finds the fragment's words in the vendored page's text, and reports the ones it cannot find. Those passages fall back to the plain URL through a list the API reads (`app/source_link_misses.json`), generated by the check.
- **Acceptance checks:**
  - Unit tests: a vatican.va passage gets a fragment of its opening words; a passage on another host, the Catechism and a full-reader document are unchanged; a listed miss gets the plain URL.
  - The check runs over the vendored vatican.va pages, and its miss rate is in the PR (expected low, since the passages are vatican.va's own text).
  - A headless Playwright run opens ten sampled links and confirms the page scrolled (`scrollY > 0`).
  - `python3 -m pytest tests/`, and the web tests if a card or reader link changes.
- **As built (#292, 9 Nov 2026):**
  - Live scope, read 9 Nov 2026: 80 excerpt-only documents whose `metadata.url` is on vatican.va (25 encyclicals, 28 apostolic exhortations, 16 councils, 11 papal documents), 7,063 visible passages, 1,157 saved results and 6 bookmarks on them. Canon Law also links to vatican.va, but to its index page, which does not hold a canon's text; only a document's own `metadata.url` takes a fragment, so its passages keep the plain URL, as the check would have listed them.
  - No vatican.va passage starts with its own paragraph number: the number is in `unit_label`, and the page prints it ("22. The truth is…"). The rule still strips one.
  - The rule is `fragment_text()` in `services/api/app/source_links.py`, which the check loads by path. Up to eight words, from the passage's first line of at least eight words (a heading line is its own block on the page, and a fragment matches within one block). It stops before a bracket, a note sign, a digit fixed to a word ("norms.12", taking the whole token unless it ends a word's punctuation), a lone number after punctuation (`"is love," 36`), or a quotation mark the stored text spaced from its words (`“ recover`). When fewer than three words come before a stop, it starts again after it, up to three times (`Jas. 1:17). As the Council…`). `-`, `,` and `&` are percent-encoded.
  - `access_fields()` takes `chunk_id` and `content`. Search cards, history restore and bookmarks pass them; a removed result passes no content and keeps the plain URL. The reader's 403 `reader_restricted` carries the fragment of the passage its `anchor` names; `/toc`, a reader request without an anchor and the reading-progress 403 keep the document URL, and the Catechism's 403 keeps the cover.
  - The check also sends to the plain URL a passage whose words stand earlier on the page in a place less like it (a repeated footnote opening such as "Cf. Second Vatican Council, Dogmatic Constitution on the"), judged by comparing the text after each match with the passage's. Results: 6,814 found, 178 repeated, 28 missing, 43 with no fragment; miss rate 2.93% of the 7,020 passages with a fragment, and 3.5% of all passages keep the plain URL. Most misses are footnote text stored as passages.
  - Headless Chromium over the vendored pages, served locally, agreed with the check: 249 of 250 sampled found links scrolled to the passage's block (the other scrolled into a tall notes block), 26 of the 28 missing links did not scroll, and the 2 that did use "…", which Chromium matched and the check does not. Ten live vatican.va links in four collections all scrolled.
- **Production safety:** API change only; the link stays the same document URL, so a fragment that fails to match opens the page as today. No data change.
- **Needs Carter:** None.
- **Out of scope:** Full-reader access for LEV texts (Decision log "LEV texts from vatican.va", 5.2). Links into the papalencyclicals.net texts, which stay on their document URL.

---

### 2.4f. Passage text labels and the amended-canon Latin link

- **Type:** PR (API and web)
- **Depends on:** 2.4a and 2.4b merged (the facts query and the opened card it extends). 1.5b for the canon-law fields: it writes the metadata this item reads. 1.2f's label is already written (`datapipeline/ocr/label.py`). Must be deployed before 4.1b (Decision log "Passage text labels (2.4f)").
- **Goal:** A reader can tell when a passage's text came from a scanned edition, when a canon's English is an unofficial translation with the Latin as the official text, and where to read the Latin of an amended canon that has no English. Earlier specs promised these labels to 2.4b, but the API sends no field for them (found by 2.4b, 10 Nov 2026).
- **Current state:**
  - 1.2f labels every passage built from scanned text with `chunks.metadata` `{"text_source": "ocr", "scan_id": ...}` (`datapipeline/ocr/label.py`). 1.2f's spec says 2.4b shows "a label such as 'Text from a scanned edition' when the passage is opened".
  - 1.5b (#158) writes `metadata["text_status"] = "unofficial_english"` and `metadata["official_latin_url"]` on the canons that show the L'Osservatore Romano English. Its label is fixed by the Decision log ("Canon law English and amendments (R2)"): "Unofficial English translation (L'Osservatore Romano). The Latin text is official." It also retires canons with no English (reason `translation-in-preparation`) with the tombstone "Canon N was amended in YEAR; no English translation is available", which promises a link to the Latin on vatican.va.
  - 2.4a's facts query (`services/api/app/rag/steps/document_facts.py`) reads no passage `metadata`. `Tombstone.read_elsewhere_url` is set for a passage-scope `translation-in-preparation` removal only in the `councils` collection (2.4a As built), so an amended canon's notice would have no link.
  - None of these passages is live before the Phase 4 apply, so nothing is missing from the site today.
- **Changes:**
  - API: the facts query also reads `chunks.metadata->>'text_source'`, `->>'text_status'` and `->>'official_latin_url'`, and the passage fields gain `text_source`, `text_status` and `official_latin_url` (all optional, default null) on `ChunkSource`, `BookmarkSource` and `ReaderPassage`. Only these three keys leave the API; the rest of `metadata` stays internal.
  - API: `read_elsewhere_url` for a `canon-law` passage-scope `translation-in-preparation` tombstone is that canon's Latin page on vatican.va. 1.5b records it in the Code's document `metadata.official_latin_urls`, a map from the retired canon's anchor (`can/295`) to its Latin page, as `held_text_url` serves councils (1.5b As built).
  - Web: `search-stream.ts` decodes the three fields once. The opened card, the bookmark and the reader passage show, in the facts block before the credit: "Text from a scanned edition" when `text_source` is `ocr` (Carter, 12 Nov 2026); for `unofficial_english`, the Decision log's sentence with "The Latin text is official" linking to `official_latin_url`. A collapsed card shows neither.
- **Acceptance checks:**
  - API: a passage with each key gets the field; a passage without them, and a database without the keys, gives today's payload (golden test as 2.4a's); a canon-law `translation-in-preparation` tombstone carries the Latin link; a councils one is unchanged.
  - Web: each label renders on the opened card, the bookmark and the reader passage, never on a collapsed card; a result without the fields renders exactly as today (the 2.4b snapshots).
  - `python3 -m pytest tests/`, `npm run lint`, `npm test`, `npm run build`.
- **Production safety:** Read-only API change and additive optional fields. No live passage carries these keys before the Phase 4 apply, so the site is unchanged until then.
- **As built (12 Nov 2026):**
  - API. `document_facts.TEXT_LABEL_COLUMNS` reads the three keys (`c.metadata->>'…'`, never the column) in the facts query and in the reader's passage query, both of which need 0042's columns, as 2.4a's fields do. `document_facts.text_labels()` keeps only `ocr`, `unofficial_english` and an `http(s)` link and drops anything else. The models type them `Literal["ocr"]`, `Literal["unofficial_english"]` and `str`. `PassageFacts.source_fields` adds them only when set, so the live chunk event is unchanged before the Phase 4 apply; restore, bookmark and reader JSON carry them as `null`, as 2.4a's and 2.4d's fields do (`test_search_routes.py::test_restore_without_0042_is_unchanged`).
  - Tombstone link. `_TOMBSTONE_SQL` joins the retired chunk for its anchor. For a `canon-law` passage-scope `translation-in-preparation` tombstone, `read_elsewhere_url` is the Code's `metadata.official_latin_urls` entry for that anchor, with 2.2w's `#retired-<release>` suffix dropped; no entry gives no link, never the Code's own URL, an index page that does not hold the canon. Other canon-law removals follow 2.4a's rules. rm-1948's `passage_id` is `uuid5(Code, "can/295")`, so the retired row's anchor is the map's key.
  - Web. `passageTextLabels()` in `lib/search-stream.ts` is the one decoder; the stream calls it, and so do the card, the bookmark and the reader for saved and reader payloads, which skip the stream. `TextLabels` in `components/common/PassageFacts.tsx` renders the lines: in the facts block right after the translation, before the notes and the credit; in the reader as a muted block under the passage text, before its note. The Latin opens in a new tab in `text-brand-accent`; without a URL the sentence shows unlinked. The Code has no document translation, so no "Translation:" line sits beside the unofficial-English one; its document note (the canons not shown) follows it.
  - Tests: `tests/test_passage_text_labels.py` (reader, restore, bookmarks and both tombstone paths against Postgres migrated through 0043), `test_document_facts.py`, `test_corpus_schema.py`; web `search-stream.test.ts`, `ChunkCard.test.tsx`, `BookmarkCard.test.tsx`, `Passage.test.tsx`. The 2.4b and 2.4d no-field snapshots are unchanged. Screenshots: `docs/screenshots/2026-11-12-2.4f/`.
- **Needs Carter:** Answered 12 Nov 2026: "Text from a scanned edition", as recommended. Found by this item, open: 5.6c plans its own scanned-text label with the Internet Archive ID (NEEDS-CARTER, 5.6c).
- **Out of scope:** OCR quality itself (1.2f). Which canons get unofficial English (1.5b, R2).

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
    | A | Novatian's Epistle XXX inside "The Epistles of Cyprian." (C-02, added 9 Oct 2026) | `aaf1a0e4` | the 5 passages `epistle-xxx/p1` to `/p5` today; Epistle XXIX and any other sender only if the research step below excludes them |

  - User rows touching each target are in the table in the Cross-cutting design section. In total 54 retrievals, 6 guest rows, 0 bookmarks, 0 labels, 0 reading progress rows and 0 feedback rows for rules A to C; 3 retrievals for the rule G heuristic.
  - Today's writer deletes what a build no longer emits, which cascades (`reader_writer.py:36-81`); `clear_collection` deletes a whole collection (`:16-33`). 2.2w removes both.
  - CCEL `<description>` blurbs sit in the ThML header of the vendored files (for example `datapipeline/sources/medieval/consolation-of-philosophy.xml:11`). The adapters iterate `div1` elements in the body (`datapipeline/ingest/church_fathers.py:59`, `ingest/medieval.py:45`), and a live search for the four medieval blurbs' opening sentences found 0 passages. Checked for the 4 medieval files only; the Fathers files were not checked passage by passage.
- **Changes:**
  - Removal registry (2.1's file, D4): entries in 2.1's scopes, never by position and never as an anchor range. A whole-document target is one `document` entry. A partial target (Treatises I and III in `5d75dc92`, Book VIII before its canons, the Sectional Confession, the Pfaff fragments) is one `passage` entry per live anchor. The long recension is 1.8c's `span` entries, which this PR checks rather than adds again. Each entry's fields are 2.1's: `reason`, `detail`, `tombstone` and `church_act`. The reason comes from 2.1's list only (D11); the distinctions an earlier draft coded as separate reasons go in `detail`:
    - `rule-a`:
      - Origen (limit 1, condemned by name: Constantinople II, 553, anathema 11) and Novatian (limit 1: Roman synod under Pope Cornelius, 251, as reported by Eusebius, Church History 6.43).
      - Tertullian's 7 works (limit 3, outside communion or not datable; Benedict XVI, general audience of 30 May 2007, for the break) and Tatian (Irenaeus, Against Heresies 1.28.1; Eusebius, Church History 4.28-29).
      - Arnobius (written before baptism; Jerome, Chronicle) and Alexander of Lycopolis (not a Christian; van Oort 2012).
      - Novatian's Epistle XXX in Cyprian's Epistles (C-02; Decision log "Letters in Cyprian's Epistles (C-02)"): limit 1, as for his other works. `detail` cites Cyprian's Epistle LI to Antonianus (Ep. 55 in the Oxford numbering), which says Novatian wrote it, and the Roman synod of 251 for the condemnation.
    - `rule-b`: the Apostolic Constitutions (Council in Trullo, canon 2, confirmed by Nicaea II, canon 1), the six forged Ignatius letters and the long Ignatian recension (majority of standard scholarship), and the Sectional Confession (Caspari 1879, Lietzmann 1904).
    - `rule-c`: the Pfaff fragments (Harnack 1900) and the medieval Latin Ignatius letters (CPG 1028).
    - `rule-g-editorial`: the rule G list after 1.8a to 1.8c.
    - The tombstone's rule letter (A, B, C, G) is derived from the reason by 2.2w, not stored here.
  - Research step for Cyprian's correspondents (C-02), before code, by R1's method (Quasten's Patrology vol. II and the Church-act search). Settle whether Epistle XXIX (Oxford Ep. xxxvi), which some editors give to Novatian, is his. Check each other sender of a letter in the collection under rule A: Cornelius, the Roman clergy, the confessors (Moyses, Maximus and others), Caldonius, Celerinus, Lucian, Firmilian and the martyrs in the mines. Record each result in the shape of `rule_a_R1.json`. A letter whose sender rule A excludes gets `rule-a` passage entries for its anchors. Carter approves the outcome (NEEDS-CARTER section B, 3.1).
  - Tombstone drafts, one sentence each, for Carter to approve. For Origen, "Removed because the Second Council of Constantinople (553) condemned Origen by name, and TheoCorpus excludes authors the Church has condemned by name." For rule G, "Removed because this text was written by a modern editor, not the author."
  - Adapters (`datapipeline/ingest/church_fathers.py`, `medieval.py`, `thml_doc.py`): skip every unit the removal registry lists. The adapter asks the registry; no author or title string matching in adapter code.
  - No writer change. 2.2w's stage step turns each registry entry into a staged tombstone, with its snapshot (`collection, title, author, reference, chapter_label`) taken from the live row, and its apply retires the rows. An ID that leaves the build with no registry entry and no redirect stops the stage (D4).
  - A regression check keeps ThML `<description>` text out of content. New `datapipeline/tests/test_thml_description_excluded.py` builds each ThML adapter's documents from fixtures containing a `<description>` and asserts no passage contains it. For vendored sources, the 0.1a coverage checks gain a rule that fails when any passage contains 40 or more consecutive characters of a file's `<description>`.
  - The release report (0.1c, staged mode in 2.2w) lists every retired ID with its registry entry and tombstone, and every user row pointing at one.
- **Acceptance checks:**
  - `test_no_novatian_passage_stays_active`: no active passage is credited to Novatian or sits in a work by him, Epistle XXX's five passages included; 0.1d's `attribution.letter_sender` entry for Epistle XXX clears.
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

  - 4.2's targeted checks for each removed author return no passage from them after cutover.
  - PR description must include the registry diff, the per-target counts, the tombstone wordings, and the R1 outcome for the two Tertullian works.
- **Production safety:** Merging changes only the registry and adapters; the publish lock (0.4) keeps them away from production until the Phase 4 apply. At the apply, removed rows are retired and stay in the tables, so every user foreign key survives, and 2.4a returns tombstones for them. 2.2w's rollback un-retires them with nothing lost. If this merged before 2.4a and 2.4b were deployed, nothing would happen, because nothing is applied until P4; the 4.1b checklist blocks cutover until both are live.
- **Needs Carter:** R1's result for To His Wife and On the Apparel of Women. Approval of each tombstone sentence. The display policy for removed text (2.4a). The rule G final list after 1.8a to 1.8c.
- **Out of scope:** Label changes for works that stay (3.2). The split of the Shorter and Longer documents and the Ignatius greetings (1.8c). Hard-deleting retired rows (post-cutover ops). The About page section on excluded authors (5.7).

---

### 3.2. Labels, certainty and notes for works that stay

- **Type:** PR (registry values; written by 2.2w; displayed by 2.4b). Takes effect at the Phase 4 apply.
- **Depends on:** 2.1, 2.2a, 2.3 (the registry fields), 2.2w (the writer), 2.4a and 2.4b (to be visible). R1 (rule A) and R4 (book contents) for the Refutation of All Heresies.
- **Goal:** Doubtful works say so. A user reading the Hortatory Address sees "Pseudo-Justin"; a user reading the Twelve Topics sees it is not Gregory's; a user reading the Didache sees it is anonymous; the Summa Supplement says it was compiled after Aquinas died.
- **Current state:**
  - Every document has only `author` for attribution; no certainty or note exists anywhere. Authors live: Justin Martyr for the Hortatory Address (`3f1d7ed1`, 41 passages), On the Sole Government of God (`dd54c7cc`, 6), The Discourse to the Greeks (`abd0e330`, 5), On the Resurrection, Fragments (`24b54b57`, 12); "Gregory Thaumaturgus." for Dubious or Spurious Writings (`44fd52c3`, 80); Barnabas (`1d83b302`); Mathetes for Diognetus (`abf69de0`, 13); "Hippolytus." for the Appendix of dubious pieces (`a2b36c64`, 57); Ignatius for The Martyrdom of Ignatius (`841b4e0a`, 8); Victorinus (`e847b8bb`, 39); Methodius for Oration on the Palms and the homily fragments (`5f210d1e`); Pamphilus (Exposition of the Acts, today positions 2 to 5).
  - In ANF volumes, one document holds several works, and chapter keys repeat across works ("Section I" occurs at positions 0 and 43 of `44fd52c3`). Work membership is therefore recorded per passage as `work_key`, in the work model 2.1 defines and 2.2a stores (`chunks.work_key`, `document_works`; D6, D11).
  - Also found by the 6 Oct reviews (C-15, C-02):
    - Martyrdoms credited to their martyrs (Opus A-008, Sol B-004). The Martyrdom of Polycarp (`f8faac83`, 22 passages) is credited to Polycarp, though it is the Church of Smyrna's letter and names its writer, Evarestus, in chapter XX; the Martyrdom of Justin Martyr (`cf8278dd`, 5 passages) is credited to Justin, though the vendored edition's notice says its author is unknown. D10's Martyrdom of Ignatius exception does not cover them.
    - Fragments framed by another writer (Opus A-009, Opus-2 B-013). 16 fragment documents (448 passages) put the quoting writer's words under the fragment's author: Papias's open with Eusebius's account, Justin's "Other Fragments" with "The most admirable Justin rightly declared…", Dionysius's "Extant Fragments" with Eusebius's narrative (17 of 79), the Stromata's "Fragments of Clemens" with a later writer's reports.
    - Letters by others in Cyprian's Epistles. 1.8c credits each to its sender as a work; this item approves the wording.
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
  | Martyrdom of Polycarp (C-15) | Church of Smyrna | genuine | "A letter of the Church of Smyrna on Polycarp's death; its writer, Evarestus, is named in chapter XX." | |
  | Martyrdom of Justin (C-15) | Anonymous | anonymous | "An account of the trial and death of Justin and his companions; its author is unknown." | |
  | Fragment collections framed by a quoting writer (C-15; 16 documents, each named in the PR) | unchanged | unchanged | work note naming where the fragments were preserved, for example "Preserved in Eusebius, Church History" (decided by Carter on 9 Oct 2026; per-span credit for the quoting writer is later) | |
  | Letters by others in Cyprian's Epistles (C-02; works set by 1.8c) | the sender, for example "Firmilian of Caesarea" | genuine | title naming sender and recipient, for example "Firmilian of Caesarea, to Cyprian" | |
  | On Loving God | Bernard of Clairvaux | genuine | translation: "Translated by William Harman van Allen (1909)" (R5; the full credit line, with "Sourced via CCEL.org", is in the Decision log row "On Loving God translation") | |

  Wording in the notes follows the research memo; Carter approves the final sentences. Works with CPG numbers take them from the research memo's confirmed list only.
  - Authenticity judgments copied from editorial text before rule G deletes it (plan rule G) go into `attribution_note`, except where this plan overrides them.
  - No code change beyond registry values and their validation test.
- **Acceptance checks:**
  - 0.1d's `attribution.narrative_of_author_death` entries clear: no work titled "Martyrdom", "Passion" or "Acts of" is credited to its martyr without a note, D10's Martyrdom of Ignatius excepted.
  - Registry validation test: every entry in the table exists, has a `certainty` (except the Martyrdom of Ignatius, which keeps its label and sets none), and every `Pseudo-` author has `certainty = pseudonymous`. The Apostolic Canons entry's author is not "Anonymous".
  - The staged release report (2.2w, with 2.3's facts section) shows exactly the listed documents and works changing.
  - After the Phase 4 apply, `GET /v1/documents/3f1d7ed1-...` returns `author: "Pseudo-Justin"` and `facts.certainty: "pseudonymous"`, and a search for "true religion of the Greeks" shows the Pseudo-Justin label on the card (manual check, screenshot in the 4.1b log).
  - PR description must list each label with its source line in the research memo, and the R1 and R4 outcomes for the Refutation.
- **Production safety:** Values only. Nothing changes before the Phase 4 apply. At the apply, 2.2w writes the new `author` and facts into Postgres and the Qdrant payload in the same publish, so cards, the reader and `/sources` agree from the first second. The `(collection, title, translation, author)` unique key has no collision because no two documents share the new labels with the same title.
- **Needs Carter:** Approval of every label and note sentence, including the Apostolic Canons wording.
- **Out of scope:** Author cleanup of malformed names such as "Tertullian: Part Fourth." and trailing periods (1.10a, 1.8c). Moving Boethius to Church Fathers (P5). The Catena Aurea's per-quotation attribution (P5; it uses 2.2a's `passage_author`).

---

### 3.3. Non-English passages: replace with English or retire

- **Type:** PR (registry entries). Takes effect at the Phase 4 apply.
- **Depends on:** 2.1 (the removal registry), 2.2a, 2.2w (retirement and tombstones).
- **Goal:** No passage in search or the reader is in a language other than English (rule E as revised by Carter on 29 Oct 2026). Where a cleared English translation exists, it replaces the passage; otherwise the passage is retired with a tombstone and comes back when one is found.
- **Current state:**
  - Plan counts: Clement, Stromata III, Latin, 33; Clement, The Instructor II.10, Latin, 4; Lactantius, Divine Institutes VI and On the Workmanship of God, Latin, 5; Ubi Lutetiam (Pius VI), Italian, 17. Total 59.
  - A Latin-stopword heuristic on 29 Sep found 33 in the Stromata (`3a68ef3f`), 5 in The Instructor (`96584290`), 3 in the Divine Institutes (`9e03c96d`), 1 in On the Workmanship of God (`f913305f`), and all 17 of Ubi Lutetiam (`ba74d920`). The small differences from the plan mean the final list must be fixed by anchor in the registry, checked by eye.
  - User rows: 1 retrieval points at one of these passages (Divine Institutes); 0 bookmarks, labels or guest rows.
  - Canon law's non-English canons are handled by 1.5b under the same rule.
- **Changes:**
  - Research step inside this item, before code. For each of the four works, record whether a cleared English translation of the missing sections exists (0.2's rights inventory holds the answer). TheoCorpus makes no translations of its own.
  - Where one exists, the adapter substitutes it (a separate adapter change under 1.8a or 1.3a) and the passage keeps its ID with `text_replaced` set.
  - Otherwise, a removal-registry entry per anchor, reason `translation-in-preparation`, with the tombstone "No public-domain English translation is available." Ubi Lutetiam is wholly Italian, so it is a `document`-scope entry. Each work that loses passages but stays gets a note in its `notes` (the document's, or the `document_works` row's for a work inside a container; 2.2a, shown in the reader's document overview, 2.4b): "Some passages are omitted: the translators left them in Latin and no public-domain English translation exists."
  - No early live apply (D7).
- **Acceptance checks:**
  - Registry test: exactly the approved anchors carry removal entries with this reason and tombstone, and each work that keeps passages carries the omission note.
  - A build check, `language.english_only`, run in the release report: no staged passage has a non-English `language`, and the Latin-stopword heuristic finds no run of 5 or more words in any staged passage outside a list of approved short quotations (a Latin phrase inside English prose).
  - After the Phase 4 apply: each retired ID returns its tombstone from `/v1/documents/.../reader`, and the one saved retrieval restores as a tombstone.
  - PR description must include the final anchor list per work with the first 80 characters of each passage, and the translation research result.
- **Production safety:** Values only; nothing changes before the Phase 4 apply. At the apply, the 59 passages leave search and the reader. 2.2w's rollback restores them.
- **Needs Carter:** Approval of the anchor list and the tombstone wording.
- **Out of scope:** Writing or commissioning translations. Short Latin phrases inside English prose (a quoted "Credo", a legal term), which are English text.

---

### 3.4. Rejected-voice ranges

- **Type:** PR (passage-registry values and their validation). Takes effect at the Phase 4 apply.
- **Depends on:** 2.1 (the `voice` field and the `voice` and `unit_label` registry overrides), 2.2a, 2.2w, 1.3a (the Syllabus and Exsurge Domine end at their last proposition), 1.8a and 1.8c (the Octavius and the Acts of Archelaus after the editorial strip), 1.2a, 1.2c and 1.2e (which list the anchors of condemned council texts in whatever text the Phase 4 build carries). Visible only with 2.4d.
- **Goal:** Every passage that states a position its document rejects carries `voice = "rejected"` and a label saying whose position it is and who rejects it, so the rerankers, the explanation model, the card and the reader never present it as the document's teaching, while it stays findable (Decision log "Rejected voices (C-01)", decided by Carter on 9 Oct 2026).
- **Current state (C-01; Opus A-002, Opus-2 B-007, Sol A-001, A-006, A-011):**
  - Lists of condemned statements, each passage one bare proposition, condemned once for the whole list:
    - Exsurge Domine (Leo X, 1520) §1 to §41, Luther's propositions, under "Pope Leo X — Exsurge Domine, §N". 6 saved retrieval rows sit on them.
    - The Syllabus of Errors (Pius IX, 1864) §1 to §80.
    - The Council of Constance, about 120 passages in Tanner's text: Wyclif's 45 articles and Hus's 30. 1.2e replaces this text with Schroeder's or retires it at Phase 4 (D9), so the ranges follow whatever the build carries.
  - An opponent speaking inside a larger work, answered in later passages:
    - Ephesus: Nestorius's second letter to Cyril, 5 build passages, filed under the council, which read and condemned it. Cyril's letters in the same document are approved texts and are not labelled.
    - Minucius Felix, the Octavius, chapters V to XIII (11 passages): the pagan Caecilius's case against Christianity, answered from chapter XVI. Today only the editor's "Argument" line names him, and 1.8a removes it.
    - Hegemonius, the Acts of Archelaus: Mani's speeches in the 5 passages that do not name him (V/p2, XIII/p1 to /p3, XIV/p2) and Turbo's exposition of his teaching (about 10 passages; Opus-2 B-007 places it in chapters 7 to 11 and 13 while Sol A-011 reads chapter XIII as Mani's own speech, so this item fixes the exact anchors from the source). Passages that say "Manes said" mark themselves.
  - Not labelled, as the reviewers judged them not misleading: dialogues whose speakers the text names (Trypho in Justin, Boso in Cur Deus Homo, Philosophy in Boethius) and authors quoting opponents inside their own argument (Augustine quoting Seneca). Firmilian's letter in Cyprian's Epistles is a credit question, settled by 1.8c, not a rejected voice.
- **Changes:**
  - A tracked list, `datapipeline/registry/rejected_voice_ranges.json`: per range, the document, first and last anchor, the label pattern and the basis (the condemning act or the work's own reply), with no passage text.
  - Passage-registry rows (2.1) for every passage in a range: `voice: "rejected"` and a `unit_label` override, in these forms (approved by Carter on 14 Nov 2026, Decision log "Rejected-voice ranges and labels (3.4)"):
    - Exsurge Domine: "Condemned proposition N of Martin Luther (condemned by Leo X, Exsurge Domine)".
    - Syllabus: "Condemned proposition N (condemned by Pius IX, Syllabus of Errors)".
    - Constance: "Condemned articles of John Wyclif (Council of Constance)" or "Condemned articles of Jan Hus (Council of Constance)", on the anchors 1.2e lists; none if the council is retired at Phase 4.
    - Ephesus: "Letter of Nestorius, condemned by the Council of Ephesus".
    - Octavius: "Caecilius, pagan objection; answered by Octavius".
    - Acts of Archelaus: "Mani's teaching, refuted by Archelaus".
  - Fallback: if 2.4d has not deployed when 4.1b step 1 freezes the Phase 4 build, the freeze PR also sets `searchable = false` on these rows (Decision log).
- **Acceptance checks:**
  - Registry test `roles.rejected_voice`: every passage in each listed range carries `voice = "rejected"` and a label matching its pattern, no passage outside the ranges carries the role except Summa objections (set by 1.7), and every range resolves to anchors in the build.
  - The PR lists each range with its passage count and saved rows.
  - After the Phase 4 apply (4.2's targeted questions, on staging first): "in every good work the just man sins" returns Exsurge Domine §31 with its label, and the explanation says Leo X condemned it; a question on the Octavius's arguments against providence returns Caecilius's speech labelled as a pagan objection.
- **Production safety:** Values only; nothing changes before the Phase 4 apply. At the apply, 2.2w writes `voice` and the labels into Postgres and the Qdrant payload together, and 2.4d shows them. Rollback restores the previous labels with everything else.
- **As built (14 Nov 2026):**
  - Ranges. `datapipeline/registry/rejected_voice_ranges.json`, 15 ranges, each with `collection`, `document_id`, `title`, `first_anchor`, `last_anchor`, `label` and `basis`, sorted by collection and document, a document's ranges in reading order. A label may hold `{n}`, the number that ends the passage's unit anchor (`exsurge-domine/10` → 10). `registry/rejected_voice.py` loads, validates and expands them.
  - Rows. `scripts/rejected_voice_rows.py` builds each listed collection, expands every range and writes `voice` and `unit_label` onto the passage-registry rows; it refuses a range that does not resolve, a passage with no row, and a row of a listed document with the role outside every range. Rerun it after a merge that changes these documents' anchors or rows.
  - The check. `roles.rejected_voice:<collection>` in `checks/content.py`, run on every collection with the registry's overrides applied (the stage's view): every range resolves, every passage in a range carries the role and its label, and no other passage carries the role but a Summa objection. Unit tests in `tests/test_rejected_voice.py`; on the build, `tests/source_checks/test_rejected_voice_sources.py` pins each range's passage count.
  - The list, on the master build of 14 Nov 2026, with saved rows from the 31 Oct snapshot:

    | Document | Ranges | Passages | Saved rows |
    |---|---|---|---|
    | Exsurge Domine | `exsurge-domine/1` to `/41` | 41 | 6 retrievals |
    | Syllabus of Errors | `/1`–`/14`, `/15`–`/18`, `/19`–`/74`, `/75`–`/76`, `/77`–`/80` | 80 | 0 |
    | Council of Constance | `session-8/wyclif-articles` to `/from-p35`; `session-15/hus-articles` to `/from-p18` | 4 | 0 |
    | Council of Ephesus | `nestorius-second-letter` to `/from-p6-2` | 4 | 0 |
    | The Octavius | `iv.iii.v` to `iv.iii.xiii` (chapters V–XIII) | 10 | 0 |
    | The Acts of Archelaus | `vii.iii.v`; `vii.iii.vi/from-p5` to `vii.iii.x`; `vii.iii.xii` to `/from-p1-2`; `vii.iii.xiii/from-p1-2`; `vii.iii.xlvi/from-p1-3` | 11 | 0 |

  - Fewer passages than the "about 270" estimate: 1.2e-5 packed Constance's 75 articles into four passages, one article to a paragraph (Tanner's text had about 120), and Chrystal's Nestorius letter is 4 pieces. So Constance's label carries no article number; each article's number is printed in the text.
  - The Syllabus's three N.B. notes and section IV's heading (`text-2`, `text-4`, `text-8`, `text-9`) are Pius IX's own words and stand between the ranges, which is why the Syllabus has five.
  - The Acts of Archelaus, read on the build. Mani's letter (chapter 5, after one sentence of narration); Turbo's account of his teaching, from the narration that introduces it (chapter 6, part 2) to the end of chapter 11; Mani's opening speech (chapter 13, both parts); and two pieces that continue a speech of his without naming him, chapter 14 part 2 and chapter 47 part 3 (the second found by this reading: the reviewers read the passages as cut before 1.10c). Chapter 13 is Mani's speech, as Sol A-011 read it. Passages that say "Manes said" or "Manes replied" mark themselves and are not labelled, nor is the Fragment of the same disputation, or Diodorus's letter (chapter 40), which reports Mani's claims as "he told us".
  - The Octavius: Caecilius's case is chapters V to XIII; chapter XIV opens "Thus far Caecilius", and his short protest in chapter XV names him.
  - Not labelled, for the council's own voice: Vienne's Ad nostrum (`council-of-vienne/series-1/canon/6`, 1.2e-2), whose eight Beghard errors are quoted inside the council's condemnation, and Constance's tyrannicide sentence (`council-of-constance/session-15/tyrannicide`, 1.2e-5), which quotes the proposition inside the council's sentence.
  - Agreement with earlier items: Exsurge Domine's 41 rows (1.3d-6) and Nestorius's 4 (1.2c) already carried the role; they gain the label and keep their notes. No Summa row is touched.
  - `registry.validate()` is empty.
- **Needs Carter:** Answered 14 Nov 2026: the ranges and each label text, approved as drafted (Decision log "Rejected-voice ranges and labels (3.4)").
- **Out of scope:** Summa objections (1.7 sets them). Removing any of these texts. Speakers the text already names. Firmilian's letter (1.8c).
