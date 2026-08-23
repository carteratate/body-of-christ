# TheoCorpus

TheoCorpus publishes a Catholic theological corpus for passage retrieval and reading.

## Language

**Source adapter**:
Converts one collection's source material into canonical Documents and Passages.
_Avoid_: Ingester, scraper

**Collection publication**:
Reconciles one collection's canonical Passages into the reader store and search index.
_Avoid_: Ingestion, load, embed

**Reader store**:
The Supabase/Postgres representation used for reading and full-text passage retrieval.
_Avoid_: Database, corpus database

**Search index**:
The Qdrant representation containing passage vectors and search payloads.
_Avoid_: Vector database, pgvector store

**Passage**:
The shared corpus unit whose stable identity joins a reader-store chunk to its search-index point.
_Avoid_: Chunk, result
