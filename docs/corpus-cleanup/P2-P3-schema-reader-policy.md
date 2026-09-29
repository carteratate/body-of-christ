# P2 and P3 work specifications for schema, reader and content policy

29 September 2026. Source of truth is `docs/2026-09-28-corpus-cleanup-plan.md`; its inclusion rules and Decision log are settled and are not reopened here. Code references are to `master` at `5475c49` in `/Users/cartertate/repos/body-of-christ`. Live measurements are read-only SELECTs against Supabase project `hvmgffvimqgiejmxwhwq` on 29 Sep 2026.

## Overview and recommended order

1. **2.4c** About page factual fix. Independent, ships first because the page is false today.
2. **2.2a** Migrations 0039 (release, attribution, tombstones, redirects, works) and 0040 (release-scoped passage keys). Nothing reads them yet.
3. **2.2c** Decision that the `search_vector` needs no DDL rebuild. Close it alongside 2.2a.
4. **2.2b** API reads Qdrant through a configurable name, then an alias; search paths honor `searchable` and the live release.
5. **2.4a** API payloads carry document facts, tombstones and redirects; reader, sources, history and bookmarks honor the live release.
6. **2.4b** Web cards, reader, bookmarks and history render the new fields, the source credit, tombstones and redirects. Must be live before any tombstone exists.
7. **2.3** Metadata backfill from the work registry (2.1). Can be applied to live rows early, with Carter's approval.
8. **3.3** Non-English passages leave search. The only P3 item that can take effect before the P4 republish.
9. **3.2** Labels, certainty and notes in the registry. Visible after 2.3's early apply or at P4.
10. **3.1** Removals in the registry and adapters, with retire-not-delete writing. Blocked by R1. Takes effect only at P4 cutover.

Every PR here deploys against today's schema and data. No item deletes a row. User rows that point at removed passages keep working because removed passages are retired, not deleted.

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

The datapipeline deletes rows in two places, and both cascade. `datapipeline/writers/reader_writer.py:16-33` (`clear_collection`) deletes a whole collection. `reader_writer.py:36-59` (`prune_missing_chunks`) and `:62-81` (`prune_missing_documents`) delete rows the new build no longer emits. A removal published through today's writer would silently delete every saved retrieval, bookmark, label and guest result that points at a removed passage, and every restored search that contained one would come back short with `restore_status = "results_unavailable"` (`services/api/app/routes/search.py:380-385`).

### The rule this plan adopts

**Removed passages and documents are retired, never deleted, while any user row points at them.** A retired row stays in `chunks` or `documents` with `retired_release` set. Search, the reader and `/sources` hide it once that release is live. A tombstone row records why it left and what to show instead. Cascades therefore never fire, and every user row keeps a valid foreign key.

How each user surface behaves after the P4 cutover:

| Surface | Passage renumbered or split (a redirect exists) | Passage removed (a tombstone exists) |
|---|---|---|
| Saved search restore | 4.1a remaps `retrievals.chunk_id` to the new id; until then 2.4a follows the redirect | Card shows the tombstone in place of the passage; `restore_status` stays `complete` |
| Bookmarks | 4.1a remaps, with its merge policy for `(user_id, chunk_id)` | Bookmark card shows the tombstone; the note is kept |
| Retrieval labels | 4.1a remaps, merge policy for `(user_id, chunk_id, search_id)` | Kept as is; labels are evaluation data about what was shown |
| Guest results and claim | 4.1a remaps, merge policy for `(guest_trial_id, chunk_id)` | Claim still copies the row; the restored card shows the tombstone |
| Reading progress | Anchor and chapter redirects rewrite `anchor` and `chapter_key` in 4.1a | Whole document removed: progress row kept, the "continue reading" entry shows the tombstone and drops out of lists |
| Reader deep link | API returns the redirect; web replaces the URL | API returns 410 with the tombstone; web shows a removal page |

Retired rows cost storage. After the rollback window that Carter sets in 4.1b, retired passages that no user row references can be hard-deleted in an ops step, because deleting them cascades nothing. Tombstones are never deleted.

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

No reading progress or product feedback rows point at documents to be removed. The plan recorded 50 retrievals on 28 Sep; the count has grown to 54 in one day, so 4.1b must re-measure at cutover.

The query that produced this table is kept in 3.1's Acceptance checks so it can be rerun at cutover.

---

### 2.2a. Additive migrations for release, attribution, tombstones, redirects and works

- **Type:** PR
- **Depends on:** none to merge. 2.1 (work registry) defines the values that later fill these columns. Applying to the live database needs Carter.
- **Goal:** Give the database the places to hold what the cleanup decides, without changing anything a user sees. After this, a document can carry its genre, issuer, date, certainty label, notes and source credit; a passage can be marked not searchable and tagged with its language and work; a release can be staged and switched live in one step; removed passages and documents leave a tombstone; moved ones leave a redirect.
- **Current state:**
  - `documents` columns live: `id, collection, title, author, year, metadata, created_at, translation (NOT NULL DEFAULT ''), chunk_count`. `chunks` columns live: `id, document_id, content, position, reference, content_embedding, search_vector, annotation, annotation_embedding, created_at, metadata, anchor, chapter_key, chapter_label, unit_label, annotation_vector` (information_schema, 29 Sep).
  - Unique keys on `chunks`: `chunks_document_id_position_key UNIQUE (document_id, position)` and partial `chunks_document_anchor_uniq (document_id, anchor) WHERE anchor IS NOT NULL` (pg_indexes, 29 Sep). Both would block a second release of a document from being staged beside the live one.
  - Passage ids are deterministic from the anchor (`reader_writer.py:47`, `passage_id(doc.id, p.anchor)`) and the writer upserts `ON CONFLICT (id) DO UPDATE` (`reader_writer.py:121`). An unchanged anchor with changed text would therefore be rewritten in place and become visible at once, which defeats staging.
  - `document_type` lives only in `documents.metadata` (16 documents). Metadata keys in use: `url` 211, `pope` 175, `source_file` 135, `testament` 73, `council_number` 20, `year` 16, `council` 16, `document_type` 16, `source_url` 6, `source` 2.
  - `year` is NULL for all 128 Fathers documents, the Summa and all 73 Bible books; `translation` is '' everywhere except the 73 Bible books (`WEB-C`); `author` is NULL for all 36 council documents and all 73 Bible books.
  - The API already tolerates a missing column for 0037 (`services/api/app/routes/documents.py:123-132`, `routes/sources.py:73-76`).
  - The Supabase migration ledger does not list every committed migration (for example 0015, 0016, 0019, 0023, 0026, 0033 are absent from `list_migrations`, though their objects exist). Unverified how they were applied; note it when applying 0039.
  - The parked branch `feat/roman-curia-collection` also numbers a migration 0039. It must renumber when it lands in P5.
