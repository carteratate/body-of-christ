-- Contents trees: the hierarchy of a document's headings (issue #250).
--
-- The reader outline (0037, document_chapters) is a flat list of chapters, the units
-- the reader loads. For the Catechism and the Summa that list is the wrong way in:
-- 3,120 Summa articles with no Part, or 29 Catechism buckets. A contents tree groups
-- the chapters under the text's own headings (Part > Treatise > Question > Article)
-- and can point at a heading inside a chapter. It never defines chapters; every node
-- opens one, by chapter_key, and optionally a passage in it, by anchor.
--
-- Named "contents" because "outline" already means 0037's chapter list.
--
-- Written by the datapipeline (reader_writer.write_document, in the transaction that
-- writes the document's chunks) from the tree a source adapter emits; most collections
-- emit none and have no rows. Read by FastAPI's /documents/{id}/toc, which returns the
-- tree only when every node's chapter and anchor still exist, so a writer that rewrites
-- chunks without rewriting the tree degrades the reader to the flat list rather than
-- sending readers to dead chapters. The API also runs on a database without this table.
--
-- Additive: one new table, nothing on existing tables changes. Numbered 0040 because
-- 2.2a (corpus cleanup, #178) reserves 0039.

-- Creating the foreign key to documents takes a SHARE ROW EXCLUSIVE lock on it, which
-- waits for and then briefly blocks writers (not readers). Fail after 2 s rather than
-- queue behind a long publish; rerun when it clears. LOCAL ends with this transaction.
SET LOCAL lock_timeout = '2s';

-- One row per node, in pre-order: a parent always precedes its children, and the
-- ordinals of a subtree are contiguous.
CREATE TABLE document_contents (
    document_id    uuid     NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal        integer  NOT NULL CHECK (ordinal > 0),
    parent_ordinal integer,
    depth          smallint NOT NULL CHECK (depth >= 0),
    -- Unique within the document and stable across builds (a source div id or a
    -- heading path), so clients can remember expanded branches.
    node_key       text     NOT NULL,
    -- "part", "treatise", "section", "chapter", "article", "question", "prologue" or
    -- "heading". Checked by the datapipeline (contents.KINDS), not here, so a new kind
    -- needs no migration.
    kind           text     NOT NULL,
    label          text     NOT NULL,
    short_label    text     NOT NULL,
    chapter_key    text     NOT NULL,
    anchor         text,
    range_label    text,
    PRIMARY KEY (document_id, ordinal),
    UNIQUE (document_id, node_key),
    FOREIGN KEY (document_id, parent_ordinal)
        REFERENCES document_contents (document_id, ordinal) ON DELETE CASCADE,
    CHECK (parent_ordinal < ordinal),
    CHECK ((parent_ordinal IS NULL) = (depth = 0))
);

-- Read by FastAPI (service role, which bypasses RLS) and written by the datapipeline.
-- RLS with no policies plus the revoke keeps it out of the Data API, as 0037 does for
-- document_chapters.
ALTER TABLE document_contents ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE document_contents FROM PUBLIC, anon, authenticated;
