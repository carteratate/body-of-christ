create table user_usage (
    user_id           uuid primary key references auth.users(id) on delete cascade,
    rate_window_start timestamptz not null default now(),
    rate_count        int not null default 0,
    quota_date        date not null default current_date,
    quota_count       int not null default 0
);

alter table user_usage enable row level security;

create policy "users own their usage"
    on user_usage for all
    using (auth.uid() = user_id);