- **Changes:**
  - New file `supabase/migrations/0039_corpus_release_and_attribution.sql`. Every statement is additive. `SET LOCAL lock_timeout = '2s'` at the top, as in 0037, so a waiting `ALTER TABLE` fails rather than queues searches. Adding a column with a constant default is a catalog-only change on Postgres 11 and later, so neither table is rewritten.

    ```sql
    SET LOCAL lock_timeout = '2s';

    -- Releases. Exactly one is live. Release 1 is today's corpus.
    CREATE TABLE corpus_releases (
        id           integer PRIMARY KEY CHECK (id > 0),
        label        text NOT NULL,
        state        text NOT NULL CHECK (state IN ('staging', 'live', 'retired')),
        created_at   timestamptz NOT NULL DEFAULT now(),
        published_at timestamptz,
        notes        text
    );
    CREATE UNIQUE INDEX corpus_releases_one_live ON corpus_releases ((true)) WHERE state = 'live';
    INSERT INTO corpus_releases (id, label, state, published_at)
    VALUES (1, 'Corpus before the 2026 cleanup', 'live', now());

    CREATE FUNCTION live_corpus_release() RETURNS integer
    LANGUAGE sql STABLE SECURITY INVOKER SET search_path = public
    AS $$ SELECT id FROM corpus_releases WHERE state = 'live' $$;

    -- Documents: visibility window plus the fields the plan asks for.
    ALTER TABLE documents
        ADD COLUMN introduced_release integer NOT NULL DEFAULT 1 CHECK (introduced_release > 0),
        ADD COLUMN retired_release    integer CHECK (retired_release IS NULL OR retired_release > introduced_release),
        ADD COLUMN genre              text,  -- 'encyclical', 'apostolic exhortation', 'treatise', 'letter', 'church order', 'commentary', 'manual', ...
        ADD COLUMN issuer             text,  -- 'Pope Leo XIII', 'Second Vatican Council'
        ADD COLUMN date_label         text,  -- display form: 'c. 375-380', '1077-78', '1265-1274'
        ADD COLUMN certainty          text CHECK (certainty IN ('genuine', 'disputed', 'pseudonymous', 'anonymous')),
        ADD COLUMN attribution_note   text,  -- 'Heimgartner (2001) assigns it to Athenagoras.'
        ADD COLUMN note               text,  -- general reader note, e.g. the Apostolic Canons note
        ADD COLUMN source_credit      text,  -- 'Text: Libreria Editrice Vaticana', 'Sourced via CCEL.org'
        ADD COLUMN clavis_ref         text;  -- 'CPG 1083'

    -- Passages: visibility window, search flag, language, work membership, note.
    ALTER TABLE chunks
        ADD COLUMN introduced_release integer NOT NULL DEFAULT 1 CHECK (introduced_release > 0),
        ADD COLUMN retired_release    integer CHECK (retired_release IS NULL OR retired_release > introduced_release),
        ADD COLUMN searchable         boolean NOT NULL DEFAULT true,
        ADD COLUMN language           text CHECK (language IS NULL OR language ~ '^[a-z]{2,3}$'),  -- NULL means English
        ADD COLUMN work_key           text,
        ADD COLUMN note               text;

    -- Works inside a document. ANF volumes hold several works per document
    -- ("Dubious or Spurious Writings." holds the Sectional Confession, the Twelve Topics
    -- and four homilies), and each carries its own attribution.
    CREATE TABLE document_works (
        document_id      uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        work_key         text NOT NULL CHECK (char_length(work_key) BETWEEN 1 AND 200),
        title            text NOT NULL,
        author           text,
        certainty        text CHECK (certainty IN ('genuine', 'disputed', 'pseudonymous', 'anonymous')),
        attribution_note text,
        note             text,
        date_label       text,
        year             integer,
        genre            text,
        clavis_ref       text,
        PRIMARY KEY (document_id, work_key)
    );

    -- Tombstones outlive the rows they describe, so no foreign keys.
    CREATE TABLE corpus_tombstones (
        entity          text NOT NULL CHECK (entity IN ('document', 'passage')),
        id              uuid NOT NULL,
        document_id     uuid NOT NULL,
        retired_release integer NOT NULL REFERENCES corpus_releases(id),
        rule            text NOT NULL CHECK (rule IN ('A', 'B', 'C', 'D', 'E', 'F', 'G', 'other')),
        reason_code     text NOT NULL,  -- see 3.1 for the vocabulary
        public_reason   text NOT NULL,  -- one plain sentence shown to users
        church_act      text,           -- 'Second Council of Constantinople (553), anathema 11'
        snapshot        jsonb NOT NULL, -- {collection, title, author, reference, chapter_label}
        created_at      timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (entity, id)
    );
    CREATE INDEX corpus_tombstones_document_idx ON corpus_tombstones (document_id);

    -- Redirects from old identities to new ones.
    CREATE TABLE corpus_redirects (
        id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        entity          text NOT NULL CHECK (entity IN ('document', 'passage', 'anchor')),
        old_id          uuid,          -- document or passage id; NULL for anchor rows
        old_document_id uuid NOT NULL,
        old_anchor      text,
        new_id          uuid,
        new_document_id uuid NOT NULL,
        new_anchor      text,
        release         integer NOT NULL REFERENCES corpus_releases(id),
        kind            text NOT NULL CHECK (kind IN ('renumbered', 'split', 'merged', 'moved', 'rewritten')),
        created_at      timestamptz NOT NULL DEFAULT now(),
        CHECK ((entity = 'anchor') = (old_id IS NULL))
    );
    CREATE UNIQUE INDEX corpus_redirects_passage_uniq ON corpus_redirects (old_id, release) WHERE entity IN ('document', 'passage');
    CREATE UNIQUE INDEX corpus_redirects_anchor_uniq  ON corpus_redirects (old_document_id, old_anchor, release) WHERE entity = 'anchor';
    ```

    A split passage redirects to its first new passage. A merge redirects every old passage to the merged one.
  - Same file, the outline must count only what the live release shows. Replace `refresh_document_outline` (0037) with `CREATE OR REPLACE FUNCTION` whose chunk subqueries add `AND c.introduced_release <= live_corpus_release() AND (c.retired_release IS NULL OR c.retired_release > live_corpus_release())`. Recreate the trigger `chunks_invalidate_outline_on_restructure` so its column list and `WHEN` clause also include `introduced_release` and `retired_release`.
  - Same file, one function for the cutover and its rollback:

    ```sql
    CREATE FUNCTION publish_corpus_release(p_release integer) RETURNS void
    LANGUAGE plpgsql SECURITY INVOKER SET search_path = public AS $$
    BEGIN
        UPDATE corpus_releases SET state = 'retired' WHERE state = 'live' AND id <> p_release;
        UPDATE corpus_releases SET state = 'live', published_at = now() WHERE id = p_release;
        IF NOT FOUND THEN RAISE EXCEPTION 'unknown release %', p_release; END IF;
        -- Every outline was built for the old release. Clearing the flag sends readers to
        -- the chunks-derived path (which also filters by the live release) until refreshed.
        UPDATE documents SET chunk_count = NULL WHERE chunk_count IS NOT NULL;
    END $$;
    ```

    The 4.1b runbook calls it, then refreshes every outline as 0038 does. Rollback is `publish_corpus_release(1)` followed by the same refresh.
  - Same file, grants as in 0037: `ENABLE ROW LEVEL SECURITY` with no policies on `corpus_releases`, `document_works`, `corpus_tombstones`, `corpus_redirects`, and `REVOKE ALL ... FROM anon, authenticated` on those tables and the two functions. FastAPI uses the service role.
  - New file `supabase/migrations/0040_release_scoped_passage_keys.sql`, separate so Carter can apply it later (it is needed only before 4.1a stages a release). It loosens two unique keys so two releases of one document can coexist. It drops constraints, which is not strictly additive, but nothing reads or writes through them (`reader_writer.py` upserts on `id`).

    ```sql
    SET LOCAL lock_timeout = '2s';
    CREATE UNIQUE INDEX chunks_document_position_release_uniq
        ON chunks (document_id, position, introduced_release);
    CREATE UNIQUE INDEX chunks_document_anchor_release_uniq
        ON chunks (document_id, anchor, introduced_release) WHERE anchor IS NOT NULL;
    ALTER TABLE chunks DROP CONSTRAINT chunks_document_id_position_key;
    DROP INDEX chunks_document_anchor_uniq;
    ```

    Each `CREATE UNIQUE INDEX` scans 54,568 rows under a lock that blocks writes, not reads. Measured size suggests seconds, not minutes (unverified; measure on a Supabase branch first).
  - Constraint this migration places on the P4 writer (owned by 4.1a, recorded here so it is not lost). A new-release passage may reuse an existing passage id only when its content, reference, labels and chapter fields are byte-identical to the live row; then the row simply stays (introduced 1, never retired). Any passage whose text changes gets a new id (for example `uuid5(document_id, anchor + '@r' + release)`), the old row is retired, and a `corpus_redirects` row of kind `rewritten` links them. Document ids are frozen (2.1), so document field changes are staged as values and applied inside the cutover transaction; 4.1a specifies that table.
  - No API or web change in this PR.
- **Acceptance checks:**
  - New test `services/api/tests/test_corpus_release_migration.py` using `tests/pg_cluster.py` (as `test_document_outline_migration.py` does). Apply 0004-era schema, 0037, 0038, then 0039. Assert:
    - `test_existing_rows_default_to_release_one`: every seeded chunk has `introduced_release = 1`, `retired_release IS NULL`, `searchable = true`; every document `introduced_release = 1`.
    - `test_one_live_release`: inserting a second `state = 'live'` row raises a unique violation.
    - `test_publish_switches_release_and_clears_outlines`: after `publish_corpus_release(2)` with release 2 staged, release 1 is `retired`, release 2 `live`, and every `chunk_count` is NULL.
    - `test_outline_counts_only_live_rows`: seed a document with 3 release-1 rows and 2 release-2 rows (0040 applied); `refresh_document_outline` gives 3 under release 1 and 2 after `publish_corpus_release(2)`.
    - `test_retiring_a_row_invalidates_the_outline`: `UPDATE chunks SET retired_release = 2` sets that document's `chunk_count` to NULL.
    - `test_redirect_anchor_rows_have_no_old_id`: the CHECK rejects an anchor redirect with `old_id`.
    - `test_new_tables_are_closed_to_client_roles`: `anon` and `authenticated` cannot SELECT from the four new tables.
  - `test_0040_allows_two_releases_per_position`: two rows with the same `(document_id, position)` and different `introduced_release` insert cleanly after 0040, and fail before it.
  - Existing suites unchanged: `python3 -m pytest tests/` in `services/api` and `python3 -m pytest` in `datapipeline`.
  - PR description must include the full SQL, the lock each statement takes, the rehearsal timings on a Supabase branch, and the sentence "This PR changes no API or web behavior."
