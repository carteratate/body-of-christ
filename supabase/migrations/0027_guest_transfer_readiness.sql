-- A guest search is transferable only after its post-result relevance
-- explanations have finished persisting. This separates user-visible result
-- completion from account-transfer readiness.

ALTER TABLE public.guest_trials
    ADD COLUMN IF NOT EXISTS transfer_ready_at timestamptz,
    ADD COLUMN IF NOT EXISTS transfer_failed_at timestamptz,
    ADD COLUMN IF NOT EXISTS transfer_pending_at timestamptz,
    ADD COLUMN IF NOT EXISTS transfer_lease_until timestamptz;

CREATE INDEX IF NOT EXISTS guest_trials_transfer_ready_idx
    ON public.guest_trials (session_token_hash, transfer_ready_at)
    WHERE claimed_by IS NULL;
