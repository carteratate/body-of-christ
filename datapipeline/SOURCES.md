# Corpus Sources & Provenance

Status of each collection's source material and its dual-pipeline ingestion
(`run_collection.py --collection <name> --target both --clean`).

| Collection | Source | Re-ingested (dual pipeline) | Notes |
|---|---|---|---|
| **bible** | local `sources/bible/eng-web-c_usfm/` (+ pericope JSON) | ✅ | WEB-C; passage = pericope clamped to chapter |
| **catechism** | local `sources/catechism/ccc.json` (nossbigg/catechism-ccc-json) | ✅ | three-tier chunking; TOC fragments dropped |
| **church-fathers** | local `sources/church-fathers/*.xml` (ANF/NPNF ThML) | ✅ | one document per (father, work); book-structured works (City of God, etc.) flattened to `Book N · Chapter M` |
| **summa** | local `sources/church-fathers/summa.xml` (ThML) | ✅ | one passage per article part; apparatus expanded |
| **encyclicals** | local `sources/encyclicals/*.html` (vendored from papalencyclicals.net / vatican.va) | ✅ | one doc per encyclical (18); one passage per §; section or §-bucket chapters; footnotes stripped |
| **canon-law** | local `sources/canon-law/*.html` (vendored from vatican.va) | ✅ | single doc; one passage per canon (1,747); Book by canon-range; Book/Title/Chapter chapters (233) |
| **councils** | local `sources/councils/*.html` (vendored from papalencyclicals.net / vatican.va) | ✅ | one doc per council / Vatican II document (36); canon + §-paragraph passages |
| **medieval** | local `sources/medieval/*.xml` (vendored from ccel.org ThML) | ✅ | one doc per (author, work) (6); reuses the church-fathers ThML builder |

**Vendoring:** the four web-sourced collections were vendored to `sources/<collection>/`
(gitignored, with a `manifest.json` recording provenance) via
`scripts/vendor_sources.py`; adapters read these local files, not the network.
Re-acquire with `python3 scripts/vendor_sources.py --collection all`.

## Reality of the remaining four

These collections are **not** sourced from local files — their old ingest scripts
(`ingest/encyclicals.py`, `canon_law.py`, `councils.py`, `medieval.py`) **download
from live web URLs** at ingest time (URLs hard-coded in each script) and parse them
(HTML via BeautifulSoup for the first three; ThML for medieval). They still hold their
**pre-rework** chunks in Supabase/Qdrant — no `anchor`/`chapter_key`, old-style
references/casing — so the new reader cannot open them (they remain searchable via the
legacy Qdrant points).

## To complete each one

Add a `build_documents()` adapter returning `list[Document]` of clean `Passage`s
(anchors, chapter_keys, cleaning), register it in `run_collection.py` `BUILDERS`, then
run `python3 run_collection.py --collection <name> --target both --clean`.

The old scripts already contain the fetch + parse logic to reuse:
- **medieval** — uses `parse_thml_string()`; closest to the church-fathers adapter. Lowest effort.
- **encyclicals / councils / canon-law** — each has a custom BeautifulSoup parser that
  emits `(content, reference, position, metadata)`; the adapter wraps that, applies the
  cleaners, and assigns anchors/chapter_keys.

Risk: ingestion depends on those external sites still serving the same pages.
