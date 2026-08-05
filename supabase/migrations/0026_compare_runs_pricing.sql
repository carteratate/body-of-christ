-- Preserve the pricing schedule behind each benchmark cost estimate.
-- Existing rows remain NULL and are explicitly reported as historical/unknown.
ALTER TABLE public.compare_runs
    ADD COLUMN IF NOT EXISTS pricing jsonb;

COMMENT ON COLUMN public.compare_runs.pricing IS
    'Snapshot of provider rates used to calculate total_cost and cost_breakdown.';
