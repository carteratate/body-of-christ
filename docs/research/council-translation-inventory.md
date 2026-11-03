# Council translation inventory and gap register (1.2a)

Item 1.2a of the corpus cleanup, issue #162. Research only: no code, no database access.
Written 2 Nov 2026 from the files vendored in `datapipeline/sources/` and the searches
listed under "Where the gaps were searched".

The councils collection holds 20 council documents for councils 1 to 20, one per council
(`datapipeline/sources/councils/manifest.json`). The 19 other than Trent come from
papalencyclicals.net, which reproduces Tanner, *Decrees of the Ecumenical Councils*.
This file says, for every document in Tanner's table of contents for those councils,
which planned public-domain English translation covers it:

- councils 1 to 7: Percival, NPNF2 vol. 14 (1900), CCEL `npnf214` (1.2c);
- councils 8 to 18: Schroeder, *Disciplinary Decrees of the General Councils* (1937),
  Internet Archive scan `DisciplinaryCouncils` (1.2e, through the 1.2f OCR tool);
- council 19, Trent: Waterworth (1848), the file already vendored (1.2b);
- council 20, Vatican I: Schaff, *Creeds of Christendom* vol. 2, CCEL `creeds2` (1.2d).

It ends with the gap register Carter approves (NEEDS-CARTER, 1.2a). Texts on it show
"translation in preparation" (D9) once their Tanner text is retired.

## Summary

- **Councils 1 to 7 are covered except two texts.** Percival prints every creed,
  definition, canon, anathema and synodal letter in Tanner's table of contents but two:
  **Nestorius's second letter to Cyril** at Ephesus (Percival records that it was read
  and elides it) and **the four anathemas on holy images** at Nicaea II (Percival has
  the acclamations, not the four "If anyone…" anathemas).
- **Schroeder is mostly complete for the Lateran councils, Lyons I and II and Vienne,
  and thin for the rest.** Measured against Tanner word for word count, canon by canon:
  Lateran II, III and IV are within a few per cent of Tanner on every canon. Constantinople IV's
  27 canons are condensed throughout, to about 40% of Tanner's length ("a summary of them
  will suffice", Schroeder p. 159). Constance has only the seven reform statutes of
  session 43; Basel has only sessions 20 and 21; Lateran V has seven bulls in excerpt.
- **Gaps, by size:** all of Florence's union decrees and every other Basel–Ferrara–Florence
  document outside sessions 20 and 21; Constance outside session 43, including Haec
  sancta, Frequens and the condemnations of Wyclif and Hus; Lateran V outside its seven
  excerpted bulls; Constantinople IV's Definition; Lyons I's bull deposing Frederick II;
  Vienne's eight Templar and Holy Land bulls; Vatican I's sessions 1 and 2.
- **Leads found for three gaps**, not yet checked as editions: Chrystal (1895) prints
  Nestorius's letter in full; Mendham (1850) and the English Hefele, vol. 5 (1896), print
  the Nicaea II anathemas; Foxe's *Acts and Monuments* (Cattley's edition) prints
  Constance's sentences against Wyclif's 45 articles and against Hus. Nothing complete
  was found before 1931 for Florence, Lateran V, Constantinople IV's Definition, the
  Templar bulls, Frederick's deposition or Vatican I's sessions 1 and 2.
- **Condemned texts read at the council (C-01):** six found, listed below. Of them only
  Vienne's eight Beghard errors are in a planned source (Schroeder pp. 389–390).

## Sources read

| Source | File | Read how |
|---|---|---|
| Tanner (papalencyclicals.net), councils 1–20 | `sources/councils/ecum-01…20-*.html` | Headings, bracketed titles and paragraph runs of each page's article text |
| Percival, NPNF2-14 | `sources/_incoming/councils/npnf214.xml` (3,196,008 bytes) | ThML div tree; every div's headings and paragraph runs; paragraph ids where a div mixes council text and notes |
| Schroeder 1937 | `sources/_incoming/councils/DisciplinaryCouncils/` `_djvu.xml` and `_page_numbers.json` | Read page by page with `ocr.pages.load_pages`, so every page number below is the printed page from `_page_numbers.json` |
| Schaff, *Creeds* vol. 2 | `sources/_incoming/councils/creeds2.xml` (4,065,931 bytes) | Section `v.ii.i`, English cells only |
| Fordham, Lateran I, II, IV | `sources/_incoming/councils/fordham-lateran{1,2,4}.html` | Not needed here: they reproduce Schroeder's text for the OCR check (1.2e) |

"Covered" and "partial" for Schroeder rest on a word count of his "Text." sections against
Tanner's text of the same canon or decree, from the OCR, so ±10% is noise. Below about
80% the shortfall was read on the page.

## Status values

- **covered**: the source prints the whole document.
- **partial**: the source prints part of it, or condenses it. The row says what is missing.
- **gap**: no planned source prints it.
- **Tanner summary**: Tanner prints only his own bracketed summary of the session, no
  council text. Nothing to translate; the passage is Tanner's editor material, retired
  under rule G (`rule-g-editorial`), not a gap.

Every row's Tanner text comes from the council's `rights_inventory.json` row for
`councils/ecum-NN-….html` (status `unknown`; the Tanner text retires at P4). The
replacement rows are:

| Source | `rights_inventory.json` row | Status |
|---|---|---|
| Percival | the council's row with `source_path` `councils/npnf214.xml` (7 rows, councils 1–7) | `pd-us-pre-1931` |
| Schroeder | the council's row with `source_path` `councils/DisciplinaryCouncils/` (11 rows, councils 8–18) | `pd-us-non-renewal` |
| Schaff | "First Vatican Council", `source_path` `councils/creeds2.xml` | `pd-us-non-renewal` |
| Waterworth | "Council of Trent", `source_path` `councils/ecum-19-council-of-trent.html` | `pd-us-pre-1931` |

