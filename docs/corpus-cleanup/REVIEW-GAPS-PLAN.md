# Closing the corpus-review gaps: plan

9 October 2026. Working file for the planning thread that turns the 6 October corpus reviews into planned work before 2.1 starts. Input: `docs/research/2026-10-06-corpus-review-synthesis.md` (findings C-01 to C-30) and the four reviews it merges. This file decides, for every finding, which item owns it, when, and with which check. It changes no spec by itself. The spec edits follow Carter's answers to section 7, one commit per item, on branch `docs/review-gaps`.

Status: **decided.** Carter answered on 9 Oct 2026: yes to all six questions and all nine defaults in section 7. The answers are in `NEEDS-CARTER.md` (entry "Review gaps") and the plan's Decision log, and the specs now state them. The issue changes are drafted in `ISSUES-DRAFT.md`.

Nothing here re-audits the corpus. I re-checked four facts because a planning decision turned on them, listed in section 9.

## 1. The short version

Only three findings change what 2.1 freezes, and all three land in 2.1's own spec:

1. **Split pieces (C-10).** Today a piece is named by its number (`…/p2`), so when text is added or removed upstream, `/p2` silently starts holding different paragraphs. 2.1 should name each piece by the first source paragraph it holds, and the release report should compare pieces one by one. Then a saved piece always reopens on its own opening paragraph, and a piece whose opening paragraph moved gets a redirect like any other moved unit.
2. **Summa anchors (C-04, C-07, C-14).** 2.1's spec builds Summa anchors from the part labels ("Objection 2", "Reply to Objection 3"). The reviews show those labels are wrong in dozens of places, so freezing anchors on them would freeze the errors or force 2.1 to wait for 1.7's role model. Every Summa paragraph already has a source ID (`SS_Q64_A7-p13`; 44,262 of 44,394). Anchoring on that ID makes 2.1 independent of the role model, and the role fixes in 1.7 become label changes that keep IDs.
3. **A role for rejected voices (C-01).** D11 says passage fields are defined once, in 2.1. A condemned proposition or a pagan's speech needs a field that tells the rerankers, the explanation model and the card "this is a position the document rejects". 2.1 adds it beside `searchable`, `language` and `passage_author`.

Everything else extends an item that already exists, plus six new items: a checks PR (0.1d), a research item for the Summa against an independent edition (R7), a Catechism text fix ahead of 1.6 (1.6a), the rejected-voice registry ranges (3.4), the API and web side of that role (2.4d), and one retrieval follow-up for the dedup threshold (RF-1).

## 2. Where this plan disagrees with the starting position or the synthesis

- **C-07 needs no new IDs.** The synthesis and the starting position give the three trailing Summa articles "new IDs, plus redirects". Under D1 an ID names a unit of text, and these passages' text does not change; only their citation and chapter are wrong. With paragraph-ID anchors (Q3) they keep their IDs, change chapter and citation in 1.7, and need no redirect. A saved "a.7" passage that is really a.8 reopens on the same words, correctly cited.
- **C-13 is not a 2.1 dependency.** 2.1 freezes passage IDs and anchors, not chapter keys. Canon anchors (`can/N`) do not change. Chapter redirects are computed once, at the Phase 4 stage, from 0.1c's chapter remap against live, however many times 1.5a changes keys before then. So C-13 is an ordinary 1.5a extension.
- **C-02 and C-15 are not 2.1 dependencies either.** 2.1's work model (D6) already has `Work.author`, so one work per Cyprian letter with its real sender fits the shape 2.1 ships. The citation and embedding-prefix fixes belong to 1.10c (which rebuilds every reference) and 2.2w (which builds the embedding input).
- **C-04 and C-14 do not have to be settled before 2.1** if Q3 is accepted. They stay 1.7's work, blocked by the new R7.
- **C-23 is mostly planned already.** 2.2w stores `embed_sha256`, the hash of the exact embedding input, on every point of the new collection. What is missing is a record of the model and dimensions, which is a small 2.2w addition.
- **C-09: only the embedding input must be decided before 4.1b.** The dedup threshold is an API constant (`_COSINE_THRESHOLD = 0.9` in `services/api/app/rag/dedup.py`) and needs no new embeddings, so it can be tested in 4.2 and changed afterwards. What would force a second embedding run is a change to the neighbour window, and the recommendation is not to change it beyond C-21's fix.
- **C-24's owner should be the web and API, not 1.4a.** 1.4a is datapipeline-only and reaches users at P4, but `SourcesPage.tsx` and `evaluate.py` deploy on merge. If they switch to "Song of Songs" before P4 they break today's sort. They must accept both names, which is 2.4b's and 2.4a's job.
- **Two gaps the synthesis dropped:**
  - **G-1. Editors' chapter titles printed at the top of passages.** About 1,669 "Chapter N.—Title" lines open passages in 16 documents (Opus A-011). City of God's are the ancient Latin capitula and stay. On the Trinity's, On Christian Doctrine's, the Banquet's and Tertullian's two remaining works' (about 640 lines) are later editors' titles. 1.8a deferred this "as its own decision after P1" and no item owns it (Opus-2 question 6).
  - **G-2. The web parses the Summa citation.** `ChunkCard.tsx:mobileCitation` extracts "Question N … Article N" from the Summa reference. 1.7's new citation ("q. 64, a. 6") breaks that regex on mobile, whatever Q-default 6 decides (Opus-2 B-011). On desktop, `primaryReference` prepends the title to Fathers references that already contain it (Opus-2 B-003). Both are 2.4b's.
