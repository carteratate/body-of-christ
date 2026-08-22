# Summa re-ingest — scope

Applying `d6a0d5d` (comma-less dialectical markers) to the data. Everything below is
measured against dev on 2026-08-22 by building the document with the fixed parser
in-process and diffing it against the live rows.

## What it recovers

**33 articles change.** Two distinct repairs:

| | articles | what is wrong today |
|---|---|---|
| Determination absorbed into the sed contra | **12** | the article has no `I answer that` chunk at all; Aquinas's answer sits inside the preceding passage. These are 12 of the 16 articles whose objections currently render with nothing attached. |
| Sed contra absorbed into the last objection | **21** | e.g. `Objection 5(293)` is really `Objection 5(204) + On the contrary(71)`. The objection's text and its embedding both carry a quoted authority that belongs to the other side of the argument. |

Neither repair is cosmetic: the first is the stitching feature failing on the passages it
exists for, the second pollutes what the reranker reads.

## What changes in the data

```
db chunks       26,750
built chunks    26,783
  new ids           33   appended at article tails
  gone ids           0
  same id, different content   176
document_id     unchanged
```

**Nothing is deleted.** But 176 chunks keep their id and change their content, which is
the part that needs care — see below.

## The hazard: Summa anchors are positional

Anchors are `{chapter_key}/{sub}` with `sub` counting pieces within the article, and
`chunks.id = uuid5(document_id, anchor)`. Insert a recovered passage mid-article and
every later piece shifts down one slot while keeping its id:

```
anchor  before                     after
  /3    On the contrary (1710)  →  On the contrary (231)
  /4    Reply to Objection 1    →  I answer that          ← same id, different passage
  /5    Reply to Objection 2    →  Reply to Objection 1
  /6    Reply to Objection 3    →  Reply to Objection 2
  /7    —                       →  Reply to Objection 3   ← new id
```

So a bookmark, a saved retrieval, or a shared reader link (`?anchor=…`, set in
`ChunkCard.tsx:188`) pointing at `/4` silently starts showing a different passage. Nothing
errors; the text just changes underneath.

Summa is the only collection of the ten with positional anchors — the other nine key on
citations (`can/1055`, `ccc/997`, `zephaniah/3/9`), which are stable under re-chunking.

## Why now is the window

Measured against the 176 chunks that would change content:

| | |
|---|---|
| retrieval rows pointing at them | **0** |
| bookmarks pointing at them | **0** |

The reassignment is currently invisible. That is a property of the corpus being young, not
of the design being safe, and it will stop being true.

## What must NOT be run

`python run_collection.py --collection summa` calls `reader_writer.clear_collection`
**unconditionally** — `--clean` gates only the Qdrant delete. That deletes all 26,750 Summa
chunks and the `documents` row, cascading through `retrievals`, `bookmarks`,
`chunk_feedback` and `guest_trial_retrievals` for the entire collection. The migration
needs a targeted upsert path instead.

## Plan

1. **Postgres** — upsert only the 33 affected articles by id. Needs a small script; the
   existing `upsert_chunk` in `load.py` already does the row-level work, so this is a
   selection problem, not a writing one.
2. **Qdrant** — the tooling already exists and is the reason it was built:
   - `backfill_missing_vectors.py` creates the 33 new points
   - `reembed_drifted_vectors.py` detects and rebuilds the 176 changed vectors
   - `reconcile_qdrant_payloads.py --fields content` syncs the displayed text
   Ordering constraint stands: re-embed before the content sync, or the sync destroys the
   evidence the classifier reads.
3. **Verify** — the 16 no-determination articles should fall to 4, and the new INFO line
   from `4795da3` gives the count directly.

## What this does not fix

Four of the 16 stay broken, and no parser change reaches them:

- **1** — *whether there are waters above the firmament* is phrased "I answer with
  Augustine", not "I answer that".
- **3** — no determination text in the source at all.

## Open decision: re-key the anchors, or keep deferring

Doing this migration on positional anchors works, but it leaves the design in place: every
future Summa re-chunk will silently reassign content under stable ids. Moving Summa to
citation-based anchors would re-key all 26,750 chunks — a much larger cascade, but the
exposure is 0 today and will never be lower.

Not a prerequisite for the 33-article fix. Worth deciding before the ingest-truncation
work (~4,502 chunks across all nine collections), which has the same shape and a much
larger blast radius.
