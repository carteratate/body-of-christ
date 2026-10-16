-- Excerpt-only documents (issue #265).
--
-- A document whose rights are not cleared keeps its passages in search, but its full
-- text is not offered: the API refuses /documents/{id}/reader and /toc for it with 403
-- `reader_restricted`, and the frontend links to the official source instead.
--
-- The value is DERIVED, never edited by hand. `datapipeline/reader_access.py` sets it
-- from `datapipeline/rights_inventory.json`: `full` when the work's status is a `pd-*`
-- status, `permission` or `licence`; `excerpt` for `in-copyright` or `unknown`. The
-- reader writer sets it on every publish, so a republish cannot reopen an uncleared text.
-- Rerunning the sync after an inventory change is the unblock path.
--
-- Additive: every existing row gets 'full', so applying this migration alone changes
-- nothing a reader sees. Blocking starts when the sync runs. Numbered 0041 because 0039
-- is reserved for 2.2a (#178) and 0040 is the contents tree.

-- ADD COLUMN with a constant default is a catalog-only change (no table rewrite), but it
-- takes an ACCESS EXCLUSIVE lock. Fail after 2 s rather than queue behind a long publish.
SET LOCAL lock_timeout = '2s';

ALTER TABLE documents
    ADD COLUMN reader_access text NOT NULL DEFAULT 'full'
        CONSTRAINT documents_reader_access_check CHECK (reader_access IN ('full', 'excerpt'));
