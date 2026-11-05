# R9. Leads for the council gaps

Research for corpus-cleanup item R9 (`docs/corpus-cleanup/P0-checks-identity-research.md`, GitHub issue #316). Done 4 November 2026. It checks the leads for the gap register in `docs/research/council-translation-inventory.md` (1.2a).

No production store was queried and nothing was vendored. To compare texts, these were read into a scratch folder on the home server and deleted with it: the OCR text of three open Internet Archive items (Hefele vol. 5, Mendham, Chrystal vol. 1) and a third-party PDF of a reprint of Deferrari's book, described under "Scans". Pages of the two restricted Internet Archive copies were read only through the Archive's public preview and search-inside.

## Result

- **Deferrari's *The Sources of Catholic Dogma* (1957): notice, registration, no renewal found.** Row `pd-us-non-renewal`, approved by Carter on 4 Nov 2026. Decree text only (Carter, 4 Nov 2026; see "Decision").
- **It fills part of G6, G8 and G9, not all of them.** Complete: Wyclif's 45 articles and Hus's 30. Excerpted: Constance's definition on communion, the proposition on tyrannicide, the core of Florence's three union bulls, and 136 words of Pastor aeternus gregem. It has nothing from Basel or Ferrara, and neither Haec sancta nor Frequens.
- **It adds six canons to Constantinople IV**, against Schroeder's summaries. It does not improve on Schroeder for Lateran V's shared bulls.
- **G2, Nicaea II's four anathemas: Hefele prints all four** (English vol. 5, 1896, p. 376). Mendham is not needed, though he prints them too (1850, p. 442).
- **G1, Nestorius's second letter: Chrystal prints it whole** (1895), at pp. 155–166, not pp. 155–161 as the register said. It needs heavy cleanup of his summaries and notes.
- **G3, G4, G5, G7, G10 and G11: no lead.** Deferrari prints none of them.
- **It also reaches four papal documents held for permission.** Above all Exsurge Domine: the site's 41 condemned propositions are Deferrari's own translation. See section 5.

## 1. Deferrari: the edition and the renewal search

### Title and copyright pages

Read in the Internet Archive's public preview of `sourcesofcatholi00denz` (leaves 7 and 8) and `sourcesofcatholi0000royj`, which agree.

| Item | Printed |
|---|---|
| Title page | "Denzinger. The Sources of Catholic Dogma. Translated by Roy J. Deferrari from the Thirtieth Edition of Henry Denzinger's *Enchiridion Symbolorum*. B. Herder Book Co., 15 & 17 South Broadway, St. Louis 2, Mo. and 33 Queen Square, London, W.C." |
| Source edition | "This translation was made from the thirtieth edition of *Enchiridion Symbolorum*, by Henry Denzinger, revised by Karl Rahner, S.J., published in 1954 by Herder & Co., Freiburg." |
| Approvals | Nihil obstat, Dominic Hughes, O.P.; imprimatur, Patrick A. O'Boyle, Archbishop of Washington, April 25, 1955 |
| Notice | "Copyright 1957 by B. Herder Book Co." |
| Printer | "Printed in the United States of America by the Vail-Ballou Press, Inc., Binghamton, New York" |
| Other | Library of Congress Catalog Card Number 57-5963 |

The translator's preface (pp. v–vi) presents the book as an English version made for this edition. It thanks Joseph C. Fenton, Dominic Hughes (above all for the Systematic Index) and five sisters who helped early on. It mentions no earlier translation.

### Registration

*Catalog of Copyright Entries*, third series, vol. 11, part 1, no. 1 (1957), p. 165, as transcribed by NYPL (`catalog_of_copyright_entries_project`, `xml/1957/1957_v11_n1.xml`, commit 82da829):

> DENZINGER, HENRY. The sources of Catholic dogma. Translated by Roy J. Deferrari, from the thirtieth edition of Henry Denzinger's Enchiridion symbolorum. © B. Herder Book Co.; 8Jan57; A265753.

The plain `A` prefix is a regular book registration, not ad interim (`AI`) or foreign (`AF`). The same transcriptions for 1954 to 1958 show no registration of the Latin *Enchiridion*.

### Renewal search

Recorded in the row. NYPL's renewals transcription (`cce-renewals`, `data/` at commit ebb6156), as in R6 and R8.

- **Window.** A 1957 copyright had to be renewed by the end of 1985. The 1984 and 1985 files are complete, with renewals dated in every month. The 1985 file holds 20,302 renewals of 1957 originals.
- **Searched in every file:** A265753; "sources of catholic dogma", "catholic dogma", "sources of cath", "symbolorum", "enchiridion", "dogma"; "denzinger" and variants; "deferrari" and variants, including "de ferrari"; "rahner"; "herder", "b. herder", "herder book"; "loreto".
- **Result: no renewal found.** "deferrari" matches 7 entries, all other titles, among them renewals by Austin Deferrari of Fathers of the Church volumes. "enchiridion" matches 4, all Epictetus or Erasmus. "rahner" matches 3, all unrelated. "herder" matches no B. Herder Book Co. claim.
- **Controls, all found:** Atlas Shrugged (renewed 7 January 1985), On the Road (renewed 16 April 1985), The Cat in the Hat (31 January 1985), and a 1957 Catholic title, *On the Truth of the Catholic Faith* (A272705, 4 January 1985). The data holds 48 originals dated 8 January 1957 and 83 neighbouring registrations from A2655xx to A2660xx.
- **Copyright Office public records** (`publicrecords.copyright.gov`): keyword searches for the title, Denzinger, *Enchiridion symbolorum*, B. Herder Book Co. and Loreto Publications found no renewal of this book. The same search finds the Catholic control as RE0000242700. A 2013 registration of *Enchiridion symbolorum* (TX0007756405) is a different, modern work.
- **Not searched:** the Stanford Copyright Renewal Database, which refuses automated access, as in R6.

### Scans

| Copy | Status |
|---|---|
| `sourcesofcatholi00denz`, `sourcesofcatholi0000royj` (Internet Archive) | 1957 printing. Lending only. Public preview of the first ten leaves and the last; public search-inside returns short snippets of the whole text |
| HathiTrust `mdp.39015000700248`, `uc1.$b785147` | Search-only (rights code `ic`) |
| Loreto Publications reprint, ISBN 1-930278-22-5 | The same text. No Herder imprint, no copyright notice and no claim of its own. A PDF scanned on a home scanner in 2012, with a text layer, is on isidore.co, which redirects to `lib.undercaffeinated.xyz` |
| `DenzingerSourcesOfCatholicDogma` (Internet Archive) | Gone; the identifier returns nothing |
| `denzinger.patristica.net/denzinger/` | Server error |

**Same text.** 15 sentences taken from the reprint, spread through the book and including four from the gap texts, were each found by search-inside in the 1957 scan. The corrigenda sheet the reprint opens with is also in the 1957 printing, at leaf 763.

**The reprint PDF, measured.** All but one of its 750 pages holds one page image, about 5,000 by 6,500 pixels, black and white, and sharp when read (printed p. 219). On printed pp. 209, 219 and 224, read against the 1.2f word list, its text layer has about 1% to 2% of words misread, such as "fron1" for "from" and "Annenians" for "Armenians"; the list also flags names and Latin, which are correct. A fresh OCR of the same three pages (RapidOCR, 300 dpi) was no better overall: it fixed those but made others ("chiefy", "fourishes") and garbled footnotes. Three pages is a small sample, and a misreading that makes another real word would not show in this count.

**The 1.2f tool does not read images.** It reads the Internet Archive's `_djvu.xml`, so neither this PDF nor a home scan can go through it as it stands. Either needs a small adapter: the PDF's text layer has word positions to feed one, and a home scan would first need an OCR engine, which this server lacks.

**There is no clean, openly available scan of the 1957 printing.** Enough of it can be read to check it, but not to build from.

**Source for 1.2e: the reprint PDF (Carter, 4 Nov 2026).** 1.2e saves a copy, hashes it and records where it came from, then builds from its text layer through a small adapter into the 1.2f cleanup and gate. Buying a 1957 printing was considered: it gives a cleaner record of origin but no better text, and a home scan would need an OCR engine as well as the adapter. Every passage is read against the page image and checked against the 1957 scan through search-inside. If the PDF has gone or its pages prove too poor, buying a copy remains the fallback.

## 2. Deferrari against the gap register

Denzinger numbers (n.) are Deferrari's margin numbers; pages are his printed pages. Words are counted from the reprint's text layer, about ±5%, against Tanner's word count for the same document. Presence was found by scoring each Tanner sentence against the book, then confirmed by reading the pages; the score alone overstates similar documents.

### Constance (G6)

| Tanner document | Deferrari | Status |
|---|---|---|
| Session 8, 45 articles of Wyclif (condemned text) | n. 581–625, pp. 208–211 | **Complete**, all 45. Not the sentence around them |
| Session 13, condemnation of communion under both kinds | n. 626, pp. 211–212 | **Extract**, about 375 of 472 words. The decree that follows it (160 words) is not printed |
| Session 15, 30 articles of Hus (condemned text) | n. 627–656, pp. 212–215 | **Complete**, all 30 (about 1,300 words against Tanner's 1,283) |
| Session 15, sentence on Jean Petit's proposition | n. 690, p. 218 | **Extract**, with an ellipsis. Deferrari's footnote says this condemnation was not approved as a definition |
| Session 15, 58 articles of Wyclif selected from the 260 | — | Not printed |
| Every other document of G6: sessions 1, 3, 4, 5 (Haec sancta), 12, 14, 21, 37, 39 (Frequens), 40, 44, 45, and the other acts of sessions 8 and 15 | — | Not printed |

Two things that look like more than they are. "Questions to be proposed to the Wycliffites and Hussites" (n. 657–689) is Martin V's bull *Inter cunctas* (1418), not a Tanner document of the council. A footnote on p. 215 quotes part of Haec sancta; that is the editor's note.

### Basel–Ferrara–Florence (G8)

| Tanner document | Deferrari | Status |
|---|---|---|
| Florence 6, Laetentur caeli (1,294 words) | n. 691–694, pp. 219–220, "Decree for the Greeks" | **Extract**, about 650 words: the definitions on the procession of the Holy Spirit, the eucharistic bread, purgatory and the primacy. Without the opening and narrative, or the closing sentence on the other patriarchs |
| Florence 8, Exultate Deo, union with the Armenians (5,052 words) | n. 695–702, pp. 220–225, "Decree for the Armenians" | **Extract**, about 2,300 words: the "fifth" section, on the seven sacraments, only. Without the opening, the creed, Chalcedon's definition, Leo's letter, the Athanasian Creed, the feasts and the Armenians' acceptance |
| Florence 11, Cantate Domino, union with the Copts (4,384 words) | n. 703–715, pp. 225–230, "A Decree in Behalf of the Jacobites" | **Extract**, about 2,700 words: the profession from "The sacrosanct Roman Church" to the form of consecration. Without the opening, the list of biblical books (marked by the editor, n. 706), the councils received, fourth marriages and the closing acceptance |
| Florence 13 and 14, bulls of union with the Syrians, Chaldeans and Maronites | — | Not printed. Denzinger's note: they "contain nothing new" (p. 230) |
| Basel, Ferrara, and Florence 7, 9, 10, 12 | — | Not printed; no entry |

### Lateran V (G9)

| Tanner document | Deferrari | Status |
|---|---|---|
| Session 11, Pastor aeternus gregem (3,038 words) | n. 740, p. 238, "The Relation Between the Pope and the Councils" | **Extract**, 136 words |
| Every other document of G9 | — | Not printed |

### Constantinople IV (G3 and the condensed canons)

| Text | Deferrari | Status |
|---|---|---|
| Definition of the eighth synod (G3) | — | Not printed; only a note that Hormisdas's rule of faith was read |
| Canons 1, 3, 11, 12, 21 | n. 336–339, 341, pp. 135–139 | Printed whole or nearly so, against Schroeder's summaries (canon 1: 29 words in Schroeder, 324 in Tanner) |
| Canon 17 | n. 340, p. 138 | **Extract**, "From Can. 17": one passage on the civil ruler's presence at synods |
| The other 21 canons | — | Not printed; Schroeder's summaries stand |

Most of these canons are printed twice, in parallel columns: the Latin of Anastasius (the longer form, labelled "Text of Anastasius") and the Greek. Tanner's numbering is Anastasius's, so that column is the one to take. The columns interleave in the text layer, and a sentence score is unreliable here; 1.2e needs column-aware OCR.

### The rest of the register and Schroeder's partial texts

| Text | Finding |
|---|---|
| G1 Nestorius's letter | Not printed |
| G2 Nicaea II's anathemas | **Partial, not usable**: n. 306–308, p. 123, "Action VIII", three anathemas shortened with ellipses. Hefele has all four |
| G4 Frederick's deposition | Not printed. "He did not send out dogmatic decrees" (p. 179) |
| G5 Vienne's Templar bulls | Not printed; the Templars appear only in the council's heading (p. 188) |
| G7, G10, G11 | Not printed. Vatican I has sessions 3 and 4 only, already covered by Schaff |
| Lateran V, Apostolici regiminis | n. 738: 263 words, against Schroeder's 660. **Schroeder stays** |
| Lateran V, Inter multiplices | n. 739: 183 words, against Schroeder's 730. **Schroeder stays** |
| Lateran I 15 and 16, Lyons II's Zelus fidei, Vienne's Exivi de paradiso, Constance's session 43 | Not printed |

### For 1.2e

- **Corrigenda touch two gap texts.** n. 691 (lines 12 to 16 are replaced) and n. 703 (add "and all these things are one" after "one eternity"), on the sheet at the start of the reprint and at leaf 763 of the 1957 scan. Apply them.
- **Margin numbers fall inside lines** ("6. God ought to obey the devil. 586"). Strip them. The articles' own numbers 1 to 45 and 1 to 30 belong to the council's lists and stay.
- **Editor's bracketed labels** ("[The procession of the Holy Spirit]", "[De novissimis]") and the "(The decrees for Greeks and Armenians ... follow.)" line at n. 714 are editor material.
- **The condemned texts.** Wyclif's 45 articles and Hus's 30 would carry `voice = "rejected"` (3.4), and the Condemned Texts table in the inventory would change. Each list needs a note saying the council's sentence is not printed, so a reader does not take them for the council's own words.

## 3. Nicaea II's four anathemas (G2)

| Tanner | Hefele, English vol. 5, p. 376 | Mendham, p. 442 |
|---|---|---|
| "does not confess that Christ our God can be represented in his humanity" | "does not confess that Christ, in His manhood, has a circumscribed form" | "confess not Christ according to the flesh to be circumscribed" |
| "does not accept representation in art of evangelical scenes" | "does not allow the explanation of the Gospels by figures" | "approve not the representation of the history of the Gospel in pictures" |
| "does not salute such representations as standing for the Lord and his saints" | "does not greet these things which are made in the name of the Lord and the saints" | "salute not such images, as being made in the name of the Lord and His Saints" |
| "rejects any written or unwritten tradition of the church" | "rejects the tradition of the Church, written or unwritten" | "sets at nought ecclesiastical tradition, written or unwritten" |

**Verdict: Hefele prints all four, whole and in order.** *A History of the Councils of the Church*, vol. 5, translated from the German with the author's approbation and edited by William R. Clark (Edinburgh: T. & T. Clark, 1896), scan `ahistoryofthecou05hefeuoft`, open. Public domain by date; row `pd-us-pre-1931`, `planned_for` 1.2c, approved by Carter.

Hefele gives them as a run of the session's acclamations, in quotation marks, inside his narrative. Each ends "let him be anathema", and Tanner's first is preceded by one more clause ("If anyone defends a member of the heresy which slanders the Christians"), which Tanner does not print and 1.2c leaves out. Hefele's "explanation of the Gospels by figures" is the weakest of the four renderings.

**Mendham** (*The Seventh General Council*, London: Painter, 1850, `seventhgeneralc00mendgoog`, p. 442, not pp. 442–443) has the same run and is closer in the second anathema. He stays the fallback, as the Decision log orders, since his book is a polemic.

## 4. Nestorius's second letter (G1)

**Verdict: Chrystal prints it whole.** James Chrystal, *Authoritative Christianity: The Third World Council*, vol. 1 (Jersey City, 1895; entered 1894), scan `authoritative01chry`, open. Public domain by date; row `pd-us-pre-1931`, `planned_for` 1.2c, approved by Carter.

- **Pages 155–166**, not 155–161. It opens "To the most religious and most dear-to-God, our Fellow Minister Cyril, Nestorius wishes joy in the Lord" and closes "May you continue strong, and continue to pray earnestly for us, O brother". Tanner's opening and closing correspond, and the sentences between match in order (59 sentences, 72% of content words shared).
- **Cleanup is heavy.** The span runs to about 5,670 words against Tanner's 1,866: three bracketed "Section" summaries (about 900 words) that are Chrystal's and argue against the letter, 106 note references and his footnotes on every page, with Greek in the OCR. 1.2c would have to read it through.
- **`voice = "rejected"`** applies (3.4), and the summaries must not come with it.

## 5. Other gaps the book could fill

Searched at Carter's request (4 Nov 2026), under the approach in "Decision": extracts placed in their own documents. Every document in ADR 0001's table that is held for permission or published in part (62) was matched against the book by incipit, and all source lines from Benedict XIV to Pius IX were read, since OCR can hide an incipit.

| Held document | Deferrari | Length | Translation |
|---|---|---|---|
| Exsurge Domine (Leo X, 1520) | n. 741–781, pp. 240–243, "Errors of Martin Luther" | All 41 condemned propositions and the pope's censure: about 1,330 of the bull's 3,950 words | **The site's own.** All 41 propositions on the site's page match the book (41 paragraphs at 50% or more of word 4-grams shared, most near 100%); no other paragraph on the page matches |
| Vix Pervenit (Benedict XIV, 1745) | n. 1475–1479, pp. 361–362, "Usury" | The five numbered teachings: about 860 of 1,935 words | Different (2% shared) |
| Singulari Nos (Gregory XVI, 1834) | n. 1617, p. 404, "The False Doctrines of Felicite de Lamennais" | One passage: about 200 of 1,650 words | Different (4%) |
| Quanto Conficiamur Moerore (Pius IX, 1863) | n. 1677, p. 424, "Indifferentism" | One passage: about 400 of 2,800 words | Different (13%) |

- **Exsurge Domine is the useful case.** R8 found no printing of it, and it is held in full. These 41 passages can stay as they are, moved to Deferrari's row, while the rest of the bull stays held under ADR 0001's extract rule. They are condemned text (`voice = "rejected"`, 3.4), and a note should say so. The site's other text is not Deferrari's; its own note credits part to Hans J. Hillerbrand.
- **False match.** The book's "Ex quo" (n. 2147a, p. 551) is Pius X's letter of 26 December 1910, not Benedict XIV's encyclical of 1756.
- **Named but not printed.** The other held documents appear, if at all, only as citations: for example the Syllabus's list of sources (pp. 433–437) names Nostis et Nobiscum, Singulari Quidem and Incredibili.
- **Already cleared elsewhere.** Qui Pluribus, Ineffabilis Deus, Quanta Cura (1864), the Syllabus and Ubi Primum (1824) are printed in the book and have older printings, which stay.
- **The modern encyclicals** still marked `unknown` belong to 1.3c, which uses vatican.va. They were not compared.
- **Rule E passages.** Nothing for Clement's Stromata III or Instructor II.10, Lactantius, or Ubi Lutetiam: the book names none of them.

## Method

As R8, with three additions. Search-inside of a restricted Internet Archive book runs from its public viewer. The viewer's preview images are obfuscated; they were read as shown on screen, not decoded. Coverage used R8's content-word pairs within six words, per Tanner sentence: absent texts scored 0.01 to 0.10 and present ones 0.24 or more, but a bull sharing formulas with a printed one scores high without being printed (the Athanasian Creed in Exultate Deo scored 49–74%), so every "printed" above was read on the page.

Not searched: HathiTrust full text and Google Books, as in R8. Later unrenewed books other than Deferrari were not searched, since the spec's steps name only his. One that a later search could start with is *The Church Teaches* (B. Herder, 1955), not examined here.

## Decision (Carter, 4 Nov 2026)

From Deferrari's book, 1.2e takes the translated decree text only. Denzinger's headings, notes and numbers are not used, and each passage carries a note saying it is an extract.

For now the book is used only this way, as extracts placed in their own documents. Before the expansion starts, item 5.0 decides how Denzinger is handled for good: as its own collection, by placing all its parts where they belong, or both.

Also decided by Carter on 4 Nov 2026, with the source for 1.2e under "Scans":

- **Partial texts come in, with a note.** Every extract listed in section 2 under Constance, Florence and Lateran V, Constantinople IV's six canons, and the extracts of Vix Pervenit, Singulari Nos and Quanto Conficiamur Moerore. Schroeder stays for Apostolici regiminis and Inter multiplices.
- **Condemned lists are shown, clearly labelled.** Wyclif's 45 articles, Hus's 30 and Exsurge Domine's 41 propositions carry `voice = "rejected"` and a note saying they are condemned statements and that the full sentence is not available.
- **Hefele and Chrystal are used** for G2 and G1 in 1.2c, with a note on Hefele's anathemas that they come from his account of the session, and without Chrystal's summaries or notes. Both rows are approved.

## Needs Carter

Nothing further for R9: every question above is answered. Item 5.0 holds the Denzinger decision for later. Approvals of publishes stay with the items that publish (1.2c, 1.2e, 1.3d).
