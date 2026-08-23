# Corpus Sources & Provenance

Status of each collection's source material and its publication to both stores
(`run_collection.py --collection <name> --target both`).

| Collection | Source | Re-published (both stores) | Notes |
|---|---|---|---|
| **bible** | local `sources/bible/eng-web-c_usfm/` (+ pericope JSON) | ✅ | WEB-C; passage = pericope clamped to chapter |
| **catechism** | local `sources/catechism/ccc.json` (nossbigg/catechism-ccc-json) | ✅ | three-tier chunking; TOC fragments dropped |
| **church-fathers** | local `sources/church-fathers/*.xml` (vendored CCEL ANF/NPNF ThML) | ✅ | one document per (father, work); book-structured works (City of God, etc.) flattened to `Book N · Chapter M` |
| **summa** | local `sources/summa/summa.xml` (ThML) | ✅ | one passage per article part; apparatus expanded |
| **encyclicals** | local `sources/encyclicals/*.html` (vendored from papalencyclicals.net / vatican.va) | ✅ | one doc per encyclical (18); one passage per §; section or §-bucket chapters; footnotes stripped |
| **apostolic-exhortations** | local `sources/apostolic-exhortations/*.html` (vendored from vatican.va) | ✅ | one document per exhortation; numbered-paragraph passages |
| **papal-documents** | local `sources/papal-documents/*.html` (vendored from vatican.va) | ✅ | one document per papal text; numbered-paragraph passages |
| **canon-law** | local `sources/canon-law/*.html` (vendored from vatican.va) | ✅ | single doc; one passage per canon (1,747); Book by canon-range; Book/Title/Chapter chapters (233) |
| **councils** | local `sources/councils/*.html` (vendored from papalencyclicals.net / vatican.va) | ✅ | one doc per council / Vatican II document (36); canon + §-paragraph passages |
| **medieval** | local `sources/medieval/*.xml` (vendored from ccel.org ThML) | ✅ | one doc per (author, work) (6); reuses the church-fathers ThML builder |

**Vendoring:** web-sourced collections are vendored to `sources/<collection>/`
(gitignored, with a `manifest.json` recording provenance) via
`scripts/vendor_sources.py`; adapters read these local files, not the network.
Re-acquire with `python3 scripts/vendor_sources.py --collection all`.

## Publishing a collection

Each collection has a `build_documents()` adapter (returning `list[Document]` of clean
`Passage`s with anchors, chapter_keys, and cleaning) registered in `publication.py`
`SOURCE_ADAPTERS`. To publish one:

```bash
python3 run_collection.py --collection <name> --target both
```

The normal command upserts before pruning in both stores. It does not empty either
store first. `--reset-search-index` explicitly deletes the collection's old Qdrant
points before writing rebuilt Passages to the search index. `--wipe-reader` is the
destructive Postgres rebuild option and requires
`--confirm-reader-wipe <collection>` with an exact collection-name match. Routine
publication preserves stable Passage IDs, so bookmarks and search history survive when
the source adapter still emits those Passages.

Vendored adapters read the local files under `sources/<collection>/`, not the network.
Re-acquire the raw sources with
`python3 scripts/vendor_sources.py --collection all` if they are missing.
