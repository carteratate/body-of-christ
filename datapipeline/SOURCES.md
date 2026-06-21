# Corpus Sources & Provenance

Status of each collection's source material and its dual-pipeline ingestion
(`run_collection.py --collection <name> --target both --clean`).

| Collection | Local source | Re-ingested (dual pipeline) | Notes |
|---|---|---|---|
| **bible** | `sources/bible/eng-web-c_usfm/` (+ `PericopeGroupedKJVVerses.json`) | ✅ | WEB-C; passage = pericope clamped to chapter |
| **catechism** | `sources/catechism/ccc.json` (nossbigg/catechism-ccc-json) | ✅ | three-tier chunking; TOC fragments dropped |
| **church-fathers** | `sources/church-fathers/*.xml` (ANF/NPNF ThML) | ✅ | one document per (father, work); book-structured works (City of God, etc.) flattened to `Book N · Chapter M` |
| **summa** | `sources/church-fathers/summa.xml` (ThML) | ✅ | one passage per article part (Objection / On the contrary / I answer that / Reply); apparatus expanded |
| **encyclicals** | ❌ **MISSING — re-acquire** | ⛔ blocked | data exists in DB from a prior ingest; no local source to rebuild through the dual pipeline |
| **canon-law** | ❌ **MISSING — re-acquire** | ⛔ blocked | same as above |
| **councils** | ❌ **MISSING — re-acquire** | ⛔ blocked | same as above; Vatican II grouped on the Sources page |
| **medieval** | ⤓ **re-download** from ccel.org (URLs in `ingest/medieval.py`) | ⛔ blocked | basic_works.xml (Anselm), consolation.xml (Boethius), loving_god.xml (Bernard), imitation.xml (Kempis) |

## To complete the remaining collections

1. **medieval** — re-download the ccel.org XML listed in `ingest/medieval.py` into
   `sources/medieval/`, then write a `build_documents()` adapter following the
   church-fathers pattern (ThML → per-work passages) and run the orchestrator.
2. **encyclicals / canon-law / councils** — locate and vendor the original sources
   under `sources/<collection>/`, add a `build_document(s)` adapter (see
   `ingest/catechism.py` and `ingest/church_fathers.py` for patterns), then run
   `run_collection.py --collection <name> --target both --clean`.

Until then these four keep their **pre-rework** chunks in Supabase/Qdrant (no
`anchor`/`chapter_key`), so the new reader will not open them; they remain
searchable via the legacy points.
