# 0001. Older papal documents with no public-domain English: retire, with a link to where they can be read

- **Status:** accepted, 31 October 2026 (Carter). The list below is final for the 30 documents marked "Retire with link"; the 39 marked "Scope search" are settled by R8's scope search, and this file is updated when it ends.
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

30 are retired with a link; the rest have a printing, are being searched, or (Nostis et Nobiscum) have an abridged one.

| Year | Document | Pope | Slug | Outcome |
|---|---|---|---|---|
| 1302 | Unam Sanctam | Boniface VIII | `unam-sanctam` | Public-domain printing: Catholic Historical Review, 1927 |
| 1520 | Exsurge Domine | Leo X | `exsurge-domine` | **Retire with link** |
| 1537 | Sublimis Deus | Paul III | `sublimis-deus` | Public-domain printing: MacNutt, 1909 |
| 1740 | Ubi Primum | Benedict XIV | `ubi-primum` | **Retire with link** |
| 1741 | Quanta Cura | Benedict XIV | `quanta-cura` | **Retire with link** |
| 1743 | Nimiam Licentiam | Benedict XIV | `nimiam-licentiam` | **Retire with link** |
| 1745 | Vix Pervenit | Benedict XIV | `vix-pervenit` | **Retire with link** |
| 1748 | Magnae Nobis | Benedict XIV | `magnae-nobis` | **Retire with link** |
| 1749 | Annus Qui Hunc | Benedict XIV | `annus-qui-hunc` | **Retire with link** |
| 1749 | Apostolica Constitutio | Benedict XIV | `apostolica-constitutio` | **Retire with link** |
| 1749 | Peregrinantes | Benedict XIV | `peregrinantes` | **Retire with link** |
| 1751 | A Quo Primum | Benedict XIV | `a-quo-primum` | **Retire with link** |
| 1754 | Cum Religiosi | Benedict XIV | `cum-religiosi` | **Retire with link** |
| 1754 | Quod Provinciale | Benedict XIV | `quod-provinciale` | **Retire with link** |
| 1755 | Allatae Sunt | Benedict XIV | `allatae-sunt` | **Retire with link** |
| 1756 | Ex Omnibus | Benedict XIV | `ex-omnibus` | **Retire with link** |
| 1756 | Ex Quo | Benedict XIV | `ex-quo` | **Retire with link** |
| 1758 | A Quo Die | Clement XIII | `a-quo-die` | **Retire with link** |
| 1759 | Appetente Sacro | Clement XIII | `appetente-sacro` | **Retire with link** |
| 1759 | Cum Primum | Clement XIII | `cum-primum` | **Retire with link** |
| 1761 | In Dominico Agro | Clement XIII | `in-dominico-agro` | **Retire with link** |
| 1766 | Christianae Reipublicae | Clement XIII | `christianae-reipublicae` | **Retire with link** |
| 1768 | Summa Quae | Clement XIII | `summa-quae` | **Retire with link** |
| 1769 | Cum Summi | Clement XIV | `cum-summi` | **Retire with link** |
| 1769 | Decet Quam Maxime | Clement XIV | `decet-quam-maxime` | **Retire with link** |
| 1769 | Inscrutabili Divinae Sapientiae | Clement XIV | `inscrutabili-divinae-sapientiae` | **Retire with link** |
| 1774 | Salutis Nostrae | Clement XIV | `salutis-nostrae` | **Retire with link** |
| 1775 | Inscrutabile | Pius VI | `inscrutabile` | **Retire with link** |
| 1791 | Charitas | Pius VI | `charitas` | **Retire with link** |
| 1800 | Diu Satis | Pius VII | `diu-satis` | Public-domain printing: London: Keating, Brown and Keating, 1800 |
| 1824 | Quod Hoc Ineunte | Leo XII | `quod-hoc-ineunte` | **Retire with link** |
| 1824 | Ubi Primum (1824) | Leo XII | `ubi-primum-1824` | Public-domain printing: Dublin: Coyne, 1824 |
| 1825 | Charitate Christi | Leo XII | `charitate-christi` | **Retire with link** |
| 1826 | Quo Graviora | Leo XII | `quo-graviora` | **Retire with link** |
| 1829 | Traditi Humilitati | Pius VIII | `traditi-humilitati` | Public-domain printing: The Jesuit, or Catholic Sentinel, 1829 |
| 1832 | Cum Primum (1832) | Gregory XVI | `cum-primum-1832` | Scope search |
| 1832 | Mirari Vos | Gregory XVI | `mirari-vos` | Public-domain printing: Catholic Magazine and Review, 1833 (Wikisource) |
| 1832 | Summo Iugiter Studio | Gregory XVI | `summo-iugiter-studio` | Scope search |
| 1833 | Quo Graviora (1833) | Gregory XVI | `quo-graviora-1833` | Scope search |
| 1834 | Singulari Nos | Gregory XVI | `singulari-nos` | Scope search (the pilot found none) |
| 1835 | Commissum Divinitus | Gregory XVI | `commissum-divinitus` | Scope search |
| 1839 | In Supremo Apostolatus | Gregory XVI | `in-supremo-apostolatus` | Public-domain printing: Bishop England's Letters to Forsyth, 1844 |
| 1840 | Probe Nostis | Gregory XVI | `probe-nostis` | Scope search |
| 1841 | Quas Vestro | Gregory XVI | `quas-vestro` | Scope search |
| 1844 | Inter Praecipuas | Gregory XVI | `inter-praecipuas` | Public-domain printing: Catholic Cabinet, 1845 |
| 1846 | Qui Pluribus | Pius IX | `qui-pluribus` | Public-domain printing: United States Catholic Magazine, 1847 |
| 1847 | Praedecessores Nostros | Pius IX | `praedecessores-nostros` | Scope search |
| 1847 | Ubi Primum (1847) | Pius IX | `ubi-primum-1847` | Scope search |
| 1849 | Nostis Et Nobiscum | Pius IX | `nostis-et-nobiscum` | Abridged printing only (The Rambler, 1850): search on; else publish it with the gaps marked |
| 1849 | Ubi Primum (1849) | Pius IX | `ubi-primum-1849` | Public-domain printing: United States Catholic Magazine, 1849 |
| 1851 | Exultavit Cor Nostrum | Pius IX | `exultavit-cor-nostrum` | Scope search |
| 1852 | Nemo Certe Ignorat | Pius IX | `nemo-certe-ignorat` | Scope search |
| 1852 | Probe Noscitis Venerabiles | Pius IX | `probe-noscitis-venerabiles` | Scope search |
| 1853 | Inter Multiplices | Pius IX | `inter-multiplices` | Scope search |
| 1854 | Apostolicae Nostrae Caritatis | Pius IX | `apostolicae-nostrae-caritatis` | Scope search |
| 1854 | Ineffabilis Deus | Pius IX | `ineffabilis-deus` | Public-domain printing: Official Documents (Baltimore: Murphy), 1855 |
| 1854 | Neminem Vestrum | Pius IX | `neminem-vestrum` | Scope search |
| 1854 | Optime Noscitis | Pius IX | `optime-noscitis` | Scope search |
| 1855 | Optime Noscitis (1855) | Pius IX | `optime-noscitis-1855` | Scope search |
| 1856 | Singulari Quidem | Pius IX | `singulari-quidem` | Scope search |
| 1858 | Amantissimi Redemptoris | Pius IX | `amantissimi-redemptoris` | Scope search |
| 1858 | Cum Nuper | Pius IX | `cum-nuper` | Scope search |
| 1858 | Cum Sancta Mater Ecclesia | Pius IX | `cum-sancta-mater-ecclesia` | Scope search |
| 1859 | Qui Nuper | Pius IX | `qui-nuper` | Scope search |
| 1860 | Nullis Certe Verbis | Pius IX | `nullis-certe-verbis` | Scope search |
| 1862 | Amantissimus | Pius IX | `amantissimus` | Scope search |
| 1863 | Incredibili | Pius IX | `incredibili` | Scope search |
| 1863 | Quanto Conficiamur Moerore | Pius IX | `quanto-conficiamur-moerore` | Scope search |
| 1864 | Maximae Quidem | Pius IX | `maximae-quidem` | Scope search |
| 1864 | Quanta Cura (1864) | Pius IX | `quanta-cura-1864` | Public-domain printing: Dublin Review, 1865 |
| 1864 | Syllabus of Errors | Pius IX | `syllabus-of-errors` | Public-domain printing: Fessler, True and False Infallibility, 1875 |
| 1865 | Meridionali Americae | Pius IX | `meridionali-americae` | Scope search |
| 1867 | Levate | Pius IX | `levate` | Scope search |
| 1870 | Respicientes | Pius IX | `respicientes` | Scope search |
| 1871 | Beneficia Dei | Pius IX | `beneficia-dei` | Scope search |
| 1871 | Saepe Venerabiles Fratres | Pius IX | `saepe-venerabiles-fratres` | Scope search |
| 1871 | Ubi Nos | Pius IX | `ubi-nos` | Scope search |
| 1872 | Quae In Patriarchatu | Pius IX | `quae-in-patriarchatu` | Scope search |
| 1873 | Etsi Multa | Pius IX | `etsi-multa` | Public-domain printing: Philadelphia pamphlet, [1874] |
| 1873 | Quartus Supra | Pius IX | `quartus-supra` | Scope search |
| 1874 | Gravibus Ecclesiae | Pius IX | `gravibus-ecclesiae` | Public-domain printing: Appletons' Annual Cyclopaedia, 1875 (Wikisource) |
| 1874 | Omnem Sollicitudinem | Pius IX | `omnem-sollicitudinem` | Scope search |
| 1874 | Vix Dum A Nobis | Pius IX | `vix-dum-a-nobis` | Scope search |
| 1875 | Graves Ac Diuturnae | Pius IX | `graves-ac-diuturnae` | Scope search |
| 1875 | Quod Nunquam | Pius IX | `quod-nunquam` | Scope search |
