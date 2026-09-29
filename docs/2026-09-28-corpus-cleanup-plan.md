# Corpus cleanup and expansion plan

28 September 2026. This file is the record of what was decided and verified in the planning thread of that date. It supersedes the handoff doc "TheoCorpus corpus cleanup and expansion plan" (Carter Tate, 28 Sep 2026) wherever the two disagree. GitHub issues for this work should be opened from this file.

Related files:

- `docs/research/2026-09-28-rule-1-authorship-verification.md` has the sources for every authorship and heresy claim below.
- `docs/research/2026-09-28-corpus-health-and-retrieval-audit.md` and `docs/research/2026-09-28-question-set-corpus-gap-audit.md` are the earlier audits.
- `docs/research/2026-09-28-theologians-spiritual-writers-candidates.md` lists candidate works for the theologians and spiritual writers collection, sorted by legal availability (27 CCEL ThML works, 58 Gutenberg or Internet Archive works, 37 authors needing payment or permission, 44 flagged items).

Nothing here has changed code or live data yet.

## Status

| Item | State |
|---|---|
| Inclusion rules A to H | Decided |
| Corpus defects | Verified against the live database and the vendored sources on 28 Sep |
| Collections after cleanup | Decided, except where noted |
| Theologians and spiritual writers candidates | Research done; four scope questions answered, the rest open (see Open items) |
| GitHub issues | Not opened yet |

## Inclusion rules

These decide whether a passage is in the corpus. Every current and future source must pass them.

**A. Communion when written.** A work stays only if its author was in communion with the Catholic Church when writing it. In communion means baptized or received into full communion, and not yet separated by heresy or schism. The rule judges each work by its date, not the author's whole life, so works an author wrote before a later break can stay. Three limits apply:

