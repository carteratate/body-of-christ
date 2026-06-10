# Medieval Collection Ingestion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "medieval" corpus collection containing Anselm, Boethius, Bernard of Clairvaux, and Thomas à Kempis, ingested from CCEL ThML files using the existing `parse_thml_string()` infrastructure.

**Architecture:** A manifest-driven `medieval.py` script downloads four ThML XML files from CCEL via httpx, parses each with the existing `parse_thml_string()` from `ingest/common.py`, post-processes Anselm's references (his file contains multiple works so `parse_thml` treats work-titles as "authors"), merges very short chapters for the Imitation of Christ, then upserts documents and chunks to the DB. Collection is registered in constants, frontend collections list, and CSS vars.

**Tech Stack:** Python asyncio, httpx, defusedxml, BeautifulSoup (not needed — ThML only), asyncpg, Next.js/TypeScript (frontend constants only).

---

## File Map

| Action | File | Purpose |
|---|---|---|
| Modify | `services/api/app/rag/constants.py` | Add `"medieval"` to `VALID_COLLECTIONS` |
| Modify | `apps/web/src/lib/collections.ts` | Add medieval entry with label and color var |
| Modify | `apps/web/src/app/globals.css` | Add `--color-collection-medieval` CSS var |
| Create | `datapipeline/ingest/medieval.py` | Ingest script |
| Create | `datapipeline/tests/test_medieval.py` | Unit tests for helper functions |
| Modify | `datapipeline/run_all.py` | Add medieval to PIPELINE |

---

## Task 1: Register "medieval" collection across the stack

**Files:**
- Modify: `services/api/app/rag/constants.py`
- Modify: `apps/web/src/lib/collections.ts`
- Modify: `apps/web/src/app/globals.css`

- [ ] **Step 1: Add to backend constants**

Edit `services/api/app/rag/constants.py` — the complete file after change:

```python
VALID_COLLECTIONS: frozenset[str] = frozenset({
    "bible",
    "catechism",
    "church-fathers",
    "encyclicals",
    "canon-law",
    "summa",
    "medieval",
})
```

- [ ] **Step 2: Add CSS variable**

In `apps/web/src/app/globals.css`, add one line inside the `@theme` block after the `--color-collection-summa` line:

```css
  --color-collection-medieval:       #5A6670;
```

- [ ] **Step 3: Add to frontend collection list**

Edit `apps/web/src/lib/collections.ts`. Add the medieval entry after `summa`:

```typescript
export const COLLECTIONS: CollectionMeta[] = [
  { key: "bible",          label: "📖 Bible",           color: "var(--color-collection-bible)" },
  { key: "catechism",      label: "⛪ Catechism",        color: "var(--color-collection-catechism)" },
  { key: "church-fathers", label: "✝ Church Fathers",   color: "var(--color-collection-church-fathers)" },
  { key: "encyclicals",    label: "📜 Encyclicals",      color: "var(--color-collection-encyclicals)" },
  { key: "canon-law",      label: "⚖️ Canon Law",        color: "var(--color-collection-canon-law)" },
  { key: "summa",          label: "📚 Summa Theologica", color: "var(--color-collection-summa)" },
  { key: "medieval",       label: "🏰 Medieval",         color: "var(--color-collection-medieval)" },
];
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd apps/web && npx tsc --noEmit
```

Expected: no output (clean).

- [ ] **Step 5: Commit**

```bash
git add services/api/app/rag/constants.py apps/web/src/lib/collections.ts apps/web/src/app/globals.css
git commit -m "feat(medieval): register medieval collection in constants and frontend"
```

---

## Task 2: Write tests for helper functions (TDD first)

**Files:**
- Create: `datapipeline/tests/test_medieval.py`

These tests exercise the two non-trivial helpers in `medieval.py` before the script is written, so we know the helpers are correct.

- [ ] **Step 1: Create the test file**

