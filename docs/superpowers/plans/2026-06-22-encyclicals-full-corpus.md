# Encyclicals Full Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 30 missing Catholic encyclicals to the Body of Christ corpus (Leo XIII through Francis), bringing the collection from 18 to 48 documents.

**Architecture:** The existing dual-pipeline is already wired for encyclicals. This plan only touches the ENCYCLICALS manifest list in `vendor_sources.py`, the test count assertion, and then runs the existing `vendor_sources.py` + `run_collection.py` pipeline. No parser changes needed — the parser already handles both papalencyclicals.net (inline `N.`) and vatican.va (bold heading + body) HTML layouts.

**Tech Stack:** Python 3, httpx (HTTP client), BeautifulSoup (HTML parsing), asyncpg (Supabase writer), qdrant-client (Qdrant writer).

## Global Constraints

- All new entries use exactly the same 4-tuple format as existing ENCYCLICALS: `(title, author, year, url)`
- `author` must be the exact string form used by existing entries: `"Pope Leo XIII"`, `"Pope Pius X"`, etc.
- Slugs are auto-derived by `_slug(title)` — do not set them manually
- Sources are vendored to `datapipeline/sources/encyclicals/` (gitignored) before ingestion
- `run_collection.py --collection encyclicals --target both --clean` does the full re-ingest; run from `datapipeline/`
- Never re-embed unless `--target both` or `--target search` is passed explicitly

---

## File Map

| File | Change |
|---|---|
| `datapipeline/scripts/vendor_sources.py` | Add 30 entries to `ENCYCLICALS` list (lines 57–76) |
| `datapipeline/tests/test_encyclicals.py` | Update `assert len(docs) == 18` → `== 48`; rename test |

---

### Task 1: Expand the ENCYCLICALS manifest list

**Files:**
- Modify: `datapipeline/scripts/vendor_sources.py:57-76`

**Interfaces:**
- Produces: `vendor_encyclicals()` downloads 30 new HTML files; `manifest.json` grows to 48 entries

- [ ] **Step 1: Replace the ENCYCLICALS list in vendor_sources.py**

Replace lines 57–76 (the current 18-entry list) with the full 48-entry list:

