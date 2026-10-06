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

Approved downloads that no PR has ingested yet wait in `sources/_incoming/<path>`, where `<path>` is the file's final place under `sources/` (R6's "Vendored as" column). No adapter reads `_incoming/`. The ingesting PR moves the file unchanged to `sources/<path>` and runs `python3 scripts/source_lock.py --write`, which keeps the file's download date and URL because its hash matches the `_incoming/` entry. Carter chose this on 5 Oct 2026 because the church-fathers adapter builds every `*.xml` in its folder, so a file dropped there early would be published ahead of its PR.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in the Supabase, Qdrant, and OpenAI values.
```

## Publish one collection

**The publish lock.** Every command that writes to the live reader tables or Qdrant
first checks `PUBLISH_LOCK.json`. It ships with an empty `approved_applies` list, so a
live publish exits with code 2 and a "locked" message. A write is allowed only when a
reviewed PR has added an entry naming the collection, the release and the step
(`stage`, `apply`, `rollback` or `repair`), and the command passes the same
`--collection` and `--release`. Runs whose database and Qdrant both point at this
machine (`localhost`, `127.0.0.1` or `::1`) are rehearsals and need no entry. No flag
or environment variable skips the lock. See item 0.4 in
`docs/corpus-cleanup/P0-checks-identity-research.md`.

To check a collection without writing anything, use the dry run. It builds the
Documents, runs the document checks and prints the counts, and needs no lock entry:

```bash
python run_collection.py --collection catechism --dry-run
```

The dry run still needs the required environment variables set, because the adapters
import `config`, but any values will do: nothing connects. The loopback exemption
trusts the hostname, so a `localhost` URL that is an SSH tunnel or port forward to
Supabase or Qdrant counts as a rehearsal. Don't point a local URL at production.

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

The document checks include the health block rules in `health.py` (item 0.1b): blank
text, page-number or punctuation debris, positions that are not `0..n-1`, duplicate
anchors, and an empty anchor, chapter key or chapter label. Any of them refuses the
build, dry run included, before a store is opened, unless that exact passage is listed
in `checks/known_defects.json` with the PR that fixes it. `pipeline.py` applies the same
rules to the documents it parses before its `reader` or `embed` stage writes them. `python3 -m checks.health
--collection <name>` reports the block rules and the softer report rules (short
fragments, footer and note leakage, duplicated text, joined paragraphs, non-English
text); their patterns are in `health_patterns.json`.

Writing a Document to the reader store also rebuilds its **reader outline** (chapter
list and passage count, `supabase/migrations/0037_document_outline.sql`) in the same
transaction, so the target database must have migration 0037 applied before publishing.

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

Their `--apply` mode is a live write, so it needs a publish-lock entry with step
`repair` for the collection (or `all`) and `--release <the entry's release>`. The same
applies to the V5 `pipeline.py` stages that write live data (`reader`, `embed`,
`bm25-index`, and `enrich` without `--sample`). Dry runs, `--status` and sample runs
need no entry.

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
