# Foundation — Passage Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared passage contract executable — the additive DB schema, the deterministic identity/anchor library, and the shared backend + frontend types — so the Dual Datapipeline and Reader plans can build against a concrete interface in parallel.

**Architecture:** A single additive migration adds the canonical-passage columns to `chunks`. A pure, unit-tested `identity` module produces deterministic `document_id`s and stable `anchor`s shared by both stores. A `model` module defines the `Passage`/`Document` dataclasses the pipeline emits. Backend Pydantic models and frontend TypeScript interfaces lock the API shapes from the contract spec.

**Tech Stack:** Postgres (Supabase, additive SQL migration), Python 3.12 (asyncpg-era datapipeline, FastAPI/Pydantic backend, pytest), Next.js/TypeScript frontend.

**Spec:** `docs/superpowers/specs/2026-06-13-passage-contract-design.md`

**Note:** Implement on a feature branch (or git worktree) off `master`; do not commit to `master` directly.

---

### Task 1: Additive migration — passage columns on `chunks`

**Files:**
- Create: `supabase/migrations/0013_chunks_passage_columns.sql`

- [ ] **Step 1: Write the migration SQL**

Create `supabase/migrations/0013_chunks_passage_columns.sql`:

```sql
-- Migration 0013: passage contract columns on chunks
-- Adds the canonical-passage fields shared by the reader and search pipelines.
-- See docs/superpowers/specs/2026-06-13-passage-contract-design.md §3.1
-- Additive only: new nullable columns + indexes. Existing rows keep NULLs until re-ingest.

ALTER TABLE chunks ADD COLUMN IF NOT EXISTS anchor        text;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS chapter_key   text;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS chapter_label text;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS unit_label    text;

-- Deep-link target: unique per document. Partial so existing NULL-anchor rows are unaffected.
CREATE UNIQUE INDEX IF NOT EXISTS chunks_document_anchor_uniq
  ON chunks (document_id, anchor)
  WHERE anchor IS NOT NULL;

-- Reader chapter-section query path (group a document's passages by chapter, in order).
CREATE INDEX IF NOT EXISTS chunks_document_chapter_pos_idx
  ON chunks (document_id, chapter_key, position);
```

- [ ] **Step 2: Apply the migration to body-of-christ-dev**

Apply via the Supabase MCP `apply_migration` tool (project `hvmgffvimqgiejmxwhwq`, name `0013_chunks_passage_columns`, the SQL above), or run `supabase db push` if the CLI is linked.

- [ ] **Step 3: Verify the columns and indexes exist**

Run this via the Supabase MCP `execute_sql` (project `hvmgffvimqgiejmxwhwq`):

```sql
SELECT column_name FROM information_schema.columns
WHERE table_name='chunks' AND column_name IN ('anchor','chapter_key','chapter_label','unit_label')
ORDER BY column_name;
SELECT indexname FROM pg_indexes
WHERE tablename='chunks' AND indexname IN ('chunks_document_anchor_uniq','chunks_document_chapter_pos_idx');
```

Expected: 4 column rows (anchor, chapter_key, chapter_label, unit_label) and 2 index rows.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/0013_chunks_passage_columns.sql
git commit -m "feat(db): add passage contract columns to chunks (migration 0013)"
```

---

### Task 2: `identity` module — deterministic document ids & anchors

**Files:**
- Create: `datapipeline/identity.py`
- Test: `datapipeline/tests/test_identity.py`

- [ ] **Step 1: Write the failing tests**

Create `datapipeline/tests/test_identity.py`:

```python
import uuid

from identity import DOCUMENT_NS, slugify, document_id, anchor


def test_slugify_basic():
    assert slugify("First Epistle to the Corinthians") == "first-epistle-to-the-corinthians"


def test_slugify_strips_punct_and_case():
    assert slugify("  Q. 68, A. 3!  ") == "q-68-a-3"
    assert slugify("John") == "john"


def test_document_id_is_uuid_string():
    did = document_id("bible", "WEB-C", "John")
    assert isinstance(did, str)
    uuid.UUID(did)  # parses without raising


