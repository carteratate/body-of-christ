# Datapipeline Ingest Design Spec

> **Superseded publication design.** Preserve this file as design history; do not run
> its publication commands. Use [`datapipeline/README.md`](../../../datapipeline/README.md).
**Date:** 2026-06-02  
**Status:** Approved  
**Scope:** All six collection ingest scripts + embed.py + run_all.py

---

## Context

The Body of Christ RAG app has six source collections in Postgres: `bible`, `catechism`, `canon-law`, `encyclicals`, `church-fathers`, `saints`. The V2 schema (migrations 0001–0009) is fully applied. The datapipeline foundation (`load.py`, `config.py`) exists and provides `upsert_document()` and `upsert_chunk()`. The existing `bible.py` was written for eBible USFM + Gutenberg downloads but the user has placed local files instead. All other ingest scripts are missing entirely, as are `embed.py` and `run_all.py`.

**Goal:** Implement all missing scripts so that running `python run_all.py` fully populates `documents`, `chunks`, and `content_embedding` for all six collections.

---

## Source Data

```
datapipeline/sources/
├── bible/
│   ├── cpdv.json               # book→chapter→verse JSON
│   └── gutenberg-bible.txt     # Douay-Rheims plain text (PG format)
├── catechism/
│   └── ccc.json                # nossbigg/catechism-ccc-json v0.0.2
└── church-fathers/
    ├── confessions.xml         # Augustine — Confessions
    ├── city-of-god.xml         # Augustine — City of God
    ├── apostolic fathers.xml   # Apostolic Fathers collection
    ├── incarnation.xml         # Athanasius — On the Incarnation
    ├── on-the-holy-trinity.xml # On the Holy Trinity
    ├── second-century.xml      # Second century fathers
    ├── summa.xml               # Aquinas — Summa Theologica
    ├── third-century.xml       # Third century fathers
    ├── third-century-2.xml
    ├── third-century-3.xml
    └── third-fourth-century.xml
```

Canon Law, Encyclicals, and Saints have no pre-downloaded files — their scripts fetch at runtime.

---

## Architecture

**Pattern:** Approach A — independent scripts. Each `ingest/*.py` is self-contained: reads its source, parses into documents + chunks, calls `load.py` helpers. No base class. Shared ThML parsing logic lives in `ingest/common.py` (used only by `church_fathers.py`).

**Data flow:**
```
ingest/*.py  →  upsert_document() + upsert_chunk()  →  documents + chunks (embedding NULL)
embed.py     →  OpenAI batch embed  →  chunks.content_embedding populated
run_all.py   →  sequences all of the above
```

**Database contract (from load.py):**
```python
upsert_document(pool, collection, title, translation, author, year, metadata) → str (UUID)
upsert_chunk(pool, document_id, content, position, reference) → str (UUID)
```
- `translation` must be `""` for non-Bible collections (NOT NULL column default `''`)
- `content_embedding` is left NULL by all ingest scripts — `embed.py` fills it
- `position` is 0-based, scoped per document

---

## Script Specifications

### `ingest/common.py` (new)

Shared ThML XML parsing utility. Used only by `church_fathers.py`.

**Public API:**
```python
@dataclass
class ThmlDocument:
    title: str
    author: str | None
    year: int | None
    chunks: list[tuple[str, str, int]]  # (content, reference, position)

def parse_thml(path: str) -> ThmlDocument: ...
```

**Metadata extraction** from `<ThML.head>`:
- `title`: `DC.Title` element text
- `author`: `DC.Creator scheme="file-as"` text, e.g. `"Augustine, Saint, Bishop of Hippo (345-430)"` — strip the date parenthetical to get clean author name
- `year`: parse from the date parenthetical in `DC.Creator` if present (e.g. `345-430` → death year `430`)
- `authorID`: used to detect the Summa (`authorID=aquinas` + `bookID=summa`)

**Chunking — standard files (all except summa.xml):**
- Parse `div1` / `div2` hierarchy
- Chunk at `div2` (chapter) level: concatenate all `<p>` element text within each `div2`
- Skip `div1`/`div2` that are title pages, TOC, or prefaces (no `<p>` content, or content < 100 chars after stripping)
- Reference: `"{div1.title}, {div2.title}"` → e.g. `"Confessions, Book I, Chapter III"`
- Strip all XML tags, collapse whitespace, decode HTML entities

**Chunking — summa.xml:**
- Detected by `authorID == "aquinas"` and `bookID == "summa"`
- Chunk at `div4` (Article) level — each Article is one Q&A unit
- Reference: build from parent div titles → e.g. `"Summa, Part I, Q2, A3"`
- Same minimum length and text-cleaning rules

