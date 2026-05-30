-- chat_sessions
create table chat_sessions (
    id          uuid        primary key default gen_random_uuid(),
    user_id     uuid        not null references auth.users(id) on delete cascade,
    title       text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

alter table chat_sessions enable row level security;

create policy "users own their sessions"
    on chat_sessions for all
    using (auth.uid() = user_id);


-- chat_messages
create table chat_messages (
    id          uuid        primary key default gen_random_uuid(),
    session_id  uuid        not null references chat_sessions(id) on delete cascade,
    user_id     uuid        not null references auth.users(id) on delete cascade,
    role        text        not null check (role in ('user', 'assistant')),
    content     text        not null,
    created_at  timestamptz not null default now()
);

alter table chat_messages enable row level security;

create policy "users own their messages"
    on chat_messages for all
    using (auth.uid() = user_id);


-- keep updated_at current on chat_sessions
create or replace function update_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create trigger chat_sessions_updated_at
    before update on chat_sessions
    for each row execute procedure update_updated_at();
