# R6. Edition and provenance check for each planned source

Research for corpus-cleanup item R6 (`docs/corpus-cleanup/P0-checks-identity-research.md`, GitHub issue #149), which blocks 1.2c, 1.2d, 1.2e, 1.8d and every 5.x addition. Done 4 and 5 October 2026 (second pass, completing 5.6c, on 5 October). No production store was queried and no source file was kept: pages, catalogue records and the opening bytes of each file were read, and sizes come from HTTP headers or the repository's own file listing.

## Result

- **230 planned works** now have a row in `datapipeline/rights_inventory.json`, each with `planned_for` set to the item that will ingest it: 1.8d 1, 1.2c 7, 1.2d 1, 1.2e 11, 5.3a 60, 5.3b 5, 5.4 7, 5.5 2, 5.6a 14, 5.6b 36, 5.6c 86. The second pass (5 Oct 2026) added 36 of the 5.6c rows: Pohle-Preuss 12, Koch-Preuss 5, Bellarmine's *Ascent* 1, Marmion's *Christ in His Mysteries* 1, Centenary Edition 14, Summa contra Gentiles 3. Every row is a draft (`checked_by` null) until Carter approves it.
- **Statuses:** 143 `pd-us-pre-1931`, 73 `in-copyright` (vatican.va texts, rights holder Libreria Editrice Vaticana), 12 `pd-us-non-renewal` (Schroeder 1937 and Schaff's sixth-edition *Creeds* vol. 2, each with its renewal search), 2 `unknown` (Tanquerey's printing, the Everyman *Dialogue of Comfort*).
- **The P1 replacements all check out.** Robertson's *On the Incarnation* (npnf204), Percival's NPNF2-14 (1900), Schaff's *Creeds* vol. 2 (the file is the 1931 sixth edition, no renewal found; its Vatican I text is identical to the 1877/1878 printing) and Schroeder's 1937 *Disciplinary Decrees* (no renewal found) are the editions the Decision log names, and each row records its basis.
- **Edition verdicts:** 224 match the edition the Decision log, a spec or the memos name (73 of them are vatican.va texts, whose only edition is the vatican.va English). 3 differ from what a memo or spec assumed: the *Way of Perfection* (the memo's Dalton 1852 fails the Decision log's Lewis-or-Stanbrook rule, so the row uses Stanbrook), the *Spiritual Combat* (the memo's "Catholic" Burns 1846 is an Anglican edition) and Catherine's *Dialogue* (CCEL's file is the 1907 abridgement). 1 has no English source at all (A New Hope for Lebanon). 2 are `unknown` (Tanquerey's printing, the Everyman *Dialogue of Comfort*). No planned work turned out to lack a public-domain edition apart from Lebanon, which is an in-copyright Vatican text with no English.
- **Renewal searches run:** Schroeder 1937 (none found; recorded in the 11 rows), Schaff's *Creeds of Christendom*, sixth edition, 1931 (none found; recorded in the Vatican I row) and McHugh and Callan's 1934 revised Roman Catechism (none found; recorded below only, since the row uses the 1923 first edition). The second pass needed none: every edition it found was published in 1930 or earlier, including the US printings of 1928 (Koch-Preuss vol. 2), so all are public domain by term.
- **Download list:** 245 files, 2,006,799,143 bytes. 153 text, XML or HTML files are 152,606,341 bytes; the other 92 are page-image PDFs and one hOCR file (1,854,192,802 bytes) needed only for the OCR route and its 20-passage check. sha256 fields are left for after Carter approves the downloads.

## Inventory format change

Carter decided on 4 Oct 2026 that planned works get rows now, with a new field `planned_for` naming the item that will ingest the work (for example "1.2c" or "5.6b"). Commit 5b5eae9 adds it to `REQUIRED_FIELDS` in `datapipeline/rights_inventory.py`, sets it to null on the 421 built works, and changes `tests/test_rights_inventory.py`: the coverage check still requires a row for every built work, ignores planned rows when looking for stale ones, and requires a built work's row to have `planned_for` cleared; a new test checks that `planned_for` is null or a non-empty string.

## Method

- **CCEL.** The size is the one CCEL's server reports in its ETag. For four vendored files (Boethius, On Loving God, ANF 1, Imitation) that figure equals the `bytes` in our manifests exactly. Header fields (`DC.Rights`, `published`, `pubHistory`, `comments`, `DC.Source`) and the title page were read from the first 25 to 40 KB of each ThML file. Where the header named no edition, the whole file was streamed and searched without saving, and for two works (the *Devout Life*, the *Pensées*) compared against a dated scan by sampling 200 six-word sequences.
- **Project Gutenberg.** Sizes from `Content-Length`; title page from the first 9 KB of the plain text.
- **Internet Archive.** Metadata and file sizes from `archive.org/metadata/<id>`; title page from the first 6 KB of the item's OCR text (`_djvu.txt`).
- **vatican.va.** Sizes from `Content-Length`, or the byte count of a GET where the server sends none. vatican.va pages are generated, so their size can change between fetches.
- **Renewal searches.** NYPL's transcription of the Catalog of Copyright Entries renewals (github.com/NYPL/cce-renewals, `data/` at commit ebb6156), the same copy used for the Imitation of Christ row. Each year file covering the renewal window was checked for renewals dated in all twelve months. The Stanford Copyright Renewal Database refuses automated access and was not used.
- **source_path for planned rows** is where the file will be vendored, under the collection the ingesting item names: `theologians/`, `church-law/` and `papal` as the 5.1b keys, and, for a scanned work, the folder of its Internet Archive item, the same folder the download list uses (for example `theologians/bookfoundations00teregoog/`). A work that spans several items (Teresa's *Letters*, Bernard's *Canticle* sermons) uses the folder of its first item; the download list puts every item in its own folder. The two 5.4 files that are already vendored keep their present paths. The ingesting PR may change the path or the `work` title to what it actually builds; it then edits the row and sets `planned_for` to null, which the coverage test now requires.
- **Credit lines** follow the Decision log examples: "Sourced via CCEL.org", "Text: Libreria Editrice Vaticana", and, as proposals, "Sourced via Project Gutenberg" and "Scan: Internet Archive" (with "Translated by X (year)" where the translator is a named person).

## P1 replacements

### 1.8d. Athanasius, *On the Incarnation*: Robertson (npnf204)

- **File:** `https://ccel.org/ccel/s/schaff/npnf204.xml`, 5,809,854 bytes. Header: `DC.Rights` Public Domain, `published` "New York: Christian Literature Publishing Co., 1892", `DC.Source` Logos Inc., "carefully proofread and corrected".
- **Title page** (IA scan `selectlibraryofn0000unse`, a 1907 Scribner reissue): NPNF second series vol. IV, *St. Athanasius: Select Works and Letters*, "Copyright, 1892, by the Christian Literature Company", printed by Parker, Oxford. The volume's own note says the translation of *De Incarnatione* "is that printed in 1885 (D. Nutt, second edition, 1891) by the editor of this volume", Archibald Robertson.
- **Section check:** the CCEL page `npnf204.vii.ii.i` opens "§1. Introductory.—The subject of this treatise…" and then "Whereas in what precedes we have drawn out", the sentence 1.8d's test expects. The italic lead sentence of each section is Robertson's own "analytical heading" (his word), which 1.8d strips under rule G.
- **Verdict:** matches the Decision log (Robertson, npnf204). `pd-us-pre-1931`. Route: clean ThML.

### 1.2c. Councils 1 to 7: Percival (NPNF2-14)

- **File:** `https://ccel.org/ccel/s/schaff/npnf214.xml`, 3,196,008 bytes. Header: `DC.Rights` Public Domain, `published` "Edinburgh: T&T Clark", "carefully proofed". CCEL's title page is the T&T Clark and Eerdmans photographic reprint.
- **Original title page** (IA `sevenecumenicalc00perc`): *A Select Library of Nicene and Post-Nicene Fathers*, second series, vol. XIV, *The Seven Ecumenical Councils of the Undivided Church*, Oxford: James Parker and Company; New York: The Christian Literature Company, MDCCCC. "Edited with notes gathered from the writings of the greatest scholars by Henry R. Percival." His preface says the translations are mostly other scholars' work, adopted after comparison with the originals; the translator column records that.
- **Verdict:** matches. `pd-us-pre-1931`. Route: clean ThML. One row per council (the seven existing council titles, source path `councils/npnf214.xml`).

### 1.2e. Councils 8 to 18: Schroeder 1937

- **Title page** (IA `DisciplinaryCouncils`, OCR text read): *Disciplinary Decrees of the General Councils: Text, Translation, and Commentary*, by Rev. H. J. Schroeder, O.P., B. Herder Book Co., 15 & 17 South Broadway, St. Louis, Mo., and 33 Queen Square, London, 1937. "All rights reserved. Printed in U.S.A." Imprimatur St. Louis, 7 April 1937. "Copyright 1937 B. Herder Book Co." Printed by Vail-Ballou Press. The preface says the book covers the general councils "up to and exclusive of the Council of Trent".
- **Renewal search** (recorded in all 11 rows): a 1937 US copyright had to be renewed in its 28th year, 1964 or 1965. Both year files are complete, with renewals dated in every month. Searched every file for the titles "disciplinary decrees" and "general councils", the names "schroeder", "h. j. schroeder", "henry joseph schroeder" and "schroeder, henry", and the claimant "herder". **No renewal found.** "herder" matches five entries, none a B. Herder Book Co. claim; the "schroeder" renewals of 1936 to 1938 originals are music and fiction; the one "general councils" match is an unrelated 1961 registration. The 1965 file does contain a 1937 Catholic book on the same subject (Clement Raab, *The twenty ecumenical councils of the Catholic Church*, renewed 15 January 1965), so the file covers titles of this kind.
- **Fordham.** The Internet Medieval Sourcebook pages for Lateran I (`basis/lateran1.asp`, 79,745 bytes), Lateran II (83,314) and Lateran IV (218,572) cite Schroeder 1937 with page ranges (pp. 177-94, 195-213, 236-296) and carry this note: B. Herder's list was bought by TAN Books, and "TAN confirmed that US copyright was not renewed". Each page also says the sourcebook's "specific electronic form of the document is copyright", permits educational and personal copying, and grants "No permission ... for commercial use". Lateran I and II keep Schroeder's notes; Lateran IV drops his commentary. See "For Carter".
- **Wikisource** tags its Schroeder transcription `{{PD-US-no-renewal}}`; the scan memo counted 27 of 677 pages proofread. Not re-counted.
- **Verdict:** matches. `pd-us-non-renewal`. Route: partial (Fordham for three councils, OCR for eight).

### 1.2d. Vatican I: Schaff, *Creeds of Christendom* vol. 2

- **File:** `https://ccel.org/ccel/s/schaff/creeds2.xml`, 4,065,931 bytes. Header: `DC.Rights` Public Domain, `published` "Sixth Edition", `firstPublished` 1877, proofed by CCEL volunteers.
- **CCEL title page:** "Reprinted by arrangement with Harper and Row, Publishers. The Creeds of Christendom Copyright, 1877, by Harper & Brothers. Copyright, 1905, 1919 by David S. Schaff. Printed in the United States of America." The volume's note is dated December 1889.
- **Comparison with the first edition:** IA `creedsofchristen02scha` is the Harper 1878 printing, "Entered according to Act of Congress, in the year 1877". Its Pastor Aeternus chapter 4 reads, as CCEL's does, "by virtue of his supreme Apostolic authority, he defines a doctrine regarding faith or morals to be held by the universal Church, by the divine assistance promised to him in blessed Peter, is possessed of that infallibility with which the divine Redeemer…", and the Syllabus item 34 also matches. Schaff's headnote names the source of the English: "Archbishop Manning: Petri Privilegium, London, 1871".
- **Edition of the file:** the header's "Sixth Edition" is Harper's sixth edition of 1931, revised by David S. Schaff. The verso in the file names no copyright later than 1919.
- **Renewal search** (recorded in the row): a 1931 copyright had to be renewed in 1958 or 1959. Both year files are complete, with renewals dated in every month. Searched every file for "creeds of christendom", "creeds", "bibliotheca symbolica", "schaff", "david s. schaff" and "schaff, david", and reviewed the Harper renewals of 1929 to 1933 originals. **No renewal found.** "schaff" matches only unrelated Schaffner and Schaffer entries, "creeds" two unrelated titles, and none of the 47 Harper renewals of 1931 originals is the *Creeds*.
- **Verdict:** the Vatican I chapter text matches the 1877 edition (1878 printing) word for word; the file to be vendored is the 1931 sixth edition. `pd-us-non-renewal`, first published 1931 in the row. Route: clean ThML.

## P5 works, in phase-plan order

### 5.3a. Roman Curia: DDF documents (60)

The 60 files are already vendored (`datapipeline/sources/roman-curia/`, hashed in `source_lock.json` as `vendored-unregistered`), so no download is needed. Rows are generated from the parked branch's manifest: title, issuer as printed (Sacred Congregation, Congregation or Dicastery for the Doctrine of the Faith), `roman-curia/<file>`, the vatican.va URL, `in-copyright`, rights holder Libreria Editrice Vaticana, credit "Text: Libreria Editrice Vaticana". Edition: the vatican.va English, the only edition the plan uses for these.

### 5.3b. Roman Curia: further texts (5)

| Work | Issuer | Finding |
|---|---|---|
| Compendium of the Social Doctrine of the Church | Pontifical Council for Justice and Peace | vatican.va page ends "© Copyright 2004 Libreria Editrice Vaticana". 1,160,524 bytes. |
| Redemptionis Sacramentum | Congregation for Divine Worship | vatican.va English; no ICEL notice on the page. 258,086 bytes. |
| Directory on Popular Piety and the Liturgy | Congregation for Divine Worship | vatican.va English; no ICEL notice on the page. 531,807 bytes. |
| The Bible and Morality (2008) | Pontifical Biblical Commission | vatican.va English. 373,861 bytes. |
| The Jewish People and Their Sacred Scriptures in the Christian Bible (2001) | Pontifical Biblical Commission | vatican.va English. 386,428 bytes. |

- **GIRM: no row.** The vatican.va English GIRM page states "The English translation of the General Instruction of the Roman Missal (Third Typical Edition) © 2002, International Committee on English in the Liturgy, Inc. All rights reserved." The Decision log drops liturgical norms in ICEL English.
- **Biblical Commission:** the commission's index on vatican.va lists English only for the two documents above. *The Interpretation of the Bible in the Church* (1993) and the 2014 and 2019 documents have no English link there.

### 5.4. Papal and universal law (7)

- **Ubicumque et Semper** (`papal-documents/ubicumque-et-semper.html`, vendored): full English text, ending "© Copyright 2010 - Libreria Editrice Vaticana".
- **A New Hope for Lebanon** (`apostolic-exhortations/a-new-hope-for-lebanon.html`, vendored, 32,369 bytes): **the file has no text, and vatican.va publishes no English.** The vendored file is the English URL, which offers only "FR - IT"; the original is French, *Une espérance nouvelle pour le Liban*, signed at Harissa on 10 May 1997. The French page is 407,827 bytes and is now the row's source URL. Off vatican.va, web searches on 5 Oct 2026 found English commentary on the exhortation (for example the *Journal of Maronite Studies*, 1998, at maronite-institute.org) but no English text and no record of a published English edition. See "For Carter".
- **Amoris Laetitia** (`apostolic-exhortations/amoris-laetitia.html`, vendored, 35,875 bytes): **the file has no text** either; the English page holds only a "DOWNLOAD PDF" link. The English is a PDF, 1,330,556 bytes. The row's source path is `apostolic-exhortations/amoris-laetitia.pdf`. See "For Carter".
- **Universi Dominici Gregis:** the consolidated English page (122,061 bytes) is headed "Revised in accordance with the modifications introduced by ... Normas nonnullas of 22 February 2013" and links the 1996 original as an English PDF (264,696 bytes), the 2007 motu proprio in French, German and Latin only (Latin page 37,052 bytes), and *Normas nonnullas* in English (47,878 bytes). This matches the source memo.

All seven are `in-copyright`, rights holder Libreria Editrice Vaticana.

### 5.5. Catechisms (2)

- **Compendium of the CCC:** vatican.va English, 378,892 bytes. `in-copyright`, LEV.
- **Roman Catechism, McHugh and Callan.** Four open Internet Archive scans are catalogued "1923", but three are later printings: `catechismofcounc0000cath` reads "Sixteenth printing, January, 1962 ... Copyright, 1934", `catechismofcounc0000pope` reads "Second revised edition, sixth printing, September, 1937 ... Copyright, 1934", and `bwb_P9-DTM-981` is a modern reprint (ISBN 1-929291-23-X). Only **`catechismofcounc0000jose`** (General Theological Seminary copy) reads "Copyright, 1923, by Joseph F. Wagner, New York" with the imprimatur of 3 January 1923. That is the row's edition: `pd-us-pre-1931`, route OCR (1,321,558 bytes of OCR text, 31,743,469-byte PDF).
- **Renewal search on the 1934 revision** (not in the row): the 1961 and 1962 files (the 28th-year window) and every other file were searched for "council of trent", "catechism", "mchugh", "callan", "john a. mchugh", "charles j. callan", "joseph f. wagner" and "wagner, inc". No renewal of either edition. McHugh and Callan renewals exist only for Kenedy prayer books (1925, 1928) and the 1937 Spencer New Testament.
- **Clean text:** Fordham's Modern History Sourcebook has the whole translation (`mod/romancat.asp`, 1,412,923 bytes) as "Source: Unknown etext", "produced using a scanner. It was spell-checked, but that's all", with the same Halsall notice as above. Its printing is not stated. A sample of 6-word and 8-word sequences matched the 1923 and the 1934 OCR at the same rate, so OCR noise hides any difference between the editions. See "For Carter".

### 5.6a. Church Fathers additions (14)

All are CCEL ThML, `DC.Rights` Public Domain, route clean ThML, `pd-us-pre-1931`. Title pages read from the Toronto and other IA scans:

| Volume | Title page | Translator (from the CCEL file) | Bytes |
|---|---|---|---|
| npnf208 | NPNF2 vol. VIII, *St. Basil: Letters and Select Works*, New York: Christian Literature Co.; Oxford and London: Parker, 1895, copyright 1895 | Blomfield Jackson | 3,303,323 |
| npnf207 | vol. VII, *S. Cyril of Jerusalem. S. Gregory Nazianzen*, same publishers, 1894 | Cyril: Edwin Hamilton Gifford; Gregory: Charles Gordon Browne and James Edward Swallow | 4,247,548 |
| npnf212 | vol. XII, *Leo the Great. Gregory the Great*, 1895 | Leo: Charles Lett Feltoe; Gregory: James Barmby | 3,461,929 |
| npnf213 | vol. XIII part II, *Gregory the Great. Ephraim Syrus. Aphrahat*, 1898 | Gregory: James Barmby | 2,246,124 |
| npnf210 | vol. X, *St. Ambrose: Select Works and Letters*, 1896 | H. de Romestin, with E. de Romestin and H. T. F. Duckworth | 3,837,030 |
| npnf109 to npnf114 | NPNF first series vols. IX to XIV, Chrysostom, New York: Christian Literature Co., 1889 (IX, XI, XII, XIII), 1890 (XIV); vol. X read from a 1908 Scribner reissue, first published 1888 | several, named per work | 3,017,592; 3,956,654; 5,349,065; 3,253,154; 4,441,248; 4,728,349 |
| dionysius/works | *The Works of Dionysius the Areopagite*, part I London and Oxford: James Parker, 1897; part II (both *Hierarchies*) 1899. Transcribed by Roger Pearse, 2004; header "Rights: public domain" | John Parker | 731,266 |

- The volume identifiers in 5.6a's spec, marked "from memory", are all correct. npnf213 also holds Ephraim Syrus and Aphrahat, which 5.6a does not plan; its adapter takes Gregory's letters only.
- The rows are one per author per volume, because the built document titles are not known until 5.6a's adapter exists. The ingesting PR splits them into per-work rows.
- Vol. 12's section title page for Gregory was not re-read; Barmby is named as translator on vol. 13's.

### 5.6b. Theologians and spiritual writers from text sources (36)

CCEL ThML, all `pd-us-pre-1931` unless noted:

| Work | Title page or header facts | Match | Bytes |
|---|---|---|---|
| Teresa, *Interior Castle* | Stanbrook, revised by Zimmerman, 3rd ed., Thomas Baker, London [1921], imprimatur 24 Feb 1921; CCEL source sacred-texts.com | matches (Stanbrook 1921) | 582,155 |
| Teresa, *Life* | David Lewis, 3rd ed. enlarged, Zimmerman intro., Baker / Benziger, MCMIV | matches (Lewis 1904) | 1,639,686 |
| Francis de Sales, *Introduction to the Devout Life* | no date in the file; the 1876 Rivingtons scan (IA `introductiontod00salegoog`, "Library of Spiritual Works for English Catholics ... A New Translation, Rivingtons, MDCCCLXXVI") matches 178 of 200 sampled sequences | year settled: 1876 | 651,626 |
| Francis de Sales, *Treatise on the Love of God* | Mackey; TAN Books 1997 reprint, "Originally published in approximately 1884 by Burns & Oates" | matches; strip TAN matter | 1,890,439 |
| Julian, *Revelations* | Grace Warrack, "First published 1901" | matches | 395,019 |
| Thérèse, *Story of a Soul* | from Project Gutenberg; Taylor, Burns Oates & Washbourne 1912, 8th ed. 1922; the printing used is not stated | matches (both pre-1931) | 681,615 |
| Ignatius, *Spiritual Exercises* | Elder Mullan, P. J. Kenedy, copyright 1914 | matches | 266,222 |
| Ignatius, *Autobiography* | O'Conor, Benziger, copyright 1900 | matches | 173,374 |
| *Cloud of Unknowing* | Underhill, second edition, John M. Watkins, 1922 | same edition, 1922 printing (spec says 1912) | 332,558 |
| Hilton, *Scale of Perfection* | Dalgairns essay; no date; companion file names Art and Book Co. / Benziger 1901 | matches | 743,898 |
| Hilton, *Treatise to a Devout Man* | Art and Book Co. / Benziger 1901 | matches | 83,173 |
| *Cell of Self-Knowledge* | Gardner; CCEL from the 1966 Cooper Square reprint of the 1910 edition | matches (1910 text) | 236,948 |
| Rolle, *Fire of Love* and *Mending of Life* | Methuen, 1st 1914, 2nd ed. 1920; CCEL: "this edition is not identical to the print source", footnote words substituted in places | matches, with a flag | 523,180 |
| Ruusbroec | Wynschenk Dom, ed. Underhill, 1916 | matches | 503,384 |
| Tauler, *Inner Way* | Hutton, Methuen, first May 1901, 2nd ed. Nov 1909 | matches | 558,831 |
| Suso, *Little Book of Eternal Wisdom* | Burns Oates & Washbourne, imprimatur 14 April 1910; includes Hilton's *Parable of the Pilgrim* | matches | 274,062 |
| Suso, *Life* | Knox, Burns, Lambert, and Oates, 1865 | matches | 475,872 |
| Bernard, *Letters* | Eales, John Hodges, 1904 | matches | 711,583 |
| Anselm, *Devotions* | Webb, Methuen, 1903 | matches | 345,840 |
| Chesterton, *Everlasting Man* | "(1925)", no publisher | matches | 603,115 |
| Newman, *Dream of Gerontius* | no printing named | 1865 poem | 57,878 |
| Pascal, *Pensées* | CCEL names no source; matches 173 of 200 sequences of the Harvard Classics vol. 48 scan (IA `thoughtstrbywftr00pascuoft`, P. F. Collier, "Copyright 1910") | matches (Trotter 1910) | 732,500 |
| Aquinas, *Catena Aurea* Matthew, Mark | "J.G.F. and J. Rivington, London, 1842"; header's "tr. William Whiston" is wrong | matches | 3,021,275; 971,399 |

Not taken from CCEL: **Catherine of Siena, *Dialogue***. CCEL's file reads "A New and Abridged Edition. Originally published in 1907 by Kegan Paul". As 5.6b's spec directs for that case, the complete 1896 translation goes to 5.6c (IA `seraphicvirginca00cathuoft`, Kegan Paul 1896, 380 pages).

Project Gutenberg, all `pd-us-pre-1931`:

| Work | eBook | Title page | Bytes |
|---|---|---|---|
| Alphonsus, *Glories of Mary* | 72411 | Second American edition, Dunigan, New York, 1852 | 1,232,145 |
| Caussade, *Abandonment* | 52057 | revised by Ramière, tr. Ella McMahon, Benziger, copyright 1887 | 222,404 |
| Brother Lawrence | 13871 | Revell, undated; the Revell edition with the same preface reads "Copyright, 1895, by Fleming H. Revell Company" (IA `cihm_05552`) | 80,593 |
| Newman, *Apologia* | 22088 | Longmans, Green, 1890 (Newman's revised text) | 818,677 |
| Newman, *Development* | 35110 | "Sixth edition"; dedication and "Preface to the edition of 1878" dated 1878; print source a University of Notre Dame Press reprint | 845,927 |
| Newman, *Idea of a University* | 24526 | no title page in the file | 961,540 |
| Newman, *Grammar of Assent* | 34022 | Burns, Oates, 1874 | 815,513 |
| Catherine, *Letters* (Scudder) | 7403 | no date in the file; first published 1905 | 636,790 |
| Mechthild (Bevan, selections) | 35811 | James Nisbet, 1896 | 214,851 |
| Chesterton, *St. Francis of Assisi* | 63084 | Hodder and Stoughton, People's Library printing, undated (first published 1923) | 270,046 |
| Chesterton, *Catholic Church and Conversion* | 76305 | Macmillan, copyright 1926, September 1927 printing | 163,703 |
| Francis de Sales, *Maxims and Counsels* | 73661 | 2nd ed., M. H. Gill, Dublin, 1884 | 132,874 |

- **Apologia:** the row uses 22088 (title page Longmans 1890). 19690 is an undated Everyman printing whose introduction cites a 1912 biography, so it is later and carries an editor's introduction.
- **Development:** 35110 does reproduce the 1878 revision, as the Decision log requires; the file has no foreword by a modern editor.

### 5.6c. Scanned works (50)

All scans below are open (not lending-only). Each row lists the OCR text and the page-image PDF in the download list. Title-page facts are from the OCR of the opening pages unless the table says "IA metadata".

**Priority six (John of the Cross and Teresa).**

| Work | Scan | Title page | Verdict |
|---|---|---|---|
| *Ascent*, *Dark Night*, *Living Flame*, *Spiritual Canticle* | `completeworksofs01johnuoft`, `...02johnuoft` | *The Complete Works of Saint John of the Cross*, translated by David Lewis, edited by the Oblate Fathers of St. Charles, preface by Cardinal Wiseman, Longman, Green, Longman, Roberts & Green, 1864, 2 vols | matches (Lewis 1864, including the Canticle) |
| *Book of the Foundations* | `bookfoundations00teregoog` | translated by David Lewis, Burns, Oates, 1871 | matches (Lewis) |
| *Letters* | `letterst01tere`, `letterst02tere`, `lettersofsaintte03tere`, `lettersofsaintte0004card` | Stanbrook, intro. Gasquet, Thomas Baker: vol. I MCMXIX, II MCMXXI, III MCMXXII, IV MCMXXIV | matches; all four volumes are 1930 or earlier (5.2's open question) |
| *Way of Perfection* | `thewayofperfecti00tereuoft` | Stanbrook, revised by Zimmerman, second edition, Thomas Baker, 1919 (imprimatur 1911, reimprimatur 1919) | matches the Decision log (Stanbrook pre-1931). The candidates memo proposed Dalton 1852 (`wayperfectionan00teregoog`, Dolman), which is neither Lewis nor Stanbrook, so the row does not use it |

**Clean-text group.** The scan is the edition check, and the OCR fallback where the clean copy's site claims copyright.

| Work | Scan and title page | Clean copy (scan-only memo) |
|---|---|---|
| Bernard, *Sermons on the Canticle* | `stbernardssermon01bern`, `...02bern`: "a Priest of Mount Melleray", Browne and Nolan, Dublin, imprimaturs 1920 | ecatholic2000 (claims copyright) |
| Bernard, *On Consideration* | `bernarddeclirvau00bernuoft`: George Lewis, Clarendon Press, 1908 | ecatholic2000 |
| Bernard, *Grace and Free Will* | `treatiseofstber00bern`: Watkin W. Williams, SPCK / Macmillan, 1920 | ecatholic2000 |
| Bonaventure, *Life of St Francis* | `TheLifeOfSaintFrancis`: Dent, 1904 (IA metadata) | Sensus Fidelium, Salter 1904 |
| Bellarmine, *Art of Dying Well* | `theartofdyingwel00belluoft`: Richardson, undated (IA "1847?") | saintsbooks.net |
| Bellarmine, *Eternal Happiness* | `theeternalhappin00belluoft`: tr. John Dalton, Thomas Richardson and Son, undated | Sensus Fidelium, edition unstated |
| Luis of Granada, *Sinner's Guide* | `sinnersguide00luis`: "A new and revised translation by a Father of the same Order", T. B. Noonan, Boston, approbations 1883 | Wikisource, Noonan |
| Liguori, *Preparation for Death* | `preparationforde00ligu`: eighth edition, Thomas Sweeney, Boston, 1854 | Sensus Fidelium, edition unstated |
| Montfort, *True Devotion* | `TreatiseTrueDevotionBlessedVirgin`: Faber, second edition, Burns and Lambert, 1863 | ecatholic2000, edition to compare |
| *Catena Aurea*, Luke, John | `catenaaureacomme03thom` (vol. III, Luke; IA catalogues the set as 1841; its title page was not read because IA returned a server error), `catenaaureacomme04thom` (vol. IV, St. John, Parker / Rivington, MDCCCXLV) | ecatholic2000 |
| Robinson, *Writings of St Francis* | `writingsofsaintf00fran_0`: Dolphin Press, Philadelphia, MCMVI, copyright 1905 | ecatholic2000 |

**OCR-only works, by value.**

| Work | Scan and title page | Status |
|---|---|---|
| Tanquerey, *The Spiritual Life* | `spirituallife0000atan` and `MN41530ucmf_5`: "Second and revised edition", Society of St. John the Evangelist, Desclée, Tournai, "Printed in Belgium", imprimatur Baltimore 24 May 1930, **no year on the title page**. IA says 1930; one library catalogue gives the second revised edition as 1932 | `unknown` |
| Marmion, *Christ the Life of the Soul* | `christlifeofsoul0000marm`: Sands, 1922 (IA metadata; the title page OCR is unreadable) | pre-1931 |
| Aquinas, *Lord's Prayer* | `LordsPrayerTrByFatherRawes`: Rawes, Burns and Oates, 1879 (IA metadata) | pre-1931 |
| Aquinas, *Two Commandments* | `AquinasOnTheCommandments`: Rawes, London, 1880 (IA metadata) | pre-1931 |
| Scupoli, *Spiritual Combat* | `spiritualcombat01scupgoog`: with *The Peace of the Soul*, Bernard Dornin, Catholic Bookstore, Philadelphia, 1817. See "For Carter" for why not Burns 1846 | pre-1931 |
| Gertrude, *Life and Revelations* | `thelifeandrevela00gertuoft`: Burns & Oates / Benziger, undated, approval letter 1870 | pre-1931 |
| Gertrude, *Exercises* | `exercisessaintg00gertgoog`: from Guéranger's French, 1863 (IA metadata) | pre-1931 |
| Scheeben after Nieremberg | `gloriesofdivineg00sche_1`: "A free rendering of the original treatise of P. Eusebius Nieremberg", Benziger, 1886 | pre-1931 |
| Möhler, *Symbolism* | `symbolismorexpos00mhrich`: Robertson, two London volumes in one, Dunigan, New York, 1844 | pre-1931 |
| Knox, *Belief of Catholics* | `beliefofcatholic0000knox_h2r4`: Harper, imprimatur 28 July 1927 | pre-1931 |
| Chesterton, *The Thing* | `thingwhyiamcatho00ches_0`: Dodd, Mead, MCMXXX, copyright 1930 | pre-1931 |
| Fisher, *English Works* | `englishworksjoh00mayogoog`: ed. Mayor, EETS, Trübner, 1876 | pre-1931 |
| Faber, *All for Jesus*, *Growth in Holiness* | `allforjesusoreas00fabeuoft`, `GrowthInHoliness1855`: John Murphy, Baltimore, undated American printings | pre-1931 |
| Lallemant | `SpiritualDoctrineOfFrLouisLallemant`: Burns & Lambert, 1855 (IA metadata) | pre-1931 |
| William of St Thierry, *Golden Epistle* | `goldenepistleofa0000domj`: "Now first translated into English by Walter Shewring and edited by Dom Justin McCann", Sheed and Ward, London, MCMXXX | pre-1931 (5.2's open date confirmed; translator is Shewring, McCann edited) |
| John of Avila, *Letters* | `lettersofblessed00johnuoft`: Stanbrook, Burns & Oates, 1904 | pre-1931 |
| Elizabeth of the Trinity, *Praise of Glory* | `thepraiseofglory00elizuoft`: Stanbrook from the 6th French edition, Washbourne 1914 (imprimatur 1912) | pre-1931 |
| Vianney, *Spirit of the Curé of Ars* | `TheSpiritOfTheCureOfArs`: Monnin, ed. Bowden, Burns, Lambert, and Oates, 1865 | pre-1931 |
| Vianney, *Thoughts* | `thoughtsofcurofa00vian`: tr. Pauline P. Stump, Flynn & Mahony, copyright 1896 | pre-1931 |
| Liguori, Centenary Edition vols. 2, 4, 5 | `thecompleteascet02liguuoft`, `...04liguuoft`, `PassionDeathOfJesusChristV5`: ed. Grimm, Benziger, 1887 | pre-1931; other volumes still to map |
| *Summa contra Gentiles*, book 1 | `summacontragenti01thomuoft`: English Dominican Fathers, Burns, Oates & Washbourne (IA "1923-1929") | pre-1931; only if Carter chooses it |

**The rest of the scan-only memo's works** (rows added so every planned work has one): *Visits to the Blessed Sacrament* (`visitstomostholy0000ligu`, Kenedy 1855, IA metadata), Catherine of Genoa's *Treatise on Purgatory* (`TreatiseOnPurgatory`, Burns 1858, IA metadata), *Little Flowers* (`littleflowersofs00unse`, Kegan Paul MDCCCXCIX, "based by permission upon the translation" of an earlier edition), Bridget (`RevelationsOfStBridget`, Sadlier 1862), Anthony of Padua's *Moral Concordances* (`moralconcordance00neal`, Hayes 1867, IA metadata), Thomas More's *Dialogue of Comfort* (`utopiawiththedia00moreuoft`, an Everyman printing that reads "Last reprinted 1946"; `unknown`), and Catherine of Siena's complete *Dialogue* (`seraphicvirginca00cathuoft`, Kegan Paul 1896).

### 5.6c, second pass: the works R6's first pass left out (36)

All are open IA scans, route OCR, `pd-us-pre-1931`. Title-page facts are from the OCR of the opening pages unless marked "IA metadata".

**Pohle-Preuss, *Dogmatic Theology*, 12 vols.** "Authorized English version with some abridgment and numerous additional references by Arthur Preuss", B. Herder, St. Louis (and Freiburg, London). Credit per the Decision log: "Joseph Pohle, adapted by Arthur Preuss".

| Vol. | Scan | Printing read |
|---|---|---|
| I God: His Knowability | `V01GodHisKnowability` | IA metadata 1917; title page not legible |
| II The Divine Trinity | `divinetrinitydog00pohluoft` | 1912, imprimatur 13 Nov 1911 |
| III God the Author of Nature | `GodTheAuthorOfNature` | IA metadata 1916; title page not legible |
| IV Christology | `christology00pohluoft` | IA metadata 1913 |
| V Soteriology | `soteriology00pohluoft` | 1914 |
| VI Mariology | `mariologydogmati00pohl` | 1914 |
| VII Grace | `graceactualhabit07pohl` | 1915 |
| VIII Sacraments 1 | `sacramentsdogmat01pohluoft` | 1915 |
| IX Sacraments 2, Eucharist | `sacramentsdogmat02pohluoft` | second, revised edition; year not legible (IA 1915-1917) |
| X Sacraments 3, Penance | `sacramentsdogmat03pohluoft` | second, revised edition, 1918 |
| XI Sacraments 4 | `sacramentsdogmat04pohluoft` | second, revised edition, 1918 |
| XII Eschatology | `eschatology00pohluoft` | 1918, copyright 1917 (IA metadata) |

IA also holds printings up to 1929 open and a 1933 printing lending-only; none of the rows uses a printing after 1930.

**Koch-Preuss, *A Handbook of Moral Theology*, 5 vols.** B. Herder Book Co., St. Louis and London. Vol. I's verso: "Copyright, 1918, by Joseph Gummersbach", first edition 1918, second 1919, third 1925. Rows use vol. I 3rd revised ed. 1925 (`moraltheology01kochuoft`), vol. II 3rd revised ed. 1928, printed in U.S.A. (`moraltheology02kochuoft`), vol. III revised ed. 1926 (`moraltheology03kochuoft`), vol. IV 1921 (`handbookofmoralt0004koch`), vol. V 2nd ed. 1924 (`bwb_C0-BOH-771_5`). Vol. V's 1933 printing on IA is lending-only. Credit: "Antony Koch, adapted by Arthur Preuss".

**Bellarmine, *The Ascent of the Mind to God*** (`ascentofmindtogo0000unse`): "In the first English translation, by T. B. Gent. Published at Doway, 1616", introduction by James Brodrick, Burns Oates and Washbourne, London, "First published 1928", imprimatur 19 April 1928. The 5.2 date question is settled. Brodrick's introduction is editorial matter to strip.

**Marmion, *Christ in His Mysteries*** (`christinhismyste0000righ`): translated from the tenth French edition by a nun of Tyburn Convent, Sands, London and Edinburgh, and B. Herder, St. Louis, 1924, made in Belgium, imprimatur Bruges 29 Dec 1923. The 5.2 question (1923 or 1924) is settled: 1924.

**Alphonsus, Centenary Edition** (ed. Grimm, Benziger, New York). IA's volume labels do not match the series numbering (IA's "vol. 1", `thecompleteascet01grimuoft`, is vol. X), so each volume was mapped from its own title page:

| Series vol. | Title | Scan | Year read |
|---|---|---|---|
| II | Way of Salvation and of Perfection | `thecompleteascet02liguuoft` | 1887 (first pass) |
| III | Great Means of Salvation and of Perfection | `bwb_W9-CTR-079` | IA metadata 1886 |
| IV | Incarnation, Birth and Infancy | `thecompleteascet04liguuoft` | 1887 (first pass) |
| V | Passion and Death | `PassionDeathOfJesusChristV5` | 1887 (first pass) |
| VI | Holy Eucharist | `alphonsusworks06alfouoft` | 1887 |
| IX | Victories of the Martyrs | `victoriesmartyrs09liguuoft` | 1888 |
| X | True Spouse of Jesus Christ, part 1 | `thecompleteascet01grimuoft` | 1888 |
| XI | True Spouse, part 2 | `truespouseofjesu1011stal` | a 1929 printing of vols. X and XI |
| XII | Dignity and Duties of the Priest (Selva) | `alphonsusworks12liguuoft` | 1889 |
| XIII | The Holy Mass | `alphonsusworks13liguuoft` | 1889 |
| XIV | The Divine Office | `alphonsusworks14liguuoft` | 1889 |
| XV | Preaching | `alphonsusworks15liguuoft` | 1890 |
| XVIII to XXII | Letters, vols. 1 to 5 | `alphonsusworks18liguuoft`, `alphonsusworks19liguuoft`, `thecompleteascet20liguuoft`, `thecompleteascet21liguuoft`, `thecompleteascet22liguuoft` | 1891, 1892, 1894, 1896, 1897 |

Not found open on IA: vol. I (*Preparation for Death*; 5.6c already has the 1854 Boston translation), vols. VII and VIII (*Glories of Mary*; 5.6b already has the 1852 Dunigan translation, Gutenberg 72411), vols. XVI and XVII (`alphonsusworks17liguuoft` returns empty metadata), and vols. XXIII and XXIV.

**Summa contra Gentiles, English Dominican Fathers** (Burns, Oates & Washbourne, London; edition choice still open). Book 1 `summacontragenti01thomuoft` (first pass; imprimatur 13 Nov 1923), Book 2 `summacontragenti02thomuoft` (imprimatur 1923), Book 3 part 1 `summacontragenti0000lond` (imprimatur 10 May 1928; `bwb_P9-EFD-520_3` is another copy), Book 3 part 2 `summacontragenti0000unse_l9e4` (1928, IA metadata). **Book 4 (1929) has no open scan**; the only IA copies found are 1934 printings and lending-only.

## Scan-only memo flags, resolved

1. **Spiritual Combat.** The memo said the clean Wikisource text is Rivingtons 1875, an Anglican house, and suggested Burns 1846 as the Catholic edition. **Burns 1846 is not a Catholic edition either.** Its title page (IA `TheSpiritualCombat1846`) reads "translated (with the additional chapters) from the Italian, for the use of members of the English Church", London, James Burns. Rivingtons 1875/1876 is a "new translation" in the same Anglican line. A Catholic edition is open on IA: Philadelphia, Bernard Dornin, "at the Catholic Bookstore", 1817, with *The Peace of the Soul* (`spiritualcombat01scupgoog`). The row uses it; see "For Carter".
2. **Little Flowers.** The clean ecatholic2000 text is the Hudleston revision (Burns Oates 1926), taken from a Heritage Press printing with a 1930s introduction by Livingston, on a site that states a copyright notice. The row uses the 1899 Kegan Paul scan instead, route OCR.
3. **Summa contra Gentiles.** aquinas.cc was not re-checked; the memo found no licence statement there. The open route is the English Dominican scans; books 1 to 3 are mapped in the second-pass section above, and book 4 has no open scan. Rickaby's abridgement stays out unless Carter chooses it.
4. **Catherine of Genoa.** Confirmed: CCEL's clean text (`catherine_g/life.xml`, 482,030 bytes) is *Life and Doctrine of Saint Catherine of Genoa*, "translated from the Italian", New York: Christian Press Association Publishing Co., 1907, a different translation from the 1858 Burns *Treatise on Purgatory* with Manning's preface. Both are pre-1931. The row keeps the memo's 1858 scan; see "For Carter".

## Coverage check

Checked the candidates memo (lists A1 and A2), the scan-only memo, 5.3 to 5.6c and 1.2c, 1.2d, 1.2e and 1.8d against the rows. Every planned work has a row. Works with no row, each on purpose:
- Middle English *Revelations of Saint Birgitta* (EETS 1929), excluded by 5.6c's spec.
- Rickaby's abridged *Of God and His Creatures* on CCEL, excluded by 5.6b's spec unless Carter chooses it.
- The Centenary volumes of the *Glories of Mary* (VII, VIII) and *Preparation for Death* (I), whose works already have rows in other translations; and vols. XVI, XVII, XXIII, XXIV, which have no open scan.
- The GIRM (ICEL), dropped by the Decision log; the International Theological Commission, out by 5.3b's default.
- CCEL's Peers, Stevens, Tobin, Epworth and Heritage files, Dalton's *Way of Perfection* and Gutenberg 5657, superseded by the editions in the rows.
- The memo's "lower value" CCEL items and "further public domain items", which no spec plans.

## Inventory diff

`git diff` of `rights_inventory.json` against master shows many deleted lines, but the 421 existing rows are unchanged apart from the added `"planned_for": null` and keep their order: removing `planned_for` from the built rows of the new file gives exactly the master file's list. The deletions are diff alignment: inserted rows share lines such as `"checked_on": null` with existing ones.

## For Carter

Each item gives a recommendation. Nothing in the plan was changed. **Carter accepted every recommendation on 5 Oct 2026**; items 11 and 15 (Summa contra Gentiles) had none and stay open, item 1 (downloads) is asked separately, item 13 stays his, and item 14 (approving the draft rows) is done row by row. The Schroeder and Creeds rows (items 2 and 2a) are approved.

1. **Approve the downloads** (table below): 245 files, 2.01 GB in all. If page images are wanted only when a work's OCR PR starts, approve the 153 text, XML and HTML files now (153 MB) and the 92 PDFs per work later. The P1 set alone is 9 files, 113 MB, of which 3 CCEL files (13 MB) unblock 1.2c, 1.2d and 1.8d. sha256 values go into the rows and `source_lock.json` once the files are fetched.
2. **Approve the *Creeds* renewal search and the Vatican I row** (`pd-us-non-renewal`). The file to be vendored is the 1931 sixth edition; its Vatican I text is the 1877 translation word for word, and no renewal was found in the complete 1958 and 1959 files. Recommendation: accept the non-renewal basis.
2a. **Approve the Schroeder renewal search and its 11 rows** (`pd-us-non-renewal`). Recommendation: approve. No renewal in the complete 1964 and 1965 files, and Fordham's pages record TAN's statement that the copyright was not renewed.
3. **Fordham's transcriptions** (Lateran I, II, IV for 1.2e, and the Roman Catechism for 5.5) carry Paul Halsall's notice that the "specific electronic form of the document is copyright" and that commercial use is not permitted. Recommendation: treat Fordham like ecatholic2000 (Decision log "OCR and scanned works"): OCR the Schroeder and 1923 Catechism scans and use Fordham only to check the OCR, unless you choose to ask Fordham.
4. **Tanquerey's printing is not settled.** Both open scans read "Second and revised edition", with a May 1930 imprimatur and no year on the title page; catalogues disagree between 1930 and 1932, and the book was printed in Belgium. The row is `unknown`. Recommendation: look at the title-page verso and colophon in the IA viewer (`spirituallife0000atan`, first ten page images) for a printing date before 5.6c starts Tanquerey; ingest only if it says 1930.
5. **Spiritual Combat.** Both editions the memos considered, Burns 1846 and Rivingtons 1875, were translated "for the use of members of the English Church". Recommendation: use the Catholic Dornin edition, Philadelphia 1817, as the row does. It pairs the *Combat* with *The Peace of the Soul* instead of *The Path of Paradise*, and needs OCR.
6. **A New Hope for Lebanon (5.4)** has no English on vatican.va (French and Italian only), the vendored file is an empty English page, and searches found no English text elsewhere. Recommendation: apply the Decision log row "Non-English with no usable English": take the French text, keep it in the reader with a note, out of search. 5.4's spec, which says both files "publish into `papal`", would need that change, and the vendored file should be replaced by the French page.
7. **Amoris Laetitia (5.4)**: the vendored HTML holds no text; the English is a 1.3 MB PDF on vatican.va. Recommendation: vendor the PDF and extract its text in 5.4 (the row's source path is the PDF). This needs a small PDF-text step that no adapter has yet.
8. **Catherine of Genoa.** The clean CCEL text is a different translation (New York, Christian Press Association, 1907) from the 1858 Burns translation the memo named, and it contains the *Life* as well as the *Treatise*. Recommendation: take the CCEL 1907 text, which is clean and pre-1931, and drop the 1858 OCR route. Carter chose the CCEL 1907 text on 5 Oct 2026; the row and the download list now use it.
9. **Little Flowers.** Recommendation: use the 1899 Kegan Paul scan by OCR, as the row does, not the Hudleston text on ecatholic2000 (the site's copyright notice, and a 1930s introduction in its print source).
10. **Rolle on CCEL** says its text "is not identical to the print source": footnote glosses replace some archaic words. Recommendation: accept it with that fact in the document note, since the changes are the editor's own glosses; the alternative is OCR of the 1914 or 1920 Methuen printing.
11. **Summa contra Gentiles** (open since the candidates memo): still your choice between Rickaby's abridgement on CCEL and the complete English Dominican scans. Books 1, 2 and 3 (both parts) have rows; book 4 has no open scan (item 15).
12. **More's *Dialogue of Comfort*** is `unknown` because the only open Everyman scan is a 1946 reprint. Recommendation: hold it until a scan of a printing from 1930 or earlier is found; low priority.
13. **Correspondence** (no change, already yours): CCEL's request for permission to republish its editions (the 5.6a and 5.6b ThML files), ecatholic2000, Sensus Fidelium (names no editions), NINS for the Newman Reader, and the Aquinas Institute if aquinas.cc is used.
14. **Approve the 230 draft rows**, or say which to change. All have `checked_by` null.
15. **Summa contra Gentiles book 4 has no open scan** (the 1929 volume). If you choose the Dominican edition, the work is incomplete until a scan of a printing from 1930 or earlier is found [choose with that gap in view; Rickaby covers all four books in abridged form].
16. **Pohle-Preuss and Koch-Preuss mix printings**: several rows use second or third revised editions (1918 to 1928) because those are the open scans. All are 1930 or earlier [accept; the revised editions are the authors' and Preuss's own revisions].
17. **Alphonsus Centenary vols. XVI, XVII, XXIII, XXIV** have no open scan [leave them out until one is found; low priority, since they are sermons, miscellany and letters].
18. **Bellarmine's *Ascent*** is a 1616 translation reissued in 1928 with Brodrick's introduction [ingest the 1616 text, strip the introduction].

## Download list for Carter

Sizes in bytes, from `Content-Length`, CCEL's ETag (which equals our manifest bytes for the files already vendored), or a GET byte count for vatican.va pages that send no length. "Vendored as" is relative to `datapipeline/sources/`.

| Item | Work | URL | Vendored as | Bytes |
|---|---|---|---|---|
| 1.8d | NPNF2-04 (On the Incarnation) | https://ccel.org/ccel/s/schaff/npnf204.xml | `church-fathers/npnf204.xml` | 5,809,854 |
| 1.2c | NPNF2-14 (councils 1 to 7) | https://ccel.org/ccel/s/schaff/npnf214.xml | `councils/npnf214.xml` | 3,196,008 |
| 1.2d | Creeds of Christendom vol. 2 (Vatican I) | https://ccel.org/ccel/s/schaff/creeds2.xml | `councils/creeds2.xml` | 4,065,931 |
| 1.2e | First Lateran Council (Fordham) | https://sourcebooks.fordham.edu/basis/lateran1.asp | `councils/fordham-lateran1.html` | 79,745 |
| 1.2e | Second Lateran Council (Fordham) | https://sourcebooks.fordham.edu/basis/lateran2.asp | `councils/fordham-lateran2.html` | 83,314 |
| 1.2e | Fourth Lateran Council (Fordham) | https://sourcebooks.fordham.edu/basis/lateran4.asp | `councils/fordham-lateran4.html` | 218,572 |
| 1.2e | Schroeder 1937, OCR text | https://archive.org/download/DisciplinaryCouncils/DisciplinaryCouncils_djvu.txt | `councils/DisciplinaryCouncils/DisciplinaryCouncils_djvu.txt` | 2,032,979 |
| 1.2e | Schroeder 1937, hOCR (word positions, for furniture removal) | https://archive.org/download/DisciplinaryCouncils/DisciplinaryCouncils_hocr.html | `councils/DisciplinaryCouncils/DisciplinaryCouncils_hocr.html` | 45,757,516 |
| 1.2e | Schroeder 1937, page images (PDF, for the 20-passage check) | https://archive.org/download/DisciplinaryCouncils/DisciplinaryCouncils.pdf | `councils/DisciplinaryCouncils/DisciplinaryCouncils.pdf` | 52,002,596 |
| 5.3b | Compendium of the Social Doctrine of the Church | https://www.vatican.va/roman_curia/pontifical_councils/justpeace/documents/rc_pc_justpeace_doc_20060526_compendio-dott-soc_en.html | `roman-curia/compendium-of-the-social-doctrine-of-the-church.html` | 1,160,524 |
| 5.3b | Redemptionis Sacramentum | https://www.vatican.va/roman_curia/congregations/ccdds/documents/rc_con_ccdds_doc_20040423_redemptionis-sacramentum_en.html | `roman-curia/redemptionis-sacramentum.html` | 258,086 |
| 5.3b | Directory on Popular Piety and the Liturgy | https://www.vatican.va/roman_curia/congregations/ccdds/documents/rc_con_ccdds_doc_20020513_vers-direttorio_en.html | `roman-curia/directory-on-popular-piety-and-the-liturgy.html` | 531,807 |
| 5.3b | The Bible and Morality | https://www.vatican.va/roman_curia/congregations/cfaith/pcb_documents/rc_con_cfaith_doc_20080511_bibbia-e-morale_en.html | `roman-curia/the-bible-and-morality.html` | 373,861 |
| 5.3b | The Jewish People and Their Sacred Scriptures in the Christian Bible | https://www.vatican.va/roman_curia/congregations/cfaith/pcb_documents/rc_con_cfaith_doc_20020212_popolo-ebraico_en.html | `roman-curia/the-jewish-people-and-their-sacred-scriptures.html` | 386,428 |
| 5.4 | Amoris Laetitia (English PDF) | https://www.vatican.va/content/dam/francesco/pdf/apost_exhortations/documents/papa-francesco_esortazione-ap_20160319_amoris-laetitia_en.pdf | `apostolic-exhortations/amoris-laetitia.pdf` | 1,330,556 |
| 5.4 | Universi Dominici Gregis (as amended 2013) | https://www.vatican.va/content/john-paul-ii/en/apost_constitutions/documents/hf_jp-ii_apc_22021996_universi-dominici-gregis.html | `church-law/universi-dominici-gregis.html` | 122,061 |
| 5.4 | Universi Dominici Gregis (1996 original) | https://www.vatican.va/content/dam/john-paul-ii/pdf/apost_constitutions/documents/universi-dominici-gregis-19960222_en.pdf | `church-law/universi-dominici-gregis-1996.pdf` | 264,696 |
| 5.4 | De aliquibus mutationibus in normis de electione Romani Pontificis | https://www.vatican.va/content/benedict-xvi/la/motu_proprio/documents/hf_ben-xvi_motu-proprio_20070611_de-electione.html | `church-law/de-aliquibus-mutationibus.html` | 37,052 |
| 5.4 | Normas Nonnullas | https://www.vatican.va/content/benedict-xvi/en/motu_proprio/documents/hf_ben-xvi_motu-proprio_20130222_normas-nonnullas.html | `church-law/normas-nonnullas.html` | 47,878 |
| 5.5 | Compendium of the CCC | https://www.vatican.va/archive/compendium_ccc/documents/archive_2005_compendium-ccc_en.html | `catechism/compendium-ccc.html` | 378,892 |
| 5.5 | Roman Catechism 1923 | https://archive.org/download/catechismofcounc0000jose/catechismofcounc0000jose_djvu.txt | `catechism/catechismofcounc0000jose/catechismofcounc0000jose_djvu.txt` | 1,321,558 |
| 5.5 | Roman Catechism 1923 | https://archive.org/download/catechismofcounc0000jose/catechismofcounc0000jose.pdf | `catechism/catechismofcounc0000jose/catechismofcounc0000jose.pdf` | 31,743,469 |
| 5.6a | NPNF208 | https://ccel.org/ccel/s/schaff/npnf208.xml | `church-fathers/npnf208.xml` | 3,303,323 |
| 5.6a | NPNF207 | https://ccel.org/ccel/s/schaff/npnf207.xml | `church-fathers/npnf207.xml` | 4,247,548 |
| 5.6a | NPNF212 | https://ccel.org/ccel/s/schaff/npnf212.xml | `church-fathers/npnf212.xml` | 3,461,929 |
| 5.6a | NPNF213 | https://ccel.org/ccel/s/schaff/npnf213.xml | `church-fathers/npnf213.xml` | 2,246,124 |
| 5.6a | NPNF210 | https://ccel.org/ccel/s/schaff/npnf210.xml | `church-fathers/npnf210.xml` | 3,837,030 |
| 5.6a | NPNF109 | https://ccel.org/ccel/s/schaff/npnf109.xml | `church-fathers/npnf109.xml` | 3,017,592 |
| 5.6a | NPNF110 | https://ccel.org/ccel/s/schaff/npnf110.xml | `church-fathers/npnf110.xml` | 3,956,654 |
| 5.6a | NPNF111 | https://ccel.org/ccel/s/schaff/npnf111.xml | `church-fathers/npnf111.xml` | 5,349,065 |
| 5.6a | NPNF112 | https://ccel.org/ccel/s/schaff/npnf112.xml | `church-fathers/npnf112.xml` | 3,253,154 |
| 5.6a | NPNF113 | https://ccel.org/ccel/s/schaff/npnf113.xml | `church-fathers/npnf113.xml` | 4,441,248 |
| 5.6a | NPNF114 | https://ccel.org/ccel/s/schaff/npnf114.xml | `church-fathers/npnf114.xml` | 4,728,349 |
| 5.6a | Parker's Dionysius | https://ccel.org/ccel/d/dionysius/works.xml | `church-fathers/dionysius-works.xml` | 731,266 |
| 5.6b | The Interior Castle | https://ccel.org/ccel/t/teresa/castle2.xml | `theologians/teresa-castle2.xml` | 582,155 |
| 5.6b | The Life of St. Teresa of Jesus | https://ccel.org/ccel/t/teresa/life.xml | `theologians/teresa-life.xml` | 1,639,686 |
| 5.6b | Introduction to the Devout Life | https://ccel.org/ccel/d/desales/devout_life.xml | `theologians/desales-devout_life.xml` | 651,626 |
| 5.6b | Treatise on the Love of God | https://ccel.org/ccel/d/desales/love.xml | `theologians/desales-love.xml` | 1,890,439 |
| 5.6b | Revelations of Divine Love | https://ccel.org/ccel/j/julian/revelations.xml | `theologians/julian-revelations.xml` | 395,019 |
| 5.6b | The Story of a Soul | https://ccel.org/ccel/t/therese/autobio.xml | `theologians/therese-autobio.xml` | 681,615 |
| 5.6b | The Spiritual Exercises of St. Ignatius of Loyola | https://ccel.org/ccel/i/ignatius/exercises.xml | `theologians/ignatius-exercises.xml` | 266,222 |
| 5.6b | The Autobiography of St. Ignatius | https://ccel.org/ccel/i/ignatius/autobiography.xml | `theologians/ignatius-autobiography.xml` | 173,374 |
| 5.6b | The Cloud of Unknowing | https://ccel.org/ccel/a/anonymous2/cloud.xml | `theologians/anonymous2-cloud.xml` | 332,558 |
| 5.6b | The Scale (or Ladder) of Perfection | https://ccel.org/ccel/h/hilton/ladder.xml | `theologians/hilton-ladder.xml` | 743,898 |
| 5.6b | Treatise Written to a Devout Man | https://ccel.org/ccel/h/hilton/treatise.xml | `theologians/hilton-treatise.xml` | 83,173 |
| 5.6b | The Cell of Self-Knowledge | https://ccel.org/ccel/g/gardner/cell.xml | `theologians/gardner-cell.xml` | 236,948 |
| 5.6b | The Fire of Love and The Mending of Life | https://ccel.org/ccel/r/rolle/fire.xml | `theologians/rolle-fire.xml` | 523,180 |
| 5.6b | The Adornment of the Spiritual Marriage, The Sparkling Stone, The Book of Supreme Truth | https://ccel.org/ccel/r/ruysbroeck/adornment.xml | `theologians/ruysbroeck-adornment.xml` | 503,384 |
| 5.6b | The Inner Way | https://ccel.org/ccel/t/tauler/inner_way.xml | `theologians/tauler-inner_way.xml` | 558,831 |
| 5.6b | A Little Book of Eternal Wisdom | https://ccel.org/ccel/s/suso/wisdom.xml | `theologians/suso-wisdom.xml` | 274,062 |
| 5.6b | The Life of Blessed Henry Suso by Himself | https://ccel.org/ccel/s/suso/susolife.xml | `theologians/suso-susolife.xml` | 475,872 |
| 5.6b | Some Letters of Saint Bernard | https://ccel.org/ccel/b/bernard/letters.xml | `theologians/bernard-letters.xml` | 711,583 |
| 5.6b | The Devotions of Saint Anselm | https://ccel.org/ccel/a/anselm/devotions.xml | `theologians/anselm-devotions.xml` | 345,840 |
| 5.6b | The Everlasting Man | https://ccel.org/ccel/c/chesterton/everlasting.xml | `theologians/chesterton-everlasting.xml` | 603,115 |
| 5.6b | The Dream of Gerontius | https://ccel.org/ccel/n/newman/gerontius.xml | `theologians/newman-gerontius.xml` | 57,878 |
| 5.6b | Pensées | https://ccel.org/ccel/p/pascal/pensees.xml | `theologians/pascal-pensees.xml` | 732,500 |
| 5.6b | Catena Aurea: Gospel of Matthew | https://ccel.org/ccel/a/aquinas/catena1.xml | `theologians/aquinas-catena1.xml` | 3,021,275 |
| 5.6b | Catena Aurea: Gospel of Mark | https://ccel.org/ccel/a/aquinas/catena2.xml | `theologians/aquinas-catena2.xml` | 971,399 |
| 5.6b | The Glories of Mary | https://www.gutenberg.org/cache/epub/72411/pg72411.txt | `theologians/pg72411.txt` | 1,232,145 |
| 5.6b | Abandonment, or Absolute Surrender to Divine Providence | https://www.gutenberg.org/cache/epub/52057/pg52057.txt | `theologians/pg52057.txt` | 222,404 |
| 5.6b | The Practice of the Presence of God | https://www.gutenberg.org/cache/epub/13871/pg13871.txt | `theologians/pg13871.txt` | 80,593 |
| 5.6b | Apologia pro Vita Sua | https://www.gutenberg.org/cache/epub/22088/pg22088.txt | `theologians/pg22088.txt` | 818,677 |
| 5.6b | An Essay on the Development of Christian Doctrine | https://www.gutenberg.org/cache/epub/35110/pg35110.txt | `theologians/pg35110.txt` | 845,927 |
| 5.6b | The Idea of a University | https://www.gutenberg.org/cache/epub/24526/pg24526.txt | `theologians/pg24526.txt` | 961,540 |
| 5.6b | An Essay in Aid of a Grammar of Assent | https://www.gutenberg.org/cache/epub/34022/pg34022.txt | `theologians/pg34022.txt` | 815,513 |
| 5.6b | Letters of Catherine Benincasa | https://www.gutenberg.org/cache/epub/7403/pg7403.txt | `theologians/pg7403.txt` | 636,790 |
| 5.6c | Life and Doctrine of Saint Catherine of Genoa (CCEL 1907, chosen by Carter on 5 Oct 2026) | https://ccel.org/ccel/c/catherine_g/life.xml | `theologians/catherine_g-life.xml` | 482,030 |
| 5.6b | Matelda and the Cloister of Hellfde (selections) | https://www.gutenberg.org/cache/epub/35811/pg35811.txt | `theologians/pg35811.txt` | 214,851 |
| 5.6b | St. Francis of Assisi | https://www.gutenberg.org/cache/epub/63084/pg63084.txt | `theologians/pg63084.txt` | 270,046 |
| 5.6b | The Catholic Church and Conversion | https://www.gutenberg.org/cache/epub/76305/pg76305.txt | `theologians/pg76305.txt` | 163,703 |
| 5.6b | Maxims and Counsels of St. Francis de Sales | https://www.gutenberg.org/cache/epub/73661/pg73661.txt | `theologians/pg73661.txt` | 132,874 |
| 5.6c | John of the Cross vol. 1 | https://archive.org/download/completeworksofs01johnuoft/completeworksofs01johnuoft_djvu.txt | `theologians/completeworksofs01johnuoft/completeworksofs01johnuoft_djvu.txt` | 968,665 |
| 5.6c | John of the Cross vol. 1 | https://archive.org/download/completeworksofs01johnuoft/completeworksofs01johnuoft.pdf | `theologians/completeworksofs01johnuoft/completeworksofs01johnuoft.pdf` | 29,029,593 |
| 5.6c | John of the Cross vol. 2 | https://archive.org/download/completeworksofs02johnuoft/completeworksofs02johnuoft_djvu.txt | `theologians/completeworksofs02johnuoft/completeworksofs02johnuoft_djvu.txt` | 875,181 |
| 5.6c | John of the Cross vol. 2 | https://archive.org/download/completeworksofs02johnuoft/completeworksofs02johnuoft.pdf | `theologians/completeworksofs02johnuoft/completeworksofs02johnuoft.pdf` | 31,416,033 |
| 5.6c | The Book of the Foundations | https://archive.org/download/bookfoundations00teregoog/bookfoundations00teregoog_djvu.txt | `theologians/bookfoundations00teregoog/bookfoundations00teregoog_djvu.txt` | 944,651 |
| 5.6c | The Book of the Foundations | https://archive.org/download/bookfoundations00teregoog/bookfoundations00teregoog.pdf | `theologians/bookfoundations00teregoog/bookfoundations00teregoog.pdf` | 11,754,065 |
| 5.6c | Letters of St Teresa | https://archive.org/download/letterst01tere/letterst01tere_djvu.txt | `theologians/letterst01tere/letterst01tere_djvu.txt` | 595,906 |
| 5.6c | Letters of St Teresa | https://archive.org/download/letterst01tere/letterst01tere.pdf | `theologians/letterst01tere/letterst01tere.pdf` | 16,851,329 |
| 5.6c | Letters of St Teresa | https://archive.org/download/letterst02tere/letterst02tere_djvu.txt | `theologians/letterst02tere/letterst02tere_djvu.txt` | 590,718 |
| 5.6c | Letters of St Teresa | https://archive.org/download/letterst02tere/letterst02tere.pdf | `theologians/letterst02tere/letterst02tere.pdf` | 23,070,225 |
| 5.6c | Letters of St Teresa | https://archive.org/download/lettersofsaintte03tere/lettersofsaintte03tere_djvu.txt | `theologians/lettersofsaintte03tere/lettersofsaintte03tere_djvu.txt` | 587,547 |
| 5.6c | Letters of St Teresa | https://archive.org/download/lettersofsaintte03tere/lettersofsaintte03tere.pdf | `theologians/lettersofsaintte03tere/lettersofsaintte03tere.pdf` | 15,062,603 |
| 5.6c | Letters of St Teresa | https://archive.org/download/lettersofsaintte0004card/lettersofsaintte0004card_djvu.txt | `theologians/lettersofsaintte0004card/lettersofsaintte0004card_djvu.txt` | 632,487 |
| 5.6c | Letters of St Teresa | https://archive.org/download/lettersofsaintte0004card/lettersofsaintte0004card.pdf | `theologians/lettersofsaintte0004card/lettersofsaintte0004card.pdf` | 18,112,944 |
| 5.6c | The Way of Perfection | https://archive.org/download/thewayofperfecti00tereuoft/thewayofperfecti00tereuoft_djvu.txt | `theologians/thewayofperfecti00tereuoft/thewayofperfecti00tereuoft_djvu.txt` | 580,254 |
| 5.6c | The Way of Perfection | https://archive.org/download/thewayofperfecti00tereuoft/thewayofperfecti00tereuoft.pdf | `theologians/thewayofperfecti00tereuoft/thewayofperfecti00tereuoft.pdf` | 22,616,611 |
| 5.6c | Sermons on the Canticle of Canticles | https://archive.org/download/stbernardssermon01bern/stbernardssermon01bern_djvu.txt | `theologians/stbernardssermon01bern/stbernardssermon01bern_djvu.txt` | 1,052,181 |
| 5.6c | Sermons on the Canticle of Canticles | https://archive.org/download/stbernardssermon01bern/stbernardssermon01bern.pdf | `theologians/stbernardssermon01bern/stbernardssermon01bern.pdf` | 32,582,942 |
| 5.6c | Bernard, Canticle vol. 2 | https://archive.org/download/stbernardssermon02bern/stbernardssermon02bern_djvu.txt | `theologians/stbernardssermon02bern/stbernardssermon02bern_djvu.txt` | 1,128,837 |
| 5.6c | Bernard, Canticle vol. 2 | https://archive.org/download/stbernardssermon02bern/stbernardssermon02bern.pdf | `theologians/stbernardssermon02bern/stbernardssermon02bern.pdf` | 35,052,277 |
| 5.6c | On Consideration | https://archive.org/download/bernarddeclirvau00bernuoft/bernarddeclirvau00bernuoft_djvu.txt | `theologians/bernarddeclirvau00bernuoft/bernarddeclirvau00bernuoft_djvu.txt` | 353,791 |
| 5.6c | On Consideration | https://archive.org/download/bernarddeclirvau00bernuoft/bernarddeclirvau00bernuoft.pdf | `theologians/bernarddeclirvau00bernuoft/bernarddeclirvau00bernuoft.pdf` | 10,182,432 |
| 5.6c | Concerning Grace and Free Will | https://archive.org/download/treatiseofstber00bern/treatiseofstber00bern_djvu.txt | `theologians/treatiseofstber00bern/treatiseofstber00bern_djvu.txt` | 308,953 |
| 5.6c | Concerning Grace and Free Will | https://archive.org/download/treatiseofstber00bern/treatiseofstber00bern.pdf | `theologians/treatiseofstber00bern/treatiseofstber00bern.pdf` | 8,334,520 |
| 5.6c | The Life of Saint Francis | https://archive.org/download/TheLifeOfSaintFrancis/TheLifeOfSaintFrancis_djvu.txt | `theologians/TheLifeOfSaintFrancis/TheLifeOfSaintFrancis_djvu.txt` | 353,433 |
| 5.6c | The Life of Saint Francis | https://archive.org/download/TheLifeOfSaintFrancis/TheLifeOfSaintFrancis.pdf | `theologians/TheLifeOfSaintFrancis/TheLifeOfSaintFrancis.pdf` | 4,186,304 |
| 5.6c | The Art of Dying Well | https://archive.org/download/theartofdyingwel00belluoft/theartofdyingwel00belluoft_djvu.txt | `theologians/theartofdyingwel00belluoft/theartofdyingwel00belluoft_djvu.txt` | 231,603 |
| 5.6c | The Art of Dying Well | https://archive.org/download/theartofdyingwel00belluoft/theartofdyingwel00belluoft.pdf | `theologians/theartofdyingwel00belluoft/theartofdyingwel00belluoft.pdf` | 5,799,848 |
| 5.6c | The Eternal Happiness of the Saints | https://archive.org/download/theeternalhappin00belluoft/theeternalhappin00belluoft_djvu.txt | `theologians/theeternalhappin00belluoft/theeternalhappin00belluoft_djvu.txt` | 435,517 |
| 5.6c | The Eternal Happiness of the Saints | https://archive.org/download/theeternalhappin00belluoft/theeternalhappin00belluoft.pdf | `theologians/theeternalhappin00belluoft/theeternalhappin00belluoft.pdf` | 13,849,263 |
| 5.6c | The Sinner's Guide | https://archive.org/download/sinnersguide00luis/sinnersguide00luis_djvu.txt | `theologians/sinnersguide00luis/sinnersguide00luis_djvu.txt` | 864,054 |
| 5.6c | The Sinner's Guide | https://archive.org/download/sinnersguide00luis/sinnersguide00luis.pdf | `theologians/sinnersguide00luis/sinnersguide00luis.pdf` | 33,101,482 |
| 5.6c | Preparation for Death | https://archive.org/download/preparationforde00ligu/preparationforde00ligu_djvu.txt | `theologians/preparationforde00ligu/preparationforde00ligu_djvu.txt` | 802,049 |
| 5.6c | Preparation for Death | https://archive.org/download/preparationforde00ligu/preparationforde00ligu.pdf | `theologians/preparationforde00ligu/preparationforde00ligu.pdf` | 27,698,274 |
| 5.6c | A Treatise on the True Devotion to the Blessed Virgin | https://archive.org/download/TreatiseTrueDevotionBlessedVirgin/TreatiseTrueDevotionBlessedVirgin_djvu.txt | `theologians/TreatiseTrueDevotionBlessedVirgin/TreatiseTrueDevotionBlessedVirgin_djvu.txt` | 326,281 |
| 5.6c | A Treatise on the True Devotion to the Blessed Virgin | https://archive.org/download/TreatiseTrueDevotionBlessedVirgin/TreatiseTrueDevotionBlessedVirgin.pdf | `theologians/TreatiseTrueDevotionBlessedVirgin/TreatiseTrueDevotionBlessedVirgin.pdf` | 6,010,907 |
| 5.6c | Catena Aurea: Gospel of Luke | https://archive.org/download/catenaaureacomme03thom/catenaaureacomme03thom_djvu.txt | `theologians/catenaaureacomme03thom/catenaaureacomme03thom_djvu.txt` | 2,106,842 |
| 5.6c | Catena Aurea: Gospel of Luke | https://archive.org/download/catenaaureacomme03thom/catenaaureacomme03thom.pdf | `theologians/catenaaureacomme03thom/catenaaureacomme03thom.pdf` | 48,377,583 |
| 5.6c | Catena Aurea: Gospel of John | https://archive.org/download/catenaaureacomme04thom/catenaaureacomme04thom_djvu.txt | `theologians/catenaaureacomme04thom/catenaaureacomme04thom_djvu.txt` | 1,726,356 |
| 5.6c | Catena Aurea: Gospel of John | https://archive.org/download/catenaaureacomme04thom/catenaaureacomme04thom.pdf | `theologians/catenaaureacomme04thom/catenaaureacomme04thom.pdf` | 39,929,863 |
| 5.6c | The Writings of Saint Francis of Assisi | https://archive.org/download/writingsofsaintf00fran_0/writingsofsaintf00fran_0_djvu.txt | `theologians/writingsofsaintf00fran_0/writingsofsaintf00fran_0_djvu.txt` | 376,735 |
| 5.6c | The Writings of Saint Francis of Assisi | https://archive.org/download/writingsofsaintf00fran_0/writingsofsaintf00fran_0.pdf | `theologians/writingsofsaintf00fran_0/writingsofsaintf00fran_0.pdf` | 17,119,742 |
| 5.6c | The Spiritual Life | https://archive.org/download/spirituallife0000atan/spirituallife0000atan_djvu.txt | `theologians/spirituallife0000atan/spirituallife0000atan_djvu.txt` | 2,192,486 |
| 5.6c | The Spiritual Life | https://archive.org/download/spirituallife0000atan/spirituallife0000atan.pdf | `theologians/spirituallife0000atan/spirituallife0000atan.pdf` | 44,784,756 |
| 5.6c | Christ the Life of the Soul | https://archive.org/download/christlifeofsoul0000marm/christlifeofsoul0000marm_djvu.txt | `theologians/christlifeofsoul0000marm/christlifeofsoul0000marm_djvu.txt` | 1,043,556 |
| 5.6c | Christ the Life of the Soul | https://archive.org/download/christlifeofsoul0000marm/christlifeofsoul0000marm.pdf | `theologians/christlifeofsoul0000marm/christlifeofsoul0000marm.pdf` | 24,306,713 |
| 5.6c | The Lord's Prayer | https://archive.org/download/LordsPrayerTrByFatherRawes/LordsPrayerTrByFatherRawes_djvu.txt | `theologians/LordsPrayerTrByFatherRawes/LordsPrayerTrByFatherRawes_djvu.txt` | 187,397 |
| 5.6c | The Lord's Prayer | https://archive.org/download/LordsPrayerTrByFatherRawes/LordsPrayerTrByFatherRawes.pdf | `theologians/LordsPrayerTrByFatherRawes/LordsPrayerTrByFatherRawes.pdf` | 2,347,374 |
| 5.6c | On the Two Commandments of Charity and the Ten Commandments of the Law | https://archive.org/download/AquinasOnTheCommandments/AquinasOnTheCommandments_djvu.txt | `theologians/AquinasOnTheCommandments/AquinasOnTheCommandments_djvu.txt` | 261,753 |
| 5.6c | On the Two Commandments of Charity and the Ten Commandments of the Law | https://archive.org/download/AquinasOnTheCommandments/AquinasOnTheCommandments.pdf | `theologians/AquinasOnTheCommandments/AquinasOnTheCommandments.pdf` | 3,479,975 |
| 5.6c | The Spiritual Combat | https://archive.org/download/spiritualcombat01scupgoog/spiritualcombat01scupgoog_djvu.txt | `theologians/spiritualcombat01scupgoog/spiritualcombat01scupgoog_djvu.txt` | 185,771 |
| 5.6c | The Spiritual Combat | https://archive.org/download/spiritualcombat01scupgoog/spiritualcombat01scupgoog.pdf | `theologians/spiritualcombat01scupgoog/spiritualcombat01scupgoog.pdf` | 3,728,482 |
| 5.6c | The Life and Revelations of Saint Gertrude | https://archive.org/download/thelifeandrevela00gertuoft/thelifeandrevela00gertuoft_djvu.txt | `theologians/thelifeandrevela00gertuoft/thelifeandrevela00gertuoft_djvu.txt` | 1,230,593 |
| 5.6c | The Life and Revelations of Saint Gertrude | https://archive.org/download/thelifeandrevela00gertuoft/thelifeandrevela00gertuoft.pdf | `theologians/thelifeandrevela00gertuoft/thelifeandrevela00gertuoft.pdf` | 32,090,471 |
| 5.6c | The Exercises of Saint Gertrude | https://archive.org/download/exercisessaintg00gertgoog/exercisessaintg00gertgoog_djvu.txt | `theologians/exercisessaintg00gertgoog/exercisessaintg00gertgoog_djvu.txt` | 302,052 |
| 5.6c | The Exercises of Saint Gertrude | https://archive.org/download/exercisessaintg00gertgoog/exercisessaintg00gertgoog.pdf | `theologians/exercisessaintg00gertgoog/exercisessaintg00gertgoog.pdf` | 4,700,702 |
| 5.6c | The Glories of Divine Grace | https://archive.org/download/gloriesofdivineg00sche_1/gloriesofdivineg00sche_1_djvu.txt | `theologians/gloriesofdivineg00sche_1/gloriesofdivineg00sche_1_djvu.txt` | 1,021,071 |
| 5.6c | The Glories of Divine Grace | https://archive.org/download/gloriesofdivineg00sche_1/gloriesofdivineg00sche_1.pdf | `theologians/gloriesofdivineg00sche_1/gloriesofdivineg00sche_1.pdf` | 24,630,203 |
| 5.6c | Symbolism | https://archive.org/download/symbolismorexpos00mhrich/symbolismorexpos00mhrich_djvu.txt | `theologians/symbolismorexpos00mhrich/symbolismorexpos00mhrich_djvu.txt` | 1,933,471 |
| 5.6c | Symbolism | https://archive.org/download/symbolismorexpos00mhrich/symbolismorexpos00mhrich.pdf | `theologians/symbolismorexpos00mhrich/symbolismorexpos00mhrich.pdf` | 57,380,581 |
| 5.6c | The Belief of Catholics | https://archive.org/download/beliefofcatholic0000knox_h2r4/beliefofcatholic0000knox_h2r4_djvu.txt | `theologians/beliefofcatholic0000knox_h2r4/beliefofcatholic0000knox_h2r4_djvu.txt` | 418,881 |
| 5.6c | The Belief of Catholics | https://archive.org/download/beliefofcatholic0000knox_h2r4/beliefofcatholic0000knox_h2r4.pdf | `theologians/beliefofcatholic0000knox_h2r4/beliefofcatholic0000knox_h2r4.pdf` | 13,092,827 |
| 5.6c | The Thing: Why I Am a Catholic | https://archive.org/download/thingwhyiamcatho00ches_0/thingwhyiamcatho00ches_0_djvu.txt | `theologians/thingwhyiamcatho00ches_0/thingwhyiamcatho00ches_0_djvu.txt` | 441,683 |
| 5.6c | The Thing: Why I Am a Catholic | https://archive.org/download/thingwhyiamcatho00ches_0/thingwhyiamcatho00ches_0.pdf | `theologians/thingwhyiamcatho00ches_0/thingwhyiamcatho00ches_0.pdf` | 45,899,267 |
| 5.6c | The English Works of John Fisher | https://archive.org/download/englishworksjoh00mayogoog/englishworksjoh00mayogoog_djvu.txt | `theologians/englishworksjoh00mayogoog/englishworksjoh00mayogoog_djvu.txt` | 1,281,299 |
| 5.6c | The English Works of John Fisher | https://archive.org/download/englishworksjoh00mayogoog/englishworksjoh00mayogoog.pdf | `theologians/englishworksjoh00mayogoog/englishworksjoh00mayogoog.pdf` | 15,884,712 |
| 5.6c | All for Jesus | https://archive.org/download/allforjesusoreas00fabeuoft/allforjesusoreas00fabeuoft_djvu.txt | `theologians/allforjesusoreas00fabeuoft/allforjesusoreas00fabeuoft_djvu.txt` | 894,755 |
| 5.6c | All for Jesus | https://archive.org/download/allforjesusoreas00fabeuoft/allforjesusoreas00fabeuoft.pdf | `theologians/allforjesusoreas00fabeuoft/allforjesusoreas00fabeuoft.pdf` | 19,941,313 |
| 5.6c | Growth in Holiness | https://archive.org/download/GrowthInHoliness1855/GrowthInHoliness1855_djvu.txt | `theologians/GrowthInHoliness1855/GrowthInHoliness1855_djvu.txt` | 868,795 |
| 5.6c | Growth in Holiness | https://archive.org/download/GrowthInHoliness1855/GrowthInHoliness1855.pdf | `theologians/GrowthInHoliness1855/GrowthInHoliness1855.pdf` | 14,323,900 |
| 5.6c | The Spiritual Doctrine of Father Louis Lallemant | https://archive.org/download/SpiritualDoctrineOfFrLouisLallemant/SpiritualDoctrineOfFrLouisLallemant_djvu.txt | `theologians/SpiritualDoctrineOfFrLouisLallemant/SpiritualDoctrineOfFrLouisLallemant_djvu.txt` | 642,290 |
| 5.6c | The Spiritual Doctrine of Father Louis Lallemant | https://archive.org/download/SpiritualDoctrineOfFrLouisLallemant/SpiritualDoctrineOfFrLouisLallemant.pdf | `theologians/SpiritualDoctrineOfFrLouisLallemant/SpiritualDoctrineOfFrLouisLallemant.pdf` | 6,680,764 |
| 5.6c | The Golden Epistle | https://archive.org/download/goldenepistleofa0000domj/goldenepistleofa0000domj_djvu.txt | `theologians/goldenepistleofa0000domj/goldenepistleofa0000domj_djvu.txt` | 283,216 |
| 5.6c | The Golden Epistle | https://archive.org/download/goldenepistleofa0000domj/goldenepistleofa0000domj.pdf | `theologians/goldenepistleofa0000domj/goldenepistleofa0000domj.pdf` | 6,968,301 |
| 5.6c | Letters of Blessed John of Avila | https://archive.org/download/lettersofblessed00johnuoft/lettersofblessed00johnuoft_djvu.txt | `theologians/lettersofblessed00johnuoft/lettersofblessed00johnuoft_djvu.txt` | 275,946 |
| 5.6c | Letters of Blessed John of Avila | https://archive.org/download/lettersofblessed00johnuoft/lettersofblessed00johnuoft.pdf | `theologians/lettersofblessed00johnuoft/lettersofblessed00johnuoft.pdf` | 7,820,180 |
| 5.6c | The Praise of Glory (her own writings only) | https://archive.org/download/thepraiseofglory00elizuoft/thepraiseofglory00elizuoft_djvu.txt | `theologians/thepraiseofglory00elizuoft/thepraiseofglory00elizuoft_djvu.txt` | 622,703 |
| 5.6c | The Praise of Glory (her own writings only) | https://archive.org/download/thepraiseofglory00elizuoft/thepraiseofglory00elizuoft.pdf | `theologians/thepraiseofglory00elizuoft/thepraiseofglory00elizuoft.pdf` | 22,618,629 |
| 5.6c | The Spirit of the Curé of Ars | https://archive.org/download/TheSpiritOfTheCureOfArs/TheSpiritOfTheCureOfArs_djvu.txt | `theologians/TheSpiritOfTheCureOfArs/TheSpiritOfTheCureOfArs_djvu.txt` | 426,213 |
| 5.6c | The Spirit of the Curé of Ars | https://archive.org/download/TheSpiritOfTheCureOfArs/TheSpiritOfTheCureOfArs.pdf | `theologians/TheSpiritOfTheCureOfArs/TheSpiritOfTheCureOfArs.pdf` | 5,349,012 |
| 5.6c | Thoughts of the Curé of Ars | https://archive.org/download/thoughtsofcurofa00vian/thoughtsofcurofa00vian_djvu.txt | `theologians/thoughtsofcurofa00vian/thoughtsofcurofa00vian_djvu.txt` | 47,322 |
| 5.6c | Thoughts of the Curé of Ars | https://archive.org/download/thoughtsofcurofa00vian/thoughtsofcurofa00vian.pdf | `theologians/thoughtsofcurofa00vian/thoughtsofcurofa00vian.pdf` | 1,558,347 |
| 5.6c | The Little Flowers of Saint Francis | https://archive.org/download/littleflowersofs00unse/littleflowersofs00unse_djvu.txt | `theologians/littleflowersofs00unse/littleflowersofs00unse_djvu.txt` | 410,241 |
| 5.6c | The Little Flowers of Saint Francis | https://archive.org/download/littleflowersofs00unse/littleflowersofs00unse.pdf | `theologians/littleflowersofs00unse/littleflowersofs00unse.pdf` | 15,798,034 |
| 5.6c | Revelations of St. Bridget on the Life and Passion of Our Lord | https://archive.org/download/RevelationsOfStBridget/RevelationsOfStBridget_djvu.txt | `theologians/RevelationsOfStBridget/RevelationsOfStBridget_djvu.txt` | 196,019 |
| 5.6c | Revelations of St. Bridget on the Life and Passion of Our Lord | https://archive.org/download/RevelationsOfStBridget/RevelationsOfStBridget.pdf | `theologians/RevelationsOfStBridget/RevelationsOfStBridget.pdf` | 3,303,489 |
| 5.6c | A Dialogue of Comfort against Tribulation | https://archive.org/download/utopiawiththedia00moreuoft/utopiawiththedia00moreuoft_djvu.txt | `theologians/utopiawiththedia00moreuoft/utopiawiththedia00moreuoft_djvu.txt` | 1,212,958 |
| 5.6c | A Dialogue of Comfort against Tribulation | https://archive.org/download/utopiawiththedia00moreuoft/utopiawiththedia00moreuoft.pdf | `theologians/utopiawiththedia00moreuoft/utopiawiththedia00moreuoft.pdf` | 25,807,044 |
| 5.6c | The Moral Concordances of Saint Anthony of Padua | https://archive.org/download/moralconcordance00neal/moralconcordance00neal_djvu.txt | `theologians/moralconcordance00neal/moralconcordance00neal_djvu.txt` | 282,685 |
| 5.6c | The Moral Concordances of Saint Anthony of Padua | https://archive.org/download/moralconcordance00neal/moralconcordance00neal.pdf | `theologians/moralconcordance00neal/moralconcordance00neal.pdf` | 6,199,638 |
| 5.6c | Visits to the Most Holy Sacrament and the Blessed Virgin Mary | https://archive.org/download/visitstomostholy0000ligu/visitstomostholy0000ligu_djvu.txt | `theologians/visitstomostholy0000ligu/visitstomostholy0000ligu_djvu.txt` | 272,020 |
| 5.6c | Visits to the Most Holy Sacrament and the Blessed Virgin Mary | https://archive.org/download/visitstomostholy0000ligu/visitstomostholy0000ligu.pdf | `theologians/visitstomostholy0000ligu/visitstomostholy0000ligu.pdf` | 6,204,303 |
| 5.6c | The Dialogue of the Seraphic Virgin Catherine of Siena | https://archive.org/download/seraphicvirginca00cathuoft/seraphicvirginca00cathuoft_djvu.txt | `theologians/seraphicvirginca00cathuoft/seraphicvirginca00cathuoft_djvu.txt` | 899,349 |
| 5.6c | The Dialogue of the Seraphic Virgin Catherine of Siena | https://archive.org/download/seraphicvirginca00cathuoft/seraphicvirginca00cathuoft.pdf | `theologians/seraphicvirginca00cathuoft/seraphicvirginca00cathuoft.pdf` | 21,684,604 |
| 5.6c | Complete Ascetical Works, vol. 2, The Way of Salvation and of Perfection | https://archive.org/download/thecompleteascet02liguuoft/thecompleteascet02liguuoft_djvu.txt | `theologians/thecompleteascet02liguuoft/thecompleteascet02liguuoft_djvu.txt` | 1,105,397 |
| 5.6c | Complete Ascetical Works, vol. 2, The Way of Salvation and of Perfection | https://archive.org/download/thecompleteascet02liguuoft/thecompleteascet02liguuoft.pdf | `theologians/thecompleteascet02liguuoft/thecompleteascet02liguuoft.pdf` | 33,962,950 |
| 5.6c | Complete Ascetical Works, vol. 4, The Incarnation, Birth and Infancy of Jesus Christ | https://archive.org/download/thecompleteascet04liguuoft/thecompleteascet04liguuoft_djvu.txt | `theologians/thecompleteascet04liguuoft/thecompleteascet04liguuoft_djvu.txt` | 1,000,087 |
| 5.6c | Complete Ascetical Works, vol. 4, The Incarnation, Birth and Infancy of Jesus Christ | https://archive.org/download/thecompleteascet04liguuoft/thecompleteascet04liguuoft.pdf | `theologians/thecompleteascet04liguuoft/thecompleteascet04liguuoft.pdf` | 27,187,713 |
| 5.6c | Complete Ascetical Works, vol. 5, The Passion and the Death of Jesus Christ | https://archive.org/download/PassionDeathOfJesusChristV5/PassionDeathOfJesusChristV5_djvu.txt | `theologians/PassionDeathOfJesusChristV5/PassionDeathOfJesusChristV5_djvu.txt` | 1,057,335 |
| 5.6c | Complete Ascetical Works, vol. 5, The Passion and the Death of Jesus Christ | https://archive.org/download/PassionDeathOfJesusChristV5/PassionDeathOfJesusChristV5.pdf | `theologians/PassionDeathOfJesusChristV5/PassionDeathOfJesusChristV5.pdf` | 12,870,442 |
| 5.6c | Summa contra Gentiles, Book 1 | https://archive.org/download/summacontragenti01thomuoft/summacontragenti01thomuoft_djvu.txt | `theologians/summacontragenti01thomuoft/summacontragenti01thomuoft_djvu.txt` | 511,000 |
| 5.6c | Summa contra Gentiles, Book 1 | https://archive.org/download/summacontragenti01thomuoft/summacontragenti01thomuoft.pdf | `theologians/summacontragenti01thomuoft/summacontragenti01thomuoft.pdf` | 15,502,796 |
| 5.6c | Dogmatic Theology I: God: His Knowability, Essence, and Attributes | https://archive.org/download/V01GodHisKnowability/V01GodHisKnowability_djvu.txt | `theologians/V01GodHisKnowability/V01GodHisKnowability_djvu.txt` | 798,177 |
| 5.6c | Dogmatic Theology I: God: His Knowability, Essence, and Attributes | https://archive.org/download/V01GodHisKnowability/V01GodHisKnowability.pdf | `theologians/V01GodHisKnowability/V01GodHisKnowability.pdf` | 7,777,299 |
| 5.6c | Dogmatic Theology II: The Divine Trinity | https://archive.org/download/divinetrinitydog00pohluoft/divinetrinitydog00pohluoft_djvu.txt | `theologians/divinetrinitydog00pohluoft/divinetrinitydog00pohluoft_djvu.txt` | 533,230 |
| 5.6c | Dogmatic Theology II: The Divine Trinity | https://archive.org/download/divinetrinitydog00pohluoft/divinetrinitydog00pohluoft.pdf | `theologians/divinetrinitydog00pohluoft/divinetrinitydog00pohluoft.pdf` | 20,061,016 |
| 5.6c | Dogmatic Theology III: God the Author of Nature and the Supernatural | https://archive.org/download/GodTheAuthorOfNature/GodTheAuthorOfNature_djvu.txt | `theologians/GodTheAuthorOfNature/GodTheAuthorOfNature_djvu.txt` | 648,547 |
| 5.6c | Dogmatic Theology III: God the Author of Nature and the Supernatural | https://archive.org/download/GodTheAuthorOfNature/GodTheAuthorOfNature.pdf | `theologians/GodTheAuthorOfNature/GodTheAuthorOfNature.pdf` | 7,027,492 |
| 5.6c | Dogmatic Theology IV: Christology | https://archive.org/download/christology00pohluoft/christology00pohluoft_djvu.txt | `theologians/christology00pohluoft/christology00pohluoft_djvu.txt` | 662,518 |
| 5.6c | Dogmatic Theology IV: Christology | https://archive.org/download/christology00pohluoft/christology00pohluoft.pdf | `theologians/christology00pohluoft/christology00pohluoft.pdf` | 19,512,267 |
| 5.6c | Dogmatic Theology V: Soteriology | https://archive.org/download/soteriology00pohluoft/soteriology00pohluoft_djvu.txt | `theologians/soteriology00pohluoft/soteriology00pohluoft_djvu.txt` | 328,482 |
| 5.6c | Dogmatic Theology V: Soteriology | https://archive.org/download/soteriology00pohluoft/soteriology00pohluoft.pdf | `theologians/soteriology00pohluoft/soteriology00pohluoft.pdf` | 11,509,825 |
| 5.6c | Dogmatic Theology VI: Mariology | https://archive.org/download/mariologydogmati00pohl/mariologydogmati00pohl_djvu.txt | `theologians/mariologydogmati00pohl/mariologydogmati00pohl_djvu.txt` | 375,156 |
| 5.6c | Dogmatic Theology VI: Mariology | https://archive.org/download/mariologydogmati00pohl/mariologydogmati00pohl.pdf | `theologians/mariologydogmati00pohl/mariologydogmati00pohl.pdf` | 10,570,436 |
| 5.6c | Dogmatic Theology VII: Grace, Actual and Habitual | https://archive.org/download/graceactualhabit07pohl/graceactualhabit07pohl_djvu.txt | `theologians/graceactualhabit07pohl/graceactualhabit07pohl_djvu.txt` | 966,852 |
| 5.6c | Dogmatic Theology VII: Grace, Actual and Habitual | https://archive.org/download/graceactualhabit07pohl/graceactualhabit07pohl.pdf | `theologians/graceactualhabit07pohl/graceactualhabit07pohl.pdf` | 24,753,750 |
| 5.6c | Dogmatic Theology VIII: The Sacraments, vol. 1: The Sacraments in General, Baptism, Confirmation | https://archive.org/download/sacramentsdogmat01pohluoft/sacramentsdogmat01pohluoft_djvu.txt | `theologians/sacramentsdogmat01pohluoft/sacramentsdogmat01pohluoft_djvu.txt` | 689,669 |
| 5.6c | Dogmatic Theology VIII: The Sacraments, vol. 1: The Sacraments in General, Baptism, Confirmation | https://archive.org/download/sacramentsdogmat01pohluoft/sacramentsdogmat01pohluoft.pdf | `theologians/sacramentsdogmat01pohluoft/sacramentsdogmat01pohluoft.pdf` | 17,648,413 |
| 5.6c | Dogmatic Theology IX: The Sacraments, vol. 2: The Holy Eucharist | https://archive.org/download/sacramentsdogmat02pohluoft/sacramentsdogmat02pohluoft_djvu.txt | `theologians/sacramentsdogmat02pohluoft/sacramentsdogmat02pohluoft_djvu.txt` | 717,328 |
| 5.6c | Dogmatic Theology IX: The Sacraments, vol. 2: The Holy Eucharist | https://archive.org/download/sacramentsdogmat02pohluoft/sacramentsdogmat02pohluoft.pdf | `theologians/sacramentsdogmat02pohluoft/sacramentsdogmat02pohluoft.pdf` | 17,913,972 |
| 5.6c | Dogmatic Theology X: The Sacraments, vol. 3: Penance | https://archive.org/download/sacramentsdogmat03pohluoft/sacramentsdogmat03pohluoft_djvu.txt | `theologians/sacramentsdogmat03pohluoft/sacramentsdogmat03pohluoft_djvu.txt` | 537,306 |
| 5.6c | Dogmatic Theology X: The Sacraments, vol. 3: Penance | https://archive.org/download/sacramentsdogmat03pohluoft/sacramentsdogmat03pohluoft.pdf | `theologians/sacramentsdogmat03pohluoft/sacramentsdogmat03pohluoft.pdf` | 13,773,244 |
| 5.6c | Dogmatic Theology XI: The Sacraments, vol. 4: Extreme Unction, Holy Orders, Matrimony | https://archive.org/download/sacramentsdogmat04pohluoft/sacramentsdogmat04pohluoft_djvu.txt | `theologians/sacramentsdogmat04pohluoft/sacramentsdogmat04pohluoft_djvu.txt` | 495,619 |
| 5.6c | Dogmatic Theology XI: The Sacraments, vol. 4: Extreme Unction, Holy Orders, Matrimony | https://archive.org/download/sacramentsdogmat04pohluoft/sacramentsdogmat04pohluoft.pdf | `theologians/sacramentsdogmat04pohluoft/sacramentsdogmat04pohluoft.pdf` | 13,107,231 |
| 5.6c | Dogmatic Theology XII: Eschatology | https://archive.org/download/eschatology00pohluoft/eschatology00pohluoft_djvu.txt | `theologians/eschatology00pohluoft/eschatology00pohluoft_djvu.txt` | 332,956 |
| 5.6c | Dogmatic Theology XII: Eschatology | https://archive.org/download/eschatology00pohluoft/eschatology00pohluoft.pdf | `theologians/eschatology00pohluoft/eschatology00pohluoft.pdf` | 11,684,003 |
| 5.6c | A Handbook of Moral Theology I: Introduction; Morality, Its Subject, Norm, and Object | https://archive.org/download/moraltheology01kochuoft/moraltheology01kochuoft_djvu.txt | `theologians/moraltheology01kochuoft/moraltheology01kochuoft_djvu.txt` | 619,141 |
| 5.6c | A Handbook of Moral Theology I: Introduction; Morality, Its Subject, Norm, and Object | https://archive.org/download/moraltheology01kochuoft/moraltheology01kochuoft.pdf | `theologians/moraltheology01kochuoft/moraltheology01kochuoft.pdf` | 18,107,218 |
| 5.6c | A Handbook of Moral Theology II: Sin and the Means of Grace | https://archive.org/download/moraltheology02kochuoft/moraltheology02kochuoft_djvu.txt | `theologians/moraltheology02kochuoft/moraltheology02kochuoft_djvu.txt` | 498,713 |
| 5.6c | A Handbook of Moral Theology II: Sin and the Means of Grace | https://archive.org/download/moraltheology02kochuoft/moraltheology02kochuoft.pdf | `theologians/moraltheology02kochuoft/moraltheology02kochuoft.pdf` | 16,366,248 |
| 5.6c | A Handbook of Moral Theology III: Man's Duties to Himself | https://archive.org/download/moraltheology03kochuoft/moraltheology03kochuoft_djvu.txt | `theologians/moraltheology03kochuoft/moraltheology03kochuoft_djvu.txt` | 376,027 |
| 5.6c | A Handbook of Moral Theology III: Man's Duties to Himself | https://archive.org/download/moraltheology03kochuoft/moraltheology03kochuoft.pdf | `theologians/moraltheology03kochuoft/moraltheology03kochuoft.pdf` | 9,828,173 |
| 5.6c | A Handbook of Moral Theology IV: Man's Duties to God | https://archive.org/download/handbookofmoralt0004koch/handbookofmoralt0004koch_djvu.txt | `theologians/handbookofmoralt0004koch/handbookofmoralt0004koch_djvu.txt` | 755,711 |
| 5.6c | A Handbook of Moral Theology IV: Man's Duties to God | https://archive.org/download/handbookofmoralt0004koch/handbookofmoralt0004koch.pdf | `theologians/handbookofmoralt0004koch/handbookofmoralt0004koch.pdf` | 17,044,777 |
| 5.6c | A Handbook of Moral Theology V: Man's Duties to His Fellowmen | https://archive.org/download/bwb_C0-BOH-771_5/bwb_C0-BOH-771_5_djvu.txt | `theologians/bwb_C0-BOH-771_5/bwb_C0-BOH-771_5_djvu.txt` | 1,170,400 |
| 5.6c | A Handbook of Moral Theology V: Man's Duties to His Fellowmen | https://archive.org/download/bwb_C0-BOH-771_5/bwb_C0-BOH-771_5.pdf | `theologians/bwb_C0-BOH-771_5/bwb_C0-BOH-771_5.pdf` | 26,966,513 |
| 5.6c | The Ascent of the Mind to God | https://archive.org/download/ascentofmindtogo0000unse/ascentofmindtogo0000unse_djvu.txt | `theologians/ascentofmindtogo0000unse/ascentofmindtogo0000unse_djvu.txt` | 422,074 |
| 5.6c | The Ascent of the Mind to God | https://archive.org/download/ascentofmindtogo0000unse/ascentofmindtogo0000unse.pdf | `theologians/ascentofmindtogo0000unse/ascentofmindtogo0000unse.pdf` | 10,999,858 |
| 5.6c | Christ in His Mysteries | https://archive.org/download/christinhismyste0000righ/christinhismyste0000righ_djvu.txt | `theologians/christinhismyste0000righ/christinhismyste0000righ_djvu.txt` | 985,466 |
| 5.6c | Christ in His Mysteries | https://archive.org/download/christinhismyste0000righ/christinhismyste0000righ.pdf | `theologians/christinhismyste0000righ/christinhismyste0000righ.pdf` | 22,683,723 |
| 5.6c | Complete Ascetical Works, vol. 3, The Great Means of Salvation and of Perfection | https://archive.org/download/bwb_W9-CTR-079/bwb_W9-CTR-079_djvu.txt | `theologians/bwb_W9-CTR-079/bwb_W9-CTR-079_djvu.txt` | 980,405 |
| 5.6c | Complete Ascetical Works, vol. 3, The Great Means of Salvation and of Perfection | https://archive.org/download/bwb_W9-CTR-079/bwb_W9-CTR-079.pdf | `theologians/bwb_W9-CTR-079/bwb_W9-CTR-079.pdf` | 20,196,158 |
| 5.6c | Complete Ascetical Works, vol. 6, The Holy Eucharist | https://archive.org/download/alphonsusworks06alfouoft/alphonsusworks06alfouoft_djvu.txt | `theologians/alphonsusworks06alfouoft/alphonsusworks06alfouoft_djvu.txt` | 1,079,801 |
| 5.6c | Complete Ascetical Works, vol. 6, The Holy Eucharist | https://archive.org/download/alphonsusworks06alfouoft/alphonsusworks06alfouoft.pdf | `theologians/alphonsusworks06alfouoft/alphonsusworks06alfouoft.pdf` | 28,080,944 |
| 5.6c | Complete Ascetical Works, vol. 9, Victories of the Martyrs | https://archive.org/download/victoriesmartyrs09liguuoft/victoriesmartyrs09liguuoft_djvu.txt | `theologians/victoriesmartyrs09liguuoft/victoriesmartyrs09liguuoft_djvu.txt` | 1,011,108 |
| 5.6c | Complete Ascetical Works, vol. 9, Victories of the Martyrs | https://archive.org/download/victoriesmartyrs09liguuoft/victoriesmartyrs09liguuoft.pdf | `theologians/victoriesmartyrs09liguuoft/victoriesmartyrs09liguuoft.pdf` | 28,088,091 |
| 5.6c | Complete Ascetical Works, vol. 10, The True Spouse of Jesus Christ, part 1 | https://archive.org/download/thecompleteascet01grimuoft/thecompleteascet01grimuoft_djvu.txt | `theologians/thecompleteascet01grimuoft/thecompleteascet01grimuoft_djvu.txt` | 1,152,181 |
| 5.6c | Complete Ascetical Works, vol. 10, The True Spouse of Jesus Christ, part 1 | https://archive.org/download/thecompleteascet01grimuoft/thecompleteascet01grimuoft.pdf | `theologians/thecompleteascet01grimuoft/thecompleteascet01grimuoft.pdf` | 33,030,909 |
| 5.6c | Complete Ascetical Works, vol. 11, The True Spouse of Jesus Christ, part 2 (scan of a 1929 printing of vols. 10-11) | https://archive.org/download/truespouseofjesu1011stal/truespouseofjesu1011stal_djvu.txt | `theologians/truespouseofjesu1011stal/truespouseofjesu1011stal_djvu.txt` | 1,442,223 |
| 5.6c | Complete Ascetical Works, vol. 11, The True Spouse of Jesus Christ, part 2 (scan of a 1929 printing of vols. 10-11) | https://archive.org/download/truespouseofjesu1011stal/truespouseofjesu1011stal.pdf | `theologians/truespouseofjesu1011stal/truespouseofjesu1011stal.pdf` | 31,389,890 |
| 5.6c | Complete Ascetical Works, vol. 12, Dignity and Duties of the Priest (Selva) | https://archive.org/download/alphonsusworks12liguuoft/alphonsusworks12liguuoft_djvu.txt | `theologians/alphonsusworks12liguuoft/alphonsusworks12liguuoft_djvu.txt` | 1,056,249 |
| 5.6c | Complete Ascetical Works, vol. 12, Dignity and Duties of the Priest (Selva) | https://archive.org/download/alphonsusworks12liguuoft/alphonsusworks12liguuoft.pdf | `theologians/alphonsusworks12liguuoft/alphonsusworks12liguuoft.pdf` | 26,527,521 |
| 5.6c | Complete Ascetical Works, vol. 13, The Holy Mass | https://archive.org/download/alphonsusworks13liguuoft/alphonsusworks13liguuoft_djvu.txt | `theologians/alphonsusworks13liguuoft/alphonsusworks13liguuoft_djvu.txt` | 961,159 |
| 5.6c | Complete Ascetical Works, vol. 13, The Holy Mass | https://archive.org/download/alphonsusworks13liguuoft/alphonsusworks13liguuoft.pdf | `theologians/alphonsusworks13liguuoft/alphonsusworks13liguuoft.pdf` | 26,172,229 |
| 5.6c | Complete Ascetical Works, vol. 14, The Divine Office | https://archive.org/download/alphonsusworks14liguuoft/alphonsusworks14liguuoft_djvu.txt | `theologians/alphonsusworks14liguuoft/alphonsusworks14liguuoft_djvu.txt` | 1,394,675 |
| 5.6c | Complete Ascetical Works, vol. 14, The Divine Office | https://archive.org/download/alphonsusworks14liguuoft/alphonsusworks14liguuoft.pdf | `theologians/alphonsusworks14liguuoft/alphonsusworks14liguuoft.pdf` | 32,019,649 |
| 5.6c | Complete Ascetical Works, vol. 15, Preaching | https://archive.org/download/alphonsusworks15liguuoft/alphonsusworks15liguuoft_djvu.txt | `theologians/alphonsusworks15liguuoft/alphonsusworks15liguuoft_djvu.txt` | 1,232,083 |
| 5.6c | Complete Ascetical Works, vol. 15, Preaching | https://archive.org/download/alphonsusworks15liguuoft/alphonsusworks15liguuoft.pdf | `theologians/alphonsusworks15liguuoft/alphonsusworks15liguuoft.pdf` | 30,080,698 |
| 5.6c | Complete Ascetical Works, vol. 18, Letters, vol. 1 | https://archive.org/download/alphonsusworks18liguuoft/alphonsusworks18liguuoft_djvu.txt | `theologians/alphonsusworks18liguuoft/alphonsusworks18liguuoft_djvu.txt` | 1,271,843 |
| 5.6c | Complete Ascetical Works, vol. 18, Letters, vol. 1 | https://archive.org/download/alphonsusworks18liguuoft/alphonsusworks18liguuoft.pdf | `theologians/alphonsusworks18liguuoft/alphonsusworks18liguuoft.pdf` | 34,036,273 |
| 5.6c | Complete Ascetical Works, vol. 19, Letters, vol. 2 | https://archive.org/download/alphonsusworks19liguuoft/alphonsusworks19liguuoft_djvu.txt | `theologians/alphonsusworks19liguuoft/alphonsusworks19liguuoft_djvu.txt` | 1,042,383 |
| 5.6c | Complete Ascetical Works, vol. 19, Letters, vol. 2 | https://archive.org/download/alphonsusworks19liguuoft/alphonsusworks19liguuoft.pdf | `theologians/alphonsusworks19liguuoft/alphonsusworks19liguuoft.pdf` | 27,297,692 |
| 5.6c | Complete Ascetical Works, vol. 20, Letters, vol. 3 | https://archive.org/download/thecompleteascet20liguuoft/thecompleteascet20liguuoft_djvu.txt | `theologians/thecompleteascet20liguuoft/thecompleteascet20liguuoft_djvu.txt` | 1,007,756 |
| 5.6c | Complete Ascetical Works, vol. 20, Letters, vol. 3 | https://archive.org/download/thecompleteascet20liguuoft/thecompleteascet20liguuoft.pdf | `theologians/thecompleteascet20liguuoft/thecompleteascet20liguuoft.pdf` | 31,921,373 |
| 5.6c | Complete Ascetical Works, vol. 21, Letters, vol. 4 | https://archive.org/download/thecompleteascet21liguuoft/thecompleteascet21liguuoft_djvu.txt | `theologians/thecompleteascet21liguuoft/thecompleteascet21liguuoft_djvu.txt` | 958,854 |
| 5.6c | Complete Ascetical Works, vol. 21, Letters, vol. 4 | https://archive.org/download/thecompleteascet21liguuoft/thecompleteascet21liguuoft.pdf | `theologians/thecompleteascet21liguuoft/thecompleteascet21liguuoft.pdf` | 29,819,930 |
| 5.6c | Complete Ascetical Works, vol. 22, Letters, vol. 5 | https://archive.org/download/thecompleteascet22liguuoft/thecompleteascet22liguuoft_djvu.txt | `theologians/thecompleteascet22liguuoft/thecompleteascet22liguuoft_djvu.txt` | 1,005,266 |
| 5.6c | Complete Ascetical Works, vol. 22, Letters, vol. 5 | https://archive.org/download/thecompleteascet22liguuoft/thecompleteascet22liguuoft.pdf | `theologians/thecompleteascet22liguuoft/thecompleteascet22liguuoft.pdf` | 27,356,871 |
| 5.6c | Summa contra Gentiles, Book 2 | https://archive.org/download/summacontragenti02thomuoft/summacontragenti02thomuoft_djvu.txt | `theologians/summacontragenti02thomuoft/summacontragenti02thomuoft_djvu.txt` | 746,103 |
| 5.6c | Summa contra Gentiles, Book 2 | https://archive.org/download/summacontragenti02thomuoft/summacontragenti02thomuoft.pdf | `theologians/summacontragenti02thomuoft/summacontragenti02thomuoft.pdf` | 20,573,709 |
| 5.6c | Summa contra Gentiles, Book 3, part 1 | https://archive.org/download/summacontragenti0000lond/summacontragenti0000lond_djvu.txt | `theologians/summacontragenti0000lond/summacontragenti0000lond_djvu.txt` | 451,725 |
| 5.6c | Summa contra Gentiles, Book 3, part 1 | https://archive.org/download/summacontragenti0000lond/summacontragenti0000lond.pdf | `theologians/summacontragenti0000lond/summacontragenti0000lond.pdf` | 11,094,143 |
| 5.6c | Summa contra Gentiles, Book 3, part 2 | https://archive.org/download/summacontragenti0000unse_l9e4/summacontragenti0000unse_l9e4_djvu.txt | `theologians/summacontragenti0000unse_l9e4/summacontragenti0000unse_l9e4_djvu.txt` | 538,213 |
| 5.6c | Summa contra Gentiles, Book 3, part 2 | https://archive.org/download/summacontragenti0000unse_l9e4/summacontragenti0000unse_l9e4.pdf | `theologians/summacontragenti0000unse_l9e4/summacontragenti0000unse_l9e4.pdf` | 11,826,069 |