- **C-02: R1 should check more than Epistle XXIX.** Sol A-007 notes that each newly identified sender (Cornelius, the Roman clergy, the confessors, Firmilian and others) needs the same rule A check as any author; the synthesis mentions only XXIX.
- **Q1's interim ("keep them out of search until the role ships") is moot under D7.** Nothing reaches live data before the Phase 4 apply, so the role and the passages ship together. The fallback only matters if 3.4 or 2.4d miss the P4 build; then the registry sets `searchable = false` on the listed ranges for that build.

## 3. What must finish before 2.1 starts, in order

1. Carter's answers to section 7, recorded in `NEEDS-CARTER.md` and, where they settle a rule, in the plan's Decision log.
2. The docs PR from this branch, merged. It holds:
   - the plan's phase table, Decision log rows and the one-line D11 change for `voice` (if Q1 is a);
   - 2.1's spec: paragraph-ID anchors for the Summa (Q3), first-unit anchors for split pieces and the per-piece stability rule (Q2), the `voice` field and its registry override (Q1), and the three 2.1 pairing rules that follow;
   - every other spec extension in section 4, and the new item specs in section 5;
   - the review files, if Carter agrees (Q6).
3. Carter's yes on the issue changes in `ISSUES-DRAFT.md`, then the issues opened and edited.

Nothing else blocks 2.1. R7 is research and can start the same day as 2.1; it blocks 1.7, not 2.1. 0.1d goes after 2.1, because most of its check IDs are keyed by anchor and 2.1 changes anchors (0.1b "As built": an item that changes anchors must re-key `health.` entries).

2.1's own open "Needs Carter" entries (anchor character mapping, the public passage registry, the removal registry format, `rolled-back`, the 408 Summa pairings, First Lateran, the 163-passage reading) stay where they are, for 2.1's implementer to ask under README §1.

## 4. Every finding

"Check" names the check id the owning item or 0.1d adds; section 6 lists them with their planned `known_defects.json` entries. "Q" refers to section 7. "default" means a recommended answer Carter is told about and can overturn.