def test_document_id_deterministic():
    assert document_id("bible", "WEB-C", "John") == document_id("bible", "WEB-C", "John")


def test_document_id_distinguishes_inputs():
    assert document_id("bible", "WEB-C", "John") != document_id("bible", "WEB-C", "Mark")
    assert document_id("bible", "WEB-C", "John") != document_id("bible", "DRA", "John")


def test_document_id_uses_fixed_namespace():
    # Guards against an accidental namespace change that would re-key every document.
    assert str(DOCUMENT_NS) == "8b4a9d2e-1c6f-4e7a-bf3d-2a5c9e0f17b6"


def test_anchor_numbers_preserved():
    assert anchor("john", 3, 16) == "john/3/16"


def test_anchor_slugifies_text_segments():
    assert anchor("First Epistle", "Chapter 49") == "first-epistle/chapter-49"
    assert anchor("i-ii", "q68", "a3", "i-answer") == "i-ii/q68/a3/i-answer"


def test_passage_id_deterministic_and_unique():
    from identity import passage_id
    did = document_id("bible", "WEB-C", "John")
    pid = passage_id(did, "john/3/16")
    assert pid == passage_id(did, "john/3/16")              # both writers agree
    assert pid != passage_id(did, "john/3/17")              # unique per anchor
    uuid.UUID(pid)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd datapipeline && python -m pytest tests/test_identity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'identity'`.

- [ ] **Step 3: Write the implementation**

Create `datapipeline/identity.py`:

```python
"""Deterministic document identity and passage anchors.

Both ingestion pipelines (reader → Supabase, search → Qdrant) derive document
ids and anchors from this module so the two stores agree. See the passage
contract spec §2–3.
"""
from __future__ import annotations

import re
import uuid

# Fixed project namespace — NEVER change. Every document_id derives from this;
# changing it would re-key the entire corpus.
DOCUMENT_NS = uuid.UUID("8b4a9d2e-1c6f-4e7a-bf3d-2a5c9e0f17b6")

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lowercase, hyphenate, trim to a URL-safe slug."""
    return _NON_SLUG.sub("-", text.strip().lower()).strip("-")


def document_id(*parts: object) -> str:
    """Deterministic UUIDv5 for a work, from its work-key parts (contract §2)."""
    key = "|".join(slugify(str(p)) for p in parts)
    return str(uuid.uuid5(DOCUMENT_NS, key))


def anchor(*segments: object) -> str:
    """Build a stable '/'-joined anchor; integers and digit strings pass through,
    text segments are slugified (contract §3.3)."""
    out: list[str] = []
    for seg in segments:
        s = str(seg)
        out.append(s if s.isdigit() else slugify(s))
    return "/".join(out)


def passage_id(document_id_str: str, anchor_str: str) -> str:
    """Deterministic passage UUID. Used as BOTH chunks.id and the Qdrant point
    id so the reader and search pipelines produce identical ids (contract §4)."""
    return str(uuid.uuid5(DOCUMENT_NS, f"{document_id_str}#{anchor_str}"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd datapipeline && python -m pytest tests/test_identity.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add datapipeline/identity.py datapipeline/tests/test_identity.py
git commit -m "feat(pipeline): deterministic document identity + anchor library"
```

---

### Task 3: `model` module — Passage / Document dataclasses

**Files:**
- Create: `datapipeline/model.py`
- Test: `datapipeline/tests/test_model.py`

- [ ] **Step 1: Write the failing tests**

Create `datapipeline/tests/test_model.py`:

```python
from model import Passage, Document


def test_passage_defaults():
    p = Passage(
        content="For God so loved the world…",
        reference="John 3:16",
        anchor="john/3/16",
        chapter_key="john/3",
        chapter_label="John 3",
        position=15,
    )
    assert p.unit_label is None
    assert p.metadata is None
    assert p.position == 15


def test_document_holds_passages():
    p = Passage(
        content="x", reference="r", anchor="a", chapter_key="c",
        chapter_label="C", position=0, unit_label="16",
    )
    doc = Document(id="d", collection="bible", title="John", passages=[p])
    assert doc.translation == ""
    assert doc.passages[0].unit_label == "16"
    assert doc.author is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd datapipeline && python -m pytest tests/test_model.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'model'`.

- [ ] **Step 3: Write the implementation**

Create `datapipeline/model.py`:

```python
"""Canonical passage + document dataclasses emitted by the parse stage.

