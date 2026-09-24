-- Precomputed reader outline: each document's passage count and ordered chapter list.
--
-- The reader derived both from `chunks` on every request. For the Summa (one document,
-- 26,750 passages, 3,120 chapters) that meant /toc scanned the whole chunks table
-- (chapter_label is not in any index) and every /reader call counted 26,750 rows and
-- listed all 3,120 chapter keys just to find the previous and next chapter. /sources
-- counted passages for every document. The outline only changes when a collection is
-- published, so it is computed then instead.
--
-- documents.chunk_count doubles as the outline's validity flag. NULL means "no current
-- outline": the API then derives the structure from chunks exactly as before.
--   * refresh_document_outline builds a document's outline and sets the count. The
--     datapipeline's reader_writer.write_document calls it as the last statement of
--     the transaction that writes the document's chunks.
--   * The invalidate_document_outline triggers set the count back to NULL whenever a
--     write changes a document's chunk set, positions or chapter fields, so an
--     outline can never be served stale: a writer that does not refresh (an older
--     datapipeline checkout, a manual fix) only returns that document to the fallback.
--     Annotation-only updates (datapipeline enrichment) leave it alone.
--   * Deleting a document removes its outline by cascade.
-- So the API, the datapipeline and 0038's backfill can deploy in any order.
--
-- Schema only. The backfill is 0038, a separate migration, because a migration runs in
-- one transaction: here the ADD COLUMN's ACCESS EXCLUSIVE lock on `documents` (which
-- blocks reads, and nearly every search and reader request reads `documents`) would be
-- held for the whole 421-document backfill. Split, this transaction commits in
-- milliseconds and 0038 takes only row locks, which readers do not wait on.

-- While the ADD COLUMN waits for its lock, every new reader of `documents` queues
-- behind it. If a long-running statement holds the table, fail after 2 s rather than
-- stall searches; rerun the migration when it clears. LOCAL ends with this transaction.
SET LOCAL lock_timeout = '2s';

ALTER TABLE documents
    ADD COLUMN chunk_count integer CHECK (chunk_count >= 0);

-- One row per chapter, in reading order. `ordinal` is 1-based and dense, so the
-- previous and next chapters are ordinal - 1 and ordinal + 1.
CREATE TABLE document_chapters (
    document_id   uuid    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal       integer NOT NULL CHECK (ordinal > 0),
    chapter_key   text    NOT NULL,
    -- Nullable because chunks.chapter_label is; the label of the chapter's first passage.
    chapter_label text,
    PRIMARY KEY (document_id, ordinal),
    UNIQUE (document_id, chapter_key)
);

-- Rebuild one document's outline from its chunks. The definition of a chapter and its
-- order matches what the reader previously derived per request: chunks with a
-- chapter_key, grouped by key, ordered by the key's first position (a key's passages
-- need not be contiguous). A chapter is one key with one label: the passage contract
-- (docs/superpowers/specs/2026-06-13-passage-contract-design.md) defines chapter_label
-- as the section's heading, and production has no key with two labels. The old /toc
-- grouped by (key, label), so a key with two labels would have listed twice; here it
-- lists once, under its first passage's label, as the reader header always showed it.
CREATE FUNCTION public.refresh_document_outline(p_document_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
    -- Lock the document row before touching its chapters, so every caller takes locks
    -- in the same order. reader_writer.write_document has already locked it (its
    -- upsert) when it calls this; without this line, a concurrent backfill that locked
    -- the chapter rows first would wait on the document row while write_document waited
    -- on the chapter rows: a deadlock. NO KEY UPDATE, not UPDATE, because FOR UPDATE
    -- also blocks the FOR KEY SHARE locks that inserts into tables referencing
    -- documents take (reading_progress, product_feedback), stalling them until commit.
    PERFORM 1 FROM documents WHERE id = p_document_id FOR NO KEY UPDATE;

    DELETE FROM document_chapters WHERE document_id = p_document_id;

    INSERT INTO document_chapters (document_id, ordinal, chapter_key, chapter_label)
    SELECT p_document_id,
           row_number() OVER (ORDER BY min(c.position))::integer,
           c.chapter_key,
           (array_agg(c.chapter_label ORDER BY c.position))[1]
    FROM chunks AS c
    WHERE c.document_id = p_document_id
      AND c.chapter_key IS NOT NULL
    GROUP BY c.chapter_key;

    UPDATE documents
    SET chunk_count = (SELECT count(*) FROM chunks WHERE document_id = p_document_id)
    WHERE id = p_document_id;
END;
$$;

-- Mark the outline of a document whose chunks change structurally as not current.
-- Row-level on purpose: write_document issues one statement per passage, and statement
-- triggers with transition tables cannot reuse plans, which made a Summa republish
-- (26,750 passages) take 182 s instead of 3 s. As row triggers it costs ~3%. The
-- `chunk_count IS NOT NULL` guard makes every row after a document's first a no-op
-- read, and the UPDATE trigger's WHEN clause skips non-structural updates without
-- calling the function (enrichment rewrites annotations on every chunk).
CREATE FUNCTION public.invalidate_document_outline()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
    IF TG_OP <> 'DELETE' THEN
        UPDATE documents SET chunk_count = NULL
        WHERE id = NEW.document_id AND chunk_count IS NOT NULL;
    END IF;
    IF TG_OP = 'DELETE' OR OLD.document_id IS DISTINCT FROM NEW.document_id THEN
        UPDATE documents SET chunk_count = NULL
        WHERE id = OLD.document_id AND chunk_count IS NOT NULL;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER chunks_invalidate_outline_on_write
    AFTER INSERT OR DELETE ON chunks
    FOR EACH ROW EXECUTE FUNCTION public.invalidate_document_outline();

CREATE TRIGGER chunks_invalidate_outline_on_restructure
    AFTER UPDATE OF document_id, position, chapter_key, chapter_label ON chunks
    FOR EACH ROW
    WHEN ((OLD.document_id, OLD.position, OLD.chapter_key, OLD.chapter_label)
          IS DISTINCT FROM (NEW.document_id, NEW.position, NEW.chapter_key, NEW.chapter_label))
    EXECUTE FUNCTION public.invalidate_document_outline();

-- Read by FastAPI (service role, which bypasses RLS) and written by the datapipeline.
-- RLS with no policies plus the revokes keeps both out of the Data API.
ALTER TABLE document_chapters ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE document_chapters FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.refresh_document_outline(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.invalidate_document_outline() FROM PUBLIC, anon, authenticated;
