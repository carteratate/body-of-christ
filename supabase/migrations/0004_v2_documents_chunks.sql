-- pgvector extension (enable if not already)
create extension if not exists vector;

-- source documents
create table documents (
    id          uuid        primary key default gen_random_uuid(),
    collection  text        not null
                              check (collection in ('bible', 'catechism', 'church-fathers',
                                                    'encyclicals', 'saints')),
    title       text        not null,
    author      text,
    year        int,
    metadata    jsonb,
    created_at  timestamptz not null default now()
);

-- text chunks
create table chunks (
    id                   uuid        primary key default gen_random_uuid(),
    document_id          uuid        not null references documents(id) on delete cascade,
    content              text        not null,
    position             int         not null,
    reference            text,
    content_embedding    vector(1536),
    search_vector        tsvector    generated always as
                           (to_tsvector('english', content)) stored,
    -- option c stubs (null until annotation batch job runs)
    annotation           jsonb,
    annotation_embedding vector(1536),
    created_at           timestamptz not null default now()
);

-- hnsw vector index (faster queries, no rebuild needed as data grows)
create index chunks_content_embedding_idx on chunks
    using hnsw (content_embedding vector_cosine_ops)
    with (m = 16, ef_construction = 64);

-- full-text index
create index chunks_search_vector_idx on chunks using gin (search_vector);

-- for collection-filtered queries
create index chunks_document_id_idx on chunks (document_id);
create index documents_collection_idx on documents (collection);

alter table documents enable row level security;
create policy "authenticated read documents"
    on documents for select
    using (auth.role() = 'authenticated');

alter table chunks enable row level security;
create policy "authenticated read chunks"
    on chunks for select
    using (auth.role() = 'authenticated');
