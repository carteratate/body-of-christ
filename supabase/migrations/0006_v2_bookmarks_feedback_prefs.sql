-- bookmarks
create table bookmarks (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null references auth.users(id) on delete cascade,
    chunk_id    uuid        not null references chunks(id) on delete cascade,
    created_at  timestamptz default now(),
    unique (user_id, chunk_id)
);

alter table bookmarks enable row level security;

create policy "users own their bookmarks"
    on bookmarks for all
    using (auth.uid() = user_id);

-- chunk feedback (thumbs up/down)
create table chunk_feedback (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null references auth.users(id) on delete cascade,
    chunk_id    uuid        not null references chunks(id) on delete cascade,
    feedback    text        not null check (feedback in ('up', 'down')),
    search_id   uuid,
    created_at  timestamptz default now(),
    unique (user_id, chunk_id)
);

alter table chunk_feedback enable row level security;

create policy "users own their feedback"
    on chunk_feedback for all
    using (auth.uid() = user_id);

-- user preferences
create table user_preferences (
    user_id                uuid        primary key
                                         references auth.users(id) on delete cascade,
    preferred_translation  text        default 'CPDV',
    default_collections    text[]      default
                                         '{bible,catechism,church-fathers,encyclicals,saints}',
    default_quota          int         default 4 check (default_quota between 3 and 5),
    created_at             timestamptz default now(),
    updated_at             timestamptz default now()
);

alter table user_preferences enable row level security;

create policy "users own their preferences"
    on user_preferences for all
    using (auth.uid() = user_id);
