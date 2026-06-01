-- supabase/migrations/0008_documents_add_translation.sql
-- Adds translation column and corrects the unique constraint on documents.
-- The original UNIQUE(collection, title) was never created in 0004;
-- this migration creates UNIQUE(collection, title, translation) directly.
--
-- translation uses NOT NULL DEFAULT '' so ON CONFLICT detection works for
-- collections without translations (catechism, encyclicals, etc.) where
-- NULL != NULL would otherwise prevent conflict detection.

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS translation text NOT NULL DEFAULT '';

ALTER TABLE documents
  ADD CONSTRAINT documents_collection_title_translation_key
  UNIQUE (collection, title, translation);
