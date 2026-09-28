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
| Theologians and spiritual writers candidates | Research done; scope questions open (see Open items) |
| GitHub issues | Not opened yet |

## Inclusion rules

These decide whether a passage is in the corpus. Every current and future source must pass them.

**A. Persons.** A work is excluded when its author, as the Church finally judged him, was a heretic or schismatic who died outside communion. Evidence counts in this order: an ecumenical council, a pope or Roman synod, and where neither exists, the agreed testimony of the Fathers. The Gelasian Decree does not count. It is a private compilation from 519 to 553 (von Dobschütz 1912), and its list of "apocrypha" includes the saint John Cassian. Non-Christian authors are excluded. The rule judges persons, so it doesn't matter whether a given work predates the author's break.

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
| Tatian | Out | Irenaeus, Against Heresies 1.28.1, says he left the Church after Justin's martyrdom. Eusebius, Church History 4.28-29, calls him the author of the Encratite doctrine. No Father defends him. |
| Tertullian | Out, on the same basis as Tatian | Benedict XVI, general audience of 30 May 2007, says his rigorism led him away from communion. |
| Non-English with no usable English | Keep in the reader, excluded from search, with a note | The reader should not lose text; search serves English readers. |
| Papal collections | Merge encyclicals, apostolic exhortations and papal documents into one "Papal documents" collection | One speaker. Genre becomes a filter, and the user can select one genre, several, or all. |
| Bishops' conferences | No collection yet | One document would get a guaranteed result slot in every search that selects it. Revisit when a second conference source exists. |
| Canon law amendments | Take current text from the Vatican amendment register (iuscangreg.it) and verify each amended canon before ingestion | The vendored source is out of date for canon 295. |
| Document identity | Freeze today's 421 document IDs in a tracked registry file. Build anchors from source structure. Build the old-to-new remap tool in Phase 0 and run it in every release report. | The manifests are gitignored, regenerated by `scripts/vendor_sources.py`, and have one row per CCEL volume, not per work. Freezing keeps every reader URL. The remap tool makes release reports meaningful and tests the Phase 4 remap months early. |
| Earlier decisions kept from the handoff doc | CCC 2267 2018 text; canons 111 and 112 in unofficial English; all editorial material deleted; English only; forgeries by heretics out; heretics out even under their own name; attribution by the Church's citations then the Clavis; Alexander of Lycopolis out; Cyprian's two anonymous treatises kept as anonymous; one cleanup republish before reorganizing; no LLM planning step in retrieval | See the handoff doc's decision log. |

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
| A | Origen, 3 works | 932 |
| A | Tertullian, 9 works | 242 |
| A | Novatian, 2 works plus Treatises I and III inside "Treatises Attributed to Cyprian" | 79 + 16 |
| A | Tatian, Address to the Greeks | 44 |
| A | Alexander of Lycopolis, a pagan Platonist (van Oort 2012) | 27 |
| B | Apostolic Constitutions except the 85 canons (Book VIII positions 35 to 43 stay) | 178 |
| B | Six forged Ignatius letters | 59 |
| B | Long recension text inside the 7 "Shorter and Longer" documents | part of 97 |
| B | Sectional Confession of Faith, by Apollinaris (CPG 3645; Caspari 1879, Lietzmann 1904) | 24 (positions 0 to 23) |
| C | Pfaff's Irenaeus fragments XXXVI to XXXIX (Harnack 1900) | 4 |
| C | Four medieval Latin Ignatius letters (CPG 1028) | 4 |
| G | Editorial material, whole passages | about 120 |

Rules A to C remove about 1,609 whole passages plus the long-recension text. Rule G removes about 120 more. On 28 Sep, 50 of 2,967 saved retrievals and no bookmarks pointed at passages to be removed.

Labels for works that stay:

- Pseudo-Justin: Hortatory Address to the Greeks (CPG 1083), On the Sole Government of God (1084), Discourse to the Greeks (1082). On the Resurrection (1081): authorship disputed; Heimgartner 2001 assigns it to Athenagoras.
- Gregory Thaumaturgus: Twelve Topics (1772) and the homilies (1775-1777) not his; On the Soul, to Tatian (1773) disputed.
- Hippolytus: Refutation of All Heresies (CPG 1899) authorship disputed; appendix pieces pseudonymous. Check whether the Refutation's book contents are authorial before removing them under rule G.
- Anonymous: the Didache, Diognetus (chapters 11 and 12 a later addition), the Muratorian fragment, On the Glory of Martyrdom, Exhortation to Repentance, Canons of Hippolytus (Egypt, about 336 to 340).
- Pseudo-Barnabas for the Epistle of Barnabas. Hegemonius for the Acts of Archelaus.
- Doubtful: Methodius's Oration on the Palms and the homily-on-the-Cross fragments, the Lactantius Poem on the Passion, Pamphilus's Exposition of Acts.
- Notes: the Martyrdom of Ignatius is a legendary account; Cyprian's Seventh Council of Carthage rule on rebaptism was not adopted by the Church; the Summa Supplement (4,084 passages) and its appendix (82) were compiled after Aquinas's death.
- Victorinus of Pettau: label the original and Jerome's recension separately.
- Commodian, Arnobius, Lactantius, Victorinus and Clement of Alexandria stay. No council or pope condemned them by name, and rule A doesn't count the Gelasian Decree.

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
| Church Fathers | Current Fathers minus removals, plus Basil, Cyril of Jerusalem, Gregory Nazianzen, Gregory the Great, Chrysostom, Ambrose, Leo | Removals and additions |
| Summa | Aquinas's Summa | None |
| Theologians and spiritual writers | Current medieval works plus later writers from the candidates memo (Teresa, John of the Cross in the Lewis translation, Francis de Sales, Catherine, Julian, Thérèse, Ignatius, Alphonsus, Montfort, Newman, more Bernard, and others) | Renamed from Medieval |