**Text cleaning:**
- Remove all XML/HTML tags with regex or `xml.etree.ElementTree`
- Decode entities (`&amp;`, `&lt;`, etc.)
- Collapse multiple whitespace to single space, strip leading/trailing

---

### `ingest/bible.py` (rewrite)

Replace the existing eBible USFM download + Gutenberg download paths with local file readers. Preserve all existing parsing and chunking logic unchanged.

**CPDV path:**
- Read `sources/bible/cpdv.json`
- Structure: `{"charset": "UTF-8", "Genesis": {"1": {"1": "text", ...}, ...}, ...}`
- Skip `"charset"` key
- For each book → chapter → group verses by `settings.BIBLE_VERSE_GROUP_SIZE` (default 4)
- Never cross chapter boundaries
- Look up testament (`OT`/`NT`) from existing `USFM_BOOK_MAP` values; if book not found in map, skip it
- Reference: `"Genesis 1:1-4"` via existing `_make_reference()`
- Document per book: `collection="bible"`, `translation="CPDV"`, `metadata={"translation": "CPDV", "testament": "OT"|"NT"}`

**Douay-Rheims path:**
- Read `sources/bible/gutenberg-bible.txt` as plain text
- Pass to existing `parse_douay_rheims()` function unchanged
- Everything downstream (chunking, upsert) is identical to existing implementation

**Removed:** `ingest_cpdv()` download logic, `_download()` helper for CPDV, USFM parser functions (`parse_usfm_book()`, `_clean_usfm_text()`), `USFM_BOOK_MAP` (keep only for testament lookup via values).

**Kept:** `DR_PG_BOOK_NAME_MAP`, `parse_douay_rheims()`, `chunk_book()`, `_make_reference()`, `_ingest_books()`, `_verify_deuterocanonicals()`, `BookVerses`, `Verse` dataclasses.

---

### `ingest/catechism.py` (new)

**Source:** `sources/catechism/ccc.json`

**JSON structure:**
```json
{
  "page_nodes": {
    "toc-102": {
      "paragraphs": [{
        "elements": [
          {"type": "ref-ccc", "ref_number": 1021},
          {"type": "text", "text": "Death puts an end..."},
          {"type": "ref", "number": 590}
        ]
      }]
    }
  }
}
```

**Parsing:**
- Iterate `data["page_nodes"].values()`
- For each page node, iterate `paragraphs`
- For each paragraph: find the first `ref-ccc` element → `para_num`; concatenate all `text` element `.text` fields → `content`
- Skip paragraphs with no `ref-ccc` element or `content` shorter than 30 chars after stripping
- Sort paragraphs by `para_num` before inserting to ensure correct `position` ordering

**Output:**
- One document: `title="Catechism of the Catholic Church"`, `author="Catholic Church"`, `year=1992`, `translation=""`, `collection="catechism"`
- One chunk per paragraph. `reference="CCC §1021"`, `position` = 0-based index in sorted order

---

### `ingest/canon_law.py` (new)

**Source:** Vatican website — scraped at runtime via `httpx`

**Step 1 — Discover pages:**
- Fetch `http://www.vatican.va/archive/cod-iuris-canonici/cic_index_en.html`
- Extract all `href` values matching `*/eng/documents/cic_lib*.html`
- Strip `#fragment` anchors, deduplicate → ~43 unique page URLs
- Prepend `http://www.vatican.va` to relative URLs

**Step 2 — Scrape each page:**
- Fetch each page URL; 1-second delay between requests
- Parse HTML with `BeautifulSoup(html, "html.parser")`
- Find the main content `<td>` (largest td, or the one containing `Can. 1`)
- Extract all `<p>` tags in order

**Step 3 — State machine parser:**
```
current_canon_num = None
current_text = []

for each <p> text:
    stripped = p.get_text(strip=True)
    if stripped.startswith("Can. "):
        flush current_canon_num + current_text as a chunk
        parse canon number from "Can. N " prefix
        current_canon_num = N
        current_text = [text after "Can. N "]
    elif stripped.startswith("§") or matches r"^\d+/" :
        current_text.append(stripped)   # sub-paragraph, belongs to current canon
    elif stripped.isupper() or len(stripped) < 10:
        pass  # section header, skip
    else:
        current_text.append(stripped)   # continuation

flush final canon
```

**Output:**
- One document: `title="Code of Canon Law (1983)"`, `author="Catholic Church"`, `year=1983`, `translation=""`, `collection="canon-law"`
- One chunk per canon. `content` = full canon text including sub-paragraphs joined with `\n`. `reference="Can. 1"`. `position` = canon number - 1 (0-based).

