# 0001. Older papal documents with no public-domain English: retire, with a link to where they can be read

- **Status:** accepted, 31 October 2026 (Carter). Every document without a printing yet is searched in full first (Carter, 31 Oct 2026, after a probe found two of the 18th-century documents the pilot had written off); only a document still without one after that search is retired with a link. This table is updated as the search settles each document, and lists the places searched for each one retired.
- **Context records:** `docs/research/R8-papal-translations.md` (the research), GitHub issue #266 (R8), corpus-cleanup item 1.3d (the change that applies it).

## Context

TheoCorpus took 86 older papal documents (Benedict XIV to Pius IX, and three bulls) from papalencyclicals.net. The Latin originals are long out of copyright, but the English is not the popes': most of it is the site's scan of Claudia Carlen's *The Papal Encyclicals 1740–1981* (1981), a modern translation with its own copyright, held by her publisher (McGrath Publishing, later reissued by Pierian Press). The site says it cannot grant permission to reuse its texts. Ubi Lutetiam is Italian and leaves under rule E, which leaves 85.

Two earlier decisions frame this one (Decision log, `docs/2026-09-28-corpus-cleanup-plan.md`):

- "Excerpt-only needs an allowed-use basis" (29 Oct 2026): showing passages of an uncleared text in search needs a published statement allowing the use. Carlen's publisher has published none, and the Holy See's statement covers only texts taken from vatican.va, which has no English for any pope before Leo XIII.
- "Older papal translations: trace first" (29 Oct 2026): each document with a public-domain English printing moves to it; each without one is retired.

R8 searched for older printings (any English translation dated before 1931, or a later one never renewed). It found them for most of the 19th-century documents and for almost none of the 18th-century ones.

## Decision

A document for which no public-domain English printing is found is **retired with a link**: its passages leave search and the database's live corpus, and no text of the uncleared translation is stored or shown. Its document page, and any saved bookmark or search result that pointed into it, shows the removal page: "No public-domain English translation is available", with a link to read the document at papalencyclicals.net (its `metadata.url`). Retired rows are kept, never deleted (D3), so the decision can be reversed.

Considered and not chosen: retiring with no link (leaves readers with nowhere to go); keeping the documents excerpt-only (passages in search, reader closed), which needs an allowed-use basis these texts lack.

Related decisions recorded with this one:

- **Nostis et Nobiscum** has only an abridged printing (*The Rambler*, February 1850, which omits paragraphs 21–24 and 31–33). R8's scope search looks for a complete one; if none is found, the abridgement is published with the omitted paragraphs marked and those passages retired, so the rest stays readable and searchable.
- **Etsi Multa** is published from an undated printing (Philadelphia, approved by Bishop James F. Wood), dated by other evidence to between November 1873 and February 1875.

## Consequences

- The retired documents disappear from search. A user who searches for, say, Benedict XIV on usury (Vix Pervenit) or Leo XII on secret societies (Quo Graviora) finds nothing from TheoCorpus and must follow the link. Bookmarks keep working and open the removal page.
- Where a public-domain printing exists, the document opens in the full reader in that translation, credited to the printing; for most, the wording differs from today's.
- Item 2.4a's `Tombstone` carries `read_elsewhere_url`, and 2.4b's removal page and tombstone card show it.

## How to reverse it

Any retired document can come back without losing its links or bookmarks:

