# Corpus review synthesis

6 October 2026. This file combines three independent-or-partly-independent corpus audits into one checked list. It was written by Claude Opus 5.5 in the session that built 0.1c. It is not committed, and nothing in it changes a spec yet.

Sources:

- **Opus**: `docs/research/2026-10-06-corpus-review-opus.md`, findings A-001 to A-024. Independent.
- **Opus-2**: `docs/research/2026-10-06-corpus-review-opus-2.md`, findings B-001 to B-015. A second Opus pass that read the first and looked for more. Not independent of Opus.
- **Sol**: `docs/research/2026-10-06-corpus-review-sol.md`, findings Sol A-001 to A-019 (its IDs reuse the letter A; they are written "Sol A-0nn" below). Independent of both Opus reports.
- **Sol supplement**: `docs/research/2026-10-06-corpus-review-sol-followup.md`, findings Sol B-001 to B-005 (written "Sol B-0nn" below). A fresh Sol pass that excluded the main Sol report's findings and did not read either Opus report. Merged into C-04, C-13, C-14 and C-15.

All three worked from the brief in `docs/corpus-cleanup/CORPUS-REVIEW-PROMPT.md`, the 6 Oct production snapshot, a master build, and read-only access to production Qdrant.

## 1. Summary

**The reviews are sound.** I re-checked the headline evidence of every finding against my own master build (the same adapter code as `7bd2b66`), my own load of the snapshot, the production vectors, and the vendored sources. Every claim I tested held, with one exception: Opus's explanation for the 12 points that share a vector (A-019) is wrong, and Sol's is right (section 4). Where counts differed between reviewers, the difference came from how wide a pattern each used, not from a wrong fact.

**The planned cleanup is not enough yet.** Together the reviews add 30 merged findings beyond what the plan and specs cover: 7 critical, 9 high, 8 medium and 6 low.

The critical ones share one theme. The text can be intact while the corpus still says the wrong thing about **who is speaking**:

- condemned propositions shown as a pope's or council's teaching;
- a pagan's and a heretic's speeches shown as a Father's;
- letters to Cyprian, one of them by Novatian, shown as Cyprian's;
- two of Aquinas's replies labelled as the objections he refutes;
- an editor's essay shown as Aquinas's answer.

Two more critical findings are plain text defects: the Catechism adapter drops the definition of an indulgence, along with most of the Ten Commandments introduction and the liturgical prayers the Catechism quotes; and a web-editor advert appears as a Council of Trent passage.

**Saved user data is barely touched today.** About 130 saved rows sit on passages with these defects. The larger exposure is a design gap. Opus-2 found that a saved passage split into pieces can reopen on a different paragraph after Phase 1, with about 700 saved rows on such pieces. Nothing in the current specs catches this (C-10).

**Rating the audits:**

| Audit | Accuracy | Strength | Weakness |
|---|---|---|---|
| Opus | High. One wrong cause (identical vectors); every other claim I tested held. | Broadest. All ten collections, the search index, keyword search, the dedup step and the About page. The only one to find the Catechism loss (the worst text defect) and the dedup collapse. | Shallow on the Summa's internal structure. |
| Opus-2 | High. | The best design-gap findings: piece IDs that shift (C-10), credits stored inside citations (C-15), the Summa citation losing its question (C-14), unsearchable text feeding neighbours' vectors (C-21). Also the only one to catch Novatian's letter. | Not independent; it read Opus first. |
| Sol | High, the most rigorous. It checked the Summa against an independent Latin edition and read every case it counted. | Deepest on the Summa and on speaker and attribution problems. Found six defects in the 1.7 spec itself. | Missed the Catechism loss, the papal structure problem and the dedup collapse. |

Two independent model families finding the same trust problems (condemned propositions, the Cyprian letters, the Octavius and Manes speeches, Psalm titles, canon-law chapters, the "Argument" summaries) is strong evidence those problems are real and central.

## 2. Merged findings

Severity is mine, after verification:

- **critical**: users are shown misleading content or a wrong attribution, or text is missing in a way that breaks an answer;
- **high**: harms retrieval or the reader across many passages, or a planned fix would cause harm;
- **medium** and **low** as usual.

