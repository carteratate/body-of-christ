# R2. Canon law: amendments to 295, 296, 360, 361 and 948, and English for the Latin canons

Research item R2 (spec: `docs/corpus-cleanup/P0-checks-identity-research.md`, "R2."). Consumed by 1.5b (`docs/corpus-cleanup/P1a-adapters-councils-papal-bible-canon.md`).

All web sources were read on 4 October 2026. No production store was queried. The vendored pages were read in place in the main checkout, `datapipeline/sources/canon-law/`; nothing from them is copied into git beyond the short quotations below.

## Sources and how they were used

- **iuscangreg.it amendment register.** "Modifiche ai canoni del CIC", https://www.iuscangreg.it/cic_modifiche.php. It lists one row per amended canon, with the type of change ("Nuovo testo" = new text; "Modifica della norma, senza toccare il testo" = the rule changed but the canon's wording did not) and the amending act. The act citations, with their vatican.va links and print references (L'Osservatore Romano, AAS), come from the faculty's universal-law list, https://www.iuscangreg.it/diritto_universale.php?tuttelingue=1, at the anchors named per canon below.
- **iuscangreg.it current text.** The faculty's multilingual Code, https://www.iuscangreg.it/cic_multilingue.php, queried for a list of canons with "Versione del Codice" set to the latest (Le prelature personali, 2023) and again set to 1983. It prints Latin, English and Italian per canon. **Its English is not a Holy See text** (for 295 and 296 the faculty's own act list cites the CLSA's *Roman Replies* 2023, pp. 62-63, as the English source). That English is therefore not quoted here and must not be used by 1.5b.
- **vatican.va.** Each amending act, on the paths iuscangreg links to. Which languages exist was read from the vatican.va English index of Francis's motu proprio, https://www.vatican.va/content/francesco/en/motu_proprio.index.html, because vatican.va answers HTTP 200 for a missing language and serves another language's page instead. The English Code on vatican.va, https://www.vatican.va/archive/cod-iuris-canonici/eng/documents/, and the Latin Code, https://www.vatican.va/archive/cod-iuris-canonici/latin/documents/cic_liberII_la.html, were fetched for comparison.
- **Vendored pages.** Every vendored page checked here (`cic_lib1-cann96-123_en.html`, `cic_lib2-cann208-329_en.html`, `cic_lib2-cann330-367_en.html`, `cic_lib2-cann460-572_en.html`, `cic_lib2-cann573-606_en.html`, `cic_lib2-cann607-709_en.html`, `cic_lib4-cann834-878_en.html`, `cic_lib4-cann879-958_en.html`) is byte-identical to the page vatican.va serves today. So "the vendored page" and "vatican.va's English Code today" are the same text throughout. The pages carry `eventDate 2018-02-14` in their metadata, but `cic_lib2-cann607-709_en.html` already includes a rescript of 25 March 2026 at canon 699 §2, so vatican.va keeps editing individual canons without updating that date.
- **L'Osservatore Romano, English edition.** The online archive (https://www.osservatoreromano.va/en/pages/archive.html) is subscriber-only, so no issue could be read directly. One issue is cited through a reprint (Part 2). Print issues were not inspected.
- **Vatican News** (vaticannews.va, run by the Holy See's Dicastery for Communication). Its English articles were checked for English renderings of each amended canon.

---

## Part 1. Amendments: canons 295, 296, 360, 361, 948

### Canon 295

- **iuscangreg.it:** amended, "Nuovo testo". Act: Francis, apostolic letter motu proprio *Le Prelature personali* ("con la quale vengono modificati i cann. 295-296 relativi alle prelature personali"), 8 August 2023, arts. 1-2. Promulgated in L'Osservatore Romano 163 (2023) n. 182, 8 Aug 2023, p. 8; AAS 115 (2023) 951-953 (iuscangreg anchor `#Q517`). In force on publication, 8 August 2023.
- **vatican.va act:** https://www.vatican.va/content/francesco/it/motu_proprio/documents/20230808-motu-proprio-prelature-personali.html. The motu proprio is in **Italian only** (the index lists IT alone; the `/en/` and `/la/` paths serve the Italian page or 404). The amended canon text inside it is Latin.
- **Current text (iuscangreg.it, "nella versione attuale, sin dal m.p. Le prelature personali (2023)")**, identical to the Latin in the act:
  > Can. 295, § 1. Praelatura personalis, quae consociationibus publicis clericalibus iuris pontificii cum facultate incardinandi clericos assimilatur, regitur statutis ab Apostolica Sede probatis vel emanatis eique praeficitur Praelatus veluti Moderator, facultatibus Ordinarii praeditus, cui ius est nationale vel internationale seminarium erigere necnon alumnos incardinare, eosque titulo servitii praelaturae ad ordines promovere.
  >
  > Can. 295, § 2. Utpote Moderator facultatibus Ordinarii praeditus, Praelatus prospicere debet sive spirituali institutioni illorum, quos titulo praedicto promoverit, sive eorundem decorae sustentationi.
- **English:** no official English. vatican.va has none (the Press Office bulletin of 8 August 2023, https://press.vatican.va/content/salastampa/en/bollettino/pubblico/2023/08/08/230808b.html, says the letter "may be consulted in Italian"). The only Holy See English found is a **Vatican News article**, "Pope modifies Church law on personal prelatures" (Deborah Castellano Lubov, 8 August 2023), https://www.vaticannews.va/en/pope/news/2023-08/pope-francis-church-law-personal-prelatures.html, which renders both paragraphs in English, introduced as "This part of the canon, therefore, is reformulated, as follows". It is a news report's rendering, not a promulgated text. Two accuracy points for whoever approves it:
  - § 2 renders the Latin "sive ... sive" (both ... and) as "either ... or", which changes the prelate's duty from two obligations to a choice between them.
  - § 1 renders "assimilatur" as "is similar to", and "iuris pontificii" as "of pontifical law".
  The L'Osservatore Romano weekly English edition of 11 August 2023 (reader page https://www.osservatoreromano.va/en/pdfreader.html/ing/2023/08/ING_2023_032_1108.pdf.html) may carry a translation; it is subscriber-only and was not read.
- **Vendored page:** `cic_lib2-cann208-329_en.html` has the **pre-2023 English** ("The statutes established by the Apostolic See govern a personal prelature, and a prelate presides over it as the proper ordinary; ..."), with no "n" amendment marker (the small "n" vatican.va prints beside a canon whose text has been changed since 1983). It lacks every element the 2023 text added: the assimilation to public clerical associations, "probatis vel emanatis", and the prelate as Moderator with an Ordinary's faculties (replacing "proper ordinary"). vatican.va's Latin Code page is also pre-2023 for this canon (and reads "ciu ius est" for "cui ius est").
- **Treatment for 1.5b:**
  - Rule F: the 1983 English becomes the history passage `can/295/history-2023`; the current passage takes the 2023 text with `amended_by` = *Le Prelature personali*, 8 Aug 2023.
  - Rule E applies to the current text unless Carter approves the Vatican News English (see "For Carter"). If approved: English in `content` labelled unofficial, the Latin above in `metadata["official_latin"]`. If not: the Latin above in `content`, `language = "la"`, `searchable = False`.

### Canon 296

- **iuscangreg.it:** amended, "Nuovo testo". Same act, art. 3 (anchor `#Q517`).
- **vatican.va act:** same page as 295, Italian only.
- **Current text (iuscangreg.it), identical to the act:**
  > Can. 296. Servatis can. 107 praescriptis, conventionibus cum praelatura initis, laici operibus apostolicis praelaturae personalis sese dedicare possunt; modus vero huius organicae cooperationis atque praecipua officia et iura cum illa coniuncta in statutis apte determinentur.
- **English:** no official English; the same Vatican News article renders it ("Can. 296. Maintaining the provisions of can. 107, ..."). Same status and caveats as 295.
- **Vendored page:** `cic_lib2-cann208-329_en.html` has the pre-2023 English, matching the live text the spec records ("Lay persons can dedicate themselves to the apostolic works of a personal prelature by agreements..."). The only change in 2023 is the opening clause "Servatis can. 107 praescriptis"; the rest of the Latin is the 1983 wording.
- **Treatment for 1.5b:** as 295: history passage `can/296/history-2023`, current text from the act, and English or rule E on Carter's answer.

### Canon 360

- **iuscangreg.it:** "Modifica della norma, senza toccare il testo": the rule changed, the wording did not. Act: Francis, apostolic constitution *Praedicate evangelium*, 19 March 2022 (anchor `#Q485`). The register notes that the Curia described in cc. 360-361 was changed first by *Pastor bonus* (1988) and then by *Praedicate evangelium*, and that it lists only the latest.
- **vatican.va act:** https://www.vatican.va/content/francesco/en/apost_constitutions/documents/20220319-costituzione-ap-praedicate-evangelium.html (English on vatican.va; also LA, IT and others). It does not amend the canon's text. Art. 12 § 1 sets the current structure: "The Roman Curia is composed of the Secretariat of State, the Dicasteries and other Institutions, all juridically equal among themselves." Art. 250 § 3 abrogates *Pastor bonus*.
- **Current text:** the 1983 text is still the canon's text. iuscangreg prints it unchanged in its latest version. Its Latin reads "et **quae** nomine et auctoritate ipsius munus explet" where vatican.va's Latin Code reads "et **qua** nomine"; this does not affect the English.
- **English:** the 1983 English on vatican.va is the canon's English; no new text exists.
- **Vendored page:** `cic_lib2-cann330-367_en.html` has the 1983 English, matching the live text the spec records. Nothing to replace.
- **Treatment for 1.5b:** no override, no history passage. Rule F is met because the text in force is unchanged. Whether the reader should note that the bodies it names were reorganised (see "For Carter") is a design question.

### Canon 361

- **iuscangreg.it:** "Modifica della norma, senza toccare il testo"; *Praedicate evangelium*, 19 March 2022 (anchor `#Q485`).
- **vatican.va act:** as for 360. No text change to canon 361.
- **Current text:** the 1983 text, unchanged in iuscangreg's latest version and in vatican.va's Latin Code.
- **English:** the 1983 English on vatican.va.
- **Vendored page:** `cic_lib2-cann330-367_en.html`, 1983 English, matching live. Nothing to replace.
- **Treatment for 1.5b:** none, as 360.

### Canon 948

- **iuscangreg.it:** "Modifica della norma, senza toccare il testo", twice:
  - Congregation for the Clergy, decree *Mos iugiter*, 22 February 1991, art. 2 (AAS 83 (1991) 443-446; anchor `#Q56`). This predates every vatican.va English page and the canon's wording was never changed by it.
  - Dicastery for the Clergy, decree *Secundum probatum*, 13 April 2025, approved in specific form by Francis the same day, in force 20 April 2025 (AAS 117 (2025) 403-408; L'Osservatore Romano 165 (2025) n. 85, 14 Apr 2025, pp. 4-5; anchor `#Q549`). It regulates "collective" Mass intentions under conditions; art. 6 keeps *Mos iugiter* in force where the provincial bishops make no provision.
- **vatican.va act:** https://www.vatican.va/content/romancuria/it/dicasteri/dicastero-clero/documenti/20250413-decreto-intenzioni-messe.html, **Italian only** (the `/en/` and `/la/` paths 404). It cites can. 948 (art. 5) but does not amend its text.
- **Current text:** the 1983 text, unchanged in iuscangreg's latest version: "Distinctae applicandae sunt Missae ad eorum intentiones pro quibus singulis stips, licet exigua, oblata et acceptata est."
- **English:** the 1983 English on vatican.va. No Holy See English of *Secundum probatum* was found (iuscangreg's English link is Zenit; Vatican News reported it in English but without a text of the canon).
- **Vendored page:** `cic_lib4-cann879-958_en.html` has the 1983 English, matching the live text the spec records. Nothing to replace.
- **Treatment for 1.5b:** none. As with 360, whether to add a reader note pointing to *Secundum probatum* is for Carter.

### Part 1 summary

| Canon | Text amended? | Act | Override in 1.5b |
|---|---|---|---|
| 295 | Yes (§§ 1-2) | *Le Prelature personali*, 8 Aug 2023 | Yes, plus history passage |
| 296 | Yes | same | Yes, plus history passage |
| 360 | No (norm only) | *Praedicate evangelium*, 19 Mar 2022 | No |
| 361 | No (norm only) | same | No |
| 948 | No (norm only) | *Mos iugiter* 1991; *Secundum probatum* 2025 | No |

---

## Part 2. English for the canons printed in Latin: 111, 112, 535 § 2, 579, 695, 700, 868 § 1 2°

The vendored English Code prints these in Latin because each was replaced after the 1983 English was made. Every one is current: the vendored Latin matches the amending act and iuscangreg's latest version (one spelling difference noted at 112).

### Canons 111, 112, 535 § 2 and 868 § 1 2°: *De concordia inter Codices*

All four come from one act: Francis, apostolic letter motu proprio *De concordia inter Codices*, 31 May 2016, arts. 1-4 (and art. 5 for 868 § 3, see below). Latin: https://www.vatican.va/content/francesco/la/apost_letters/documents/papa-francesco-lettera-ap_20160531_de-concordia-inter-codices.html. Promulgated in L'Osservatore Romano 156 (2016) n. 212, 16 Sep 2016, p. 4; AAS 108 (2016) 602-606 (iuscangreg anchor `#Q308`).

- **English source found:** L'Osservatore Romano, Weekly Edition in English, **23 September 2016, page 9**. Seen only through the EWTN Library reprint, which carries that credit line: https://www.ewtn.com/catholicism/library/de-concordia-inter-codices-7264. The print page was not inspected.
- **Not on vatican.va in English.** The letter exists there in LA, IT and ES only (index above; the `/en/` path serves another language). The Press Office English bulletin of 15 September 2016 (https://press.vatican.va/content/salastampa/en/bollettino/pubblico/2016/09/15/160915b.html) summarises the letter but gives no canon text. iuscangreg's English citation for this act is *Eastern Legal Thought* 13 (2017) 49-54, which is not a Holy See publication.
- **Status for the reader label:** unofficial English (L'Osservatore Romano), Latin official. This is the treatment the plan already names for 111, 112, 535 and 868.
- **Per canon, where the English sits in the reprint:**
  - **111** (all of §§ 1-3): art. 1, beginning "§1. Through the reception of baptism a child is ascribed to the Latin Church...". The reprint's article heading misprints the canon as "Can. III".
  - **112** (all of §§ 1-3): art. 2, beginning "§1. After the reception of baptism, the following are enrolled in another Church sui iuris...". Spelling note: the act and the vendored page read "ascribuntur" in § 1; iuscangreg reads "adscribuntur".
  - **535 § 2**: art. 3, beginning "§2. In the baptismal register, a note is also to be made of ascription to a Church 'sui iuris'...".
  - **868 § 1 2°**: art. 4, beginning "§1. 2° there must be a founded hope that the infant will be brought up in the Catholic religion subject to § 3...".
- **Reprint quality.** The EWTN copy has typesetting errors elsewhere in the letter ("henccforth", "neccssary", "in its entirely"), and its 868 § 3 reads "for than to obtain access to the actual ministry" where the Latin has "ministrum proprium" (their own minister). If 1.5b vendors the EWTN page, the text should be checked against the print page or the errors noted. That is a question for Carter below.

### Canon 868 § 3 is missing from the source (new finding)

Art. 5 of *De concordia* added a § 3 to canon 868:
> § 3. Infans christianorum non catholicorum licite baptizatur, si parentes aut unus saltem eorum aut is, qui legitime eorundem locum tenet, id petunt et si eis physice aut moraliter impossibile sit accedere ad ministrum proprium.

The vendored `cic_lib4-cann834-878_en.html` (and vatican.va today) has only §§ 1-2 for canon 868, in neither Latin nor English, although § 1 2° itself says "firma §3". iuscangreg's current text includes § 3. Canon 868 as built therefore lacks a paragraph in force. The same L'Osservatore Romano weekly English edition (ORE below) covers it (art. 5). Adding a paragraph goes beyond what 1.5b's "Changes" list names, so it is listed for Carter rather than written into the spec.

### Canon 579: *Authenticum charismatis*

- Act: Francis, apostolic letter motu proprio *Authenticum charismatis*, 1 November 2020, in force 10 November 2020 (AAS 112 (2020) 1075-1076; anchor `#Q449`). English on vatican.va: https://www.vatican.va/content/francesco/en/motu_proprio/documents/papa-francesco-motu-proprio-20201101_authenticum-charismatis.html, which cites "L'Osservatore Romano, Weekly edition, n. 45, 6/11/2020".
- **English source: none found.** The vatican.va English letter (the ORE weekly text) leaves the new canon in Latin: "I have decided to modify can. 579, which is replaced by the following text:" followed by the Latin. The Vatican News report of 4 November 2020 (https://www.vaticannews.va/en/pope/news/2020-11/pope-francs-apostolic-letter-motu-propio-institutes-consecrated.html) also prints "The amended canon 579 reads:" with the Latin, and only paraphrases it in English. iuscangreg's English citation is a CLSA Newsletter.
- Places searched: vatican.va (EN letter and index), Vatican News, iuscangreg's act list, ORE (subscriber-only, not read beyond the citation vatican.va gives).
- **Status:** rule E: Latin kept in the reader, out of search.

### Canon 695 (§ 1): *Recognitum Librum VI*

- Act: Francis, apostolic letter motu proprio *Recognitum Librum VI*, 26 April 2022 (L'Osservatore Romano 162 (2022) n. 94, 26 Apr 2022, p. 7; AAS 114 (2022) 551-552; anchor `#Q487`). Latin: https://www.vatican.va/content/francesco/la/motu_proprio/documents/20220426-motu-proprio-recognitum-librum-vi.html.
- **English source: none found.** vatican.va lists IT and LA only; its `/en/` page is an English title with no body. No Vatican News English article was found. The English renderings in circulation are Catholic News Agency's (e.g. https://www.aciafrica.org/news/5737/pope-francis-updates-canon-law-on-dismissal-from-religious-institutes), not the Holy See's. iuscangreg gives no English citation.
- Places searched: vatican.va (EN, LA, IT, index), Vatican News, web search for any Holy See English, iuscangreg's act list; ORE weekly English for late April 2022 not read (subscriber-only).
- **Status:** rule E for § 1.
- **Spec correction.** Only § 1 is Latin. In the vendored page § 2 is English ("§2. In these cases, after the proofs regarding the facts and imputability have been collected, ..."), because only § 1 was replaced. The R2 spec and 1.5b said "695 ... in full"; both are corrected in this branch. The plan's "Verified corpus problems" table (Canon law) said the same; it is corrected to "695 §1" in this branch, as a fact correction.

### Canon 700: *Expedit ut iura*

- iuscangreg lists two amendments and treats the later as current: *Competentias quasdam decernere* (11 February 2022) and then *Expedit ut iura*, 2 April 2023, art. 1, in force 7 May 2023 (AAS 115 (2023) 405-406; anchor `#Q511`). The vendored page has the 2023 Latin, which matches the act and iuscangreg. So the live text is current.
- English on vatican.va: https://www.vatican.va/content/francesco/en/motu_proprio/documents/20230402-motu-proprio-expedit-ut-iura.html (EN and IT exist; no LA page).
- **English source: none found.** The vatican.va English letter describes the change in English ("the term of 'ten days' is replaced by 'thirty days'") but gives the canon itself only in Latin. The Vatican News report of 3 April 2023 (https://www.vaticannews.va/en/pope/news/2023-04/pope-extends-deadline-to-appeal-dismissal-from-institutes.html) paraphrases without a text. iuscangreg's English citations are *The Canonist* and *Roman Replies*, both non-Holy See.
- Places searched: vatican.va (EN, IT, index), Vatican News, iuscangreg's act list; ORE weekly English for April 2023 not read (subscriber-only).
- **Status:** rule E.

### Part 2 summary

| Canon | Latin in the source | English source | Status |
|---|---|---|---|
| 111 | all | ORE weekly English, 23 Sep 2016, p. 9 (via EWTN reprint) | Unofficial English, Latin official |
| 112 | all | same | Unofficial English, Latin official |
| 535 | § 2 | same | Unofficial English, Latin official |
| 868 | § 1 2° (and § 3 missing) | same | Unofficial English, Latin official |
| 579 | all | none found | Rule E |
| 695 | § 1 only | none found | Rule E for § 1 |
| 700 | all | none found | Rule E |

---

## Amendments outside the two lists (listed, not fixed)

iuscangreg's register has 61 rows. The plan's canon-law section already covers 237, 265, 686 § 1, 688, 694, 1308 and 1310. A spot check of the vendored pages against the register found one more group the plan does not name:

- **De concordia inter Codices arts. 6-11, the marriage canons 1108 § 3 (new), 1109, 1111 § 1, 1112 § 1, 1116 § 3 (new) and 1127 § 1.** The vendored `cic_lib4-cann998-1165_en.html` (= vatican.va today) still has the pre-2016 English for all six, in English and with no amendment marker. For example 1109 still ends "provided that one of them is of the Latin rite", and 1108 and 1116 have no § 3. Under rule F these are superseded texts in search today. The same ORE English (23 Sep 2016, p. 9) covers them.
- **Canon 699 § 2:** a Leo XIV rescript *ex audientia* of 25 March 2026 (anchor `#Q574`, "Facoltà speciali"). The vendored page already carries it, so this is not a gap; it shows the vendored pages were fetched after 25 March 2026.

The rest of the register was not checked against the vendored text.

---

## For Carter

1. **Approve the English source for 111, 112, 535 § 2 and 868 § 1 2°:** L'Osservatore Romano, Weekly Edition in English, 23 September 2016, p. 9, as reprinted by the EWTN Library (URL above). Two sub-questions:
   - Is the EWTN reprint an acceptable copy for 1.5b to vendor, given its typesetting errors, or must the print page be checked first? An ORE subscription would show the page; I found no free copy.
   - The proposed label, as the spec suggests: "Unofficial English translation (L'Osservatore Romano). The Latin text is official."
2. **Canons 295 and 296 have no official English.** The only Holy See English is a Vatican News article of 8 August 2023, which mistranslates "sive ... sive" in 295 § 2 as "either ... or". Choose one:
   - (a) Use the Vatican News English, labelled e.g. "Unofficial English translation (Vatican News). The Latin text is official."
   - (b) Rule E: Latin in the reader, out of search.
   I lean to (b) for 295 because of the § 2 error, and (a) or (b) is equally defensible for 296. Either way the 1983 English becomes the history passage.
3. **Canons 579, 695 § 1 and 700:** no Holy See English exists; they follow rule E as decided. No approval needed unless you want to override.
4. **Canon 868 § 3 is missing from the source** (added in 2016, not on vatican.va's English page). Should 1.5b add it as a new paragraph (Latin official, ORE English unofficial)? That goes beyond 1.5b's current "Changes".
5. **Canons 360, 361 and 948** keep their text; their rules were changed by other law (*Praedicate evangelium*; *Mos iugiter* and *Secundum probatum*). Should the reader carry a short note pointing to that law, or nothing? Nothing is the default under rule F.
6. **The marriage canons 1108, 1109, 1111, 1112, 1116 and 1127** carry pre-2016 English in the source, the same problem as 295. They are outside R2's lists, so they need either a new item or an extension of 1.5b.
7. **The plan's "Verified corpus problems" table** (Canon law row "Latin in the English Code") said 695 is Latin "in full". Only § 1 is. The table is corrected to "695 §1" in this branch.

Uncertain: the content of the ORE English pages (2016, 2020, 2022, 2023), which could not be read without a subscription. The 11 August 2023 issue in particular may carry an ORE English of 295-296.

## Answered by Carter (4 Oct 2026)

Carter answered as follows: (1) approve the 2016 L'Osservatore Romano English and the label, used only after a check against the printed page, else rule E (the print-check condition was later relaxed; see the Follow-up below); (2) rule E for 295 and 296; (3) add 868 §3 in 1.5b; (4) no reader note on 360, 361, 948; (5) extend 1.5b to the six marriage canons. Recorded in `NEEDS-CARTER.md`, the plan's Decision log and the 1.5b spec.

## Follow-up: checking the 2016 English without the printed page (4 Oct 2026)

Carter's approval required the L'Osservatore Romano English (ORE) to be checked against the printed page. What was found:

- **The print issue is not freely reachable.** The ORE online reader (osservatoreromano.va, `pdfreader.html/ing/...`) lists only 2025 and 2026 issues and needs a subscriber login; the 23 Sep 2016 issue is not on archive.org. The vatican.va English URL for *De concordia* (`.../en/apost_letters/documents/papa-francesco-lettera-ap_20160531_de-concordia-inter-codices.html`) returns a page with no text, only links to ES, IT and LA.
- **A second copy of the same English exists.** The Canon Law Society of Great Britain and Ireland's English Code (https://canonlawabstracts.uk/html/code_of_canon_law.pdf, "Incorporates amendments to … De concordia inter Codices, 31 May 2016") prints the 2016 texts with the note "Revised wording according to m.p. De concordia inter Codices". A word-by-word comparison with the EWTN reprint, after normalising British spelling (favourable in 1112 §1 is the only spelling difference), quotation marks around *sui iuris*, and page furniture, found:
  - **identical** canon text for 10 of the 11: 111, 112, 535 §2, 868 §1 2°, 1108 §3, 1109, 1111 §1, 1112 §1, 1116 §3 and 1127 §1;
  - **868 §3 different.** The CLSGBI Code uses another translation there ("Infants of non-Catholic Christians … approach their own minister"), the same wording as the Catholic Herald's translation (Bradley and Condon) reprinted by Catholic Culture (https://www.catholicculture.org/culture/library/view.cfm?recnum=11370). So for 868 §3 the EWTN reprint is the only ORE witness, and it reads "for than to obtain access to the actual ministry". "For than" is a typo; "the actual ministry" does not render the Latin *ministrum proprium* ("their own minister"), and whether it is the print's wording or a transcription error cannot be told.
  - EWTN's known errors ("Can. III", "henccforth", "neccssary", "in its entirely") are all in the article headings or the preamble, not in the canon texts.
- **How independent the two copies are.** Nothing shows where the CLSGBI editor took these texts from; they could in principle have been copied from EWTN. Two points suggest a separate path: CLSGBI did not take 868 §3 from the same source (it used the Catholic Herald's wording there), and it does not reproduce any of EWTN's typesetting errors. The residual risk is that both copies descend from one transcription rather than independently from the print.
- The CLSGBI text is copyright (The Canon Law Society Trust) and is used here only as a witness, not as a source for 1.5b.

**Carter's decision (4 Oct 2026):** the word-for-word agreement of the two copies stands in for the print check for the 10 canons above. 1.5b uses the ORE English from the EWTN reprint for those, with the label already approved. 868 §3 follows rule E (Latin, out of search) until someone sees the printed page.
