# Republish checks (corpus cleanup 4.2), 20 Nov 2026

The spec is `docs/corpus-cleanup/P4-P5-republish-expand.md`, item 4.2. Checks are written fresh and hold no user data; results name corpus passages only.

## Staging (4.1b step 2), 20 Nov 2026, 20:49 to 21:05 UTC

- **Run:** `services/api/scripts/republish_checks.py --spend` in process on the Lenovo, with `CORPUS_READ_SCHEMA=staging` and `QDRANT_READ_COLLECTION=chunks-republish-2026-10`, against production's staged publish `republish-2026-10` (built from master `99600f5`). Read-only; nothing was written.
- **Checks:** 115 in all: 59 searches through the production pipeline (`hyde_cohere_luna_seats10t80_ftsminmatch`, 3 of them also asking the explanation model), 49 database checks, 3 keyword searches and 4 aggregates over every result.
- **First run:** 113 PASS, 1 FAIL, 1 ERROR.
  - `2.4d.exsurge-domine-31` FAIL: the explanation said the passage is "Luther's condemned proposition 31, which Exsurge Domine rejects" but did not name Leo X, which the check also requires. The point of the check (C-01, the explanation marks the position as rejected) held.
  - `4.2.answers.bible` ERROR: the listwise reranker returned malformed output (`rerank_listwise_luna:structured_contract_failed`), so the search fell back to Cohere's order; the check counts any degraded search as an error.
