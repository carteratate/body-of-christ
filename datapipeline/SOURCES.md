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

## Re-ingesting a collection

Each collection has a `build_documents()` adapter (returning `list[Document]` of clean
`Passage`s with anchors, chapter_keys, and cleaning) registered in `run_collection.py`
`BUILDERS`. To (re-)ingest one:

```bash
python3 run_collection.py --collection <name> --target both --clean
```

`--clean` clears the collection's existing rows (via `reader_writer.clear_collection`)
and deletes its old Qdrant points (via `delete_collection_points`) before writing, so a
re-chunk never leaves superseded vectors behind.

Note on the four vendored web collections (`encyclicals`, `canon-law`, `councils`,
`medieval`): adapters read the vendored local files under `sources/<collection>/`, not
the network. Re-acquire the raw sources with
`python3 scripts/vendor_sources.py --collection all` if they are missing.