1. **Condemned by name.** Every work is excluded, whatever its date, when a formal act of the Holy See condemned, excommunicated or formally warned against the author by name (Origen at Constantinople II; Novatian at Cornelius's Roman synod of 251; Loisy by the Holy Office in 1908). A work that such an act condemned, prohibited, placed on the Index or formally warned against is excluded too. Formal acts of the Holy See are those of ecumenical councils, popes, Roman synods and the Roman congregations (the Holy Office, now the Dicastery for the Doctrine of the Faith, and the Index). Acts of local bishops and informal papal remarks don't count. The latest formal act governs, so a formal lifting restores the author or work (Faustina: prohibited 1959, lifted 1978; Rosmini: propositions condemned 1887, the CDF's note of 2001).
2. **Doctors.** A declared Doctor of the Church passes, whatever their communion. This admits Gregory of Narek (Armenian Church; Doctor 2015).
3. **Dates must be shown.** Only authors whose communion changed during their writing life are dated: adult converts who wrote before baptism or reception, and authors who later broke. Each such author is dated from one named standard chronology, recorded in the work registry. A work stays only when that chronology places it after baptism or reception and before any break, and standard sources don't disagree. Otherwise the work is excluded.

When an author left communion is established in this order: a formal act of the Holy See as defined in limit 1, and where none exists, the agreed testimony of the Fathers. The Gelasian Decree does not count. It is a private compilation from 519 to 553 (von Dobschütz 1912), and its list of "apocrypha" includes the saint John Cassian. Every other author, including anonymous and pseudonymous ones, is presumed to have been in communion. The presumption covers the Western Schism (1378 to 1417): those who followed a rival claimant in good faith count as in communion (Vincent Ferrer followed Avignon and is a saint). Rules B to D still apply to anonymous and pseudonymous works. Non-Christian authors are excluded. Scripture and magisterial texts are outside this rule.

**B. Forgeries.** A work whose own text claims to be written by a saint or apostle is removed when a Church judgment, or the majority of standard scholarship, identifies its writer as heterodox. Otherwise it stays, labeled "Pseudo-" plus the claimed author. Majority means most of the critical editions and major studies, not unanimity. Trullo canon 2 counts as a Church judgment because Nicaea II canon 1 confirmed Trullo's canons.

**C. Late fabrications.** A work written after about 750 under a patristic author's name is removed, whoever wrote it.

**D. Received works.** A pseudonymous work the Church has used with authority stays, labeled, even if B or C would remove it.

**E. English only in search.** Non-English passages are replaced with a public-domain or licensed English translation. If none exists, the passage stays in the reader with a note and is excluded from search.

**F. Current text only.** For law and the Catechism, only the text in force is searchable. Superseded versions are kept only as labeled, linked history.

**G. No editor-written material.** This covers essays, introductions, prefaces, elucidations, notes and bracketed comments by editors or translators, tables of contents, and translators' "Argument" summaries, in every edition. Authors' own prefaces stay (Irenaeus, Augustine's book prefaces). Quotations from Augustine's Retractations inside translators' prefaces stay, relabeled. Text that is only mislabeled stays with its label fixed. Before deleting editorial text, copy its authenticity judgments into attribution labels, except judgments this plan overrides.

**H. Attribution.** Works that stay are credited the way the Church's own texts cite them (the Catechism, magisterial footnotes, the Office of Readings), then by the Clavis Patrum Graecorum and Latinorum. Doubtful works carry a certainty label: genuine, disputed, pseudonymous or anonymous.

Two specific rules carried over from the handoff doc: CCC 2267 uses the 2018 text, and canons 111, 112, 535 and 868 show the L'Osservatore Romano English, labeled unofficial, with the Latin as the official text.

## Decision log

All decided by Carter on 28 September 2026.

| Decision | What was decided | Why |
|---|---|---|
| Forgery bar | Majority of standard scholarship, or a Church judgment | Lightfoot rejected the view that the long Ignatian recension and the Apostolic Constitutions share a heterodox compiler, so "consensus" would keep them. Carter chose the stricter outcome. |
| Test for rule B | The work's own text must claim the false author | Separates the Cohortatio, whose text never names Justin, from the Ignatian forgeries, whose greetings name Ignatius. Checked in the database and source on 28 Sep. |
| Apostolic Canons | Keep all 85, with a note that the Latin West received canons 1 to 50 through Dionysius Exiguus | Trullo canon 2 confirms all 85, Nicaea II canon 1 confirms Trullo's canons, and the 1990 Eastern code treats that body of canons as Eastern patrimony. Keeping all 85 also avoids splitting a passage at canon 51. |
| Apostolic Constitutions | Remove everything except the canons | Trullo canon 2 judges the Constitutions corrupted by heretics. |
| Cohortatio | Keep, labeled Pseudo-Justin (CPG 1083) | Two independent grounds. Its text doesn't claim Justin. And Riedweg's Marcellus attribution (1994) is one proposal, titled with a question mark; Marcellus was acquitted by Pope Julius and Serdica and never condemned by name. |
| Rule A evidence | The agreed testimony of the Fathers counts where no council or pope spoke | No ecumenical council existed before 325. For 2nd-century figures the Church's judgment reaches us only through the Fathers. |
| Rule A basis (revised later on 28 Sep) | Judge each work by whether its author was in communion when writing it, not the author's whole life. Authors condemned by name by a council, pope or Roman synod stay out entirely. Replaces the earlier person-only rule. | Recovers text written during an author's Catholic years without reopening any author the Church condemned by name. Carter weighed this against keeping the person rule and chose it knowing each work now needs a date. |
| "In communion" | Baptism or reception into full communion. A catechumen is not yet in communion. | A date the sources can establish. |
| Unknown authors | Presumed in communion | Otherwise the Didache, Diognetus, the Cloud and Pseudo-Dionysius all fail. |
| Rule A dating method | Date only authors whose communion changed while they wrote (about 20 across the corpus and candidates). One named standard chronology per author, recorded in the work registry. Exclude a work when standard sources disagree about which side of the line it falls on. | Keeps the research to one task. Errors fall toward exclusion, which protects user trust more than it costs text. Every date can be audited. Weaknesses accepted: Tertullian's chronology partly rests on how Montanist a work sounds; disputed works such as On the Pallium are lost; every new convert-author needs the check. |
| Which Church acts count for rule A limit 1 | Every formal act of the Holy See: councils, popes, Roman synods, and the Roman congregations (Holy Office/DDF, Index). Condemnations, prohibitions and formal warnings all count. The latest formal act governs; a formal lifting restores. Local bishops and informal papal praise don't count. | Most modern condemnations came through the congregations; counting only popes and councils would admit Loisy. "Latest act governs" keeps Faustina and Rosmini in. Each inclusion or exclusion cites one dated Church document. Weaknesses accepted: the Index prohibited some works for non-doctrinal reasons; its status since 1966 is contested; formal liftings are scattered and can be missed; counting warnings is a judgment call made in favour of trust. Effect: Loisy, Tyrrell and Teilhard (1962 monitum, reaffirmed 1981) out; the Provincial Letters, Maxims of the Saints, Spiritual Guide and Augustinus out; Rosmini and Faustina in. |
| Doctors of the Church | Pass whatever their communion. Gregory of Narek is in. | Declaring a Doctor requires a finding of eminent doctrine; it is the Church's strongest judgment of a writer. |
| Tatian | Out | Irenaeus, Against Heresies 1.28.1, says he left the Church after Justin's martyrdom. Eusebius, Church History 4.28-29, calls him the author of the Encratite doctrine. Under the revised rule A, the Address to the Greeks would stay only if it can be dated before his break, and its date is disputed. |
| Tertullian | Works from his Catholic years stay; works from after his break or that can't be dated go | Benedict XVI, general audience of 30 May 2007, says his rigorism led him away from communion. No council or pope condemned him by name, so the revised rule A judges each work. |
| Novatian | Out entirely | Excommunicated by name by Pope Cornelius's Roman synod in 251 (Eusebius, Church History 6.43), so limit 1 of rule A applies even to On the Trinity, written before the schism. |
| Arnobius | Out | Jerome's Chronicle says he wrote Against the Heathen before baptism, to convince a bishop of his sincerity. |
| Summa collection | Stays the Summa only. Aquinas's other works go in Theologians and spiritual writers. | Carter's choice. Open: whether the Catena Aurea comes in at all, since it is mostly quotations from the Fathers. |
| Boethius and Pseudo-Dionysius | Move to Church Fathers | Both predate the 750 line. Boethius's document ID stays frozen; only its collection changes. |
| Public domain by non-renewal | Accepted, with a renewal search recorded per work in the rights inventory (PR 0.2) | Opens mid-century translations such as the 1940 Bruce Imitation. |
| Lay and non-canonized writers | In scope if they pass rules A to H | The rules judge communion and authorship, not canonization. |
| Pre-conversion works among the candidates | Out: Chesterton's Orthodoxy (1908), Newman's Parochial and Plain Sermons, Edith Stein's pre-1922 works. Newman's Development of Christian Doctrine uses the 1878 edition he revised as a Catholic. | Consequence of the revised rule A. |
| Dante and Pascal | Dante out. Pascal's Pensées in (Trotter 1910), his Provincial Letters out. | The Divine Comedy is allegorical poetry; a line from the Inferno in results reads as teaching, and the poem puts named popes in hell. Pascal died in communion; the Provincial Letters were placed on the Index in 1657, so rule A removes them. Weaknesses accepted: popes have praised Dante highly; the Pensées leans Jansenist on grace and chunks poorly because it is fragments; its Index status is still to be checked (R1). |
| Licences | No spending in this cleanup. Revisit after the free phase ships and usage shows demand. | 85 free works are more than the pipeline can absorb soon, and licensing text for AI search is slow and often refused. Weakness accepted: Bonaventure's systematic works, Hildegard and Peter Damian stay thin, and non-magisterial writing stays mostly pre-1930. |
| Catena Aurea | In, in Theologians and spiritual writers, genre "commentary". Each quotation is attributed to the Father quoted, as "Chrysostom, quoted in Aquinas's Catena Aurea". | Carter's choice. Attributing each quotation keeps the Fathers' words from appearing under Aquinas's name. Weakness: the same Father's text may appear twice, once in his own work and once in the Catena. |
| Modern manuals and theology | All in: Tanquerey, Marmion, Scheeben (credited "after Nieremberg"), Moehler, Pohle-Preuss, Koch-Preuss, and similar public-domain works, in Theologians and spiritual writers with genre "manual" or "treatise" and the date on the card. Adaptations are credited with the adapter ("Joseph Pohle, adapted by Arthur Preuss"). | Manuals answer precise doctrinal questions the gap audit found unanswered, and their theological notes tell users how certain a statement is. Carter's condition: no manual passage may teach something against Church teaching. Weaknesses accepted: in adaptations the adapter's words are woven into the text and can't be separated under rule G; some pre-Vatican II positions were later reworded; multi-volume sets are large and mostly scans. |
| On Loving God translation | Keep, labeled "translator unknown (via Paul Halsall's Internet Medieval Sourcebook)". Trace it (R5); swap to a verified public-domain translation if the trace fails. | The vendored file credits only Halsall and every edition field is empty. It is not Patmore's 1884 translation; the chapter titles differ. |
| Two vendored papal documents missing from manifests | Add A New Hope for Lebanon (1997) and Ubicumque et Semper (2010) in PR 5.4 | Both files are vendored but absent from the manifests and the database. |
| Pre-PR fact checks | Canons 296, 360, 361 and 948, the Esther claims, and the Refutation's book contents each become a research sub-issue that must close before its adapter PR | Each is a check against a named source and matters for one PR only. |
| Genuine Ignatius letters | Separate the shorter text out of the vendored ANF volume, not Lightfoot | Same middle recension, already vendored, keeps frozen IDs, no scan. Weaknesses: older translation; the split relies on each chapter's first paragraph being the shorter version, which the coverage test must prove per chapter. |
| Storage (4.0) | Compact `chunks` with VACUUM FULL in an approved quiet window, measure, then buy Supabase Pro only if a rehearsal still exceeds about 350 MB or when V5 enrichment is scheduled. Qdrant new collection with vectors on disk if memory is tight. | Live data is about 100 MB of a 380 MB table; the rest is space left by earlier rewrites. Weaknesses: the lock blocks search and the reader for its duration (likely under a minute); Pro may only be postponed. |
| Where checks run | GitHub Actions for tests that need no sources; source checks run locally and their report is a required PR-template section | The repo is public, so Actions minutes are free; sources are gitignored. Weakness: the local checks rely on discipline. |
| Baseline eval (0.3) | The `docs/eval/` gold sets plus targeted questions, not stored user queries | Avoids sending users' queries to providers. Weakness: gold sets may miss some removals, hence the targeted questions. |
| Collection guarantee after the papal merge (5.1c) | One guaranteed slot per collection; no per-genre guarantee | Genre is a filter; per-genre slots would recreate the one-document-owns-a-slot problem. Weakness: selecting all papal genres now guarantees one papal slot, not up to three. |
| Production safety | Every PR must leave production working: publish lock first, additive migrations, Qdrant alias, filters that exclude only explicit values, expand-and-contract collection merge | See "Production stays working at every merge" in the phase plan. |
| About page | After P5, replace it with "What's in TheoCorpus and why": the collections and why, the rules in plain language, who is excluded and why with the Church act cited, translations and rights, how to report an error. Counts come from `/sources`. An early factual fix removes names not in the corpus (2.4c). | Makes the curation auditable, which is the trust argument for a public Catholic app. Weaknesses: naming excluded authors invites argument; the page must change when a rule changes, so rule-change PRs carry an About page checklist item. |
| Rights review | Done on 28 Sep; the memos are kept outside this public repo. Carter handles correspondence with rights holders. Texts already in the corpus stay in scope, and the planned Roman Curia documents and Compendiums are built as planned. TheoCorpus makes no translations of its own. | Kept private because it concerns correspondence not yet sent. |
| Source replacements | On the Incarnation moves to Robertson's NPNF translation (npnf204). The council texts now taken from papalencyclicals.net, except Trent, move to Percival (councils 1 to 7), Schroeder 1937 (8 to 18) and Schaff 1877 (Vatican I), in PR 1.2. Gaps where no public-domain translation exists (chiefly Florence's doctrinal decrees) are recorded, not filled by our own translation. | Confirmed by Carter. Public-domain editions with clear provenance. |
| Editions for planned sources | Use only public-domain editions: David Lewis and pre-1931 Stanbrook for John of the Cross and Teresa (no Peers), Lewis 1864 for the Spiritual Canticle (not CCEL's 1995 modernization), Gutenberg 13871 for Brother Lawrence (not 5657), a 1930 printing of Tanquerey. Liturgical norms in ICEL English are dropped. Each work's rights status is recorded in the rights inventory (PR 0.2) before ingestion. | |
| Manual screening | None. Manuals go in whole, like other theologians' works. | Carter's choice, 28 Sep. |
| Source credits | A small credit line (for example "Text: Libreria Editrice Vaticana" or "Sourced via CCEL.org") shown only when a passage is opened and its text is viewed, not on result cards. | Carter's choice. Rights holders expect credit; CCEL made it a condition. |
| CCEL staff descriptions | Never shown in the reader or indexed for search. | These are modern CCEL-owned blurbs, already excluded by rule G; this makes it explicit. |
| Pricing | TheoCorpus stays free. | Carter's decision. Commercial use would weaken the legal position on the copyrighted texts. |
| Group 3 additions (Roman Curia documents, Compendiums, papal law) | Start the code now, ahead of the phase order, while permission requests are pending. Each PR must still keep production working. | Carter's choice, 28 Sep. |
| OCR and scanned works (5.6c) | Use a clean typed text wherever one exists, after confirming it is the planned edition (19 of the 48 scan-only works have one; see `docs/research/2026-09-28-scan-only-works-text-sources.md`). Where the clean copy sits on a site that claims copyright on its pages (ecatholic2000.com), ask the site or use it only to check our own OCR. For the rest (23 works plus the missing parts of 6), a script strips page furniture and rejoins broken words, then a language model fixes character-level errors under hard limits (edits changing more than about 2% of a passage's words are rejected; the raw OCR is kept). Gate before ingestion: unrecognized-word rate on body text within 1 point of the clean baseline, and 20 random passages checked against the page images. Scanned passages carry a source label. One PR per work; John of the Cross (Ascent, Dark Night, Living Flame) and Teresa (Foundations, Letters, Way of Perfection) first. | OCR means software reading letters off page photographs; its output mixes in page numbers, headers, margin notes and misread letters. This approach recovers the priority works and keeps each work's cost visible. Weaknesses accepted: the model can alter wording despite the limits; the 20-passage check takes about 30 to 60 minutes per work; leftover typos show in the reader. |
| Non-English with no usable English | Keep in the reader, excluded from search, with a note | The reader should not lose text; search serves English readers. |
| Papal collections | Merge encyclicals, apostolic exhortations and papal documents into one "Papal documents" collection | One speaker. Genre becomes a filter, and the user can select one genre, several, or all. |
| Bishops' conferences | No collection yet | One document would get a guaranteed result slot in every search that selects it. Revisit when a second conference source exists. |
| Canon law amendments | Take current text from iuscangreg.it (the Pontifical Gregorian University canon law faculty's register of amendments, not a Vatican site) checked against the amending documents on vatican.va, and verify each amended canon before ingestion | The vendored source is out of date for canon 295. Corrected 28 Sep: an earlier version of this row called iuscangreg.it a Vatican register. |
| Document identity | Freeze today's 421 document IDs in a tracked registry file. Build anchors from source structure. Build the old-to-new remap tool in Phase 0 and run it in every release report. | The manifests are gitignored, regenerated by `scripts/vendor_sources.py`, and have one row per CCEL volume, not per work. Freezing keeps every reader URL. The remap tool makes release reports meaningful and tests the Phase 4 remap months early. |
| Earlier decisions kept from the handoff doc | CCC 2267 2018 text; canons 111 and 112 in unofficial English; all editorial material deleted; English only; forgeries by heretics out; heretics out even under their own name (narrowed by the revised rule A to works written outside communion and authors condemned by name); attribution by the Church's citations then the Clavis; Alexander of Lycopolis out; Cyprian's two anonymous treatises kept as anonymous; one cleanup republish before reorganizing; no LLM planning step in retrieval | See the handoff doc's decision log. |

## Corrections to the handoff doc

- `document_type` is not a column. It sits in `documents.metadata` for 16 documents.
- `translation` is not empty everywhere. The 73 Bible books have "WEB-C".
- `year` is empty for all 128 Fathers documents and for the Summa.
- The Phase 2 ordering premise was wrong. Phase 1 relabels also change IDs (for example, the Bible document ID includes the book name). The real constraint is that identity must be fixed before release reports are generated, so the identity PR moves to Phase 0.
- Canon 295 in the vendored source has only the pre-2023 text, so a parser fix can't produce the 2023 wording. The handoff doc said the problems were all in parsing.
- Canons 535 and 868 are English with only the amended paragraphs (535 §2, 868 §1 2°) in Latin.
- Quanta Cura (1864) is one "Preamble" passage and 12 passages labeled "Paragraphs 1–12", not "Preamble throughout".
- Gregory Thaumaturgus's 38 "Argument I" to "Argument XIX" passages are whole chapters, not summaries. Fix the labels and keep the text.
- The Sectional Confession fragment at position 23 is part of the Confession and goes with it. Position 24 is an Elucidation, removed under rule G.
- Irenaeus doesn't call Tatian the Encratites' founder. Eusebius does.
- Benedict XIV did not remove Clement of Alexandria from the Martyrology. His letter Postquam intelleximus (1748) declined to add him. Clement stays.
- Retrievals were 2,967 on 28 Sep, not 2,951. Counts for the republish must be read at cutover.
- The vendored Boethius is W. V. Cooper's translation (Dent, 1902), not H. R. James. The vendored On Loving God names no translator.
- There are 38 Doctors of the Church, not 37. Leo XIV declared Newman a Doctor on 1 November 2025.
- CCEL's Ascent of Mount Carmel, Dark Night and Way of Perfection are E. Allison Peers's translations, very likely under restored US copyright. Use David Lewis's translations. CCEL's Chesterton St. Thomas Aquinas (1933) is under US copyright until 2029.

## Verified corpus problems, fixes, and what users see after

Counts were measured on 28 Sep 2026 against the live database (54,568 passages, 421 documents) and the vendored sources.

### All collections

| Problem | Fix | User effect |
|---|---|---|
| Split passages repeat their parent's citation. Rows sharing a citation: Bible 495, apostolic exhortations 412, encyclicals 411, medieval 240, Catechism 98, papal documents 91, councils 1,282, Fathers 5,941, and every Summa passage. | Give each passage its own range. | A citation points at exactly the text shown. |
| Paragraphs joined with no space. Vita Consecrata has 188 joins in 86 passages. | Insert the space during normalization. | Keyword search finds both words. |
| Translator footnotes inline in at least 584 Fathers and medieval passages. | Strip note markup at ingestion. | Passages read as the author wrote them. |
| Genre, issuer and translation are missing for most documents. | Add real fields and backfill them. | Cards show translation and date. Genre and issuer filters work. |

### Councils

| Problem | Fix | User effect |
|---|---|---|
| Vatican II keeps about 443,000 of about 1,058,000 characters of source text (source includes notes). Gaudium et Spes keeps 74,319 of 216,676. Nostra Aetate 4 is 155 characters. | Group unnumbered paragraphs with the numbered section before them. | The Council's teaching, such as Nostra Aetate 4 on Jewish guilt, is findable. |
| 240 Vatican II passages start with "Cf." or "See". Nostra Aetate has stray sections 11 and 12. | Stop at the notes. | No footnote cards in results. |
| Other councils lose text inside lists and divs. Trent keeps 204,107 of about 549,814 characters. Vatican I keeps 6,053 of about 54,223. Nicaea is 4 passages. | Parse all body text. | Trent, Vatican I and the canons of Nicaea become searchable. |
| All 36 council documents have no author. | Set the council's name. | Cards name the council. |

### Papal documents

| Problem | Fix | User effect |
|---|---|---|
| Roman-numeral paragraphs treated as headings, prose after them dropped. In Dominico Agro is 224 characters, Annus Qui Hunc 2,277. | Keep the prose. | Whole documents are readable. |
| Endnotes glued to final paragraphs. Fratelli Tutti 287 is 9 passages, the later ones mostly notes. | Split notes off. | No walls of citations in results. |
| 28 passages under 20 characters, such as "146", "PAUL VI", "Eph. 1:10).". | Merge headings, drop debris. | No empty cards. |
| Quanta Cura (1864) labeled "Paragraphs 1–12" throughout. | Real paragraph labels. | Citations point to a paragraph. |
| Evangelii Gaudium, Evangelii Nuntiandi, Ineffabilis Deus, Munificentissimus Deus, three Jubilee bulls and the Syllabus of Errors filed as encyclicals. | Correct genres. | Accurate labels and filters. |

### Bible

| Problem | Fix | User effect |
|---|---|---|
| 245 verses missing, found by diffing live references against the WEB-C source. Includes Daniel 3:31-97, Daniel 13 and 14, Isaiah 55:9-13, Mark 2:28, Deuteronomy 1:5-8, 1 Kings 8:62-66, Esther 4:18-47 and 10:4-14. | Stop relying on the KJV pericope file to decide which verses exist. | Susanna, Bel and the Dragon and the Song of the Three are findable. |
| Joel has 3 chapters, Malachi 4. | Nova Vulgata numbering. | References match Church documents. |
| "Song of Solomon". | Rename to "Song of Songs". | Catholic naming. |
| Deuterocanonical books are about one passage per chapter (Sirach 58 passages for 51 chapters). | Chunk by pericope. | Focused results. |

### Canon law

| Problem | Fix | User effect |
|---|---|---|
| Glued canons: 112 in 111, 238 in 237, 689 in 688, new 1308 in 1307, new 1310 in 1309. | Split them. | "Canon 112" finds canon 112. |
| Canons 266 and 1330 missing from the database though present in the source. | Fix the parser. | Both canons findable. |
| Superseded text kept for 265, 686 §1, 694, 1308, 1310 though the source has the new text. | Keep the version the source marks new. | Users read current law. |
| 295 is pre-2023 in the source itself. 296, 360, 361 and 948 not yet verified. | Current text from iuscangreg.it, verified per canon. | Current law. |
| Latin in the English Code: 111, 579, 695, 700 in full; 535 §2 and 868 §1 2°. | Rule 6 treatment where an unofficial English exists; otherwise rule E. | Readable text with an honest label. |
| Page footer leaks into canons 123 and 694. | Strip it. Use the "n" marker to flag amended canons. | Clean canons with an "amended" badge. |

### Catechism

| Problem | Fix | User effect |
|---|---|---|
| CCC 2267 is the 1997 text ("very rare, if not practically non-existent"). | Load the 2018 text. | Current teaching on the death penalty. |
| 509 sentences in 310 passages start with lowercase "the". | Fix at source. | Clean text. |
| 29 numeric chapter labels. 496 passages are "(part)" references. | Part, Section, Chapter and Article labels. Paragraph numbers inside passages. | Readers see where each paragraph starts. |

### Summa

| Problem | Fix | User effect |
|---|---|---|
| Part I questions 71 and 72 missing. | Restore from summa.xml. | Days five and six of creation exist. |
| 21 blank passages, 3 more under 20 characters. | Remove; publication check rejects blanks. | No empty cards. |
| Citations name only the article. | Cite objection, reply and corpus. | Precise citations. |

### Church Fathers and medieval

| Problem | Fix | User effect |
|---|---|---|
| Editor material stored as author text: 73 Elucidations passages (187,682 characters), Shedd's essay (11 passages, 35,246 characters), translators' prefaces, biographical notices, tables of contents, Boethius and Imitation forewords, and bracketed editor comments such as the anti-transubstantiation note inside Gregory Thaumaturgus's Twelve Topics. | Remove at ingestion under rule G. | No editors' opinions under saints' names. |
| Every Ignatius letter lost its opening greeting. The adapter skips paragraphs before the first chapter div (source line 9621 of `apostolic fathers.xml` has the Tarsians greeting; no stored passage does). | Keep pre-chapter paragraphs. Coverage test measures other letters. | Letters open as written. |
| The 7 "Shorter and Longer Versions" documents store both versions of each chapter back to back. In the source, the first paragraph of each chapter is the shorter version. | Separate them. | No duplicate text inside passages. |
| 54 documents (3,862 passages) have authors ending in a period; others read "Tertullian: Part Fourth.", "Appendix.". | Fix authors. | Correct author labels and filters. |
| Peter of Alexandria's epistle interleaved with Balsamon and Zonaras (21 passages). Asterius Urbanus document holds only an editor's note. | Split out commentary; parse Asterius. | Only Peter's words carry his name. |
| Anselm all dated 1099. Cur Deus Homo has 27 duplicate anchors. Boethius has 68 "Introduction" labels. Bernard has 20 labels cut at 60 characters. | Correct dates (1076, 1077-78, 1098), separate books, fix labels. | Accurate dates, working reader links. |

### Non-English

| Passages | Language | Count |
|---|---|---|
| Clement, Stromata III | Latin | 33 |
| Clement, The Instructor II.10 | Latin | 4 |
| Lactantius, Divine Institutes VI and On the Workmanship of God | Latin | 5 |
| Ubi Lutetiam | Italian | 17 |

Fix under rule E.

### Product copy

The About page (`apps/web/src/components/about/AboutPage.tsx`) names Origen, John Chrysostom, Bonaventure, Hildegard and Duns Scotus, none of whom are in the corpus. Rewrite it from the actual contents.

## What the rules remove

| Rule | Removed | Passages |
|---|---|---|
| A | Origen, 3 works (condemned by name, Constantinople II) | 932 |
| A | Tertullian, 7 of 9 works: those written after his break or not datable. To His Wife (22) and On the Apparel of Women (28) provisionally stay as Catholic-era works, pending the dating research in Open items | 192 |
| A | Novatian, 2 works plus Treatises I and III inside "Treatises Attributed to Cyprian" (condemned by name, 251) | 79 + 16 |
| A | Tatian, Address to the Greeks (not datable before his break) | 44 |
| A | Arnobius, Against the Heathen (written before baptism) | 392 |
| A | Alexander of Lycopolis, a pagan Platonist (van Oort 2012) | 27 |
| B | Apostolic Constitutions except the 85 canons (Book VIII positions 35 to 43 stay) | 178 |
| B | Six forged Ignatius letters | 59 |
| B | Long recension text inside the 7 "Shorter and Longer" documents | part of 97 |
| B | Sectional Confession of Faith, by Apollinaris (CPG 3645; Caspari 1879, Lietzmann 1904) | 24 (positions 0 to 23) |
| C | Pfaff's Irenaeus fragments XXXVI to XXXIX (Harnack 1900) | 4 |
| C | Four medieval Latin Ignatius letters (CPG 1028) | 4 |
| G | Editorial material, whole passages | about 120 |

Rules A to C remove about 1,951 whole passages plus the long-recension text. Rule G removes about 120 more. On 28 Sep, 50 of 2,967 saved retrievals and no bookmarks pointed at passages to be removed.

Labels for works that stay:

- Pseudo-Justin: Hortatory Address to the Greeks (CPG 1083), On the Sole Government of God (1084), Discourse to the Greeks (1082). On the Resurrection (1081): authorship disputed; Heimgartner 2001 assigns it to Athenagoras.
- Gregory Thaumaturgus: Twelve Topics (1772) and the homilies (1775-1777) not his; On the Soul, to Tatian (1773) disputed.
- Hippolytus: Refutation of All Heresies (CPG 1899) authorship disputed; appendix pieces pseudonymous. Check whether the Refutation's book contents are authorial before removing them under rule G.
- Anonymous: the Didache, Diognetus (chapters 11 and 12 a later addition), the Muratorian fragment, On the Glory of Martyrdom, Exhortation to Repentance, Canons of Hippolytus (Egypt, about 336 to 340).
- Pseudo-Barnabas for the Epistle of Barnabas. Hegemonius for the Acts of Archelaus.
- Doubtful: Methodius's Oration on the Palms and the homily-on-the-Cross fragments, the Lactantius Poem on the Passion, Pamphilus's Exposition of Acts.
- Notes: the Martyrdom of Ignatius is a legendary account; Cyprian's Seventh Council of Carthage rule on rebaptism was not adopted by the Church; the Summa Supplement (4,084 passages) and its appendix (82) were compiled after Aquinas's death.
- Victorinus of Pettau: label the original and Jerome's recension separately.
- Commodian, Lactantius, Victorinus and Clement of Alexandria stay. No council or pope condemned them by name, they wrote after baptism, and rule A doesn't count the Gelasian Decree. Arnobius goes: he wrote before baptism.

## Collections after cleanup and additions

One collection per kind of speaker, with genre as a filter inside it.

| Collection | Holds | Change |
|---|---|---|
| Bible | Scripture, all verses, Nova Vulgata numbering | Fixes only |
| Catechism | CCC, then the Compendium and the Roman Catechism of Trent | Adds catechisms |
| Councils | Ecumenical councils, full text | Fixes only |
| Papal documents | Encyclicals, exhortations, apostolic letters, constitutions, bulls, motu proprios; genre filter with one, several or all selectable | Merges three collections |
| Roman Curia | CDF/DDF documents, Pontifical Biblical Commission, social doctrine Compendium, liturgical norms | New |
| Church law | 1983 Code, current text, plus universal laws such as Universi Dominici Gregis | Renamed from Canon law |
| Church Fathers | Current Fathers minus removals, plus Boethius and Pseudo-Dionysius moved from Medieval, plus Basil, Cyril of Jerusalem, Gregory Nazianzen, Gregory the Great, Chrysostom, Ambrose, Leo | Removals, moves and additions |
| Summa | Aquinas's Summa only | None |
| Theologians and spiritual writers | Current medieval works plus later writers from the candidates memo (Teresa, John of the Cross in the Lewis translation, Francis de Sales, Catherine, Julian, Thérèse, Ignatius, Alphonsus, Montfort, Newman's Catholic works, more Bernard, Aquinas's works outside the Summa, lay writers such as Chesterton's Catholic works, and others). Boethius moves out to the Fathers. | Renamed from Medieval |

Nine collections, down from ten. The merge must update every hard-coded collection key: `user_preferences.default_collections`, `searches.filters`, `guest_trials.filters`, `VALID_COLLECTIONS`, the HyDE prompts and `_COLLECTION_MAX_TOKENS`, `config.overlap_for`, `routes/evaluate.py`, `compare.py`, `apps/web/src/lib/collections.ts`, and the Qdrant payload. Genre and issuer become indexed Qdrant payload fields.

## Phase and PR plan

Each parent is a tracking issue; each child is one PR unless marked.

| Parent | Children, in merge order |
|---|---|
| P0 Checks, provenance, identity and safety | 0.0 GitHub Actions workflow for the tests that need no vendored sources (API tests, datapipeline unit tests, web lint and tests), plus a PR template whose required section holds the locally run source checks; 0.4 publish lock: `run_collection` refuses production writes without an explicit cutover flag (merges before any P1 PR); 0.1a coverage and sequence tests; 0.1b health rules; 0.1c release report with remap-based ID diff; 0.2 source hashes, manifests, rights inventory; 2.1 work registry with frozen IDs, structural anchors, and the rule A fields (communion dates, chronology source, Church acts); 0.3 baseline eval run on the `docs/eval/` gold sets plus targeted questions for the removals and the Vatican II recovery (no stored user queries); 0.5 ops: read the Qdrant plan's memory and disk limits |
| P0 research (sub-issues, each blocks the PR named) | R1 rule A dating and Church-act check (blocks 3.1); R2 canons 296, 360, 361, 948 against iuscangreg.it (blocks 1.5); R3 Esther claims (blocks 1.4); R4 whether the Refutation's book contents are authorial (blocks 1.8a); R5 trace the On Loving God translator (blocks 1.9); R6 edition and provenance check for each planned source (blocks the matching 5.x additions) |
| P1 Adapter fixes | 1.10 shared text hygiene first; 1.1 Vatican II; 1.2 other councils; 1.3 papal; 1.4 Bible; 1.5 canon law; 1.6 Catechism; 1.7 Summa; 1.8a ANF editorial strip; 1.8b NPNF Augustine editorial strip; 1.8c Fathers labels, authors, greetings, recension split with the genuine Ignatius letters taken from the separated ANF text (same branch as the P3 splits); 1.9 medieval. Every PR attaches its release report. None publishes, because of the lock. |
| P2 Schema and reader | 2.2a additive migration from 0039: document fields, attribution, notes, release column, tombstones, redirects, all nullable or defaulted to the current release, and the API tolerates their absence; 2.2b Qdrant alias pointing at today's `chunks` collection with the API reading the alias, the searchable flag (the filter excludes only `searchable = false`, so points without the field stay searchable), full-text search, embedding neighbors, stitch; 2.2c search_vector rebuild; 2.3 metadata backfill; 2.4a API payload, tombstones, redirects; 2.4b web cards and reader; 2.4c About page factual fix (remove the authors who are not in the corpus) |
| P3 Content policy | 3.1 removals; 3.2 labels; 3.3 non-English |
| P4 Republish | 4.0 storage (decided): compact `chunks` with `VACUUM FULL` in a quiet window Carter approves, measure, and buy Supabase Pro only if the rehearsal exceeds about 350 MB or the V5 enrichment is scheduled; build the new Qdrant collection with vectors on disk if 0.5 shows memory is tight; 4.1a remap tooling with a merge policy for the unique constraints on bookmarks, guest_trial_retrievals and retrieval_labels, rehearsed on a Supabase branch; 4.1b production cutover runbook (ops) including the alias switch and its rollback; 4.2 comparison against the baseline (ops) |
| P5 Reorganize and expand | 5.1a genre and issuer filters; 5.1b collection-key migration in four expand-and-contract PRs (API accepts old and new keys and maps old to new; web sends new keys; migration rewrites stored preferences and filters and Qdrant payloads in place with no re-embedding; old keys removed); 5.1c one guaranteed slot per collection, no per-genre guarantee (decided); 5.2 rights inventory completed for every planned source (ops); 5.3 Roman Curia; 5.4 papal and universal law, including A New Hope for Lebanon and Ubicumque et Semper; 5.5 catechisms; 5.6a Fathers additions; 5.6b spiritual writers from CCEL ThML and Gutenberg text; 5.6c scanned works, one PR per work (pending the OCR decision); 5.7 About page rewritten as "What's in TheoCorpus and why"; Eastern code (blocked on license) |
| Retrieval follow-ups | Separate parent, started after the new baseline |

**Production stays working at every merge.** API and web changes deploy on merge; the datapipeline doesn't touch production until P4. The rules that keep that true:

- The publish lock (0.4) merges before any adapter PR, so a routine repair can't publish new IDs piecemeal.
- Every migration is additive, nullable or defaulted, and the API already tolerates missing columns (the 0037 pattern).
- Search reads Qdrant through an alias from 2.2b on, so cutover and rollback are each one alias switch.
- New filters exclude only explicit values, so old rows without the new fields behave as today.
- The collection merge runs expand and contract: each of its four PRs deploys and works alone.
- The About page gets its factual fix early (2.4c) because it is false today; the full rewrite waits until the content it describes exists (5.7).

Republish constraints found on 28 Sep:

- New migrations start at 0039. `0035_studies.sql` sits untracked in `supabase/migrations/`.
- API and web changes deploy on merge, before the republish, so they must work against today's schema and data.
- During the republish, search and the reader must filter on a release column so old and new rows are never both visible.
- Build a new Qdrant collection and switch the alias to it, rather than rebuilding in place.
- Restart the API after cutover to clear the one-hour `/sources` cache. Remap the gold IDs in `docs/eval/`.
- Storage measured on 28 Sep: `chunks` is 380 MB, of which about 100 MB is live column data (content 42 MB, search_vector 49 MB, metadata 5 MB); its overflow (TOAST) storage is 203 MB. Qdrant holds one collection, `chunks`, 54,568 points at 1,536 dimensions (about 335 MB of raw vectors), no quantization, no alias.

## Open items

- Rights follow-up: the Imitation of Christ renewal search.
- Rule A dating research and Church-act check: R1 in P0 research. Unverified so far: Theologia Germanica on the Index, the exact form of Tyrrell's 1907 excommunication, and the Pensées.
- Known research limits, accepted: CPG entry notes (behind a login), Metzger's SC 320 introduction, the Oxford Dictionary of the Christian Church and Quasten were not consulted directly. Consult a library copy only if a decision turns on one.
- Ops actions needing Carter: the `VACUUM FULL` window (4.0).
- GitHub issues not yet opened.
