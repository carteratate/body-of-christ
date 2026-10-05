# Corpus Sources & Provenance

Status of each collection's source material and its publication to both stores
(`run_collection.py --collection <name> --target both`).

| Collection | Source | Re-published (both stores) | Notes |
|---|---|---|---|
| **bible** | local `sources/bible/eng-web-c_usfm/` (+ pericope JSON) | ✅ | WEB-C; passage = pericope clamped to chapter |
| **catechism** | local `sources/catechism/ccc.json` (nossbigg/catechism-ccc-json) | ✅ | three-tier chunking; TOC fragments dropped |
| **church-fathers** | local `sources/church-fathers/*.xml` (vendored CCEL ANF/NPNF ThML) | ✅ | one document per (father, work) (128); book-structured works (City of God, etc.) flattened to `Book N · Chapter M` |
| **summa** | local `sources/summa/summa.xml` (ThML) | ✅ | one passage per article part; apparatus expanded |
| **encyclicals** | local `sources/encyclicals/*.html` (vendored from papalencyclicals.net / vatican.va) | ✅ | one doc per encyclical (131); one passage per §; section or §-bucket chapters; footnotes stripped |
| **apostolic-exhortations** | local `sources/apostolic-exhortations/*.html` (vendored from vatican.va) | ✅ | one document per exhortation (30); numbered-paragraph passages |
| **papal-documents** | local `sources/papal-documents/*.html` (vendored from vatican.va) | ✅ | one document per papal text (14); numbered-paragraph passages |
| **canon-law** | local `sources/canon-law/*.html` (vendored from vatican.va) | ✅ | single doc; one passage per canon (1,747); Book by canon-range; Book/Title/Chapter chapters (233) |
| **councils** | local `sources/councils/*.html` (vendored from papalencyclicals.net / vatican.va) | ✅ | one doc per council / Vatican II document (36); canon + §-paragraph passages |
| **medieval** | local `sources/medieval/*.xml` (vendored from ccel.org ThML) | ✅ | one doc per (author, work) (6); reuses the church-fathers ThML builder |

**Vendoring:** web-sourced collections are vendored to `sources/<collection>/`
(gitignored, with a `manifest.json` recording provenance) via
`scripts/vendor_sources.py`; adapters read these local files, not the network.
Re-acquire with `python3 scripts/vendor_sources.py --collection all`.

**Document counts** in the table are what the `publication.py` adapter emits, not the
number of source files — one file can yield several documents (the medieval
`proslogium-monologium-and-cur-deus-homo.xml` produces three). Verified 2026-09-17.
Re-check without touching either store:

```bash
python3 -c "from publication import SOURCE_ADAPTERS as A; d=A['encyclicals'](); print(len(d))"
```

**Adapters read `manifest.json`, not the directory**, so a vendored file that no
manifest entry references is never published. The exception is church-fathers:
`ingest/church_fathers.build_all()` builds every `*.xml` in `sources/church-fathers/`
except `summa.xml`, whatever its manifest says. Every vendored file, published or not, is
pinned by hash in the tracked `source_lock.json`; its `role` says which files an adapter
reads (`adapter-input`, `adapter-auxiliary`) and which are on disk but unpublished
(`vendored-unregistered`, each with a `note` giving the reason). Check the vendored
files against it with `python3 scripts/source_lock.py --verify`; after a deliberate
change, rewrite it with `--write` (`vendor_sources.py` does this itself for the
collection it vendors). The edition and rights status of each published work are in
`rights_inventory.json`.

Approved downloads that no PR has ingested yet wait in `sources/_incoming/<path>` (locked with role `vendored-unregistered`), where `<path>` is the file's final place under `sources/` (R6's "Vendored as" column). No adapter reads `_incoming/`. The ingesting PR moves the file unchanged to `sources/<path>` and runs `python3 scripts/source_lock.py --write`, which keeps the file's download date and URL because its hash matches the `_incoming/` entry. Carter chose this on 5 Oct 2026 because the church-fathers adapter builds every `*.xml` in its folder, so a file dropped there early would be published ahead of its PR.

## Publishing a collection

Each entry in `publication.py`'s `SOURCE_ADAPTERS` registry returns a `list[Document]`
of clean `Passage`s with anchors, chapter keys, and source-specific cleaning. To
publish one:

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

The publish lock (`PUBLISH_LOCK.json`, item 0.4) refuses every live write unless a
reviewed PR has listed the collection and release; pass `--release <release>` with
the run. `--dry-run` builds and checks a collection without writing and needs no
entry. Local rehearsals, with both the database and Qdrant on this machine, are
exempt. See README.md, "Publish one collection".

Vendored adapters read the local files under `sources/<collection>/`, not the network.
Re-acquire the raw sources with
`python3 scripts/vendor_sources.py --collection all` if they are missing.
