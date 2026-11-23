# TheoCorpus collection publication

The non-V5 data pipeline turns source material into canonical `Document` and
`Passage` objects, then publishes them into two stores:

- The **reader store** is Supabase/Postgres. It holds Documents and Passages for
  reading, full-text retrieval, bookmarks, and search history.
- The **search index** is Qdrant. It holds Passage vectors and search payloads.

`publish.py` is the one publish path (plan D2); `run_collection.py` only dry-runs.
Source adapters build domain objects; they do not write to either store directly.

## Source data

Source files are required before publication. Provenance and acquisition instructions
for all ten sources live in [`SOURCES.md`](SOURCES.md). `publication.py` registers each
source's adapter in `SOURCE_BUILDS`, and the eight collections a publish writes in
`SOURCE_ADAPTERS` (corpus cleanup 5.1b.3, `collection_keys.py`):

| Collection (published) | Sources (`sources/<key>/`) | Source adapter |
|---|---|---|
| `bible` | `bible` | `ingest/bible.py` |
| `catechism` | `catechism` | `ingest/catechism.py` |
| `church-fathers` | `church-fathers`, and Boethius from `medieval` | `ingest/church_fathers.py`, `ingest/medieval.py` |
| `church-law` | `canon-law` | `ingest/canon_law.py` |
| `councils` | `councils` | `ingest/councils.py` |
| `papal` | `encyclicals`, `apostolic-exhortations`, `papal-documents` | `ingest/encyclicals.py`, `ingest/apostolic_exhortations.py`, `ingest/papal_documents.py` |
| `summa` | `summa` | `ingest/summa.py` |
| `theologians` | `medieval` (all but Boethius) | `ingest/medieval.py` |

A source keeps its old name: the work registry files each frozen ID under it, the checks
(0.1a to 0.1c) and their known defects are keyed by it, and the embedding overlap follows
it, so the rename moves no ID and changes no vector. Until 5.1b.3's publish is applied,
live rows carry the old keys; a stage, report or apply of a new key also covers the live
rows under each old key that becomes it (`collection_keys.live_keys`). Until then, stage
`church-fathers` together with `theologians`: Boethius moves between them.

Vendored adapters read local files under `sources/<collection>/`; they do not fetch
from source websites during publication. Acquire missing vendored sources separately:

```bash
python scripts/vendor_sources.py --collection all
```

Approved downloads that no PR has ingested yet wait in `sources/_incoming/<path>`, where `<path>` is the file's final place under `sources/` (R6's "Vendored as" column). No adapter reads `_incoming/`. The ingesting PR moves the file unchanged to `sources/<path>` and runs `python3 scripts/source_lock.py --write`, which keeps the file's download date and URL because its hash matches the `_incoming/` entry. Carter chose this on 5 Oct 2026 because the church-fathers adapter builds every `*.xml` in its folder, so a file dropped there early would be published ahead of its PR.

The three papal adapters build an older document from its public-domain printing instead of its papalencyclicals.net page when `ingest/papal_printings.json` names one (1.3d): the printing's file, URL, and which site paragraph each printed block is, checked with `python3 scripts/align_editions.py --collection <c> --printings`.

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

**Publishing goes through `publish.py`** (item 2.2w, plan D2). A publish never writes
straight into the live tables. It builds into staging, compares that with live, then
moves it into live in one transaction:

```bash
python3 publish.py stage    --collection bible --release 2026-12-bible   # or --collection all
python3 publish.py report   --release 2026-12-bible
python3 publish.py apply    --release 2026-12-bible    # also switches the alias
python3 publish.py cleanup  --release 2026-12-bible    # once the apply is checked

python3 publish.py status   [--release 2026-12-bible]
python3 publish.py switch   --release 2026-12-bible    # after apply --no-switch
python3 publish.py rollback --release 2026-12-bible    # undo an applied publish
python3 publish.py discard  --release 2026-12-bible    # abandon a publish never applied

# After the 14-day rollback window (4.1b step 13); each is a dry run without --execute
python3 publish.py purge-retired       --release republish-2026-10 [--execute --disk-free-gb <GB>]
python3 publish.py drop-old-collection --release republish-2026-10 [--execute --confirm <name>]
```

The release name is the publish ID: `corpus_publishes.id`, the lock entry's `release`,
and the suffix of `chunks-<release>`. Use 3 to 63 lowercase letters, digits and hyphens.
The lock entry's steps are `stage` for `stage` and `discard`, `apply` for `apply`,
`switch`, `cleanup` and a live `purge-retired` or `drop-old-collection`, and `rollback`
for `rollback`. Those two work across the whole corpus, so only an `all` entry for the
release approves them. `status` only reads. `report` reads
too, but recording a passing report's hash needs the release's `stage` approval.

