-- Migration 0013: passage contract columns on chunks
-- Adds the canonical-passage fields shared by the reader and search pipelines.
-- See docs/superpowers/specs/2026-06-13-passage-contract-design.md §3.1
-- Additive only: new nullable columns + indexes. Existing rows keep NULLs until re-ingest.

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS anchor        text;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS chapter_key   text;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS chapter_label text;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS unit_label    text;

-- Deep-link target: unique per document. Partial so existing NULL-anchor rows are unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS chunks_document_anchor_uniq
  ON chunks (document_id, anchor)
  WHERE anchor IS NOT NULL;

-- Reader chapter-section query path (group a document's passages by chapter, in order).
CREATE INDEX IF NOT EXISTS chunks_document_chapter_pos_idx
  ON chunks (document_id, chapter_key, position);