"Verified" means I reproduced the evidence myself. "Reviewer evidence" means I checked the code path or a sample but not the full count. Owners are suggestions; every owner change to another item's design needs Carter's approval (README §3).

### Critical

**C-01. Condemned and opponents' words carry no role.** Sources: Opus A-002, Opus-2 B-007, Sol A-001, A-006, A-011.
- Exsurge Domine §1–41 (Luther's propositions, 6 saved rows).
- The Syllabus of Errors §1–80.
- Constance's condemned articles of Wyclif and Hus, about 120 passages.
- Nestorius's second letter to Cyril at Ephesus, 5 passages.
- The pagan Caecilius's speech in the Octavius, chapters V–XIII (11 passages).
- Manes's speeches in the Acts of Archelaus: 5 passages with no inline speaker, plus Turbo's exposition.

The models see only "§N" or nothing, and `passage_role` passes no warning. Verified: the labels, the counts for Exsurge, the Syllabus and Constance, and the passage IDs for the Nestorius letter.
- **Owner:** a new "rejected-voice role" item, consulting 1.3a, 1.2a, 1.8c and 3.2.
- **Check:** a registry of known rejected-voice ranges whose roles must reach the rerankers, the explanation prompt and the card.

**C-02. Letters by others filed under Cyprian, one by Novatian.** Sources: Opus-2 B-001, Sol A-007.
- 16 of the 82 letters (45 passages) were written by the Roman clergy, Cornelius, confessors and Firmilian, but all are credited "Cyprian.".
- Epistle XXX was written by Novatian. The corpus's own Epistle LI says so. Rule A removes Novatian entirely, but this letter is on no list.
- Firmilian's letter calls Pope Stephen a Judas under Cyprian's name.

Verified: the author field, Epistle XXX's 5 passages, the Epistle LI sentence, and Firmilian's letter.
- **Owner:** 3.1 (a `rule-a` removal for Epistle XXX; Epistle XXIX needs R1's view) and 1.8c or 3.2 (a work per letter with its real author).
- **Check:** `attribution.letter_sender`.

**C-03. The Catechism adapter drops text.** Source: Opus A-001.
- **What is lost:**
  - The definition of an indulgence (CCC 1471) is in `ccc.json` and in no passage, live or build.
  - CCC 2052–2074 keep about the first line of each paragraph; `ccc/2053` is 120 characters and stops mid-phrase.
  - The liturgical prayers the Catechism quotes are dropped.
  - At least 43 paragraphs lose text.
- **Cause:** `is_section_header` tests `"indent" in paragraph`, but all 483 indented source paragraphs keep `indent` under `attrs`, so the test never fires. Short unnumbered lines are then treated as headers and dropped.
- **Why no check notices:** coverage reads 98.96% and passes, and each paragraph keeps its first line, so the sequence check passes too.
- **Verified:** the missing definition, the truncated `ccc/2053`, and the cause in code and source.
- **Owner:** 1.6, or its own small PR first, since anchors and IDs do not change.
- **Check:** a per-paragraph word-completeness test (`coverage.catechism.paragraph_words`) and a sentinel for CCC 1471.

**C-04. Aquinas's own answer mislabelled or mixed with an editor's.** Sources: Sol A-013, A-019, Sol B-001.
- **Replies labelled as objections:** two replies carry "Objection 2" and "Objection 3" (II-II q.172 a.1; Suppl. q.77 a.4), each sitting between replies 1–3 and 2–4. The source has the typo, and 1.7's walk would keep it.
- **An editor's essay as a reply:** III q.26 a.2 appends the edition's "St. Thomas and the Immaculate Conception (editorial note)" to reply 3.
- **A supplied reply:** I-II q.102 a.6 reply 10 is the editor Nicolai's reconstruction. Its warning is stripped and the text kept as Aquinas's.
- **Counterarguments inside objections:** four sed contra paragraphs that open "The contrary(,) however" instead of "On the contrary" are appended to Objection 3, so Aquinas's own argument is labelled as the view he refutes (I-II q.46 a.7; II-II q.56 a.1 and a.2; II-II q.140 a.2). Both today's parser and 1.7's walk do this (Sol B-001). Verified: all four.

Verified: both mislabels and their neighbours, and the editorial-note passage. The Nicolai case rests on the reviewer's evidence.
- **Owner:** 1.7, with a reviewed role-override list and `rule-g-editorial` entries.
- **Check:** `roles.summa.objection-after-replies`, plus a test that "supplied by" warnings are acted on before they are stripped.

**C-05. Site adverts and secondary-source text as authoritative passages.** Sources: Opus A-005, Opus-2 B-008.
- `council-of-trent/sec-0/21` is entirely a web-editor advert.
- `cum-sancta-mater-ecclesia/4` ends in a second advert. Its year is also wrong: 1858 is stored, but the dating line and Pius IX's thirteenth year give 1859.
- `exsurge-domine/41/p3` holds 1,833 characters taken from a 1964 translation, plus a "Webmaster comment".

Verified: all three.
- **Owner:** 1.2b (Trent), 1.3a (the two papal passages) and 2.3 (the year).
- **Check:** a blocking boilerplate pattern list in `health_patterns.json`.

**C-06. Syllabus §80 swallows text from other documents.** Source: Sol A-004.
- `syllabus-of-errors/80/p1` is 3,841 characters, and `/p2` continues with exhortations on papal constitutions, Freemasonry and Prussian law.
- The adapter appends the source's unnumbered paragraphs to the last numbered proposition.

Verified: lengths and openings.
- **Owner:** 1.3a, with an explicit end of body for the Syllabus.

**C-07. Three Summa articles hold the next article under the wrong citation.** Source: Sol A-003.
- II-II q.64 a.7 holds a.8, q.66 a.5 holds a.6, and q.123 a.10 holds a.11.
- In total 51 passages are affected; 24 of them belong to the following article.
- The `fetch_context.py` docstring knows of the three keys, but 1.7's walk keeps them merged.

Verified: two of the second determinations cite the first article.
- **Owner:** 1.7 and 2.1 (new structural IDs for the three trailing articles).
- **Check:** `structure.summa.one-disputation-per-article`.

### High

**C-08. Papal documents: next section's heading glued on, real chapters replaced by "Paragraphs N–M".** Source: Opus A-003.
- About 950 papal passages end with the next section's title, e.g. `fratelli-tutti/8` ends "CHAPTER ONE / DARK CLOUDS OVER A CLOSED WORLD".
- 115 documents show bucket chapters although their sources have titled sections.
- 1.3a treats only numbered headings as headings, and only documents of 20 paragraphs or fewer get headings.

Verified: the example. My looser count gives about 940 passages.
- **Owner:** 1.3a, following 1.1's approach of moving the heading to the start of the next section.
- **Check:** `health.R9_trailing_heading`, plus no bucket chapters where the source has headings.

**C-09. Search drops distinct neighbouring passages as "duplicates", and some pairs have identical vectors.** Sources: Opus A-004 and A-019, recast; Sol (coverage).
- **Mechanism:** dedup (`services/api/app/rag/dedup.py`) drops the lower-ranked of two passages from one document within two positions whose vectors have cosine above 0.9. Each vector is built from the passage plus 200 to 300 characters of each neighbour, so a short passage is mostly its neighbours.
- **Collision rates** among nearby pairs, recomputed on the production vectors: canon law 35.7%, Summa 20.5%, councils 8.9%.
- **The extreme case:** six pairs of short neighbours have byte-identical embedding inputs and vectors (e.g. canons 892/893, Syllabus §75/§76). They can never both be shown.

Verified: the code, the rates, and that the inputs are identical.
- **Owner:** a retrieval follow-up, decided before 4.1b so the republish embeds once. Options: a higher threshold for chapter-keyed collections, a second "clean text" comparison, or less canon-law overlap.
- **Check:** `index.dedup_collision_rate` in the release report.

**C-10. A saved piece can reopen on a different paragraph.** Source: Opus-2 B-002.
- **The gap:** D1 promises an ID names the same text. But 0.1c's stability check joins a unit's pieces by design, so text sliding between pieces passes.
- **Measured:** in Opus-2's simulation of 1.10b, 558 surviving Fathers pieces open on a different paragraph, 67 of them with saved rows.
- **Wider exposure:** live has 702 saved rows on pieces, and 1.10c, 1.1, 1.3a and 1.6 move piece boundaries again.

Verified: the 0.1c code does join pieces. The simulation numbers are the reviewer's evidence.
- **Owner:** 0.1c and 2.1 (a per-piece stability rule) and 4.1a (redirects for shifted pieces).
- **Check:** `release.piece_stability`.

**C-11. Psalm titles and the Sirach prologue are dropped.** Sources: Opus-2 B-004, Sol A-009.
- The 138 Psalm superscriptions (`\d`, such as Psalm 51's Nathan and Bathsheba title) and the Prologue of Sirach are in the USFM and in no passage.
- In Catholic Bibles the Psalm titles are Scripture; the Vatican's Psalm 51 numbers its title as verses 1–2.
- 1.4a's verse check cannot see unnumbered lines.

Verified: 138 `\d` lines, none in the build; the prologue is in the source, not the build.
- **Owner:** 1.4a.
- **Check:** `coverage.bible.superscriptions` and `sentinel.sirach_prologue`.

**C-12. Editors' "Argument" summaries have no owner, and some are the only speaker signal.** Sources: Opus A-011, Opus-2 B-006, Sol A-008.
- About 136 summaries in works that stay are owned by no item: the Epistles of Cyprian 81–82, the Octavius 41, the Treatises of Cyprian 8–10, Treatises Attributed to Cyprian 2, and the Re-baptism treatise 1.
- Novatian's 37 are moot under rule A, and City of God's 22 belong to 1.8b.
- Rule G removes them, but 1.8a's patterns do not.
- In the Octavius, and in Cyprian's letters by others, the summary is today the only text naming the speaker, so removal must come with C-01 and C-02.

Verified: counts with two patterns (163 narrow, 200 broad); Sol's 175 is the right reading.
- **Owner:** 1.8a, coordinated with C-01 and C-02.
- **Check:** `editorial.argument_lines`.

**C-13. Canon-law chapter keys merge unrelated titles, and 100 more canons show the wrong chapter number.** Sources: Opus A-006, Sol A-002, Sol B-003.
- 17 keys appear in separate runs, covering 209 canons; e.g. Book IV "Title I" holds baptism, sacramentals and sacred places.
- It affects the reader and dedup's per-chapter cap.
- Separately, 100 Book VII canons in contiguous runs (1481–1490, 1496–1500, 1507–1512, 1539–1586, 1596–1597, 1628–1640, 1645–1648, 1720–1731; 13 saved rows) say "Chapter I" where the source's table of contents gives II to VI, because the parser forward-fills the last chapter number (Sol B-003). A contiguity check cannot see this.

Verified: 17 and 209, in both live and build; the wrong "Chapter I" on canons 1481, 1547 and 1584.
- **Owner:** 1.5a. Keys are built from the full Book/Part/Section/Title/Chapter path, with chapter redirects.
- **Check:** `structure.chapter_contiguous`.

**C-14. The 1.7 Summa spec needs rework before it is built.** Sources: Sol A-012, A-014, A-015, A-016, A-017, A-018 and Opus-2 B-011.
1. Its bold-only paragraph walk would turn an unbold sed contra (II-II q.23 a.2) into part of objection 3 (Sol A-016).
2. Its acceptance check "at most 1 article lacks I answer that" cannot pass. Verified: I q.91 a.4 and q.117 a.2 have a sed contra and then replies with no determination, and q.74 a.3 has no sed contra (Sol A-014).
3. The vendored Summa itself lacks two argument units, I q.76 a.3 objection 3 and I q.89 a.3's second sed contra. Verified for q.76: the embryo argument is absent among the objections and present in the replies (Sol A-018).
4. 27 pieces carry wrong source numbers or unrecognised "Reply OBJ" markers (Sol A-015).
5. 14 replies answer a counterargument under "On the contrary" and cannot be stitched (Sol A-017).
6. One sed contra is duplicated in the source (I-II q.20 a.6). Verified identical (Sol A-012).
8. Three more articles lack their whole sed contra in the vendored English and in New Advent, though the Leonine Latin has it: I-II q.88 a.4, II-II q.182 a.4, III q.7 a.10 (Sol B-002). Verified: each goes from its last objection straight to "I answer that". With item 3 that makes five units the source edition omits; recovering them needs an existing English edition, since TheoCorpus makes no translations.
9. 39 pieces labelled with one reply also contain a separate prose reply to a different objection or to a counterargument, including five joint replies (Sol B-005). Verified: the I q.62 a.4 example. 1.7 needs real reply-target metadata, not one number per piece.
7. 1.7's new short citation ("Summa Theologiae I, q. 19, a. 9, ad 1") removes the article's question from `reference`, the only provenance field the rerankers, the explanation model and the card read (Opus-2 B-011).

- **Owner:** 1.7.
- **Check:** each finding names one. A fuller comparison against the Leonine edition is open (section 5).

**C-15. Credits and citations disagree after the planned relabels.** Sources: Opus-2 B-003 and B-013, Opus A-008, A-009 and A-016, Sol B-004.
- **Credits frozen into citations:** every Fathers and medieval `reference` embeds the author ("Clement of Rome — First Epistle…"), and so does the embedding prefix. 3.2's relabels (for example "Pseudo-Justin") change `author` but leave the old name in the citation and the vector.
- **Martyrdoms credited to their martyrs:** the Martyrdom of Polycarp (22 passages) and of Justin (5) are credited to the martyrs. Opus and the Sol supplement found this independently; the source names the Church of Smyrna (writer Evarestus) and calls Justin's narrator unknown (verified).
- **Fragments framed by another writer:** fragment collections open with the quoting Father's framing; Papias's open with Eusebius (verified).
- **A work hidden inside another:** Lactantius's Epitome is cited as "Divine Institutes, Chap. I…" (verified).
- **A title collision:** after 1.10a strips periods, two documents are titled "Fragments", which dedup treats as one source (verified).

- **Owner:** 1.10c (references and prefix from the registry credit), 3.2 (martyrdoms, fragments), 1.8c (Epitome) and 1.10a (titles).
- **Check:** `labels.reference_author_consistent` and `registry.unique_title_per_collection`.

**C-16. Keyword search cannot match common forms.** Sources: Opus A-007 and A-020, Opus-2 B-014, Sol A-005 and A-010.
- **What the index sees and misses:** `search_vector` is `to_tsvector('english', content)`. It indexes verse markers and note numbers as words, never sees references ("canon 1055", "CCC 2267"), and cannot match:
  - ligatures ("Irenæus"; 2,051 live passages have æ or œ);
  - archaic verb forms ("loveth");
  - 18 canons whose source has `V`/`Y` in place of "ff"/"ffi" ("diVerent", "suYcient");
  - about 155 words broken by a line-end hyphen ("pre- cisely").
- **Verified:** the generated-column definition, the 18 canons, the ligature count and the hyphen samples. The query results ("John 3:16" matching Maccabees) are the reviewers' local Postgres runs.
- **Owner:** 2.2c, reopened (strip markers, add the reference at lower weight, inside the 4.0 compaction window); 1.10a (ligatures, hyphens); 1.5a (canon spellings).
- **Check:** reference sentinels and `fts.no_marker_tokens`.

### Medium

**C-17. Footnote numbers left in papal and Vatican II texts.** Sources: Opus A-012, Opus-2 B-005.
- The forms are "(35)", "points out.9", "…universe". 83", "[ 3 ]" and Lumen Gentium's "(21*)".
- About 950 to 1,100 passages are affected, with 190 saved rows.

Verified: the Veritatis Splendor example; a broad pattern gives 1,086.
- **Owner:** 1.3a (drop `<sup>` callers) and 1.1.
- **Check:** `health.R12_note_caller`.

**C-18. Editors' matter in papal documents.** Source: Opus A-010.
- Haerent Animo §1 is an editor's introduction.
- Menti Nostrae's preamble is a translation credit.
- Africae Munus §1 is its table of contents.

Verified: all three.
- **Owner:** 1.3a.

**C-19. Canon-law defects 1.5a's patterns miss.** Source: Opus A-013.
- Canon 297 ends with a page footer.
- Canons 111, 237, 535, 604, 688, 699 and 775 carry `n§` mid-text.
- 112 canons have line breaks inside sentences.

Verified: all three.
- **Owner:** 1.5a.

**C-20. Vatican II chapters missing from the reader.** Source: Opus-2 B-009.
- Lumen Gentium jumps from Chapter VI to VIII, and Sacrosanctum Concilium from V to VII.
- Gaudium et Spes repeats "Chapter I".

Verified: the LG and SC outlines.
- **Owner:** 1.1.
- **Check:** `structure.chapter_sequence`.

**C-21. Unsearchable passages still shape their neighbours' vectors.** Source: Opus-2 B-012.
- The neighbour window ignores `searchable`. So history passages (CCC 2267's 1997 text, superseded canons) and Latin canons would be embedded into the vectors of the current text beside them.
- **Owner:** 2.2w.
- **Check:** a unit test on `build_embedding_input`.

**C-22. Ten-plus misc ThML labelling defects.** Sources: Opus A-014, A-022, Opus-2 B-010.
- The editor's provenance lines in the Hippolytus and other fragments.
- About 56 to 78 mis-cased Roman numerals in labels ("Ii.", "Vi.").
- 39 Summa passages with stray `[N]` cross-reference numbers (verified).

- **Owner:** 1.8a, 1.9 and 1.7.

**C-23. Embedding provenance is not recorded.** Source: Sol (coverage).
- Nothing records which text produced each vector, so a vector built from the wrong text (the old 86) can only be inferred.
- **Owner:** 2.2w. Store an input hash, the model and the dimensions per point at the republish.
- **Check:** `index.embedding_input_hash`.

**C-24. Song of Songs rename breaks hard-coded lists.** Source: Opus-2 B-015.
- `SourcesPage.tsx` `BOOK_ORDER` and the `evaluate.py` prompt name "Song of Solomon" (verified).
- **Owner:** 1.4a or 2.4b.

### Low

**C-25. About page claims beyond 2.4c's fix.** Source: Opus A-015. Owner 2.4c.

**C-26. Very large single reader chapters in papal documents.** Source: Opus A-017. Novo Millennio Ineunte has about 99,000 characters in one chapter. Owner 1.3a, with C-08.

**C-27. Lowercase-start Summa fragments** ("stands the authority of Scripture."). Source: Opus A-018. Owner 1.7.

**C-28. Docs describe Qdrant collections that do not exist.** Source: Opus A-023. Production has only `chunks` (verified), and `stages/embed.py` deletes from `facets`/`questions` on every run. Owner: docs, and 2.2w.

**C-29. Summa reply numbers with no matching objection, from the source edition.** Source: Opus A-024. Owner: none beyond 1.7 updating the stitching docstring count.

**C-30. Rare broken entity and soft hyphens.** Source: Opus coverage. The Syllabus has one `&quuot;`; the 43 soft hyphens fall in removed works. Owner 1.3a.

## 3. Saved user data

From the reviewers' joins against `references.json`, spot-checked:
- **C-01:** the condemned propositions hold 6 saved rows.
- **C-04 and C-07:** about 3 rows.
- **C-11:** the first passages of the 117 Psalms with titles hold 49 retrievals, 3 bookmarks and 3 guest rows. Their text gains the title; their IDs do not change.
- **C-17:** about 190 rows. The text is cleaned in place under the same IDs.
- **C-10:** 702 rows on split pieces, at risk once boundaries move.

No finding requires deleting a saved row. Every fix keeps IDs (D1), retires with a tombstone (D3), or redirects.

## 4. Disagreements and how they were settled

- **The 12 identical vectors.** Opus said at least one vector of each pair was built from another passage's text. Sol said the inputs are identical. I rebuilt the embedding input for all six pairs with `writers/search_writer.build_embedding_input` on the live passages. All six pairs have byte-identical inputs, because both passages are shorter than the neighbour window and each includes the other in full. Sol is right: the vectors are not corrupt. The defect is the design: the window swamps short passages. It is now part of C-09.
- **How many "Argument" summaries.** Opus counted 43, Opus-2 163 and Sol 175. Opus-2's pattern misses the "Chapter I. Argument.—" form used in Novatian's works, and Sol's includes two Banquet chapter titles. The number that matters, summaries in works that stay with no owner, is about 136 (C-12).
- **Severity of the Summa structure findings.** Sol rates several "critical". I rate the role inversions and the editor's text critical (C-04), the merged articles critical (C-07), and the rest of the 1.7 issues high as one finding (C-14). They are few passages each, and stitching already attaches nothing to them, which is the safe failure.
- **Whether the index is healthy.** All three agree: no orphans, no missing points, and payloads equal Postgres except the 21 known blank Summa rows. I re-read three vectors from production and they match Opus's dump.

## 5. Still unverified, and what it would take

- **The Supplement of the Summa** has not been compared with any independent edition. The Sol supplement's bulk attempt was blocked (HTTP 403), so its empty result proves nothing.
- **Stored reader outlines.** Nobody has checked that `document_chapters` rows match the passages, only that `chunk_count` does (all 421 match). This needs either a read-only SELECT against production (Sol gives the exact query) or adding `document_chapters` to the next snapshot export. Both need Carter's approval.
- **The Summa against an independent edition.** Sol built an inventory of the four core parts against the Leonine Latin (Corpus Thomisticum) and found 263 discrepancy candidates. Only some are dispositioned so far, and the Supplement is not compared. Two real omissions are already proven (C-14 item 3), so the rest should be worked through before Phase 4.
- **The full canon-law hierarchy.** Only the 17 non-contiguous keys are proven. Wrong labels on contiguous runs (canon 265 under the wrong heading) suggest more.
- **Retrieval of reference-style questions by vector.** This needs about $0.001 of embeddings, which no reviewer ran.

## 6. Questions for Carter

Each needs an answer before the owning spec can be edited. Recommendations are mine, after reading all three reports.

1. **Should condemned propositions and opponents' speeches be labelled and stay searchable, or move to the reader only?**
   - Recommended: label them (for example "Condemned proposition 10", "Caecilius, pagan objection; answered by Octavius") and carry the label to the rerankers, the explanation prompt and the card, as the Summa's objections already are.
   - Until that ships, keep them out of search.
2. **Should Novatian's Epistle XXX be removed under rule A, and how should the other 15 letters to Cyprian be credited?**
   - Recommended: remove XXX, and have R1 check XXIX.
   - Credit the rest per letter through D6's work model (for example "Firmilian of Caesarea, to Cyprian").
3. **Should a split piece's ID follow its text when piece boundaries move?**
   - Recommended: yes. Use a per-piece stability check, and redirect a shifted piece to the piece now holding its opening text.
4. **Should the dedup threshold or the neighbour window change before the republish embeds everything?**
   - Recommended: test a 0.97 threshold for chapter-keyed collections in 4.2's comparison, which needs no new embeddings.
   - Store a clean-text hash for later.
5. **Should keyword search drop verse markers and index references?** Recommended: yes, in the 4.0 compaction window.
6. **Should the Summa's new citations keep the article's question?** Recommended: yes ("… q. 64, a. 6, co.: Whether it is lawful to kill the innocent?").
7. **Should Psalm titles and the Sirach prologue be restored?** Recommended: yes, the titles as the unnumbered opening of each psalm and the prologue as its own passage.
8. **Should the Catechism fix go first as its own small PR?** Recommended: yes. Text changes under existing anchors, so no IDs move.
9. **May the stored reader outlines be checked?** Recommended: add `document_chapters` to the next snapshot export rather than running a separate query.
10. **Should Phase 4 wait for the full independent Summa comparison?** Recommended: yes, for the four core parts and the Supplement.
11. **Should the five Summa units the source edition omits block publication of their articles until an existing English edition supplies them?** Recommended: yes, recover them alongside 1.7 without making a translation; if none can be found, publish with a reader note saying the unit is missing.

## 7. Suggested next step

Turn the approved answers into spec edits, one commit per item, with the new checks added to 0.1a, 0.1b or 0.1c as each finding names. Most findings extend Phase 1 items already in the plan: 1.1, 1.3a, 1.4a, 1.5a, 1.6, 1.7, 1.8a, 1.8c, 1.10a, 1.10c, 2.2c, 2.2w, 3.1 and 3.2.

Three need new items or design decisions first:
- the rejected-voice role (C-01);
- the piece stability rule (C-10), which belongs with 2.1, the next item in the plan;
- the dedup and embedding decision (C-09), which must land before 4.1b.
