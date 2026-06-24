-- Add per-user daily rate limit columns for the /v1/evaluate endpoint.
-- Nullable date: NULL means no evaluations yet today. Count defaults to 0.
alter table user_usage
  add column evaluate_date date default null,
  add column evaluate_count integer default 0;
