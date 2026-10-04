# Corpus cleanup and expansion plan

28 September 2026. This file is the record of what was decided and verified in the planning thread of that date. It supersedes the handoff doc "TheoCorpus corpus cleanup and expansion plan" (Carter Tate, 28 Sep 2026) wherever the two disagree. GitHub issues for this work should be opened from this file.

Related files:

- `docs/research/2026-09-28-rule-1-authorship-verification.md` has the sources for every authorship and heresy claim below.
- `docs/research/2026-09-28-corpus-health-and-retrieval-audit.md` and `docs/research/2026-09-28-question-set-corpus-gap-audit.md` are the earlier audits.
- `docs/research/2026-09-28-theologians-spiritual-writers-candidates.md` lists candidate works for the theologians and spiritual writers collection, sorted by legal availability (27 CCEL ThML works, 58 Gutenberg or Internet Archive works, 37 authors needing payment or permission, 44 flagged items).

- `docs/research/2026-09-28-scan-only-works-text-sources.md` says where clean typed text exists for works otherwise available only as page scans.
- `docs/corpus-cleanup/` holds the detailed work specifications, one file per phase. Every item there follows the same template: goal, current state with evidence, changes by file and function, acceptance checks, production safety, what needs Carter, out of scope.
- `docs/corpus-cleanup/README.md` is the procedure every implementer follows for any item: ask Carter the item's open questions before writing code, record the answers, update other specs only within set limits, and get a fresh-context review before the PR.
- `docs/corpus-cleanup/NEEDS-CARTER.md` lists everything Carter must approve, decide or supply, by phase.

Nothing here has changed code or live data yet.

## Start here

**The order is fixed: fix and republish the current corpus first, then reorganize and expand.** Do not add collections or sources before Phase 4 is done, except where an item says otherwise.

1. Read this file's Inclusion rules, Decision log, and Cross-cutting design decisions (D1 to D11). They are settled, and the design decisions override any spec that disagrees. Reopen a decision only if Carter does.
2. Before starting any item, read `docs/corpus-cleanup/README.md` and follow it. It says to ask Carter the item's open questions from `NEEDS-CARTER.md` before writing code, and sets what an implementer may and may not change in other specs.
3. Open `docs/corpus-cleanup/P0-checks-identity-research.md` and start with its first item. Phase 0 builds the checks, the publish lock and the frozen ID registry that every later change is measured against. The publish lock (0.4) must merge before any Phase 1 adapter change.
4. Work through the phases in the order of the "Phase and PR plan" table below. Each item's spec lists what it depends on.
5. Every PR must leave production working. API and web deploy on merge; the datapipeline does not touch production until it is run. See "Production stays working at every merge" below.
6. Ask Carter before any change to live data (Supabase project hvmgffvimqgiejmxwhwq, which production runs on; Qdrant), before sending stored user queries to an outside provider, and before pushing, opening issues or PRs on the public repo.

**Current state (29 Sep 2026)**