| C | Sev. | Decision | Owner(s) | Order and dependency | Check | Waits on |
|---|---|---|---|---|---|---|
| C-01 rejected voices without a role | crit. | pre-2.1 spec change, plus two new items | 2.1 defines `Passage.voice`; 2.2a adds `chunks.voice`; 2.2w stages it and writes it to the payload; **3.4** records the ranges; **2.4d** carries it to rerankers, explanation and card. 1.3a (Syllabus and Exsurge boundaries), 1.2a (list the Nestorius letter as "condemned text read at the council"), 1.2e (Constance in Schroeder), 1.7 (sets `voice` on objections), 1.8a and 1.8c (Octavius, Acts of Archelaus) consult it | 2.1 before P1. 3.4 after 2.1; its Constance ranges after 1.2e. 2.4d deployed before 4.1b | `roles.rejected_voice` (3.4), `roles.voice_reaches_model_inputs` (2.4d) | Q1 |
| C-02 letters to Cyprian, one by Novatian | crit. | extension | 1.8c: one work per letter, credited to its sender ("Firmilian of Caesarea, to Cyprian"). 3.1: `rule-a` passage entries for Epistle XXX's 5 anchors, plus a research step (R1's method) on XXIX and on each sender. 3.2: credit wording | 1.8c in P1; 3.1 in P3 | `attribution.letter_sender` (0.1d, fixed_by 1.8c); 3.1 registry test that no Novatian passage stays active | default |
| C-03 Catechism drops text, incl. CCC 1471 | crit. | new item | **1.6a**; 1.6 then works on complete text | first P1b PR; after 2.1 and 0.1d; before 1.6 | `coverage.catechism.paragraph_words:<n>`, `sentinel.ccc_1471_definition` (0.1d) | default |
| C-04 Aquinas's answer mislabelled or mixed with an editor's | crit. | extension | 1.7: a reviewed corrections file for roles; editorial scope excluded before roles are assigned; III q.26 a.2's editorial section and I-II q.102 a.6 ad 10 (Nicolai's reconstruction) removed under rule G, their judgments copied first; the four "The contrary, however" sed contras separated | after R7 | `roles.summa.objection-after-replies`, `roles.summa.variant-sed-contra-boundaries`, `attribution.summa.editor-supplied-replies` | Q3, Q5 |
| C-05 site adverts and secondary-source text | crit. | extension | 1.2b (Trent `sec-0/21`), 1.3a (Cum Sancta Mater `/4` tail; Exsurge `41/p3` braces and webmaster note as `rule-g-editorial` spans), 2.3 (Cum Sancta Mater year 1859) | P1, P2 | `health.R10_site_boilerplate`, block (0.1d) | none |
| C-06 Syllabus §80 swallows other text | crit. | extension | 1.3a: the Syllabus body ends after §80; the appended extracts get removal entries | P1 | `structure.syllabus_body_boundary` (0.1d) | none |
| C-07 three Summa keys hold two articles | crit. | extension; IDs kept (section 2) | 1.7: the corrections file splits `SS_Q64_A7`, `SS_Q66_A5`, `SS_Q123_A10`; the trailing articles get their own chapter keys and citations | after R7 | `structure.summa.one-disputation-per-article` (0.1d) | Q3 |
| C-08 papal trailing headings, bucket chapters | high | extension | 1.3a: an unnumbered short line between numbered paragraphs is a heading; it moves to the start of the next section and drives chapters, as 1.1 does | P1 | `health.R9_trailing_heading`, `structure.bucket_chapters_with_headings` (0.1d) | none |
| C-09 dedup drops distinct neighbours | high | decision now; extensions; RF-1 | Decision: the republish keeps today's embedding input except C-21's fix. 2.2w's staged report computes the collision rate. **RF-1** adds the threshold as a pipeline setting and 4.2 runs it as an arm | the decision before 4.1b; RF-1's arm in 4.2; any change after cutover | `index.dedup_collision_rate` (2.2w report) | default |
| C-10 a saved piece reopens on other text | high | pre-2.1 spec change | 2.1: a piece's anchor names the first source unit it holds; 0.1c's stability check compares pieces one by one; the freeze pairs drifted pieces by text. 1.10b, 1.10c, 1.1, 1.3a, 1.6, 1.6a: a piece whose opening unit no longer opens a piece gets a redirect. 4.1a moves the user rows | 2.1 | `release.piece_stability` (2.1) | Q2 |
| C-11 Psalm titles, Sirach prologue | high | extension | 1.4a: each `\d` title becomes the unnumbered opening of its psalm's first passage; the prologue becomes `sirach/prologue`. 0.1d: the coverage extractor counts `\d` as body text | P1 | `coverage.bible.superscriptions`, `sentinel.sirach_prologue` (0.1d) | default |
| C-12 editors' "Argument" summaries | high | extension | 1.8a: 1.8b's `^Argument[.—]` pattern in ANF volumes; the editor's "Epistle N." number and title lines; 138 summaries in works that stay. The speaker signal they carry is replaced by 3.4 (Octavius) and 1.8c (letter senders) before P4 | P1; 3.4 and 1.8c in the same P4 build | `editorial.argument_lines` (0.1d) | none |
| C-13 canon chapter keys and numbers | high | extension (not pre-2.1) | 1.5a: keys from the full Book/Part/Section/Title/Chapter path, reset at each higher level, chapter numbers from the source's table of contents | P1 | `structure.chapter_contiguous:canon-law`, `structure.canon_law.chapter_number_agreement` (0.1d) | none |
| C-14 the 1.7 spec needs rework | high | extension, blocked by R7 | 1.7: recognise canonical openings without bold; allowlist the three reply-only articles; fix wrong numbers and "Reply OBJ" markers from the corrections file; keep one copy of the duplicated sed contra; store real reply targets, joint and to-the-sed-contra (default); recover the five omitted units from an existing English edition (Q5) | after R7 | `roles.summa.unbold-paragraph-openings`, `structure.summa.reply-only-articles`, `structure.summa.argument-numbering`, `context.summa.reply-targets`, `text.summa.adjacent-duplicate-parts`, `labels.summa_reference_has_question` | Q5, default |
| C-15 credits and citations disagree | high | extension | 1.10c: ThML references become "<title>, <label>", with no author. 2.2w: the embedding prefix uses the resolved display author. 3.2: Church of Smyrna for the Martyrdom of Polycarp, Anonymous for the Acts of Justin, a work note for fragment collections ("preserved in Eusebius"). 1.8c: the Epitome as its own work. 1.10a: no two titles alike in a collection. 2.4b: G-2 | P1 to P3 | `labels.reference_author_consistent`, `registry.unique_title_per_collection`, `attribution.narrative_of_author_death`, `structure.embedded_work_labelled` | none |
| C-16 keyword search misses common forms | high | reopen 2.2c; extensions | 2.2c becomes a migration: `search_vector` drops verse markers and adds the reference at lower weight, rewritten in 4.0's window. 1.10a: fold æ and œ, rejoin reviewed line-end hyphens. 1.5a: the 18 V/Y canons from reviewed overrides. Archaic verb forms go to RF | 2.2c migration ready before 4.0; run in 4.0's window, before 4.1b step 1 | `fts.no_marker_tokens`, `fts.reference_lookup`, `health.no_ligatures`, `health.R14_hyphen_space`, `text.canon_law.ligature_corruption` | Q4 |
| C-17 footnote callers | med. | extension | 1.3a (`<sup>` callers, "[ N ]"), 1.1 ("(N*)") | P1 | `health.R12_note_caller` (0.1d) | none |
| C-18 papal editors' matter | med. | extension | 1.3a: removal entries for Haerent Animo §1, Menti Nostrae's credit, Africae Munus's contents; the real first paragraph gets a never-live anchor, as Quanta Cura does | P1 | `health.R11_papal_editorial` (0.1d) | none |
| C-19 canon defects 1.5a misses | med. | extension | 1.5a: c. 297 footer, c. 230's inline "[Cf. …]" (Opus A-013, dropped by the synthesis), mid-text `n§`, broken lines | P1 | 1.5a acceptance | none |
| C-20 Vatican II chapters missing | med. | extension | 1.1 | P1 | `structure.chapter_sequence` (0.1d) | none |
| C-21 unsearchable text in neighbours' vectors | med. | extension | 2.2w: the neighbour window skips `searchable = false` passages | P2 | `index.no_unsearchable_neighbour_text` (2.2w unit test) | none |
| C-22 misc ThML labelling | med. | extension | 1.8a (fragment provenance lines, the Stromata translator credit), 1.9 (Roman numerals in the label helpers), 1.7 (stray `[N]` in `expand_apparatus`) | P1 | `editorial.provenance_lines`, `labels.roman_case`, `health.summa_bracket_numbers` (0.1d) | none |
| C-23 embedding provenance | med. | extension (mostly planned) | 2.2w: also record the model and dimensions with each publish | P2 | `index.embedding_input_hash` (2.2w report) | none |
| C-24 Song of Songs in hard-coded lists | med. | extension, owner changed | 2.4b (`BOOK_ORDER` holds both names), 2.4a (`evaluate.py` prompt names both) | before P4 | web test that every `/sources` Bible title has a rank | none |
| C-25 About page claims | low | extension | 2.4c | P2 | none | 2.4c's own approval |
| C-26 very large papal chapters | low | extension | 1.3a, with C-08 | P1 | `structure.chapter_size`, report only (0.1d) | none |
| C-27 lowercase Summa fragments | low | extension | 1.7: keep "On the contrary," and "I answer that," in the text, as printed | after R7 | `health.R13_lower_start`, report only (0.1d) | none |
| C-28 docs name absent Qdrant collections | low | extension | 2.2w's docs step corrects CLAUDE.md §4 | P2 | none | none |
| C-29 replies for absent objections | low | no action beyond a docstring | 1.7 updates the `stitch.py` count | after R7 | existing | none |
| C-30 broken entity | low | extension | 1.3a (the Syllabus "&quuot;"); the soft hyphens sit in works 3.1 removes | P1 | none | none |
| G-1 editors' chapter titles in content | high | extension | 1.8a and 1.8b: move later editors' titles from the content into the chapter label; keep City of God's capitula | P1 | `editorial.chapter_title_lines` (0.1d) | default |
| G-2 web parses the Summa citation | med. | extension | 2.4b: parse old and new Summa forms; stop doubling the title on Fathers cards | before P4 | `ChunkCard.test.tsx` cases | none |

