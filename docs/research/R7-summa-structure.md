# R7. The Summa against an independent edition

30 October 2026. Research item R7 (issue #227), which blocks 1.7. Spec: `docs/corpus-cleanup/P0-checks-identity-research.md`, section R7. Decision log rows: "The Summa against an independent edition (R7)", "Summa reply targets (1.7)", "Summa anchors (2.1)". Nothing here touches live data.

Deliverables:

- this document;
- `datapipeline/ingest/summa_corrections.json`, which 1.7 reads (format in section 8; IDs, numbers and short labels only, no passage text);
- `datapipeline/tests/test_summa_corrections.py`, which checks the file's format, and with sources that every key is a paragraph of `summa.xml`.

## 1. Summary

- **Candidates.** The four core parts were inventoried unit by unit against the Leonine Latin (Corpus Thomisticum: 87 pages, 23,322 units, 2,663 articles plus 6 one-article questions). Reading the English as a parser that trusts its bold labels would, **353 articles** differ from the Latin: 290 in their markers, and 63 more only because the Latin has a general reply ("Et per hoc patet responsio ad obiecta") that the English gives as prose. The 6 Oct review counted 263 by a method it did not publish; a looser English reading here (unbold "On the contrary" and "Reply OBJ" counted as markers) gives 248. Sol's figure falls between the two. Section 3 explains.
- **Every candidate has a verdict** (section 9: 426 findings in the 353 articles). Taking each article's most serious finding: 11 articles have an omission, 62 a source error, 271 only prose or joint replies, 9 only legitimate variants. By finding: 298 prose or joint replies, 53 legitimate variants, 63 source errors, 12 omissions.
- **The printed edition decides whose defect it is.** Every source error and omission was checked against scans of the printed English Dominican translation (second edition, 1920s), except where noted. **Most defects are CCEL's, not the translators'.** Of the 12 omissions, 10 are text the printed edition has and CCEL lost. Of the 63 source errors, 61 are CCEL's (wrong numbers, unrecognised markers, a duplicated paragraph, articles merged into one div, markers left unbolded); the other 2 are editorial units the print itself carries (C-04), and III q.26 a.2's appended editorial section (7 paragraphs, A-019) is flagged too.
- **The five known omitted units.** Four are CCEL's: I q.76 a.3 objection 3, I q.89 a.3's second sed contra, and the sed contras of I-II q.88 a.4 and III q.7 a.10 are all in the printed second edition. **Only II-II q.182 a.4's sed contra is missing from the print too.** It is in another pre-1931 English translation, Hugh Pope's *On Prayer and the Contemplative Life* (1914). So all five can be restored from an existing English edition (section 6).
- **Five omissions the reviews did not know**, all CCEL's and all in the print: I q.80 a.2 reply 3; I-II q.4 a.4 reply 1; I-II q.29 a.3 replies 2 and 3; the first half of I q.112 a.2 reply 1; and a span of I q.117 a.2 running from inside the sed contra to inside the determination. I q.117 a.2 is therefore **not a reply-only article**, as A-014 read it. The other two (I q.74 a.3 and q.91 a.4) are confirmed: their Latin has no determination either.
- **The Supplement** (446 article containers) was compared with the Leonine text in volume 12 of the Opera omnia (1906), which Corpus Thomisticum links to on archive.org rather than hosting. The route is open: nothing was refused. But that scan's two-column OCR supports only a partial machine comparison. The English side is inventoried completely: 123 articles with irregular markers. The source errors among them were read against the Latin and the print (10 entries in the corrections file), and the remainder is a stated gap (section 7).

## 2. Sources

| Role | Source | Notes |
|---|---|---|
| English under test | `datapipeline/sources/summa/summa.xml` (CCEL ThML, the English Dominican translation, second edition; CCEL's text of the Benziger 1947 printing) | Paragraph ids `FP_Q76_A3-p4` etc.; every non-empty `<p>` inside an article container has one. |
| Latin census, four core parts | [Corpus Thomisticum](https://www.corpusthomisticum.org/iopera.html), "Textum Leoninum Romae 1888 editum et automato translatum a Roberto Busa SJ … denuo recognovit Enrique Alarcón" | 87 pages (`sth0000`–`sth4090`), fetched 30 Oct 2026 one at a time, 6 s apart, all HTTP 200. Each unit is titled (`I q. 76 a. 3 arg. 3`) and numbered; this document cites units as `[CT 31534]`. |
| Latin, Supplement | Leonine *Opera omnia* vol. 12 (Rome, 1906), [archive.org `operaomniaiussui12thom`](https://archive.org/details/operaomniaiussui12thom), OCR text and word-coordinate XML | Corpus Thomisticum does not host the Supplement; its index links "Fr. Rainaldus Romanus, Supplementum, Quaestiones 1-99" to this scan. This is the base text used here. |
| The printed English (authority for what our English should say) | Burns Oates & Washbourne (London) printings of the Dominican translation, from archive.org (University of Toronto, Trent University and Digital Library of India copies) | Volumes and dates in the next table. |
| Another English edition | Hugh Pope, O.P., *On Prayer and the Contemplative Life by S. Thomas Aquinas* (R. & T. Washbourne, London, 1914), [archive.org `onprayercontempl00thomuoft`](https://archive.org/details/onprayercontempl00thomuoft) | A separate translation of II-II qq. 179–182 (with the treatise on prayer). |

Printed volumes used (the second-edition series appeared volume by volume between 1920 and 1929; each scan's own title page is quoted):

| Key in the corrections file | archive.org item | Contents | Edition as printed |
|---|---|---|---|
| dom2-v4 | summatheologicao0004thom | I, QQ. 75–102 | "Second and revised edition", imprimatur 1922 (a second copy, summatheologi04thom, is the same edition) |
| dom2-v5 | summatheologicao0005thom | I, QQ. 103–119 | 1922 |
| dom2-v6 | summatheologicao0006thom | I-II, QQ. 1–48 | "First published 1914, Second edition 1927" |
| dom2-v7 | summatheologicao0007thom | I-II, QQ. 49–89 | imprimatur 3 Feb 1927 |
| dom2-v8 | summatheologicao0008fath | I-II, QQ. 90–114 | "First printed 1915, Second edition 1927" |
| dom2-v9 | summatheologicao0009thom | II-II, QQ. 1–46 | date not in the scan's text |
| dom2-v10 | summatheologicao0010thom | II-II, QQ. 47–79 | 1929 |
| dom2-v11 | summatheologicao0011thom | II-II, QQ. 80–100 | date not in the scan's text |
| dom2-v12 | summatheologicao0012thom | II-II, QQ. 101–140 | 1922 |
| dom2-v14 | sumatheologicaof0014unse (Benziger, New York, 1922); also summatheologicao0000thom_v3w8 (London, 1922) | II-II, QQ. 171–189 | 1922 |
| dom2-v15 | thesummatheologi15aquiuoft | III, QQ. 1–26 | "Second and revised edition"; printing date not in the scan's text |
| dom1-v15 | summatheologi15thom | III, QQ. 1–26 | first edition, R. & T. Washbourne, 1913 |
| dom2-v16 | in.ernet.dli.2015.188677 (Digital Library of India) | III, QQ. 27–59 | "Second and revised edition", 1926 |
| dom2-v17 | summatheologicao0017thom | III, QQ. 60–83 | 1923 |
| dom-v18 | summatheologi18thom | III 84–90, Suppl. 1–33 | R. & T. Washbourne, 1917 |
| dom-v19, v20, v21 | summatheologicao0019thom, 0020thom, 0021thom | Suppl. 34–68, 69–86, 87–99 and appendices | 1930 (as read in the scan's text), 1921, 1922 |

Not found as text or not needed: Part I QQ. 1–74 (no source error or omission falls there, except the markup cases in section 5, which were not checked in print) and II-II QQ. 141–170. Liberty Fund's Online Library of Liberty was not needed once archive.org had every volume used.

**Which Latin text the translators used.** The volumes do not say. Volume 1 (Part I QQ. 1–26, both the 1911 first edition and the second edition) describes the Leonine edition in its introduction. The translators' notes cite Leonine readings as variants ("The Leonine edition has …", I q.75 a.5; I-II q.19 a.7), and they keep passages the Leonine prints only in its apparatus or not at all: III q.55 a.6 objection 5 ("wanting in the older codices, and in the text of the Leonine edition"), III q.7 a.9 reply 3 (no Leonine ad 3, and no note), III q.22 a.2 reply 3 ("Some editions, however, give the following reply"), and I-II q.102 a.6 reply 10 ("supplied by Nicolai"). So their base was a pre-Leonine text, probably the Piana tradition that Nicolai's edition follows, collated with the Leonine where it had appeared.

**Not used as a witness.** New Advent shares the CCEL omissions (A-018, B-002), so it proves nothing about them. The Aquinas Institute's Latin-English edition (aquinas.cc) is copyrighted. Carter allowed it for cross-checking hard cases, one page at a time, but no case needed it: the Latin and the print settled every one. A web search turned up a pirated copy of that edition's Supplement volume, which was not opened.

All downloads (approved by Carter on 30 Oct 2026) are under the main checkout's gitignored `datapipeline/releases/local/r7/downloads/`, with the scripts in `…/r7/scripts/` (section 10).

## 3. Method

1. **Latin inventory.** Every `<P TITLE="…">` unit on the 87 pages: part, question, article, unit (`arg. N`, `s. c.` or `s. c. N`, `co.`, `ad N`, `ad arg.`, `pr.`) and unit number.
2. **English inventory.** Every `<p>` of every article container (`div4`, and a `div3` with no `div4`: I q.71, q.72 and the I-II prologue), with its source id, its bold marker (`Objection N:`/`Objection N.`, `On the contrary,`, `I answer that,`, `Reply to Objection N:`), and any unbold opening of the forms the reviews found: "On the contrary" with or without a comma, "The contrary, however", "I answer that" without a comma, "I answer with", "Reply OBJ N", "Replies OBJ", "OBJ N.", and a bare "Further,". Prose replies ("This suffices for the Reply to the Second Objection", "The reply to the third objection is clear…") are recognised by an ordinal near "objection" or "argument" and a reply word.
3. **Candidates.** An article is a candidate when the strict English inventory (bold markers only) differs from the Latin in any of: argument numbers (not exactly 1..n), the number of sed contras, the number of determinations, the set of reply numbers, a Latin general reply, or an objection after the determination. That gives 353. With a looser English reading (unbold canonical openings and "Reply OBJ" counted as markers) the count is 248. Sol's 263 lies between, and Sol's scripts are on Carter's Mac, so the two lists could not be compared item by item. Every Sol finding about the core parts falls inside the 353 and is cited by its finding ID in the table.
4. **Classification.** For every Latin reply with no bold English counterpart, a locator found the English paragraph naming its target. Its matches were spot-checked, and every case it could not place (53) was read by hand against the Latin unit. Every structural difference (arguments, sed contras, determinations, article boundaries: 91 cases) was read by hand. Replies to the sed contra were recorded in every core article, candidate or not, because the Leonine numbers them after the objections (ad 4 when there are three arguments; A-017, C-29).
5. **Print check.** Each source error and omission was located in the printed volume and its markers listed, to decide whether the defect is CCEL's (the print is right) or the translators' (the print has it too). For the 36 markers that are only unbolded, the print's words were checked for five; bolding is markup, which OCR cannot show.

## 4. Results by class

| Class | Meaning | Findings | Articles (most serious) |
|---|---|---:|---:|
| prose or joint reply | The Latin's reply exists in the English but without a bold marker: an unmarked paragraph, a joint reply ("the First and Second Objections"), a reply sentence inside another part's paragraph, a general reply, or a reply to the sed contra | 298 | 271 |
| legitimate variant | The English differs from the Leonine as the translation itself does: a second or third sed contra set as its own paragraph or kept in one; a sed contra the translators number as an objection because Aquinas answers it ("Objection 4: On the contrary"); units from the translators' base text that the Leonine lacks or prints only in its apparatus (flag `not-in-leonine`) | 53 | 9 |
| source error | A correction is needed. CCEL's (61): unbolded or unrecognised markers (36 unbolded, 8 "Reply OBJ"/"OBJ"), wrong argument or reply numbers (10), a reply labelled as an objection, three divs holding two articles, a duplicated sed contra, a determination opening inside the sed contra's paragraph, the shifted numbering in I q.76 a.3. The print's own (2): Nicolai's supplied reply and an editor's note (C-04) | 63 | 62 |
| omission | Text in the Latin that is not in our English: 10 CCEL's (the print has it), 2 the translators' | 12 | 11 |

Thirteen more findings fall outside the 353: six replies to the sed contra in articles whose markers agree with the Latin, and the seven paragraphs of III q.26 a.2's editorial section. The Supplement adds 10 source errors (section 7).

## 5. Source errors and omissions

Each has an entry in the corrections file. "Print" names the volume key from section 2.

| Article | What | Latin | Print | Whose |
|---|---|---|---|---|
| I q.76 a.3 | objection 3 (the embryo argument) missing; the source's "Objection 3" is objection 4 | arg. 3 [CT 31534], arg. 4 [CT 31535] | dom2-v4 p. 35 has Obj. 3 | CCEL |
| I q.80 a.2 | reply 3 missing | ad 3 [CT 31844] | dom2-v4 p. 126 | CCEL |
| I q.89 a.3 | second sed contra missing | s. c. 2 [CT 32200] | dom2-v4 p. 243 | CCEL |
| I q.108 a.8 | the determination opens inside the sed contra's paragraph (`-p5`) | co. [CT 32988] | dom2-v5 | CCEL |
| I q.112 a.2 | first half of reply 1 and its label missing; the second half survives as `-p8` | ad 1 [CT 33110] | dom2-v5 p. 119 | CCEL |
| I q.117 a.2 | the end of the sed contra and the opening of the determination lost inside `-p5` | s. c. [CT 33331], co. [CT 33332] | dom2-v5 p. 180 | CCEL |
| I-II q.4 a.4 | reply 1 missing | ad 1 [CT 33635] | dom2-v6 p. 58 | CCEL |
| I-II q.20 a.6 | sed contra printed twice (`-p5`, `-p6`) | s. c. [CT 34477] | dom2-v6 (once) | CCEL |
| I-II q.29 a.3 | replies 2 and 3 missing | ad 2, ad 3 [CT 34772, 34773] | dom2-v6 p. 343 | CCEL |
| I-II q.40 a.1, q.81 a.3; II-II q.41 a.1, q.79 a.3; III q.50 a.3, q.79 a.4 | reply with the wrong number (A-015) | see table | print numbers them as the Latin does | CCEL |
| II-II q.36 a.2, q.26 a.11; III q.10 a.2 | objection with the wrong number (A-015) | see table | as the Latin | CCEL |
| II-II q.4 a.8 | third objection unlabelled (a bare "Further,") | arg. 3 | dom2-v9 "Obj. 3." | CCEL |
| II-II q.98 a.3 | "OBJ 2." not recognised | arg. 2 | dom2-v11 "Obj. 2." | CCEL |
| 7 paragraphs opening "Reply OBJ N" / "Replies OBJ" (A-015) | the print's "Reply Obj. N is clear …" (no period after the number) left unconverted | see table | dom2-v4, v5, v8 | CCEL |
| II-II q.172 a.1 | reply 2 labelled "Objection 2" (A-013) | ad 2 | dom2-v14 "Reply Obj. 2." | CCEL |
| II-II q.64 a.7, q.66 a.5, q.123 a.10 | each div also holds the next article (C-07, A-003) | a. 8, a. 6, a. 11 | each has its own heading in print | CCEL |
| 25 sed contras and 11 determinations | the opening is printed but not bolded: "On the contrary is the authority of …", "The contrary, however …", "I answer that As …", "I answer with Augustine" (A-014, A-016, B-001) | see table | words as printed (5 checked) | CCEL (markup) |
| I-II q.102 a.6 | reply 10 "supplied by Nicolai" (A-019): flagged `editor-supplied` | no ad 10 in the Leonine | dom2-v8, with the note | translators' |
| III q.26 a.2 | "St. Thomas and the Immaculate Conception (editorial note)", seven paragraphs appended to reply 3 (A-019): flagged `editorial` | none | the 1926 printing sets it as front matter of III QQ. 27–59 | the edition's |
| III q.22 a.2 | the editor's note (`editorial`) and a reply 3 "some editions give" (`not-in-leonine`, a variant) | no ad 3 | dom2-v15, with the note | translators' |
| III q.55 a.6 | objection 5 "wanting in the older codices and in the text of the Leonine edition, which, however, gives it in a note": a manuscript variant, flagged `not-in-leonine` (a variant, not editorial); the Leonine prints ad 5 [CT 49380] | no arg. 5 | dom2-v16, with the note | translators' base text |
| III q.57 a.4 | objection 2 and reply 2 "omitted in the Leonine edition as not being in the original manuscript"; the 1926 printing omits them too (it goes Obj. 1, 3, 4, 5), so CCEL's later printing restored them: flagged `not-in-leonine` | no arg. 2 for them | dom2-v16 | a later printing |
| II-II q.182 a.4 | sed contra missing | s. c. [CT 46231] | absent from dom2-v14 and the London 1922 issue | translators' |
| II-II q.20 a.3 | the general reply "Et per hoc patet responsio ad obiecta" not translated | ad arg. | absent from dom2-v9 | translators' |

Also noted, but outside R7's structural scope: the translators' 19 sentence-level notes on Leonine readings ("The words in brackets are omitted in the Leonine edition", II-II q.87 a.2, q.145 a.1, q.153 a.5; III q.75 a.4, q.84 a.2, q.86 a.6, q.88 a.1; Suppl. q.34 a.4; and others), which mark words the Leonine lacks inside a unit whose structure agrees.

Facts for 1.7 found on the way (they are in the corrections file, so 1.7's walk is right whichever way it reads markers):

- Comma-less unbold openings are more common than the reviews found: 19 sed contras open "On the contrary is/stands the authority of …" and 4 determinations "I answer that As …". 1.7's list of exact canonical openings has only "On the contrary," and "I answer that," with commas.
- Twelve paragraphs carry "On the contrary," inside prose (for example `FP_Q39_A6-p6`, `FS_Q89_A1-p9`). Today's regex splits them as sed contras. A paragraph walk does not, and only I q.108 a.8 has a real part opening inside a paragraph.
- In 19 core articles the translators print the sed contra arguments as further objections: 26 paragraphs opening "Objection N: On the contrary, …", "Objection N: On the other hand, …" or "Objection N: Further, …". The Supplement has 10 more articles in the "On the contrary" form. Against the Latin each is a sed contra; the translators number it as an objection because Aquinas answers it. In two of them Aquinas grants the argument instead of answering it ("Quartum concedimus", II-II q.123 a.12 and q.136 a.5). See question 1 in section 8.

## 6. Omitted units: where each can come from

TheoCorpus makes no translation of its own. For each unit below, the proposed edition is an existing printed English text. **Carter approves the edition for each unit.** No recovered text is in this repository yet: 1.7 vendors it into an override file.

| Unit | Latin | Proposed edition | Page | Scan | Alternative |
|---|---|---|---|---|---|
| I q.76 a.3 obj. 3 | arg. 3 [CT 31534] | Dominican translation, 2nd ed., Part I QQ. 75–102 (1922) | 35 | [leaf 47](https://archive.org/details/summatheologicao0004thom/page/n47) | — |
| I q.80 a.2 ad 3 | ad 3 [CT 31844] | same volume | 126 | [leaf 138](https://archive.org/details/summatheologicao0004thom/page/n138) | — |
| I q.89 a.3 s.c. 2 | s. c. 2 [CT 32200] | same volume | 243 | [leaf 255](https://archive.org/details/summatheologicao0004thom/page/n255) | summatheologi04thom (same edition), p. 243 |
| I q.112 a.2 ad 1 (first half) | ad 1 [CT 33110] | 2nd ed., Part I QQ. 103–119 (1922) | 119 | [leaf 131](https://archive.org/details/summatheologicao0005thom/page/n131) | — |
| I q.117 a.2, end of s.c. and opening of co. | s. c. [CT 33331], co. [CT 33332] | same volume | 180 | [leaf 192](https://archive.org/details/summatheologicao0005thom/page/n192) | — |
| I-II q.4 a.4 ad 1 | ad 1 [CT 33635] | 2nd ed., I-II QQ. 1–48 (1927) | 58 | [leaf 70](https://archive.org/details/summatheologicao0006thom/page/n70) | — |
| I-II q.29 a.3 ad 2 and ad 3 | [CT 34772, 34773] | same volume | 343 | [leaf 355](https://archive.org/details/summatheologicao0006thom/page/n355) | — |
| I-II q.88 a.4 s.c. | s. c. [CT 37352] | 2nd ed., I-II QQ. 49–89 (1927) | 485 | [leaf 497](https://archive.org/details/summatheologicao0007thom/page/n497) | — |
| III q.7 a.10 s.c. | s. c. [CT 47160] | 1st ed., Part III QQ. 1–26 (1913), whose date is certain | 120 | [leaf 134](https://archive.org/details/summatheologi15thom/page/n134) | 2nd ed. copy thesummatheologi15aquiuoft, p. 127 (undated in the scan) |
| II-II q.182 a.4 s.c. | s. c. [CT 46231] | Hugh Pope, *On Prayer and the Contemplative Life* (1914), a different translator | 249 | [leaf 273](https://archive.org/details/onprayercontempl00thomuoft/page/n273) | none in the Dominican translation |
| II-II q.20 a.3 general reply | ad arg. | none found | — | — | Recommended: no recovery and no reader note, since it is a six-word formula ("Hence the replies to the objections are clear") and the article loses no argument |

Places searched for II-II q.182 a.4 beyond the Dominican printings: the London (1922) and New York (1922) issues of II-II QQ. 171–189; Rickaby's *Aquinas Ethicus* vol. II (1896), which abridges q.182 a.4 to reply 3; a web search, which found Pope's translation and Freddoso's modern translation (copyrighted, so usable only with permission); Google Books (its anonymous API quota was exhausted) and HathiTrust full-text search (it refused the request), neither of which could be searched.

Proposed rows for `datapipeline/rights_inventory.json`, in its existing format, to add in 1.7's PR once Carter approves the editions (public facts only):

```json
{"work": "Summa Theologiae: units missing from the CCEL text", "author": "Thomas Aquinas", "collection": "summa",
 "source_path": "summa/recovered_units.json",
 "edition": "Fathers of the English Dominican Province translation, Burns Oates & Washbourne: second and revised edition, Part I QQ. 75-119 (1922), I-II QQ. 1-89 (1927); first edition, Part III QQ. 1-26 (R. & T. Washbourne, 1913)",
 "translator": "Fathers of the English Dominican Province", "first_published": 1913,
 "source_url": "https://archive.org/details/summatheologicao0004thom", "status": "pd-us-pre-1931",
 "rights_holder": null, "renewal_search": null, "credit_line": null,
 "checked_by": null, "checked_on": null, "planned_for": "1.7"}
{"work": "On Prayer and the Contemplative Life (Summa Theologiae II-II qq. 179-182)", "author": "Thomas Aquinas", "collection": "summa",
 "source_path": "summa/recovered_units.json",
 "edition": "Hugh Pope, O.P., On Prayer and the Contemplative Life by S. Thomas Aquinas, R. & T. Washbourne, London, 1914",
 "translator": "Hugh Pope", "first_published": 1914,
 "source_url": "https://archive.org/details/onprayercontempl00thomuoft", "status": "pd-us-pre-1931",
 "rights_holder": null, "renewal_search": null, "credit_line": null,
 "checked_by": null, "checked_on": null, "planned_for": "1.7"}
```

## 7. The Supplement

- **Route.** The Leonine Supplement is volume 12 of the *Opera omnia* (1906), on archive.org; Corpus Thomisticum links to it and hosts no transcription. Downloads: the OCR text (5.6 MB) and the word-coordinate XML (62 MB), two requests, both HTTP 200. No route was blocked. (The 6 Oct bulk attempt that got HTTP 403 ×99 was against New Advent's English, not a Latin text.) The base text for the comparison is therefore the Leonine Supplement as printed in 1906, read through archive.org's OCR.
- **Reading order.** The OCR merges the two columns line by line and skews them. Rebuilding the column order from word coordinates gives readable running text (`l12_text.py`), but the markers are often damaged ("dicenbum", drop capitals, a missed "Praeterea"). Of 446 English articles, an automatic Latin inventory aligns 391. On 82 of them the OCR is clean and agrees with the English; it is clean and disagrees on 91 more, and most of those are OCR misses on inspection.
- **What was done.** The English side is inventoried completely: 123 of the 446 articles have irregular markers. Those whose replies the locator could not place (33 replies in 20 articles) were read in the printed English (vols. 18–21). Six are CCEL errors the print gets right (XP q.40 a.3 "Reply 11", q.41 a.1, q.52 a.1, q.71 a.14, q.77 a.4 (A-013), q.97 a.1). In six articles (XP q.26 a.2, q.33 a.2, q.58 a.4, q.71 a.10, q.87 a.3, q.96 a.12) the print, like CCEL, has no separate replies; whether the Latin has them needs the scan read by hand. The corrections file has 10 Supplement entries: the six numbering errors and the four "Reply OBJ" paragraphs, each cited to its Leonine scan image. The Leonine OCR was legible for most of these (XP q.14 a.4 and q.62 a.4 have joint "ad secundum et tertium"; q.71 a.14 has two arguments; q.41 a.1 four).
- **Gap.** A unit-by-unit verdict for the rest of the Supplement against the Latin is not complete. Reason: the only open Latin witness is a two-column 1906 scan whose OCR cannot be machine-compared reliably. Finishing means reading roughly 200 articles' units on the page images. Whether that is worth doing depends on what 3.2 decides for the Supplement (compiled after Aquinas's death, Inclusion notes): question 4 in section 8.

## 8. For 1.7: the corrections file and open questions

**How 1.7 reads `summa_corrections.json`.**

- `paragraphs` is keyed by the source's paragraph id, the same id 2.1's Summa anchor is built from (`FP_Q76_A3-p4` ⇒ `summa/FP_Q76_A3/p4`). Fields:
  - `role`: one of `objection`, `sed-contra`, `determination`, `reply`, `article-title`, `editorial`, `duplicate`. Absent where the role the source's marker gives stands.
  - `number`: the Leonine argument or sed contra number.
  - `latin_role`, `latin_number`: the Leonine role where 1.7's current design keeps the printed label instead (the translators' "Objection 4: On the contrary"; question 1 below). They do not change the role 1.7 emits.
  - `targets`: on a reply, what it answers (`obj N`, `sc N`; joint replies list several).
  - `also_answers`: a reply sentence inside another part's paragraph.
  - `holds`: further Latin units of the same part in the paragraph (a second sed contra).
  - `parts`: a part opening inside the paragraph (I q.108 a.8, anchor suffix `-2` per 2.1).
  - `move_to`: the trailing article of a two-article div (C-07).
  - `duplicate_of`; `flag` (`editorial`, `editor-supplied`, `not-in-leonine`); `source_label` (the label as printed).
  - `class` and `defect` (R7's verdict and whose defect it is); `latin` (the cited unit); `printed` (the print volume key and page); a short `note` or `source_note`.
- `articles` holds the article-level facts. `missing` lists the omitted units, each `{"unit", "missing": true, "after", "latin", "defect", "printed" | "other_edition"}`; 1.7 gives the recovered text's anchor `<div id>/recovered-<n>` (2.1). Also `reply_only` (I q.74 a.3, q.91 a.4), `unmarked_determination` (I q.68 a.2), and the three new article ids with `from_div` and `first_paragraph`.
- `print` maps the volume keys to archive.org items and edition statements.
- Paragraphs without an entry keep the role their bold marker gives.

**Questions for Carter that change 1.7's design** (also in the summary message):

1. **"Objection 4: On the contrary".** 26 paragraphs are sed contras in the Latin that the translators print and number as objections because Aquinas answers them. 1.7 now keeps the printed label and sets `voice = "rejected"`. In two (II-II q.123 a.12, q.136 a.5) Aquinas grants the argument ("Quartum concedimus"), so it is not a view he rejects. The file records the Latin role as `latin_role` and leaves `role` alone, so 1.7's current design stands until Carter decides. Recommended: keep the printed label and number; set `voice = "rejected"` except for those two; use the Latin role for citations ("sed contra" vs "obj. 4").
2. **Text lost from inside a paragraph.** In I q.117 a.2 and I q.112 a.2 the lost text is not a whole unit: it begins or ends inside a paragraph CCEL kept. 1.7 now plans recovered units as new passages (`recovered-<n>`). Recommended: restore the printed text in place inside the existing passage (D1: fixing a unit's text keeps its ID), and split I q.117 a.2's determination off as its own part (`p5-2`). Whole missing units (I q.76 a.3 obj. 3 and the rest) stay as new `recovered-<n>` passages.
3. **Units the Leonine lacks.** III q.57 a.4 objection 2 and reply 2 are in CCEL but in neither the Leonine nor the 1926 printing. III q.55 a.6 objection 5 and III q.22 a.2 reply 3 are in the print with the translators' notes saying the Leonine lacks them or gives them only in its apparatus. They are manuscript or edition variants, not editors' writing, so the file flags them `not-in-leonine`, not `editor-supplied`, and 1.7 does not exclude them automatically. Recommended: keep III q.55 a.6 objection 5 (the Leonine prints its reply, ad 5); remove III q.57 a.4's objection 2 and reply 2 and III q.22 a.2's reply 3 as text outside the Leonine, by removal entries, and then number III q.57 a.4 by the Leonine (the file records those numbers as `latin_number` and leaves the printed numbers in force until this is decided).
4. **The Supplement.** Finish reading the remaining Supplement articles against the Leonine page images, or accept the partial comparison until 3.2 decides how the Supplement is presented? Recommended: wait for 3.2.

## 9. Every candidate and its verdict

One row per finding. Class: prose-reply, variant, source-error, omission. Whose: `ccel` (the print is right) or `translators` (the print has it too). Print: the volume key, with a page where cited. Rows marked "(not a candidate)" are in articles whose markers agree with the Latin: replies to the sed contra, and III q.26 a.2's editorial section. Review ref cites the 6 Oct finding that already covered the case.

| Article | Source paragraph | Latin unit | Class | Whose | Finding | Print | Review ref |
|---|---|---|---|---|---|---|---|
| FP_Q1_A4 | FP_Q1_A4-p5 | I q. 1 a. 4 ad arg. [CT 28255] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FP_Q3_A8 | FP_Q3_A8-p5 | I q. 3 a. 8 s. c. 1 [CT 28375]; I q. 3 a. 8 s. c. 2 [CT 28376] | variant |  | 2 sed contra arguments, each its own paragraph after the first |  |  |
| FP_Q4_A2 | FP_Q4_A2-p7 | I q. 4 a. 2 ad 2 [CT 28396] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FP_Q6_A4 | FP_Q6_A4-p8 | I q. 6 a. 4 ad arg. [CT 28492] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q7_A1 | FP_Q7_A1-p8 | I q. 7 a. 1 ad 1 [CT 28499] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q12_A6 | FP_Q12_A6-p9 | I q. 12 a. 6 ad 2 [CT 28730] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q13_A4 | FP_Q13_A4-p7 | I q. 13 a. 4 ad 1 [CT 28818] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q13_A5 | FP_Q13_A5-p13 | I q. 13 a. 5 ad 4 [CT 28830] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q13_A5 | FP_Q13_A5-p5 | I q. 13 a. 5 s. c. 1 [CT 28824]; I q. 13 a. 5 s. c. 2 [CT 28825] | variant |  | 2 sed contra arguments, each its own paragraph after the first |  |  |
| FP_Q13_A10 | FP_Q13_A10-p10 | I q. 13 a. 10 ad 2 [CT 28874] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q13_A10 | FP_Q13_A10-p11 | I q. 13 a. 10 ad 4 [CT 28875] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FP_Q13_A10 | FP_Q13_A10-p12 | I q. 13 a. 10 ad 5 [CT 28876] | prose-reply |  | reply numbered 5 answers the sed contra (the Leonine numbers it ad 5) |  | A-017 |
| FP_Q13_A10 | FP_Q13_A10-p5 | I q. 13 a. 10 s. c. 1 [CT 28870]; I q. 13 a. 10 s. c. 2 [CT 28871] | variant |  | 2 sed contra arguments, each its own paragraph after the first |  |  |
| FP_Q14_A4 | FP_Q14_A4-p10 | I q. 14 a. 4 ad 3 [CT 28923] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q14_A16 | FP_Q14_A16-p10 | I q. 14 a. 16 ad 3 [CT 29018] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q16_A2 | FP_Q16_A2-p6 | I q. 16 a. 2 ad arg. [CT 29061] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q17_A1 | FP_Q17_A1-p12 | I q. 17 a. 1 ad 4 [CT 29121] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q18_A2 | FP_Q18_A2-p10 | I q. 18 a. 2 ad 3 [CT 29160] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q24_A1 | FP_Q24_A1-p10 | I q. 24 a. 1 ad 4 [CT 29472] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FP_Q24_A1 | FP_Q24_A1-p8 | I q. 24 a. 1 ad 2 [CT 29470] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q24_A2 | FP_Q24_A2-p8 | I q. 24 a. 2 ad 2 [CT 29479] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q28_A4 | FP_Q28_A4-p12 | I q. 28 a. 4 ad 5 [CT 29647] | prose-reply |  | reply numbered 5 answers the sed contra (the Leonine numbers it ad 5) |  | A-017 |
| FP_Q28_A4 | FP_Q28_A4-p6 | I q. 28 a. 4 s. c. [CT 29641] | variant |  | sed contra printed as 'Objection 5' (the translators number an answered sed contra as an objection) |  |  |
| FP_Q29_A2 | FP_Q29_A2-p11 | I q. 29 a. 2 ad 4 [CT 29669] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FP_Q29_A2 | FP_Q29_A2-p12 | I q. 29 a. 2 ad 5 [CT 29670] | prose-reply |  | reply numbered 5 answers the sed contra (the Leonine numbers it ad 5) |  | A-017 |
| FP_Q29_A2 | FP_Q29_A2-p5 | I q. 29 a. 2 s. c. 1 [CT 29663] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| FP_Q29_A2 | FP_Q29_A2-p6 | I q. 29 a. 2 s. c. 2 [CT 29664] | variant |  | sed contra printed as 'Objection 5' (the translators number an answered sed contra as an objection) |  |  |
| FP_Q31_A4 | FP_Q31_A4-p9 | I q. 31 a. 4 ad 2 [CT 29768] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q32_A3 | FP_Q32_A3-p12 | I q. 32 a. 3 ad 4 [CT 29797] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FP_Q32_A3 | FP_Q32_A3-p13 | I q. 32 a. 3 ad 5 [CT 29798] | prose-reply |  | reply numbered 5 answers the sed contra (the Leonine numbers it ad 5) |  | A-017 |
| FP_Q32_A3 | FP_Q32_A3-p5 | I q. 32 a. 3 s. c. 1 [CT 29791] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| FP_Q32_A3 | FP_Q32_A3-p6 | I q. 32 a. 3 s. c. 2 [CT 29792] | variant |  | sed contra printed as 'Objection 5' (the translators number an answered sed contra as an objection) |  |  |
| FP_Q32_A4 | FP_Q32_A4-p7 | I q. 32 a. 4 ad arg. [CT 29803] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q33_A3 | FP_Q33_A3-p10 | I q. 33 a. 3 ad 3 [CT 29830] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q39_A8 | FP_Q39_A8-p16 | I q. 39 a. 8 ad 1 [CT 30063] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q43_A8 | FP_Q43_A8-p9 | I q. 43 a. 8 ad arg. [CT 30281] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q48_A5 | FP_Q48_A5-p11 | I q. 48 a. 5 ad 4 [CT 30509] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FP_Q48_A5 | FP_Q48_A5-p6 | I q. 48 a. 5 s. c. [CT 30504] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| FP_Q52_A1 | FP_Q52_A1-p8 | I q. 52 a. 1 ad arg. [CT 30635] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q52_A2 | FP_Q52_A2-p10 | I q. 52 a. 2 ad 1 [CT 30641] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q53_A2 (not a candidate) | FP_Q53_A2-p11 | I q. 53 a. 2 ad 3 [CT 30665] | prose-reply |  | reply numbered 3 answers the sed contra (the Leonine numbers it ad 3) |  | A-017 |
| FP_Q54_A5 | FP_Q54_A5-p8 | I q. 54 a. 5 ad 1 [CT 30708] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q58_A2 | FP_Q58_A2-p10 | I q. 58 a. 2 ad 3 [CT 30820] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q58_A5 | FP_Q58_A5-p8 | I q. 58 a. 5 ad 1 [CT 30842] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q60_A2 | FP_Q60_A2-p10 | I q. 60 a. 2 ad 2 [CT 30906] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q61_A1 | FP_Q61_A1-p9 | I q. 61 a. 1 ad 3 [CT 30943] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q62_A4 | FP_Q62_A4-p12 | I q. 62 a. 4 ad 3 [CT 31000] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q63_A3 | FP_Q63_A3-p9 | I q. 63 a. 3 ad arg. [CT 31065] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q63_A9 | FP_Q63_A9-p8 | I q. 63 a. 9 ad 2 [CT 31116] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q66_A1 | FP_Q66_A1-p11 | I q. 66 a. 1 ad 4 [CT 31202] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q66_A1 | FP_Q66_A1-p12 | I q. 66 a. 1 ad 5 [CT 31203] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q66_A1 | FP_Q66_A1-p5 | I q. 66 a. 1 s. c. 1 [CT 31196]; I q. 66 a. 1 s. c. 2 [CT 31197] | variant |  | 2 sed contra arguments in one paragraph |  |  |
| FP_Q67_A1 | FP_Q67_A1-p7 | I q. 67 a. 1 ad arg. [CT 31242] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q68_A1 | FP_Q68_A1-p16 | I q. 68 a. 1 ad 2 [CT 31276] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q68_A2 | FP_Q68_A2-p6 | I q. 68 a. 2 co. [CT 31281] | source-error | ccel | determination opens 'I answer that' or 'I answer with' with no bold marker |  | A-014 |
| FP_Q74_A1 | FP_Q74_A1-p11 | I q. 74 a. 1 ad 4 [CT 31420] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FP_Q74_A1 | FP_Q74_A1-p12 | I q. 74 a. 1 ad 5 [CT 31421] | prose-reply |  | reply numbered 5 answers the sed contra (the Leonine numbers it ad 5) |  | A-017 |
| FP_Q74_A1 | FP_Q74_A1-p5 | I q. 74 a. 1 s. c. 1 [CT 31414] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| FP_Q74_A1 | FP_Q74_A1-p6 | I q. 74 a. 1 s. c. 2 [CT 31415] | variant |  | sed contra printed as 'Objection 5' (the translators number an answered sed contra as an objection) |  |  |
| FP_Q74_A2 (not a candidate) | FP_Q74_A2-p13 | I q. 74 a. 2 ad 5 [CT 31432] | prose-reply |  | reply numbered 5 answers the sed contra (the Leonine numbers it ad 5) |  | A-017 |
| FP_Q76_A1 | FP_Q76_A1-p18 | I q. 76 a. 1 ad 2 [CT 31514] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q76_A3 | FP_Q76_A3-p3 | I q. 76 a. 3 arg. 3 [CT 31534] | omission | ccel | obj 3 absent from the source (the print has it) | dom2-v4 p. 35 | A-018 |
| FP_Q76_A3 | FP_Q76_A3-p4 | I q. 76 a. 3 arg. 4 [CT 31535] | source-error | ccel | the argument the source numbers 3 is objection 4: objection 3 is missing | dom2-v4 | A-018 |
| FP_Q78_A1 | FP_Q78_A1-p10 | I q. 78 a. 1 ad 1 [CT 31678] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q80_A2 | FP_Q80_A2-p8 | I q. 80 a. 2 ad 3 [CT 31844] | omission | ccel | reply 3 absent | dom2-v4 p. 126 |  |
| FP_Q82_A5 | FP_Q82_A5-p9 | I q. 82 a. 5 ad 3 [CT 31910] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FP_Q84_A5 | FP_Q84_A5-p10 | I q. 84 a. 5 ad arg. [CT 31986] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q85_A6 | FP_Q85_A6-p8 | I q. 85 a. 6 ad 2 [CT 32064] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FP_Q85_A6 | FP_Q85_A6-p8 | I q. 85 a. 6 ad 3 [CT 32065] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FP_Q85_A7 | FP_Q85_A7-p7 | I q. 85 a. 7 ad 1 [CT 32071] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q85_A7 | FP_Q85_A7-p7 | I q. 85 a. 7 ad 2 [CT 32072] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q86_A1 | FP_Q86_A1-p7 | I q. 86 a. 1 ad 1 [CT 32089] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FP_Q86_A3 | FP_Q86_A3-p6 | I q. 86 a. 3 ad arg. [CT 32107] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q89_A1 | FP_Q89_A1-p10 | I q. 89 a. 1 ad 2 [CT 32187] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FP_Q89_A3 | FP_Q89_A3-p4 | I q. 89 a. 3 s. c. 2 [CT 32200] | omission | ccel | sc 2 absent from the source (the print has it) | dom2-v4 p. 243 | A-018 |
| FP_Q89_A3 | FP_Q89_A3-p8 | I q. 89 a. 3 ad 3 [CT 32204] | prose-reply |  | reply numbered 3 answers the sed contra (the Leonine numbers it ad 3) |  | A-017 |
| FP_Q89_A3 | FP_Q89_A3-p9 | I q. 89 a. 3 ad 4 [CT 32205] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FP_Q90_A3 | FP_Q90_A3-p7 | I q. 90 a. 3 ad 1 [CT 32270] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q92_A2 | FP_Q92_A2-p7 | I q. 92 a. 2 ad 1 [CT 32333] | source-error | ccel | reply opens 'Reply OBJ' (the print's 'Reply Obj. N' without a period); not recognised as a reply | dom2-v4 | A-015 |
| FP_Q92_A3 | FP_Q92_A3-p10 | I q. 92 a. 3 ad 3 [CT 32343] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q93_A4 | FP_Q93_A4-p8 | I q. 93 a. 4 ad 2 [CT 32385] | source-error | ccel | reply opens 'Reply OBJ' (the print's 'Reply Obj. N' without a period); not recognised as a reply | dom2-v4 | A-015 |
| FP_Q93_A5 | FP_Q93_A5-p8 | I q. 93 a. 5 ad 1 [CT 32392] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q94_A2 | FP_Q94_A2-p9 | I q. 94 a. 2 ad 1 [CT 32449] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q96_A2 | FP_Q96_A2-p7 | I q. 96 a. 2 ad arg. [CT 32531] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q96_A4 | FP_Q96_A4-p8 | I q. 96 a. 4 ad arg. [CT 32545] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q97_A1 | FP_Q97_A1-p8 | I q. 97 a. 1 ad 1 [CT 32553] | source-error | ccel | reply opens 'Reply OBJ' (the print's 'Reply Obj. N' without a period); not recognised as a reply | dom2-v4 | A-015 |
| FP_Q97_A2 | FP_Q97_A2-p8 | I q. 97 a. 2 ad 1 [CT 32562] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q97_A4 | FP_Q97_A4-p5 | I q. 97 a. 4 s. c. 1 [CT 32578]; I q. 97 a. 4 s. c. 2 [CT 32579] | variant |  | 2 sed contra arguments in one paragraph |  |  |
| FP_Q97_A4 | FP_Q97_A4-p8 | I q. 97 a. 4 ad 1 [CT 32581] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q98_A2 | FP_Q98_A2-p6 | I q. 98 a. 2 s. c. 1 [CT 32595]; I q. 98 a. 2 s. c. 2 [CT 32596] | variant |  | 2 sed contra arguments in one paragraph |  |  |
| FP_Q99_A1 | FP_Q99_A1-p11 | I q. 99 a. 1 ad 3 [CT 32611] | source-error | ccel | reply opens 'Reply OBJ' (the print's 'Reply Obj. N' without a period); not recognised as a reply | dom2-v4 | A-015 |
| FP_Q100_A1 | FP_Q100_A1-p9 | I q. 100 a. 1 ad 3 [CT 32629] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q102_A3 | FP_Q102_A3-p7 | I q. 102 a. 3 ad arg. [CT 32683] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q102_A4 | FP_Q102_A4-p8 | I q. 102 a. 4 ad 2 [CT 32690] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q103_A4 | FP_Q103_A4-p8 | I q. 103 a. 4 ad 2 [CT 32723] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q103_A8 | FP_Q103_A8-p9 | I q. 103 a. 8 ad 2 [CT 32754] | source-error | ccel | reply opens 'Reply OBJ' (the print's 'Reply Obj. N' without a period); not recognised as a reply | dom2-v5 | A-015 |
| FP_Q105_A8 | FP_Q105_A8-p6 | I q. 105 a. 8 ad arg. [CT 32852] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q107_A2 | FP_Q107_A2-p8 | I q. 107 a. 2 ad 1 [CT 32900] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q107_A5 | FP_Q107_A5-p7 | I q. 107 a. 5 ad 1 [CT 32919] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q108_A4 | FP_Q108_A4-p7 | I q. 108 a. 4 ad arg. [CT 32951] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q108_A5 | FP_Q108_A5-p8 | I q. 108 a. 5 s. c. [CT 32958] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v5 |  |
| FP_Q108_A8 | FP_Q108_A8-p5 | I q. 108 a. 8 co. [CT 32988] | source-error | ccel | the determination opens inside the sed contra's paragraph | dom2-v5 |  |
| FP_Q112_A2 | FP_Q112_A2-p7 | I q. 112 a. 2 ad 1 [CT 33110] | omission | ccel | first half of reply 1 and its label absent; its second half survives as an unmarked paragraph | dom2-v5 p. 119 |  |
| FP_Q112_A3 | FP_Q112_A3-p9 | I q. 112 a. 3 ad 1 [CT 33120] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q113_A6 | FP_Q113_A6-p7 | I q. 113 a. 6 ad 1 [CT 33175] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q113_A7 | FP_Q113_A7-p9 | I q. 113 a. 7 ad 2 [CT 33184] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q113_A8 | FP_Q113_A8-p8 | I q. 113 a. 8 ad arg. [CT 33192] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q114_A2 | FP_Q114_A2-p9 | I q. 114 a. 2 ad 1 [CT 33207] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q114_A3 | FP_Q114_A3-p8 | I q. 114 a. 3 ad 1 [CT 33215] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q114_A5 | FP_Q114_A5-p6 | I q. 114 a. 5 ad arg. [CT 33230] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q115_A1 | FP_Q115_A1-p14 | I q. 115 a. 1 ad 2 [CT 33240] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FP_Q116_A1 | FP_Q116_A1-p9 | I q. 116 a. 1 ad 1 [CT 33293] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FP_Q116_A3 | FP_Q116_A3-p9 | I q. 116 a. 3 ad arg. [CT 33308] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FP_Q117_A2 | FP_Q117_A2-p5 | I q. 117 a. 2 s. c. [CT 33331]; I q. 117 a. 2 co. [CT 33332] | omission | ccel | the end of the sed contra and the opening of the determination are lost inside one paragraph; the print has both (not a reply-only article, as A-014 read it) | dom2-v5 p. 180 | A-014 |
| FP_Q119_A2 | FP_Q119_A2-p11 | I q. 119 a. 2 ad 3 [CT 33402] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FS_Q1_A3 | FS_Q1_A3-p6 | I-II q. 1 a. 3 co. [CT 33426] | source-error | ccel | determination opens 'I answer that' or 'I answer with' with no bold marker | dom2-v6 |  |
| FS_Q1_A8 | FS_Q1_A8-p8 | I-II q. 1 a. 8 ad arg. [CT 33467] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q3_A2 | FS_Q3_A2-p14 | I-II q. 3 a. 2 ad 5 [CT 33554] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FS_Q4_A4 | FS_Q4_A4-p6 | I-II q. 4 a. 4 ad 1 [CT 33635] | omission | ccel | reply 1 absent | dom2-v6 p. 58 |  |
| FS_Q5_A8 | FS_Q5_A8-p6 | I-II q. 5 a. 8 ad 1 [CT 33738] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FS_Q6_A8 | FS_Q6_A8-p7 | I-II q. 6 a. 8 ad 1 [CT 33803] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q7_A3 | FS_Q7_A3-p5 | I-II q. 7 a. 3 s. c. [CT 33824] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v6 |  |
| FS_Q8_A3 | FS_Q8_A3-p10 | I-II q. 8 a. 3 ad 4 [CT 33862] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q11_A2 (not a candidate) | FS_Q11_A2-p11 | I-II q. 11 a. 2 ad 4 [CT 33962] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FS_Q17_A6 | FS_Q17_A6-p10 | I-II q. 17 a. 6 ad 3 [CT 34230] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q19_A9 | FS_Q19_A9-p9 | I-II q. 19 a. 9 ad 2 [CT 34417] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q19_A10 | FS_Q19_A10-p16 | I-II q. 19 a. 10 ad 3 [CT 34427] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q19_A10 | FS_Q19_A10-p17 | I-II q. 19 a. 10 ad 4 [CT 34428] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q19_A10 | FS_Q19_A10-p18 | I-II q. 19 a. 10 ad 5 [CT 34429] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q19_A10 | FS_Q19_A10-p19 | I-II q. 19 a. 10 ad 6 [CT 34430] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q19_A10 | FS_Q19_A10-p5 | I-II q. 19 a. 10 s. c. 1 [CT 34421]; I-II q. 19 a. 10 s. c. 2 [CT 34422]; I-II q. 19 a. 10 s. c. 3 [CT 34423] | variant |  | 3 sed contra arguments, each its own paragraph after the first |  |  |
| FS_Q20_A4 | FS_Q20_A4-p10 | I-II q. 20 a. 4 ad 3 [CT 34463] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q20_A6 | FS_Q20_A6-p6 | I-II q. 20 a. 6 s. c. [CT 34477] | source-error | ccel | the sed contra is printed twice; the print has it once | dom2-v6 (once) | A-012 |
| FS_Q23_A2 | FS_Q23_A2-p9 | I-II q. 23 a. 2 ad arg. [CT 34554] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q23_A3 | FS_Q23_A3-p9 | I-II q. 23 a. 3 ad arg. [CT 34560] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q23_A4 | FS_Q23_A4-p11 | I-II q. 23 a. 4 ad arg. [CT 34566] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q24_A2 | FS_Q24_A2-p8 | I-II q. 24 a. 2 ad 1 [CT 34581] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q25_A1 | FS_Q25_A1-p11 | I-II q. 25 a. 1 ad 3 [CT 34608] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FS_Q26_A3 (not a candidate) | FS_Q26_A3-p11 | I-II q. 26 a. 3 ad 4 [CT 34658] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FS_Q26_A4 | FS_Q26_A4-p9 | I-II q. 26 a. 4 ad 2 [CT 34665] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q27_A3 | FS_Q27_A3-p10 | I-II q. 27 a. 3 ad 1 [CT 34690] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q28_A5 | FS_Q28_A5-p8 | I-II q. 28 a. 5 ad 1 [CT 34740] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q29_A3 | FS_Q29_A3-p9 | I-II q. 29 a. 3 ad 1 [CT 34771] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q29_A3 | FS_Q29_A3-p9 | I-II q. 29 a. 3 ad 2 [CT 34772] | omission | ccel | replies 2 and 3 absent | dom2-v6 p. 343 |  |
| FS_Q29_A3 | FS_Q29_A3-p9 | I-II q. 29 a. 3 ad 3 [CT 34773] | omission | ccel | replies 2 and 3 absent | dom2-v6 p. 343 |  |
| FS_Q29_A4 | FS_Q29_A4-p8 | I-II q. 29 a. 4 ad 1 [CT 34779] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q29_A5 | FS_Q29_A5-p7 | I-II q. 29 a. 5 ad 1 [CT 34787] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FS_Q31_A7 | FS_Q31_A7-p7 | I-II q. 31 a. 7 ad arg. [CT 34885] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q33_A4 | FS_Q33_A4-p9 | I-II q. 33 a. 4 ad 3 [CT 34991] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q35_A4 | FS_Q35_A4-p11 | I-II q. 35 a. 4 ad 3 [CT 35057] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q37_A3 | FS_Q37_A3-p7 | I-II q. 37 a. 3 ad arg. [CT 35149] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q38_A3 | FS_Q38_A3-p9 | I-II q. 38 a. 3 ad 3 [CT 35182] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q39_A1 | FS_Q39_A1-p8 | I-II q. 39 a. 1 ad 2 [CT 35206] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q40_A1 | FS_Q40_A1-p8 | I-II q. 40 a. 1 ad 2 [CT 35238] | source-error | ccel | reply numbered 1; the Latin and the print number it 2 | dom2-v6 | A-015 |
| FS_Q40_A6 | FS_Q40_A6-p8 | I-II q. 40 a. 6 ad 2 [CT 35278] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q40_A7 | FS_Q40_A7-p8 | I-II q. 40 a. 7 ad arg. [CT 35285] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q41_A3 | FS_Q41_A3-p9 | I-II q. 41 a. 3 ad arg. [CT 35316] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q41_A4 | FS_Q41_A4-p7 | I-II q. 41 a. 4 s. c. [CT 35322] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v6 |  |
| FS_Q42_A1 | FS_Q42_A1-p10 | I-II q. 42 a. 1 ad arg. [CT 35335] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q44_A2 | FS_Q44_A2-p8 | I-II q. 44 a. 2 ad 1 [CT 35409] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q44_A3 | FS_Q44_A3-p8 | I-II q. 44 a. 3 ad 2 [CT 35418] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q44_A4 | FS_Q44_A4-p7 | I-II q. 44 a. 4 ad 1 [CT 35425] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q46_A2 | FS_Q46_A2-p5 | I-II q. 46 a. 2 s. c. 1 [CT 35473]; I-II q. 46 a. 2 s. c. 2 [CT 35474] | variant |  | 2 sed contra arguments, each its own paragraph after the first |  |  |
| FS_Q46_A2 | FS_Q46_A2-p9 | I-II q. 46 a. 2 ad arg. [CT 35476] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q46_A7 | FS_Q46_A7-p5 | I-II q. 46 a. 7 s. c. [CT 35512] | source-error | ccel | sed contra opens 'The contrary, however' with no bold marker | dom2-v6 | C-04, B-001 |
| FS_Q47_A3 | FS_Q47_A3-p8 | I-II q. 47 a. 3 ad 1 [CT 35549] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q47_A4 | FS_Q47_A4-p8 | I-II q. 47 a. 4 ad 1 [CT 35557] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q48_A4 | FS_Q48_A4-p8 | I-II q. 48 a. 4 ad 2 [CT 35591] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q49_A2 | FS_Q49_A2-p12 | I-II q. 49 a. 2 ad 2 [CT 35608] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q51_A3 | FS_Q51_A3-p8 | I-II q. 51 a. 3 ad arg. [CT 35697] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q52_A3 | FS_Q52_A3-p8 | I-II q. 52 a. 3 ad arg. [CT 35728] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q56_A5 | FS_Q56_A5-p9 | I-II q. 56 a. 5 ad 2 [CT 35871] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q58_A2 | FS_Q58_A2-p12 | I-II q. 58 a. 2 ad 3 [CT 35949] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q60_A2 | FS_Q60_A2-p9 | I-II q. 60 a. 2 ad 1 [CT 36030] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q61_A3 | FS_Q61_A3-p8 | I-II q. 61 a. 3 ad 1 [CT 36079] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FS_Q61_A4 | FS_Q61_A4-p9 | I-II q. 61 a. 4 ad 2 [CT 36086] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q62_A4 | FS_Q62_A4-p8 | I-II q. 62 a. 4 ad 1 [CT 36128] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q63_A1 | FS_Q63_A1-p11 | I-II q. 63 a. 1 ad 1 [CT 36137] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q63_A2 | FS_Q63_A2-p7 | I-II q. 63 a. 2 ad 1 [CT 36143] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FS_Q64_A2 | FS_Q64_A2-p8 | I-II q. 64 a. 2 ad 1 [CT 36176] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q65_A1 | FS_Q65_A1-p12 | I-II q. 65 a. 1 ad 2 [CT 36201] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q66_A2 | FS_Q66_A2-p12 | I-II q. 66 a. 2 ad 3 [CT 36252] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q67_A1 | FS_Q67_A1-p10 | I-II q. 67 a. 1 ad 2 [CT 36294] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q67_A3 | FS_Q67_A3-p13 | I-II q. 67 a. 3 ad 3 [CT 36311] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q69_A3 | FS_Q69_A3-p17 | I-II q. 69 a. 3 ad 5 [CT 36437] | prose-reply |  | reply numbered 5 answers the sed contra (the Leonine numbers it ad 5) |  | A-017 |
| FS_Q69_A3 | FS_Q69_A3-p18 | I-II q. 69 a. 3 ad 6 [CT 36438] | prose-reply |  | reply numbered 6 answers the sed contra (the Leonine numbers it ad 6) |  | A-017 |
| FS_Q69_A3 | FS_Q69_A3-p6 | I-II q. 69 a. 3 s. c. 1 [CT 36430] | variant |  | sed contra printed as 'Objection 5' (the translators number an answered sed contra as an objection) |  |  |
| FS_Q69_A3 | FS_Q69_A3-p7 | I-II q. 69 a. 3 s. c. 2 [CT 36431] | variant |  | sed contra printed as 'Objection 6' (the translators number an answered sed contra as an objection) |  |  |
| FS_Q70_A3 | FS_Q70_A3-p13 | I-II q. 70 a. 3 ad 4 [CT 36472] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FS_Q70_A3 | FS_Q70_A3-p5 | I-II q. 70 a. 3 s. c. [CT 36467] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| FS_Q70_A4 | FS_Q70_A4-p10 | I-II q. 70 a. 4 ad 3 [CT 36480] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q72_A2 | FS_Q72_A2-p10 | I-II q. 72 a. 2 ad 2 [CT 36552] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q74_A5 | FS_Q74_A5-p9 | I-II q. 74 a. 5 ad 3 [CT 36732] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q74_A9 | FS_Q74_A9-p7 | I-II q. 74 a. 9 ad 1 [CT 36770] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q77_A1 | FS_Q77_A1-p10 | I-II q. 77 a. 1 ad 3 [CT 36861] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q78_A3 | FS_Q78_A3-p10 | I-II q. 78 a. 3 ad 4 [CT 36951] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FS_Q79_A4 | FS_Q79_A4-p10 | I-II q. 79 a. 4 ad 4 [CT 36995] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FS_Q79_A4 | FS_Q79_A4-p5 | I-II q. 79 a. 4 s. c. [CT 36990] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| FS_Q80_A2 | FS_Q80_A2-p11 | I-II q. 80 a. 2 ad 3 [CT 37012] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q81_A3 | FS_Q81_A3-p8 | I-II q. 81 a. 3 ad 2 [CT 37056] | source-error | ccel | reply numbered 1; the Latin and the print number it 2 | dom2-v7 | A-015 |
| FS_Q84_A2 | FS_Q84_A2-p8 | I-II q. 84 a. 2 ad 1 [CT 37160] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q85_A4 | FS_Q85_A4-p8 | I-II q. 85 a. 4 ad 1 [CT 37219] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q85_A6 | FS_Q85_A6-p11 | I-II q. 85 a. 6 ad arg. [CT 37236] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q85_A6 | FS_Q85_A6-p5 | I-II q. 85 a. 6 s. c. 1 [CT 37232]; I-II q. 85 a. 6 s. c. 2 [CT 37233]; I-II q. 85 a. 6 s. c. 3 [CT 37234] | variant |  | 3 sed contra arguments, each its own paragraph after the first |  |  |
| FS_Q87_A2 | FS_Q87_A2-p9 | I-II q. 87 a. 2 ad 3 [CT 37270] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FS_Q87_A5 | FS_Q87_A5-p9 | I-II q. 87 a. 5 ad 3 [CT 37296] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q88_A4 | FS_Q88_A4-p5 | I-II q. 88 a. 4 s. c. [CT 37352] | omission | ccel | sc 1 absent from the source (the print has it) | dom2-v7 p. 485 | B-002 |
| FS_Q89_A1 | FS_Q89_A1-p6 | I-II q. 89 a. 1 co. [CT 37379] | source-error | ccel | determination opens 'I answer that' or 'I answer with' with no bold marker | dom2-v7 |  |
| FS_Q89_A5 | FS_Q89_A5-p8 | I-II q. 89 a. 5 ad 2 [CT 37415] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q93_A4 | FS_Q93_A4-p10 | I-II q. 93 a. 4 ad 4 [CT 37561] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FS_Q93_A4 | FS_Q93_A4-p9 | I-II q. 93 a. 4 ad 3 [CT 37560] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q94_A1 | FS_Q94_A1-p11 | I-II q. 94 a. 1 ad 4 [CT 37587] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q95_A3 | FS_Q95_A3-p9 | I-II q. 95 a. 3 ad arg. [CT 37653] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q95_A4 | FS_Q95_A4-p12 | I-II q. 95 a. 4 ad 2 [CT 37661] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q97_A2 | FS_Q97_A2-p8 | I-II q. 97 a. 2 ad 3 [CT 37727] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| FS_Q99_A5 | FS_Q99_A5-p13 | I-II q. 99 a. 5 ad 2 [CT 37835] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q100_A1 | FS_Q100_A1-p8 | I-II q. 100 a. 1 ad arg. [CT 37850] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| FS_Q100_A2 | FS_Q100_A2-p10 | I-II q. 100 a. 2 ad 3 [CT 37858] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q101_A2 | FS_Q101_A2-p13 | I-II q. 101 a. 2 ad 4 [CT 37971] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q102_A5 | FS_Q102_A5-p39 | I-II q. 102 a. 5 ad 8 [CT 38080] | source-error | ccel | reply opens 'Reply OBJ' (the print's 'Reply Obj. N' without a period); not recognised as a reply | dom2-v8 | A-015 |
| FS_Q102_A6 | FS_Q102_A6-p20 | I-II q. 102 a. 6 ad 3 [CT 38097] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q102_A6 | FS_Q102_A6-p33 | no Leonine unit | source-error | translators | editor-supplied: reply 10 'supplied by Nicolai'; not in the codices; the Leonine has no ad 10 | dom2-v8 | A-019 |
| FS_Q109_A10 | FS_Q109_A10-p8 | I-II q. 109 a. 10 ad 2 [CT 38442] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q110_A4 | FS_Q110_A4-p9 | I-II q. 110 a. 4 ad 2 [CT 38476] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q113_A9 | FS_Q113_A9-p8 | I-II q. 113 a. 9 ad 1 [CT 38643] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q114_A9 | FS_Q114_A9-p9 | I-II q. 114 a. 9 ad 3 [CT 38726] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| FS_Q114_A10 | FS_Q114_A10-p12 | I-II q. 114 a. 10 ad 4 [CT 38735] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| FS_Q114_A10 | FS_Q114_A10-p5 | I-II q. 114 a. 10 s. c. [CT 38730] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| SS_Q1_A1 | SS_Q1_A1-p9 | II-II q. 1 a. 1 ad 2 [CT 38744] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q1_A8 | SS_Q1_A8-p8 | II-II q. 1 a. 8 s. c. [CT 38808] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v9 |  |
| SS_Q2_A2 | SS_Q2_A2-p11 | II-II q. 2 a. 2 ad 2 [CT 38854] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q2_A2 | SS_Q2_A2-p6 | II-II q. 2 a. 2 s. c. [CT 38851] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v9 |  |
| SS_Q4_A7 | SS_Q4_A7-p10 | II-II q. 4 a. 7 ad 1 [CT 39002] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q4_A8 | SS_Q4_A8-p4 | II-II q. 4 a. 8 arg. 3 [CT 39009] | source-error | ccel | third objection has no label (a bare 'Further,'); the print labels it 'Obj. 3.' | dom2-v9 | A-015 |
| SS_Q8_A2 | SS_Q8_A2-p10 | II-II q. 8 a. 2 ad 1 [CT 39096] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q8_A7 | SS_Q8_A7-p9 | II-II q. 8 a. 7 ad 1 [CT 39134] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q9_A3 | SS_Q9_A3-p9 | II-II q. 9 a. 3 ad 2 [CT 39166] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q10_A2 | SS_Q10_A2-p8 | II-II q. 10 a. 2 ad 1 [CT 39190] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q10_A6 | SS_Q10_A6-p9 | II-II q. 10 a. 6 ad arg. [CT 39222] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q10_A9 | SS_Q10_A9-p9 | II-II q. 10 a. 9 ad 1 [CT 39246] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q10_A10 | SS_Q10_A10-p10 | II-II q. 10 a. 10 ad 1 [CT 39254] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q10_A11 | SS_Q10_A11-p8 | II-II q. 10 a. 11 ad arg. [CT 39262] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q15_A2 | SS_Q15_A2-p9 | II-II q. 15 a. 2 ad arg. [CT 39407] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q17_A3 | SS_Q17_A3-p7 | II-II q. 17 a. 3 ad arg. [CT 39461] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q17_A4 | SS_Q17_A4-p8 | II-II q. 17 a. 4 ad arg. [CT 39467] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q17_A8 | SS_Q17_A8-p8 | II-II q. 17 a. 8 ad 1 [CT 39499] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q18_A4 | SS_Q18_A4-p7 | II-II q. 18 a. 4 ad 1 [CT 39534] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q19_A2 | SS_Q19_A2-p7 | II-II q. 19 a. 2 s. c. [CT 39551] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v9 |  |
| SS_Q19_A6 | SS_Q19_A6-p9 | II-II q. 19 a. 6 ad 2 [CT 39588] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q19_A9 | SS_Q19_A9-p15 | II-II q. 19 a. 9 ad 5 [CT 39616] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q20_A2 | SS_Q20_A2-p9 | II-II q. 20 a. 2 ad 3 [CT 39659] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q20_A3 | SS_Q20_A3-p8 | II-II q. 20 a. 3 ad arg. [CT 39665] | omission | translators | the general reply 'Et per hoc patet responsio ad obiecta' is not translated | dom2-v9: absent in print too |  |
| SS_Q20_A4 | SS_Q20_A4-p9 | II-II q. 20 a. 4 ad 1 [CT 39671] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q21_A4 | SS_Q21_A4-p8 | II-II q. 21 a. 4 ad arg. [CT 39704] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q23_A2 | SS_Q23_A2-p5 | II-II q. 23 a. 2 s. c. [CT 39734] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v9 | A-016 |
| SS_Q25_A3 | SS_Q25_A3-p8 | II-II q. 25 a. 3 ad 1 [CT 39911] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q25_A4 | SS_Q25_A4-p8 | II-II q. 25 a. 4 ad 2 [CT 39920] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q25_A8 | SS_Q25_A8-p8 | II-II q. 25 a. 8 ad 1 [CT 39955] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q25_A9 | SS_Q25_A9-p8 | II-II q. 25 a. 9 ad arg. [CT 39963] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q26_A11 | SS_Q26_A11-p11 | II-II q. 26 a. 11 ad 4 [CT 40076] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q26_A11 | SS_Q26_A11-p4 | II-II q. 26 a. 11 arg. 3 [CT 40070] | source-error | ccel | third objection numbered 2 | dom2-v9 | A-015 |
| SS_Q27_A5 | SS_Q27_A5-p9 | II-II q. 27 a. 5 ad 1 [CT 40131] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q27_A7 | SS_Q27_A7-p11 | II-II q. 27 a. 7 ad 2 [CT 40146] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q29_A4 | SS_Q29_A4-p9 | II-II q. 29 a. 4 ad 2 [CT 40221] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q31_A4 | SS_Q31_A4-p9 | II-II q. 31 a. 4 ad 3 [CT 40292] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q32_A1 | SS_Q32_A1-p11 | II-II q. 32 a. 1 ad 3 [CT 40302] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q32_A6 | SS_Q32_A6-p8 | II-II q. 32 a. 6 ad arg. [CT 40345] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q32_A8 | SS_Q32_A8-p11 | II-II q. 32 a. 8 ad 4 [CT 40363] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q33_A5 | SS_Q33_A5-p9 | II-II q. 33 a. 5 ad arg. [CT 40420] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q34_A4 | SS_Q34_A4-p4 | II-II q. 34 a. 4 s. c. 1 [CT 40478]; II-II q. 34 a. 4 s. c. 2 [CT 40479] | variant |  | 2 sed contra arguments, each its own paragraph after the first |  |  |
| SS_Q34_A4 | SS_Q34_A4-p7 | II-II q. 34 a. 4 ad arg. [CT 40481] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q35_A2 | SS_Q35_A2-p7 | II-II q. 35 a. 2 ad arg. [CT 40514] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q36_A2 | SS_Q36_A2-p3 | II-II q. 36 a. 2 arg. 2 [CT 40543] | source-error | ccel | second objection numbered 1 | dom2-v9 | A-015 |
| SS_Q36_A3 | SS_Q36_A3-p8 | II-II q. 36 a. 3 ad 2 [CT 40558] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q36_A4 | SS_Q36_A4-p5 | II-II q. 36 a. 4 s. c. [CT 40563] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v9 |  |
| SS_Q37_A2 | SS_Q37_A2-p5 | II-II q. 37 a. 2 s. c. [CT 40580] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v9 |  |
| SS_Q38_A2 | SS_Q38_A2-p5 | II-II q. 38 a. 2 s. c. [CT 40599] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v9 |  |
| SS_Q39_A3 | SS_Q39_A3-p9 | II-II q. 39 a. 3 ad arg. [CT 40626] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q40_A3 | SS_Q40_A3-p9 | II-II q. 40 a. 3 ad arg. [CT 40661] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q40_A4 | SS_Q40_A4-p7 | II-II q. 40 a. 4 ad arg. [CT 40667] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q41_A1 | SS_Q41_A1-p8 | II-II q. 41 a. 1 ad 2 [CT 40675] | source-error | ccel | reply numbered 1; the Latin and the print number it 2 | dom2-v9 | A-015 |
| SS_Q43_A4 | SS_Q43_A4-p8 | II-II q. 43 a. 4 ad arg. [CT 40740] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q43_A8 | SS_Q43_A8-p9 | II-II q. 43 a. 8 ad 1 [CT 40776] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q44_A5 | SS_Q44_A5-p5 | II-II q. 44 a. 5 s. c. [CT 40819] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v9 |  |
| SS_Q44_A5 | SS_Q44_A5-p9 | II-II q. 44 a. 5 ad arg. [CT 40821] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q44_A7 | SS_Q44_A7-p8 | II-II q. 44 a. 7 ad arg. [CT 40835] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q45_A2 | SS_Q45_A2-p9 | II-II q. 45 a. 2 ad 2 [CT 40859] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q46_A2 | SS_Q46_A2-p7 | II-II q. 46 a. 2 ad 1 [CT 40909] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q47_A6 | SS_Q47_A6-p9 | II-II q. 47 a. 6 ad 2 [CT 40967] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q47_A7 | SS_Q47_A7-p8 | II-II q. 47 a. 7 ad 1 [CT 40974] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q49_A6 | SS_Q49_A6-p5 | II-II q. 49 a. 6 s. c. [CT 41105] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v10 |  |
| SS_Q49_A7 | SS_Q49_A7-p5 | II-II q. 49 a. 7 s. c. [CT 41113] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v10 |  |
| SS_Q51_A4 | SS_Q51_A4-p6 | II-II q. 51 a. 4 co. [CT 41188] | source-error | ccel | determination opens 'I answer that' or 'I answer with' with no bold marker | dom2-v10 |  |
| SS_Q56_A1 | SS_Q56_A1-p5 | II-II q. 56 a. 1 s. c. [CT 41370] | source-error | ccel | sed contra opens 'The contrary, however' with no bold marker | dom2-v10 | C-04, B-001 |
| SS_Q56_A2 | SS_Q56_A2-p5 | II-II q. 56 a. 2 s. c. [CT 41378] | source-error | ccel | sed contra opens 'The contrary, however' with no bold marker | dom2-v10 | C-04, B-001 |
| SS_Q57_A3 | SS_Q57_A3-p7 | II-II q. 57 a. 3 ad 1 [CT 41405] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q58_A2 | SS_Q58_A2-p9 | II-II q. 58 a. 2 ad 2 [CT 41437] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q58_A6 | SS_Q58_A6-p9 | II-II q. 58 a. 6 ad 1 [CT 41470] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q58_A11 | SS_Q58_A11-p8 | II-II q. 58 a. 11 ad 2 [CT 41511] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q60_A5 | SS_Q60_A5-p10 | II-II q. 60 a. 5 ad 3 [CT 41596] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q61_A3 | SS_Q61_A3-p7 | II-II q. 61 a. 3 ad arg. [CT 41633] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q62_A3 | SS_Q62_A3-p8 | II-II q. 62 a. 3 ad 1 [CT 41666] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q62_A4 | SS_Q62_A4-p8 | II-II q. 62 a. 4 ad 1 [CT 41674] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q63_A3 | SS_Q63_A3-p7 | II-II q. 63 a. 3 ad arg. [CT 41736] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q64_A7 | SS_Q64_A7-p13 | II-II q. 64 a. 8 | source-error | ccel | the div also holds SS_Q64_A8 (from SS_Q64_A7-p13, 10 paragraphs); the print gives it its own heading | dom2-v10 | C-07, A-003 |
| SS_Q66_A5 | SS_Q66_A5-p10 | II-II q. 66 a. 6 | source-error | ccel | the div also holds SS_Q66_A6 (from SS_Q66_A5-p10, 9 paragraphs); the print gives it its own heading | dom2-v10 | C-07, A-003 |
| SS_Q66_A9 | SS_Q66_A9-p6 | II-II q. 66 a. 9 ad 1 [CT 41921] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q76_A1 | SS_Q76_A1-p11 | II-II q. 76 a. 1 ad 2 [CT 42202] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q76_A2 | SS_Q76_A2-p8 | II-II q. 76 a. 2 ad arg. [CT 42211] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q76_A3 | SS_Q76_A3-p8 | II-II q. 76 a. 3 ad arg. [CT 42217] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q79_A3 | SS_Q79_A3-p8 | II-II q. 79 a. 3 ad 1 [CT 42333] | source-error | ccel | reply numbered 2; the Latin and the print number it 1 | dom2-v10 | A-015 |
| SS_Q83_A14 | SS_Q83_A14-p10 | II-II q. 83 a. 14 ad 4 [CT 42584] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| SS_Q83_A14 | SS_Q83_A14-p5 | II-II q. 83 a. 14 s. c. [CT 42579] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| SS_Q87_A1 | SS_Q87_A1-p11 | II-II q. 87 a. 1 ad 1 [CT 42708] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q87_A4 | SS_Q87_A4-p8 | II-II q. 87 a. 4 ad 1 [CT 42737] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q88_A11 | SS_Q88_A11-p16 | II-II q. 88 a. 11 ad 5 [CT 42835] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q88_A11 | SS_Q88_A11-p6 | II-II q. 88 a. 11 s. c. 1 [CT 42828]; II-II q. 88 a. 11 s. c. 2 [CT 42829] | variant |  | 2 sed contra arguments, each its own paragraph after the first |  |  |
| SS_Q89_A6 | SS_Q89_A6-p11 | II-II q. 89 a. 6 ad 2 [CT 42891] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q90_A3 | SS_Q90_A3-p8 | II-II q. 90 a. 3 ad arg. [CT 42951] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q94_A2 | SS_Q94_A2-p11 | II-II q. 94 a. 2 ad 2 [CT 43024] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q95_A5 | SS_Q95_A5-p12 | II-II q. 95 a. 5 ad 1 [CT 43083] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q95_A5 | SS_Q95_A5-p14 | II-II q. 95 a. 5 ad 3 [CT 43085] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q95_A6 | SS_Q95_A6-p10 | II-II q. 95 a. 6 ad arg. [CT 43091] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q95_A8 | SS_Q95_A8-p12 | II-II q. 95 a. 8 ad 1 [CT 43105] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q96_A4 | SS_Q96_A4-p11 | II-II q. 96 a. 4 ad 4 [CT 43140] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| SS_Q96_A4 | SS_Q96_A4-p5 | II-II q. 96 a. 4 s. c. [CT 43135] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| SS_Q98_A3 | SS_Q98_A3-p3 | II-II q. 98 a. 3 arg. 2 [CT 43194] | source-error | ccel | second objection opens 'OBJ 2.' (not recognised) | dom2-v11 | A-015 |
| SS_Q98_A4 | SS_Q98_A4-p11 | II-II q. 98 a. 4 ad 4 [CT 43209] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| SS_Q98_A4 | SS_Q98_A4-p5 | II-II q. 98 a. 4 s. c. [CT 43204] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| SS_Q106_A2 | SS_Q106_A2-p7 | II-II q. 106 a. 2 ad arg. [CT 43495] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q107_A3 | SS_Q107_A3-p12 | II-II q. 107 a. 3 ad 4 [CT 43559] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| SS_Q107_A3 | SS_Q107_A3-p5 | II-II q. 107 a. 3 s. c. [CT 43554] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| SS_Q109_A4 | SS_Q109_A4-p8 | II-II q. 109 a. 4 ad arg. [CT 43641] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q110_A2 | SS_Q110_A2-p12 | II-II q. 110 a. 2 ad arg. [CT 43656] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q111_A4 | SS_Q111_A4-p10 | II-II q. 111 a. 4 ad arg. [CT 43717] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q111_A4 | SS_Q111_A4-p5 | II-II q. 111 a. 4 s. c. 1 [CT 43713]; II-II q. 111 a. 4 s. c. 2 [CT 43714]; II-II q. 111 a. 4 s. c. 3 [CT 43715] | variant |  | 3 sed contra arguments, each its own paragraph after the first |  |  |
| SS_Q118_A2 | SS_Q118_A2-p7 | II-II q. 118 a. 2 ad 1 [CT 43868] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q121_A2 | SS_Q121_A2-p7 | II-II q. 121 a. 2 ad 1 [CT 43981] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q123_A7 | SS_Q123_A7-p7 | II-II q. 123 a. 7 ad 1 [CT 44099] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q123_A7 | SS_Q123_A7-p7 | II-II q. 123 a. 7 ad 2 [CT 44100] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q123_A9 | SS_Q123_A9-p7 | II-II q. 123 a. 9 ad arg. [CT 44114] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| SS_Q123_A10 | SS_Q123_A10-p11 | II-II q. 123 a. 11 | source-error | ccel | the div also holds SS_Q123_A11 (from SS_Q123_A10-p11, 9 paragraphs); the print gives it its own heading | dom2-v12 | C-07, A-003 |
| SS_Q123_A12 | SS_Q123_A12-p11 | II-II q. 123 a. 12 ad 4 [CT 44140] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q123_A12 | SS_Q123_A12-p12 | II-II q. 123 a. 12 ad 5 [CT 44141] | prose-reply |  | reply numbered 5 answers the sed contra (the Leonine numbers it ad 5) |  | A-017 |
| SS_Q123_A12 | SS_Q123_A12-p5 | II-II q. 123 a. 12 s. c. 1 [CT 44134] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| SS_Q123_A12 | SS_Q123_A12-p6 | II-II q. 123 a. 12 s. c. 2 [CT 44135] | variant |  | sed contra printed as 'Objection 5' (the translators number an answered sed contra as an objection) |  |  |
| SS_Q124_A4 | SS_Q124_A4-p7 | II-II q. 124 a. 4 co. [CT 44172] | source-error | ccel | determination opens 'I answer that' or 'I answer with' with no bold marker | dom2-v12 |  |
| SS_Q129_A2 | SS_Q129_A2-p6 | II-II q. 129 a. 2 co. [CT 44281] | source-error | ccel | determination opens 'I answer that' or 'I answer with' with no bold marker | dom2-v12 |  |
| SS_Q136_A5 | SS_Q136_A5-p11 | II-II q. 136 a. 5 ad 4 [CT 44527] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q136_A5 | SS_Q136_A5-p5 | II-II q. 136 a. 5 s. c. [CT 44523] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| SS_Q136_A5 | SS_Q136_A5-p9 | II-II q. 136 a. 5 ad 1 [CT 44525] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q140_A2 | SS_Q140_A2-p5 | II-II q. 140 a. 2 s. c. [CT 44607] | source-error | ccel | sed contra opens 'The contrary, however' with no bold marker | dom2-v12 | C-04, B-001 |
| SS_Q147_A4 (not a candidate) | SS_Q147_A4-p12 | II-II q. 147 a. 4 ad 5 [CT 44856] | prose-reply |  | reply numbered 5 answers the sed contra (the Leonine numbers it ad 5) |  | A-017 |
| SS_Q148_A2 | SS_Q148_A2-p10 | II-II q. 148 a. 2 ad 4 [CT 44906] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| SS_Q148_A2 | SS_Q148_A2-p5 | II-II q. 148 a. 2 s. c. [CT 44901] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| SS_Q149_A4 | SS_Q149_A4-p7 | II-II q. 149 a. 4 ad arg. [CT 44969] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q153_A3 | SS_Q153_A3-p5 | II-II q. 153 a. 3 s. c. 1 [CT 45107]; II-II q. 153 a. 3 s. c. 2 [CT 45108] | variant |  | 2 sed contra arguments, each its own paragraph after the first |  |  |
| SS_Q154_A1 | SS_Q154_A1-p9 | II-II q. 154 a. 1 co. [CT 45139] | source-error | ccel | determination opens 'I answer that' or 'I answer with' with no bold marker |  |  |
| SS_Q154_A2 | SS_Q154_A2-p8 | II-II q. 154 a. 2 s. c. 1 [CT 45152]; II-II q. 154 a. 2 s. c. 2 [CT 45153]; II-II q. 154 a. 2 s. c. 3 [CT 45154] | variant |  | 3 sed contra arguments, each its own paragraph after the first |  |  |
| SS_Q154_A4 | SS_Q154_A4-p5 | II-II q. 154 a. 4 s. c. 1 [CT 45173]; II-II q. 154 a. 4 s. c. 2 [CT 45174] | variant |  | 2 sed contra arguments, each its own paragraph after the first |  |  |
| SS_Q160_A2 | SS_Q160_A2-p11 | II-II q. 160 a. 2 ad 3 [CT 45452] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q162_A8 | SS_Q162_A8-p7 | II-II q. 162 a. 8 ad 1 [CT 45585] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| SS_Q169_A2 | SS_Q169_A2-p13 | II-II q. 169 a. 2 ad 4 [CT 45767] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| SS_Q169_A2 | SS_Q169_A2-p5 | II-II q. 169 a. 2 s. c. [CT 45762] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| SS_Q171_A5 | SS_Q171_A5-p8 | II-II q. 171 a. 5 ad arg. [CT 45825] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q172_A1 | SS_Q172_A1-p11 | II-II q. 172 a. 1 ad 2 [CT 45842] | source-error | ccel | reply labelled Objection 2 (C-04, A-013) | dom2-v14 | C-04, A-013 |
| SS_Q173_A3 | SS_Q173_A3-p13 | II-II q. 173 a. 3 ad 4 [CT 45912] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| SS_Q173_A3 | SS_Q173_A3-p5 | II-II q. 173 a. 3 s. c. [CT 45907] | variant |  | sed contra printed as 'Objection 4' (the translators number an answered sed contra as an objection) |  |  |
| SS_Q173_A4 | SS_Q173_A4-p10 | II-II q. 173 a. 4 ad arg. [CT 45918] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q182_A3 | SS_Q182_A3-p7 | II-II q. 182 a. 3 ad arg. [CT 46227] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| SS_Q182_A4 | SS_Q182_A4-p4 | II-II q. 182 a. 4 s. c. [CT 46231] | omission | translators | sc 1 absent from the source and from the print; found in Hugh Pope's 1914 translation | pope1914 p. 249 | B-002 |
| SS_Q185_A7 (not a candidate) | SS_Q185_A7-p13 | II-II q. 185 a. 7 ad 4 [CT 46399] | prose-reply |  | reply numbered 4 answers the sed contra (the Leonine numbers it ad 4) |  | A-017 |
| SS_Q188_A5 | SS_Q188_A5-p6 | II-II q. 188 a. 5 co. [CT 46609] | source-error | ccel | determination opens 'I answer that' or 'I answer with' with no bold marker | dom2-v14 |  |
| TP_Q2_A4 | TP_Q2_A4-p7 | III q. 2 a. 4 ad 1 [CT 46817] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q2_A9 | TP_Q2_A9-p10 | III q. 2 a. 9 ad 4 [CT 46862] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q2_A10 | TP_Q2_A10-p10 | III q. 2 a. 10 ad 3 [CT 46870] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q2_A11 | TP_Q2_A11-p8 | III q. 2 a. 11 ad 1 [CT 46876] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q7_A9 | TP_Q7_A9-p10 | III q. 7 a. 9 (no ad 3) | variant |  | reply 3 is in the print and not in the Leonine text (no translators' note) | dom2-v15 |  |
| TP_Q7_A10 | TP_Q7_A10-p4 | III q. 7 a. 10 s. c. [CT 47160] | omission | ccel | sc 1 absent from the source (the print has it) | dom2-v15 p. 127 | B-002 |
| TP_Q10_A2 | TP_Q10_A2-p2 | III q. 10 a. 2 arg. 1 [CT 47296] | source-error | ccel | first objection numbered 2 | dom2-v15 | A-015 |
| TP_Q11_A4 | TP_Q11_A4-p7 | III q. 11 a. 4 ad arg. [CT 47350] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| TP_Q16_A7 | TP_Q16_A7-p11 | III q. 16 a. 7 ad 3 [CT 47614] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q20_A2 | TP_Q20_A2-p13 | III q. 20 a. 2 ad 4 [CT 47791] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| TP_Q20_A2 | TP_Q20_A2-p5 | III q. 20 a. 2 s. c. 1 [CT 47784]; III q. 20 a. 2 s. c. 2 [CT 47785]; III q. 20 a. 2 s. c. 3 [CT 47786] | variant |  | 3 sed contra arguments, each its own paragraph after the first |  |  |
| TP_Q21_A4 | TP_Q21_A4-p15 | III q. 21 a. 4 ad 3 [CT 47825] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q22_A2 | TP_Q22_A2-p11 | no Leonine unit | source-error | translators | editorial: editor's note: the reply to objection 3 is wanting in the manuscripts | dom2-v15 | C-04 |
| TP_Q22_A2 | TP_Q22_A2-p12 | no Leonine unit | variant |  | not-in-leonine: 'Some editions give the following reply' | dom2-v15 | C-04 |
| TP_Q22_A2 | TP_Q22_A2-p13 | no Leonine unit | variant |  | not-in-leonine: reply 3 from 'some editions'; the Leonine has no ad 3 | dom2-v15 | C-04 |
| TP_Q22_A5 | TP_Q22_A5-p9 | III q. 22 a. 5 ad 3 [CT 47866] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q24_A3 | TP_Q24_A3-p9 | III q. 24 a. 3 ad 2 [CT 47931] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q24_A4 | TP_Q24_A4-p7 | III q. 24 a. 4 ad 1 [CT 47938] | source-error | ccel | reply opens 'Reply OBJ' (the print's 'Reply Obj. N' without a period); not recognised as a reply | dom2-v15 | A-015 |
| TP_Q25_A2 | TP_Q25_A2-p9 | III q. 25 a. 2 ad 2 [CT 47955] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| TP_Q26_A2 (not a candidate) | TP_Q26_A2-p10 | no Leonine unit | source-error | translators | editorial: the edition's section 'St. Thomas and the Immaculate Conception (editorial note)', appended to reply 3; the 1926 printing sets it as front matter of III QQ. 27-59 | dom2-v15 | C-04, A-019 |
| TP_Q26_A2 (not a candidate) | TP_Q26_A2-p11 | no Leonine unit | source-error | translators | editorial: the edition's section 'St. Thomas and the Immaculate Conception (editorial note)', appended to reply 3; the 1926 printing sets it as front matter of III QQ. 27-59 | dom2-v15 | C-04, A-019 |
| TP_Q26_A2 (not a candidate) | TP_Q26_A2-p12 | no Leonine unit | source-error | translators | editorial: the edition's section 'St. Thomas and the Immaculate Conception (editorial note)', appended to reply 3; the 1926 printing sets it as front matter of III QQ. 27-59 | dom2-v15 | C-04, A-019 |
| TP_Q26_A2 (not a candidate) | TP_Q26_A2-p13 | no Leonine unit | source-error | translators | editorial: the edition's section 'St. Thomas and the Immaculate Conception (editorial note)', appended to reply 3; the 1926 printing sets it as front matter of III QQ. 27-59 | dom2-v15 | C-04, A-019 |
| TP_Q26_A2 (not a candidate) | TP_Q26_A2-p14 | no Leonine unit | source-error | translators | editorial: the edition's section 'St. Thomas and the Immaculate Conception (editorial note)', appended to reply 3; the 1926 printing sets it as front matter of III QQ. 27-59 | dom2-v15 | C-04, A-019 |
| TP_Q26_A2 (not a candidate) | TP_Q26_A2-p15 | no Leonine unit | source-error | translators | editorial: the edition's section 'St. Thomas and the Immaculate Conception (editorial note)', appended to reply 3; the 1926 printing sets it as front matter of III QQ. 27-59 | dom2-v15 | C-04, A-019 |
| TP_Q26_A2 (not a candidate) | TP_Q26_A2-p16 | no Leonine unit | source-error | translators | editorial: the edition's section 'St. Thomas and the Immaculate Conception (editorial note)', appended to reply 3; the 1926 printing sets it as front matter of III QQ. 27-59 | dom2-v15 | C-04, A-019 |
| TP_Q31_A8 | TP_Q31_A8-p9 | III q. 31 a. 8 ad 1 [CT 48224] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q32_A3 | TP_Q32_A3-p10 | III q. 32 a. 3 ad 3 [CT 48252] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q33_A3 | TP_Q33_A3-p8 | III q. 33 a. 3 ad 2 [CT 48286] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q34_A4 | TP_Q34_A4-p8 | III q. 34 a. 4 ad 2 [CT 48327] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q37_A2 | TP_Q37_A2-p5 | III q. 37 a. 2 s. c. [CT 48481] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v16 |  |
| TP_Q37_A3 | TP_Q37_A3-p6 | III q. 37 a. 3 s. c. [CT 48490] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v16 |  |
| TP_Q37_A4 | TP_Q37_A4-p5 | III q. 37 a. 4 s. c. [CT 48499] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v16 |  |
| TP_Q38_A1 | TP_Q38_A1-p5 | III q. 38 a. 1 s. c. [CT 48508] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v16 |  |
| TP_Q41_A4 | TP_Q41_A4-p9 | III q. 41 a. 4 s. c. [CT 48691] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v16 |  |
| TP_Q44_A1 | TP_Q44_A1-p7 | III q. 44 a. 1 co. [CT 48772] | source-error | ccel | determination opens 'I answer that' or 'I answer with' with no bold marker | dom2-v16 | A-016 |
| TP_Q45_A3 | TP_Q45_A3-p6 | III q. 45 a. 3 s. c. [CT 48826] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v16 |  |
| TP_Q45_A4 | TP_Q45_A4-p6 | III q. 45 a. 4 s. c. [CT 48836] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v16 |  |
| TP_Q50_A3 | TP_Q50_A3-p10 | III q. 50 a. 3 ad 3 [CT 49131] | source-error | ccel | reply numbered 2; the Latin and the print number it 3 | dom2-v16 | A-015 |
| TP_Q52_A1 | TP_Q52_A1-p6 | III q. 52 a. 1 co. [CT 49197] | source-error | ccel | determination opens 'I answer that' or 'I answer with' with no bold marker | dom2-v16 |  |
| TP_Q53_A3 | TP_Q53_A3-p8 | III q. 53 a. 3 ad 1 [CT 49283] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q55_A6 | TP_Q55_A6-p6 | no Leonine unit | variant |  | not-in-leonine: objection 5, 'wanting in the older codices, and in the text of the Leonine edition', which gives it in a note from a later codex; the Leonine prints ad 5 (CT 49380) | dom2-v16 | C-04 |
| TP_Q55_A6 | TP_Q55_A6-p7 | no Leonine unit | variant |  | not-in-leonine: continuation of objection 5 (a manuscript variant the Leonine gives in a note) | dom2-v16 | C-04 |
| TP_Q57_A4 | TP_Q57_A4-p11 | no Leonine unit | variant |  | not-in-leonine: reply 2 to that objection | dom2-v16 | C-04 |
| TP_Q57_A4 | TP_Q57_A4-p12 | no Leonine unit | variant |  | not-in-leonine: continuation of reply 2 | dom2-v16 | C-04 |
| TP_Q57_A4 | TP_Q57_A4-p3 | no Leonine unit | variant |  | not-in-leonine: objection 2, 'omitted in the Leonine edition as not being in the original manuscript'; absent from the 1926 printing | dom2-v16 | C-04 |
| TP_Q57_A4 | TP_Q57_A4-p4 | no Leonine unit | variant |  | not-in-leonine: continuation of objection 2 | dom2-v16 | C-04 |
| TP_Q57_A4 | TP_Q57_A4-p5 | III q. 57 a. 4 arg. 2-4, ad 2-4 | variant |  | objections and replies 3-5 are the Leonine's 2-4 (recorded as latin_number; the printed numbers stand) |  |  |
| TP_Q64_A3 | TP_Q64_A3-p9 | III q. 64 a. 3 ad 1 [CT 49763] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| TP_Q65_A1 | TP_Q65_A1-p21 | III q. 65 a. 1 ad 6 [CT 49835] | prose-reply |  | reply numbered 6 answers the sed contra (the Leonine numbers it ad 6) |  | A-017 |
| TP_Q65_A1 | TP_Q65_A1-p22 | III q. 65 a. 1 ad 7 [CT 49836] | prose-reply |  | reply numbered 7 answers the sed contra (the Leonine numbers it ad 7) |  | A-017 |
| TP_Q65_A1 | TP_Q65_A1-p23 | III q. 65 a. 1 ad 8 [CT 49837] | prose-reply |  | reply numbered 8 answers the sed contra (the Leonine numbers it ad 8) |  | A-017 |
| TP_Q65_A1 | TP_Q65_A1-p7 | III q. 65 a. 1 s. c. 1 [CT 49826] | variant |  | sed contra printed as 'Objection 6' (the translators number an answered sed contra as an objection) |  |  |
| TP_Q65_A1 | TP_Q65_A1-p8 | III q. 65 a. 1 s. c. 2 [CT 49827] | variant |  | sed contra printed as 'Objection 7' (the translators number an answered sed contra as an objection) |  |  |
| TP_Q65_A1 | TP_Q65_A1-p9 | III q. 65 a. 1 s. c. 3 [CT 49828] | variant |  | sed contra printed as 'Objection 8' (the translators number an answered sed contra as an objection) |  |  |
| TP_Q66_A8 | TP_Q66_A8-p6 | III q. 66 a. 8 co. [CT 49945] | source-error | ccel | determination opens 'I answer that' or 'I answer with' with no bold marker | dom2-v17 |  |
| TP_Q72_A3 | TP_Q72_A3-p6 | III q. 72 a. 3 ad 1 [CT 50338] | prose-reply |  | reply given as a sentence inside the preceding part's paragraph |  |  |
| TP_Q73_A6 | TP_Q73_A6-p8 | III q. 73 a. 6 ad arg. [CT 50463] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| TP_Q75_A5 | TP_Q75_A5-p10 | III q. 75 a. 5 ad 3 [CT 50576] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q79_A4 | TP_Q79_A4-p9 | III q. 79 a. 4 ad 2 [CT 50838] | source-error | ccel | reply numbered 1; the Latin and the print number it 2 | dom2-v17 | A-015 |
| TP_Q83_A2 | TP_Q83_A2-p7 | III q. 83 a. 2 s. c. [CT 51117] | source-error | ccel | sed contra opens 'On the contrary' with no bold marker | dom2-v17 |  |
| TP_Q86_A6 | TP_Q86_A6-p10 | III q. 86 a. 6 ad 4 [CT 51403] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q88_A1 | TP_Q88_A1-p6 | III q. 88 a. 1 s. c. 1 [CT 51442]; III q. 88 a. 1 s. c. 2 [CT 51443] | variant |  | 2 sed contra arguments, each its own paragraph after the first |  |  |
| TP_Q88_A4 | TP_Q88_A4-p8 | III q. 88 a. 4 ad 1 [CT 51470] | prose-reply |  | reply given as an unmarked paragraph (joint) |  |  |
| TP_Q89_A2 | TP_Q89_A2-p10 | III q. 89 a. 2 ad 4 [CT 51488] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| TP_Q90_A2 | TP_Q90_A2-p13 | III q. 90 a. 2 ad 5 [CT 51540] | prose-reply |  | reply given as an unmarked paragraph |  |  |
| XP_Q14_A4 | XP_Q14_A4-p9 | Suppl. q. 14 a. 4 ad 2 et 3 (Leonine vol. 12, archive.org operaomniaiussui12thom, scan image 490) | source-error | ccel | joint reply opens 'Reply OBJ 2 and 3' | dom-v18 | A-015 |
| XP_Q16_A2 | XP_Q16_A2-p11 | Suppl. q. 16 a. 2 ad 4, 5 (Leonine vol. 12, archive.org operaomniaiussui12thom, scan image about 493) | source-error | ccel | reply opens 'Reply OBJ 4,5' (answers the arguments the translators number 4 and 5) | dom-v18 | A-015 |
| XP_Q40_A3 | XP_Q40_A3-p8 | Suppl. q. 40 a. 3 ad 1 (Leonine vol. 12, archive.org operaomniaiussui12thom, scan image 535) | source-error | ccel | first reply numbered 11 | dom-v19 | A-015 |
| XP_Q41_A1 | XP_Q41_A1-p3 | Suppl. q. 41 a. 1 arg. 2 (Leonine vol. 12, archive.org operaomniaiussui12thom, scan image 538) | source-error | ccel | second objection numbered 1 | dom-v19 | A-015 |
| XP_Q52_A1 | XP_Q52_A1-p7 | Suppl. q. 52 a. 1 arg. 6 (Leonine vol. 12, archive.org operaomniaiussui12thom, scan image 559) | source-error | ccel | sixth objection numbered 7 | dom-v19 | A-015 |
| XP_Q62_A4 | XP_Q62_A4-p10 | Suppl. q. 62 a. 4 ad 2 et 3 (Leonine vol. 12, archive.org operaomniaiussui12thom, scan image 587) | source-error | ccel | joint reply opens 'Reply OBJ 2 and 3' | dom-v19 | A-015 |
| XP_Q71_A14 | XP_Q71_A14-p3 | Suppl. q. 71 a. 14 arg. 2 (Leonine vol. 12, archive.org operaomniaiussui12thom, scan image 619) | source-error | ccel | second objection numbered 3 | dom-v20 | A-015 |
| XP_Q77_A4 | XP_Q77_A4-p11 | Suppl. q. 77 a. 4 ad 3 (Leonine vol. 12, archive.org operaomniaiussui12thom, scan image 635) | source-error | ccel | reply labelled Objection 3 (C-04, A-013) | dom-v20 | C-04, A-013 |
| XP_Q95_A5 | XP_Q95_A5-p15 | Suppl. q. 95 a. 5 ad 4 (Leonine vol. 12, archive.org operaomniaiussui12thom, scan image 690) | source-error | ccel | reply opens 'Reply OBJ 4' | dom-v21 | A-015 |
| XP_Q97_A1 | XP_Q97_A1-p8 | Suppl. q. 97 a. 1 ad 1 (Leonine vol. 12, archive.org operaomniaiussui12thom, scan image about 707) | source-error | ccel | first reply numbered 2 | dom-v21 |  |

## 10. Reproduction

The scripts are in the main checkout's gitignored `datapipeline/releases/local/r7/scripts/`, beside the downloads (`…/r7/downloads/`) and outputs (`…/r7/out/`), not in the repository. Run Python over downloaded files with `python3 -I`, in this order:

1. `fetch_ct.sh` (the 87 Corpus Thomisticum pages, 6 s apart), `la_inventory.py`, then `en_inventory.py summa.xml`.
2. `compare.py` (candidates; `compare_loose.py` is the looser reading), `classify.py` (locates replies), `build.py` (merges the hand verdicts, which are in the script with their reasons), then `emit.py` (this table and the corrections file).
3. Reading aids: `view.py`, `tails.py`, `pstruct.py` (the printed markers of one article in a volume's OCR), `pfind.py`.
4. Supplement: `l12_text.py` (column order from word coordinates), `l12_units2.py`, `supp_compare.py`.