Nine collections, down from ten. The merge must update every hard-coded collection key: `user_preferences.default_collections`, `searches.filters`, `guest_trials.filters`, `VALID_COLLECTIONS`, the HyDE prompts and `_COLLECTION_MAX_TOKENS`, `config.overlap_for`, `routes/evaluate.py`, `compare.py`, `apps/web/src/lib/collections.ts`, and the Qdrant payload. Genre and issuer become indexed Qdrant payload fields.

## Phase and PR plan

Each parent is a tracking issue; each child is one PR unless marked.

| Parent | Children, in merge order |
|---|---|
| P0 Checks, provenance and identity | 0.1a coverage and sequence tests; 0.1b health rules; 0.1c release report with remap-based ID diff; 0.2 source hashes, manifests, rights inventory; 2.1 work registry with frozen IDs and structural anchors; 0.3 baseline eval run (ops, needs Carter's approval before sending stored queries to providers); where checks run, since there is no CI and sources are gitignored (decision) |
| P1 Adapter fixes | 1.10 shared text hygiene first; 1.1 Vatican II; 1.2 other councils; 1.3 papal; 1.4 Bible; 1.5 canon law; 1.6 Catechism; 1.7 Summa; 1.8a ANF editorial strip; 1.8b NPNF Augustine editorial strip; 1.8c Fathers labels, authors, greetings, recension split (same branch as the P3 splits); 1.9 medieval |
| P2 Schema and reader | 2.2a migration: document fields, attribution, notes, release column, tombstones, redirects; 2.2b searchable flag through Qdrant, full-text search, embedding neighbors, stitch; 2.2c search_vector rebuild; 2.3 metadata backfill; 2.4a API payload, tombstones, redirects; 2.4b web cards, reader, About page |
| P3 Content policy | 3.1 removals; 3.2 labels; 3.3 non-English |
| P4 Republish | 4.0 storage: Supabase Pro or per-collection swap (decision, blocking; chunks is 380 MB of a 401 MB database on a 500 MB tier); 4.1a remap tooling with a merge policy for the unique constraints on bookmarks, guest_trial_retrievals and retrieval_labels, rehearsed on a Supabase branch; 4.1b production cutover runbook (ops); 4.2 comparison against the baseline (ops, needs approval) |
| P5 Reorganize and expand | 5.1a genre and issuer filters; 5.1b collection-key migration; 5.1c collection-guarantee slots after the merge (decision); 5.2 rights review (ops); 5.3 Roman Curia; 5.4 papal and universal law; 5.5 catechisms; 5.6 Fathers and spiritual writers; Eastern code (blocked on license) |
| Retrieval follow-ups | Separate parent, started after the new baseline |

Republish constraints found on 28 Sep:

- New migrations start at 0039. `0035_studies.sql` sits untracked in `supabase/migrations/`.
- API and web changes deploy on merge, before the republish, so they must work against today's schema and data.
- During the republish, search and the reader must filter on a release column so old and new rows are never both visible.
- Build a new Qdrant collection and switch an alias to it, rather than rebuilding in place.
- Restart the API after cutover to clear the one-hour `/sources` cache. Remap the gold IDs in `docs/eval/`.

## Open items

- Theologians and spiritual writers scope questions (candidates memo, section 6): whether Summa becomes an Aquinas collection; whether Boethius and Pseudo-Dionysius move to the Fathers; whether public domain by non-renewal is accepted; lay writers, Dante, Pascal, modern manuals; licence spending; OCR clean-up budget.
- CCEL asks permission to republish its editions even where the base text is public domain. All current Fathers and medieval sources are CCEL ThML. Nobody has recorded asking.
- Not verified by the research agent: CPG entry notes (behind a login), Metzger's SC 320 introduction, the Oxford Dictionary of the Christian Church, Quasten.
- Canons 296, 360, 361 and 948: verify against iuscangreg.it.
- Esther: the handoff doc's claims about verses 4:6, 9:5 and 9:30 and about Greek additions inside Hebrew verses were not checked.
- Whether the Refutation of All Heresies book contents are authorial.
- Handoff doc open decisions still open: genuine Ignatius letters from the separated ANF text or Lightfoot's translation; A New Hope for Lebanon and Ubicumque et Semper manifests; permissions from the Vatican and other rights holders.
- GitHub issues not yet opened.
