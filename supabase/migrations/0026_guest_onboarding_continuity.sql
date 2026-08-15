-- Persist the two-search guest onboarding session long enough to transfer its
-- searches and selected passages to a newly authenticated account.

ALTER TABLE public.guest_trials
    ADD COLUMN IF NOT EXISTS session_token_hash text,
    ADD COLUMN IF NOT EXISTS query text,
    ADD COLUMN IF NOT EXISTS filters jsonb,
    ADD COLUMN IF NOT EXISTS result_count integer,
    ADD COLUMN IF NOT EXISTS completed_at timestamptz,
    ADD COLUMN IF NOT EXISTS claimed_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS claimed_at timestamptz;

CREATE INDEX IF NOT EXISTS guest_trials_session_token_hash_idx
    ON public.guest_trials (session_token_hash, created_at);

CREATE TABLE IF NOT EXISTS public.guest_trial_retrievals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    guest_trial_id uuid NOT NULL REFERENCES public.guest_trials(id) ON DELETE CASCADE,
    chunk_id uuid NOT NULL REFERENCES public.chunks(id) ON DELETE CASCADE,
    rank integer NOT NULL,
    reranker_score double precision,
    explanation text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (guest_trial_id, chunk_id)
);

CREATE INDEX IF NOT EXISTS guest_trial_retrievals_trial_idx
    ON public.guest_trial_retrievals (guest_trial_id, rank);

ALTER TABLE public.guest_trial_retrievals ENABLE ROW LEVEL SECURITY;

-- Both guest tables are backend-owned. With RLS enabled and no client policy,
-- browser database clients cannot read or mutate temporary onboarding data.
