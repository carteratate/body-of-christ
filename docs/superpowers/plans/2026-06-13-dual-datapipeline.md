# Dual Datapipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 3-step ingest→embed→migrate chain with two direct pipelines fed by one parse — a reader writer (→ Supabase clean passages + FTS) and a search writer (→ neighbor-augmented embeddings in Qdrant) — plus a cleaning layer that makes every collection production-grade, and the church-fathers rebuild + Qdrant cleanup.

**Architecture:** Each collection's `ingest` module parses its source into an ordered list of clean `Passage`s (identity + anchors from the Foundation `identity` module, text scrubbed by the `normalize` cleaners). Two writers consume that one list: `reader_writer` upserts documents + passages to Supabase; `search_writer` builds neighbor-augmented embedding inputs and upserts points to Qdrant with `point.id == chunks.id`.

**Tech Stack:** Python 3.12, asyncpg (Supabase), `qdrant-client` (AsyncQdrantClient), OpenAI embeddings (`text-embedding-3-large`, dim 1536), pytest.

**Depends on:** Foundation plan (`identity.py`, `model.py`, migration 0013) must be merged first.
**Specs:** `docs/superpowers/specs/2026-06-13-dual-datapipeline-design.md`, `…-passage-contract-design.md`.

**Note:** Implement on a feature branch off `master`. The `datapipeline/.env` needs `QDRANT_URL` and `QDRANT_API_KEY` added (copy the values from `services/api/.env`).

---

### Task 1: Pipeline config — Qdrant + overlap/size knobs

**Files:**
- Modify: `datapipeline/config.py`
- Test: `datapipeline/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `datapipeline/tests/test_config.py`:

```python
import os
import importlib


