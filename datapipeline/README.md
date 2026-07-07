# TheoCorpus — Data Pipeline

Ingests Catholic theology source texts (Bible, Catechism, Encyclicals, Church Fathers, Lives of Saints) into the Supabase Postgres + pgvector database for the V2 RAG feature.

## ⚠️ Data Required Before Running

**Do not run any scripts until you have the source data files.**

The ingestion scripts download or read source data that must be obtained separately:

| Script | Requires |
|--------|---------|
| `ingest/bible.py` | USFM files (CPDV from eBible.org) + Douay-Rheims HTML (Project Gutenberg #8300) |
| `ingest/catechism.py` | `catechism-ccc-json` GitHub repo cloned locally |
| `ingest/encyclicals.py` | Network access to papalencyclicals.net |
| `ingest/church_fathers.py` | CCEL ThML files |
| `ingest/saints.py` | Network access (Butler's Lives + Wikidata SPARQL) |
| `embed.py` | Populated `chunks` table (run ingest scripts first) |

**Current status:** Schema migration 0008 must be applied to Supabase before any script will work.
See `supabase/migrations/0008_documents_add_translation.sql`.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in DATABASE_URL and OPENAI_API_KEY
```

## Run Order

Scripts must be run in this order so that document rows exist before chunks are embedded:

1. Bible
2. Catechism
3. Encyclicals
4. Church Fathers
5. Saints
6. Embed

## Running the Full Pipeline

```bash
python run_all.py
```

## Single Collection

```bash
python run_all.py --collection bible
```

## Incremental Update (Single Source)

```bash
python ingest/encyclicals.py --source-url <url>
```

## Re-Embed Missing Chunks Only

```bash
python embed.py --missing-only
```

## Run a Single Ingestion Script Directly

```bash
# Run a single ingestion script
python ingest/catechism.py
```
