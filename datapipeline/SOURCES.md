# Corpus Sources & Provenance

Status of each collection's source material and its publication to both stores
(`publish.py`; see "Publishing a collection" below).

Rows are sources (`publication.SOURCE_BUILDS`). Since 5.1b.3 the three papal sources
publish together as `papal`, `canon-law` as `church-law`, and `medieval` as
`theologians`, except Boethius, who publishes with `church-fathers` (README, "Source
data").

| Source | Source files | Re-published (both stores) | Notes |
|---|---|---|---|
| **bible** | local `sources/bible/eng-web-c_usfm/` (+ pericope JSON) | ✅ | WEB-C; passage = pericope clamped to chapter |
| **catechism** | structure: local `sources/catechism/ccc.json` (nossbigg/catechism-ccc-json, vatican.va's English); words and footnotes: local `sources/catechism/us-edition/ccc-us.json`, the US edition from Catholic Cross Reference's Catechism search, built once by `scripts/fetch_us_catechism.py` (#279), then corrected to the USCCB's current online book by the reviewed table `ingest/catechism_corrections.json` (each entry checked against the page image) | ✅ | three-tier chunking; TOC fragments dropped; US text aligned by paragraph number (`ingest/catechism_us.py`); footnotes in `metadata.footnotes` |
| **catechism** (Compendium) | local `sources/catechism/compendium-ccc.html`, the Compendium of the Catechism's English page on vatican.va (5.5) | not yet | `ingest/catechism_compendium.py`; one passage per question (598) with its answer; the CCC paragraph numbers under each question in `metadata.ccc_references`; the motu proprio, introduction, appendix and texts between sections left out |
| **catechism** (Roman Catechism) | McHugh and Callan's 1923 translation, Internet Archive scan `sources/catechism/catechismofcounc0000jose/` (`_djvu.xml`, page map), read through 1.2f's OCR tool into the tracked `ocr/texts/mchugh-callan-roman-catechism.json`; Fordham's transcription (`sources/catechism/fordham-romancat.html`) only checks it (5.5) | not yet | `ingest/roman_catechism.py`; one passage per translators' section, their headings as labels; notes, introduction and appendices left out |
| **church-fathers** | local `sources/church-fathers/*.xml` (vendored CCEL ANF/NPNF ThML) | ✅ | one document per (father, work) (128); book-structured works (City of God, etc.) flattened to `Book N · Chapter M` |
| **summa** | local `sources/summa/summa.xml` (ThML) | ✅ | one passage per article part; apparatus expanded |
| **encyclicals** | local `sources/encyclicals/*.html` (vendored from papalencyclicals.net / vatican.va) | ✅ | one doc per encyclical (131); one passage per §; section or §-bucket chapters; footnotes stripped |
| **apostolic-exhortations** | local `sources/apostolic-exhortations/*.html` (vendored from vatican.va) | ✅ | one document per exhortation (31); numbered-paragraph passages; Amoris Laetitia read from vatican.va's PDF (`ingest/papal_pdf.py`, 5.4) |
| **papal-documents** | local `sources/papal-documents/*.html` (vendored from vatican.va) | ✅ | one document per papal text (15, with Ubicumque et Semper from 5.4); numbered-paragraph passages |
| **church-law** | local `sources/church-law/`: Universi Dominici Gregis as amended in 2013 (vatican.va HTML), its 1996 original (vatican.va PDF) and Normas Nonnullas (vatican.va HTML), 5.4 | not yet | `ingest/universal_law.py`; one passage per number; the 1996 text and Normas Nonnullas are history, `searchable = false` |
| **canon-law** | local `sources/canon-law/*.html` (vendored from vatican.va) | ✅ | single doc; one passage per canon (1,747); Book by canon-range; Book/Title/Chapter chapters (233) |
| **councils** | local `sources/councils/*.html` (vendored from papalencyclicals.net / vatican.va) | ✅ | one doc per council / Vatican II document (36); canon + §-paragraph passages |
| **medieval** | local `sources/medieval/*.xml` (vendored from ccel.org ThML) | ✅ | one doc per (author, work) (6); reuses the church-fathers ThML builder |
| **medieval** (5.6b) | local `sources/theologians/*.xml` (CCEL ThML, R6's downloads), one `ingest.theologians.WORKS` entry each | not yet | `ingest/theologians.py`; Teresa's Interior Castle (Stanbrook 1921) and Life with the Relations (Lewis 1904); Francis de Sales's Introduction to the Devout Life (Rivingtons 1876) and Treatise on the Love of God (Mackey, about 1884); Julian of Norwich's Revelations of Divine Love (Warrack 1901); Thérèse's Story of a Soul with her letters, counsels and prayers (Taylor 1912); Ignatius's Spiritual Exercises (Mullan 1914) and Autobiography with da Câmara's preface (O'Conor 1900); from Project Gutenberg text (`ingest/gutenberg_text.py`), Alphonsus's Glories of Mary (Dunigan 1852, eBook 72411) and Brother Lawrence's Practice of the Presence of God (Revell, about 1895, eBook 13871); editors' matter left out per work; the works' printed headings in the text, marked (`metadata.headings`) |
| **roman-curia** | local `sources/roman-curia/*.html` with `manifest.json` (vendored from vatican.va by `scripts/vendor_sources.py --collection roman-curia`) | not yet | the Dicastery for the Doctrine of the Faith's doctrinal documents, 1966–2026 (60; 5.3a); real paragraph numbers kept, unnumbered text grouped by section; headings marked in the text (#445); endnotes, title blocks and signatures left out; the Professio Fidei commentary page's opening texts left out |

**Vendoring:** web-sourced collections are vendored to `sources/<collection>/`
(gitignored, with a `manifest.json` recording provenance) via
`scripts/vendor_sources.py`; adapters read these local files, not the network.
Re-acquire with `python3 scripts/vendor_sources.py --collection all`.

**Document counts** in the table are what the `publication.py` adapter emits, not the
number of source files — one file can yield several documents (the medieval
`proslogium-monologium-and-cur-deus-homo.xml` produces three). Verified 2026-09-17.
Re-check without touching either store:

```bash
python3 -c "from publication import SOURCE_BUILDS as B; d=B['encyclicals'](); print(len(d))"
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

Each entry in `publication.py`'s `SOURCE_ADAPTERS` registry (by published collection;
`SOURCE_BUILDS` holds the same by source) returns a `list[Document]`
of clean `Passage`s with anchors, chapter keys, and source-specific cleaning. To check
one without writing anything:

```bash
python3 run_collection.py --collection <name> --dry-run
```

To publish, use `publish.py` (item 2.2w):

1. `stage` builds the collection into the `staging` schema and a new Qdrant collection.
2. `report` compares it with live.
3. `apply` moves it into live in one transaction that never deletes a row, then switches
   the alias `chunks_live`.
4. `cleanup` drops the staging tables once the apply is checked.

`rollback` undoes an applied publish within its window, and is the only rollback path.
Passage IDs come from the passage registry, so a passage keeps its ID when its text is
fixed and its anchor rebuilt, and a removed passage is retired with a tombstone, never
deleted. See README.md, "Publish one collection".

The publish lock (`PUBLISH_LOCK.json`, item 0.4) refuses every live step unless a
reviewed PR has listed the collection, release and step; pass `--release <release>`.
Local rehearsals, with both the database and Qdrant on this machine, are exempt.

Vendored adapters read the local files under `sources/<collection>/`, not the network.
Re-acquire the raw sources with
`python3 scripts/vendor_sources.py --collection all` if they are missing.