A gap has no replacement row. The leads named for three gaps have no row either; each
would need an edition check and a rights row (R6's method) before any use.

## Inventory

Percival locations are CCEL div ids in `npnf214.xml`. Schroeder locations are printed
pages. Tanner sections are Tanner's headings as the vendored page prints them.

### 1. Nicaea I (325) — Percival

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — (Tanner's editor material) | Tanner summary |
| Profession of faith of the 318 fathers | "The profession of faith of the 318 fathers" | `vii.iii`, paragraphs `-p3` to `-p7` (before "Notes.") | covered |
| Canons 1–20 | "Canons" | `vii.vi.i`, `.iii`, `.iv`, `.v`, `.vi`, `.viii`, `.x`, `.xii`, `.xiv`, `.xv`, `.xvi`, `.xviii`, `.xix`, `.xxi`, `.xxii`, `.xxiv`, `.xxv`, `.xxvii`, `.xxviii`, `.xxx` | covered |
| Letter of the synod to the Egyptians | "The letter of the synod in Nicaea to the Egyptians" | `vii.ix` ("The Synodal Letter") | covered |

### 2. Constantinople I (381) — Percival

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Exposition of the 150 fathers (the creed) | "The exposition of the 150 fathers" | `ix.iii-p6`, `-p7` | covered |
| Letter of the bishops gathered in Constantinople (382, to Damasus and the Western bishops) | "A letter of the bishops gathered in Constantinople" | `ix.ix` ("The Synodical Letter", a.d. 382) | covered |
| Canons 1–7 | "Canons" | `ix.viii.i`, `.iii`, `.iv`, `.v`, `.vi`, `.vii`, `.ix` | covered |

### 3. Ephesus (431) — Percival

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Second letter of Cyril to Nestorius | "Second letter of Cyril to Nestorius" | `x.v` | covered |
| Second letter of Nestorius to Cyril (**condemned text read at the council**) | "Second letter of Nestorius to Cyril" | Not printed: `x.vi` records the reading and elides the letter ("…") | **gap** — lead: Chrystal 1895, pp. 155–161 |
| Third letter of Cyril to Nestorius | "Third letter of Cyril to Nestorius" | `x.viii` | covered |
| Twelve anathemas of Cyril | "Twelve Anathemas Proposed by Cyril…" | `x.ix.i`, `.iii`–`.x`, `.xii`–`.xiv` (the anathema paragraph in each, before "Notes.") | covered |
| Judgment against Nestorius | "The judgment against Nestorius" | `x.xi` ("Decree of the Council Against Nestorius"), `-p3` | covered |
| Synodical letter about the expulsion of the eastern bishops | "Synodical letter about the expulsion…" | `x.xvi.i-p4`, `-p5` (the letter's opening, in a div titled "Introduction") and canons I–VI, `x.xvi.ii`, `.iv`, `.v`, `.vi`, `.viii`, `.ix` | covered |
| Definition of the faith at Nicaea (session 6) | "Definition of the faith at Nicaea" | `x.xvi.x` (canon VII) | covered |
| Definition against the Messalians | "Definition against the impious Messalians…" | `x.xvi.xv` | covered |
| Resolution on ordinations in Cyprus | "Resolution: that the bishops of Cyprus…" | `x.xvi.xii` (canon VIII) | covered |
| Formula of union | "Formula of union between Cyril and John of Antioch" | Inside Cyril's letter to John, `xi.v-p6` to `-p9` (Percival prints the letter with Chalcedon) | covered |
| Letter of Cyril to John of Antioch about peace | "Letter of Cyril to John of Antioch about peace" | `xi.v` | covered |
| Excerpt from the Council of Chalcedon | "Excerpt from the Council of Chalcedon" | Tanner's quotation of Chalcedon's definition; the text is at `xi.xiii` | covered (with Chalcedon) |

### 4. Chalcedon (451) — Percival

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Letter of Pope Leo to Flavian (the Tome) | "The letter of Pope Leo to Flavian…" | `xi.vii`, `-p4` to `-p8` (`-p9` is Percival's bracketed note) | covered |
| Definition of the faith | "Definition of the faith" | `xi.xiii`, `-p3` to `-p13` | covered |
| Canons 1–27 | "Canons" 1–27 | `xi.xviii.i` to `.xxvii` | covered |
| Canon 28 (Tanner: "in fact a resolution passed by the council at the 16th session") | 28 | `xi.xviii.xxviii` | covered |

Tanner's introduction names canons 29 and 30 without printing them. Percival prints both,
as extracts of the acts (`xi.xviii.xxx`, `.xxxi`). They are not Tanner documents; 1.2c
decides whether its allowlist takes them (see "Percival's units").

### 5. Constantinople II (553) — Percival

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Sentence against the Three Chapters | "Sentence against the 'Three Chapters'" | `xii.vi` ("The Sentence of the Synod") | covered |
| Fourteen anathemas | "Anathemas against the 'Three Chapters'" | `xii.vii` ("The Capitula of the Council"), I–XIV | covered |

### 6. Constantinople III (680–681) — Percival

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Exposition of faith | "Exposition of faith" | `xiii.x` ("The Definition of Faith") | covered |

### 7. Nicaea II (787) — Percival

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Definition | "Definition" | `xvi.xii` ("The Decree of the Holy, Great, Ecumenical Synod…") | covered |
| Anathemas concerning holy images (four) | "Anathemas concerning holy images" | Not printed. `xvi.xii-p14` has the session's acclamations ("Anathema to those who…"), not the four anathemas | **gap** — leads: Mendham 1850, pp. 442–443; Hefele, English vol. 5 (1896), p. 376 |
| Canons 1–22 | "Canons" | `xvi.xiv.i` to `.xxii` | covered |

### 8. Constantinople IV (869–870) — Schroeder

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Definition of the holy and universal eighth synod | "[Definition of the holy and universal eighth synod]" | Not in Schroeder (his history, pp. 157–159, describes the sessions) | **gap** |
| Canons 1–27 | "Canons" 1–27 | pp. 159–176 | **partial**: every canon condensed. Schroeder: "Since some of the canons of this council are noted for their verboseness, a summary of them will suffice" (p. 159). His "Text." sections total about 2,900 words against Tanner's 7,300; canon 1 is 29 words against 324 |

### 9. Lateran I (1123) — Schroeder

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Canons 1–22 | "Canons" | pp. 178–194, canons 1–22 | covered except Tanner's canons 15 and 16. The numberings differ after canon 1. For those two, Schroeder's canons 13 (truce of God) and 17 (monks) translate the other recension, the text Tanner prints only as a variant; Tanner's main texts (15: confirmation of the popes' decrees on the peace and truce of God, arson and highways; 16: monks' subjection to their bishops) have no Schroeder equivalent: **partial** for 15 and 16 |

### 10. Lateran II (1139) — Schroeder

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Canons 1–30 | "Canons" | pp. 197–213, canons 1–30 | covered (canon by canon within the OCR noise) |

### 11. Lateran III (1179) — Schroeder

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Canons 1–27 | "Canons" | pp. 214–235, canons 1–27 | covered (canon by canon) |

### 12. Lateran IV (1215) — Schroeder

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Constitutions 1–71 (1 Confession of faith, 2 On the error of abbot Joachim, 3 On heretics, … 71 Crusade) | "Constitutions" | pp. 237–296, canons 1–71 | covered (canon by canon) |

### 13. Lyons I (1245) — Schroeder

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Bull deposing the emperor Frederick II | "Bull Deposing The Emperor Frederick II" | Not printed; Schroeder's history reports the deposition (p. 300) | **gap** |
| Constitutions I 1–22 and II 1–5 | "Constitutions" | pp. 301–316 (first series, 1–18) and pp. 317–323 (second series, 1–9) | covered: 27 units each, about 90% of Tanner's length overall. Schroeder groups them in another order (his 13–16 and 18 are Tanner's II 1–5; his 17 is Tanner's I 18); 1.2e aligns them |

### 14. Lyons II (1274) — Schroeder

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Constitutions II 1–31 (1 On the supreme Trinity, 2 the conclave, …) | "Constitutions", II | pp. 330–360, canons 1–31 | covered (canon by canon) |
| Constitution I, Zelus fidei (the crusade) | "Constitutions", I | pp. 360–364, canon 32 | **partial**: Tanner's part [Id] (586 words: the dismissal of those attending, with the provisions that follow) is not printed |

### 15. Vienne (1311–1312) — Schroeder

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Bulls on the Templars and the Holy Land [1]–[8] (Tanner prints them in smaller type: "considerable doubt that a document is the work of the council") | "[Bulls and ordinances of the Roman curia concerning the order of the Templars…]" | Not printed; Schroeder's history names Vox in excelso (p. 369) | **gap** |
| Decree [1], on the faith (Fidei catholicae) | "Decrees" [1] | p. 372, first series canon 1 | covered |
| Decrees [2]–[37] | "Decrees" | pp. 379–442: first series 2–20, second series 1–18 | covered. Schroeder has 39 units against Tanner's 38 and orders them his own way; 1.2e aligns them |
| Decree on the Beghards and Beguines (Ad nostrum; **condemned text read at the council**: eight errors) | "Decrees" [28] | pp. 389–390, first series canon 6 | covered |
| Exivi de paradiso | "Decrees" [38] | pp. 406–413, first series canon 21 | **partial**: abbreviated ("Owing to its length, abbreviations will be made", p. 407); about 3,600 words against Tanner's 4,900 |

### 16. Constance (1414–1418) — Schroeder

Schroeder translates only the seven general reform statutes of session 43 (pp. 453–455).
His history paraphrases the session 5 decrees (p. 444) and Frequens (pp. 447–448,
"which reads substantially as follows"); a paraphrase is his own text, not a
translation. Tanner's file also carries e-text editor material that is neither Tanner's
nor the council's (the "Second Introduction", a one-line comment opening session 5, and
footnote 1 "not from Tanner").

| Session | Tanner documents | Replacement | Status |
|---|---|---|---|
| — | Introduction; Second Introduction (e-text editor) | — | Tanner summary |
| 1 | On the matters to be treated in the council (John XXIII's bull and the session's decrees) | — | **gap** |
| 2 | Summary only (John XXIII offers to resign) | — | Tanner summary |
| 3 | Decrees on the integrity and authority of the council | — | **gap** |
| 4 | Decrees on its authority and integrity, as abbreviated by Zabarella | — | **gap** |
| 5 | Decrees on its authority and integrity (Haec sancta) | Paraphrase only, p. 444 | **gap** |
| 6, 7 | Summaries only | — | Tanner summary |
| 8 | Opening decree; Sentence condemning Wyclif's 45 articles (**condemned text**); Condemnation of Wyclif's books; Condemnation of 260 other articles; Wyclif declared a heretic | — | **gap** — lead: Foxe, *Acts and Monuments*, Cattley ed., vol. 3 (the sentence and the 45 articles) |
| 9–11 | Summaries only | — | Tanner summary |
| 12 | Decree on the process for a papal election; Sentence deposing John XXIII; Decree that none of the three contenders may be re-elected | — | **gap** |
| 13 | Condemnation of communion under both kinds; Decree that no priest may give communion under both kinds | — | **gap** |
| 14 | Uniting of the obediences; Decree on the manner of electing the pope; Approval of Gregory XII's resignation | — | **gap** |
| 15 | Sentence condemning 260 articles of Wyclif; 58 articles of Wyclif (**condemned text**); Sentence against Hus; Sentence of degradation; Sentence to the stake; 30 articles of Hus (**condemned text**); Sentence on Jean Petit's proposition (**condemned text**) | — | **gap** — lead: Foxe, Cattley ed., vol. 3 (the sentence against Hus) |
| 16–20 | Summaries only (session 19's names Jerome of Prague's abjuration and an ordinance on the Franciscans, not printed) | — | Tanner summary |
| 21 | Sentence condemning Jerome of Prague | — | **gap** |
| 22–36 | Summaries only | — | Tanner summary |
| 37 | Sentence deposing Benedict XIII | — | **gap** |
| 38 | Summary only | — | Tanner summary |
| 39 | On general councils (Frequens); Provision against future schisms; On the profession to be made by the pope; That prelates may not be translated without their consent; On spoils and procurations | Frequens paraphrased, pp. 447–448 | **gap** |
| 40 | Reforms to be made before the council is dissolved; Election may begin without Benedict's cardinals; On the manner and form of electing the pope | The 18 reform points listed in the history, pp. 448–449 | **gap** |
| 41, 42 | Summaries only | — | Tanner summary |
| 43 | Statutes on the reform of the church: seven statutes, then a closing declaration | pp. 453–455, decrees 1–7 | **partial**: decree 1 condensed (175 words against 402); the closing declaration is not printed |
| 44 | Decree on the place of the next council | — | **gap** |
| 45 | Sentence dissolving the council, and indulgences | — | **gap** |

### 17. Basel–Ferrara–Florence (1431–1445) — Schroeder

Schroeder translates the decrees of Basel's sessions 20 and 21 only (pp. 473–479:
"the first four were issued by the council in the twentieth session, the remainder in
the twenty-first"). His history (pp. 456–472) narrates the rest and names Laetentur
caeli without translating it. Tanner's session numbers for Ferrara print with stray
footnote digits ("Session 31", "42", "5′"); they are sessions 3, 4 and 5.

| Session | Tanner documents | Replacement | Status |
|---|---|---|---|
| — | Introduction | — | Tanner summary |
| Basel 1 | Opening statement; Establishment of the council; Purpose of the council | — | **gap** |
| Basel 2 | Decree that the council is legitimately begun | — | **gap** |
| Basel 3 | Impossibility of dissolving the council | — | **gap** |
| Basel 4 | Safe-conduct and hearing for the Bohemians | — | **gap** |
| Basel 5, 6 | Summaries only | — | Tanner summary |
| Basel 7 | Decree on a papal election during the council | — | **gap** |
| Basel 8 | That there ought to be only one council | — | **gap** |
| Basel 9, 10 | Summaries only | — | Tanner summary |
| Basel 11 | Six decrees on the authority of general councils | — | **gap** |
| Basel 12 | Decree on elections and confirmations of bishops | — | **gap** |
| Basel 13, 14 | Summaries only | — | Tanner summary |
| Basel 15 | On provincial and synodal councils | — | **gap** |
| Basel 16 | Summary only | — | Tanner summary |
| Basel 17 | Admission of the papal presidents | — | **gap** |
| Basel 18 | Renewal of Constance's decree on general councils | — | **gap** |
| Basel 19 | Agreement with the Greeks on union; Agreement of the deputies with the Greek envoys; On Jews and neophytes; On those who desire conversion | — | **gap** |
| Basel 20 | On concubinaries; Excommunicates not to be shunned unless named; Interdicts not to be imposed lightly; (untitled) against frivolous appeals | pp. 473–475, decrees 1–4 | covered |
| Basel 21 | Eleven decrees: annates; peaceful possession; the divine office; times in choir; hours outside choir; wandering in church; the notice-board; the creed and songs at mass; pledging divine worship; chapters during mass; spectacles in churches | pp. 475–479, decrees 5–15 | covered |
| Basel 22 | Condemnation of the book of Augustine of Rome (quotes his propositions: **condemned text**) | — | **gap** |
| Basel 23 | Seven decrees: election of the pope; the pope's profession; form of consent; number and qualities of cardinals; elections; reservations; Clementine letters | — | **gap** |
| Basel 24 | On business with the Greeks and indulgences; Safe-conduct for the Greeks | — | **gap** |
| Basel 25 | On the places for the council with the Greeks | — | **gap** |
| Ferrara 1 | Declaration of Cardinal Albergati | — | **gap** |
| Ferrara 2 | On the legitimate continuation of the council at Ferrara | — | **gap** |
| Ferrara 3 | Penalties against members of the Basel synod | — | **gap** |
| Ferrara 4 | Ferrara declared legitimate and ecumenical | — | **gap** |
| Ferrara 5 | Decree moving the council to Florence | — | **gap** |
| Florence 6 | Definition of the union with the Greeks (Laetentur caeli) | — | **gap** |
| Florence 7 | Decree against the synod at Basel | — | **gap** |
| Florence 8 | Bull of union with the Armenians | — | **gap** |
| Florence 9 | Monition against the antipope Felix V | — | **gap** |
| Florence 10 | Eugenius IV's exhortation to the Basel synod | — | **gap** |
| Florence 11 | Bull of union with the Copts (Cantate Domino) | — | **gap** |
| Florence 12 | Convocation of the Lateran continuation | — | **gap** |
| Florence 13 | Bull of union with the Syrians | — | **gap** |
| Florence 14 | Bull of union with the Chaldeans and the Maronites of Cyprus | — | **gap** |

### 18. Lateran V (1512–1517) — Schroeder

Schroeder: "only the decrees incorporated in the bulls are given; lengthy introductions
and conclusions are omitted or merely summarized" (p. 487). Each of his seven bulls is
headed "From the bull …". Word counts are Schroeder's against Tanner's.

| Session | Tanner documents | Replacement | Status |
|---|---|---|---|
| — | Introduction | — | Tanner summary |
| 1 | Summary only (the bulls convoking and postponing the council) | — | Tanner summary |
| 2 | The quasi-council of Pisa condemned | — | **gap** |
| 3 | Measures of the schismatic cardinals rejected | — | **gap** |
| 4 | The Pragmatic revoked and Pisa's acts on it annulled | — | **gap** |
| 5 | Bull renewing the constitution against simony in papal elections | — | **gap** |
| 6 | Safe-conduct for those coming to the council | — | **gap** |
| 7 | Summary only (Meditatio cordis nostri read) | — | Tanner summary |
| 8 | Condemnation of every proposition contrary to the faith (Apostolici regiminis) | pp. 487–488 | **partial**: introduction omitted; about 660 words against 900 |
| 8 | On peace among Christian princes and the Bohemians | — | **gap** |
| 8 | Bull on reform | — | **gap** |
| 9 | The pope urges Christian rulers to make peace | — | **gap** |
| 9 | Bull on reform of the curia (Supernae dispositionis arbitrio) | pp. 488–498 | **partial**: about 4,600 words against 7,000 |
| 10 | On the Montes pietatis (Inter multiplices) | pp. 498–500 | **partial**: about 730 against 1,170 |
| 10 | Bull against exempt persons (Regimini universalis ecclesiae) | pp. 500–504 | **partial**: about 1,700 against 2,700 |
| 10 | On printing books (Inter sollicitudines) | pp. 504–505 | **partial**: about 520 against 730 |
| 10 | On a date for those acknowledging the Pragmatic Sanction | — | **gap** |
| 11 | On how to preach (Supernae majestatis praesidio) | pp. 505–506 | **partial**: about 690 against 2,260 |
| 11 | Bull on the agreements with the king of France | — | **gap** |
| 11 | Abrogation of the Pragmatic Sanction (Pastor aeternus gregem) | — | **gap** |
| 11 | On religious and their privileges (Dum intra mentis arcana) | pp. 506–512 | **partial**: about 1,090 against 2,400 |
| 12 | Against those attacking the houses of cardinals | — | **gap** |
| 12 | Constitution imposing taxes and closing the council | — | **gap** |

### 19. Trent (1545–1563) — Waterworth, for completeness

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Sessions 1–25, decrees and canons; bulls of indiction and confirmation | The vendored page is Waterworth's 1848 translation, not Tanner's | `sources/councils/ecum-19-council-of-trent.html` (1.2b parses it whole) | covered |

### 20. Vatican I (1869–1870) — Schaff

Schaff's section is CCEL `v.ii.i`. Its ThML `title` attribute reads "The Orthodox
Confession of the Eastern Church, A.D. 1643." (a CCEL mislabel); its heading reads
"V. Decreta dogmatica Concilii Vaticani…". The English column holds Dei Filius and
Pastor Aeternus only (7,286 words), in Manning's translation (*Petri Privilegium*, 1871).

| Document | Tanner section | Replacement and location | Status |
|---|---|---|---|
| Introduction | "Introduction" | — | Tanner summary |
| Session 1: decree of opening the council | "Decree of opening of the council" | — | **gap** |
| Session 2: profession of faith | "Profession of faith" | — (see below) | **gap** |
| Session 3: Dei Filius, prologue, chapters 1–4, canons | "Dogmatic constitution on the catholic faith" | `v.ii.i`, English cells | covered |
| Session 4: Pastor Aeternus, prologue, chapters 1–4 | "Session 4" | `v.ii.i`, English cells | covered |

The session 2 profession is the formula of the 1564 Profession of the Tridentine Faith,
which Pius IX recited. Schaff prints that 1564 profession in English as its own document
(`creeds2` `v.i.ii`), not as an act of the Vatican Council.

## Condemned texts read at the council (C-01)

Texts a council read and condemned. They stay in the corpus with their council; 3.4
gives their passages `voice = "rejected"` from the anchors 1.2c and 1.2e list. Where the
text is a gap, nothing is listed until a replacement exists.

| Council | Text | In which source | Note |
|---|---|---|---|
| Ephesus | Nestorius's second letter to Cyril | Tanner only (live `council-of-ephesus/sec-3/3/p1` to `sec-3/6`); not in Percival | Gap |
| Nicaea II | Definition of the iconoclast synod of Hieria (754), read and refuted at session 6 | Not in Tanner; Percival `xvi.x` prints an "Epitome" of it with his bracketed summaries | Only if 1.2c's allowlist takes it (recommended: no) |
| Vienne | Eight errors of the Beghards and Beguines in Ad nostrum | Tanner [28]; Schroeder pp. 389–390 | The listed errors are the rejected voice; the decree around them is the council's |
| Constance | Wyclif's 45 articles (session 8) | Tanner only | Gap |
| Constance | 58 articles of Wyclif selected from the 260; 30 articles of Hus; Jean Petit's proposition (all session 15) | Tanner only | Gap |
| Basel | Propositions of Augustine of Rome quoted in the session 22 condemnation | Tanner only | Gap |

Looked at and not marked, because the council states the error in its own words rather
than reading out the condemned text: Constantinople II's sentence and anathemas 12–14
(Theodore, Theodoret, Ibas), Lateran IV's constitution 2 (Joachim, Amaury), Vienne's
decree [1] (Olivi), Lateran V's Apostolici regiminis. 3.4 may decide otherwise. The
counter-anathemas of Nestorius that Percival quotes under each of Cyril's anathemas
(`x.ix.*`, after "Notes.") are his notes, not texts read at the council, and are
dropped as editor material.

## Percival's units: council text or editor material (for 1.2c)

**Inside a canon or anathema div** the council's text is the paragraphs between the
heading ("Canon I.", class `c34`, also `c46` and, for Nicaea II canon I, `c31`; or the
roman numeral, `c14`) and the first "Notes." paragraph (class `c31`; `c40` in Chalcedon
XXV). Everything from "Notes." on is editor material: the "Ancient Epitome", the
commentators (Zonaras, Balsamon, Aristenus, Hefele, Van Espen and others), and Percival's
own notes. Three exceptions:

- Constantinople I canons V and VI open with Percival's parenthesis "(Probably adopted at
  a Council held in Constantinople the next year, 382…)" (`ix.viii.vi`, `ix.viii.vii-p2`).
  Drop it.
- Every Nicaea II canon (`xvi.xiv.i`–`.xxii`) opens with a one-sentence title in classes
  `c50` or `c35` ("That the sacred Canons are in all things to be observed."). These are
  the titles of the Greek collections, not canon text: drop them, or use them as labels.
- `xii.vii` (Constantinople II's anathemas) has a "Notes." paragraph and Hefele's note
  after anathema XI; anathemas XII–XIV follow under their own headings. Resume at the next
  roman numeral.

**In every other allowlisted div**, stop at a "Note." or "Notes." paragraph: what follows is editor material (for example `x.xvi.xvii-p5` onward, `xi.xv-p5` onward, `xi.xiii-p14` onward).

**Everywhere**, Percival's source lines in parentheses ("(Found in …)", "(Labbe and
Cossart …)", "(From the Acts …)") and his bracketed connecting notes ("[Next was read …]")
are editor material.

Each div, by council. "Allowlist" is the recommendation for 1.2c's per-council list;
"other author" means a text the council received but did not issue.

| Council | Div | Title | Kind | Allowlist |
|---|---|---|---|---|
| all | `i`–`vi`, `xviii` | Title pages, preface, introductions, bibliography, Excursus on Roman law, indexes | editor | no |
| Nicaea | `vii.i`, `vii.ii` | Title page, Historical Introduction | editor | no |
| Nicaea | `vii.iii` | The Nicene Creed (`-p3` to `-p7`; after "Notes.", the Creed of Eusebius is Percival's note) | council | yes |
| Nicaea | `vii.iv`, `vii.v`, `vii.vi.ii`, `.vii`, `.ix`, `.xi`, `.xiii`, `.xvii`, `.xx`, `.xxiii`, `.xxvi`, `.xxix`, `.xxxi`, `vii.xi` | Excursus | editor | no |
| Nicaea | `vii.vi.*` canon divs | Canons I–XX | council | yes |
| Nicaea | `vii.vii` | Captions of the Arabic canons attributed to the council | later collection, not the council's | no |
| Nicaea | `vii.viii` | Proposed action on clerical celibacy (Hefele's narrative) | editor | no |
| Nicaea | `vii.ix` | The Synodal Letter | council | yes |
| Nicaea | `vii.x` | On the keeping of Easter (Constantine's letter) | other author | no |
| — | `viii`, `xiv`, `xv`, `xvii` | Ancyra, Neocaesarea, Gangra, Antioch, Laodicea, Trullo, Sardica, Carthage, Apostolic Canons and the canonical epistles | not ecumenical councils (out of scope, 1.2c) | no |
| Constantinople I | `ix.i`, `ix.ii`, `ix.iv`, `ix.v`, `ix.vii`, `ix.viii.ii`, `.viii`, `.x` | Title page, introductions, excursus, notes, warning on canon VII | editor | no |
| Constantinople I | `ix.iii` | The creed (`-p6`, `-p7` only; the rest is the introductory note, notes and Epiphanius's creeds) | council | yes |
| Constantinople I | `ix.vi` | Letter to the emperor Theodosius | council | yes (not in Tanner) |
| Constantinople I | `ix.viii.*` canon divs | Canons I–VII | council | yes |
| Constantinople I | `ix.ix` | The Synodical Letter (382) | council | yes |
| Ephesus | `x.i`, `x.ii`, `x.iii`, `x.vii`, `x.ix.ii`, `x.ix.xi`, `x.xvi.iii`, `.vii`, `.xi`, `.xvi` | Title page, introductions, notes, excursus | editor | no |
| Ephesus | `x.iv`, `x.vi`, `x.x`, `x.xii`, `x.xiv`, `x.xv` | Extracts from the acts (council record cut and joined by Percival's bracketed summaries) | acts, mixed | no |
| Ephesus | `x.v` | Cyril's second letter | other author (approved) | yes |
| Ephesus | `x.viii`, `x.ix` anathema divs | Cyril's third letter and the twelve anathemas | other author (approved) | yes |
| Ephesus | `x.xi` | Decree against Nestorius (`-p3`) | council | yes |
| Ephesus | `x.xiii` | Letter of Pope Celestine to the synod | other author | no |
| Ephesus | `x.xvi.i` | Titled "Introduction" but `-p4`, `-p5` are the council's synodical letter | council | yes |
| Ephesus | `x.xvi.*` canon divs | Canons I–VIII | council | yes |
| Ephesus | `x.xvi.xiii`, `.xiv`, `.xv`, `.xvii` | Letter to the synod in Pamphylia; letter to Pope Celestine; definition against the Messalians; decree on Euprepius and Cyril (`-p3`; from `-p5` "Note." on, editor) | council | yes (only the Messalians definition is in Tanner) |
| Chalcedon | `xi.i`, `xi.ii`, `xi.xviii.xxix`, `xi.xix` notes | Title page, introduction, excursus | editor | no |
| Chalcedon | `xi.iii`, `.iv`, `.vi`, `.viii`, `.ix`, `.xi`, `.xii`, `.xiv`, `.xix` | Extracts from the acts | acts, mixed | no |
| Chalcedon | `xi.v` | Cyril's letter to John of Antioch (with the formula of union) | other author (approved) | yes (Tanner prints it with Ephesus) |
| Chalcedon | `xi.vii` | The Tome of Leo (`-p4` to `-p8`) | other author (approved) | yes |
| Chalcedon | `xi.x` | Condemnation sent to Dioscorus | council | yes (not in Tanner) |
| Chalcedon | `xi.xiii` | The Definition (`-p3` to `-p13`) | council | yes |
| Chalcedon | `xi.xv`, `.xvi`, `.xvii` | Decrees on Jerusalem and Antioch (`-p4`; from `-p5` "Note." on, editor), Ephesus, Nicomedia (`-p10` is Percival's bracketed note) | council | yes (not in Tanner) |
| Chalcedon | `xi.xviii.i`–`.xxviii` | Canons I–XXVIII | council | yes |
| Chalcedon | `xi.xviii.xxx`, `.xxxi` | Canons XXIX and XXX (extracts of the acts) | acts | Carter's choice; not Tanner documents |
| Constantinople II | `xii.i`–`.iii`, `.viii`, `.xi`, `.xiii` | Title page, introduction, excursus, historical notes | editor | no |
| Constantinople II | `xii.iv`, `.v` | Extracts from the acts | acts, mixed | no |
| Constantinople II | `xii.vi` | The Sentence of the Synod | council | yes |
| Constantinople II | `xii.vii` | The Capitula (14 anathemas) | council | yes |
| Constantinople II | `xii.ix` | Fifteen anathemas against Origen (their attribution to this council is discussed in Percival's excursus `xii.viii`) | disputed | Carter's choice; not in Tanner |
| Constantinople II | `xii.x` | Justinian's anathematisms against Origen | other author | no |
| Constantinople II | `xii.xii` | Decretal letter of Pope Vigilius | other author | no |
| Constantinople III | `xiii.i`, `.ii`, `.iv`, `.xiii` | Title page, introductions, excursus on Honorius | editor | no |
| Constantinople III | `xiii.iii`, `.vii`, `.ix` | Extracts from the acts | acts, mixed | no |
| Constantinople III | `xiii.v`, `.vi` | Letters of Pope Agatho | other author | no |
| Constantinople III | `xiii.viii` | Sentence against the Monothelites | council | yes (not in Tanner) |
| Constantinople III | `xiii.x` | The Definition of Faith | council | yes |
| Constantinople III | `xiii.xi` | Address to the emperor, abridged by Percival (bracketed summaries `-p3`, `-p5`, `-p13` and elisions) | council, abridged | no |
| Constantinople III | `xiii.xii` | Letter to Agatho | council | yes (not in Tanner) |
| Constantinople III | `xiii.xiv` | Imperial edict | other author | no |
| Nicaea II | `xvi.i`, `.ii`, `.xi`, `.xiii`, `.xvi`–`.xxi` | Title page, introduction, excursus, the Caroline Books, notes on later councils | editor | no |
| Nicaea II | `xvi.iii`, `.iv` | Imperial letters (sacra) | other author | no |
| Nicaea II | `xvi.v`–`.ix` | Extracts from the acts (session II includes part of Pope Hadrian's letter) | acts, mixed | no |
| Nicaea II | `xvi.x` | Epitome of the Definition of the iconoclast synod of 754 | **condemned text read at the council**, abridged by the editor | no |
| Nicaea II | `xvi.xii` | The Decree (Definition) | council | yes |
| Nicaea II | `xvi.xiv.*` | Canons I–XXII | council | yes |
| Nicaea II | `xvi.xv` | Letter of the synod to the emperor and empress | council | yes (not in Tanner) |

Counts for 1.2c's checks, as printed: Nicaea 20 canons, the Creed and the Synodal Letter;
Constantinople I 7 canons; Ephesus 8 canons, Cyril's second and third letters and the 12
anathemas; Chalcedon 30 canons (28 plus the two acts extracts) and the Definition;
Constantinople II 14 anathemas; Constantinople III the Definition; Nicaea II 22 canons
and the Definition.

## Schroeder's units: council text or editor material (for 1.2e)

Each council opens with Schroeder's "History." and a bibliography (editor). Each canon
then has, in order: the heading "CANON N"; "Summary." (Schroeder's own one-line digest,
editor); "Text." (the translation, council text); "Comment." (Schroeder's commentary,
editor); then footnotes at the page foot (editor). Constance, Basel and Lateran V have no
canon headings: their decrees are numbered paragraphs (Constance, Basel) or bulls headed
"From the bull …" (Lateran V), each without Summary or Comment, after the council's
history. Schroeder's history sometimes paraphrases a decree (Haec sancta p. 444, Frequens
pp. 447–448): that is his text, not a translation. Pages 513 onward are the Latin texts
and the index, which rule E keeps out.

Units printed, for 1.2e's canon counts: Constantinople IV 27 (condensed); Lateran I 22;
Lateran II 30; Lateran III 27; Lateran IV 71; Lyons I 18 and a second series of 9;
Lyons II 32; Vienne 21 and a second series of 18; Constance 7; Basel 15; Lateran V 7
bulls. The OCR misses a few headings (for example Lateran IV's "CANON 71" on p. 292 and
Lyons II's "CANON 10"), so a count taken from the OCR alone comes out short.

Schroeder also covers councils 1 to 7 (pp. 8–156), with the same layout. It fills neither
Percival gap: it prints canons only, and summarizes Nicaea II's ("we will content
ourselves with giving a summary of them", p. 143).

## The spec's unverified points, settled

| Point (1.2a "Current state") | Finding |
|---|---|
| `npnf214` is not vendored | It is, in the holding folder: `sources/_incoming/councils/npnf214.xml`, 3,196,008 bytes. Its structure is as described above |
| Does Schroeder include Constance's session decrees? | Only the seven statutes of session 43 (pp. 453–455). Haec sancta and Frequens are paraphrased in his history, not translated |
| Vienne's doctrinal constitution? | Yes: Fidei catholicae is first-series canon 1, p. 372 |
| Lateran V's doctrinal bulls? | Apostolici regiminis, yes, without its introduction (pp. 487–488). The other doctrinal or quasi-doctrinal acts (the condemnations of Pisa, Pastor aeternus gregem) are not printed |
| Florence's doctrinal decrees | Confirmed gaps: Laetentur caeli and the bulls of union with the Armenians, Copts, Syrians, Chaldeans and Maronites |
| Vatican I's opening decree and the profession of faith of sessions 1 and 2 | Confirmed gaps: Schaff's English column holds Dei Filius and Pastor Aeternus only |

Found while settling them, and not in the spec: Constantinople IV's canons in Schroeder
are condensed throughout, and Lateran I's canons 15 and 16, Lyons II's constitution I, Constance's session 43, Vienne's Exivi de paradiso and
Lateran V's seven bulls are partial. Whether condensed or excerpted text should stand in
for a council's text is a new NEEDS-CARTER question (1.2e).

## Where the gaps were searched

All on 2 Nov 2026, from this server. The method is R8's (`docs/research/R8-papal-translations.md`,
"Method"), with its tool `docs/research/R8_tools/fts.py`.

- **Internet Archive full-text search**, limited to items dated 1930 or earlier, with
  phrases a translation of any period would contain. Queries, by gap:
  - Nestorius's letter: `"fellow minister Cyril" Nestorius`; `"Nestorius to" "Cyril"
    "fellow-minister" letter`; `"your astonishing letter"`; `"the insults" Nestorius
    Cyril letter`. Found: Chrystal, *Authoritative Christianity: The Third World Council*,
    vol. 1 (Jersey City, 1895; IA `authoritative01chry`), which translates the acts of
    Ephesus; the letter is at pp. 155–161, read in Act I, divided by Chrystal's bracketed
    section summaries and footnotes (editor material). Also *On Faith and the Creed* (1886)
    for Cyril's letters only.
  - Nicaea II anathemas: `"circumscribed" anathema "images" Nicaea "unwritten"`;
    `"evangelical narrations" anathema`; `"does not confess" "circumscribed" "let him be
    anathema"`; then the advanced search by title and creator. Found: Mendham, *The
    Seventh General Council, the Second of Nicaea* (London, 1850; IA
    `seventhgeneralc00mendgoog`), session 7, pp. 442–443; Hefele, *A History of the
    Councils of the Church*, English vol. 5 (Edinburgh, 1896; IA
    `ahistoryofthecou05hefeuoft`), p. 376, quoting them in his narrative. A polemical
    work of 1854 quotes one of them.
  - Constantinople IV's Definition: `"eighth synod" Photius Ignatius definition anathema
    Basil`; `Photius "Ignatius" council 869 "definition" English acts translated`;
    `Photius "eighth" synod definition "husbandman" anathema`; `"Hormisdas" formula
    Photius "eighth" council "royal road"`. Nothing.
  - Lyons I's deposition of Frederick II: `Frederick "fealty" "absolve" Innocent council
    Lyons sentence deposition "we absolve"`; `"Matthew Paris" "English history" Frederick
    sentence council Lyons 1245`. Nothing usable.
  - Vienne's Templar bulls: `"Vox in excelso" Templars bull translation`; `Templars
    Clement bull "order of the Templars" suppress "by way of provision" Vienne`;
    `"Hospitallers" Templars property bull Clement Vienne "Ad providam"`. Nothing.
  - Constance: `"has power immediately from Christ" Constance council` (Haec sancta is
    quoted in essays, for example O'Reilly, *The Relations of the Church to Society*,
    1892, not printed as a document); `"Frequens" "general councils" "five years" "seven
    years" "ten years" Constance`; `Wyclif "forty-five articles" Constance "God ought to
    obey the devil"` (Lechler, *John Wycliffe and his English Precursors*, 1884, and
    Workman, *John Wyclif*, 1926, discuss the articles; not checked for a full list);
    `Hus articles Constance "predestinate" "condemned" "There is only one holy universal
    church"`. No complete printing of any session's decrees.
  - Florence: `"Let the heavens rejoice" Florence Greeks "holy Spirit" "proceeds" union
    1439`; `"the Holy Ghost is eternally from the Father and the Son" Florence`; `"Decree
    for the Armenians" matter form minister sacraments`; `"seven sacraments" "matter"
    "form" "minister" Armenians Eugenius`; `"firmly believes, professes and preaches"
    Jacobites`; `"holy Roman church" "firmly believes" "outside the catholic church"
    "eternal fire" Florence`. Only short quotations inside manuals (Pohle-Preuss, *The
    Divine Trinity*, 1911–1919; Bainvel, *Is There Salvation Outside the Catholic
    Church?*, 1917).
  - Lateran V: `"Pastor aeternus" Leo X "Pragmatic Sanction" abrogation translation`;
    `"Apostolici regiminis" soul immortal Lateran`. Only quotations in manuals (Pohle-Preuss,
    *God the Author of Nature*, 1912–1919).
  - Vatican I sessions 1 and 2: `Vatican council 1870 "profession of faith" "sixth of
    January" "I, Pius"`; `Vatican council "eighth of December, 1869" decree opening
    "council" translation`. Nothing.
- **English Wikisource** (search API): Nestorius second letter Cyril; Council of Constance
  decree; Haec sancta; Laetentur caeli; Council of Florence decree union Greeks; Cantate
  Domino Jacobites; decree for the Armenians Florence; Vox in excelso Templars; Frederick
  II deposition Innocent IV Lyons; Fifth Lateran Council. Found: Foxe, *The Acts and
  Monuments*, ed. Stephen Reed Cattley, vol. 3, transcribed from the scan, with "The
  Sentence given by the Council of Constance, in condemnation of the Doctrine, and Five and
  Forty Articles of John Wickliff" and "The Sentence or Judgment of the Council of
  Constance against John Huss"; and McNabb, *The Decrees of the Vatican Council* (1907),
  whose contents are Dei Filius and Pastor Aeternus only. The rest returned encyclopedia
  articles. Five further queries (Vatican I profession, Constantinople IV, Nicaea II
  anathemas, Wyclif and Hus articles) were refused by the API's rate limit; the IA
  searches above cover the same texts.
- **Fordham, Internet Medieval Sourcebook**: the index pages (`sbook.asp`, `sbook1*.asp`,
  `sbook2.asp`, `sbook3.asp`). Its council texts are Lateran I, II and IV (Schroeder) and
  a dead link to Lateran III; "Second Council of Nicea: Decree on Icons"
  (`source/nicea2-dec.asp`) is Percival's text, without the four anathemas; its other
  council links go to EWTN's copies of Tanner. Nothing for any gap.
- **CCEL**: Schaff, *History of the Christian Church*, vols. 5 and 6 (`hcc5`, `hcc6`).
  Haec sancta and Frequens are paraphrased with the Latin in a note; Laetentur caeli is
  named. No translations.
- **Not searched**: HathiTrust full text (refuses this server, as in R8); Google Books.

## Gap register

The texts below have no public-domain English translation in the planned sources. Once
Carter approves this list, each Tanner passage holding one of them is retired at P4 with
reason `translation-in-preparation` (D9, D11), and its document notes the gap. Tanner's
own summaries and introductions are not gaps: they retire as `rule-g-editorial`.

| # | Council | Text | Lead found |
|---|---|---|---|
| G1 | Ephesus | Nestorius's second letter to Cyril (condemned text) | Chrystal 1895, pp. 155–161 |
| G2 | Nicaea II | The four anathemas concerning holy images | Mendham 1850, pp. 442–443; Hefele vol. 5 (1896), p. 376 |
| G3 | Constantinople IV | Definition of the eighth synod | — |
| G4 | Lyons I | Bull deposing the emperor Frederick II | — |
| G5 | Vienne | Bulls on the Templars and the Holy Land, [1]–[8] | — |
| G6 | Constance | Sessions 1, 3, 4, 5 (Haec sancta), 8, 12, 13, 14, 15, 21, 37, 39 (Frequens and four others), 40, 44, 45: every document listed for them above | Foxe, Cattley ed., vol. 3, for the sentences of sessions 8 and 15 |
| G7 | Constance | Session 43's closing declaration | — |
| G8 | Basel–Ferrara–Florence | Basel sessions 1–4, 7, 8, 11, 12, 15, 17–19, 22–25; Ferrara sessions 1–5; Florence sessions 6–14, including Laetentur caeli and the bulls of union with the Armenians, Copts, Syrians, Chaldeans and Maronites | — |
| G9 | Lateran V | Sessions 2–6; session 8's bulls on peace and the Bohemians and on reform; session 9's exhortation to peace; session 10's decree on the Pragmatic Sanction; session 11's French agreements and Pastor aeternus gregem; session 12's two constitutions | — |
| G10 | Vatican I | Session 1, decree of opening; session 2, profession of faith | — |

Partial texts (Constantinople IV's canons, Lateran I's canons 15 and 16, Lyons II's
constitution I, Constance's session 43, Vienne's Exivi de paradiso, Lateran V's seven
bulls) are not on the register. What is published for them
depends on Carter's answer to the new question in NEEDS-CARTER (1.2e); if the answer is
"whole texts only", they join it.
