# 0001. Older papal documents with no public-domain English: hold for permission, with a link to where they can be read

- **Status:** accepted, 31 October 2026; revised 1 November 2026 (Carter). Documents with no public-domain printing after R8's full search are **held for permission** (removal reason `awaiting-permission`), not retired for good; documents with only an extract publish the extract and hold the rest. Permission is to be asked once the site is complete. This table is final for R8; 1.3d keeps it in step with the removal registry.
- **Context records:** `docs/research/R8-papal-translations.md` (the research), GitHub issue #266 (R8), corpus-cleanup item 1.3d (the change that applies it).

## Context

TheoCorpus took 86 older papal documents (Benedict XIV to Pius IX, and three bulls) from papalencyclicals.net. The Latin originals are long out of copyright, but the English is not the popes': most of it is the site's scan of Claudia Carlen's *The Papal Encyclicals 1740–1981* (1981), a modern translation with its own copyright, held by her publisher (McGrath Publishing, later reissued by Pierian Press). The site says it cannot grant permission to reuse its texts. The 110 translations made for that edition are registered with the US Copyright Office (*One hundred ten papal encyclicals*, TXu000087711, 21 December 1981, claimant McGrath Publishing Company); the set is published today by Pierian Press, and Faithlife licenses it electronically (R8 report, section 6). Ubi Lutetiam is Italian and leaves under rule E, which leaves 85.

Two earlier decisions frame this one (Decision log, `docs/2026-09-28-corpus-cleanup-plan.md`):

- "Excerpt-only needs an allowed-use basis" (29 Oct 2026): showing passages of an uncleared text in search needs a published statement allowing the use. Carlen's publisher has published none, and the Holy See's statement covers only texts taken from vatican.va, which has no English for any pope before Leo XIII.
- "Older papal translations: trace first" (29 Oct 2026): each document with a public-domain English printing moves to it; each without one is retired.

R8 searched for older printings (any English translation dated before 1931, or a later one never renewed). It found them for most of the 19th-century documents and for almost none of the 18th-century ones.

## Decision

A document for which R8 found no public-domain English printing is **held for permission** (Carter, 1 Nov 2026). 1.3d gives it a `document`-scope removal entry with reason `awaiting-permission`. Its rows stay in the database, retired, never deleted (D3); it is out of search, the reader, AI explanations, `/sources` and the search index (the publish builds a new Qdrant collection without it). A reader who reaches it by an old link or bookmark sees the removal page: "This translation is not available on TheoCorpus at present.", with a link to the document at papalencyclicals.net (its `metadata.url`). Its rights row stays `unknown`, with its papalencyclicals.net source, so the text can return unchanged.

A document for which R8 found **only an extract or an abridgement** in a public-domain printing is built from that printing; only the paragraphs the printing lacks are held, each with a `passage`-scope `awaiting-permission` entry, and the reader's overview says which are missing (Carter, 1 Nov 2026). This applies to Nostis et Nobiscum, Qui Nuper, Nullis Certe Verbis, Levate, Cum Summi, Salutis Nostrae and Traditi Humilitati.

Why "held" rather than "retired": the only English for these documents is Carlen's (1981), registered and in copyright, so permission from its publisher is the one route back, and Carter means to ask once the site is complete. A distinct reason makes the whole set one query, and one change, when the answer comes.

Considered and not chosen: deleting the texts (a re-import later for no gain while nothing is shown); retiring with no link (leaves readers nowhere to go); keeping the documents excerpt-only (passages in search), which needs an allowed-use basis these texts lack (Decision log, 29 Oct 2026).

Related decisions recorded with this one:

- **Etsi Multa** is published from an undated printing (Philadelphia, approved by Bishop James F. Wood), dated by other evidence to between November 1873 and February 1875.
- **Nostis et Nobiscum** has only an abridged printing (*The Rambler*, February 1850, which omits paragraphs 21–24 and 31–33); it follows the extract rule above.