Keep `DATABASE_URL` on a direct or session-mode connection (Supabase's pooler on port
5432). `switch` and `rollback` hold a session-level advisory lock across statements,
which transaction mode (port 6543) could leave held on a pooled connection.

- `stage` builds the collections and writes them into the `staging` schema (migrations
  0042 and 0043; the live tables' shape, no foreign keys) and a new Qdrant collection
  `chunks-<release>` that no alias points at. Users read neither. The Qdrant alias
  `chunks_live` must exist: the stage copies the collections it does not build, and
  unchanged vectors, from the alias's target. Passage IDs come from the passage registry
  (D1); a stage stops on any live ID it drops that no open removal entry or redirect in
  `registry/` explains (D4), and turns each explained one into a staged tombstone or
  redirect. Vectors come from the embedding cache (`cache.db`), then from the live point
  with the same `embed_sha256`, then OpenAI, and a new vector goes into the cache before
  its point is written, so restaging an unchanged build costs nothing.
  `QDRANT_WRITE_COLLECTION` overrides the collection name for a local run.
- `report` runs the release report (below) on the staged corpus against a fresh
  read-only export of live, adds the publish checks (every live ID kept or explained,
  points and payload facts equal to staging, embedding input hashes, dedup collision
  rates, the document-facts diff, user impact, staging size), and records its hash for
  the apply. It writes to `releases/local/publish-<release>-<time>/`.
- `apply` writes the before-snapshot to `releases/snapshots/<release>-before/` (corpus
  text, gitignored), then in one transaction updates, inserts and retires (it never
  deletes), writes tombstones and redirects, moves the user rows on redirected IDs
  (4.1a, below), and refreshes outlines. It then switches `chunks_live` to the publish's
  collection, unless `--no-switch`. It refuses a staged corpus that no longer matches the
  report's hash. It prints the remap's public counts for the publish log.
  `--retire-only --collection <name>` retires the documents an open `document` removal
  entry names, with nothing staged.
- `switch` moves the alias after `apply --no-switch`. Qdrant applies the move atomically.
- `rollback` is the only rollback path (D11). Within the 14-day rollback window (it refuses
  after it, since step 13 may have deleted what it would restore) it undoes
  an applied publish from its before-snapshot in one transaction, retires every row the
  publish inserted under a `rolled-back` tombstone, moves user rows back from the remap's
  ledger, then points the alias back. Roll back
  the latest publish first. It works after `cleanup`, and leaves staging loaded, so run
  `cleanup` again afterwards.
- `cleanup` drops the staging tables and returns their space. Run it once the apply is
  checked.
- `discard` drops the staging tables of a publish that was never applied.

User rows on redirected IDs (4.1a, `remap_user_data.py`). Bookmarks, saved search
results, labels, guest results, feedback and reading positions on an ID, anchor or
chapter with a redirect move to its target inside the apply. Where two of a user's rows
meet on one passage, one is kept by a fixed rule (the module docstring lists them) and
the other is recorded. The record, the ledger, holds user IDs and note text: it is
written to `user_remap_ledger.jsonl` in the before-snapshot folder, its sha256 joins the
snapshot's, and it is never committed. `rollback` undoes only what the ledger recorded,
keeps every change a user made since the apply, and counts each row it skips instead of
failing. `python3 -m remap_user_data --dry-run [--rows]` prints what the apply would move
for the staged publish, in a read-only transaction.

After the rollback window for a publish that was applied (`retention.py`, 4.1b step 13):

- `purge-retired` deletes retired passages and documents that nothing points at (D3).
  It reads the foreign keys into `chunks` and `documents` from the database, and keeps a
  retired row that any row outside the corpus tables points at (a later table included),
  that a corpus row's `superseded_by` names, that sits in the chapter a reading position
  names (it labels the position), or whose removal reason holds the text for
  its return (`awaiting-permission`, `translation-in-preparation`; ADR 0001). The dry run
  lists the keys, what would go, what stays and why, and an upper estimate of the
  transaction log the deletes and the `VACUUM` after them write. A live run works in
  batches of 1,000, each its own transaction under the publish lock: it locks its rows,
  checks the references again, copies each passage's anchor and chapter key into its
  tombstone's snapshot (the API's notice for an old reader link reads them), deletes,
  and refreshes the touched documents' outlines. It refuses inside any publish's
  rollback window, while staging is held, and unless `--disk-free-gb`, read from the
  Supabase dashboard (Database -> Disk) just before, covers twice its WAL estimate plus
  1 GB. Run `VACUUM (analyze) chunks` afterwards, after the same disk check.
- `--close-window-early "<who, when>"` on either command closes the release's own
  rollback window before its 14 days, by a recorded decision (the republish's, Carter,
  21 Nov 2026). It lifts that one refusal; every other refusal, the lock and the disk
  check stay. Each output then opens with an `EARLY CLOSE:` line naming the decision; log
  it on the release's issue. After the old collection is gone, `rollback` refuses.