```python
# datapipeline/tests/test_medieval.py
import sys, os
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ingest.medieval import fix_multi_work_refs, merge_short_chunks


# ── fix_multi_work_refs ──────────────────────────────────────────────────────

def test_fix_multi_work_refs_rewrites_work_as_author():
    """Refs like 'Proslogium — Chapter I' become 'Anselm — Proslogium, Chapter I'."""
    chunks = [
        ("content", "Proslogium — Chapter I", 0, {}),
        ("content", "Cur Deus Homo — Book II, Chapter III", 1, {}),
    ]
    fixed = fix_multi_work_refs(chunks, "Anselm")
    assert fixed[0][1] == "Anselm — Proslogium, Chapter I"
    assert fixed[1][1] == "Anselm — Cur Deus Homo, Book II, Chapter III"


def test_fix_multi_work_refs_leaves_correct_refs_alone():
    """Refs already starting with the real author name are not touched."""
    chunks = [("content", "Anselm — Proslogium, Chapter I", 0, {})]
    fixed = fix_multi_work_refs(chunks, "Anselm")
    assert fixed[0][1] == "Anselm — Proslogium, Chapter I"


def test_fix_multi_work_refs_preserves_positions():
    """Position values are passed through unchanged."""
    chunks = [("a", "Work — Ch I", 5, {}), ("b", "Work — Ch II", 6, {})]
    fixed = fix_multi_work_refs(chunks, "Author")
    assert fixed[0][2] == 5
    assert fixed[1][2] == 6


# ── merge_short_chunks ───────────────────────────────────────────────────────

def test_merge_short_chunks_merges_below_min():
    """Two short chunks below min_chars are merged into one."""
    chunks = [
        ("short text A", "Work — Ch I", 0, {"k": "v"}),
        ("short text B", "Work — Ch II", 1, {"k": "v"}),
    ]
    result = merge_short_chunks(chunks, min_chars=100, ceiling=3500)
    assert len(result) == 1
    assert "short text A" in result[0][0]
    assert "short text B" in result[0][0]
    assert result[0][2] == 0  # position reset to 0


def test_merge_short_chunks_does_not_merge_above_min():
    """A chunk at or above min_chars is emitted as-is."""
    long_content = "x" * 500
    chunks = [
        (long_content, "Work — Ch I", 0, {}),
        ("short", "Work — Ch II", 1, {}),
    ]
    result = merge_short_chunks(chunks, min_chars=400, ceiling=3500)
    # First chunk should be separate; short chunk goes into next group
    assert result[0][0] == long_content


def test_merge_short_chunks_respects_ceiling():
    """Accumulated content never exceeds ceiling before flushing."""
    big_content = "x" * 1800
    chunks = [(big_content, f"Work — Ch {i}", i, {}) for i in range(3)]
    result = merge_short_chunks(chunks, min_chars=400, ceiling=3500)
    for content, _, _, _ in result:
        assert len(content) <= 3500 + 200  # allow slight overshoot from joining


def test_merge_short_chunks_reassigns_positions_sequentially():
    """Output positions are 0, 1, 2... regardless of input positions."""
    chunks = [("x" * 50, f"W — Ch {i}", i * 10, {}) for i in range(4)]
    result = merge_short_chunks(chunks, min_chars=300, ceiling=3500)
    positions = [pos for _, _, pos, _ in result]
    assert positions == list(range(len(positions)))
```