- **Production safety:** Merging deploys nothing to the database; migrations in this repo are applied by hand. Once 0039 is applied, today's API ignores every new column and table, and the defaults make all 54,568 passages visible and searchable exactly as now. Today's datapipeline inserts rows without the new columns, which take their defaults. The replaced `refresh_document_outline` returns the same outline as before while release 1 is the only release. If 2.2b deploys before 0039 is applied, 2.2b's probe finds no columns and runs today's SQL. 0040 has no effect on any reader while only release 1 exists.
- **Needs Carter:** Approval to apply 0039 to the live database, then separately 0040. The final names for genre values (a closed vocabulary, used by 5.1a filters).
- **Out of scope:** Filling any column (2.3, 3.1 to 3.3). Changing foreign keys from CASCADE to RESTRICT (a possible later hardening, not additive). The collection merge and its CHECK constraint (5.1b). The P4 staging table for document values and the remap tool (4.1a). Hard-deleting retired rows (ops after 4.1b's rollback window).

---

### 2.2b. Qdrant alias, searchable flag and live-release filtering on the search path

- **Type:** PR, plus two ops steps
- **Depends on:** none to merge. Its filters take effect once 2.2a's 0039 is applied. The alias ops step needs Carter.
- **Goal:** Make the P4 cutover and its rollback a single alias switch, and make search skip anything marked not searchable or not in the live release. Users see no change today.
- **Current state:**
  - The Qdrant collection name is a constant, `QDRANT_COLLECTION = "chunks"` (`services/api/app/rag/qdrant_client.py:10`). It is used by vector search (`rag/steps/retrieve_vector.py:30-39`), the near-duplicate check that fetches embedding neighbors (`rag/dedup.py:199-205`, `client.retrieve(..., with_vectors=True)`) and the health check (`app/main.py:88-93`, `client.get_collection`).
  - Vector search filters only on `collection` (`retrieve_vector.py:33-35`).
  - Full-text search filters only on `collection` (`rag/steps/retrieve_fts.py:16-26`).
  - Summa stitching loads every passage of an article from Postgres with no visibility filter (`rag/steps/fetch_context.py:37-45`). Position backfill reads `chunks` by id (`rag/steps/fetch_positions.py:59-60`) and is skipped on the degraded path, so it cannot be the only guard.
  - Qdrant holds one collection, `chunks`, 54,568 points of 1,536 dimensions, no alias (plan, 28 Sep). Payload fields written by `datapipeline/writers/search_writer.py:39-62` are `collection, document_id, document_title, author, content, reference, anchor, chapter_label, chapter_key, unit_label`. No `searchable` field exists.
  - The datapipeline writes to the literal name `chunks` (`datapipeline/writers/qdrant.py:15`), and `qdrant_schema.recreate_chunks` deletes and recreates a collection called `chunks` (`datapipeline/qdrant_schema.py:19-30`). An alias cannot share a name with a collection, so the alias needs a new name.
  - Unverified whether the Qdrant server version accepts an alias name in `get_collection`. Search, retrieve and upsert accept aliases in current Qdrant documentation; the health call must be tested.
- **Changes:**
  - `services/api/app/config.py`: add `qdrant_read_collection: str = Field(default="chunks", validation_alias="QDRANT_READ_COLLECTION")`.
  - `rag/qdrant_client.py`: replace the constant with `def read_collection() -> str: return settings.qdrant_read_collection`. Update `retrieve_vector.py`, `dedup.py` and `main.py` to call it. Log the name at startup in `init_qdrant`.
  - `main.py` health check: resolve the name with `client.get_collection(read_collection())`; if the Qdrant test shows aliases are not accepted there, first map alias to collection with `client.get_collection_aliases` or `client.get_aliases`, then call `get_collection` on the target. Report `{"qdrant_read": <alias or name>, "qdrant_target": <collection>}` in `/health/search`.
  - New module `services/api/app/corpus_schema.py`, the one place that knows which 0039 objects exist:

    ```python
    @dataclass(frozen=True)
    class CorpusSchema:
        release: bool       # chunks.introduced_release and live_corpus_release() exist
        searchable: bool    # chunks.searchable exists
        attribution: bool   # documents.genre ... source_credit exist
        works: bool         # document_works exists
        tombstones: bool    # corpus_tombstones exists
        redirects: bool     # corpus_redirects exists

    async def current() -> CorpusSchema        # one information_schema query, cached 300 s
    async def live_release() -> int | None     # SELECT live_corpus_release(); cached 30 s; None when absent
    def invalidate() -> None                   # called on UndefinedColumnError / UndefinedTableError
    ```

    Probe once at startup (in the lifespan, after the pool) and lazily after the TTL. Any query that fails with `asyncpg.UndefinedColumnError` or `UndefinedTableError` calls `invalidate()` and retries once with the legacy SQL, as `routes/documents.py:123-132` does.
  - `retrieve_fts.py`: build `_SQL` from the schema. With `searchable`, add `AND c.searchable`. With `release`, add `AND c.introduced_release <= $4 AND (c.retired_release IS NULL OR c.retired_release > $4)` and `AND d.introduced_release <= $4 AND (d.retired_release IS NULL OR d.retired_release > $4)`, passing `live_release()`. Without either, the SQL is byte-identical to today's.
  - `retrieve_vector.py`: add `must_not=[FieldCondition(key="searchable", match=MatchValue(value=False))]` to the filter. Points without the field do not match `must_not`, so they stay searchable. Release separation for vectors comes from the alias; there is no release field in Qdrant.
  - `fetch_context.py` (stitch): add the release filter and `AND c.searchable` when present. A stitched part that is not searchable is dropped; when no part is left, the card has no attachment, which is today's behavior on a stitch failure.
  - `fetch_positions.py`: select `searchable` and the release columns when present and return which ids are hidden. `pipelines/runner.py` drops a vector candidate whose Postgres row is hidden. This is defense in depth for a Qdrant flag that disagrees with Postgres; on the degraded path it is skipped and the Qdrant filter alone applies.
  - Datapipeline, so P4 cannot delete the live collection by accident:
    - `datapipeline/config.py`: add `QDRANT_WRITE_COLLECTION` (default `chunks`). `writers/qdrant.py`, `stages/bm25_index.py` and `stages/embed.py` use it instead of the literal.
    - `qdrant_schema.recreate_chunks(client, name)`: refuse, with `SystemExit`, when `name` is the target of any alias. Create a `BOOL` payload index on `searchable` and keep the `collection` keyword index.
    - `search_writer.build_point`: add `"searchable": p.searchable` (default True on `Passage`, added to `datapipeline/model.py`).
  - Ops step 1 (Carter), after the PR is deployed with the default `chunks`: create the alias `chunks_live` pointing at `chunks` with `update_collection_aliases([CreateAliasOperation(create_alias=CreateAlias(collection_name="chunks", alias_name="chunks_live"))])`. Optionally create the `searchable` BOOL payload index on `chunks` (builds an index; deletes nothing).
  - Ops step 2 (Carter): set `QDRANT_READ_COLLECTION=chunks_live` in the API's Railway environment and restart. Check `/health/search` reports the alias and the `chunks` target.
- **Acceptance checks:**
  - `services/api/tests/test_retrieve.py`: `test_search_vector_excludes_only_explicit_unsearchable` asserts the filter has `must` on collection and `must_not` on `searchable == False`, and nothing else. `test_search_vector_uses_configured_read_collection` sets `QDRANT_READ_COLLECTION=chunks_live` and asserts `collection_name == "chunks_live"`.
  - New `tests/test_retrieve_fts_sql.py`: with a schema lacking 0039 the SQL equals today's text exactly; with 0039 it contains the searchable and release predicates and passes the live release as `$4`. A real-SQL variant on `pg_cluster` seeds one searchable and one `searchable = false` row matching the same term and asserts only the first returns; and one row with `retired_release = 1` under live release 1 is hidden.
  - `tests/test_stitch.py`: `test_unsearchable_parts_are_not_attached` and `test_retired_parts_are_not_attached`.
  - `tests/test_dedup.py`: `test_neighbor_fetch_reads_configured_collection`.
  - `tests/test_startup_wiring.py`: health reports alias and target.
  - Alias behavior against a real server: a test marked `qdrant_live` (skipped unless `QDRANT_TEST_URL` is set) runs against `docker run qdrant/qdrant` at the production server version, creates `chunks` with 3 points (one `searchable=false`, one without the field), creates alias `chunks_live`, and asserts `query_points`, `retrieve` and the health call all work through the alias, and that the `must_not` filter returns the two expected points. The PR records the server version tested.
  - `datapipeline/tests/test_qdrant_schema.py`: `recreate_chunks` refuses a name that an alias targets.
  - PR description must state the rollout order (merge, ops 1, ops 2), the rollback (unset `QDRANT_READ_COLLECTION`), and the result of the live-Qdrant test.
- **Production safety:** With the default `chunks`, the API reads exactly the collection it reads today. No live point has a `searchable` field, so the `must_not` clause matches nothing. Before 0039 is applied, `corpus_schema` reports nothing and the SQL is unchanged. After 0039 is applied, every row is release 1 and searchable, so the predicates keep every row. Creating an alias changes nothing for a client that does not use it. Switching the env var to the alias reads the same collection. At P4, 4.1b builds a new collection and repoints `chunks_live`; rollback repoints it to `chunks`. If 2.4a deploys before this item, 2.4a still works, because each item adds its own predicates through the same `corpus_schema` module; whichever merges second reuses it.
- **Needs Carter:** Ops step 1 (create the alias, optionally the payload index) and ops step 2 (Railway env var and restart). Both touch live infrastructure.
- **Out of scope:** Building the new collection, on-disk vectors and quantization (4.0, 4.1b). Genre and issuer payload fields (5.1a). The `facets` and `questions` collections, which the API does not read.

---

### 2.2c. search_vector rebuild

- **Type:** decision
- **Depends on:** 2.2a (for the searchable column the decision relies on)
- **Goal:** Decide whether the full-text index needs rebuilding for the cleanup, and record why, so nobody runs a 380 MB table rewrite without cause.
- **Current state:**
  - `chunks.search_vector` is `tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED` with a GIN index (`supabase/migrations/0004_v2_documents_chunks.sql:26-27, 40`). Postgres recomputes it on every insert and every update of `content`.
  - It is the only FTS column the API queries (`retrieve_fts.py:23-24`). `annotation_vector` (0019) is written by enrichment only.
  - Storage on 28 Sep: `search_vector` about 49 MB of 380 MB; TOAST 203 MB (plan).
  - The plan gives no rationale for 2.2c. The likely concerns are listed below with what already handles each.
- **Changes:** Recommended decision, no DDL:
  - Text fixes in P1 (joined paragraphs, stripped notes) reach FTS automatically, because the column is generated from `content`.
  - Non-English passages leave FTS through the `searchable` predicate (2.2b), not through the tsvector. Making the generated expression depend on `searchable` would need `DROP COLUMN` and `ADD COLUMN`, which rewrites the table under an exclusive lock.
  - Retired passages leave FTS through the release predicate (2.2b).
  - Space left by earlier rewrites is reclaimed by 4.0's `VACUUM FULL`, which also rebuilds the GIN index.
  - A post-cutover check is added to the 4.2 comparison: `SELECT count(*) FROM chunks WHERE search_vector IS DISTINCT FROM to_tsvector('english', content)` must return 0.
  - If Carter wants title or author weighting in FTS later, that is a retrieval follow-up with its own eval, not part of the cleanup.
- **Acceptance checks:** The decision is recorded in the plan's Decision log by Carter. The post-cutover query above is added to the 4.2 checklist.
- **Production safety:** Nothing changes.
- **Needs Carter:** Confirm the no-DDL decision, or name the missing concern this item was meant to cover.
- **Out of scope:** Changing the text search configuration, weighting, or `annotation_vector`.

---

### 2.3. Document metadata backfill

- **Type:** PR (registry fields, writer, backfill script), plus an optional ops apply
- **Depends on:** 2.1 (work registry with frozen ids), 0.2 (rights inventory, for source credits), 2.2a applied. 1.3 decides corrected papal genres; this item carries whatever 1.3 decides.
- **Goal:** Every document gets its real genre, issuer, date, translation and source credit, so cards and the reader can show them and 5.1a can filter on genre and issuer. If Carter approves an early apply, users see correct dates and translations before the republish.
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
  - The writer upserts `id, collection, title, translation, author, year, metadata` only (`datapipeline/writers/reader_writer.py:99-106`).
  - Anselm's three works all carry `year = 1099`; the plan corrects them to 1076, 1077-78 and 1098 (that fix belongs to 1.9; this item carries the values).
- **Changes:**
  - Registry (2.1's tracked file; its path is set by 2.1): add per-document fields `genre, issuer, year, date_label, translation, source_credit, certainty, attribution_note, note, clavis_ref`, and per-work entries `{work_key, title, author, certainty, attribution_note, note, date_label, year, genre, clavis_ref, positions: [first, last] or anchors}`. Validation in the registry loader: `certainty` in the four values, `genre` in the vocabulary Carter approves in 2.2a, `source_credit` present for every document (source from 0.2), `year` integer or null.
  - Value rules:
    - `translation`: the edition or translator shown to users, for example `Ante-Nicene Fathers (1885-1896)`, `Nicene and Post-Nicene Fathers, Series I`, `Vatican English`, `WEB-C` kept for the Bible (the web maps codes to names, `apps/web/src/components/sources/SourcesPage.tsx:12`). The `(collection, title, translation, author)` unique key allows this.
    - `issuer`: the pope for papal documents (from `metadata.pope`), the council for council documents, `Holy See` for the Catechism and the Code.
    - `year` stays the sortable integer; `date_label` carries ranges and "c.".
    - `source_credit`: exactly the wording 0.2's rights inventory records per source. If 0.2 agrees, vatican.va texts get `Text: Libreria Editrice Vaticana` and CCEL ThML texts get `Sourced via CCEL.org`. Never derived from a ThML `<description>`.
  - `datapipeline/model.py`: add the fields to `Document`, and `work_key`, `searchable`, `language`, `note` to `Passage`.
  - `datapipeline/writers/reader_writer.py:write_document`: write the new document columns and upsert `document_works` rows for the document, and write the new passage columns. It requires 0039 and fails with a clear message if the columns are missing.
  - New script `datapipeline/scripts/backfill_document_metadata.py`:
    - Reads the registry and the live `documents` rows by frozen id.
    - `--dry-run` (default) prints a per-document diff and totals by field.
    - `--apply` requires the publish lock's explicit production flag (0.4) and writes, in one transaction, `UPDATE documents SET genre, issuer, year, date_label, translation, source_credit, certainty, attribution_note, note, clavis_ref` for existing ids only, plus `document_works` rows and `UPDATE chunks SET work_key` by position range. It never touches `content`, `anchor`, `position`, `chapter_*`, never inserts or deletes documents or passages, and refuses if any registry id is missing from the database.
    - Writes a JSON report (counts per field, ids changed) for the PR or ops log.
  - Setting `work_key` updates `chunks` but not a column that 0037's triggers watch, so outlines stay valid.
- **Acceptance checks:**
  - `datapipeline/tests/test_backfill_document_metadata.py`: dry run on a fixture database changes nothing; apply updates only the listed columns (compare every other column before and after); refuses without the production flag; refuses when a registry id is missing; is idempotent (a second apply reports 0 changes).
  - `datapipeline/tests/test_reader_writer.py`: `write_document` writes the new columns and `document_works`.
  - Registry validation test: every document has `source_credit`; no `<description>` text appears in any registry field (check against the extracted blurbs of the vendored ThML files).
  - PR description must include the dry-run diff summary against the live database (read-only), with counts per field and per collection.
- **Production safety:** Merging changes no live data; the script defaults to dry run and the writer runs only under the publish lock. An early apply updates only new or empty display columns plus `year` and `translation` for 348 documents, which the current API already returns (`DocumentResponse.year`, `.translation`) and today's web already shows in the reader overview (`apps/web/src/components/reader/DocumentOverview.tsx:186`) and on `/sources`. The `/sources` cache holds old values for up to 1 hour (`routes/sources.py:16-18`). At P4 the writer writes the same values from the same registry, so there is nothing to reconcile. If 2.4a is not yet deployed, the new columns are simply unread.
- **Needs Carter:** Approval of the genre vocabulary and of an early `--apply` against the live database. The source credit wording where 0.2 has not settled it.
- **Out of scope:** Author corrections such as "Tertullian: Part Fourth." (1.8c), council authors (1.2), Anselm's date values (1.9), labels and certainty values themselves (3.2), genre and issuer filters (5.1a).

---

### 2.4a. API payloads, tombstones and redirects

- **Type:** PR
- **Depends on:** 2.2a merged (applied or not; the API tolerates both). Shares `corpus_schema.py` with 2.2b, whichever merges first creates it.
- **Goal:** The API sends each result's translation, date, attribution, certainty, notes, language and source credit. Removed passages and documents come back as tombstones instead of disappearing, and moved ones come back as redirects. The reader, `/sources`, history restore and bookmarks show only the live release.
- **Current state:**
  - The SSE `chunk` event's `source` carries `collection, document_title, author, reference, document_id, anchor, chapter_key, unit_label` only (`services/api/app/rag/pipeline.py:369-403`). The Pydantic mirror is `ChunkSource` (`app/models/search.py:21-35`), the TS mirror `ChunkSource` (`apps/web/src/lib/search-stream.ts:1-20`), which declares an optional `metadata` the API never sends.
  - History restore joins `retrievals → chunks → documents` (`routes/search.py:330-343`) and reports `results_unavailable` when rows are missing (`:380-385`). Bookmarks join the same way (`routes/bookmarks.py:161-167`).
  - The reader reads `documents`, `document_chapters` and `chunks` with no visibility filter (`routes/documents.py:28-70, 227-243`); a missing document is a 404 "Document not found" (`:130-131`). Guest reader access joins `guest_trial_retrievals → chunks` (`:91-101`).
  - `/sources` lists every document (`routes/sources.py:21-36`). Reading progress joins `chunks` for the chapter label (`routes/reading_progress.py:33-45`).
  - `DocumentResponse` has `id, collection, title, author, year, translation, metadata, chunk_count` (`app/models/documents.py:5-13`). `ReaderPassage` has no language or note (`:36-43`).
- **Changes:**
  - Models (`app/models/search.py`, `app/models/documents.py`, `app/models/bookmarks.py`), all new fields optional with default `None`:

    ```python
    class DocumentFacts(BaseModel):
        year: Optional[int] = None
        date_label: Optional[str] = None
        translation: Optional[str] = None
        genre: Optional[str] = None
        issuer: Optional[str] = None
        certainty: Optional[Literal["genuine", "disputed", "pseudonymous", "anonymous"]] = None
        attribution_note: Optional[str] = None
        note: Optional[str] = None
        source_credit: Optional[str] = None
        work_title: Optional[str] = None   # from document_works when the passage has a work_key

    class Tombstone(BaseModel):
        entity: Literal["document", "passage"]
        rule: str
        reason_code: str
        public_reason: str
        church_act: Optional[str] = None
        removed_in_release: int
        title: Optional[str] = None
        author: Optional[str] = None
        reference: Optional[str] = None

    class Redirect(BaseModel):
        document_id: str
        anchor: Optional[str] = None
        chunk_id: Optional[str] = None
    ```

    `ChunkSource` and `BookmarkSource` gain `facts: Optional[DocumentFacts]`, `language: Optional[str]`, `passage_note: Optional[str]`. `ChunkResult` and `BookmarkResponse` gain `status: Literal["current", "moved", "removed"] = "current"`, `tombstone: Optional[Tombstone]`, `redirect: Optional[Redirect]`. `DocumentResponse` gains `facts`, `works: list[WorkInfo]` and `status`. `ReaderPassage` gains `language`, `note`, `work_key`.
  - Work-level fields override document-level ones in `DocumentFacts` when a passage has a `work_key` (author and certainty for "Dubious or Spurious Writings." come from the work, not the document).
  - New step `rag/steps/document_facts.py`, called from `pipeline.py` after ranking and before the chunk events. One query per search: `SELECT ... FROM documents d WHERE d.id = ANY($1)` plus `document_works` for the `(document_id, work_key)` pairs and `chunks.language, note, work_key` for the result ids. Timeout 1 s; on failure it records via `degradation.record_recovery` (as `fetch_context` does) and events go out without `facts`. Guest search uses the same pipeline (`routes/guest_search.py:359`), so guests get the fields too.
  - Chunk event `source` adds `facts`, `language`, `passage_note`. The event shape change is additive.
  - Visibility predicate. One helper in `corpus_schema.py` returns the SQL fragment and parameter for "visible in the live release" given a table alias, or an empty fragment when 0039 is absent. Apply it to:
    - `routes/documents.py`: `_DOCUMENT_SQL` and fallbacks, the legacy TOC, first chapter and chapter key queries, the anchor lookup at `:227-229` and the passage query at `:239-243`. `document_chapters` is already built from live rows by 2.2a's function.
    - `routes/sources.py`: hide retired documents; bump the cache key with the live release so a switch shows at once in a process that has not restarted.
    - `routes/reading_progress.py`: the chapter label lateral join uses visible rows; a progress row whose document is retired is left out of `GET /reading-progress` lists and returns `status: "removed"` with the tombstone on the single-document GET.
    - History restore and bookmarks do **not** filter; they join retired rows on purpose and mark them.
  - Tombstone and redirect resolution, in a new `app/corpus_lifecycle.py`:
    - `async def resolve_passages(conn, ids) -> dict[str, Resolution]`, where `Resolution` is `current`, `moved(redirect)` or `removed(tombstone)`. Order of checks: a row visible in the live release is `current`; else a `corpus_redirects` row for the id, following at most 3 hops, is `moved`; else a `corpus_tombstones` row is `removed`; else `current` (a row outside every release window with no record is treated as today's behavior and logged as a warning).
    - `async def resolve_document(conn, doc_id, anchor) -> Resolution` with the same order, and for anchors the `entity = 'anchor'` redirects.
  - `routes/search.py:get_search_results`: after the existing join, call `resolve_passages`. `moved` results carry the redirect and the new passage's content and source; `removed` results carry `status: "removed"` and the tombstone and **no content** (see Needs Carter). `restore_status` counts moved and removed results as present, so a restore with removals is still `complete`.
  - `routes/bookmarks.py:list_bookmarks`: same resolution.
  - `routes/documents.py`: for a document that is not visible, `get_document`, `get_document_toc` and `get_document_reader` return HTTP 410 with body `{"detail": "removed", "tombstone": {...}}` when a document tombstone exists, HTTP 404 with body `{"detail": "moved", "redirect": {...}}` when a redirect exists, and today's 404 otherwise. An anchor that is no longer visible in a visible document returns the chapter from the anchor redirect with `highlight_anchor` set to the new anchor and a `redirected_from` field.
  - `require_document_access` for guests: keep the join, but also allow a document reached through a redirect from a passage the guest retrieved.
  - Explanations persisted in `retrievals.explanation` are returned unchanged for moved and removed results; the web decides whether to show them.
- **Acceptance checks:**
  - `tests/test_search_routes.py`: `test_restore_marks_removed_passage_with_tombstone_and_no_content`, `test_restore_follows_redirect_to_new_passage`, `test_restore_with_removal_is_complete`, `test_restore_without_0039_is_unchanged` (golden JSON of today's response).
  - `tests/test_bookmarks.py`: removed and moved bookmarks, note preserved.
  - `tests/test_reader_chapter_endpoint.py` and `test_reader_outline_endpoints.py`: retired passages are not in the chapter; a retired document returns 410 with the tombstone; a redirected document returns 404 with `redirect`; an old anchor returns the new chapter and `redirected_from`; both outline and fallback paths agree under release 2.
  - `tests/test_sources_endpoint.py`: retired documents hidden; cache refreshes on a release change.
  - `tests/test_reading_progress.py`: removed document leaves the list.
  - `tests/test_pipeline_persistence.py` or a new `test_document_facts.py`: chunk events include `facts` when 0039 exists; a failing facts query still yields chunk events without `facts` and records a recovery, not a degradation.
  - `tests/test_document_access_and_failures.py`: guest access through a redirect.
  - `tests/test_contract_models.py`: every new field optional; an event without them validates.
  - PR description must include before-and-after JSON for one search event, one restore and one reader response, and state that every added field is optional.
- **Production safety:** Before 0039 is applied, `corpus_schema` reports nothing, the facts step is skipped, no predicates are added and no resolution queries run, so every response is today's. After 0039 with only release 1 and no tombstones or redirects, every row is `current`, and the only change is that responses carry the extra optional fields; today's web ignores unknown fields. The 410 and redirect bodies can only occur after P4 creates tombstones and redirects, and 2.4b must be live by then. Adding one query per search adds latency of a few milliseconds (unverified; measure p95 before and after on the eval set).
- **Needs Carter:** Whether a removed passage shows its text anywhere after removal. Recommended is no text, with title, author, reference and one plain sentence of reason, with the Church act where one exists. The alternative keeps showing the text with a "removed from TheoCorpus" banner, which keeps the user's history intact but keeps excluded text on screen.
- **Out of scope:** Rewriting user rows to new ids (4.1a). Changing any SSE event type or the `/v1/chat` contract. Genre filters (5.1a).

---

### 2.4b. Web cards, reader, bookmarks, history and the source credit

- **Type:** PR
- **Depends on:** 2.4a deployed (the web reads optional fields and works without them)
- **Goal:** Users see the translation, date and attribution of what they read, including labels such as "Pseudo-Justin" and "disputed", and any note (for example, that the Apostolic Canons reached the Latin West only as canons 1 to 50). When a passage is opened and its text is on screen, a small source credit line such as "Text: Libreria Editrice Vaticana" or "Sourced via CCEL.org" appears below the text. Removed and moved passages are explained instead of failing.
- **Current state:**
  - `ChunkCard` has a collapsed header (`apps/web/src/components/search/ChunkCard.tsx:249-305`, fixed height 96 px mobile and 68 px desktop) and an expanded body with the passage text (`:307-397`). The Bible translation badge reads `source.metadata?.translation` (`:227-230`), which the API never sends, so it never shows.
  - `BookmarkCard` always shows the passage text (`apps/web/src/components/bookmarks/BookmarkCard.tsx:151-153`).
  - Reader: `DocumentOverview` shows `author · year · translation` (`apps/web/src/components/reader/DocumentOverview.tsx:186`); `ReaderChrome` shows the title (`ReaderChrome.tsx:77`); `ChapterSection` and `Passage` render headings and text with no metadata (`ChapterSection.tsx`, `Passage.tsx`).
  - `SourcesPage` shows author, year and translation per document (`SourcesPage.tsx:236-252`).
  - Reader load errors show a generic failure (`DocumentReader.tsx:197`, "Failed to load").
  - Restore status handling lives in `lib/search-experience/useSearchPageExperience.ts`.
- **Changes:**
  - `apps/web/src/lib/search-stream.ts` (the only SSE decoder): add `facts?: DocumentFacts | null`, `language?: string | null`, `passage_note?: string | null` to `ChunkSource`, and `status?`, `tombstone?`, `redirect?` to `ChunkResult`. Remove the unused `metadata` field. Types in `lib/api.ts` for `DocumentInfo`, `ReaderPassage`, `BookmarkChunkInfo`, `Bookmark`, `SearchResultsResponse` gain the same optional fields.
  - New pure module `apps/web/src/lib/attribution.ts` with unit tests:
    - `formatAttribution(author, facts)` returns e.g. `Pseudo-Justin`, `Justin Martyr (authorship disputed)`, `Anonymous`.
    - `formatDate(facts, fallbackYear)` prefers `date_label`, then `year`.
    - `formatTranslation(code)` maps `WEB-C` and similar codes to names (move the map from `SourcesPage.tsx:12`).
    - `certaintyTag(certainty)` returns `null` for `genuine`, else a short tag (`disputed`, `pseudonymous`, `anonymous`).
  - `ChunkCard.tsx`:
    - Collapsed header, which is the result card: author line uses `formatAttribution`, and a small certainty tag appears beside it when not genuine. Add the date after the author when it fits (`Augustine · 397-400`). No source credit, no notes, no translation in the header. Keep the fixed heights; truncate as today.
    - Fix the Bible badge to use `facts.translation`.
    - Expanded body, where the text is viewed: below the text and above "Why this is relevant", one muted line for the translation, then the notes (`attribution_note`, document `note`, `passage_note`), then the source credit as the last line in `text-xs text-brand-muted`. Use tokens only, no new hex.
    - A passage with `language` other than English shows "This passage is in Latin; it is not included in search." in the expanded body. Search should never return one after 3.3, so this matters for bookmarks and history.
    - `status === "removed"`: render a tombstone card with title, author, reference, `public_reason` and `church_act`, no content, no bookmark or feedback buttons, and a "Why was this removed?" link to the About page anchor (5.7 fills it; until then link to `/about`).
    - `status === "moved"`: render normally from the new content, with a muted line "This passage was renumbered in a corpus update."
    - Copy action: citation uses `formatAttribution` so a copied Pseudo-Justin passage is not credited to Justin.
  - `BookmarkCard.tsx`: same notes, translation and source credit under the text; tombstone and moved states; keep the user's note editable in both.
  - Reader:
    - `DocumentOverview.tsx`: attribution line becomes `formatAttribution · formatDate · formatTranslation`; show certainty, notes and the list of works with their own labels when `works` is non-empty; source credit at the bottom of the header section.
    - `ChapterSection.tsx`: source credit once at the end of each loaded chapter section (the text is being viewed). When a chapter's passages belong to a work whose attribution differs from the document's, show the work's label under the chapter heading.
    - `Passage.tsx`: non-English passages get the language note above the text; `note` renders as a small muted paragraph after the passage.
    - `DocumentReader.tsx` and `lib/api.ts` reader fetchers: on 410 with a tombstone, show a removal page (title, author, reason, Church act, back button). On 404 with `redirect`, `router.replace` to the new document and anchor, keeping `from` and `returnKey`. On `redirected_from`, highlight the new anchor.
    - Guest reader shares these components (`isGuest`); no guest fork.
  - `SourcesPage.tsx`: use `formatAttribution` and `formatDate`; show a certainty tag.
  - History restore: `useSearchPageExperience.ts` treats `removed` and `moved` results as present; no "results unavailable" notice for them.
- **Acceptance checks:**
  - `ChunkCard.test.tsx`: header shows attribution and certainty tag and never the source credit; expanded body shows translation, notes and credit in that order; Bible translation badge renders from `facts`; removed status renders the tombstone without content and without bookmark buttons; moved status shows the renumbered line; copy text uses the attributed author; a result with no `facts` renders exactly as today (snapshot).
  - `BookmarkCard.test.tsx`: credit under the text; tombstone keeps the note.
  - `DocumentReader.test.tsx`: 410 shows the removal page; 404 with redirect replaces the URL; credit appears once per chapter section.
  - `lib/attribution.test.ts` for each formatter.
  - `SearchPage.test.tsx`: a restore with a removed result shows no unavailable notice.
  - `npm run lint` (0 errors, no new warnings in touched files), `npm test`, `npm run build`.
  - PR description must include screenshots at 375 px and desktop, dark and light themes, of a collapsed card, an expanded card with a credit, a tombstone card, the reader overview with works, and the removal page.
- **Production safety:** Every new field is optional. Before 2.4a deploys, or before 0039 is applied, all fields are absent and the components render today's output, which the snapshot tests hold. Tombstones and redirects cannot exist until P4, and this PR must be live before the P4 cutover (4.1b checklist item).
- **Needs Carter:** Confirm the reading of "only when a passage is opened and its text is viewed" as the expanded search card, the bookmark card and the reader, and never the collapsed result card. The narrower reading is the reader only. Confirm the tombstone wording pattern.
- **Out of scope:** The About page rewrite (5.7). Genre and issuer filter controls (5.1a). Any change to search lifecycle state in `lib/search-experience/` beyond counting moved and removed results as present.

---

### 2.4c. About page factual fix

- **Type:** PR
- **Depends on:** none
- **Goal:** The About page stops naming authors who are not in the corpus.
- **Current state:**
  - `apps/web/src/components/about/AboutPage.tsx:14-15` (church-fathers) names "Ignatius of Antioch, Justin Martyr, Origen, Athanasius, Augustine, and John Chrysostom". `:16-17` (medieval) names "Anselm of Canterbury, Bonaventure, Hildegard of Bingen, and Duns Scotus" and says "roughly 9th through 15th centuries".
  - Live, 29 Sep: Chrysostom, Bonaventure, Hildegard and Duns Scotus have no documents. **Origen is in the corpus today** (3 documents, 932 passages) and leaves under rule A at P4; the plan's statement that none of the five are in the corpus is wrong for Origen, but his name goes anyway because the removal is decided. Ignatius (21 docs), Justin Martyr (9), Athanasius (1), Augustine (5), Irenaeus (6) and Anselm (3) are present.
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

- **Type:** PR (registry entries, adapter and writer changes, tombstone writer). Takes effect at the P4 cutover.
- **Depends on:** R1 (rule A dating and Church-act check; decides Tertullian's To His Wife and On the Apparel of Women), 2.1 (registry), 2.2a applied, 2.4a and 2.4b deployed before cutover, 1.8a, 1.8b and 1.8c (editorial strips and the recension split, which share this item's registry entries), 4.1a (remap and rehearsal) for application.
- **Goal:** After the republish, the works the rules exclude are gone from search and the reader, each leaves a tombstone that says why in one sentence, and no user loses a saved search, bookmark, label or guest result.
- **Current state:**
  - Removal targets and their live document ids (29 Sep):

    | Rule | Target | Document ids (prefix) | Scope |
    |---|---|---|---|
    | A | Origen: Against Celsus, De Principiis, Letter to Gregory | `5a05852b`, `4c96eac3`, `9c052574` | whole |
    | A | Tertullian: De Fuga, Exhortation to Chastity, On Fasting, On Modesty, On Monogamy, On the Pallium, On the Veiling of Virgins | `d2b71f9f`, `e5d235f3`, `89201a06`, `6b70b67f`, `01abb5ad`, `d7f29587`, `17b7747f` | whole |
    | A | Tertullian: To His Wife, On the Apparel of Women | `3717ce05`, `e73bb326` | kept provisionally, pending R1 |
    | A | Novatian: On the Trinity, On the Jewish Meats | `0f23bbcf`, `2f22d9b5` | whole |
    | A | Novatian inside "Treatises Attributed to Cyprian on Questionable Authority." | `5d75dc92` | chapter labels Treatise I (positions 1 to 8) and Treatise III (25 to 32) |
    | A | Tatian, Address to the Greeks | `356b9c9b` | whole |
    | A | Arnobius, Against the Heathen | `85e7153f` | whole |
    | A | Alexander of Lycopolis, Of the Manichaeans | `0d274c4c` | whole |
    | B | Apostolic Constitutions Books I to VII | `d72938c6`, `df17e279`, `df6fd2f7`, `aab0848e`, `49437294`, `f04e045b`, `fd6550b9` | whole |
    | B | Apostolic Constitutions Book VIII | `10d8d7c6` | positions 0 to 34 go; 35 to 43 ("The Ecclesiastical Canons of the Same Holy Apostles") stay |
    | B | Six forged Ignatius letters (Maria of Cassobelae, Mary at Neapolis, Tarsians, Philippians, Antiochians, Hero) | `7073bae0`, `4fe41814`, `56add0dd`, `567be8a5`, `0311d705`, `5553da19` | whole |
    | B | Sectional Confession of Faith (Apollinaris, CPG 3645) | `44fd52c3` | positions 0 to 23 |
    | B | Long recension text in the 7 "Shorter and Longer Versions" documents | `89853cef`, `c1bcdc39`, `bb72e2f6`, `fa2cd483`, `995d76f9`, `f9e64ef8`, `fc317c73` | text inside passages; split by 1.8c |
    | C | Pfaff fragments of Irenaeus XXXVI to XXXIX | `0066869a` | positions 37 to 40 |
    | C | Four medieval Latin Ignatius letters (CPG 1028) | `76b8b853`, `63e7f0b7`, `830a2c63`, `1a0a016b` | whole |
    | G | Editorial passages (Elucidations, translators' introductions and notices, "Argument" summaries that are editorial) | many | about 120 by the plan; a label heuristic finds 144 (chapter labels matching Elucidation, Translator, Introductory Note or Notice, Biographical, Argument); 1.8a to 1.8c settle the exact list |

  - User rows touching each target are in the table in the Cross-cutting design section. In total 54 retrievals, 6 guest rows, 0 bookmarks, 0 labels, 0 reading progress rows and 0 feedback rows for rules A to C; 3 retrievals for the rule G heuristic.
  - The writer deletes what a build no longer emits, which cascades (`reader_writer.py:36-81`); `clear_collection` deletes a whole collection (`:16-33`).
  - CCEL `<description>` blurbs sit in the ThML header of the vendored files (for example `datapipeline/sources/medieval/consolation-of-philosophy.xml:11`). The adapters iterate `div1` elements in the body (`datapipeline/ingest/church_fathers.py:59`, `ingest/medieval.py:45`), and a live search for the four medieval blurbs' opening sentences found 0 passages. Checked for the 4 medieval files only; the Fathers files were not checked passage by passage.
- **Changes:**
  - Registry: each target above gets `status: remove` with `rule`, `reason_code`, `public_reason`, `church_act`, and for partial targets the position or anchor ranges (2.1 defines the range form). `reason_code` vocabulary:
    - `condemned_by_name` (A, limit 1): Origen (Constantinople II, 553, anathema 11), Novatian (Roman synod under Pope Cornelius, 251, as reported by Eusebius, Church History 6.43).
    - `outside_communion_or_undated` (A, limit 3): Tertullian's 7 works (Benedict XVI, general audience of 30 May 2007, for the break), Tatian (Irenaeus, Against Heresies 1.28.1; Eusebius, Church History 4.28-29).
    - `before_baptism` (A): Arnobius (Jerome, Chronicle).
    - `non_christian_author` (A): Alexander of Lycopolis (van Oort 2012).
    - `forgery_heterodox` (B): Apostolic Constitutions (Council in Trullo, canon 2, confirmed by Nicaea II, canon 1), six Ignatius letters and the long recension (majority of standard scholarship), Sectional Confession (Caspari 1879, Lietzmann 1904).
    - `late_fabrication` (C): Pfaff fragments (Harnack 1900), medieval Latin Ignatius letters (CPG 1028).
    - `editorial` (G).
  - `public_reason` drafts, one sentence each, for Carter to approve. For Origen, "Removed because the Second Council of Constantinople (553) condemned Origen by name, and TheoCorpus excludes authors the Church has condemned by name." For rule G, "Removed because this text was written by a modern editor, not the author."
  - Adapters (`datapipeline/ingest/church_fathers.py`, `medieval.py`, `thml_doc.py`): skip every registry range marked `remove`. The adapter asks the registry; no author or title string matching in adapter code.
  - Writer, release mode (used only with the P4 cutover flag):
    - `reader_writer.prune_missing_chunks` and `prune_missing_documents` gain a `release` parameter. In release mode they set `retired_release = <new release>` instead of deleting, and write a `corpus_tombstones` row for each retired id that the registry marks `remove`, or a `corpus_redirects` row when the registry or remap tool gives a successor. A retired id with neither is an error that stops the run.
    - `clear_collection` refuses to run when any user row references the collection's passages, naming the tables and counts.
  - Tombstone snapshot is taken from the live row before retiring: `collection, title, author, reference, chapter_label`.
  - A regression check that no ThML `<description>` text reaches content: new `datapipeline/tests/test_thml_description_excluded.py` builds each ThML adapter's documents from fixtures containing a `<description>` and asserts no passage contains it. For vendored sources, the 0.1a coverage checks gain a rule that fails when any passage contains 40 or more consecutive characters of a file's `<description>`.
  - Release report (0.1c) lists every retired id with its rule and tombstone, and every user row pointing at one.
- **Acceptance checks:**
  - `datapipeline/tests/test_church_fathers.py`: building with the registry emits none of the removed ranges; Book VIII emits exactly the 9 canon passages; "Treatises Attributed to Cyprian" emits Treatises II and IV only (plus nothing editorial).
  - `datapipeline/tests/test_reader_writer.py`: in release mode no DELETE is issued (assert with a statement log); retired rows get `retired_release`; each gets a tombstone or redirect; a retired id without either raises.
  - `test_clear_collection_refuses_with_user_rows`.
  - Rehearsal on a Supabase branch (4.1a): after publishing release 2 and `publish_corpus_release(2)`, the counts of `retrievals`, `bookmarks`, `retrieval_labels`, `guest_trial_retrievals` and `reading_progress` are unchanged, and the removed ids return tombstones through `/searches/{id}/results`.
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
- **Production safety:** Merging changes only the registry, adapters and writer; the publish lock (0.4) keeps them away from production until P4. At cutover, removed rows are retired in the staged release and stay in the tables, so every user foreign key survives, and 2.4a returns tombstones for them. Rollback (`publish_corpus_release(1)` and the alias back to `chunks`) makes them visible again with nothing lost. If this merged before 2.4a and 2.4b were deployed, nothing would happen, because nothing publishes until P4; the 4.1b checklist blocks cutover until both are live.
- **Needs Carter:** R1's result for To His Wife and On the Apparel of Women. Approval of each `public_reason` sentence. The display policy for removed text (2.4a). The rule G final list after 1.8a to 1.8c.
- **Out of scope:** Label changes for works that stay (3.2). The split of the Shorter and Longer documents and the Ignatius greetings (1.8c). Hard-deleting retired rows (post-cutover ops). The About page section on excluded authors (5.7).

---

### 3.2. Labels, certainty and notes for works that stay

- **Type:** PR (registry values; displayed by 2.4b). Applied early by 2.3's `--apply` if Carter approves, otherwise at P4.
- **Depends on:** 2.1, 2.2a applied, 2.3 (fields and backfill script), 2.4a and 2.4b (to be visible), R4 for the Hippolytus appendix scope.
- **Goal:** Doubtful works say so. A user reading the Hortatory Address sees "Pseudo-Justin"; a user reading the Twelve Topics sees it is not Gregory's; a user reading the Didache sees it is anonymous; the Summa Supplement says it was compiled after Aquinas died.
- **Current state:**
  - Every document has only `author` for attribution; no certainty or note exists anywhere. Authors live: Justin Martyr for the Hortatory Address (`3f1d7ed1`, 41 passages), On the Sole Government of God (`dd54c7cc`, 6), The Discourse to the Greeks (`abd0e330`, 5), On the Resurrection, Fragments (`24b54b57`, 12); "Gregory Thaumaturgus." for Dubious or Spurious Writings (`44fd52c3`, 80); Barnabas (`1d83b302`); Mathetes for Diognetus (`abf69de0`, 13); "Hippolytus." for the Appendix of dubious pieces (`a2b36c64`, 57); Ignatius for The Martyrdom of Ignatius (`841b4e0a`, 8); Victorinus (`e847b8bb`, 39); Methodius for Oration on the Palms and the homily fragments (`5f210d1e`); Pamphilus (Exposition of the Acts, positions 2 to 5).
  - In ANF volumes, one document holds several works, and chapter keys repeat across works ("Section I" occurs at positions 0 and 43 of `44fd52c3`). Work boundaries must therefore be position or anchor ranges, which is why 2.2a adds `chunks.work_key` and `document_works`.
  - Unverified which document holds the Refutation of All Heresies (CPG 1899), the Muratorian fragment, On the Glory of Martyrdom, Exhortation to Repentance, Canons of Hippolytus, the Acts of Archelaus and the Lactantius Poem on the Passion. 2.1's registry must locate each by CPG number before this PR.
- **Changes:** Registry values, per the plan's "Labels for works that stay", using 2.2a's fields. `author` is the rule H credit shown to users; `certainty` is the label; `clavis_ref` the CPG number.

  | Work | author | certainty | attribution_note or note | clavis_ref |
  |---|---|---|---|---|
  | Hortatory Address to the Greeks | Pseudo-Justin | pseudonymous | "Not by Justin Martyr. Riedweg (1994) proposes Marcellus of Ancyra, with a question mark." | CPG 1083 |
  | On the Sole Government of God | Pseudo-Justin | pseudonymous | "Not by Justin Martyr; date uncertain." | CPG 1084 |
  | Discourse to the Greeks | Pseudo-Justin | pseudonymous | "Not by Justin Martyr." | CPG 1082 |
  | On the Resurrection, Fragments | Justin Martyr | disputed | "Authorship disputed; Heimgartner (2001) assigns it to Athenagoras." | CPG 1081 |
  | Twelve Topics on the Faith (work in `44fd52c3`, positions 28 to 40) | Pseudo-Gregory Thaumaturgus | pseudonymous | "Not by Gregory Thaumaturgus." | CPG 1772 |
  | On the Subject of the Soul, to Tatian | Gregory Thaumaturgus | disputed | | CPG 1773 |
  | Four Homilies, On All the Saints (works in `44fd52c3`) | Pseudo-Gregory Thaumaturgus | pseudonymous | | CPG 1775 to 1777 |
  | Refutation of All Heresies | Hippolytus | disputed | "Attributed to Hippolytus in modern times; the attribution is disputed." | CPG 1899 |
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
  | Martyrdom of Ignatius | Anonymous | anonymous | "A legendary account." | |
  | Seventh Council of Carthage under Cyprian | Cyprian | genuine | "Its ruling on rebaptizing heretics was not adopted by the Church." | |
  | Summa Supplement and its appendix | Thomas Aquinas | genuine | "Compiled after Aquinas's death from his earlier writings." Applied as a work over the Supplement's 4,084 and appendix's 82 passages. | |
  | Victorinus, Commentary on the Apocalypse | Victorinus of Pettau | genuine | Two works: original and "Jerome's recension", labeled separately. | |
  | Apostolic Canons (Book VIII positions 35 to 43) | Anonymous | anonymous | "The Latin West received canons 1 to 50 through Dionysius Exiguus; all 85 were confirmed by the Council in Trullo (canon 2) and Nicaea II (canon 1)." | |
  | Cyprian's two anonymous treatises in `5d75dc92` (Treatises II and IV) | Anonymous | anonymous | | |
  | On Loving God | Bernard of Clairvaux | genuine | translation: "translator unknown (via Paul Halsall's Internet Medieval Sourcebook)" | |

  Wording in the notes follows the research memo; Carter approves the final sentences. Works with CPG numbers take them from the research memo's confirmed list only.
  - Authenticity judgments copied from editorial text before rule G deletes it (plan rule G) go into `attribution_note`, except where this plan overrides them.
  - No code change beyond registry values and their validation test.
- **Acceptance checks:**
  - Registry validation test: every entry in the table exists, has a `certainty`, and every `Pseudo-` author has `certainty = pseudonymous`.
  - `backfill_document_metadata.py --dry-run` against live shows exactly the listed documents and works changing.
  - After an early apply or at P4, `GET /v1/documents/3f1d7ed1-...` returns `author: "Pseudo-Justin"`, `facts.certainty: "pseudonymous"`, and a search for "true religion of the Greeks" shows the Pseudo-Justin label on the card (manual check, screenshot in the PR or ops log).
  - PR description must list each label with its source line in the research memo.
- **Production safety:** Values only. Unapplied, nothing changes. Applied early by 2.3's script, the new `author` values appear on cards and in `/sources` and nothing else changes; the `(collection, title, translation, author)` unique key has no collision because no two documents share the new labels with the same title. The Qdrant payload still carries the old author until P4, so vector-only results show the old author on the card while FTS and reader show the new one. **To avoid that mismatch, the early apply should wait until 2.4a is deployed**, since 2.4a's `facts` and document author come from Postgres for every result (2.4a must take `author` from the facts query, overriding the payload).
- **Needs Carter:** Approval of every label and note sentence. Whether the early apply happens before P4.
- **Out of scope:** Author cleanup of malformed names such as "Tertullian: Part Fourth." (1.8c). Moving Boethius and Pseudo-Dionysius to Church Fathers (P5). The Catena Aurea's per-quotation attribution (P5).

---

### 3.3. Non-English passages: keep in the reader, remove from search

- **Type:** PR (registry values and writer), plus an ops step that can apply it before P4
- **Depends on:** 2.2a applied, 2.2b deployed (its FTS and Qdrant filters), 2.4b deployed (the language note), 2.1.
- **Goal:** Latin and Italian passages stop appearing in search results. They stay readable in the reader with a note saying they are not in English and not searched. Where a public-domain or licensed English translation exists, it replaces them instead.
- **Current state:**
  - Plan counts: Clement, Stromata III, Latin, 33; Clement, The Instructor II.10, Latin, 4; Lactantius, Divine Institutes VI and On the Workmanship of God, Latin, 5; Ubi Lutetiam (Pius VI), Italian, 17. Total 59.
  - A Latin-stopword heuristic on 29 Sep found 33 in the Stromata (`3a68ef3f`), 5 in The Instructor (`96584290`), 3 in the Divine Institutes (`9e03c96d`), 1 in On the Workmanship of God (`f913305f`), and all 17 of Ubi Lutetiam (`ba74d920`). The small differences from the plan mean the final list must be fixed by id in the registry, checked by eye.
  - User rows: 1 retrieval points at one of these passages (Divine Institutes); 0 bookmarks, labels or guest rows.
  - Canon law's Latin (canons 111, 579, 695, 700, and paragraphs of 535 and 868) is handled by 1.5 under the plan's rule 6 and rule E; it uses the same `language` and `searchable` fields when no unofficial English exists.
- **Changes:**
  - Research step inside this item, before code: for each of the four works, record whether a public-domain or licensed English translation of the missing sections exists (0.2's rights inventory holds the answer). The plan's default when none exists is reader-only; TheoCorpus makes no translations of its own.
  - Registry: per passage id (or anchor range), `language` (`la` or `it`), `searchable: false`, and a passage `note`, for example "Left in Latin by the Ante-Nicene Fathers translators; no public-domain English translation is available." When an English translation is adopted, the adapter substitutes it (a separate adapter change under 1.8a or 1.3) and the passage stays searchable.
  - Writer: `Passage.searchable`, `language`, `note` flow to `chunks` (2.3's writer change) and to the Qdrant payload (`searchable`, 2.2b's `build_point` change).
  - Ops apply before P4, with Carter's approval, by a small script `datapipeline/scripts/apply_passage_flags.py --dry-run|--apply` (production flag from 0.4):
    - `UPDATE chunks SET searchable = false, language = $lang, note = $note WHERE id = ANY($ids)` for the registry ids.
    - Qdrant `set_payload({"searchable": False}, points=ids)` on the collection the alias targets.
    - Verifies afterwards that each id is absent from an FTS query on a distinctive Latin word and from a vector query using the passage's own vector.
  - No change to the reader, which already shows every passage of a chapter; 2.4b adds the language note.
- **Acceptance checks:**
  - Registry test: exactly the approved ids carry `searchable: false`, each with `language` and `note`.
  - Script tests: dry run changes nothing; apply sets only the three columns and the one payload key; refuses without the flag.
  - After the ops apply: the FTS and vector checks above pass for all ids; `/v1/documents/9e03c96d-.../reader` for the affected chapter still returns those passages with `language: "la"`.
  - PR description must include the final id list per work with the first 80 characters of each passage, and the translation research result.
- **Production safety:** Before 2.2b deploys, the column and payload flag are ignored by search, so applying early changes nothing; that is why this item waits for 2.2b. After the apply, the only change is that 59 passages leave search results. The one retrieval pointing at one of them still restores, because history restore does not filter on `searchable`. Rollback is the same script with `searchable = true` and the payload key deleted. At P4, the new collection is built with the flag already set.
- **Needs Carter:** Approval of the id list, the note wording, and the early ops apply against Supabase and Qdrant.
- **Out of scope:** Canon law Latin (1.5). Writing or commissioning translations. Removing any non-English passage from the reader.
