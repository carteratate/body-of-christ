-- Backfill 'canon-law' into user_preferences rows that were created before
-- migration 0007 added it to the column DEFAULT. The WHERE clause makes this
-- idempotent: rows that already contain 'canon-law' are untouched.

UPDATE user_preferences
SET default_collections = array_append(default_collections, 'canon-law')
WHERE NOT ('canon-law' = ANY(default_collections));
