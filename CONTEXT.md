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

**My Passages**:
A person's private list of source Passages they have saved for later, with optional private notes.
_Avoid_: Collection

**Study**:
A person-authored work that places source Passages and original writing in a chosen order.
_Avoid_: Collection

**Study block**:
One ordered part of a Study: original writing or an occurrence of a source Passage with its own optional heading and commentary.
_Avoid_: Bookmark

**Published version**:
A fixed, publicly readable form of a Study or saved Passage as it appeared when its owner chose to publish it.
_Avoid_: Live share
