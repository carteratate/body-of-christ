# TheoCorpus collection publication

The non-V5 data pipeline turns source material into canonical `Document` and
`Passage` objects, then reconciles one collection into two stores:

- The **reader store** is Supabase/Postgres. It holds Documents and Passages for
  reading, full-text retrieval, bookmarks, and search history.
- The **search index** is Qdrant. It holds Passage vectors and search payloads.

`run_collection.py` is the sole supported non-V5 publication interface. Source
adapters build domain objects; they do not write to either store directly.

## Source data

Source files are required before publication. Provenance and acquisition instructions
for all ten collections live in [`SOURCES.md`](SOURCES.md). The adapters registered in
`publication.py` are:

| Collection | Source adapter |
|---|---|
| `apostolic-exhortations` | `ingest/apostolic_exhortations.py` |
| `bible` | `ingest/bible.py` |
| `canon-law` | `ingest/canon_law.py` |
| `catechism` | `ingest/catechism.py` |
| `church-fathers` | `ingest/church_fathers.py` |
| `councils` | `ingest/councils.py` |
| `encyclicals` | `ingest/encyclicals.py` |
| `medieval` | `ingest/medieval.py` |
| `papal-documents` | `ingest/papal_documents.py` |
| `summa` | `ingest/summa.py` |

Vendored adapters read local files under `sources/<collection>/`; they do not fetch
from source websites during publication. Acquire missing vendored sources separately:

```bash
python scripts/vendor_sources.py --collection all
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in the Supabase, Qdrant, and OpenAI values.
```

## Publish one collection

Routine publication safely upserts Documents and Passages before pruning stale records
from each selected store:

```bash
python run_collection.py --collection bible --target both
```

Use `--target reader` or `--target search` when repairing only one store. A limited
publication is useful for local validation and disables collection-wide pruning:

```bash
python run_collection.py --collection catechism --target reader --limit 1
```

The runner refuses suspicious build collapse and identity churn before writes. A
routine publication retains stable Passage identities, preserving bookmarks and search
history for Passages the adapter still emits.

### Reset the search index

Routine search publication is incremental. Use the explicit reset only when replacing
the selected collection's Qdrant points is intentional:

```bash
python run_collection.py --collection bible --target search --reset-search-index
```

### Wipe the reader store

A reader wipe deletes the collection's reader-store records and can cascade into
user-owned data. It requires the collection name twice, with an exact match:

```bash
python run_collection.py \
  --collection bible \
  --target reader \
  --wipe-reader \
  --confirm-reader-wipe bible
```

## Narrow repair commands

Prefer the target-specific repair tools when a full collection publication would do
unnecessary work. They dry-run by default; inspect each command's `--help` before
authorizing writes.

```bash
python scripts/backfill_missing_vectors.py --collection bible
python scripts/reembed_drifted_vectors.py --collection bible
python scripts/reconcile_qdrant_payloads.py --collection bible
```

These repair tools use the same canonical source-adapter registry as collection
publication. They do not make the retired Postgres `content_embedding` column active;
all searchable vectors live in Qdrant.

## Tests

The non-V5 suite is local and uses fakes for store and embedding boundaries:

```bash
python -m pytest -q
```

The `stages/` pipeline is the separate V5 experiment. Its similarly named embedding
stage is outside the non-V5 publication interface described here.
