-- compare_runs is an internal benchmarking table with no user_id column.
-- All access goes through the FastAPI service role key, which bypasses RLS.
-- Enabling RLS with no policies denies anon/authenticated PostgREST access, which is correct.
ALTER TABLE public.compare_runs ENABLE ROW LEVEL SECURITY;