---

### `ingest/encyclicals.py` (new)

**Source:** papalencyclicals.net — scraped at runtime via `httpx`

**Hardcoded source list (18 documents):**
```python
ENCYCLICALS = [
    ("Rerum Novarum",        "Pope Leo XIII",        1891, "<url>"),
    ("Quadragesimo Anno",    "Pope Pius XI",         1931, "<url>"),
    ("Humani Generis",       "Pope Pius XII",        1950, "<url>"),
    ("Mater et Magistra",    "Pope John XXIII",      1961, "<url>"),
    ("Pacem in Terris",      "Pope John XXIII",      1963, "<url>"),
    ("Humanae Vitae",        "Pope Paul VI",         1968, "<url>"),
    ("Evangelii Nuntiandi",  "Pope Paul VI",         1975, "<url>"),
    ("Redemptor Hominis",    "Pope John Paul II",    1979, "<url>"),
    ("Laborem Exercens",     "Pope John Paul II",    1981, "<url>"),
    ("Veritatis Splendor",   "Pope John Paul II",    1993, "<url>"),
    ("Evangelium Vitae",     "Pope John Paul II",    1995, "<url>"),
    ("Fides et Ratio",       "Pope John Paul II",    1998, "<url>"),
    ("Deus Caritas Est",     "Pope Benedict XVI",    2005, "<url>"),
    ("Spe Salvi",            "Pope Benedict XVI",    2007, "<url>"),
    ("Caritas in Veritate",  "Pope Benedict XVI",    2009, "<url>"),
    ("Evangelii Gaudium",    "Pope Francis",         2013, "<url>"),
    ("Laudato Si",           "Pope Francis",         2015, "<url>"),
    ("Amoris Laetitia",      "Pope Francis",         2016, "<url>"),
]
```
*(Actual URLs to be confirmed during implementation by checking papalencyclicals.net.)*

**Parsing:**
- Fetch each URL; 1-second delay between requests
- Parse with BeautifulSoup; find the main content area (strip nav, headers, footers)
- Extract numbered paragraph `<p>` tags (paragraphs typically numbered inline as `1.`, `2.` or in a span)
- Group paragraphs 3 at a time into chunks
- Skip paragraphs shorter than 50 chars (headers, section titles)

**Output:**
- One document per encyclical. `collection="encyclicals"`, `translation=""`, `metadata={"pope": author, "year": year}`
- Reference: `"Laudato Si, §15-17"` (use paragraph numbers from document if parseable, else sequential)

---

### `ingest/church_fathers.py` (new)

**Source:** `sources/church-fathers/*.xml` (local ThML files)

**Algorithm:**
```python
xml_files = sorted(glob("sources/church-fathers/*.xml"))
xml_files = [f for f in xml_files if not f.endswith(".Zone.Identifier")]

for path in xml_files:
    doc = parse_thml(path)          # from common.py
    if not doc.chunks:
        log warning and skip
        continue
    doc_id = await upsert_document(
        pool,
        collection="church-fathers",
        title=doc.title,
        translation="",
        author=doc.author,
        year=doc.year,
        metadata={"source_file": basename(path)},
    )
    for content, reference, position in doc.chunks:
        await upsert_chunk(pool, doc_id, content, position, reference)
```

**Output:** One document per XML file. References and chunk boundaries determined by `common.parse_thml()`.

---

### `ingest/saints.py` (new)

**Source:** New Advent Catholic Encyclopedia — scraped at runtime

**Step 1 — Collect saint article URLs:**
- Fetch all 26 letter index pages: `https://www.newadvent.org/cathen/{letter}.htm`
- For each page, extract `<a href>` links to `cathen/*.htm` articles
- Filter: keep only links where the visible link text contains `Saint`, `St.`, `Blessed`, or `Venerable` (case-insensitive)
- Deduplicate

**Step 2 — Scrape each article:**
- Fetch article URL; 1-second delay between requests
- Parse with BeautifulSoup
- Extract `<h1>` or `<h2>` as saint name/title
- Extract main article body text (the `<div id="content">` or equivalent — inspect during implementation)
- Strip footnotes, navigation links, citation blocks
- Split into ~400-word chunks (split on sentence boundaries, not mid-sentence)
- Skip articles with total content < 100 chars (stubs)

**Output:**
- One document per saint. `collection="saints"`, `title` = saint name, `author="Catholic Encyclopedia"`, `year=1913`, `translation=""`
- Reference: `"St. Francis of Assisi — Catholic Encyclopedia"`
- `metadata={"url": article_url}`

