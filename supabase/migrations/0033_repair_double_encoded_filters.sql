-- supabase/migrations/0033_repair_double_encoded_filters.sql
-- Repair `filters` rows stored as jsonb *strings* instead of jsonb objects.
--
-- Cause: app/db.py registers a jsonb codec (encoder=json.dumps), so asyncpg
-- serialises jsonb parameters itself. Call sites that also called json.dumps
-- before binding therefore encoded twice, storing
--   "{\"collections\": [...], \"translation\": \"CPDV\", \"quota\": 5}"
-- (a JSON string) rather than an object. The read path in routes/search.py
-- compensated with a json.loads fallback, so the bug was invisible from the
-- app while making the column unusable from SQL: `filters->'collections'`
-- returned NULL, so collections could not be queried, indexed or aggregated.
--
-- The write sites are fixed in the same change (rag/pipeline.py,
-- routes/guest_search.py, rag/compare/persist.py now pass plain objects).
-- This migration repairs the rows those sites already wrote.
--
-- `#>> '{}'` extracts the jsonb string's text, which is then re-parsed as
-- jsonb. Rows already stored as objects are left untouched by the WHERE.
UPDATE searches
   SET filters = (filters #>> '{}')::jsonb
 WHERE jsonb_typeof(filters) = 'string';

UPDATE guest_trials
   SET filters = (filters #>> '{}')::jsonb
 WHERE jsonb_typeof(filters) = 'string';
