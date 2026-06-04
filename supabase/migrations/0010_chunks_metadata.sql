-- Migration 0010: chunks.metadata jsonb + collection constraint update

-- 1. Clean up saints data before constraint change (saints collection was never useful)
DELETE FROM chunks WHERE document_id IN (
    SELECT id FROM documents WHERE collection = 'saints'
);
DELETE FROM documents WHERE collection = 'saints';

-- 2. Add metadata column to chunks
-- Used by: Bible (chapter_desc), Catechism (para_start/para_end), Canon Law (can_start/can_end)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS metadata jsonb;

-- 3. Update documents collection CHECK constraint (drop old, add new without saints, add summa)
-- The constraint was named documents_collection_check in migration 0007.
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_collection_check;

ALTER TABLE documents
  ADD CONSTRAINT documents_collection_check
  CHECK (collection IN ('bible', 'catechism', 'church-fathers', 'encyclicals', 'canon-law', 'summa'));

-- 4. Update default for new user_preferences rows (existing rows keep their stored value).
ALTER TABLE user_preferences
  ALTER COLUMN default_collections
  SET DEFAULT '{bible,catechism,church-fathers,encyclicals,canon-law,summa}';