- `drop-old-collection` deletes the Qdrant collection the publish's switch moved the
  alias away from, once no alias or publish uses it. It cannot be undone, so it needs
  `--confirm` with the collection's name.
- Deleting the before-snapshot (and its ledger) and any backups is by hand, and the lock
  entry is removed by a follow-up PR.

No other code path in the datapipeline deletes a chunk or document row, and nothing
deletes a live one.

**Reading a staged corpus.** With `CORPUS_READ_SCHEMA=staging`, a process that imports
the API reads the staged corpus with no write access: its pool sets `search_path` to
`staging, public` and `default_transaction_read_only` on each time it hands out a
connection, and refuses a connection those settings do not hold on, or a database with no
staged corpus. The API server itself
refuses to start with anything but `public`, so this is for in-process runs such as the
pre-cutover checks (item 4.2). It covers Postgres only: point vector search at the staged
collection with `QDRANT_READ_COLLECTION=chunks-<release>` (item 2.2b).

The document checks include the health block rules in `health.py` (item 0.1b): blank
text, page-number or punctuation debris, positions that are not `0..n-1`, duplicate
anchors, and an empty anchor, chapter key or chapter label. Any of them refuses the
build, dry run included, before a store is opened, unless that exact passage is listed
in `checks/known_defects.json` with the PR that fixes it. `pipeline.py` applies the
same rules to every collection it parses before an `embed` or full `enrich` stage
runs, dry run included. `python3 -m checks.health --collection <name>` reports
the block rules and the softer report rules (short fragments, footer and note leakage,
duplicated text, joined paragraphs, non-English text); their patterns are in
`health_patterns.json`.

The release report (item 0.1c) compares a build with what users see today.
`scripts/export_live_snapshot.py` copies the live corpus and anonymous counts of saved
user rows to `releases/snapshots/<date>/`, read only and with Carter's approval for each
run; the snapshot holds in-copyright text, so that directory is gitignored and only the
hash index `releases/snapshots.json` is tracked. `python3 -m release.report --snapshot
releases/snapshots/<date> --collection <name>` then maps every live passage to one
outcome (`same`, `moved`, `split`, `merged`, `renumbered`, `removed`, defined in
`release/remap.py`), fails when a passage ID would show different text, and counts the
saved rows each outcome touches. Its `report.md` holds no passage text unless run with
`--no-public`. A passage moved to another collection is found only when both collections
are in the run; `--collection all` covers every move.

Excerpt-only passages from vatican.va link to their opening words on the page with a text
fragment (item 2.4e, `services/api/app/source_links.py`). `python3 -m checks.source_links`
looks for every fragment in the vendored page, reading the live passages read-only, and
reports the miss rate; with `--write` it rewrites `services/api/app/source_link_misses.json`,
the passages that keep the plain URL. Rerun it with `--write` right after the apply (it reads
live passages), in a small PR, whenever a publish changes passages of a document whose `metadata.url` is on
vatican.va: a new passage the list does not know gets a fragment that may not match, which
opens the page at the top, as before 2.4e.
A PR that moves documents onto vatican.va (1.3c) checks them before their publish with
`--build <collection> --source-key <key> ... --write`: it reads those documents from the
build, under the passage IDs they will carry live, and replaces only their entries, kept
under `from_build`. A live `--write` keeps the `from_build` entries it does not read, so the
list holds them until the documents are live on vatican.va and the live run takes over.

An adapter change that moves passage boundaries updates the passage registry (2.1) in the
same PR: `python3 scripts/reconcile_registry.py --item <id> --collection <name>
--snapshot releases/snapshots/<date>` adds a row for each new piece, redirects each live
piece whose opening paragraph no longer opens one, and gives a piece whose text moved
elsewhere a new ID with a redirect. A piece that keeps its opening words but scores under
the stability threshold is listed as a problem until a person checks it and reruns with
`--kept-reason`, which records it in `registry/kept_text.json`. A passage whose metadata
declares `text_replaced` (a new translation, an amended canon) is not held to its live text,
as in the release report.

Each document's facts (genre, issuer, year and display date, translation, source credit,
notes; 2.3) live on its `registry/works.json` entry, and the build sets them on the
Document over the adapter's values. They are derived, not typed by hand: after a change to
an adapter's year or notes, a papal genre, a rights row's credit line or a rule in
`document_facts.py`, run `python3 scripts/document_facts_registry.py` (needs the sources)
and commit `works.json`. A source check fails while the two disagree. After a merge of
master, rerun it rather than merging `works.json` facts by hand.

