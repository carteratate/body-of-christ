-- Backfill the reader outline (0037) for the current corpus.
--
-- Separate from 0037 so the backfill does not run under 0037's ACCESS EXCLUSIVE lock on
-- `documents`, which blocks reads. This file is one transaction and takes only row
-- locks (refresh_document_outline locks each document's row FOR NO KEY UPDATE), which
-- plain SELECTs, and inserts that reference documents, never wait on: searches and the reader keep reading throughout, and until
-- the transaction commits they see chunk_count NULL and fall back to deriving the
-- outline from chunks. The row locks are held until commit, so a datapipeline publish
-- of a document already visited waits for the backfill to finish (a second or two for
-- the current 421 documents: the aggregation alone measured 350 ms on production).
--
-- Do not run a collection wipe or prune (clear_collection, prune_missing_documents)
-- while this runs: they lock documents rows in scan order, this in id order, so the two
-- can deadlock. Postgres would abort one of them; rerun it.
--
-- Idempotent: each call replaces that document's outline, so rerunning is harmless.

-- If a publish is holding a document row, fail fast and rerun rather than wait on it.
-- LOCAL ends with this transaction.
SET LOCAL lock_timeout = '5s';

DO $$
DECLARE
    doc_id uuid;
BEGIN
    FOR doc_id IN SELECT id FROM documents ORDER BY id LOOP
        PERFORM public.refresh_document_outline(doc_id);
    END LOOP;
END;
$$;