Unverified items from the synthesis's section 5 go to: the Supplement and the 263 core candidates, R7; stored reader outlines, 0.1d; the full canon hierarchy, 1.5a's acceptance (every canon checked against the source's table of contents, Sol B-003's method); reference-style vector retrieval, 4.2's targeted questions (no separate spend).

## 5. New items

Full specs follow in the standard template once Carter answers. Summaries:

- **0.1d. Checks for the 6 October review findings.** PR, P0, after 2.1. Adds every check in section 6 that can run on a build or snapshot, each failing defect listed in `known_defects.json` with `fixed_by` and strict xfail, as 0.1a to 0.1c did. Extends `checks.report.check_scope` to the new namespaces. Adds `document_chapters` to `export_live_snapshot.py` and an outline comparison (Sol's query, run offline). Running the export against production is a separate approval when it runs.
- **R7. The Summa against an independent edition.** Research, P0, blocks 1.7. Disposition of Sol's 263 core discrepancy candidates; an independent comparison of the Supplement (by a route that is not blocked, such as a scan); for the five units the vendored edition omits (I q.76 a.3 obj. 3, I q.89 a.3 s.c. 2, I-II q.88 a.4, II-II q.182 a.4 and III q.7 a.10 s.c.), an existing public-domain English edition that has them, recorded in the rights inventory, or "none found". Output: `docs/research/R7-summa-structure.md` and the reviewed corrections file 1.7 reads.
- **1.6a. Catechism: restore dropped lines.** PR, P1, before 1.6. `is_section_header` reads `attrs.indent`; line-per-paragraph nodes are joined before header detection. Same anchors and IDs; split pieces follow 2.1's piece rule.
- **2.4d. Rejected-voice role in the API and web.** PR, P2. Reads `voice` when present. The rerank cards and the explanation prompt get the instruction that a rejected passage states a position the document rejects, added only when a card carries it, so today's prompts stay byte-identical until P4. The card and reader show a label. Deployed before 4.1b.
- **3.4. Rejected-voice ranges.** PR, P3, applied at P4. Passage-registry rows with `voice = "rejected"` and a `unit_label` text ("Condemned proposition 10"; "Caecilius, pagan objection; answered by Octavius") for Exsurge Domine §1 to §41, the Syllabus §1 to §80, Constance's condemned articles (after 1.2e), Nestorius's second letter at Ephesus, Octavius V to XIII and the Manes speeches in the Acts of Archelaus.
- **RF-1. Dedup threshold for chapter-keyed collections.** Child of #131. Adds the threshold as a pipeline setting (default 0.9, unchanged), runs 0.97 for canon law, the Catechism, the Summa and the Bible as an arm in 4.2, and ships a change only if 4.2's comparison supports it.

## 6. Checks and planned `known_defects.json` entries

Not added yet; each owning spec will describe them. "Starts failing" means the check fails on master and enters `known_defects.json` with `fixed_by` the owner.

| Check id | Added by | Starts failing on master? | fixed_by |
|---|---|---|---|
| `coverage.catechism.paragraph_words:<n>` | 0.1d | yes, at least 43 paragraphs | 1.6a |
| `sentinel.ccc_1471_definition` | 0.1d | yes | 1.6a |
| `coverage.bible.superscriptions` | 0.1d | yes, 138 titles in 117 psalms (one entry, `units` listed) | 1.4a |
| `sentinel.sirach_prologue` | 0.1d | yes | 1.4a |
| `health.R9_trailing_heading` | 0.1d | yes, about 950 passages; report-only until 1.3a, then block in papal collections | 1.3a |
| `structure.bucket_chapters_with_headings` | 0.1d | yes, 115 documents | 1.3a |
| `health.R10_site_boilerplate` (block) | 0.1d | yes, 3 passages | 1.2b, 1.3a |
| `health.R11_papal_editorial` | 0.1d | yes | 1.3a |
| `health.R12_note_caller` | 0.1d | yes, about 1,000 passages, report-only | 1.3a, 1.1 |
| `health.R13_lower_start` | 0.1d | report only | 1.7 |
| `health.R14_hyphen_space` | 0.1d | report only, reviewed allowlist | 1.10a |
| `health.no_ligatures` | 0.1d | yes | 1.10a |
| `health.summa_bracket_numbers` | 0.1d | yes, 39 | 1.7 |
| `structure.syllabus_body_boundary` | 0.1d | yes | 1.3a |
| `structure.chapter_contiguous:<collection>` | 0.1d | yes, 17 canon keys | 1.5a |
| `structure.canon_law.chapter_number_agreement` | 0.1d | yes, 100 canons | 1.5a |
| `structure.chapter_sequence` | 0.1d | yes, LG, SC, GS | 1.1 |
| `structure.chapter_size` | 0.1d | report only | 1.3a |
| `structure.summa.one-disputation-per-article` | 0.1d | yes, 3 | 1.7 |
| `structure.embedded_work_labelled` | 0.1d | yes, the Epitome | 1.8c |
| `roles.summa.objection-after-replies` | 0.1d | yes, 2 | 1.7 |
| `roles.summa.variant-sed-contra-boundaries` | 0.1d | yes, 4 | 1.7 |
| `editorial.argument_lines` | 0.1d | yes, 175 | 1.8a, 1.8b |
| `editorial.chapter_title_lines` | 0.1d | yes, by work (G-1) | 1.8a, 1.8b |
| `editorial.provenance_lines` | 0.1d | yes, 24 | 1.8a |
| `attribution.letter_sender` | 0.1d | yes, 16 letters | 1.8c, 3.1 |
| `attribution.narrative_of_author_death` | 0.1d (registry check, live from 3.2) | yes, 2 documents | 3.2 |
| `labels.reference_author_consistent` | 0.1d | passes today; fails once 3.2 relabels unless 1.10c lands first | 1.10c |
| `labels.roman_case` | 0.1d | yes, 56 | 1.9 |
| `registry.unique_title_per_collection` | 0.1d | fails after 1.10a ("Fragments" twice) | 1.10a |
| `text.canon_law.ligature_corruption` | 0.1d | yes, 18 canons | 1.5a |
| `text.summa.adjacent-duplicate-parts` | 0.1d | yes, 1 | 1.7 |
| `release.outline_matches` (stored `document_chapters` against derived) | 0.1d, on the next snapshot | unknown until the export runs | the item that owns any mismatch |
| `release.piece_stability` | 2.1 | 44 non-Summa pieces between live and master (section 9), paired by text in the freeze | 2.1 |
| `roles.summa.unbold-paragraph-openings`, `structure.summa.reply-only-articles`, `structure.summa.argument-numbering`, `context.summa.reply-targets`, `labels.summa_reference_has_question`, `attribution.summa.editor-supplied-replies` | 1.7, with fixtures | new behaviour, tested in the PR that builds it | 1.7 |
| `roles.rejected_voice` | 3.4 | registry test | 3.4 |
| `roles.voice_reaches_model_inputs` | 2.4d | API test | 2.4d |
| `fts.no_marker_tokens`, `fts.reference_lookup` | 2.2c | local Postgres test | 2.2c |
| `index.dedup_collision_rate`, `index.embedding_input_hash`, `index.no_unsearchable_neighbour_text` | 2.2w | report sections and a unit test | 2.2w |

## 7. Questions for Carter

Sent in one message on 9 October 2026. **Answered 9 October 2026: yes to every question and every default below.**

- **Q1.** Should condemned propositions and opponents' speeches stay in search with a "rejected voice" label, or move to the reader only?
- **Q2.** Should a split piece's ID follow its own opening paragraph when piece boundaries move?
- **Q3.** Should 2.1 anchor Summa passages on the source's paragraph IDs instead of on the part labels?
- **Q4.** Should keyword search drop verse markers and index references, at the cost of one table rewrite in 4.0's maintenance window?
- **Q5.** Should Phase 4 wait for the full independent Summa comparison (R7), and should articles missing a unit wait for an existing English edition?
- **Q6.** May the four review reports, the synthesis and the two prompt files be committed with this plan?

Defaults taken unless Carter objects (each is a synthesis question or a reviewer recommendation):

- Epistle XXX is removed under rule A, like Novatian's other works; the other letters are credited per letter to their senders; R1's method checks XXIX and each sender (synthesis Q2).
- The Summa's new citations keep the article's question (synthesis Q6).
- Psalm titles and the Sirach prologue are restored (synthesis Q7).
- The Catechism fix goes first as its own PR, 1.6a (synthesis Q8).
- Stored reader outlines are checked from the next snapshot export, not by a separate query (synthesis Q9).
- Dedup: no change to the embedding input before the republish beyond C-21; the threshold is tested in 4.2 as RF-1 (synthesis Q4).
- Later editors' chapter titles move from the content into the chapter label (G-1).
- 1.7 stores real reply targets, including joint replies and replies to the sed contra (Sol supplement Q2).
- Fragment collections get a work note ("preserved in Eusebius, Church History") for P4; per-span credits later (Opus Q4).

## 8. Phase table after the change

Changes in bold.

| Parent | Children, in merge order |
|---|---|
| P0 | 0.0; 0.4; 0.1a; 0.1b; 0.1c; 0.2; 2.1 **(extended: Summa paragraph anchors, first-unit piece anchors and per-piece stability, the `voice` field)**; **0.1d checks for the review findings, with `document_chapters` in the snapshot**; 0.3; 0.5; 0.6 |
| P0 research | R1 to R6 (closed); **R7 the Summa against an independent edition (blocks 1.7)** |
| P1 | 1.10a; 1.10b; 1.10c; 1.1; 1.3a; 1.3b; 1.5a; 1.5b; 1.4a; 1.4b; 1.4c; 1.2a; 1.2b; 1.2c; 1.2d; 1.2f; 1.2e; **1.6a Catechism dropped lines**; 1.6; 1.7 **(after R7)**; 1.8a; 1.8d; 1.8b; 1.8c; 1.8e; 1.9. 1.6a has no dependency on 1.10 and may go first |
| P2 | 2.4c; 2.2a; 2.2w; 2.2b; 2.2c **(now a migration, run in 4.0's window)**; 2.3; 2.4a; 2.4b; **2.4d rejected-voice role in API and web** |
| P3 | 3.3; 3.2; 3.1; **3.4 rejected-voice ranges** |
| P4 | 4.0 **(also runs the 2.2c rewrite)**; 4.1a; 4.2 **(with the RF-1 arm)**; 4.1b; 4.2 again |
| P5 | unchanged |
| RF | **RF-1 dedup threshold**; archaic verb forms (Opus A-020); stitching reads 1.7's reply targets |

## 9. Facts re-checked for this plan

Each was checked because a decision turned on it.

- Summa paragraphs have source IDs: 44,262 of 44,394 `<p>` in `sources/summa/summa.xml`, and II-II q.64 a.8's title is `SS_Q64_A7-p13`, inside a.7's div. (Q3, C-07.)
- ThML paragraphs mostly have source IDs: all 6,896 in `apostolic fathers.xml`, 5,547 of 5,682 in `city-of-god.xml`, 1,203 of 1,247 in the Imitation. A piece anchor can name its first paragraph by ID, and by its ordinal in the source div where no ID exists. (Q2.)
- Per-piece drift today: comparing each live non-Summa piece with the master-build passage of the same ID, piece by piece (8-word shingles, the larger of the two containments), 44 of 6,699 fall below 0.5: medieval 37, exhortations 3, encyclicals 3, councils 1. 7 of them hold 17 saved rows. So the per-piece rule adds about 44 pairings to 2.1's freeze, beside the 408 Summa ones. Script in this session's scratchpad, run on `datapipeline/releases/local/review-opus/corpus.pkl`. (Q2.)
- Roles reach the models only through `unit_label`, via `services/api/app/rag/steps/passage_role.py:display_role`, and the dedup threshold is the constant `_COSINE_THRESHOLD = 0.9` in `rag/dedup.py`. (Q1, C-09.)
