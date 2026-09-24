-- Backfill the reader outline (0037) for the current corpus.
--
-- Separate from 0037 so the backfill does not run under 0037's ACCESS EXCLUSIVE lock on
-- `documents`, which blocks reads. This file is one transaction and takes only row
-- locks (refresh_document_outline locks each document's row FOR UPDATE), which plain
-- SELECTs never wait on: searches and the reader keep reading throughout, and until
-- the transaction commits they see chunk_count NULL and fall back to deriving the
-- outline from chunks. The row locks are held until commit, so a datapipeline publish
-- of a document already visited waits for the backfill to finish (a second or two for
-- the current 421 documents: the aggregation alone measured 350 ms on production).
--
-- Idempotent: each call replaces that document's outline, so rerunning is harmless.

-- If a publish is holding a document row, fail fast and rerun rather than wait on it.
SET lock_timeout = '5s';

DO $$
DECLARE
    doc_id uuid;
BEGIN
    FOR doc_id IN SELECT id FROM documents ORDER BY id LOOP
        PERFORM public.refresh_document_outline(doc_id);
    END LOOP;
END;
$$;