One Passage is the unit shared by the reader (Supabase) and search (Qdrant),
per the passage contract spec §3.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Passage:
    content: str          # clean reading text (no breadcrumb headers, no (1/3))
    reference: str        # clean human citation
    anchor: str           # stable deep-link key, unique within a document
    chapter_key: str      # groups passages into a reader chapter-section
    chapter_label: str    # display heading for that section
    position: int         # global 0-based order within the document
    unit_label: str | None = None   # inline ordinal (verse no., "Reply to Objection 2")
    metadata: dict | None = None


@dataclass
class Document:
    id: str               # deterministic document_id (identity.document_id)
    collection: str
    title: str
    author: str | None = None
    year: int | None = None
    translation: str = ""
    metadata: dict | None = None
    passages: list[Passage] = field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd datapipeline && python -m pytest tests/test_model.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add datapipeline/model.py datapipeline/tests/test_model.py
git commit -m "feat(pipeline): Passage and Document dataclasses"
```

---

### Task 4: Backend contract models (reader + TOC + search anchor)

**Files:**
- Modify: `services/api/app/models/documents.py` (append new models)
- Modify: `services/api/app/models/search.py:16-23` (add `anchor` to `ChunkSource`)
- Test: `services/api/tests/test_contract_models.py`

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/test_contract_models.py`:

```python
from app.models.documents import (
    DocumentResponse, ReaderPassage, ReaderChapter, TocEntry, TocResponse,
)
from app.models.search import ChunkSource


def _doc() -> DocumentResponse:
    return DocumentResponse(id="d", collection="bible", title="John", chunk_count=21)


def test_reader_chapter_shape():
    passage = ReaderPassage(
        id="p1", anchor="john/3/16", chapter_key="john/3", chapter_label="John 3",
        unit_label="16", reference="John 3:16", content="For God so loved…",
    )
    chapter = ReaderChapter(
        document=_doc(), chapter_key="john/3", chapter_label="John 3",
        passages=[passage], prev_chapter_key="john/2", next_chapter_key="john/4",
        highlight_anchor="john/3/16",
    )
    assert chapter.passages[0].unit_label == "16"
    assert chapter.next_chapter_key == "john/4"


def test_reader_passage_optionals_default_none():
    p = ReaderPassage(
        id="p", anchor="a", chapter_key="c", chapter_label="C", content="x",
    )
    assert p.unit_label is None
    assert p.reference is None


def test_toc_response_shape():
    toc = TocResponse(document=_doc(), chapters=[TocEntry(chapter_key="john/1", chapter_label="John 1")])
    assert toc.chapters[0].chapter_label == "John 1"


def test_chunk_source_accepts_anchor():
    src = ChunkSource(collection="bible", document_title="John", document_id="d", anchor="john/3/16")
    assert src.anchor == "john/3/16"


def test_chunk_source_anchor_defaults_none():
    src = ChunkSource(collection="bible", document_title="John", document_id="d")
    assert src.anchor is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/api && python -m pytest tests/test_contract_models.py -v`
Expected: FAIL with `ImportError` (ReaderPassage/TocEntry not defined) and `ChunkSource` having no `anchor`.

- [ ] **Step 3: Add the reader/TOC models**

Append to `services/api/app/models/documents.py` (keep the existing `DocumentResponse`, `ReaderChunk`, `ReaderResponse` for now — the Reader plan removes the old ones):

```python
class ReaderPassage(BaseModel):
    id: str
    anchor: str
    chapter_key: str
    chapter_label: str
    unit_label: Optional[str] = None
    reference: Optional[str] = None
    content: str


class ReaderChapter(BaseModel):
    document: DocumentResponse
    chapter_key: str
    chapter_label: str
    passages: list[ReaderPassage]
    prev_chapter_key: Optional[str] = None
    next_chapter_key: Optional[str] = None
    highlight_anchor: Optional[str] = None


class TocEntry(BaseModel):
    chapter_key: str
    chapter_label: str


class TocResponse(BaseModel):
    document: DocumentResponse
    chapters: list[TocEntry]
```