## Consequences

- The held documents disappear from search. A user who searches for, say, Benedict XIV on usury (Vix Pervenit) or Leo XII on secret societies (Quo Graviora) finds nothing from TheoCorpus and must follow the link. Bookmarks keep working and open the removal page. If permission is granted, the set returns in one publish, under the same document and passage IDs.
- Where a public-domain printing exists, the document opens in the full reader in that translation, credited to the printing; for most, the wording differs from today's.
- Item 2.4a's `Tombstone` carries `read_elsewhere_url`, and 2.4b's removal page and tombstone card show it.

## How to reverse it

Any held document or paragraph can come back without losing its links or bookmarks:

1. **If a public-domain printing is found** (HathiTrust and *The Tablet* were not searchable from the server in 2026; Quod Hoc Ineunte's 1824 London translation is known from reviews but was not located): add its row to `datapipeline/rights_inventory.json`, vendor it, rebuild the document as 1.3d does, and close its removal entry.
2. **If Carlen's publisher grants permission** (Pierian Press, Ann Arbor; the 1981 claimant was McGrath Publishing Company), or a published allowed-use statement turns up: record it as the rows' `permission` status (or an excerpt basis), with the grant's scope and date; every document still carrying the papalencyclicals.net text can then return in full (or excerpt-only) at once.
3. **If Carter decides to accept the risk instead**: revise the Decision log row "Excerpt-only needs an allowed-use basis" for these documents.

In every case the document keeps its ID, its removal entry in `datapipeline/registry/removals.json` gains `closed_by` and `closed_on` (entries are never deleted), and the next publish un-retires it.

## Where the decision is recorded in data

- `datapipeline/registry/removals.json`: one `document`-scope entry per held document, and one `passage`-scope entry per held paragraph of a partial document, all with reason `awaiting-permission` and `added_by: "1.3d"`. This is the machine record; 1.3d's acceptance check requires it to match the table below. `grep awaiting-permission` lists the whole set.
- `datapipeline/rights_inventory.json`: the retired documents' rows stay `unknown` with their papalencyclicals.net source; documents with a printing have a row for it (`planned_for: "1.3d"` until built).

## Where the full search looked (31 Oct – 1 Nov 2026)

Every document marked "Not found so far" was searched in all of these:

- **Internet Archive full text**, per document: the Latin incipit, the incipit with the pope's name, the date line in English, and topic terms any translation must use (for example Poland and the Jews, usury, Albania, the Greek Euchologion, Sardinia, Lamennais), each limited to the document's year to 1930, keeping English hits and excluding modern machine translations.
- **Catholic periodicals**, every Internet Archive volume dated in the document's year or the next, scored with a different-translation detector (`docs/research/R8_tools/xlate.py`): *The Dublin Review*, *The Rambler*, *The Metropolitan* (Baltimore), *Brownson's Quarterly Review*, *The Catholic World*, *The Irish Ecclesiastical Record*, *Annals of the Propagation of the Faith*, *The United States Catholic Magazine*, *The Catholic Magazine* (London and Birmingham), *The Catholic Cabinet*, *Ave Maria*, *The American Catholic Quarterly Review*, *The Month*, *The Tablet* (the volumes on the Internet Archive), *The Catholic Miscellany*: 2,048 volumes.
- **Annual reference works**: *The Laity's Directory* (London, 1768–1799), the *Metropolitan Catholic Almanac* and *Catholic Directory* (1833–1864), *The Annual Register*, and *Appletons' Annual Cyclopaedia* (1861–1902, each volume matched to its year from its title page).
- **Church histories that quote papal letters in English**: Artaud de Montor, *Lives and Times of the Roman Pontiffs* (New York, 1867); Darras, *General History of the Catholic Church* (1865); *Interesting Letters of Pope Clement XIV* (1777).
- **Canadiana (CIHM) microfiche**: every title naming an encyclical, bull, brief, jubilee or pope, to 1880.

Not searched, because they refuse this server: HathiTrust full text, and Google Books (quota). *The Tablet*'s own archive was not searched beyond the Internet Archive's volumes. Each held document lists these as not searched.

## The 85 documents

Outcomes: a public-domain printing (built from it in 1.3d); an extract only (published with its gaps held); or **held for permission** (no printing found in the places listed above).

| Year | Document | Pope | Slug | Outcome |
|---|---|---|---|---|
| 1302 | Unam Sanctam | Boniface VIII | `unam-sanctam` | Public-domain printing: Catholic Historical Review, 1927 |
| 1520 | Exsurge Domine | Leo X | `exsurge-domine` | **Held for permission** |
| 1537 | Sublimis Deus | Paul III | `sublimis-deus` | Public-domain printing: MacNutt, 1909 |
| 1740 | Ubi Primum | Benedict XIV | `ubi-primum` | **Held for permission** |
| 1741 | Quanta Cura | Benedict XIV | `quanta-cura` | **Held for permission** |
| 1743 | Nimiam Licentiam | Benedict XIV | `nimiam-licentiam` | **Held for permission** |
| 1745 | Vix Pervenit | Benedict XIV | `vix-pervenit` | **Held for permission** |
| 1748 | Magnae Nobis | Benedict XIV | `magnae-nobis` | **Held for permission** |
| 1749 | Annus Qui Hunc | Benedict XIV | `annus-qui-hunc` | **Held for permission** |
| 1749 | Apostolica Constitutio | Benedict XIV | `apostolica-constitutio` | **Held for permission** |
| 1749 | Peregrinantes | Benedict XIV | `peregrinantes` | **Held for permission** |
| 1751 | A Quo Primum | Benedict XIV | `a-quo-primum` | **Held for permission** |
| 1754 | Cum Religiosi | Benedict XIV | `cum-religiosi` | **Held for permission** |
| 1754 | Quod Provinciale | Benedict XIV | `quod-provinciale` | **Held for permission** |
| 1755 | Allatae Sunt | Benedict XIV | `allatae-sunt` | **Held for permission** |
| 1756 | Ex Omnibus | Benedict XIV | `ex-omnibus` | **Held for permission** |
| 1756 | Ex Quo | Benedict XIV | `ex-quo` | **Held for permission** |
| 1758 | A Quo Die | Clement XIII | `a-quo-die` | **Held for permission** |
| 1759 | Appetente Sacro | Clement XIII | `appetente-sacro` | **Held for permission** |
| 1759 | Cum Primum | Clement XIII | `cum-primum` | **Held for permission** |
| 1761 | In Dominico Agro | Clement XIII | `in-dominico-agro` | **Held for permission** |
| 1766 | Christianae Reipublicae | Clement XIII | `christianae-reipublicae` | **Held for permission** |
| 1768 | Summa Quae | Clement XIII | `summa-quae` | **Held for permission** |
| 1769 | Cum Summi | Clement XIV | `cum-summi` | Abridged only (Interesting Letters of Pope Clement XIV, 1777, from the French): published; paragraph 9 held for permission |
| 1769 | Decet Quam Maxime | Clement XIV | `decet-quam-maxime` | **Held for permission** |
| 1769 | Inscrutabili Divinae Sapientiae | Clement XIV | `inscrutabili-divinae-sapientiae` | **Held for permission** |
| 1774 | Salutis Nostrae | Clement XIV | `salutis-nostrae` | Abridged only (Interesting Letters of Pope Clement XIV, 1777, from the French): published; the proclamation of paragraph 2 and paragraphs 3–4 and 8–9 held for permission |
| 1775 | Inscrutabile | Pius VI | `inscrutabile` | **Held for permission** |
| 1791 | Charitas | Pius VI | `charitas` | **Held for permission** |
| 1800 | Diu Satis | Pius VII | `diu-satis` | Public-domain printing: London: Keating, Brown and Keating, 1800 |
| 1824 | Quod Hoc Ineunte | Leo XII | `quod-hoc-ineunte` | **Held for permission** |
| 1824 | Ubi Primum (1824) | Leo XII | `ubi-primum-1824` | Public-domain printing: Dublin: Coyne, 1824 |
| 1825 | Charitate Christi | Leo XII | `charitate-christi` | **Held for permission** |
| 1826 | Quo Graviora | Leo XII | `quo-graviora` | **Held for permission** |
| 1829 | Traditi Humilitati | Pius VIII | `traditi-humilitati` | Abridged only (The Jesuit, Boston, 1829): published; the paragraphs it lacks (at least 8–9, settled by 1.3d) held for permission |
| 1832 | Cum Primum (1832) | Gregory XVI | `cum-primum-1832` | **Held for permission** |
| 1832 | Mirari Vos | Gregory XVI | `mirari-vos` | Public-domain printing: Catholic Magazine and Review, 1833 (Wikisource) |
| 1832 | Summo Iugiter Studio | Gregory XVI | `summo-iugiter-studio` | **Held for permission** |
| 1833 | Quo Graviora (1833) | Gregory XVI | `quo-graviora-1833` | **Held for permission** |
| 1834 | Singulari Nos | Gregory XVI | `singulari-nos` | **Held for permission** |
| 1835 | Commissum Divinitus | Gregory XVI | `commissum-divinitus` | **Held for permission** |
| 1839 | In Supremo Apostolatus | Gregory XVI | `in-supremo-apostolatus` | Public-domain printing: Bishop England's Letters to Forsyth, 1844 |
| 1840 | Probe Nostis | Gregory XVI | `probe-nostis` | **Held for permission** |
| 1841 | Quas Vestro | Gregory XVI | `quas-vestro` | **Held for permission** |
| 1844 | Inter Praecipuas | Gregory XVI | `inter-praecipuas` | Public-domain printing: Catholic Cabinet, 1845 |
| 1846 | Qui Pluribus | Pius IX | `qui-pluribus` | Public-domain printing: United States Catholic Magazine, 1847 |
| 1847 | Praedecessores Nostros | Pius IX | `praedecessores-nostros` | **Held for permission** |
| 1847 | Ubi Primum (1847) | Pius IX | `ubi-primum-1847` | **Held for permission** |
| 1849 | Nostis Et Nobiscum | Pius IX | `nostis-et-nobiscum` | Abridged only (The Rambler, February 1850): published; paragraphs 21–24 and 31–33 held for permission |
| 1849 | Ubi Primum (1849) | Pius IX | `ubi-primum-1849` | Public-domain printing: United States Catholic Magazine, 1849 |
| 1851 | Exultavit Cor Nostrum | Pius IX | `exultavit-cor-nostrum` | Public-domain printing: Archbishop of Quebec's pastoral, 1852 (Canadiana microfiche) |
| 1852 | Nemo Certe Ignorat | Pius IX | `nemo-certe-ignorat` | **Held for permission** |
| 1852 | Probe Noscitis Venerabiles | Pius IX | `probe-noscitis-venerabiles` | **Held for permission** |
| 1853 | Inter Multiplices | Pius IX | `inter-multiplices` | Public-domain printing: The Metropolitan (Baltimore), June 1853 |
| 1854 | Apostolicae Nostrae Caritatis | Pius IX | `apostolicae-nostrae-caritatis` | Public-domain printing: The Metropolitan (Baltimore), October 1854 |
| 1854 | Ineffabilis Deus | Pius IX | `ineffabilis-deus` | Public-domain printing: Official Documents (Baltimore: Murphy), 1855 |
| 1854 | Neminem Vestrum | Pius IX | `neminem-vestrum` | **Held for permission** |
| 1854 | Optime Noscitis | Pius IX | `optime-noscitis` | **Held for permission** |
| 1855 | Optime Noscitis (1855) | Pius IX | `optime-noscitis-1855` | **Held for permission** |
| 1856 | Singulari Quidem | Pius IX | `singulari-quidem` | **Held for permission** |
| 1858 | Amantissimi Redemptoris | Pius IX | `amantissimi-redemptoris` | Public-domain printing: The Metropolitan (Baltimore), August 1858 |
| 1858 | Cum Nuper | Pius IX | `cum-nuper` | **Held for permission** |
| 1858 | Cum Sancta Mater Ecclesia | Pius IX | `cum-sancta-mater-ecclesia` | Public-domain printing: Bishop of Kingston's pastoral, 1859 |
| 1859 | Qui Nuper | Pius IX | `qui-nuper` | Partial only (Dublin Review, September 1859): published; paragraph 2 and the lines of 3 it lacks held for permission |
| 1860 | Nullis Certe Verbis | Pius IX | `nullis-certe-verbis` | Partial only (The Rambler, March 1860): published; the paragraphs it lacks (at least 9 and 11–13, settled by 1.3d) held for permission |
| 1862 | Amantissimus | Pius IX | `amantissimus` | **Held for permission** |
| 1863 | Incredibili | Pius IX | `incredibili` | **Held for permission** |
| 1863 | Quanto Conficiamur Moerore | Pius IX | `quanto-conficiamur-moerore` | **Held for permission** |
| 1864 | Maximae Quidem | Pius IX | `maximae-quidem` | **Held for permission** |
| 1864 | Quanta Cura (1864) | Pius IX | `quanta-cura-1864` | Public-domain printing: Dublin Review, 1865 |
| 1864 | Syllabus of Errors | Pius IX | `syllabus-of-errors` | Public-domain printing: Fessler, True and False Infallibility, 1875 |
| 1865 | Meridionali Americae | Pius IX | `meridionali-americae` | **Held for permission** |
| 1867 | Levate | Pius IX | `levate` | Partial only (Appletons' Annual Cyclopaedia for 1867): published, about 400 words (the preamble and the start of paragraph 2); the rest held for permission |
| 1870 | Respicientes | Pius IX | `respicientes` | Public-domain printing: Appletons' Annual Cyclopaedia for 1870, 1871 |
| 1871 | Beneficia Dei | Pius IX | `beneficia-dei` | **Held for permission** |
| 1871 | Saepe Venerabiles Fratres | Pius IX | `saepe-venerabiles-fratres` | **Held for permission** |
| 1871 | Ubi Nos | Pius IX | `ubi-nos` | **Held for permission** |
| 1872 | Quae In Patriarchatu | Pius IX | `quae-in-patriarchatu` | **Held for permission** |
| 1873 | Etsi Multa | Pius IX | `etsi-multa` | Public-domain printing: Philadelphia pamphlet, [1874] |
| 1873 | Quartus Supra | Pius IX | `quartus-supra` | **Held for permission** |
| 1874 | Gravibus Ecclesiae | Pius IX | `gravibus-ecclesiae` | Public-domain printing: Appletons' Annual Cyclopaedia, 1875 (Wikisource) |
| 1874 | Omnem Sollicitudinem | Pius IX | `omnem-sollicitudinem` | **Held for permission** |
| 1874 | Vix Dum A Nobis | Pius IX | `vix-dum-a-nobis` | Public-domain printing: Appletons' Annual Cyclopaedia for 1874, 1875 |
| 1875 | Graves Ac Diuturnae | Pius IX | `graves-ac-diuturnae` | Public-domain printing: Appletons' Annual Cyclopaedia for 1875, 1876 |
| 1875 | Quod Nunquam | Pius IX | `quod-nunquam` | Public-domain printing: Appletons' Annual Cyclopaedia for 1875, 1876 |