---

### `embed.py` (new)

**Algorithm:**
```python
# 1. Fetch all un-embedded chunks
rows = await pool.fetch(
    "SELECT id, content FROM chunks WHERE content_embedding IS NULL ORDER BY id"
)

# 2. Batch through OpenAI
BATCH_SIZE = 100
for i in range(0, len(rows), BATCH_SIZE):
    batch = rows[i:i+BATCH_SIZE]
    texts = [r["content"] for r in batch]
    vectors = await embed_texts(client, texts)  # openai.AsyncOpenAI client created in embed.py

    async with pool.acquire() as conn:
        async with conn.transaction():
            for row, vec in zip(batch, vectors):
                await conn.execute(
                    "UPDATE chunks SET content_embedding = $1::vector WHERE id = $2",
                    "[" + ",".join(str(v) for v in vec) + "]",
                    row["id"],
                )

# 3. Report
print(f"Embedded {len(rows)} chunks.")
```

**Notes:**
- Uses `openai.AsyncOpenAI` with `text-embedding-3-large`, `dimensions=1536` — same model as the backend
- Reads `OPENAI_API_KEY` from `.env` via `config.py`
- `--missing-only` flag is the default behavior (always skips already-embedded chunks)
- `--dry-run` flag: prints count of un-embedded chunks and exits without calling OpenAI
- Handles OpenAI rate limit errors with exponential backoff (max 3 retries)

---

### `run_all.py` (new)

```python
PIPELINE = [
    ("bible",          "ingest.bible",          ingest_bible),
    ("catechism",      "ingest.catechism",      ingest_catechism),
    ("canon-law",      "ingest.canon_law",      ingest_canon_law),
    ("encyclicals",    "ingest.encyclicals",    ingest_encyclicals),
    ("church-fathers", "ingest.church_fathers", ingest_church_fathers),
    ("saints",         "ingest.saints",         ingest_saints),
    ("embed",          "embed",                 run_embed),
]
```

- Each ingest module exposes an async `main(pool)` function
- `run_all.py` initialises the pool once, runs each step in order, prints timing
- `--collection <name>` flag: run only that collection's ingest + embed
- `--skip-embed` flag: run all ingest scripts but skip the embedding step

---

## Error Handling

- **Network failures** (canon_law, encyclicals, saints): `httpx` timeout of 30s per request. On failure, log the URL and skip — do not abort the whole run. Print a summary of skipped URLs at the end.
- **Malformed source files** (church_fathers): if `parse_thml()` raises, log the filename and skip. Continue with remaining files.
- **Short/empty chunks**: enforced by minimum length checks in each parser — silently skipped.
- **Duplicate runs**: `upsert_document` and `upsert_chunk` both use `ON CONFLICT DO UPDATE` — safe to re-run any script.
- **OpenAI failures** (embed.py): exponential backoff, max 3 retries per batch. On final failure, log chunk IDs and continue — they will be picked up on next `embed.py` run since `content_embedding` remains NULL.

---

## Dependencies

All already present in `datapipeline/requirements.txt` — no additions needed:
- `httpx>=0.27.0` — HTTP client for scraping
- `beautifulsoup4>=4.12.0` + `lxml>=5.0.0` — HTML parsing
- `tqdm>=4.66.0` — progress bars
- `asyncpg>=0.29.0` — DB
- `openai>=1.0.0` — embeddings
- `python-dotenv>=1.0.0` — env loading

---

## Verification

After running the full pipeline:
```sql
-- Check document counts per collection
SELECT collection, count(*) FROM documents GROUP BY collection;

-- Check chunk counts and embedding coverage
SELECT d.collection, count(c.id) as chunks,
       count(c.content_embedding) as embedded
FROM chunks c JOIN documents d ON c.document_id = d.id
GROUP BY d.collection;

-- Spot-check a canon
SELECT content, reference FROM chunks c
JOIN documents d ON c.document_id = d.id
WHERE d.collection = 'canon-law' AND c.reference = 'Can. 1';

-- Spot-check a CCC paragraph
SELECT content FROM chunks c
JOIN documents d ON c.document_id = d.id
WHERE d.collection = 'catechism' AND c.reference = 'CCC §1';
```

Expected approximate chunk counts:
| Collection | Documents | Chunks (approx) |
|---|---|---|
| bible | 146 (73 books × 2 translations) | ~35,000 |
| catechism | 1 | ~2,800 |
| canon-law | 1 | ~1,752 |
| encyclicals | 18 | ~2,500 |
| church-fathers | 11 (one per XML file) | ~3,000 |
| saints | ~500 | ~1,500 |