1. **If a public-domain printing is found** (HathiTrust and *The Tablet* were not searchable from the server in 2026; Quod Hoc Ineunte's 1824 London translation is known from reviews but was not located): add its row to `datapipeline/rights_inventory.json`, vendor it, rebuild the document as 1.3d does, and close its removal entry.
2. **If Carlen's publisher grants permission** (or a published allowed-use statement turns up): record it as the rows' `permission` status (or an excerpt basis), with the grant's scope and date; every document still carrying the papalencyclicals.net text can then return in full (or excerpt-only) at once.
3. **If Carter decides to accept the risk instead**: revise the Decision log row "Excerpt-only needs an allowed-use basis" for these documents.

In every case the document keeps its ID, its removal entry in `datapipeline/registry/removals.json` gains `closed_by` and `closed_on` (entries are never deleted), and the next publish un-retires it.

## Where the decision is recorded in data

- `datapipeline/registry/removals.json`: one `document`-scope entry per retired document, reason `translation-in-preparation`, `added_by: "1.3d"`. This is the machine record; 1.3d's acceptance check requires it to match the table below.
- `datapipeline/rights_inventory.json`: the retired documents' rows stay `unknown` with their papalencyclicals.net source; documents with a printing have a row for it (`planned_for: "1.3d"` until built).

## The 85 documents

Outcomes: a public-domain printing; "Full search" (being searched); or, once the search is done, "Retire with link" with the places searched.

| Year | Document | Pope | Slug | Outcome |
|---|---|---|---|---|
| 1302 | Unam Sanctam | Boniface VIII | `unam-sanctam` | Public-domain printing: Catholic Historical Review, 1927 |
| 1520 | Exsurge Domine | Leo X | `exsurge-domine` | Full search |
| 1537 | Sublimis Deus | Paul III | `sublimis-deus` | Public-domain printing: MacNutt, 1909 |
| 1740 | Ubi Primum | Benedict XIV | `ubi-primum` | Full search |
| 1741 | Quanta Cura | Benedict XIV | `quanta-cura` | Full search |
| 1743 | Nimiam Licentiam | Benedict XIV | `nimiam-licentiam` | Full search |
| 1745 | Vix Pervenit | Benedict XIV | `vix-pervenit` | Full search |
| 1748 | Magnae Nobis | Benedict XIV | `magnae-nobis` | Full search |
| 1749 | Annus Qui Hunc | Benedict XIV | `annus-qui-hunc` | Full search |
| 1749 | Apostolica Constitutio | Benedict XIV | `apostolica-constitutio` | Full search |
| 1749 | Peregrinantes | Benedict XIV | `peregrinantes` | Full search |
| 1751 | A Quo Primum | Benedict XIV | `a-quo-primum` | Full search |
| 1754 | Cum Religiosi | Benedict XIV | `cum-religiosi` | Full search |
| 1754 | Quod Provinciale | Benedict XIV | `quod-provinciale` | Full search |
| 1755 | Allatae Sunt | Benedict XIV | `allatae-sunt` | Full search |
| 1756 | Ex Omnibus | Benedict XIV | `ex-omnibus` | Full search |
| 1756 | Ex Quo | Benedict XIV | `ex-quo` | Full search |
| 1758 | A Quo Die | Clement XIII | `a-quo-die` | Full search |
| 1759 | Appetente Sacro | Clement XIII | `appetente-sacro` | Full search |
| 1759 | Cum Primum | Clement XIII | `cum-primum` | Full search |
| 1761 | In Dominico Agro | Clement XIII | `in-dominico-agro` | Full search |
| 1766 | Christianae Reipublicae | Clement XIII | `christianae-reipublicae` | Full search |
| 1768 | Summa Quae | Clement XIII | `summa-quae` | Full search |
| 1769 | Cum Summi | Clement XIV | `cum-summi` | Public-domain printing: Interesting Letters of Pope Clement XIV, 1777 |
| 1769 | Decet Quam Maxime | Clement XIV | `decet-quam-maxime` | Full search |
| 1769 | Inscrutabili Divinae Sapientiae | Clement XIV | `inscrutabili-divinae-sapientiae` | Full search |
| 1774 | Salutis Nostrae | Clement XIV | `salutis-nostrae` | Public-domain printing: Interesting Letters of Pope Clement XIV, 1777 |
| 1775 | Inscrutabile | Pius VI | `inscrutabile` | Full search |
| 1791 | Charitas | Pius VI | `charitas` | Full search |
| 1800 | Diu Satis | Pius VII | `diu-satis` | Public-domain printing: London: Keating, Brown and Keating, 1800 |
| 1824 | Quod Hoc Ineunte | Leo XII | `quod-hoc-ineunte` | Full search |
| 1824 | Ubi Primum (1824) | Leo XII | `ubi-primum-1824` | Public-domain printing: Dublin: Coyne, 1824 |
| 1825 | Charitate Christi | Leo XII | `charitate-christi` | Full search |
| 1826 | Quo Graviora | Leo XII | `quo-graviora` | Full search |
| 1829 | Traditi Humilitati | Pius VIII | `traditi-humilitati` | Public-domain printing: The Jesuit, or Catholic Sentinel, 1829 |
| 1832 | Cum Primum (1832) | Gregory XVI | `cum-primum-1832` | Full search |
| 1832 | Mirari Vos | Gregory XVI | `mirari-vos` | Public-domain printing: Catholic Magazine and Review, 1833 (Wikisource) |
| 1832 | Summo Iugiter Studio | Gregory XVI | `summo-iugiter-studio` | Full search |
| 1833 | Quo Graviora (1833) | Gregory XVI | `quo-graviora-1833` | Full search |
| 1834 | Singulari Nos | Gregory XVI | `singulari-nos` | Full search (the pilot found none) |
| 1835 | Commissum Divinitus | Gregory XVI | `commissum-divinitus` | Full search |
| 1839 | In Supremo Apostolatus | Gregory XVI | `in-supremo-apostolatus` | Public-domain printing: Bishop England's Letters to Forsyth, 1844 |
| 1840 | Probe Nostis | Gregory XVI | `probe-nostis` | Full search |
| 1841 | Quas Vestro | Gregory XVI | `quas-vestro` | Full search |
| 1844 | Inter Praecipuas | Gregory XVI | `inter-praecipuas` | Public-domain printing: Catholic Cabinet, 1845 |
| 1846 | Qui Pluribus | Pius IX | `qui-pluribus` | Public-domain printing: United States Catholic Magazine, 1847 |
| 1847 | Praedecessores Nostros | Pius IX | `praedecessores-nostros` | Full search |
| 1847 | Ubi Primum (1847) | Pius IX | `ubi-primum-1847` | Full search |
| 1849 | Nostis Et Nobiscum | Pius IX | `nostis-et-nobiscum` | Abridged printing only (The Rambler, 1850): search on; else publish it with the gaps marked |
| 1849 | Ubi Primum (1849) | Pius IX | `ubi-primum-1849` | Public-domain printing: United States Catholic Magazine, 1849 |
| 1851 | Exultavit Cor Nostrum | Pius IX | `exultavit-cor-nostrum` | Full search |
| 1852 | Nemo Certe Ignorat | Pius IX | `nemo-certe-ignorat` | Full search |
| 1852 | Probe Noscitis Venerabiles | Pius IX | `probe-noscitis-venerabiles` | Full search |
| 1853 | Inter Multiplices | Pius IX | `inter-multiplices` | Full search |
| 1854 | Apostolicae Nostrae Caritatis | Pius IX | `apostolicae-nostrae-caritatis` | Full search |
| 1854 | Ineffabilis Deus | Pius IX | `ineffabilis-deus` | Public-domain printing: Official Documents (Baltimore: Murphy), 1855 |
| 1854 | Neminem Vestrum | Pius IX | `neminem-vestrum` | Full search |
| 1854 | Optime Noscitis | Pius IX | `optime-noscitis` | Full search |
| 1855 | Optime Noscitis (1855) | Pius IX | `optime-noscitis-1855` | Full search |
| 1856 | Singulari Quidem | Pius IX | `singulari-quidem` | Full search |
| 1858 | Amantissimi Redemptoris | Pius IX | `amantissimi-redemptoris` | Full search |
| 1858 | Cum Nuper | Pius IX | `cum-nuper` | Full search |
| 1858 | Cum Sancta Mater Ecclesia | Pius IX | `cum-sancta-mater-ecclesia` | Full search |
| 1859 | Qui Nuper | Pius IX | `qui-nuper` | Full search |
| 1860 | Nullis Certe Verbis | Pius IX | `nullis-certe-verbis` | Full search |
| 1862 | Amantissimus | Pius IX | `amantissimus` | Full search |
| 1863 | Incredibili | Pius IX | `incredibili` | Full search |
| 1863 | Quanto Conficiamur Moerore | Pius IX | `quanto-conficiamur-moerore` | Full search |
| 1864 | Maximae Quidem | Pius IX | `maximae-quidem` | Full search |
| 1864 | Quanta Cura (1864) | Pius IX | `quanta-cura-1864` | Public-domain printing: Dublin Review, 1865 |
| 1864 | Syllabus of Errors | Pius IX | `syllabus-of-errors` | Public-domain printing: Fessler, True and False Infallibility, 1875 |
| 1865 | Meridionali Americae | Pius IX | `meridionali-americae` | Full search |
| 1867 | Levate | Pius IX | `levate` | Full search |
| 1870 | Respicientes | Pius IX | `respicientes` | Full search |
| 1871 | Beneficia Dei | Pius IX | `beneficia-dei` | Full search |
| 1871 | Saepe Venerabiles Fratres | Pius IX | `saepe-venerabiles-fratres` | Full search |
| 1871 | Ubi Nos | Pius IX | `ubi-nos` | Full search |
| 1872 | Quae In Patriarchatu | Pius IX | `quae-in-patriarchatu` | Full search |
| 1873 | Etsi Multa | Pius IX | `etsi-multa` | Public-domain printing: Philadelphia pamphlet, [1874] |
| 1873 | Quartus Supra | Pius IX | `quartus-supra` | Full search |
| 1874 | Gravibus Ecclesiae | Pius IX | `gravibus-ecclesiae` | Public-domain printing: Appletons' Annual Cyclopaedia, 1875 (Wikisource) |
| 1874 | Omnem Sollicitudinem | Pius IX | `omnem-sollicitudinem` | Full search |
| 1874 | Vix Dum A Nobis | Pius IX | `vix-dum-a-nobis` | Full search |
| 1875 | Graves Ac Diuturnae | Pius IX | `graves-ac-diuturnae` | Full search |
| 1875 | Quod Nunquam | Pius IX | `quod-nunquam` | Full search |