```python
ENCYCLICALS = [
    # Pope Leo XIII (1878–1903)
    ("Aeterni Patris",            "Pope Leo XIII",     1879, "https://www.papalencyclicals.net/leo13/l13arpa.htm"),
    ("Immortale Dei",             "Pope Leo XIII",     1885, "https://www.papalencyclicals.net/leo13/l13sta.htm"),
    ("Libertas",                  "Pope Leo XIII",     1888, "https://www.papalencyclicals.net/leo13/l13liber.htm"),
    ("Rerum Novarum",             "Pope Leo XIII",     1891, "https://www.papalencyclicals.net/leo13/l13rerum.htm"),
    ("Providentissimus Deus",     "Pope Leo XIII",     1893, "https://www.papalencyclicals.net/leo13/l13provi.htm"),
    ("Divinum Illud Munus",       "Pope Leo XIII",     1897, "https://www.papalencyclicals.net/leo13/l13divin.htm"),
    ("Mirae Caritatis",           "Pope Leo XIII",     1902, "https://www.papalencyclicals.net/leo13/l13mirae.htm"),
    # Pope Pius X (1903–1914)
    ("Pascendi Dominici Gregis",  "Pope Pius X",       1907, "https://www.papalencyclicals.net/pius10/p10pasce.htm"),
    # Pope Benedict XV (1914–1922)
    ("Spiritus Paraclitus",       "Pope Benedict XV",  1920, "https://www.papalencyclicals.net/ben15/b15sp.htm"),
    # Pope Pius XI (1922–1939)
    ("Quas Primas",               "Pope Pius XI",      1925, "https://www.papalencyclicals.net/pius11/p11quasp.htm"),
    ("Casti Connubii",            "Pope Pius XI",      1930, "https://www.papalencyclicals.net/pius11/p11casti.htm"),
    ("Quadragesimo Anno",         "Pope Pius XI",      1931, "https://www.papalencyclicals.net/pius11/p11quadr.htm"),
    ("Mit Brennender Sorge",      "Pope Pius XI",      1937, "https://www.papalencyclicals.net/pius11/p11brenn.htm"),
    ("Divini Redemptoris",        "Pope Pius XI",      1937, "https://www.papalencyclicals.net/pius11/p11divre.htm"),
    # Pope Pius XII (1939–1958)
    ("Mystici Corporis Christi",  "Pope Pius XII",     1943, "https://www.papalencyclicals.net/pius12/p12mystc.htm"),
    ("Divino Afflante Spiritu",   "Pope Pius XII",     1943, "https://www.papalencyclicals.net/pius12/p12divin.htm"),
    ("Mediator Dei",              "Pope Pius XII",     1947, "https://www.papalencyclicals.net/pius12/p12media.htm"),
    ("Humani Generis",            "Pope Pius XII",     1950, "https://www.papalencyclicals.net/pius12/p12human.htm"),
    ("Munificentissimus Deus",    "Pope Pius XII",     1950, "https://www.papalencyclicals.net/pius12/p12munif.htm"),
    # Pope John XXIII (1958–1963)
    ("Mater et Magistra",         "Pope John XXIII",   1961, "https://www.papalencyclicals.net/john23/j23mater.htm"),
    ("Pacem in Terris",           "Pope John XXIII",   1963, "https://www.papalencyclicals.net/john23/j23pacem.htm"),
    # Pope Paul VI (1963–1978)
    ("Ecclesiam Suam",            "Pope Paul VI",      1964, "https://www.papalencyclicals.net/paul06/p6eccles.htm"),
    ("Mysterium Fidei",           "Pope Paul VI",      1965, "https://www.papalencyclicals.net/paul06/p6myster.htm"),
    ("Populorum Progressio",      "Pope Paul VI",      1967, "https://www.papalencyclicals.net/paul06/p6popu.htm"),
    ("Humanae Vitae",             "Pope Paul VI",      1968, "https://www.papalencyclicals.net/paul06/p6humana.htm"),
    ("Evangelii Nuntiandi",       "Pope Paul VI",      1975, "https://www.vatican.va/content/paul-vi/en/apost_exhortations/documents/hf_p-vi_exh_19751208_evangelii-nuntiandi.html"),
    # Pope John Paul II (1978–2005)
    ("Redemptor Hominis",         "Pope John Paul II", 1979, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_04031979_redemptor-hominis.html"),
    ("Dives in Misericordia",     "Pope John Paul II", 1980, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_30111980_dives-in-misericordia.html"),
    ("Laborem Exercens",          "Pope John Paul II", 1981, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_14091981_laborem-exercens.html"),
    ("Dominum et Vivificantem",   "Pope John Paul II", 1986, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_18051986_dominum-et-vivificantem.html"),
    ("Redemptoris Mater",         "Pope John Paul II", 1987, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_25031987_redemptoris-mater.html"),
    ("Sollicitudo Rei Socialis",  "Pope John Paul II", 1987, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_30121987_sollicitudo-rei-socialis.html"),
    ("Redemptoris Missio",        "Pope John Paul II", 1990, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_07121990_redemptoris-missio.html"),
    ("Centesimus Annus",          "Pope John Paul II", 1991, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_01051991_centesimus-annus.html"),
    ("Veritatis Splendor",        "Pope John Paul II", 1993, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_06081993_veritatis-splendor.html"),
    ("Evangelium Vitae",          "Pope John Paul II", 1995, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_25031995_evangelium-vitae.html"),
    ("Ut Unum Sint",              "Pope John Paul II", 1995, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_25051995_ut-unum-sint.html"),
    ("Fides et Ratio",            "Pope John Paul II", 1998, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_14091998_fides-et-ratio.html"),
    ("Ecclesia de Eucharistia",   "Pope John Paul II", 2003, "https://www.vatican.va/content/john-paul-ii/en/encyclicals/documents/hf_jp-ii_enc_20030417_eccl-de-euch.html"),
    # Pope Benedict XVI (2005–2013)
    ("Deus Caritas Est",          "Pope Benedict XVI", 2005, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20051225_deus-caritas-est_en.html"),
    ("Spe Salvi",                 "Pope Benedict XVI", 2007, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20071130_spe-salvi_en.html"),
    ("Caritas in Veritate",       "Pope Benedict XVI", 2009, "http://www.vatican.va/holy_father/benedict_xvi/encyclicals/documents/hf_ben-xvi_enc_20090629_caritas-in-veritate_en.html"),
    # Pope Francis (2013–2025)
    ("Lumen Fidei",               "Pope Francis",      2013, "https://www.vatican.va/content/francesco/en/encyclicals/documents/papa-francesco_20130629_enciclica-lumen-fidei.html"),
    ("Evangelii Gaudium",         "Pope Francis",      2013, "https://www.vatican.va/content/francesco/en/apost_exhortations/documents/papa-francesco_esortazione-ap_20131124_evangelii-gaudium.html"),
    ("Laudato Si",                "Pope Francis",      2015, "https://www.vatican.va/content/francesco/en/encyclicals/documents/papa-francesco_20150524_enciclica-laudato-si.html"),
    ("Fratelli Tutti",            "Pope Francis",      2020, "https://www.vatican.va/content/francesco/en/encyclicals/documents/papa-francesco_20201003_enciclica-fratelli-tutti.html"),
    ("Dilexit Nos",               "Pope Francis",      2024, "https://www.vatican.va/content/francesco/en/encyclicals/documents/20241024-enciclica-dilexit-nos.html"),
    # Pope Leo XIV (2025–present)
    ("Magnifica Humanitas",       "Pope Leo XIV",      2026, "https://www.vatican.va/content/leo-xiv/en/encyclicals/documents/20260515-magnifica-humanitas.html"),
]
```

