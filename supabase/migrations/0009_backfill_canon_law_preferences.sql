-- Backfill 'canon-law' into user_preferences rows that were created before
-- migration 0007 added it to the column DEFAULT. The WHERE clause makes this
-- idempotent: rows that already contain 'canon-law' are untouched.
-- The OR default_collections IS NULL branch handles the edge case where the
-- array column was never set (ANY returns NULL for a NULL array).

UPDATE user_preferences
SET default_collections = array_append(default_collections, 'canon-law')
WHERE NOT ('canon-law' = ANY(default_collections))
   OR default_collections IS NULL;