- **Rerun of those two and the two slowest searches:** 4 PASS. The Exsurge explanation named Leo X.
- **Every check has passed against staging.**
- **Cost:** $0.3576, plus $0.0243 for the rerun (the pipeline's cost tracker; no judge).
- **Timing** (4.0 step 5):
  - Vector search on the new collection: median 0.27 s, slowest 0.54 s.
  - Whole searches: median 12.16 s. The slowest were 97.4 s (Against Celsus) and 72.1 s (q. 71), both in model steps with fast vector search, and took 13.8 s and 10.5 s on the rerun. No Qdrant upgrade is needed.

### The near-duplicate filter

The release report flagged a much higher near-duplicate collision rate on the new fingerprints, which prefix author, title and chapter: Summa 67.4% of neighbouring pairs against 20.5% today. The run recorded every similarity the filter computed. At the old line of 0.9 it dropped 98 candidates in 36 of the 59 searches.

#411 (merged 20 Nov 2026) gives each collection a line that fires on the new fingerprints as often as 0.9 does on today's, read from the pair's own points, so it switches with the alias. Replayed on this run's similarities, the drops fall to 32 in 14 searches. The post-cutover run measures it live.

32 of the 59 searches returned fewer than their 5 results, most of them because of the standing per-source cap (two per document or chapter). Several had no near-duplicate drop at all.

## Production (4.1b step 11)

Not yet run.

## Every check

| Check | Kind | Staging | Detail (staging) | Production |
|---|---|---|---|---|
| `4.2.nostra-aetate-4` | search | PASS | found Nostra Aetate, §4 (part 2 of 2) [councils] | not yet run |
| `4.2.trent-justification` | search | PASS | found Council of Trent, Session 6, Decree on Justification, Chapter VII [councils] | not yet run |
| `4.2.vatican-i-infallibility` | search | PASS | found First Vatican Council, Pastor Aeternus, Chapter IV (part 2 of 2) [councils] | not yet run |
| `4.2.vatican-i-faith-reason` | search | PASS | found First Vatican Council, Dei Filius, Chapter IV (part 2 of 2) [councils] | not yet run |
| `4.2.ccc-2267` | search | PASS | ok: found CCC §2263–2267 [catechism] \| ok: none among 2 results | not yet run |
| `4.2.ccc-2267-history` | database | PASS | stored = 1, searchable = 0 | not yet run |
| `4.2.canon-112` | search | PASS | ok: first is Code of Canon Law, Can. 112 [canon-law] \| ok: none among 1 results | not yet run |
| `4.2.susanna` | search | PASS | found Daniel 13:29–57 [bible] | not yet run |
| `4.2.bel-and-the-dragon` | search | PASS | found Daniel 14:1–27 [bible] | not yet run |
| `4.2.no-short-passages` | database | PASS | short = 0 | not yet run |
| `4.2.vatican-ii-no-note-cards` | database | PASS | note_cards = 0 | not yet run |
| `4.2.indulgence` | search | PASS | found CCC §1471 [catechism] | not yet run |
| `4.2.psalm-51-title` | database | PASS | with_title = 1 | not yet run |
| `2.2c.keyword-canon-1055` | keyword | PASS | first is Code of Canon Law, Can. 1055 [canon-law] | not yet run |
| `2.2c.keyword-ccc-2267` | keyword | PASS | first is CCC §2263–2267 [catechism] | not yet run |
| `2.2c.keyword-john-3` | keyword | PASS | found John 3:22–36 [bible] | not yet run |
| `2.2c.search-vector-rebuilt` | database | PASS | stale = 0 | not yet run |
| `1.7.summa-citations` | database | PASS | all 27115 Summa passages cite their own article | not yet run |
| `1.8c.firmilian-credited` | database | PASS | passages = 12, credited_otherwise = 0 | not yet run |
| `1.8c.firmilian-search` | search | PASS | ok: found The Epistles of Cyprian, Firmilian of Caesarea, to Cyprian · Epistle LXXIV (part 9 of 12) [church-fathers] \| ok: none among 3 results | not yet run |
| `3.1.origen` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.tertullian-seven-works` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.novatian-works` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.novatian-letters` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.tatian` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.arnobius` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.alexander-of-lycopolis` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.hippolytus` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.panegyric-to-origen` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.phoenix` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.apostolic-constitutions` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.forged-ignatius` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.sectional-confession` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.pfaff-fragments` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.medieval-ignatius` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.1.kept-works` | database | PASS | 10d8d7c6-680c-5739-bc98-6ce557371f25 6, 3717ce05-ad42-5ec3-b3ce-ff3964908e05 20, 506ebe31-239c-509c-ba5e-b6c822d002df 52, 5d75dc92-df2c-5421-904f-4249590ff48a 1 | not yet run |
| `3.1.search-against-celsus` | search | PASS → PASS on rerun | none among 5 results | not yet run |
| `3.1.search-flight-in-persecution` | search | PASS | none among 5 results | not yet run |
| `3.1.search-naassenes` | search | PASS | none among 2 results | not yet run |
| `3.1.search-roman-clergy-letters` | search | PASS | none among 2 results | not yet run |
| `3.1.search-to-his-wife` | search | PASS | found To His Wife, Chapter I: Design of the Treatise. Disavowal of Personal Motives in Writing It [church-fathers] | not yet run |
| `3.1.search-apparel-of-women` | search | PASS | found On the Apparel of Women, Book II · Chapter XIII: It is Not Enough that God Know Us to Be Chaste: We Must Seem So Before Men. Especially in These Times of  | not yet run |
| `3.3.ubi-lutetiam` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.3.latin-passages` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.3.omission-notes` | database | PASS | Instructor 1, Stromata 1, Divine Institutes 1, Workmanship of God 1 | not yet run |
| `3.3.search-stromata-iii` | search | PASS | none among 4 results | not yet run |
| `3.3.search-ubi-lutetiam` | search | PASS | none among 5 results | not yet run |
| `1.3d.held-documents` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `1.3d.search-held` | search | PASS | none among 1 results | not yet run |
| `1.3d.ineffabilis-deus` | search | PASS | found Ineffabilis Deus, §52 [encyclicals] | not yet run |
| `1.3d.mirari-vos` | search | PASS | found Mirari Vos, §13 [encyclicals] | not yet run |
| `1.3d.quanta-cura-restored` | database | PASS | restored = 1 | not yet run |
| `1.5b.unofficial-english` | database | PASS | labelled = 9 | not yet run |
| `1.5b.retired-canons` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `1.5b.latin-links` | database | PASS | links = 6 | not yet run |
| `1.5b.search-personal-prelatures` | search | PASS | none among 4 results | not yet run |
| `1.7.q71` | search | PASS → PASS on rerun | found Summa Theologiae I, q. 71, a. 1, co.: On the Work of the Fifth Day [summa] | not yet run |
| `1.7.q72` | search | PASS | found Summa Theologiae I, q. 72, a. 1, co.: On the Work of the Sixth Day [summa] | not yet run |
| `1.7.question-prologues` | database | PASS | prologues = 613 | not yet run |
| `3.4.rejected-voice-ranges` | database | PASS | Exsurge Domine 41, Summa 10522, Octavius 10, Ephesus 4, Syllabus 80, Constance 4, Acts of Archelaus 11 | not yet run |
| `2.4d.exsurge-domine-31` | search | FAIL → PASS on rerun | ok: found Exsurge Domine, §31 [papal-documents] \| ok: explanation: 'The claim that a just person sins in every good work is Luther’s condemned proposition 31,  | not yet run |
| `2.4d.summa-objection` | search | PASS | ok: found Summa Theologiae I, q. 2, a. 3, obj. 1: Whether God exists? [summa] \| ok: explanation: 'The argument that God’s infinite goodness should preclude any | not yet run |
| `2.4d.caecilius` | search | PASS | ok: found The Octavius of Minucius Felix, Chapter V (part 2 of 2) [church-fathers] \| ok: explanation: 'Caecilius argues that disasters kill good and bad people | not yet run |
| `3.4.syllabus` | search | PASS | found Syllabus of Errors, §15 [encyclicals] | not yet run |
| `3.4.wyclif` | search | PASS | found Council of Constance, Session 8, Articles of Wyclif (part 1 of 2) [councils] | not yet run |
| `3.4.nestorius` | search | PASS | found Council of Ephesus, Nestorius's Second Letter (part 3 of 4) [councils] | not yet run |
| `3.4.mani` | search | PASS | found The Acts of the Disputation with the Heresiarch Manes, Chapter VI (part 2 of 3) [church-fathers] | not yet run |
| `2.4f.lateran-iv-scanned` | search | PASS | found Fourth Lateran Council, Canon 21 [councils] | not yet run |
| `2.4f.scanned-label-counts` | database | PASS | apostolic-exhortations 187, councils 388, encyclicals 481, papal-documents 9 | not yet run |
| `1.2c.chalcedon` | search | PASS | found Council of Chalcedon, The Definition of Faith (part 3 of 3) [councils] | not yet run |
| `1.4b.joel-numbering` | search | PASS | found Joel 3:1–5 [bible] | not yet run |
| `1.4b.daniel-hosea-numbering` | database | PASS | daniel = 1, hosea = 1 | not yet run |
| `1.4a.book-names-and-prologue` | database | PASS | song_of_songs = 1, sirach_prologue = 1 | not yet run |
| `1.4c.deuterocanonical-pericopes` | database | PASS | Tobit 31, Judith 45, Wisdom 47, Sirach 125, Baruch 20, 1 Maccabees 101, 2 Maccabees 74 | not yet run |
| `1.8c.ignatius-shorter-recension` | database | PASS | shorter = 91, other = 0 | not yet run |
| `1.8d.robertson-incarnation` | search | PASS | found On the Incarnation of the Word, Section 20 [church-fathers] | not yet run |
| `1.8d.robertson-text` | database | PASS | robertson = 1, lawson = 0, passages = 59 | not yet run |
| `1.9.anselm` | database | PASS | cur_deus_homo = 1, proslogium_date = 1, proslogium_preface = 1 | not yet run |
| `phase-1.removals` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `contents.summa-and-catechism` | database | PASS | summa = 3775, catechism = 566, supplement = 1 | not yet run |
| `3.2.document-labels` | database | PASS | all 17 as registered | not yet run |
| `3.2.work-labels` | database | PASS | all 12 as registered | not yet run |
| `3.2.works-hold-their-passages` | database | PASS | Apostolic Canons 6, Supplement's appendix 84, Supplement 4245, Muratorian Fragment 2 | not yet run |
| `3.2.diognetus-note` | database | PASS | noted = 2, other_notes = 0 | not yet run |
| `3.2.preservation-notes` | database | PASS | noted = 15 | not yet run |
| `3.2.fathers-dates-and-genres` | database | PASS | dated = 54, with_genre = 91 | not yet run |
| `3.2.apostle-lists` | database | PASS | visible = 0, live_documents = 0 | not yet run |
| `3.2.pseudo-justin` | search | PASS | found Hortatory Address to the Greeks, Chapter I [church-fathers] | not yet run |
| `3.2.supplement` | search | PASS | found Summa Theologiae Suppl., q. 82, prologue [summa] | not yet run |
| `3.2.didache` | search | PASS | found The Teaching of the Twelve Apostles, Chapter VII [church-fathers] | not yet run |
| `3.2.martyrdom-of-polycarp` | search | PASS | ok: found The Martyrdom of Polycarp, Chapter XIV.—The prayer of Polycarp. [church-fathers] \| ok: none among 2 results | not yet run |
| `4.2.answers.bible` | search | ERROR → PASS on rerun | 5 results, first James 1:19–27 [bible] | not yet run |
| `4.2.answers.catechism` | search | PASS | 5 results, first CCC §2558–2563 [catechism] | not yet run |
| `4.2.answers.church-fathers` | search | PASS | 5 results, first The First Apology, Chapter LXI.—Christian baptism. [church-fathers] | not yet run |
| `4.2.answers.councils` | search | PASS | 5 results, first Council of Basel-Ferrara-Florence, Florence, Session 6, Laetentur caeli [councils] | not yet run |
| `4.2.answers.encyclicals` | search | PASS | 5 results, first Centesimus Annus, §15 [encyclicals] | not yet run |
| `4.2.answers.apostolic-exhortations` | search | PASS | 5 results, first Familiaris Consortio, §17 [apostolic-exhortations] | not yet run |
| `4.2.answers.papal-documents` | search | PASS | 3 results, first Salvifici Doloris, §26 (part 2 of 2) [papal-documents] | not yet run |
| `4.2.answers.canon-law` | search | PASS | 5 results, first Code of Canon Law, Can. 1066 [canon-law] | not yet run |
| `4.2.answers.summa` | search | PASS | 5 results, first Summa Theologiae II-II, q. 110, a. 3, co.: Whether every lie is a sin? [summa] | not yet run |
| `4.2.answers.medieval` | search | PASS | 5 results, first On Loving God, Chapter V. Of the Christian's debt of love, how great it is (part 2 of 2) [medieval] | not yet run |
| `4.2.reference.bible` | search | PASS | ok: found Psalms 23:1–6 [bible] \| ok: vector path found Psalms 23:1–6 [bible] | not yet run |
| `4.2.reference.catechism` | search | PASS | ok: found CCC §1471 [catechism] \| ok: vector path found CCC §1471 [catechism] | not yet run |
| `4.2.reference.canon-law` | search | PASS | ok: found Code of Canon Law, Can. 1055 [canon-law] \| ok: vector path found Code of Canon Law, Can. 1055 [canon-law] | not yet run |
| `4.2.reference.summa` | search | PASS | ok: found Summa Theologiae I, q. 2, a. 3, co.: Whether God exists? (part 1 of 2) [summa] \| ok: vector path found Summa Theologiae I, q. 2, a. 3, co.: Whether G | not yet run |
| `4.2.reference.councils` | search | PASS | ok: found Lumen Gentium, §25 (part 1 of 2) [councils] \| ok: vector path found Lumen Gentium, §25 (part 1 of 2) [councils] | not yet run |
| `4.2.reference.encyclicals` | search | PASS | ok: found Rerum Novarum, §20 [encyclicals] \| ok: vector path found Rerum Novarum, §20 [encyclicals] | not yet run |
| `4.2.reference.apostolic-exhortations` | search | PASS | ok: found Familiaris Consortio, §11 [apostolic-exhortations] \| ok: vector path found Familiaris Consortio, §11 [apostolic-exhortations] | not yet run |
| `4.2.reference.papal-documents` | search | PASS | ok: found Ordinatio Sacerdotalis, §4 [papal-documents] \| ok: vector path found Ordinatio Sacerdotalis, §4 [papal-documents] | not yet run |
| `4.2.reference.church-fathers` | search | PASS | ok: found The Confessions of Saint Augustine, Book X · Chapter XXVII [church-fathers] \| ok: vector path found The Confessions of Saint Augustine, Book X · Chap | not yet run |
| `4.2.reference.medieval` | search | PASS | ok: found Proslogium, Chapter II [medieval] \| ok: vector path found Proslogium, Chapter II [medieval] | not yet run |
| `4.2.no-short-results` | aggregate | PASS | all 221 results across 59 searches | not yet run |
| `4.2.results-searchable` | aggregate | PASS | all 221 results across 59 searches | not yet run |
| `4.2.summa-results-cite-their-article` | aggregate | PASS | all 27 Summa passages cite their own article | not yet run |
| `4.2.vatican-ii-results-not-notes` | aggregate | PASS | all 221 results across 59 searches | not yet run |
