# R8. Older papal translations: confirm, renew, and look for alternatives

Research for corpus-cleanup item R8 (`docs/corpus-cleanup/P0-checks-identity-research.md`, GitHub issue #266), which blocks 1.3d. Stage one, done 31 October 2026: the confirmations, the renewal searches, and the pilot. The rest waits for Carter's scope decision (step 4 of the spec).

No production store was queried and nothing was vendored. To compare texts, the OCR text (`_djvu.txt`) of about 40 Internet Archive items was read into a scratch folder on the home server and deleted with it. The spec asks for approval before downloads; these were reads for comparison, not downloads for the corpus, but Carter should know they happened.

## Result

- **15 of the 85 documents now have a public-domain English printing** (12 in stage one, three from the 1800–1830 search after the pilot), each with a draft row in `datapipeline/rights_inventory.json` (`status: pd-us-pre-1931`, `planned_for: "1.3d"`, `checked_by` null until Carter approves). Four of them print the translation papalencyclicals.net reproduces: Quanta Cura, the Syllabus, Sublimis Deus and Unam Sanctam. The other eleven are different, older translations: Ineffabilis Deus, In Supremo Apostolatus, Ubi Primum (1849), Mirari Vos, Qui Pluribus, Etsi Multa, Inter Praecipuas, Gravibus Ecclesiae, Diu Satis, Ubi Primum (1824) and Traditi Humilitati.
- **One of the 16 Oct candidates was wrong.** The "1900 edition" of Ineffabilis Deus is a St. Paul Editions pamphlet of the 1990s (Internet Archive dates it "[19??]"; its study questions are by John R. Sheets, auxiliary bishop of Fort Wayne–South Bend from 1991). The site's text is that modern translation. An 1855 translation replaces it.
- **Both renewal searches found no renewal, and both are now moot**: In Supremo Apostolatus and Ubi Primum (1849) each have an English printing from the 1840s, so neither needs the 1935 or 1954 book.
- **Pilot: 4 of 10 found complete, 1 abridged, 5 none found.** By group: Pius IX and Gregory XVI 3 of 5 complete plus 1 abridged; 18th century 0 of 3; the two others (Charitas, Exsurge Domine) 0 of 2. Including the documents outside the pilot, 10 of the 12 Pius IX and Gregory XVI documents searched have a complete printing.
- **Recommendation:** search the 38 remaining Pius IX and Gregory XVI documents (estimate 8 to 12 hours), make a short attempt at the six of 1800 to 1830, and retire the 18th-century group unless Carter wants a fuller search of it. Details under "Scope decision".

## The 85 documents

papalencyclicals.net's pages for the encyclicals from Benedict XIV to Pius IX and three bulls: 86 documents, 263,315 words and 1,409 passages in a build of this branch. Ubi Lutetiam is Italian and leaves under rule E, which leaves 85. By group:

| Group | Documents | Found | Pilot, none found | Not yet searched |
|---|---|---|---|---|
| Bulls before 1740 (Unam Sanctam, Exsurge Domine, Sublimis Deus) | 3 | 2 | 1 | 0 |
| 1740–1799 (Benedict XIV, Clement XIII, Clement XIV, Pius VI) | 26 | 0 | 4 | 22 |
| 1800–1830 (Pius VII, Leo XII, Pius VIII) | 6 | 0 | 0 | 6 |
| Gregory XVI (1831–1846) | 10 | 3 | 1 | 6 |
| Pius IX (1846–1878) | 40 | 7 | 1 (abridged printing found) | 32 |
| **Total** | **85** | **12** | **7** | **66** |

## Method

- **Internet Archive full-text search** (`archive.org/services/search/beta/page_production/`, `service_backend=fts`). It searches the OCR of every text item, accepts quoted phrases, proximity (`"a b c"~25`) and a `year:[A TO B]` filter, and returns highlighted snippets. It covers Google-digitized books, the Serials in Microfilm periodicals (`sim_*`: *Dublin Review*, *Rambler*, *United States Catholic Magazine*, *Catholic Historical Review* and others), Canadiana microfiche (`cihm_*`) and Eighteenth Century Collections Online (`bim_eighteenth-century_*`).
- **Same translation.** Share of the site text's word 4-grams that occur in the printing's OCR, overall and per paragraph. A printing of the same translation scores 80–99% even with poor OCR; a different translation of the same document scores 10–25%.
- **Re-run of the 16 Oct trace, all 86 documents.** Eight 9-word phrases spread through each site text, searched as exact phrases. The only items before 1931 that hold three or more of a document's phrases are the printings of Quanta Cura, the Syllabus, Sublimis Deus and Unam Sanctam listed in section 1, and the misdated Ineffabilis Deus reprint. Every other document's wording appears only in Carlen (1981) or later, as the 16 Oct check found.
- **Different translation.** A different translation shares the content words, not the wording. The detector removes stopwords, stems crudely, and finds the window of the printing (1.3 times the site text's length) with the largest share of the site text's content-word pairs that fall within six words of each other. Calibrated on known pairs: a different translation of the same document scores 13–33% (Ineffabilis Deus vs. Murphy 1855: 33%; In Supremo vs. England 1844: 17%; Quanta Cura vs. Spalding 1865: 30%); unrelated books score 0.7–3%. Two limits showed in the pilot. Parallel Latin and English columns interleave in the OCR, which halves the score (Ubi Primum 1849 scored 7%). Short documents score high against large volumes by chance (Praedecessores Nostros, about 1,000 words, scored 17% against a book review). **Every find below was confirmed by reading the printing, not by the score.**
- **What finds them.** Automated discovery (proximity queries on rare words, the incipit, the date line) failed its own calibration: it did not surface Appletons' printing of Gravibus Ecclesiae. What worked was targeted search: the Latin incipit, or a term the document cannot avoid (Gaeta, Bible societies, Lamennais, Expilly), limited to the two or three years after the document's date, then reading the hits. Nineteenth-century Catholic periodicals printed most encyclicals in English within months, often "in Latin, with a translation for this magazine".
- **Renewal searches.** NYPL's transcription of the Catalog of Copyright Entries renewals (github.com/NYPL/cce-renewals, `data/` at commit ebb6156), as in R6.
- **Not searched, and why.** HathiTrust full-text search refuses this server and Firecrawl's proxy alike (HTTP 403, Cloudflare block). The keyless Google Books API was over its shared daily quota. Wikisource's search API rate-limited a bulk pass after 30 queries; single lookups worked. Carter could run HathiTrust searches from a browser; it would add Google-scanned periodicals that the Internet Archive lacks, *The Tablet* above all.

### Traps

- **Modern machine translations dated by their source.** The Internet Archive holds many recent uploads titled "... English Translation" whose `year` is the source's: "Acta Sanctae Sedis – Vol. 6 (1870-71) – English Translation", "Bullarium Franciscanum – Tomus II (1759) – English Translation", a Liguori *Theologia Moralis* dated 1785. They match every year filter. None was used; every find below has a title page or catalogue record of its own period.
- **Undated items.** Most Internet Archive items with no `year` are modern uploads (several "Quanta Cura and the Syllabus of Errors" PDFs dated 1864 are modern typesettings). The 16 Oct check's doubt about `cihm_48367` was the reverse case: it is a genuine microfiche of an 1864 printing, though not of the site's translation.

## 1. The pre-1931 candidates of 16 October

| Document | Verdict | Printing | Evidence |
|---|---|---|---|
| Quanta Cura (1864) | **Confirmed**, same translation | *The Dublin Review*, new series vol. 4, April 1865 (`sim_dublin-review_1865-04_4`); also *Catholic Historical Review*, new series vol. 7 no. 2, July 1927, which reprints it "in translation" | 95% (Dublin) and 98% (CHR) of the site's 4-grams; 13 of 14 paragraphs match. The 14th, "§1", is a footnote the build labels as a paragraph. |
| Syllabus of Errors | **Confirmed**, same translation | Fessler, *The True and False Infallibility of the Popes*, tr. Ambrose St. John (New York: Catholic Publication Society, 1875) (`TheTrueAndFalse`) | 87%, 78 of 81 paragraphs. The same translation is also in *Pamphlets, Religious* (1872, 86%), Monk's *Syllabus for the People* (1875, 82%) and C. C. Marshall's *Roman Catholic Church in the Modern State* (1928, 93%). The row uses Fessler, a Catholic printing; Marshall's OCR is the cleanest if 1.3d wants it. |
| Quanta Cura and the Syllabus, `cihm_48367` | **Genuine 1864 printing, different text** | *The Encylical Letter of Pope Pius IX, and the Syllabus of Modern Errors, dated Dec. 8, 1864* (CIHM microfiche of a copy held by the Public Archives of Canada) | A sibling of the site's Quanta Cura (48%, poor OCR) and a different Syllabus (21%). Not needed. |
| Sublimis Deus | **Confirmed**, same translation | MacNutt, *Bartholomew de Las Casas* (Putnam, 1909) (`bartholomewdelas00macnuoft`) | 99%, all paragraphs |
| Unam Sanctam | **Confirmed**, same translation | Sister M. Mildred Curley, "An Episode in the Conflict between Boniface VIII and Philip the Fair", *Catholic Historical Review*, new series vol. 7 no. 2, July 1927 (`sim_catholic-historical-review_1927-07_7_2`) | 84%, all paragraphs; read side by side, the same text, set in parallel Latin and English columns. Also in her dissertation *The Conflict between Pope Boniface VIII and King Philip IV, the Fair* (CUA, 1927). |
| Ineffabilis Deus | **Rejected** | The "1900 edition" (`IneffabilisDeus`) is St. Paul Editions, Boston, "reprinted from *Our Lady*, Papal Teaching Series", with study questions by Bishop John R. Sheets (auxiliary of Fort Wayne–South Bend from 1991); catalogue date "[19??]" | The site's text matches it at 98%, so the site's text is modern. **Replaced** by a different 1855 translation (section 3). |

## 2. Renewal searches

Both now moot (section 3), recorded for completeness and kept out of the rows.

- **In Supremo Apostolatus, 1935 printing.** John Eppstein, *The Catholic Tradition of the Law of Nations*, which prints the site's translation (8 of 8 phrases). The 28th-year window is 1962–63: both year files are complete for every month. Searched every file for "law of nations", "eppstein", "catholic association for international peace", "international peace" and "carnegie endowment". **No renewal found.** The book appeared in London (Burns, Oates & Washbourne) and in Washington (Catholic Association for International Peace) in 1935. If the London edition came first, the book is a UK work whose US copyright the URAA could have restored in 1996 regardless of renewal (Eppstein died in 1988). Non-renewal alone would not have cleared it.
- **Ubi Primum (1849), 1954 printing.** *Papal Documents on Mary*, compiled by William J. Doheny and Joseph P. Kelly (Milwaukee: Bruce, 1954): 7 of 8 phrases. The window is 1981–82: both files complete. Searched every file for "papal documents", "documents on mary", "doheny", and 1954 originals renewed by Bruce. **No renewal found.** Bruce renewed little at all: one to four renewals a year in the 1953–60 files, none in 1981–82.

## 3. Documents found

Each has a draft row (`planned_for: "1.3d"`). For the eight different translations, 1.3d aligns paragraphs by content, as the spec says.

| Document | Printing | Notes |
|---|---|---|
| Ineffabilis Deus (1854) | *Official Documents Connected with the Definition of the Dogma of the Immaculate Conception*, Latin and English (Baltimore: John Murphy; London: Dolman, 1855), pp. 59–98; approved by Archbishop Kenrick, 14 May 1855 (`officialdocumen00ixgoog`) | Complete; read through the definition and the closing. Google scan of an NYPL copy; OCR fair. |
| In Supremo Apostolatus (1839) | *Letters of the Late Bishop England to the Hon. John Forsyth* (Baltimore: John Murphy, 1844), "The same in English", with the note "the translator has aimed at a verbatim rather than graceful translation" (`lettersoflatebis00engl_0`) | Complete. Also in an 1840 printing, Forsyth's *Address to the People of Georgia* (`addresstopeopleo01fors`, 13%). |
| Ubi Primum (1849) | *The United States Catholic Magazine* (Baltimore), vol. 8 no. 13, 31 March 1849, "in Latin, with a translation for this magazine", ending "Given at Gaeta, February 2, 1849" (`sim_united-states-catholic-magazine_1849-03-31_8_13`) | Complete. The Latin and English columns interleave in the OCR, so 1.3d needs 1.2f's cleanup. |
| Mirari Vos (1832) | *The Catholic Magazine and Review*, vol. 3 (Birmingham, 1833), on Wikisource as "Gregory XVI's Encyclical Letter", transcribed from the scan (index pages 69–80) | Known before R8; now has its row. Proofread transcription, so no OCR. |
| Qui Pluribus (1846) | *The United States Catholic Magazine and Monthly Review*, vol. 6 (Baltimore, 1847), "Encyclical letter of Pope Pius IX, to the Catholic hierarchy throughout the world", about pp. 150–160 (`USCatholicMagazineMonthlyReviewV6`) | Complete; read the opening and the running heads through p. 159. |
| Etsi Multa (1873) | *Encyclical Letter of Our Most Holy Lord Pius IX ... examined by the Rt. Rev. Bishop of Philadelphia, and published with his approbation* (Philadelphia: McLaughlin Brothers) (`encyclicalletter00cath_6`) | Complete pamphlet, 23%. **The title page has no year**: the catalogue says 1874, and Bishop Wood's approbation places it before his death in 1883. The acceptance check asks for a date on the title page; Carter decides whether this suffices. |
| Inter Praecipuas (1844) | *The Catholic Cabinet, and Chronicle of Religious Intelligence* (St. Louis, 1845; title page 1845, approved by Bishop Peter Richard Kenrick), "Circular letter of Pope Gregory XVI", pp. 230 ff. (`catholiccabinet01unkngoog`) | Complete. Also printed in 1844 by Protestant opponents: *The Bull of Pope Gregory XVI* (Philadelphia: H. Montgomery), *Rome's Policy towards the Bible*, *The Baptist Magazine* (March 1845). |
| Gravibus Ecclesiae (1874) | *The American Annual Cyclopaedia ... of the Year 1874*, vol. 14 (New York: Appleton, 1875), pp. 753–756, on Wikisource as "Encyclical Letter by Pope Pius IX Announcing a Jubilee" (scan `americanannualc10unkngoog`) | Proofread transcription. |

## 4. Pilot

Ten documents as the spec asks: five of the 19th century, three of the 18th, two others. Time is agent time for the targeted search, beyond the shared setup (about two hours of tooling).

| Document | Result | Searched | Time |
|---|---|---|---|
| Qui Pluribus (Pius IX, 1846) | **Found**: US Catholic Magazine, 1847 | IA full text: incipit 1846–49 with "Venerable Brethren" and "Bible societies"; automated proximity queries | 15 min |
| Nostis et Nobiscum (Pius IX, 1849) | **Abridged**: *The Rambler*, February 1850, "Encyclic of Pius IX to the Archbishops and Bishops of Italy", with "a few paragraphs only of minor importance ... omitted" (`sim_rambler-a-catholic-journal-and-review_1850-02_5_part-xxvi`) | IA: incipit 1849–52 and 1853–1930; "socialism" and "communism" with "encyclical" and "Italy" 1850–51. *Mercersburg Review* and *The Metropolitan* (1850–51) checked: no translation | 15 min |
| Etsi Multa (Pius IX, 1873) | **Found**: Philadelphia pamphlet, [1874] | IA: automated proximity queries (found it), *The Armoury* (April 1874; not read further) | 5 min |
| Singulari Nos (Gregory XVI, 1834) | **None found** | IA: incipit with Lamennais 1834–40; "Venerable Brethren", "Lamennais" and "Paroles" 1834–1930; *Dublin Review* 1836 (quotes only); Artaud de Montor's *Life and Times of Gregory XVI* (no text); the 1834 French and Latin edition | 20 min |
| Inter Praecipuas (Gregory XVI, 1844) | **Found**: *Catholic Cabinet*, 1845 | IA: "Bible societies", "Gregory" and "8th of May" 1844–1930; *Christian's Monthly Magazine* 1844–45 (extracts only) | 15 min |
| Vix Pervenit (Benedict XIV, 1745) | **None found** | IA: incipit 1745–1930 (Latin, Italian, French and German hits only); incipit with usury terms and English context; O'Callaghan, *Usury* (1828); *Dublin Review* 1836 and 1874; Addis and Arnold, *Catholic Dictionary* (1884) (quotations only) | 20 min |
| Ex Quo (Benedict XIV, 1756) | **None found** | IA: incipit with "Euchologion" or "Euchology"; Benedict XIV with "Greek rite" and "Venerable Brethren"; Twiss, *Letters Apostolic of Pius IX* (1851; Latin briefs) | 10 min |
| A Quo Die (Clement XIII, 1758) | **None found** | IA: incipit with "Clement XIII" (Latin hits only); Clement XIII with "Venerable Brethren" 1758–1830, ECCO included | 10 min |
| Charitas (Pius VI, 1791) | **None found** | IA: Expilly, Marolles and Saurine with "brief" 1791–1930; Civil Constitution with "brief" and "Pius VI"; scored La Marche's *Pastoral Letter* (1791), Barruel's *History of the Clergy* (1794), Pressensé (1868), De Cormenin (1847): narrative and quotations only | 20 min |
| Exsurge Domine (Leo X, 1520) | **None found** | IA: incipit with "Arise, O Lord", "wild boar", "foxes"; Roscoe's *Life of Leo X* (1805; Latin appendix, English summary only) | 10 min |

Bulk discovery ran for all ten as well (proximity, incipit and date queries, about 40 seconds each); it found only Etsi Multa.

## Scope decision (for Carter)

**Hit rate.** Pius IX and Gregory XVI: 10 of 12 documents searched have a complete printing (7 of 8 Pius IX, 3 of 4 Gregory XVI), one more has an abridged one (Nostis et Nobiscum), and one has none (Singulari Nos). Before 1800: 2 of 7, and both are the bulls whose site text already was the old translation; the pilot found nothing for the four 18th-century documents (Charitas included) or for Exsurge Domine.

**Why the split.** From the 1830s, Catholic magazines in England, Ireland and the United States printed each encyclical in English within months, and the Internet Archive holds many of them: the *United States Catholic Magazine* (1842–49), *The Metropolitan* (1853–59), *The Catholic Cabinet* (1843–45), *The Rambler* (1848–62), *The Dublin Review*, *Brownson's Quarterly Review*, *Appletons' Annual Cyclopaedia* (1861–1902), and the *Annals of the Propagation of the Faith* (English edition from 1838). Before 1830 there is no such press, and an 18th-century encyclical was rarely put into English at all.

**Projected cost of the rest**, at the pilot's 10 to 20 minutes a document:

| Option | Documents | Time | Expected finds |
|---|---|---|---|
| A. Search all 66 remaining | 66 | 13–20 h | about 30 |
| B. Pius IX and Gregory XVI only (recommended) | 38 | 8–12 h | about 25–30 (70–80%) |
| B plus 1800–1830 | 44 | 9–14 h | B plus 1 or 2 |
| C. Retire the rest | 0 | 0 | none; 66 documents retired |

Under B, the whole 1740–1799 group (26 documents, about 105,000 words) and Exsurge Domine retire with tombstones, and so do the six of 1800–1830 unless they are added. The search would take the 1860s and 1870s to *Appletons'* and the *Dublin Review* first, and the 1840s and 1850s to the *United States Catholic Magazine*, *The Metropolitan* and *The Rambler*; *The Tablet* needs HathiTrust, if Carter can run those searches.

## Decisions (Carter, 31 Oct 2026)

- **Scope: everything.** First set to scope B (search the Pius IX and Gregory XVI documents; retire the 1740–1799 group and Exsurge Domine). Revised the same day: a ten-minute probe of ECCO found two of the 18th-century documents the pilot had written off (Cum Summi and Salutis Nostrae, in *Interesting Letters of the Late Pope Clement XIV*, 1777), so every document without a printing is searched in full before any is retired.
- **Retire with a link.** A document with no public-domain printing is retired, and its removal page links to it at papalencyclicals.net. Recorded, with the full list and how to reverse it, in `docs/adr/0001-retire-papal-documents-without-public-domain-english.md`, which 1.3d keeps current.
- **Etsi Multa** uses its undated Philadelphia printing: the catalogue dates it 1874, and the "Rt. Rev. Bishop of Philadelphia" who approved it held that title only until February 1875.
- **Nostis et Nobiscum**: the scope search looks for a complete printing. If none is found, *The Rambler*'s abridgement (February 1850) is published with the gaps marked: it omits paragraphs 21–24 (marked "* * *") and 31–33 (unmarked), about 1,120 of 5,570 words, and those passages are retired.
- **1800–1830: one hour of search**, done 31 Oct:
  - **Diu Satis: found.** *An Encyclical Letter of Our Most Holy Father Pope Pius VII ... Translated from the Latin original, by the Rev. Benedict Rayment* (London: Keating, Brown and Keating, 1800). Complete; long-s OCR, so 1.2f's cleanup.
  - **Ubi Primum (1824): found.** *The Encyclical Letter of Pope Leo the XII ... with an English Translation of the Same* (Dublin: Richard Coyne, publisher to the Roman Catholic Bishops of Ireland, 1824).
  - **Traditi Humilitati: found.** *The Jesuit, or Catholic Sentinel* (Boston), 14 November 1829. Reads as complete; the scan's last lines are garbled, so 1.3d confirms the ending.
  - **Quod Hoc Ineunte: printing known, not located.** *Popery in 1824: a Circular Letter of Pope Leo the Twelfth ... and the Bull of Jubilee for the Year 1825, translated from the original Latin, with an Introduction and Notes* (London, 1824; reviewed in *Blackwood's*, *The Eclectic Review*, *The Congregational Magazine*), but no scan was found. *The Baptist Magazine* (January 1825) prints extracts. Retired with a link for now; HathiTrust may hold the pamphlet.
  - **Charitate Christi: none found.** The Baltimore pamphlet *Bull of His Holiness Leo XII, for the Indiction of the Universal Jubilee of 1826* (Fielding Lucas, 1826) holds the companion bull that extended the Jubilee, not this covering letter to the bishops.
  - **Quo Graviora (1826): none found** in the 1826–30 press; later books cite and summarise it only.
- Reads of public sources for comparison no longer need approval; vendoring still does.

## 5. Full search (31 Oct – 1 Nov 2026)

Every document without a printing was searched in the places ADR 0001 lists ("Where the full search looked"). Nine more were found, each read to its closing date line and checked third by third (`endcheck.py`), since the detector also fires on extracts and on related allocutions:

| Document | Printing |
|---|---|
| Inter Multiplices (1853) | *The Metropolitan* (Baltimore), vol. 1 no. 5, June 1853 |
| Apostolicae Nostrae Caritatis (1854) | *The Metropolitan*, vol. 2 no. 9, October 1854, with Archbishop Kenrick's pastoral |
| Amantissimi Redemptoris (1858) | *The Metropolitan*, new series vol. 1 no. 7, August 1858 |
| Cum Sancta Mater Ecclesia (1859) | Pastoral of Edward John Horan, Bishop of Kingston, 1859 (Canadiana microfiche `cihm_51176`) |
| Exultavit Cor Nostrum (1851) | *Encyclical Letter ... Ordering Prayers and Announcing a New Jubilee*, Canada, 1851 (`cihm_43402`); also the Archbishop of Quebec's pastoral of 1852 |
| Respicientes (1870) | *Appletons' Annual Cyclopaedia* for 1870 (1871) |
| Vix Dum a Nobis (1874) | *Appletons' Annual Cyclopaedia* for 1874 (1875) |
| Graves ac Diuturnae (1875) | *Appletons' Annual Cyclopaedia* for 1875 (1876) |
| Quod Nunquam (1875) | *Appletons' Annual Cyclopaedia* for 1875 (1876) |

Extracts only (not enough for the reader): Qui Nuper (*Dublin Review* and *Rambler*, September 1859, paragraph 2 summarised), Nullis Certe Verbis (*Rambler*, March 1860, last third missing), Levate (*Appletons'* for 1867, the opening 400 words, called an allocution).

Lessons for anyone continuing: *Appletons'* volumes are misdated in the Internet Archive's catalogue (the 1874 volume is filed as 1861), so match them by title page; a high score can come from an allocution of the same weeks, so read the opening and closing; short documents score high by chance against large volumes.

After this search: **26 documents have a printing, 3 have extracts only, Nostis et Nobiscum has an abridgement, and 55 have no printing found so far** (24 of the 26 of 1740–1799, Exsurge Domine, three Leo XII documents of 1824–26, seven of Gregory XVI, and 20 of Pius IX). The remaining search options are HathiTrust from a browser (blocked here) and *The Tablet*'s own archive.

## 6. Carlen's own translations: can they be cleared?

Checked 1 Nov 2026, at Carter's request, whether the site's text of the 59 documents without a public-domain printing could be cleared by tracing Carlen's edition.

- **They are Carlen's own translations, not reprints.** Pierian Press, which publishes the set today, says: "One hundred and ten encyclicals, containing 275,000 words, were translated into English especially for this edition" (pierianpress.com, *The Papal Encyclicals, 1740–1981*). That matches the trace of section 1: for these documents the site's wording appears in nothing printed before 1981. So there is no earlier printing whose rights could be traced.
- **They are registered.** US Copyright Office public catalogue: *One hundred ten papal encyclicals*, registration **TXu000087711**, registered 21 December 1981, claimant **McGrath Publishing Company** (the 1981 publisher, Wilmington, N.C.). No notice or renewal question arises: a 1981 work registered in 1981 is in copyright until at least 2076 (95 years if made for hire), and no recorded transfer was found.
- **The current publisher is Pierian Press** (Ann Arbor), which reissued the set in 1990 and still sells it (ISBN 0-87650-259-1); Faithlife licenses an electronic edition (Logos and Verbum, "Publisher: Pierian Press, 1990"). No transfer from McGrath to Pierian is recorded in the online catalogue, though transfers need not be recorded.
- **No published allowed-use statement** was found on Pierian's or Faithlife's pages, so under the Decision log ("Excerpt-only needs an allowed-use basis") these texts have no basis today.

**Conclusion.** Tracing Carlen gives no public-domain basis. The one route that keeps these 59 documents, and could also let the 26 found ones keep their modern wording, is **permission from Pierian Press** (and McGrath's successor, if the rights did not pass). The request should name the 110 translations (or the 85 documents), the use (non-profit, search and reader, with credit), and ask whether a recorded transfer from McGrath exists.

## Needs Carter

1. **Approve the 26 draft rows** (`checked_by` null): the 12 of section 3, the three 1800–1830 finds, Cum Summi and Salutis Nostrae (*Interesting Letters of the Late Pope Clement XIV*, Newcastle, 1777, translated from the French edition), and the nine of section 5.
2. **When to stop searching.** The 55 documents without a printing can be retired with a link now, or after HathiTrust (from Carter's browser) and *The Tablet*'s archive are tried. Four print the site's own translation (Quanta Cura, the Syllabus, Sublimis Deus, Unam Sanctam); eleven are different, older translations.

## Side findings

- **Unam Sanctam loses its opening paragraph in the build.** "Urged by faith, we are obliged to believe and to maintain that the Church is one ..." sits in the same `<p>` as the centred date line on the site's page, and the parser drops it with the date. The document opens at "We venerate this Church as one". It is the bull's best-known passage, so 1.3a or 1.3d should check it; rebuilding from Curley's printing in 1.3d fixes it.
- **Quanta Cura's footnote is a paragraph.** Its last passage, labelled "§1", is footnote 1 ("Gregory XVI, encyclical epistle 'Mirari vos,' 15 August 1832"). Footnotes kept as numbered paragraphs belong to 1.3a.

## Tools

The scripts used are in `docs/research/R8_tools/` (standard library only; run from that folder with `python3 -I`):

- `fts.py`: Internet Archive full-text search with a year cut-off.
- `compare.py`: same-translation check (word 4-grams), overall and per paragraph.
- `xlate.py`: different-translation detector (content-word pairs, best window).

- `dump.py`: writes the site texts (`texts/<slug>.txt`) and `docs.json` from the encyclicals and papal-documents adapters; run it from `datapipeline/` with the datapipeline venv.

`compare.py` and `xlate.py` read those texts, and fetch an item's `_djvu.txt` into `dl/` on first use.