A papal document whose text moves to another edition (1.3c, 1.3d) is aligned with its old
one first: `python3 scripts/align_editions.py --collection <name> [--slug <slug>] --out
<file>` pairs the two editions' paragraphs by the names, numbers and rarer words they
share, and lists every place where that pairing differs from their numbering, for a person
to review. The reviewed result goes into `ingest/papal_anchors.json` (which live anchor a
built paragraph carries) and the redirects; the alignment itself reads both editions by
their own numbering.

A stage also builds each staged document's **reader outline** (chapter list and passage
count, `supabase/migrations/0037_document_outline.sql`) in staging with
`staging.refresh_document_outline`, so the pre-cutover checks read staging as they will
read live.

A Document can also carry a **contents tree** (`Document.contents`, the hierarchy of its
headings; `contents.py`, issue #250). The build refuses a tree that opens a chapter the
document lacks, names an anchor outside its chapter, repeats a key or meets chapters out
of reading order, and a dry run prints each tree's node count and any chapter no node
opens. The stage writes the tree into `staging.document_contents` with the passages, and
a document whose adapter stops emitting a tree loses its staged rows.

## Narrow repair commands

Prefer a publish for a change to a collection's text or structure: it writes Postgres
and Qdrant from one staging build. These tools fix one store's drift in place. They
dry-run by default, and a dry run reads `QDRANT_WRITE_COLLECTION` if it is set, otherwise
the alias `chunks_live`. Inspect each command's `--help` before authorizing writes.

```bash
python scripts/backfill_missing_vectors.py --collection bible
python scripts/reembed_drifted_vectors.py --collection bible
python scripts/reconcile_qdrant_payloads.py --collection bible
```

Their `--apply` mode is a live write. It needs a publish-lock entry with step `repair`
for the collection (or `all`), `--release <the entry's release>`, and
`QDRANT_WRITE_COLLECTION` naming the Qdrant collection to write, which has no default.
The V5 `pipeline.py` stages `embed` and `bm25-index` need the same entry and setting;
`enrich` without `--sample` needs the entry, and writes only annotations. Dry runs,
`--status` and sample runs need no entry. The V5 `reader` stage is retired: it cleared
and rewrote a live collection, which D2 forbids.

These repair tools use the same canonical source-adapter registry as a publish. They do not make the retired Postgres `content_embedding` column active;
all searchable vectors live in Qdrant.

## Reader access (excerpt-only documents)

`documents.reader_access` (migration 0041, issue #265) decides whether a document's full
text is offered in the reader. It is derived from `rights_inventory.json` and never
edited by hand: `full` for a `pd-*` status, `permission` or `licence`; `excerpt` for
`in-copyright` or `unknown`, and for any document with no inventory row. An excerpt-only
document keeps its passages in search; the API refuses its reader and contents with 403
`reader_restricted`, and the frontend links to its official source instead.

Every stage sets the column from the inventory in `staging.documents`, so a republish can
never reopen an uncleared text (D12). To apply an inventory change without republishing,
which is how a document is unblocked:

```bash
python3 reader_access.py           # dry run: lists every document that would change
python3 reader_access.py --apply   # writes them in one transaction
```

A document whose live URL differs from its row's `source_url` is listed as held and made excerpt-only, even if it is open now: its row describes the edition a coming publish brings.

The sync writes nothing but this one derived column, so unlike the repair tools above
it needs no publish-lock entry. Its `--apply` is still a live change: run the dry run
first and get Carter's go-ahead. The API reads the column fresh on every request, so no
cache needs clearing.

## Scanned works (OCR clean-up and gate)

`ocr/` turns a scanned book's OCR into usable text and gates it (item 1.2f). A work is a
config in `ocr/works/<work>.json`; everything derived from the scan goes to the
gitignored `ocr_work/<work>/`. It reads the scan's `_djvu.xml` and `_page_numbers.json`,
vendored through `sources/_incoming/` like any approved download.

```bash
python3 -m ocr clean   <work>      # remove page furniture, mend broken words, write passages
python3 -m ocr correct <work>      # model correction: calls the provider and spends money
python3 -m ocr sample  <work>      # draw the person's check, once, with a recorded seed
python3 -m ocr check   <work> <passage> matches --by NAME
python3 -m ocr gate    <work>      # writes ocr_work/<work>/gate.md and check.md
```

`correct` stops before any call that could take the work past its config's
`ceiling_usd`, counting earlier runs. Only public-domain scan text goes to the provider.
The OCR writes nothing to the live stores; the work's adapter PR uses its text, labels
each passage with `ocr.label.label_passage`, and pastes `gate.md`.

## Tests

The non-V5 suite is local and uses fakes for store and embedding boundaries:

```bash
python -m pytest -q
```

The `stages/` pipeline is the separate V5 experiment. Its similarly named embedding
stage is outside the non-V5 publication interface described here.
