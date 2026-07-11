-- guest_trials is backend-owned. Enabling RLS without client policies denies
-- anon/authenticated access while the service role continues to bypass RLS.
ALTER TABLE public.guest_trials ENABLE ROW LEVEL SECURITY;