- [ ] **Step 2: Run vendor_sources.py to download the 30 new HTML files**

```bash
cd datapipeline && python3 scripts/vendor_sources.py --collection encyclicals
```

Expected: Downloads ~30 new files, skips the 18 already cached. Final line: `manifest: manifest.json (48 entries)`. Any `WARNING: failed` lines for individual URLs need the URL corrected (see Task 2).

- [ ] **Step 3: Commit**

```bash
git add datapipeline/scripts/vendor_sources.py
git commit -m "feat(encyclicals): expand manifest to 48 encyclicals (Leo XIII through Leo XIV)"
```

---

### Task 2: Update test count and re-run tests

**Files:**
- Modify: `datapipeline/tests/test_encyclicals.py:61-65`

**Interfaces:**
- Consumes: `build_documents()` from `ingest/encyclicals.py` — returns `list[Document]`

- [ ] **Step 1: Update the document count assertion and test name**

In `datapipeline/tests/test_encyclicals.py`, replace:

```python
@pytest.mark.skipif(not _vendored, reason="encyclicals not vendored")
def test_all_eighteen_documents_produce_passages():
    docs = build_documents()
    assert len(docs) == 18
    for d in docs:
        assert d.passages, f"{d.title} produced no passages"
```

With:

```python
@pytest.mark.skipif(not _vendored, reason="encyclicals not vendored")
def test_all_documents_produce_passages():
    docs = build_documents()
    assert len(docs) == 48
    for d in docs:
        assert d.passages, f"{d.title} produced no passages"
```

- [ ] **Step 2: Run the full test suite**

```bash
cd datapipeline && QDRANT_URL="http://localhost:6333" QDRANT_API_KEY="test" .venv/bin/python -m pytest tests/test_encyclicals.py -v
```

Expected: All tests pass. If `test_all_documents_produce_passages` fails with a count mismatch (e.g., `assert 46 == 48`), it means some URLs failed to download in Task 1 — check vendor output for `WARNING` lines and fix those URLs in `vendor_sources.py`, then re-run vendor and test.

- [ ] **Step 3: Commit**

```bash
git add datapipeline/tests/test_encyclicals.py
git commit -m "test(encyclicals): update document count assertion to 48"
```

---

### Task 3: Re-ingest the encyclicals collection

**Files:**
- No source changes — this runs the existing pipeline against the expanded manifest

**Interfaces:**
- Consumes: `sources/encyclicals/manifest.json` (48 entries), vendored HTML files
- Produces: Upserted rows in Supabase `documents` + `chunks` tables; vectors in Qdrant `encyclicals` collection

- [ ] **Step 1: Run full re-ingest with --clean to replace all existing data**

```bash
cd datapipeline && python3 run_collection.py --collection encyclicals --target both --clean
```

`--clean` deletes the old Qdrant points and Supabase rows for the collection before re-inserting. This avoids duplicate documents from the 18 already-ingested encyclicals. Expected output ends with summary lines showing `48` documents and several thousand passages upserted.

- [ ] **Step 2: Verify in Supabase**

```bash
cd datapipeline && python3 -c "
import asyncio, asyncpg, os
from dotenv import load_dotenv
load_dotenv('.env')

async def check():
    pool = await asyncpg.create_pool(os.environ['DATABASE_URL'], statement_cache_size=0)
    row = await pool.fetchrow(\"SELECT COUNT(DISTINCT d.id) AS docs, COUNT(c.id) AS chunks FROM documents d JOIN chunks c ON c.document_id = d.id WHERE d.collection = 'encyclicals'\")
    print(f'docs={row[\"docs\"]}  chunks={row[\"chunks\"]}')
    await pool.close()

asyncio.run(check())
"
```

Expected: `docs=48  chunks=<number in range 4000–12000>`.

- [ ] **Step 3: Commit**

```bash
git add -p  # nothing to stage — pipeline run has no file output
git commit --allow-empty -m "feat(encyclicals): ingest full 48-encyclical corpus into Supabase + Qdrant"
```

(Or skip this commit if you prefer not to create empty commits — the vendor_sources and test commits already tell the story.)