| Thing | Where it is |
|---|---|
| This plan and its research | Branch `docs/corpus-cleanup-plan` (worktree `/Users/cartertate/repos/boc-corpus-plan` on Carter's Mac). Not yet pushed or merged. |
| Vendored source files | `datapipeline/sources/` in the main checkout. Gitignored and present only on Carter's Mac; `scripts/vendor_sources.py` re-downloads them, and `--verify` checks their hashes. |
| An early Roman Curia collection | Local branch `feat/roman-curia-collection` (worktree `/Users/cartertate/repos/boc-roman-curia`), reviewed, parked for PR 5.3. Built ahead of order by mistake; do not merge it before Phase 4. Its migration is numbered 0039 and will need renumbering. |
| Rights research | Private, outside git, on Carter's Mac. Never commit rights analysis to this public repo. The decisions that follow from it are in the Decision log. |
| GitHub issues | Not opened. They are to be opened from `docs/corpus-cleanup/`, one parent per phase, after Carter approves. |
| Live corpus | Unchanged: 54,568 passages, 421 documents, 10 collections. |

**Known environment gaps on master**

- There is no CI. Run tests locally: `python3 -m pytest` in `datapipeline/` and in `services/api/`, `npx vitest run` and `npm run lint` in `apps/web/`.
- With vendored sources present, four datapipeline tests fail on master in full-suite order (`test_enrichment_sample_run` twice, `test_pass1_pilot_diff_report`, `test_pass1_questions_cosine_audit`) because a fresh checkout has no `datapipeline/.env`; they pass alone. Without sources and `.env` the count is 14 (see 0.0).
- `services/api/tests/test_hyde_steps.py` imports `httpx2`, which is not a declared dependency.
- `npx tsc --noEmit` in `apps/web/` reports one error in `src/lib/preference-writer.test.ts`.
- The web lint baseline is 0 errors and 4 warnings.

## Status

| Item | State |
|---|---|
| Inclusion rules A to H | Decided |
| Corpus defects | Verified against the live database and the vendored sources on 28 Sep |
| Collections after cleanup | Decided, except where noted |
| Theologians and spiritual writers candidates | Research done; scope questions answered (see Decision log) |
| Detailed work specifications | `docs/corpus-cleanup/`, one file per phase |
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
| Boethius and Pseudo-Dionysius | Boethius moves to Church Fathers; Pseudo-Dionysius is added there (5.6a), since the corpus's two "Dionysius." documents are Dionysius of Alexandria | Both predate the 750 line. Boethius's document ID stays frozen; only its collection changes. |
| Public domain by non-renewal | Accepted, with a renewal search recorded per work in the rights inventory (PR 0.2) | Opens mid-century translations such as the 1940 Bruce Imitation. |
| Lay and non-canonized writers | In scope if they pass rules A to H | The rules judge communion and authorship, not canonization. |
| Pre-conversion works among the candidates | Out: Chesterton's Orthodoxy (1908), Newman's Parochial and Plain Sermons, Edith Stein's pre-1922 works. Newman's Development of Christian Doctrine uses the 1878 edition he revised as a Catholic. | Consequence of the revised rule A. |
| Dante and Pascal | Dante out. Pascal's Pensées in (Trotter 1910), his Provincial Letters out. | The Divine Comedy is allegorical poetry; a line from the Inferno in results reads as teaching, and the poem puts named popes in hell. Pascal died in communion; the Provincial Letters were placed on the Index in 1657, so rule A removes them. Weaknesses accepted: popes have praised Dante highly; the Pensées leans Jansenist on grace and chunks poorly because it is fragments; its Index status is still to be checked (R1). |
| Licences | No spending in this cleanup. Revisit after the free phase ships and usage shows demand. | 85 free works are more than the pipeline can absorb soon, and licensing text for AI search is slow and often refused. Weakness accepted: Bonaventure's systematic works, Hildegard and Peter Damian stay thin, and non-magisterial writing stays mostly pre-1930. |
| Catena Aurea | In, in Theologians and spiritual writers, genre "commentary". Each quotation is attributed to the Father quoted, as "Chrysostom, quoted in Aquinas's Catena Aurea". | Carter's choice. Attributing each quotation keeps the Fathers' words from appearing under Aquinas's name. Weakness: the same Father's text may appear twice, once in his own work and once in the Catena. |
| Modern manuals and theology | All in: Tanquerey, Marmion, Scheeben (credited "after Nieremberg"), Moehler, Pohle-Preuss, Koch-Preuss, and similar public-domain works, in Theologians and spiritual writers with genre "manual" or "treatise" and the date on the card. Adaptations are credited with the adapter ("Joseph Pohle, adapted by Arthur Preuss"). | Manuals answer precise doctrinal questions the gap audit found unanswered, and their theological notes tell users how certain a statement is. Carter's condition: no manual passage may teach something against Church teaching. Weaknesses accepted: in adaptations the adapter's words are woven into the text and can't be separated under rule G; some pre-Vatican II positions were later reworded; multi-volume sets are large and mostly scans. |
| On Loving God translation | Keep the vendored file. It is William Harman van Allen's translation (Saint Bernard On Loving God, Caldey Books No. 1, Caldey Abbey, 1909), public domain as a pre-1931 publication. Credit: "Translated by William Harman van Allen (1909). Sourced via CCEL.org". Restore the 1909 Chapter VIII title. | Decided by Carter on 4 Oct 2026 (revises the 28 Sep row), on R5's findings (`docs/research/R5-on-loving-god.md`): all 15 chapter titles and the chapter openings match a scan of the 1909 edition. The 28 Sep version kept it as "translator unknown" pending the trace. |
| Two vendored papal documents missing from manifests | Add A New Hope for Lebanon (1997) and Ubicumque et Semper (2010) in PR 5.4 | Both files are vendored but absent from the manifests and the database. |
| Pre-PR fact checks | Canons 296, 360, 361 and 948, the Esther claims, and the Refutation's book contents each become a research sub-issue that must close before its adapter PR | Each is a check against a named source and matters for one PR only. |
| Genuine Ignatius letters | Separate the shorter text out of the vendored ANF volume, not Lightfoot | Same middle recension, already vendored, keeps frozen IDs, no scan. Weaknesses: older translation; the split relies on each chapter's first paragraph being the shorter version, which the coverage test must prove per chapter. |
| Storage (4.0) | Compact `chunks` with VACUUM FULL in an approved quiet window, measure, and rehearse locally (D8). The specs project that compaction and the Phase 4 apply may each briefly pass the 500 MB Free-plan limit (see 4.0), so Carter chooses between running anyway and a month of Supabase Pro after the rehearsal measures the real peak. Qdrant: new collection with vectors on disk if memory is tight. | Live row data is about 120 MB of a 380 MB table; the rest is space left by earlier rewrites. Updated 29 Sep from the 4.0 spec's projection. |
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
| Group 3 additions (Roman Curia documents, Compendiums, papal law) | Wait for the cleanup: the current corpus is fixed and republished first, as the plan orders. A Roman Curia adapter (60 Dicastery documents, reviewed) was built early on local branch `feat/roman-curia-collection` and is parked for PR 5.3. | Corrected 29 Sep. The earlier row read "start the code now" from an ambiguous question; Carter's standing decision is one cleanup republish before reorganizing or expanding. |
| OCR and scanned works (5.6c) | Use a clean typed text wherever one exists, after confirming it is the planned edition (19 of the 48 scan-only works have one; see `docs/research/2026-09-28-scan-only-works-text-sources.md`). Where the clean copy sits on a site that claims copyright on its pages (ecatholic2000.com), ask the site or use it only to check our own OCR. For the rest (23 works plus the missing parts of 6), a script strips page furniture and rejoins broken words, then a language model fixes character-level errors under hard limits (edits changing more than about 2% of a passage's words are rejected; the raw OCR is kept). Gate before ingestion: unrecognized-word rate on body text within 1 point of the clean baseline, and 20 random passages checked against the page images. Scanned passages carry a source label. One PR per work; John of the Cross (Ascent, Dark Night, Living Flame) and Teresa (Foundations, Letters, Way of Perfection) first. | OCR means software reading letters off page photographs; its output mixes in page numbers, headers, margin notes and misread letters. This approach recovers the priority works and keeps each work's cost visible. Weaknesses accepted: the model can alter wording despite the limits; the 20-passage check takes about 30 to 60 minutes per work; leftover typos show in the reader. |
| Non-English with no usable English | Keep in the reader, excluded from search, with a note | The reader should not lose text; search serves English readers. |
| Papal collections | Merge encyclicals, apostolic exhortations and papal documents into one "Papal documents" collection | One speaker. Genre becomes a filter, and the user can select one genre, several, or all. |
| Bishops' conferences | No collection yet | One document would get a guaranteed result slot in every search that selects it. Revisit when a second conference source exists. |
| Canon law amendments | Take current text from iuscangreg.it (the Pontifical Gregorian University canon law faculty's register of amendments, not a Vatican site) checked against the amending documents on vatican.va, and verify each amended canon before ingestion | The vendored source is out of date for canon 295. Corrected 28 Sep: an earlier version of this row called iuscangreg.it a Vatican register. |
| Document identity | Freeze today's 421 document IDs in a tracked registry file. Build anchors from source structure. Build the old-to-new remap tool in Phase 0 and run it in every release report. | The manifests are gitignored, regenerated by `scripts/vendor_sources.py`, and have one row per CCEL volume, not per work. Freezing keeps every reader URL. The remap tool makes release reports meaningful and tests the Phase 4 remap months early. |
| Canon law English and amendments (R2) | Use the L'Osservatore Romano English (23 Sep 2016, p. 9) for the De concordia inter Codices canons (111, 112, 535 §2, 868 §1 2° and §3, 1108, 1109, 1111, 1112, 1116, 1127), labelled "Unofficial English translation (L'Osservatore Romano). The Latin text is official.", only after it is checked against the printed page; otherwise rule E. 295 and 296 (2023) follow rule E. No reader note on 360, 361, 948. | Decided by Carter on 4 Oct 2026, on R2's findings (`docs/research/R2-canons.md`). The only reachable copy of the English is a reprint with errors, and the only English for 295 mistranslates §2. |
| Esther additions numbering (R3) | Keep WEB-C chapter and verse numbers for Esther, and title restored passages by addition letter ("Addition C: Esther's prayer"). Store the Nova Vulgata, Septuagint and NAB ranges in metadata for whole additions only, never per verse. Nova Vulgata numbering elsewhere in the Bible is unchanged. | Decided by Carter on 4 Oct 2026, on R3's findings (`docs/research/R3-esther.md`); the Septuagint range and the corrected reason added the same day after review. The Nova Vulgata's additions follow the Old Latin, not the Greek WEB-C translates, so they align only as whole additions. The Catechism and the Italian Lectionary cite the Septuagint's letters, which label the Greek WEB-C translates; the English Lectionary cites the NAB's letter chapters. None of these is WEB-C's own numbering. |
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
| Latin in the English Code: 111, 579, 700 in full; 695 §1, 535 §2 and 868 §1 2°. | Rule 6 treatment where an unofficial English exists; otherwise rule E. | Readable text with an honest label. |
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

The About page (`apps/web/src/components/about/AboutPage.tsx`) names John Chrysostom, Bonaventure, Hildegard and Duns Scotus, none of whom are in the corpus, and Origen, who is in it today (3 works, 932 passages) but is removed under rule A. Its medieval blurb says 9th to 15th centuries, which leaves out Boethius (524). Rewrite it from the actual contents. Corrected 29 Sep: an earlier version said Origen was not in the corpus.

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
| Church Fathers | Current Fathers minus removals, plus Boethius moved from Medieval, Pseudo-Dionysius (an addition: the two "Dionysius." documents in the corpus are Dionysius of Alexandria), plus Basil, Cyril of Jerusalem, Gregory Nazianzen, Gregory the Great, Chrysostom, Ambrose, Leo | Removals, moves and additions |
| Summa | Aquinas's Summa only | None |
| Theologians and spiritual writers | Current medieval works plus later writers from the candidates memo (Teresa, John of the Cross in the Lewis translation, Francis de Sales, Catherine, Julian, Thérèse, Ignatius, Alphonsus, Montfort, Newman's Catholic works, more Bernard, Aquinas's works outside the Summa, lay writers such as Chesterton's Catholic works, and others). Boethius moves out to the Fathers. | Renamed from Medieval |

Nine collections, down from ten. The merge must update every hard-coded collection key: `user_preferences.default_collections`, `searches.filters`, `guest_trials.filters`, `VALID_COLLECTIONS`, the HyDE prompts and `_COLLECTION_MAX_TOKENS`, `config.overlap_for`, `routes/evaluate.py`, `compare.py`, `apps/web/src/lib/collections.ts`, and the Qdrant payload. Genre and issuer become indexed Qdrant payload fields.

## Cross-cutting design decisions

D1 to D10 settled on 29 Sep 2026 after a cross-check of the work specifications found them assuming different mechanics. Every spec in `docs/corpus-cleanup/` must follow these; where a spec disagrees, this section wins.

**D1. A passage ID names one unit of text for good.** `passage_id = f(document_id, anchor)` does not change. An anchor names the same unit of text in every release, so fixing that unit's text (stripping notes, restoring dropped prose, correcting a label) keeps its ID, and bookmarks and saved results stay valid and gain the corrected text. If a fix changes which text an anchor names (Joel and Malachi renumbering, a council rebuilt by session, a split recension), the fix must give the unit a new anchor, and the old anchor gets a redirect to the new one. The release report (0.1c) fails any build where an unchanged anchor's text similarity falls below the threshold 0.1c sets without a redirect. Passage IDs are frozen the same way document IDs are: the 2.1 registry maps each unit that exists today to its current passage ID, and structural anchors decide which unit is which, not what its ID is. Only genuinely new units (restored verses, recovered prose, split recensions) get new IDs. Rebuilding anchors must not re-key the corpus.

**D2. One writer, stage then apply, for the republish and for every publish after it.** A publish never writes straight into the live tables:
1. It builds the collection into staging tables with the live tables' shape (schema `staging`) and a new Qdrant collection.
2. The release report is produced from staging against live.
3. Apply is one database transaction: update changed rows in place by ID, insert new IDs, mark removed IDs retired (never delete them while a user row points at them), write tombstones and redirects, refresh the reader outline (`refresh_document_outline`).
4. Then the Qdrant alias `chunks_live` is switched.

This replaces the "release column" and the two-releases-side-by-side design. No query filters on a release, `chunks` never holds two copies of the corpus, and the "doubles chunks" storage problem shrinks to one staging copy (about 120 MB of live row data, about 210 MB with its indexes; figures in 4.0). It is also the steady-state publish mode after Phase 4, so no later publish can run today's delete-based prune (`writers/reader_writer.py`), which cascades away user rows. The publish lock (0.4) stays locked except for an apply named in a reviewed change to the lock file.

**D3. Removed text is retired, never deleted, while user data points at it.** Every table that references a passage cascades on delete (retrievals, bookmarks, retrieval_labels, guest_trial_retrievals, and reading_progress for documents). Retired passages leave search and the reader's chapter lists, keep their row, and show a tombstone: one sentence of reason and the Church act, with no text. Retired rows with no user references may be deleted after the rollback window (4.1b).

**D4. Every removal has one registry.** Everything any phase removes (rule A to C removals, rule G editorial text, notes split off, duplicate passages, Tanner council texts) is recorded by anchor, never by position, in one tracked file owned by 2.1, with its reason and tombstone text. The writer refuses to retire an ID the registry does not explain.

**D5. Shared vocabularies are defined once.**
- Genre, in 2.2a, lowercase and hyphenated everywhere. Papal: `encyclical`, `apostolic-exhortation`, `apostolic-letter`, `apostolic-constitution`, `motu-proprio`, `bull`, `letter`. Roman Curia: `declaration`, `instruction`, `doctrinal-note`, `note`, `response`, `norms`, `considerations`, `commentary`. Catechisms and law: `catechism`, `compendium`, `code`, `law`. Writers: `treatise`, `manual`, `sermon`, `commentary`, `poem`, `rule`. Anything else: `other`. Adding a value is a normal PR change to 2.2a's list.
- Remap outcomes, in 0.1c: `same`, `moved`, `split`, `merged`, `renumbered`, `removed`. Redirect kinds in 2.2a use the same words.
- Citation for split pieces, in 1.10c: "(part 2 of 3)". The Catechism and Summa adopt it.
- The Qdrant alias is `chunks_live`, and the `searchable` payload index is boolean.
- Every passage, searchable or not, is a Qdrant point; non-searchable ones carry `searchable = false`.
- Document facts that search filters on (collection, genre, issuer, searchable) are written to the Qdrant payload by the D2 writer.
- 2.2a names the two fields later items need: `documents.superseded_by` (links an older text to the current one that replaces it, for Church law and the Catechism) and `chunks.passage_author` (a passage-level author, for Catena Aurea quotations and combined pages).

**D6. Works inside one document are modelled, not split.** Container documents (an ANF volume, "Treatises Attributed to Cyprian") keep their frozen ID and gain a `work_key` per passage and a `document_works` row per work (2.2a). There are no "P3 splits". Splitting the two Augustine treatise volumes into separate documents (1.8b) is the one exception proposed, and it waits for Carter.

**D7. Nothing touches live data before the Phase 4 apply, with one exception Carter may approve.** The early live applies some specs offered (metadata backfill, labels, search flags) are dropped; they ride the Phase 4 apply. The exception is On the Incarnation (1.8d): because Lawson's 1944 translation is copyrighted, its 47 passages may be taken out of search and the reader before Phase 4, by retiring them (D3), if Carter approves. The baseline eval (0.3) runs before any live change.

**D8. Rehearsals run locally.** Supabase branches need the Pro plan and copy schema only, so the Phase 4 rehearsal runs against a local Postgres restored from a `pg_dump` of production. The dump contains user data: it stays on Carter's Mac, is deleted after the rehearsal, and needs his approval. Pro stays a separate decision (4.0).

**D9. OCR tooling comes forward.** The council replacements for councils 8 to 18 (Schroeder, 1937) exist mostly as page scans. The OCR clean-up tool and its quality gate (the method in the Decision log) are built in Phase 1 as item 1.2f, so councils 8 to 18 can be replaced before Phase 4. Where a council's public-domain text is still not ready at Phase 4, its Tanner text is retired and the gap is shown as a tombstone ("translation in preparation"), since TheoCorpus makes no translations of its own.

**D10. Ownership fixes.** Trailing periods on author names are fixed once, in 1.10a (not 1.8c). R2 and R3 are specified in the P0 file; the P1a file refers to them. The Martyrdom of Ignatius keeps its author label and gets the note the plan names. The Apostolic Canons are labelled as received works under rule D ("attributed to the Apostles; compiled about 380"), not "Anonymous". The Refutation of All Heresies waits on R1 (rule A), not only R4.

**D11. Single definitions for the remaining shared mechanics** (settled after the final cross-check on 29 Sep):
- **Publish lock.** The format in 0.4 is the only one: `PUBLISH_LOCK.json` holds `approved_applies`, a list of `{collection, release, steps, reason, approved_by, pr}` where steps are `stage`, `apply`, `rollback` or `repair`. Every write command takes `--release`; the release name is the publish ID. An entry is added by a reviewed PR before a run and removed by another after its rollback window closes. The only exemption: runs whose database and Qdrant URLs are both loopback hosts (local rehearsals) pass without an entry. There is no other bypass.
- **Removal reasons.** 2.1's list is the only list (`rule-a`, `rule-b`, `rule-c`, `rule-g-editorial`, `note-split-off`, `duplicate`, `debris`, `other-author`, `superseded-translation`, `translation-in-preparation`, `not-current-law`). 3.1 and 2.2a use it; 2.2w turns each registry entry into its tombstone row (reason, public text, Church act). The long Ignatian recension is `rule-b`.
- **Staging Qdrant collection** is named `chunks-<release>`.
- **Rollback** is 2.2w's `rollback` command and nothing else: it reverses the apply from its before-snapshot, runs 4.1a's reverse remap in the same transaction, then points `chunks_live` back. The `pg_dump` taken before an apply is a last-resort backup, not a rollback path.
- **Genre list and the work model** live in Python in 2.1 (Phase 0), so Phase 1 adapters can use them before Phase 2: a genre module that 2.2a's `corpus_genres` table is seeded from and tested against, and the `Passage.work_key` field and `document_works` registry shape. 2.2a adds only their database side.
- **Passage fields adapters set:** `searchable`, `language` and `passage_author` are fields on the `Passage` model (added in 2.1). An adapter may set them (1.5b's Latin canons); a registry entry overrides the adapter (3.3).
- **Superseded text** at passage level (CCC 2267, amended canons): the old text is kept as its own passage, `searchable = false`, anchor `<anchor>/history-<year>`, linked by `chunks.superseded_by` to the current passage; the reader shows it as "earlier text". Whole-document history (Universi Dominici Gregis) uses `documents.superseded_by`.
- **Issuer** is two columns: `issuer` (a slug such as `ddf`, `holy-see`, `pope-leo-xiii`) for filters, and `issuer_label` for display.
- **Redirect kinds** are `moved`, `split`, `merged`, `renumbered`. `same` and `removed` are release-report outcomes only.
- **Writer and remap ownership.** 2.2w owns the apply step and calls a `UserDataRemap` interface; 4.1a implements it. 2.2w can move a passage to another document by updating its `document_id` in place, which keeps its ID (needed if Carter approves 1.8b's split).
- **Other writers.** 2.2w updates every other script that writes to the corpus or Qdrant (`backfill_vectors.py`, `reconcile.py`, `stages/reader.py`, `stages/bm25_index.py`, and the repair scripts in `scripts/`) to use `QDRANT_WRITE_COLLECTION` and the lock, or retires them.
- **Embeddings** are looked up in the datapipeline's content-addressed cache first; only cache misses are sent to OpenAI.
- **On the Incarnation** early retirement (D7) follows 2.2w's procedure with reason `translation-in-preparation`, after 0.3, 2.2a, 2.2b, 2.4a and 2.4b.
- **The 1.2e fallback** (a council with no public-domain text ready) is applied by 4.1b step 1, which freezes the Phase 4 build.

## Phase and PR plan

Each parent is a tracking issue; each child is one PR unless marked.

| Parent | Children, in merge order (full specs in `docs/corpus-cleanup/`) |
|---|---|
| P0 Checks, provenance, identity and safety (`P0-checks-identity-research.md`) | 0.0 CI for source-free tests and a PR template; 0.4 publish lock (merges before any P1 PR); 0.1a coverage and sequence tests; 0.1b health rules; 0.1c release report with remap-based ID diff (defines the remap vocabulary, D5); 0.2 source hashes, manifests, rights inventory; 2.1 work registry: frozen IDs, structural anchors, rule A and attribution fields, the removal registry (D4); 0.3 baseline eval with judging, before any live change (ops); 0.5 Qdrant plan limits (ops); 0.6 storage headroom snapshot (ops) |
| P0 research (each blocks the item named) | R1 rule A dating and Church-act check (blocks 3.1, 3.2, 5.6a, 5.6b); R2 canons 295, 296, 360, 361, 948 and English sources for the Latin canons (blocks 1.5b); R3 Esther (blocks 1.4a); R4 Refutation book contents (blocks 1.8a); R5 On Loving God translator (blocks 1.9); R6 edition and provenance of each new source (blocks 1.2c, 1.2d, 1.2e, 1.8d and every 5.x addition) |
| P1 Adapter fixes (`P1a-...md`, `P1b-...md`) | 1.10a shared hygiene and author periods; 1.10b translator notes out of passages; 1.10c split-piece citations; 1.1 Vatican II; 1.3a papal adapters; 1.3b papal genres and labels; 1.5a canon law parsing; 1.5b current canon text (after R2); 1.4a Bible missing verses (after R3); 1.4b Nova Vulgata numbering; 1.4c deuterocanonical pericopes; 1.2a council source research; 1.2b councils parsing; 1.2c Percival for councils 1 to 7; 1.2d Schaff for Vatican I; 1.2f OCR clean-up tool and gate (D9); 1.2e Schroeder for councils 8 to 18; 1.6 Catechism; 1.7 Summa; 1.8a ANF editorial strip; 1.8d On the Incarnation to Robertson; 1.8b NPNF Augustine; 1.8c Fathers labels, greetings, recensions; 1.8e dropped whole works (decision); 1.9 medieval |
| P2 Schema, writer and reader (`P2-P3-...md`) | 2.4c About page factual fix; 2.2a additive migration: document facts, work model (D6), retired flag, tombstones, redirects, staging schema; 2.2w the stage-then-apply writer (D2); 2.2b Qdrant alias `chunks_live`, searchable flag, payload fields; 2.2c search_vector (decision: it is generated, no rebuild); 2.3 metadata into the registry and staging; 2.4a API: document facts, tombstones, redirects; 2.4b web: labels, source credit on opened passages, tombstones |
| P3 Content policy | 3.3 non-English out of search; 3.2 labels and notes; 3.1 removals into the removal registry (applied at 4.1b, D2) |
| P4 Republish (`P4-P5-...md`) | 4.0 storage (VACUUM FULL window, Pro decision); 4.1a user-data remap for redirects, rehearsed locally (D8); 4.2 comparison against the baseline on staging; 4.1b cutover: lock-file change, apply, alias switch, outline refresh, cache restart, rollback window; 4.2 again on production |
| P5 Reorganize and expand | 5.2 rights inventory for planned sources (can run now); 5.1a genre and issuer filters; 5.1c one guarantee slot per collection; 5.1b.1 to 5.1b.4 collection-key migration, expand and contract; 5.3a Roman Curia (parked branch); 5.4 papal and universal law; 5.5 catechisms; 5.6a Fathers additions; 5.3b further Curia texts; 5.6b spiritual writers from text sources; 5.6c scanned works, one PR each; 5.7 About page rewrite; 5.8 Eastern code (blocked on licence) |
| Retrieval follow-ups | RF: separate parent, started after the new baseline |

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
- The republish stages into separate tables and applies in one transaction (D2), so old and new text are never both visible.
- Build a new Qdrant collection and switch the `chunks_live` alias to it, rather than rebuilding in place.
- Restart the API after cutover to clear the one-hour `/sources` cache. Remap the gold IDs in `docs/eval/`.
- Storage measured on 28 Sep: `chunks` is 380 MB (heap 89 MB, overflow or TOAST storage 203 MB, indexes 88 MB), of which live row data is 123 MB (content 42 MB, search_vector 49 MB and metadata 5 MB are the largest columns). The 4.0 spec holds the storage figures every spec cites. Qdrant holds one collection, `chunks`, 54,568 points at 1,536 dimensions (about 335 MB of raw vectors), no quantization, no alias.

## Open items

- Rights follow-up: the Imitation of Christ renewal search.
- Rule A dating research and Church-act check: R1 in P0 research. Unverified so far: Theologia Germanica on the Index, the exact form of Tyrrell's 1907 excommunication, and the Pensées.
- Known research limits, accepted: CPG entry notes (behind a login), Metzger's SC 320 introduction, the Oxford Dictionary of the Christian Church and Quasten were not consulted directly. Consult a library copy only if a decision turns on one.
- Everything that needs Carter, grouped and ordered by phase, is in `docs/corpus-cleanup/NEEDS-CARTER.md`.
- GitHub issues not yet opened.
