# R5. On Loving God translator trace

Research for corpus-cleanup item R5 (`docs/corpus-cleanup/P0-checks-identity-research.md`), which blocks 1.9. Done 4 Oct 2026. No production store was queried.

## Result

The vendored text is **William Harman van Allen's translation, "Saint Bernard On Loving God", Caldey Books No. 1, published at Caldey Abbey, Tenby, South Wales, 1909.** The dedication, every chapter title and the chapter openings match the 1909 scan word for word, with the few differences listed below. The trace succeeded, so 1.9 needs no replacement translation.

Published in 1909, the translation is public domain in the US as a work published before 1931. No renewal search is needed.

## Input examined

- `datapipeline/sources/medieval/on-loving-god.xml` in Carter's main checkout, sha256 `b26350f4a9b9928d021301c76bd37f441da3c8932b3118d63e9a111d54e99d92`, 109,926 bytes. Both match the spec.
- Its ThML head is as the spec says. `firstPublished`, `pubHistory`, `published`, `editorialComments` and `DC.Source` are empty, and the only provenance is the title-page line "Made available to the net by Paul Halsall" with his Fordham address.

## Sources consulted

| Candidate | Record or scan | Text examined? |
|---|---|---|
| van Allen, Caldey Abbey, Tenby, 1909 | Scan: Internet Archive [`bwb_S0-BRH-980`](https://archive.org/details/bwb_S0-BRH-980) (General Theological Seminary copy; IA's `creator` field misreads the name as "William Darman"). Catalogue: Open Library [OL20772509M](https://openlibrary.org/books/OL20772509M), from a University of Toronto (Fisher Library) MARC record: "translated by William Harman van Allen", Tenby, Caldey Abbey, 1909, xvi, 93, [3] p., general preface signed Dom Aelred Carlyle. Bibliography: Project Canterbury's [van Allen page](https://anglicanhistory.org/usa/whvanallen) lists "Saint Bernard on Loving God. Tenby: Caldey Abbey, 1909" and gives his dates as 1870 to 1931. | Yes, OCR text of the full scan |
| Marianne Caroline and Coventry Patmore, Kegan Paul 1881; 2nd ed. Burns and Oates 1884 | Scans: IA [`saintbernardlove00bernuoft`](https://archive.org/details/saintbernardlove00bernuoft) (1884, Toronto), [`OnTheLoveOfGod`](https://archive.org/details/OnTheLoveOfGod) and [`saintbernardonl01berngoog`](https://archive.org/details/saintbernardonl01berngoog) (1881) | Yes, the 1884 OCR text |
| Edmund G. Gardner, Dent and Dutton, 1915/1916 (Latin and English facing) | Open Library [OL16428819M](https://openlibrary.org/books/OL16428819M) (1916, from a BC library MARC record) and [OL18719962M](https://openlibrary.org/books/OL18719962M) (1915, Harvard record) | No. I found no open scan |
| Terence L. Connolly SJ, privately printed 1935; Spiritual Book Associates 1937; later Newman Press and Mission Press issues | Open Library [OL16419393M](https://openlibrary.org/books/OL16419393M) (1935, Columbia and Harvard records); IA [`saintbernardonlo0000bern`](https://archive.org/details/saintbernardonlo0000bern) (1937), [`saintbernardonlo0000bern_w9k3`](https://archive.org/details/saintbernardonlo0000bern_w9k3) (1943) | No. IA lends these only, and the OCR text is restricted |
| "On the Love of God", Mowbray, 1950 (IA [`bwb_C0-AJV-396`](https://archive.org/details/bwb_C0-AJV-396)) and 1982 (IA [`onloveofgoddedil0000bern`](https://archive.org/details/onloveofgoddedil0000bern)) | IA records only | No. Restricted |
| Internet Medieval Sourcebook | The IMS page `sourcebooks.fordham.edu/basis/bernard-loving.asp` returned HTTP 500 on 4 Oct 2026, and the legacy Fordham URL redirects to the site home page. The IMS index [sbook2.asp](https://sourcebooks.fordham.edu/sbook2.asp) now lists "Bernard of Clairvaux (1090-1153): The Love of God [At CCEL]" and links to CCEL. So IMS no longer carries its own copy or a stated source. | n/a |
| TAN Books, 2025 | Its [preview PDF](https://tanbooks.com/content/3361_Preview.pdf) has the same chapter titles and dedication as the vendored file and says only that it "was re-typeset from publicly available sources". | Front matter only |

The Gardner, Connolly and Mowbray texts could not be read. That does not weaken the result, because the van Allen match is positive and verbatim. Those editions also came after 1909, so none can be the earlier source of van Allen's wording.

## Side-by-side chapter titles

Vendored titles are from the `div1` `title` attributes. The van Allen column follows the 1909 contents page and chapter heads, which use title case. Square brackets mark OCR damage I corrected from the other place the title appears. Patmore's 1884 edition has only 11 chapters, ending at the resurrection chapter. The Carthusian letter and the last chapters are absent.

| Ch. | Vendored (CCEL/Halsall) | van Allen 1909 | Patmore 1884 |
|---|---|---|---|
| - | DEDICATION | Dedication | (none) |
| I | Why we should love God and the measure of that love | Why we should Love God, and the Measure of that Love | Why we ought to love God, and how we ought to love Him |
| II | On loving God. How much God deserves love from man in recognition of His gifts, both material and spiritual: and how these gifts should be cherished without neglect of the Giver | How much God deserves Love from Man in recognition of His Gifts both Material and Spiritual; and how these Gifts should be cherished without neglect of the Giver | That God has a right to the love of man because of His gifts to soul and body. How these should be confessed, and not turned against Him who gave them |
| III | What greater incentives Christians have, more than the heathen, to love God | What Greater Incentives Christians have, more than Heathen, to Love God | What motives Christians have, more than Infidels, to love God |
| IV | Of those who find comfort in the recollection of God, or are fittest for His love | Of those who find Comfort in the Recollection of God, or are fittest for His Love | For whom there is comfort in the thought of God; and who are fittest to feel love for Him |
| V | Of the Christian's debt of love, how great it is | Of the Christian's Debt of Love, how great it is | Of the obligation to love God, especially for Christians |
| VI | A brief summary | A Brief Summary | A summary of what has hitherto been said |
| VII | Of love toward God not without reward: and how the hunger of man's heart cannot be satisfied with earthly things | Of Love toward God not without Reward; and how the hunger of Man's Heart cannot be satisfied with Earthly Things | The rewards and advantage of the love of God. The heart of man is not to be satisfied by earthly things |
| VIII | Of the first degree of love: wherein man loves **God** for self's sake | Of the First Degree of Love, wherein Man loves **Self** for Self's sake | We begin by the love of self, this being for us the first degree of love |
| IX | Of the second and third degrees of love | Of the Second and Third Degrees of Love | Of the second and third degrees of love |
| X | Of the fourth degree of love: wherein man does not even love self save for God's sake | Of the Fourth Degree of Love, wherein Man does not even love Self, save for God's sake | The fourth degree of love is to love self only for God |
| XI | Of the attainment of this perfection of love only at the resurrection | Of the Attainment of this Perfection of Love only at the Resurrection | The saints will have perfect love only after the general resurrection |
| XII | Of love: out of a letter to the Carthusians | Of Love: Out of a Letter to the Carthusians | (absent) |
| XIII | Of the law of self-will and desire, of slaves and hirelings | Of the Law of Self-will and Desire; of Slaves and Hirelings | (absent) |
| XIV | Of the law of the love of sons | Of the Law of the Love of Sons | (absent) |
| XV | Of the four degrees of love, and of the blessed state of the heavenly fatherland | Of the Four Degrees of Love, and of the Blessed State of the Heavenly Fatherland | (absent) |

Fifteen of fifteen titles match van Allen in wording, apart from case, punctuation and the two differences in bold or noted below. None matches Patmore.

## Side-by-side opening sentences

Chapter I, first three sentences:

- **Vendored.** "You want me to tell you why God is to be loved and how much. I answer, the reason for loving God is God Himself; and the measure of love due to Him is immeasurable love. Is this plain?"
- **van Allen 1909.** "You want me to tell you why God is to be loved, and how much. I answer, the reason for loving God is God Himself; and the measure of love due to Him is immeasurable love. Is this plain?" One comma differs.
- **Patmore 1884.** "You wish me to explain for what reason and in what measure we should love God. I should say that God Himself is the motive of our love to Him, and that the measure of due love is to be without measure. Is this clear enough?" A different translation.

The dedication's opening sentence ("To the illustrious Lord Haimeric, ... wisheth long life in the Lord and death in the Lord.") is identical in the vendored file and the 1909 scan. The first sentence of every chapter from II to XV also matches the 1909 text, apart from punctuation.

## Differences between the vendored file and the 1909 print

These are transcription changes by Halsall or CCEL. None of them makes the text a different translation.

1. **Chapter VIII title.** 1909 reads "wherein Man loves Self for Self's sake", and the vendored file reads "loves God for self's sake". This looks like a transcription error. The chapter's own text, in both versions, supports 1909: "this is carnal love, wherewith man loves himself first and selfishly".
2. **Chapter II title.** The vendored file prefixes "On loving God." The 1909 head and contents lack it. It is probably the running title picked up by the transcriber.
3. **Spelling.** 1909 uses British spelling throughout ("Saviour" 4 times, "honour" 8, "favour" 3). The vendored file is partly Americanized ("Savior" 2, "honor" 5 against "honour" 2, "favor" 3). I could not tell whether Halsall typed from a different printing or modernized the spelling himself. I found no other printing in any catalogue.
4. **Apparatus.** 1909 numbers its paragraphs and puts scripture references in the margin. The vendored file drops the numbers and gives references inline, for example "( Luke 7.47 )". The 1909 translator's preface, the Caldey general preface and a Latin memorial dedication are not in the vendored file.

1.9 should keep the vendored wording. The plan's rules have TheoCorpus make no translations of its own, and correcting the chapter VIII title back to the 1909 reading is a question for Carter (see below).

## Bibliographic record

- **Title:** Saint Bernard On Loving God
- **Series:** Caldey Books, No. 1
- **Translator:** William Harman van Allen, S.T.D. (1870 to 1931), Rector of the Church of the Advent, Boston
- **Publisher:** Caldey Abbey, Tenby, South Wales, 1909. The translator's preface is dated "Feast of S. Bartholomew, 1909" at Veere, Netherlands.
- **Extent:** xvi, 93, [3] p.
- **Latin basis:** "The text used is chiefly that of the Patrologia" (translator's preface).
- **Records:** Open Library [OL20772509M](https://openlibrary.org/books/OL20772509M) (University of Toronto MARC); Project Canterbury [bibliography](https://anglicanhistory.org/usa/whvanallen); scan IA [`bwb_S0-BRH-980`](https://archive.org/details/bwb_S0-BRH-980).
- **Transmission:** Paul Halsall's 1990s electronic text, then CCEL (`DC.Date` Created 2000-07-09), then `https://ccel.org/ccel/b/bernard/loving_god.xml`, then the vendored file.

## Rights

- **US.** First published 1909. Works published before 1931 are public domain in the US, so the status is `pd-us-pre-1931`. The Decision log's renewal-search requirement applies only to `pd-us-non-renewal` works, so none is needed. I did not search the renewal databases.
- **UK, for information only.** Van Allen died in 1931 (Project Canterbury), so a life-plus-70 term ended at the close of 2001.
- **Transcription layer.** Halsall's and CCEL's markup and transcription add no new translated text. CCEL's condition of credit is already covered by the plan's "Sourced via CCEL.org" credit line (Decision log "Source credits").

## Draft rights-inventory entry (0.2 format)

0.2 has not merged, so this entry lives here and is not written to `datapipeline/rights_inventory.json`. The 0.2 implementer copies it in once Carter approves it.

```json
{"work": "On Loving God", "collection": "medieval", "source_path": "medieval/on-loving-god.xml",
 "edition": "Saint Bernard On Loving God, Caldey Books No. 1, Caldey Abbey, Tenby, 1909",
 "translator": "William Harman van Allen", "first_published": 1909,
 "source_url": "https://ccel.org/ccel/b/bernard/loving_god.xml", "status": "pd-us-pre-1931",
 "renewal_search": null,
 "credit_line": "Translated by William Harman van Allen (1909). Sourced via CCEL.org",
 "checked_by": "Carter", "checked_on": null}
```

`renewal_search` is null because the status is pre-1931. `checked_on` stays null until Carter confirms. If 0.2 settles on a credit line without the translator, drop the first sentence of `credit_line`; the translator still goes into the document metadata in 1.9.

## Effect on 1.9

- Set the On Loving God translator metadata to "William Harman van Allen", with edition "Caldey Abbey, Tenby, 1909". The interim "translator unknown (via Paul Halsall's Internet Medieval Sourcebook)" label is no longer needed.
- No replacement translation and no new source file. The vendored file stays.
- The spec text for R5 and 1.9 needs no factual correction. The Decision log row "On Loving God translation" still reads as the interim position. Updating it is Carter's call, so this commit leaves it alone.

## For Carter

1. **Approve the identification**: van Allen, Caldey Abbey, 1909. The evidence is 15 of 15 chapter titles and the chapter openings matching the 1909 scan.
2. **Approve the rights entry** above (`pd-us-pre-1931`, no renewal search) and its credit line, so 0.2 can copy it into `rights_inventory.json`.
3. **Update the Decision log row** "On Loving God translation" from "translator unknown" to the van Allen credit. The README forbids an implementer from editing it.
4. **Chapter VIII title.** Decide whether 1.9 should keep the vendored "loves God for self's sake" or use the 1909 print's "loves Self for Self's sake". 1909 is the translator's own printed text and agrees with the chapter's content. Changing it is a label fix only; passage IDs and anchors do not depend on labels after 2.1.
5. The NEEDS-CARTER entry for R5 (approve a replacement if the trace fails) no longer applies, because the trace succeeded.

## Answered by Carter (4 Oct 2026)

Carter approved all four: the van Allen 1909 identification, the credit line, the Decision log update, and restoring the 1909 Chapter VIII title. Recorded in `NEEDS-CARTER.md`, the plan's Decision log, and the 1.9 and 3.2 specs.
