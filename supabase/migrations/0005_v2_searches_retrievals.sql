-- searches (must be created before retrievals due to fk)
create table searches (
    id            uuid        primary key default gen_random_uuid(),
    user_id       uuid        not null references auth.users(id) on delete cascade,
    query         text        not null,
    filters       jsonb,
    result_count  int,
    created_at    timestamptz default now()
);

alter table searches enable row level security;

create policy "users own their searches"
    on searches for all
    using (auth.uid() = user_id);

create index searches_user_id_created_at_idx on searches (user_id, created_at desc);

-- retrievals
create table retrievals (
    id              uuid        primary key default gen_random_uuid(),
    search_id       uuid        not null references searches(id) on delete cascade,
    chunk_id        uuid        not null references chunks(id) on delete cascade,
    rank            int         not null,
    reranker_score  float,
    explanation     text,
    created_at      timestamptz default now()
);

create index retrievals_search_id_idx on retrievals (search_id);

alter table retrievals enable row level security;

create policy "users own their retrievals"
    on retrievals for all
    using (
        exists (
            select 1 from searches
            where searches.id = search_id
              and searches.user_id = auth.uid()
        )
    );