- [ ] **Step 4: Add `anchor` to `ChunkSource`**

In `services/api/app/models/search.py`, modify `ChunkSource` (lines 16-23) to add the field:

```python
class ChunkSource(BaseModel):
    collection: str
    document_title: str
    author: Optional[str] = None
    reference: Optional[str] = None
    document_id: str
    position: Optional[int] = None
    anchor: Optional[str] = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd services/api && python -m pytest tests/test_contract_models.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add services/api/app/models/documents.py services/api/app/models/search.py services/api/tests/test_contract_models.py
git commit -m "feat(api): reader/TOC contract models + anchor on ChunkSource"
```

---

### Task 5: Frontend contract types

**Files:**
- Modify: `apps/web/src/lib/api.ts` (add reader/TOC interfaces; add `anchor` to `ChunkSource`)

- [ ] **Step 1: Add `anchor` to the frontend `ChunkSource`**

In `apps/web/src/lib/api.ts`, modify the `ChunkSource` interface (lines 123-131) to add `anchor`:

```ts
export interface ChunkSource {
  collection: string;
  document_title: string;
  author: string | null;
  reference: string | null;
  document_id: string;
  position: number | null;
  anchor?: string | null;
  metadata?: Record<string, unknown> | null;
}
```

- [ ] **Step 2: Add the reader/TOC interfaces**

In `apps/web/src/lib/api.ts`, in the `// ── V2 Documents ──` section (after `DocumentInfo`, near line 170), add:

```ts
export interface ReaderPassage {
  id: string;
  anchor: string;
  chapter_key: string;
  chapter_label: string;
  unit_label: string | null;
  reference: string | null;
  content: string;
}

export interface ReaderChapter {
  document: DocumentInfo;
  chapter_key: string;
  chapter_label: string;
  passages: ReaderPassage[];
  prev_chapter_key: string | null;
  next_chapter_key: string | null;
  highlight_anchor: string | null;
}

export interface TocEntry {
  chapter_key: string;
  chapter_label: string;
}

export interface TocResponse {
  document: DocumentInfo;
  chapters: TocEntry[];
}
```

> Leave the existing `ReaderChunk`/`ReaderResponse` interfaces in place; the Reader plan removes them when it swaps the reader data source. The new interfaces are additive and unused until then (exported types do not trip eslint no-unused).

- [ ] **Step 3: Verify the frontend type-checks**

Run: `cd apps/web && npm run build`
Expected: build succeeds (type check passes). If the build is too slow in your environment, `npx tsc --noEmit` is an acceptable substitute.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/api.ts
git commit -m "feat(web): reader/TOC contract types + anchor on ChunkSource"
```

---

## Self-Review

**Spec coverage (passage-contract spec):**
- §2 document identity → Task 2 (`document_id`).
- §3.1 schema columns → Task 1 (migration). §3.3 anchor format → Task 2 (`anchor`) + exercised in tests.
- §3 passage model → Task 3 (`Passage`/`Document`).
- §6 API response shapes (`ReaderPassage`, `ReaderChapter`, `TocEntry`, `TocResponse`) → Task 4 (backend) + Task 5 (frontend).
- §4 Qdrant payload `anchor` surfaced to results (`ChunkSource.anchor`) → Task 4 + Task 5.
- Not in this plan (correctly deferred): endpoint logic, sources simplification, embedding retirement, cleaning, reader UI — these belong to the Dual Datapipeline and Reader plans, which depend on this foundation.

**Placeholder scan:** none — every step has concrete SQL/code/commands.

**Type consistency:** `chapter_key`/`chapter_label`/`unit_label`/`anchor` names match across the migration, `Passage`, backend `ReaderPassage`/`ReaderChapter`, and frontend interfaces. `prev_chapter_key`/`next_chapter_key`/`highlight_anchor` match between backend `ReaderChapter` and frontend `ReaderChapter`. `ChunkSource.anchor` optional in both backend and frontend.