def test_overlap_defaults_and_per_collection(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://x")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-x")
    monkeypatch.setenv("QDRANT_URL", "https://q")
    monkeypatch.setenv("QDRANT_API_KEY", "qk")
    import config
    importlib.reload(config)
    s = config.settings
    assert s.QDRANT_URL == "https://q"
    assert s.MAX_PASSAGE_CHARS == 3500
    # per-collection overlap falls back to the default tuple when unset
    assert s.overlap_for("bible") == s.DEFAULT_OVERLAP
    assert isinstance(s.overlap_for("summa"), tuple) and len(s.overlap_for("summa")) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd datapipeline && python -m pytest tests/test_config.py -v`
Expected: FAIL (`QDRANT_URL` attribute / `overlap_for` missing).

- [ ] **Step 3: Extend the config**

In `datapipeline/config.py`, add the Qdrant fields, the size/overlap knobs, and an accessor. Replace the `Settings` dataclass and the `settings` construction:

```python
@dataclass(frozen=True)
class Settings:
    # --- Required ---
    DATABASE_URL: str
    OPENAI_API_KEY: str
    QDRANT_URL: str
    QDRANT_API_KEY: str

    # --- Embedding ---
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIMS: int = 1536
    EMBEDDING_BATCH_SIZE: int = 100

    # --- Chunking / cleaning ---
    MIN_CHUNK_LENGTH: int = 50
    MAX_PASSAGE_CHARS: int = 3500
    # (tail_prev, head_next) characters of neighbor context added at embed time.
    DEFAULT_OVERLAP: tuple[int, int] = (200, 200)
    PER_COLLECTION_OVERLAP: dict[str, tuple[int, int]] = field(default_factory=lambda: {
        "bible": (120, 120),
        "summa": (0, 0),       # articles are self-contained; sub-passages carry their own context
        "catechism": (200, 200),
        "church-fathers": (200, 200),
    })

    def overlap_for(self, collection: str) -> tuple[int, int]:
        return self.PER_COLLECTION_OVERLAP.get(collection, self.DEFAULT_OVERLAP)


settings = Settings(
    DATABASE_URL=_require_env("DATABASE_URL"),
    OPENAI_API_KEY=_require_env("OPENAI_API_KEY"),
    QDRANT_URL=_require_env("QDRANT_URL"),
    QDRANT_API_KEY=_require_env("QDRANT_API_KEY"),
)
```

(Add `field` to the existing `from dataclasses import dataclass, field` import.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd datapipeline && python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add datapipeline/config.py datapipeline/tests/test_config.py
git commit -m "feat(pipeline): config for Qdrant + per-collection overlap/size knobs"
```

---

### Task 2: Qdrant writer client + collection-delete script (brief Step 4)

**Files:**
- Create: `datapipeline/writers/__init__.py` (empty)
- Create: `datapipeline/writers/qdrant.py`
- Create: `datapipeline/scripts/__init__.py` (empty)
- Create: `datapipeline/scripts/delete_collection_qdrant.py`
- Test: `datapipeline/tests/test_qdrant_writer.py`

- [ ] **Step 1: Write the failing test (filter construction is the unit under test)**

Create `datapipeline/tests/test_qdrant_writer.py`:

```python
from writers.qdrant import collection_filter, QDRANT_COLLECTION, EMBEDDING_DIMS


def test_collection_filter_targets_payload_collection():
    f = collection_filter("church-fathers")
    cond = f.must[0]
    assert cond.key == "collection"
    assert cond.match.value == "church-fathers"


def test_constants():
    assert QDRANT_COLLECTION == "chunks"
    assert EMBEDDING_DIMS == 1536
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd datapipeline && python -m pytest tests/test_qdrant_writer.py -v`
Expected: FAIL (`No module named 'writers'`).

- [ ] **Step 3: Implement the Qdrant writer module**

Create `datapipeline/writers/__init__.py` (empty) and `datapipeline/writers/qdrant.py`:

```python
"""Qdrant client + helpers for the search pipeline."""
from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, FieldCondition, Filter, HnswConfigDiff, MatchValue,
    PayloadSchemaType, PointStruct, VectorParams,
)

from config import settings

QDRANT_COLLECTION = "chunks"
EMBEDDING_DIMS = 1536


def get_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)


def collection_filter(collection: str) -> Filter:
    return Filter(must=[FieldCondition(key="collection", match=MatchValue(value=collection))])


async def ensure_collection(client: AsyncQdrantClient) -> None:
    if await client.collection_exists(QDRANT_COLLECTION):
        return
    await client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=EMBEDDING_DIMS, distance=Distance.COSINE),
        hnsw_config=HnswConfigDiff(m=16, ef_construct=64),
    )
    await client.create_payload_index(
        collection_name=QDRANT_COLLECTION, field_name="collection",
        field_schema=PayloadSchemaType.KEYWORD,
    )


async def delete_collection_points(client: AsyncQdrantClient, collection: str) -> None:
    await client.delete(
        collection_name=QDRANT_COLLECTION,
        points_selector=collection_filter(collection),
        wait=True,
    )


async def upsert_points(client: AsyncQdrantClient, points: list[PointStruct]) -> None:
    if points:
        await client.upsert(collection_name=QDRANT_COLLECTION, points=points, wait=True)
```

- [ ] **Step 4: Implement the standalone delete script**

Create `datapipeline/scripts/__init__.py` (empty) and `datapipeline/scripts/delete_collection_qdrant.py`:

```python
"""Delete all Qdrant points for one collection. Run BEFORE re-ingesting it.

    cd datapipeline && python scripts/delete_collection_qdrant.py --collection church-fathers
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from writers.qdrant import get_client, delete_collection_points  # noqa: E402


async def main(collection: str) -> None:
    client = get_client()
    try:
        await delete_collection_points(client, collection)
        print(f"Deleted all Qdrant points where collection == {collection!r}.")
    finally:
        await client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True)
    args = ap.parse_args()
    asyncio.run(main(args.collection))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd datapipeline && python -m pytest tests/test_qdrant_writer.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add datapipeline/writers datapipeline/scripts datapipeline/tests/test_qdrant_writer.py
git commit -m "feat(pipeline): Qdrant writer client + collection-delete script"
```

---

### Task 3: Cleaning layer — whitespace, punctuation, ellipsis

**Files:**
- Create: `datapipeline/normalize/__init__.py`
- Create: `datapipeline/normalize/text.py`
- Test: `datapipeline/tests/test_normalize_text.py`

- [ ] **Step 1: Write the failing tests (golden samples from the real corpus audit)**

Create `datapipeline/tests/test_normalize_text.py`:

```python
from normalize.text import collapse_whitespace, tighten_punctuation, normalize_ellipses, clean_text


def test_collapse_whitespace_keeps_paragraphs():
    assert collapse_whitespace("a   b\t c") == "a b c"
    assert collapse_whitespace("para one\n\npara two") == "para one\n\npara two"


def test_tighten_punctuation():
    assert tighten_punctuation("word .") == "word."
    assert tighten_punctuation("a ; b") == "a; b"


def test_normalize_ellipsis_three_dots():
    assert normalize_ellipses("no other gods before me . . .") == "no other gods before me …"
    assert normalize_ellipses("bone of my bones. . .") == "bone of my bones …"


def test_normalize_ellipsis_collapses_long_table_runs():
    # Summa "diagram" leader-dot artifact: a long run collapses to a single space.
    out = normalize_ellipses("UNDER THE LAW . . . . . . . . all descendants")
    assert "…" not in out and ". ." not in out
    assert "UNDER THE LAW all descendants" == " ".join(out.split())


def test_clean_text_pipeline():
    assert clean_text("word  .  Next . . .") == "word. Next …"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd datapipeline && python -m pytest tests/test_normalize_text.py -v`
Expected: FAIL (`No module named 'normalize'`).

- [ ] **Step 3: Implement the text cleaners**

Create `datapipeline/normalize/__init__.py` (empty) and `datapipeline/normalize/text.py`:

```python
"""Pure text-normalization cleaners (whitespace, punctuation, ellipsis)."""
from __future__ import annotations

import re

_SPACES = re.compile(r"[ \t ]+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")
# 3+ dots separated only by spaces.
_ELLIPSIS = re.compile(r"\.(?:\s*\.){2,}")


def collapse_whitespace(text: str) -> str:
    # Collapse horizontal whitespace; preserve newlines (paragraph structure).
    lines = [_SPACES.sub(" ", ln).strip() for ln in text.split("\n")]
    out = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def tighten_punctuation(text: str) -> str:
    return _SPACE_BEFORE_PUNCT.sub(r"\1", text)


def normalize_ellipses(text: str) -> str:
    def repl(m: re.Match) -> str:
        dots = m.group(0).count(".")
        # Long runs (≥6 dots) are table/diagram artifacts → drop to a space.
        # Genuine omission marks (3–5 dots) → a single ellipsis character.
        return " " if dots >= 6 else "…"
    return _ELLIPSIS.sub(repl, text)


def clean_text(text: str) -> str:
    """Universal cleaner applied to every passage's content."""
    text = normalize_ellipses(text)
    text = collapse_whitespace(text)
    text = tighten_punctuation(text)
    return text.strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd datapipeline && python -m pytest tests/test_normalize_text.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add datapipeline/normalize/__init__.py datapipeline/normalize/text.py datapipeline/tests/test_normalize_text.py
git commit -m "feat(pipeline): text cleaners (whitespace, punctuation, ellipsis)"
```

---

### Task 4: Cleaning layer — Title-case shouting headings

**Files:**
- Create: `datapipeline/normalize/caps.py`
- Test: `datapipeline/tests/test_normalize_caps.py`

- [ ] **Step 1: Write the failing tests**

Create `datapipeline/tests/test_normalize_caps.py`:

```python
from normalize.caps import title_case_shouting


def test_title_cases_long_caps_runs():
    assert title_case_shouting("THE FORMATION OF CLERICS") == "The Formation of Clerics"
    assert title_case_shouting("OF THE GIFTS") == "Of the Gifts"


def test_preserves_known_acronyms():
    assert title_case_shouting("CCC IN BRIEF") == "CCC in Brief"


def test_leaves_normal_text_alone():
    assert title_case_shouting("For God so loved the world") == "For God so loved the world"
    assert title_case_shouting("Chapter I") == "Chapter I"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd datapipeline && python -m pytest tests/test_normalize_caps.py -v`
Expected: FAIL (`No module named 'normalize.caps'`).

- [ ] **Step 3: Implement**

Create `datapipeline/normalize/caps.py`:

```python
"""Title-case ALL-CAPS shouting in headings/titles/references."""
from __future__ import annotations

import re

_KEEP = {"CCC", "OT", "NT", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"}
_LOWER = {"of", "the", "and", "in", "to", "for", "on", "a", "an", "or", "with", "by", "from"}
# A run of 3+ consecutive all-caps words (each ≥2 letters), e.g. "THE FORMATION OF CLERICS".
_CAPS_RUN = re.compile(r"\b(?:[A-Z][A-Z'’]+)(?:\s+[A-Z][A-Z'’]+){2,}\b")


def _title_word(word: str, first: bool) -> str:
    if word in _KEEP:
        return word
    low = word.lower()
    if not first and low in _LOWER:
        return low
    return low.capitalize()


def title_case_shouting(text: str) -> str:
    def repl(m: re.Match) -> str:
        words = m.group(0).split()
        return " ".join(_title_word(w, i == 0) for i, w in enumerate(words))
    return _CAPS_RUN.sub(repl, text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd datapipeline && python -m pytest tests/test_normalize_caps.py -v`
Expected: PASS (3 tests). (`CCC IN BRIEF` → `CCC` kept, `IN`→`in`, `BRIEF`→`Brief`.)

- [ ] **Step 5: Commit**

```bash
git add datapipeline/normalize/caps.py datapipeline/tests/test_normalize_caps.py
git commit -m "feat(pipeline): Title-case shouting headings cleaner"
```

---

### Task 5: Cleaning layer — strip inline footnote markers

**Files:**
- Create: `datapipeline/normalize/footnotes.py`
- Test: `datapipeline/tests/test_normalize_footnotes.py`

- [ ] **Step 1: Write the failing tests (golden samples from encyclicals)**

Create `datapipeline/tests/test_normalize_footnotes.py`:

```python
from normalize.footnotes import strip_footnote_markers


def test_strips_inline_endnote_anchors():
    assert strip_footnote_markers("on the condition of the working classes.[1] It is") \
        == "on the condition of the working classes. It is"


def test_strips_after_quote():
    assert strip_footnote_markers('became poor”;[18] and who') == 'became poor”; and who'


def test_leaves_text_without_markers():
    assert strip_footnote_markers("no markers here") == "no markers here"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd datapipeline && python -m pytest tests/test_normalize_footnotes.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `datapipeline/normalize/footnotes.py`:

```python
"""Strip inline footnote/endnote anchor markers like [1], [18]."""
from __future__ import annotations

import re

# A bracketed integer immediately following a word/punctuation = an endnote anchor.
_MARKER = re.compile(r"(?<=\S)\s*\[\d+\]")


def strip_footnote_markers(text: str) -> str:
    return _MARKER.sub("", text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd datapipeline && python -m pytest tests/test_normalize_footnotes.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add datapipeline/normalize/footnotes.py datapipeline/tests/test_normalize_footnotes.py
git commit -m "feat(pipeline): strip inline footnote markers cleaner"
```

---

### Task 6: Cleaning layer — Summa apparatus expansion

**Files:**
- Create: `datapipeline/normalize/summa.py`
- Test: `datapipeline/tests/test_normalize_summa.py`

- [ ] **Step 1: Write the failing tests (golden samples from Summa)**

Create `datapipeline/tests/test_normalize_summa.py`:

```python
from normalize.summa import expand_apparatus, PART_NAMES


def test_expands_question_article_brackets():
    assert expand_apparatus("as we shall explain further on (TP, Q[7], AA[3],4).") \
        == "as we shall explain further on (Third Part, Q. 7, Aa. 3, 4)."
    assert expand_apparatus("as stated above (A[1]).") == "as stated above (A. 1)."


def test_expands_question_ranges():
    assert expand_apparatus("(QQ[1]-114)") == "(Qq. 1–114)"


def test_drops_editorial_bracket_star():
    assert expand_apparatus("the blessed [*Cf. FP, Q[12]], Article") == "the blessed, Article"


def test_fixes_period_after_label():
    assert expand_apparatus("Question. 102 - OF THE CAUSES") == "Question 102 - OF THE CAUSES"


def test_part_names_present():
    assert PART_NAMES["FS"] == "First Part of the Second Part"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd datapipeline && python -m pytest tests/test_normalize_summa.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

Create `datapipeline/normalize/summa.py`:

```python
"""Expand the Summa's cryptic reference apparatus into readable prose."""
from __future__ import annotations

import re

PART_NAMES = {
    "FP": "First Part",
    "FS": "First Part of the Second Part",
    "SS": "Second Part of the Second Part",
    "SP": "Second Part",
    "TP": "Third Part",
    "XP": "Supplement",
}

# Order matters: drop bracket-star notes first, then expand tokens.
_BRACKET_STAR = re.compile(r"\s*\[\*[^\]]*\]")
_QQ_RANGE = re.compile(r"QQ\[(\d+)\]\s*-\s*\[?(\d+)\]?")
_AA_PAIR = re.compile(r"AA\[(\d+)\]\s*,\s*(\d+)")
_AA = re.compile(r"AA\[(\d+)\]")
_Q = re.compile(r"\bQ\[(\d+)\]")
_A = re.compile(r"\bA\[(\d+)\]")
_OBJ = re.compile(r"\bOBJ\[(\d+)\]")
_LABEL_PERIOD = re.compile(r"\b(Question|Article|Reply|Objection)\.\s*")
_PART_TOKEN = re.compile(r"\b(FP|FS|SS|SP|TP|XP)\b")


def expand_apparatus(text: str) -> str:
    text = _BRACKET_STAR.sub("", text)
    text = _QQ_RANGE.sub(r"Qq. \1–\2", text)
    text = _AA_PAIR.sub(r"Aa. \1, \2", text)
    text = _AA.sub(r"Aa. \1", text)
    text = _Q.sub(r"Q. \1", text)
    text = _A.sub(r"A. \1", text)
    text = _OBJ.sub(r"Objection \1", text)
    text = _LABEL_PERIOD.sub(r"\1 ", text)
    text = _PART_TOKEN.sub(lambda m: PART_NAMES[m.group(1)], text)
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd datapipeline && python -m pytest tests/test_normalize_summa.py -v`
Expected: PASS (5 tests).

> Note: `test_drops_editorial_bracket_star` expects `"the blessed, Article"` — the bracket-star regex consumes the leading space, so `"blessed [*…], Article"` → `"blessed, Article"`.

- [ ] **Step 5: Commit**

```bash
git add datapipeline/normalize/summa.py datapipeline/tests/test_normalize_summa.py
git commit -m "feat(pipeline): Summa apparatus expansion cleaner"
```

---

### Task 7: Reader writer — Supabase documents + passages

**Files:**
- Create: `datapipeline/writers/reader_writer.py`
- Test: `datapipeline/tests/test_reader_writer.py`

- [ ] **Step 1: Write the failing test (SQL-building is unit-tested with a fake connection)**

Create `datapipeline/tests/test_reader_writer.py`:

```python
import asyncio
from model import Passage, Document
from writers import reader_writer


class FakeConn:
    def __init__(self):
        self.calls = []
    async def execute(self, sql, *args):
        self.calls.append((sql, args))
    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return None


class FakePool:
    def __init__(self, conn): self._c = conn
    def acquire(self):
        pool = self
        class _Ctx:
            async def __aenter__(self): return pool._c
            async def __aexit__(self, *a): return False
        return _Ctx()


def test_write_document_inserts_doc_and_passages():
    conn = FakeConn()
    pool = FakePool(conn)
    doc = Document(
        id="11111111-1111-1111-1111-111111111111", collection="bible",
        title="John", translation="WEB-C",
        passages=[Passage(content="x", reference="John 3:16", anchor="john/3/16",
                           chapter_key="john/3", chapter_label="John 3", position=0,
                           unit_label="16")],
    )
    asyncio.run(reader_writer.write_document(pool, doc))
    joined = " ".join(sql for sql, _ in conn.calls)
    assert "INSERT INTO documents" in joined
    assert "INSERT INTO chunks" in joined
    # passage args include the anchor + chapter fields
    chunk_args = [args for sql, args in conn.calls if "INSERT INTO chunks" in sql][0]
    assert "john/3/16" in chunk_args
    assert "john/3" in chunk_args
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd datapipeline && python -m pytest tests/test_reader_writer.py -v`
Expected: FAIL (`reader_writer` missing).

- [ ] **Step 3: Implement the reader writer**

Create `datapipeline/writers/reader_writer.py`:

```python
"""Write clean documents + passages to Supabase (the reader + FTS store).

Does NOT populate content_embedding (retired — vectors live only in Qdrant).
chunks.id is the deterministic passage id so it matches the Qdrant point id.
"""
from __future__ import annotations

import json

import asyncpg

from model import Document
from identity import passage_id


async def clear_collection(pool: asyncpg.Pool, collection: str) -> None:
    """Delete a collection's chunks + documents before a clean re-ingest."""
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM chunks WHERE document_id IN "
            "(SELECT id FROM documents WHERE collection = $1)",
            collection,
        )
        await conn.execute("DELETE FROM documents WHERE collection = $1", collection)


async def write_document(pool: asyncpg.Pool, doc: Document) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO documents (id, collection, title, translation, author, year, metadata)
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::jsonb)
            ON CONFLICT (id) DO UPDATE SET
                title=EXCLUDED.title, translation=EXCLUDED.translation,
                author=EXCLUDED.author, year=EXCLUDED.year, metadata=EXCLUDED.metadata
            """,
            doc.id, doc.collection, doc.title, doc.translation or "",
            doc.author, doc.year, json.dumps(doc.metadata) if doc.metadata else None,
        )
        for p in doc.passages:
            pid = passage_id(doc.id, p.anchor)
            await conn.execute(
                """
                INSERT INTO chunks
                  (id, document_id, content, position, reference,
                   anchor, chapter_key, chapter_label, unit_label, metadata)
                VALUES ($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8,$9,$10::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                   content=EXCLUDED.content, position=EXCLUDED.position,
                   reference=EXCLUDED.reference, anchor=EXCLUDED.anchor,
                   chapter_key=EXCLUDED.chapter_key, chapter_label=EXCLUDED.chapter_label,
                   unit_label=EXCLUDED.unit_label, metadata=EXCLUDED.metadata
                """,
                pid, doc.id, p.content, p.position, p.reference,
                p.anchor, p.chapter_key, p.chapter_label, p.unit_label,
                json.dumps(p.metadata) if p.metadata else None,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd datapipeline && python -m pytest tests/test_reader_writer.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add datapipeline/writers/reader_writer.py datapipeline/tests/test_reader_writer.py
git commit -m "feat(pipeline): reader_writer (Supabase documents + passages)"
```

---

### Task 8: Search writer — augmented embedding input + Qdrant upsert

**Files:**
- Create: `datapipeline/writers/search_writer.py`
- Test: `datapipeline/tests/test_search_writer.py`

- [ ] **Step 1: Write the failing tests (embedding-input builder + point builder are pure)**

Create `datapipeline/tests/test_search_writer.py`:

```python
from model import Passage, Document
from writers.search_writer import build_embedding_input, build_point


def _p(pos, content, anchor):
    return Passage(content=content, reference=f"r{pos}", anchor=anchor,
                   chapter_key="john/3", chapter_label="John 3", position=pos)


def test_embedding_input_adds_neighbor_context_within_chapter():
    ps = [_p(0, "Aaa.", "john/3/1"), _p(1, "Bbb.", "john/3/2"), _p(2, "Ccc.", "john/3/3")]
    out = build_embedding_input(ps, 1, k_prev=10, k_next=10, prefix="[John 3] ")
    assert out.startswith("[John 3] ")
    assert "Bbb." in out and "Aaa." in out and "Ccc." in out


def test_embedding_input_does_not_cross_chapter():
    a = _p(0, "Aaa.", "john/3/1")
    b = Passage(content="Bbb.", reference="r", anchor="john/4/1",
                chapter_key="john/4", chapter_label="John 4", position=1)
    out = build_embedding_input([a, b], 1, k_prev=50, k_next=50, prefix="")
    assert "Aaa." not in out  # previous passage is a different chapter


def test_build_point_uses_clean_content_and_matching_id():
    doc = Document(id="d", collection="bible", title="John")
    p = _p(0, "Clean text", "john/3/16")
    point = build_point(doc, p, vector=[0.0] * 1536)
    assert point.payload["content"] == "Clean text"
    assert point.payload["anchor"] == "john/3/16"
    assert point.payload["collection"] == "bible"
    assert point.payload["document_id"] == "d"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd datapipeline && python -m pytest tests/test_search_writer.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the search writer**

Create `datapipeline/writers/search_writer.py`:

```python
"""Embed neighbor-augmented passages and upsert them to Qdrant.

Stored payload content stays clean; overlap exists only in the embedded text.
point.id == chunks.id (deterministic passage id), so RRF dedup across the
vector + FTS paths is correct.
"""
from __future__ import annotations

import openai
from qdrant_client.models import PointStruct

from config import settings
from identity import passage_id
from model import Document, Passage
from writers.qdrant import upsert_points


def build_embedding_input(passages: list[Passage], idx: int,
                          k_prev: int, k_next: int, prefix: str) -> str:
    p = passages[idx]
    parts = [prefix] if prefix else []
    if k_prev and idx > 0 and passages[idx - 1].chapter_key == p.chapter_key:
        parts.append(passages[idx - 1].content[-k_prev:])
    parts.append(p.content)
    if k_next and idx + 1 < len(passages) and passages[idx + 1].chapter_key == p.chapter_key:
        parts.append(passages[idx + 1].content[:k_next])
    return " ".join(parts).strip()


def build_point(doc: Document, p: Passage, vector: list[float]) -> PointStruct:
    return PointStruct(
        id=passage_id(doc.id, p.anchor),
        vector=vector,
        payload={
            "collection": doc.collection,
            "document_id": doc.id,
            "document_title": doc.title,
            "author": doc.author,
            "content": p.content,          # CLEAN, never the augmented text
            "reference": p.reference,
            "anchor": p.anchor,
            "chapter_label": p.chapter_label,
        },
    )


async def _embed(client: openai.AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    import asyncio
    for attempt in range(3):
        try:
            resp = await client.embeddings.create(
                input=texts, model=settings.EMBEDDING_MODEL, dimensions=settings.EMBEDDING_DIMS,
            )
            return [r.embedding for r in sorted(resp.data, key=lambda r: r.index)]
        except openai.RateLimitError:
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


async def write_document(client_qdrant, doc: Document) -> None:
    """Embed all passages (augmented) and upsert points for one document."""
    oa = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    k_prev, k_next = settings.overlap_for(doc.collection)
    prefix_for = lambda p: f"[{p.chapter_label}] "
    try:
        batch = settings.EMBEDDING_BATCH_SIZE
        for start in range(0, len(doc.passages), batch):
            window = doc.passages[start:start + batch]
            inputs = [
                build_embedding_input(doc.passages, start + i, k_prev, k_next, prefix_for(p))
                for i, p in enumerate(window)
            ]
            vectors = await _embed(oa, inputs)
            points = [build_point(doc, p, v) for p, v in zip(window, vectors)]
            await upsert_points(client_qdrant, points)
    finally:
        await oa.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd datapipeline && python -m pytest tests/test_search_writer.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add datapipeline/writers/search_writer.py datapipeline/tests/test_search_writer.py
git commit -m "feat(pipeline): search_writer (augmented embedding + Qdrant points)"
```

---

### Task 9: Church-fathers rebuild — per-(father, work) passages (brief Step 2 & 4)

**Files:**
- Modify: `datapipeline/ingest/common.py` (add `parse_thml_works` returning per-work `Document`s)
- Rewrite: `datapipeline/ingest/church_fathers.py` (build `Document`s, no DB writes)
- Test: `datapipeline/tests/test_church_fathers.py`

- [ ] **Step 1: Write the failing test (against the real multi-author file)**

Create `datapipeline/tests/test_church_fathers.py`:

```python
import os
from ingest.church_fathers import build_documents

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "sources", "church-fathers")


def test_apostolic_fathers_splits_into_per_work_documents():
    path = os.path.join(_SRC, "apostolic fathers.xml")
    docs = build_documents(path)
    # Clement of Rome's First Epistle should be its own document with the right author/title.
    clement = [d for d in docs if d.author == "Clement of Rome"
               and "First Epistle" in d.title]
    assert clement, [(d.author, d.title) for d in docs][:10]
    d = clement[0]
    assert d.collection == "church-fathers"
    assert d.passages and d.passages[0].chapter_key
    # No breadcrumb header cruft in clean content.
    assert not d.passages[0].content.lstrip().startswith("[")


def test_single_author_files_unchanged_author():
    path = os.path.join(_SRC, "confessions.xml")
    docs = build_documents(path)
    assert len(docs) == 1
    assert docs[0].author == "Augustine"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd datapipeline && python -m pytest tests/test_church_fathers.py -v`
Expected: FAIL (`build_documents` missing).

- [ ] **Step 3: Add per-work extraction to `common.py`**

In `datapipeline/ingest/common.py`, add a function that walks `div1`=father / `div2`=work and yields `(author, work_title, [chapter_elems])`, skipping front-matter titles (reuse `_SKIP_TITLES`, extended). Add near the other helpers:

```python
_SKIP_WORK_TITLES = _SKIP_TITLES | frozenset({
    "introductory note", "introductory notice", "introductory notice.",
    "title pages", "subject index", "subject indexes", "appendix",
})


def iter_works(root):
    """Yield (author_label, work_title, [chunk_div_elements]) for a ThML volume.

    Multi-author volume: div1 = father, div2 = work, chapters = div2's chunk-level divs.
    Single-author file: falls back to the document's own author/title with all chapters.
    """
    div1s = [d for d in root.iter("div1")
             if (d.get("title") or "").strip().lower() not in _SKIP_WORK_TITLES]
    multi = _detect_is_multi_author(root)
    chunk_level = _detect_chunk_level(root)
    for d1 in div1s:
        father = _maybe_title_case((d1.get("title") or "").strip())
        div2s = [d for d in d1.iter("div2")
                 if (d.get("title") or "").strip().lower() not in _SKIP_WORK_TITLES]
        if multi and div2s:
            for d2 in div2s:
                work = (d2.get("title") or "").strip()
                chapters = [e for e in d2.iter(f"div{chunk_level}")
                            if (e.get('title') or '').strip().lower() not in _SKIP_WORK_TITLES]
                yield father, work, chapters
        else:
            chapters = [e for e in d1.iter(f"div{chunk_level}")]
            yield father, (d1.get("title") or "").strip(), chapters
```

> During execution, verify `iter_works` against the real XML structure with the Task-1 test and adjust the div-walking if a file nests differently (some volumes use `div3` chapters under `div2`). The test names a concrete expected work to anchor correctness.

- [ ] **Step 4: Rewrite `church_fathers.py` to build `Document`s**

Replace `datapipeline/ingest/church_fathers.py` with a builder (no DB writes — the orchestrator calls the writers):

```python
"""Church Fathers ingestion — one Document per (father, work)."""
from __future__ import annotations

import os
from glob import glob

from identity import document_id, anchor as make_anchor, slugify
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import title_case_shouting
from ingest.common import (
    parse_thml_string, iter_works, _extract_p_text, split_at_sentences,
)
import defusedxml.ElementTree as ET
import re

_SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources", "church-fathers")
_SINGLE_AUTHOR = {"confessions.xml": "Augustine", "incarnation.xml": "Athanasius"}
_MAX = 3500


def _strip_doctype(xml: str) -> str:
    return re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", xml, flags=re.DOTALL)


def build_documents(path: str) -> list[Document]:
    filename = os.path.basename(path)
    if filename == "summa.xml":
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        root = ET.fromstring(_strip_doctype(f.read()))

    docs: list[Document] = []
    for father, work, chapters in iter_works(root):
        author = title_case_shouting(father).strip() or "Unknown"
        title = title_case_shouting(work).strip() or author
        did = document_id("church-fathers", author, title)
        work_slug = slugify(title)
        passages: list[Passage] = []
        pos = 0
        for ch in chapters:
            raw = _extract_p_text(ch)
            if len(raw) < 100:
                continue
            ch_label = title_case_shouting((ch.get("title") or "").strip()) or f"Section {pos+1}"
            ch_slug = slugify(ch_label)
            parts = split_at_sentences(raw, target=_MAX, overlap=0) if len(raw) > _MAX else [raw]
            for i, part in enumerate(parts):
                sub = f"-{i+1}" if len(parts) > 1 else ""
                a = make_anchor(work_slug, ch_slug) + sub
                passages.append(Passage(
                    content=clean_text(part),
                    reference=f"{author} — {title}, {ch_label}",
                    anchor=a,
                    chapter_key=make_anchor(work_slug, ch_slug),
                    chapter_label=ch_label,
                    position=pos,
                    unit_label=None,
                    metadata={"source_file": filename},
                ))
                pos += 1
        if passages:
            docs.append(Document(id=did, collection="church-fathers", title=title,
                                 author=author, metadata={"source_file": filename},
                                 passages=passages))
    return docs


def build_all() -> list[Document]:
    docs: list[Document] = []
    for path in sorted(glob(os.path.join(_SRC_DIR, "*.xml"))):
        if path.endswith(".Zone.Identifier"):
            continue
        docs.extend(build_documents(path))
    return docs
```

> `confessions.xml`/`incarnation.xml` are single-`div1` files, so `iter_works` yields one work with the file's own author — `parse_thml_string` already resolves Augustine/Athanasius from `DC.Creator`; if `iter_works` returns the wrong author label for these, special-case them with `_SINGLE_AUTHOR[filename]`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd datapipeline && python -m pytest tests/test_church_fathers.py -v`
Expected: PASS. If the real XML nests works differently than assumed, fix `iter_works` until both assertions pass (the test pins concrete, known-correct output).

- [ ] **Step 6: Commit**

```bash
git add datapipeline/ingest/common.py datapipeline/ingest/church_fathers.py datapipeline/tests/test_church_fathers.py
git commit -m "feat(pipeline): church-fathers rebuild into per-work documents"
```

---

### Task 10: Summa adapter — article sub-passages + apparatus + reference

**Files:**
- Modify: `datapipeline/ingest/summa.py` (build `Document` with article sub-passages)
- Test: `datapipeline/tests/test_summa.py`

- [ ] **Step 1: Write the failing tests**

Create `datapipeline/tests/test_summa.py`:

```python
import os
from ingest.summa import build_document

_SRC = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "sources", "church-fathers", "summa.xml")


def test_summa_builds_one_document_with_clean_refs():
    doc = build_document(_SRC)
    assert doc.collection == "summa"
    assert doc.title.startswith("Summa")
    # Articles split into parts → many passages, none gigantic.
    assert all(len(p.content) <= 4000 for p in doc.passages)
    # Apparatus expanded in references (no Q[..]/A[..] bracket scheme, no shouting).
    sample = doc.passages[0].reference
    assert "Q[" not in sample and "A[" not in sample


def test_summa_unit_labels_mark_article_parts():
    doc = build_document(_SRC)
    labels = {p.unit_label for p in doc.passages if p.unit_label}
    assert any(l and l.startswith("Objection") for l in labels) or "I answer that" in labels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd datapipeline && python -m pytest tests/test_summa.py -v`
Expected: FAIL (`build_document` missing).

- [ ] **Step 3: Implement the Summa adapter**

Add a TODO header documenting the source table/leader-dot origin (the brief's Step 1), then build the `Document`. Append to / restructure `datapipeline/ingest/summa.py`:

```python
"""Summa Theologica ingestion → one Document, one passage per article part.

SOURCE NOTE: the NPNF source XML flattened a 3-column comparison table into
runs of '. . . . .' leader dots in a few articles ("may be seen from the
following diagram"). normalize.text.normalize_ellipses() collapses those long
runs; the cryptic apparatus (Q[7], AA[3], FP/TP, QQ[1]-114) is expanded by
normalize.summa.expand_apparatus().
"""
from __future__ import annotations

import os
import re
import defusedxml.ElementTree as ET

from identity import document_id, anchor as make_anchor
from model import Document, Passage
from normalize.text import clean_text
from normalize.caps import title_case_shouting
from normalize.summa import expand_apparatus
from ingest.common import _extract_p_text

# Splits an article body into its dialectical parts.
_PART_RE = re.compile(
    r"(Objection\s+\d+:|On the contrary,|I answer that,|Reply to Objection\s+\d+:)",
)
_PART_NAME = re.compile(r"(Objection\s+\d+|Reply to Objection\s+\d+|On the contrary|I answer that)")


def _split_article(text: str) -> list[tuple[str | None, str]]:
    """Return [(part_label, part_text)] split on the dialectical markers."""
    pieces = _PART_RE.split(text)
    if len(pieces) == 1:
        return [(None, text.strip())]
    out: list[tuple[str | None, str]] = []
    # pieces alternate: [pre, marker, body, marker, body, ...]
    if pieces[0].strip():
        out.append((None, pieces[0].strip()))
    for i in range(1, len(pieces), 2):
        marker = pieces[i].strip().rstrip(":,")
        body = (marker + " " + pieces[i + 1].strip()).strip() if i + 1 < len(pieces) else marker
        out.append((marker, body))
    return out


def build_document(path: str) -> Document:
    with open(path, encoding="utf-8", errors="replace") as f:
        xml = re.sub(r"<!DOCTYPE[^>]*(?:>|\[.*?\]>)", "", f.read(), flags=re.DOTALL)
    root = ET.fromstring(xml)

    did = document_id("summa")
    passages: list[Passage] = []
    pos = 0
    for div1 in root.iter("div1"):
        part = expand_apparatus(title_case_shouting((div1.get("title") or "").strip()))
        for div3 in div1.iter("div3"):       # Question
            q = expand_apparatus(title_case_shouting((div3.get("title") or "").strip()))
            for div4 in div3.iter("div4"):    # Article
                a_title = expand_apparatus(title_case_shouting((div4.get("title") or "").strip()))
                body = clean_text(expand_apparatus(_extract_p_text(div4)))
                if len(body) < 50:
                    continue
                ch_key = make_anchor("summa", part, q, a_title)
                ch_label = f"{q} — {a_title}".strip(" —")
                ref = f"Summa Theologiae, {part}, {q}, {a_title}".replace(" ,", ",")
                for i, (label, ptext) in enumerate(_split_article(body)):
                    passages.append(Passage(
                        content=ptext,
                        reference=ref,
                        anchor=ch_key + f"/{i}",
                        chapter_key=ch_key,
                        chapter_label=ch_label,
                        position=pos,
                        unit_label=label,
                        metadata={"part": part},
                    ))
                    pos += 1
    return Document(id=did, collection="summa",
                    title="Summa Theologiae", author="Thomas Aquinas",
                    metadata={"source_file": "summa.xml"}, passages=passages)
```

> Verify the `div1→div3→div4` nesting against the real file with the test; the existing `_chunk_summa` in `common.py` confirms Part=div1, Question=div3, Article=div4. Adjust if a Part wraps Questions in `div2` treatises (then iterate `div1→div2→div3→div4`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd datapipeline && python -m pytest tests/test_summa.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add datapipeline/ingest/summa.py datapipeline/tests/test_summa.py
git commit -m "feat(pipeline): Summa article-part passages + apparatus cleanup"
```

---

### Task 11: Bible adapter — pericope passages clamped to chapters

**Files:**
- Modify: `datapipeline/ingest/bible.py` (add `build_documents` producing `Document`s)
- Test: `datapipeline/tests/test_bible_passages.py`

- [ ] **Step 1: Write the failing tests**

Create `datapipeline/tests/test_bible_passages.py`:

```python
from ingest.bible import clamp_pericopes_to_chapters


def test_multi_chapter_pericope_splits_at_chapter_boundary():
    # A pericope spanning 2 Samuel 15–16 yields one passage per chapter.
    verses = [(15, 1, "a"), (15, 2, "b"), (16, 1, "c")]
    out = clamp_pericopes_to_chapters("The Revolt", verses)
    assert len(out) == 2
    assert out[0][0] == 15 and out[1][0] == 16           # (chapter, [verses])
    assert [v for _, vs in out for v in vs] == [(15,1,"a"), (15,2,"b"), (16,1,"c")]


def test_single_chapter_pericope_stays_whole():
    verses = [(3, 14, "x"), (3, 15, "y"), (3, 16, "z")]
    out = clamp_pericopes_to_chapters("Nicodemus", verses)
    assert len(out) == 1 and out[0][0] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd datapipeline && python -m pytest tests/test_bible_passages.py -v`
Expected: FAIL (`clamp_pericopes_to_chapters` missing).

- [ ] **Step 3: Implement chapter-clamping + a `build_documents` that emits `Document`s**

Add to `datapipeline/ingest/bible.py`:

```python
from itertools import groupby
from identity import document_id, anchor as make_anchor
from model import Document, Passage
from normalize.text import clean_text


def clamp_pericopes_to_chapters(title, verses):
    """Group a pericope's (chapter, verse, text) list into per-chapter parts.

    Returns [(chapter, [(chapter, verse, text), ...])] so a passage never
    crosses a chapter boundary while keeping the pericope title.
    """
    out = []
    for chapter, group in groupby(verses, key=lambda v: v[0]):
        out.append((chapter, list(group)))
    return out


def build_documents(usfm_dir=None, translation="WEB-C"):
    """Build one Document per book; passages = pericope sections clamped to chapters."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    usfm_dir = usfm_dir or os.path.join(root, _DEFAULT_USFM_SUBDIR)
    pericope_map = load_pericopes(os.path.join(root, _DEFAULT_PERICOPE_PATH))
    books = load_usfm_directory(usfm_dir)
    docs: list[Document] = []
    for name, book in sorted(books.items()):
        did = document_id("bible", translation, name)
        book_slug = slugify_book(name)
        verse_map = {(v.chapter, v.verse): v.text for v in book.verses}
        passages: list[Passage] = []
        pos = 0
        for p in pericope_map.get(name, []):
            verses = collect_pericope_verses(verse_map, p.start_chapter, p.start_verse,
                                             p.end_chapter, p.end_verse)
            if not verses:
                continue
            for chapter, chap_verses in clamp_pericopes_to_chapters(p.title, verses):
                content = clean_text(" ".join(t for _, _, t in chap_verses))
                if not content:
                    continue
                first_v = chap_verses[0][1]
                passages.append(Passage(
                    content=content,
                    reference=_format_reference(name, chapter, first_v,
                                                chapter, chap_verses[-1][1]),
                    anchor=make_anchor(book_slug, chapter, first_v),
                    chapter_key=make_anchor(book_slug, chapter),
                    chapter_label=f"{name} {chapter}",
                    position=pos,
                    unit_label=str(first_v),
                    metadata={"pericope": p.title, "testament": book.testament,
                              "translation": translation,
                              "verses": [{"v": v, "t": t} for _, v, t in chap_verses]},
                ))
                pos += 1
        # Books without pericopes (deuterocanonical, Psalms): one passage per chapter.
        if not passages:
            for chapter, chap_verses in groupby(sorted(verse_map.items()),
                                                key=lambda kv: kv[0][0]):
                cv = list(chap_verses)
                content = clean_text(" ".join(t for _, t in cv))
                if not content:
                    continue
                passages.append(Passage(
                    content=content, reference=f"{name} {chapter}",
                    anchor=make_anchor(book_slug, chapter, cv[0][0][1]),
                    chapter_key=make_anchor(book_slug, chapter),
                    chapter_label=f"{name} {chapter}", position=pos,
                    unit_label=str(cv[0][0][1]),
                    metadata={"testament": book.testament, "translation": translation},
                ))
                pos += 1
        docs.append(Document(id=did, collection="bible", title=name, translation=translation,
                             metadata={"testament": book.testament}, passages=passages))
    return docs


def slugify_book(name: str) -> str:
    from identity import slugify
    return slugify(name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd datapipeline && python -m pytest tests/test_bible_passages.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add datapipeline/ingest/bible.py datapipeline/tests/test_bible_passages.py
git commit -m "feat(pipeline): bible passages = pericopes clamped to chapters"
```

---

### Task 12: Catechism adapter — drop TOC fragments, clean text

**Files:**
- Modify: `datapipeline/ingest/catechism.py` (add `build_document`)
- Test: `datapipeline/tests/test_catechism_passages.py`

- [ ] **Step 1: Write the failing tests**

Create `datapipeline/tests/test_catechism_passages.py`:

```python
from ingest.catechism import build_document, _DEFAULT_SRC


def test_no_tiny_toc_fragments():
    doc = build_document(_DEFAULT_SRC)
    # The old pipeline emitted 9-char "Article 2" / "PART TWO:" passages; drop them.
    tiny = [p for p in doc.passages if len(p.content) < 30]
    assert tiny == [], tiny[:5]


def test_unit_label_is_ccc_number_and_text_clean():
    doc = build_document(_DEFAULT_SRC)
    numbered = [p for p in doc.passages if p.unit_label]
    assert numbered
    assert all(". . ." not in p.content for p in doc.passages)  # ellipses normalized
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd datapipeline && python -m pytest tests/test_catechism_passages.py -v`
Expected: FAIL (`build_document` missing).

- [ ] **Step 3: Implement (reuse the existing tier chunker, then map → Passage)**

Add to `datapipeline/ingest/catechism.py`:

```python
import json as _json
from identity import document_id, anchor as make_anchor
from model import Document, Passage
from normalize.text import clean_text

_MIN_CONTENT = 30


def build_document(source_path: str | None = None) -> Document:
    src = source_path or _DEFAULT_SRC
    with open(src, encoding="utf-8") as f:
        data = _json.load(f)
    page_nodes = data.get("page_nodes", {})

    def _key(k: str) -> int:
        try:
            return int(k.split("-", 1)[1])
        except (IndexError, ValueError):
            return 0

    ids = sorted(page_nodes.keys(), key=_key)
    raw_chunks = chunk_nodes([page_nodes[k] for k in ids], ids)  # (content, ref, meta, pos)

    did = document_id("catechism")
    passages: list[Passage] = []
    pos = 0
    for content, reference, meta, _ in raw_chunks:
        clean = clean_text(content)
        if len(clean) < _MIN_CONTENT:
            continue                      # drop TOC-only fragments ("Article 2")
        paras = meta.get("ccc_paragraphs") or []
        first = paras[0] if paras else None
        chapter_no = (first // 100) if first else 0    # coarse chapter grouping by CCC century
        passages.append(Passage(
            content=clean,
            reference=reference,
            anchor=make_anchor("ccc", first) if first else make_anchor("ccc", meta.get("path", str(pos))),
            chapter_key=make_anchor("ccc", "part", str(chapter_no)),
            chapter_label=f"CCC §§{chapter_no*100}–{chapter_no*100+99}" if first else "CCC",
            position=pos,
            unit_label=(f"§{first}" if first else None),
            metadata=meta,
        ))
        pos += 1
    return Document(id=did, collection="catechism",
                    title="Catechism of the Catholic Church", author="Catholic Church",
                    year=1992, metadata={"source": "nossbigg/catechism-ccc-json"},
                    passages=passages)
```

> Chapter grouping here is coarse (by CCC century). During execution, if a finer/native section grouping is available in the source `page_nodes` path, prefer it for `chapter_key`/`chapter_label`; the test only requires no tiny fragments + clean text + CCC unit labels.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd datapipeline && python -m pytest tests/test_catechism_passages.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add datapipeline/ingest/catechism.py datapipeline/tests/test_catechism_passages.py
git commit -m "feat(pipeline): catechism passages drop TOC fragments + clean text"
```

---

### Task 13: Orchestration — run a collection through both writers

**Files:**
- Create: `datapipeline/run_collection.py`
- Modify: `datapipeline/run_all.py` (route to the new builders/writers)
- Test: `datapipeline/tests/test_run_collection.py`

- [ ] **Step 1: Write the failing test (the builder registry + flag parsing are unit-testable)**

Create `datapipeline/tests/test_run_collection.py`:

```python
from run_collection import BUILDERS


def test_builders_registered():
    assert set(BUILDERS) >= {"bible", "catechism", "church-fathers", "summa"}
    # each builder is callable returning documents (smoke: church-fathers)
    assert callable(BUILDERS["church-fathers"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd datapipeline && python -m pytest tests/test_run_collection.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement the orchestrator**

Create `datapipeline/run_collection.py`:

```python
"""Run one collection through both pipelines: parse → reader (Supabase) + search (Qdrant)."""
from __future__ import annotations

import argparse
import asyncio

import asyncpg

from config import settings
from model import Document
from writers import reader_writer
from writers.qdrant import get_client, ensure_collection, delete_collection_points
from writers import search_writer
from ingest import church_fathers, summa, bible, catechism

BUILDERS = {
    "church-fathers": church_fathers.build_all,
    "summa": lambda: [summa.build_document(summa._SRC if hasattr(summa, "_SRC") else None)],
    "bible": bible.build_documents,
    "catechism": lambda: [catechism.build_document()],
}


async def run(collection: str, target: str, clean: bool, limit: int | None) -> None:
    docs: list[Document] = BUILDERS[collection]()
    if limit:
        docs = docs[:limit]
    print(f"{collection}: {len(docs)} documents, {sum(len(d.passages) for d in docs)} passages")

    pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=5,
                                     statement_cache_size=0)
    qdrant = get_client()
    try:
        await ensure_collection(qdrant)
        if target in ("reader", "both"):
            await reader_writer.clear_collection(pool, collection)
            for d in docs:
                await reader_writer.write_document(pool, d)
        if target in ("search", "both"):
            if clean:
                await delete_collection_points(qdrant, collection)
            for d in docs:
                await search_writer.write_document(qdrant, d)
    finally:
        await pool.close()
        await qdrant.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", required=True, choices=list(BUILDERS))
    ap.add_argument("--target", default="both", choices=["reader", "search", "both"])
    ap.add_argument("--clean", action="store_true", help="delete the collection's Qdrant points first")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    asyncio.run(run(a.collection, a.target, a.clean, a.limit))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd datapipeline && python -m pytest tests/test_run_collection.py -v`
Expected: PASS.

- [ ] **Step 5: Retire the old two-step path**

Delete `datapipeline/embed.py`'s Supabase-embedding role and `services/api/scripts/migrate_to_qdrant.py` usage by adding a deprecation note at the top of each (do not delete the files yet — they remain as reference until all collections are re-ingested):

In `services/api/scripts/migrate_to_qdrant.py`, add at the top of the module docstring: `DEPRECATED: superseded by datapipeline search_writer (direct-to-Qdrant). Kept for reference only.` Same note in `datapipeline/embed.py`.

- [ ] **Step 6: Commit**

```bash
git add datapipeline/run_collection.py datapipeline/run_all.py datapipeline/embed.py services/api/scripts/migrate_to_qdrant.py datapipeline/tests/test_run_collection.py
git commit -m "feat(pipeline): dual-write orchestrator; deprecate embed/migrate path"
```

---

### Task 14: Live re-ingest of the locally-sourced collections + source acquisition

**Files:**
- Create: `datapipeline/sources/SOURCES.md` (provenance log)
- (No new code — this task runs the pipeline and verifies the data.)

- [ ] **Step 1: Add `QDRANT_URL` / `QDRANT_API_KEY` to `datapipeline/.env`**

Copy the two values from `services/api/.env` into `datapipeline/.env`.

- [ ] **Step 2: Dry-run church-fathers with the Qdrant clean, small limit**

Run: `cd datapipeline && python run_collection.py --collection church-fathers --target both --clean --limit 1`
Expected: prints document/passage counts; no errors; one document's points upserted.

- [ ] **Step 3: Verify church-fathers data quality in Supabase**

Via Supabase MCP `execute_sql` (project `hvmgffvimqgiejmxwhwq`):

```sql
SELECT d.author, d.title, count(c.id) AS passages,
       bool_or(c.content LIKE '[%') AS any_bracket_header,
       bool_or(c.anchor IS NULL) AS any_missing_anchor
FROM documents d JOIN chunks c ON c.document_id=d.id
WHERE d.collection='church-fathers'
GROUP BY d.author, d.title ORDER BY d.author LIMIT 20;
```

Expected: real per-author/per-work rows (e.g. `Clement of Rome — First Epistle to the Corinthians`), `any_bracket_header=false`, `any_missing_anchor=false`.

- [ ] **Step 4: Full re-ingest of the four locally-sourced collections**

Run each (church-fathers uses `--clean`):

```bash
cd datapipeline
python run_collection.py --collection church-fathers --target both --clean
python run_collection.py --collection summa --target both --clean
python run_collection.py --collection bible --target both --clean
python run_collection.py --collection catechism --target both --clean
```

Expected: each completes; passage counts roughly match the audit (bible ~3k, summa more than 3,120 due to article splitting, church-fathers per-work documents).

- [ ] **Step 5: Verify parity (Supabase id == Qdrant id) on a sample**

Pick one chunk id from Supabase and confirm it exists in Qdrant with matching clean content (Supabase MCP for the id; a small Python snippet or Qdrant dashboard for the point). Confirm `anchor`/`chapter_label` present in the payload.

- [ ] **Step 6: Record source provenance + open the acquisition workstream**

Create `datapipeline/sources/SOURCES.md` listing, per collection, the source URL/origin and local path. Mark **encyclicals, canon-law, councils** as **MISSING — re-acquire** and **medieval** as **re-download from ccel.org** (URLs already in `ingest/medieval.py`). These four are **blocked** for full structural re-ingest until sourced; once a source lands, add its `build_documents`/`build_document` adapter following the patterns in Tasks 9–12 and run `run_collection.py` for it. (Separate follow-up plan per collection as sources arrive.)

- [ ] **Step 7: Commit**

```bash
git add datapipeline/sources/SOURCES.md
git commit -m "docs(pipeline): source provenance + acquisition status; re-ingest verified"
```

---

## Self-Review

**Spec coverage (dual-datapipeline spec):**
- §2 one-parse→two-writers → Tasks 7, 8, 13. §3 module layout → Tasks 1–8, 13.
- §4 per-collection passage construction → church-fathers (9), summa (10), bible (11), catechism (12); other 4 deferred to acquisition (14).
- §5 cleaning layer: text (3), caps (4), footnotes (5), summa apparatus (6); applied in the adapters (9–12).
- §6 embedding/Qdrant → Task 8. §7 source acquisition → Task 14. §8 CF rebuild + Step 4 delete → Tasks 2, 9, 13/14.
- §9 migration/retire embed+migrate → Foundation (migration) + Task 13.
- §10 testing → unit tests in every task + live verification (14).

**Placeholder scan:** none — concrete code/SQL/commands throughout. The adapter tasks include "verify against real XML" execution notes, but each ships runnable code + a test pinning known-correct output.

**Type consistency:** `Passage`/`Document` field names match the Foundation `model.py`. `passage_id`, `document_id`, `anchor`, `slugify` match the Foundation `identity.py`. Qdrant payload keys (`collection, document_id, document_title, author, content, reference, anchor, chapter_label`) match the contract §4 and `retrieve.py`'s reads (plus the new `anchor`). `overlap_for`/`MAX_PASSAGE_CHARS` consistent between config (1) and search_writer (8).

**Note for executor:** footnote/caps cleaners are wired into the *encyclicals/councils/canon-law* adapters, which live in the deferred acquisition workstream (Task 14 follow-ups); Tasks 9–12 apply `clean_text` + `title_case_shouting` (+ `expand_apparatus` for summa). The footnote cleaner is unit-tested now so it is ready when those adapters are built.
