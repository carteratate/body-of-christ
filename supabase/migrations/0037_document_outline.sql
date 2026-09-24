-- Precomputed reader outline: each document's passage count and ordered chapter list.
--
-- The reader derived both from `chunks` on every request. For the Summa (one document,
-- 26,750 passages, 3,120 chapters) that meant /toc scanned the whole chunks table
-- (chapter_label is not in any index) and every /reader call counted 26,750 rows and
-- listed all 3,120 chapter keys just to find the previous and next chapter. /sources
-- counted passages for every document. The outline only changes when a collection is
-- published, so it is computed then instead.
--
-- Maintained by `refresh_document_outline`, which the datapipeline's
-- `reader_writer.write_document` calls inside the transaction that writes a document's
-- chunks. Anything else that changes a document's chunk set, positions or chapter
-- fields must call it too. Deleting a document removes its outline by cascade.
--
-- Additive: until a document has been refreshed its chunk_count is NULL, and the API
-- falls back to deriving the outline from chunks, so deploy order does not matter.
--
-- Schema only. The backfill is 0038, a separate migration, because a migration runs in
-- one transaction: here the ADD COLUMN's ACCESS EXCLUSIVE lock on `documents` (which
-- blocks reads, and nearly every search and reader request reads `documents`) would be
-- held for the whole 421-document backfill. Split, this transaction commits in
-- milliseconds and 0038 takes only row locks, which readers do not wait on.

-- Fail fast rather than queue every reader behind the ADD COLUMN if a long-running
-- statement already holds a lock on `documents`; rerun the migration when it clears.
SET lock_timeout = '5s';

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
    -- on the chapter rows: a deadlock.
    PERFORM 1 FROM documents WHERE id = p_document_id FOR UPDATE;

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

-- Read by FastAPI (service role, which bypasses RLS) and written by the datapipeline.
-- RLS with no policies plus the revokes keeps both out of the Data API.
ALTER TABLE document_chapters ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE document_chapters FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.refresh_document_outline(uuid) FROM PUBLIC, anon, authenticated;