- [ ] **Step 2: Run tests, confirm they all FAIL (medieval.py doesn't exist yet)**

```bash
cd datapipeline && .venv/bin/python3 -m pytest tests/test_medieval.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'ingest.medieval'` or similar import error.

- [ ] **Step 3: Commit the test file**

```bash
git add datapipeline/tests/test_medieval.py
git commit -m "test(medieval): add failing tests for fix_multi_work_refs and merge_short_chunks"
```

---

## Task 3: Implement medieval.py

**Files:**
- Create: `datapipeline/ingest/medieval.py`

- [ ] **Step 1: Create the ingest script**

```python
# datapipeline/ingest/medieval.py
"""Medieval theology ingestion.

Downloads ThML XML from CCEL via httpx, parses using parse_thml_string()
from common.py, post-processes references for multi-work files, merges
short chapters, then upserts documents and chunks to the DB.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load import close_pool, get_pool, upsert_chunk, upsert_document
from ingest.common import parse_thml_string

_DELAY = 1.5       # seconds between CCEL requests
_MERGE_MIN = 450   # merge chunks shorter than this many chars
_CEILING = 3500    # hard max chunk size

# Manifest of works to ingest. Each entry:
#   url          — CCEL ThML XML direct URL
#   title        — document title to store in DB (overrides ThML metadata)
#   author       — real author name
#   year         — approximate year of composition
#   fix_author   — True when parse_thml treats work-titles as author labels
#                  (multi-work single-author files like Anselm's basic_works.xml)
#   merge_short  — True to merge consecutive short chapters (Imitation of Christ)
WORKS: list[dict] = [
    {
        "url":        "https://ccel.org/ccel/a/anselm/basic_works.xml",
        "title":      "Proslogium, Monologium, and Cur Deus Homo",
        "author":     "Anselm",
        "year":       1099,
        "fix_author": True,
        "merge_short": False,
    },
    {
        "url":        "https://ccel.org/ccel/b/boethius/consolation.xml",
        "title":      "Consolation of Philosophy",
        "author":     "Boethius",
        "year":       524,
        "fix_author": False,
        "merge_short": False,
    },
    {
        "url":        "https://ccel.org/ccel/b/bernard/loving_god.xml",
        "title":      "On Loving God",
        "author":     "Bernard of Clairvaux",
        "year":       1128,
        "fix_author": False,
        "merge_short": False,
    },
    {
        "url":        "https://ccel.org/ccel/k/kempis/imitation.xml",
        "title":      "Imitation of Christ",
        "author":     "Thomas à Kempis",
        "year":       1441,
        "fix_author": False,
        "merge_short": True,
    },
]


def fix_multi_work_refs(
    chunks: list[tuple[str, str, int, dict | None]],
    real_author: str,
) -> list[tuple[str, str, int, dict | None]]:
    """Rewrite refs produced by multi-author detection back to single-author form.

    parse_thml_string() treats Anselm's file as multi-author because it has
    multiple div1 elements with non-generic titles (Proslogium, Monologium…).
    That produces refs like "Proslogium — Chapter I". This function converts
    those to "Anselm — Proslogium, Chapter I".
    """
    fixed = []
    for content, ref, pos, meta in chunks:
        if " — " in ref and not ref.startswith(real_author):
            work_title, rest = ref.split(" — ", 1)
            new_ref = f"{real_author} — {work_title.strip()}, {rest.strip()}"
            fixed.append((content, new_ref, pos, meta))
        else:
            fixed.append((content, ref, pos, meta))
    return fixed


def merge_short_chunks(
    chunks: list[tuple[str, str, int, dict | None]],
    min_chars: int = _MERGE_MIN,
    ceiling: int = _CEILING,
) -> list[tuple[str, str, int, dict | None]]:
    """Merge adjacent short chunks so no chunk is below min_chars.

    Uses the first accumulated chunk's reference and metadata for the merged
    entry. Respects ceiling: never lets accumulated content exceed it.
    Reassigns positions sequentially starting from 0.
    """
    result: list[tuple[str, str, int, dict | None]] = []
    buf_parts: list[str] = []
    buf_ref: str = ""
    buf_meta: dict | None = None
    buf_len: int = 0
    out_pos: int = 0

    def _flush() -> None:
        nonlocal out_pos, buf_parts, buf_ref, buf_meta, buf_len
        if buf_parts:
            result.append(("\n\n".join(buf_parts), buf_ref, out_pos, buf_meta))
            out_pos += 1
            buf_parts, buf_ref, buf_meta, buf_len = [], "", None, 0

    for content, ref, _, meta in chunks:
        if len(content) >= min_chars:
            _flush()
            result.append((content, ref, out_pos, meta))
            out_pos += 1
        else:
            if buf_len + len(content) > ceiling:
                _flush()
            if not buf_parts:
                buf_ref = ref
                buf_meta = meta
            buf_parts.append(content)
            buf_len += len(content)
            if buf_len >= min_chars:
                _flush()

    _flush()
    return result


async def main(pool) -> None:
    """Download, parse, and upsert all medieval works."""
    total_chunks = 0

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        with tqdm(total=len(WORKS), unit="work", desc="Medieval") as pbar:
            for work in WORKS:
                url = work["url"]
                title = work["title"]
                author = work["author"]
                year = work["year"]

                pbar.set_postfix({"work": title[:30]})

                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                except httpx.HTTPError as exc:
                    print(f"\n  WARNING: Failed to fetch {url}: {exc}", file=sys.stderr)
                    pbar.update(1)
                    time.sleep(_DELAY)
                    continue

                try:
                    doc = parse_thml_string(resp.text)
                except Exception as exc:
                    print(f"\n  WARNING: Failed to parse {title}: {exc}", file=sys.stderr)
                    pbar.update(1)
                    time.sleep(_DELAY)
                    continue

                if not doc.chunks:
                    print(f"\n  WARNING: No chunks from {title}", file=sys.stderr)
                    pbar.update(1)
                    time.sleep(_DELAY)
                    continue

                chunks = list(doc.chunks)

                if work["fix_author"]:
                    chunks = fix_multi_work_refs(chunks, author)

                if work["merge_short"]:
                    chunks = merge_short_chunks(chunks)

                doc_id = await upsert_document(
                    pool,
                    collection="medieval",
                    title=title,
                    translation="",
                    author=author,
                    year=year,
                    metadata={"source_url": url},
                )

                for content, reference, position, meta in chunks:
                    chunk_meta = (meta or {}) | {"source_url": url}
                    await upsert_chunk(pool, doc_id, content, position, reference, metadata=chunk_meta)

                total_chunks += len(chunks)
                pbar.set_postfix({"work": title[:30], "chunks": len(chunks)})
                pbar.update(1)
                time.sleep(_DELAY)

    print(f"  Done. {total_chunks} total chunks written for medieval.")


if __name__ == "__main__":
    async def _run():
        pool = await get_pool()
        try:
            await main(pool)
        finally:
            await close_pool()
    asyncio.run(_run())
```

- [ ] **Step 2: Run the failing tests from Task 2 — they should now pass**

```bash
cd datapipeline && .venv/bin/python3 -m pytest tests/test_medieval.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add datapipeline/ingest/medieval.py
git commit -m "feat(medieval): medieval.py ingest script with ThML download and reference fixing"
```

---

## Task 4: Wire medieval into run_all.py

**Files:**
- Modify: `datapipeline/run_all.py`

- [ ] **Step 1: Add medieval to the PIPELINE list**

In `datapipeline/run_all.py`, add `medieval` to the import and PIPELINE:

```python
from ingest import bible, catechism, canon_law, encyclicals, church_fathers, summa, medieval

PIPELINE: list[tuple[str, object]] = [
    ("bible",          bible),
    ("catechism",      catechism),
    ("canon-law",      canon_law),
    ("encyclicals",    encyclicals),
    ("church-fathers", church_fathers),
    ("summa",          summa),
    ("medieval",       medieval),
]
```

- [ ] **Step 2: Verify run_all.py still imports cleanly**

```bash
cd datapipeline && .venv/bin/python3 -c "import run_all; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add datapipeline/run_all.py
git commit -m "feat(medieval): add medieval to run_all.py pipeline"
```

---

## Task 5: Run ingestion and verify

- [ ] **Step 1: Run medieval ingestion standalone**

```bash
cd datapipeline && .venv/bin/python3 -m ingest.medieval
```

Expected output (approximate):
```
Medieval: 100%|████| 4/4 [work=Imitation of Christ, chunks=NNN]
  Done. NNN total chunks written for medieval.
```

Watch for any `WARNING` lines. If a CCEL URL returns a non-200, the URL may have changed — check the CCEL page and update the manifest.

- [ ] **Step 2: Confirm documents in DB**

```bash
cd datapipeline && .venv/bin/python3 -c "
import asyncio
from load import get_pool, close_pool
async def check():
    pool = await get_pool()
    rows = await pool.fetch(\"SELECT title, author, COUNT(c.id) AS n FROM documents d JOIN chunks c ON c.document_id = d.id WHERE d.collection = 'medieval' GROUP BY d.title, d.author ORDER BY d.title\")
    for r in rows:
        print(r['title'], '|', r['author'], '|', r['n'], 'chunks')
    await close_pool()
asyncio.run(check())
"
```

Expected (approximate chunk counts):
```
Consolation of Philosophy | Boethius | 80-120
Imitation of Christ | Thomas à Kempis | 80-150
On Loving God | Bernard of Clairvaux | 15-40
Proslogium, Monologium, and Cur Deus Homo | Anselm | 100-200
```

- [ ] **Step 3: Spot-check references for Anselm**

```bash
cd datapipeline && .venv/bin/python3 -c "
import asyncio
from load import get_pool, close_pool
async def check():
    pool = await get_pool()
    rows = await pool.fetch(\"SELECT reference FROM chunks c JOIN documents d ON c.document_id = d.id WHERE d.collection = 'medieval' AND d.author = 'Anselm' LIMIT 5\")
    for r in rows: print(r['reference'])
    await close_pool()
asyncio.run(check())
"
```

Expected: refs like `"Anselm — Proslogium, Chapter I"` — NOT `"Proslogium — Chapter I"`.

- [ ] **Step 4: Commit verification note**

No code change needed. The ingestion is complete.

---

## Self-Review

**Spec coverage:**
- ✅ "medieval" registered in constants.py, collections.ts, globals.css
- ✅ Anselm (Proslogium, Monologium, Cur Deus Homo), Boethius, Bernard, à Kempis ingested
- ✅ Anselm ref fix: multi-work ThML refs corrected to include real author name
- ✅ Short chapter merging for Imitation of Christ
- ✅ Monastery grey color `#5A6670`
- ✅ run_all.py updated
- ✅ Bonaventure deferred (CCEL ThML not available at any standard path; needs manual sourcing)

**Placeholder scan:** None found — all steps contain complete code.

**Type consistency:** `fix_multi_work_refs` and `merge_short_chunks` both accept and return `list[tuple[str, str, int, dict | None]]` — matches `ThmlDocument.chunks` type throughout.
