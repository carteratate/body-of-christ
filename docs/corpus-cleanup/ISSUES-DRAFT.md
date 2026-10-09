# GitHub issue changes for the 6 Oct 2026 review findings (draft)

9 October 2026. Drafts only: no issue has been created, edited or commented on. Carter approves every change before it is made (`NEEDS-CARTER.md`, section A, "Plan, all phases").

The cleanup issues were opened on 29 Sep 2026: 80 issues labelled `corpus-cleanup`, parents #132 (P0), #143 (P0 research), #150 (P1), #176 (P2), #185 (P3), #189 (P4), #194 (P5), and #131 for retrieval follow-ups. Children are linked to their parent as GitHub sub-issues and open with "Part of #N". This file follows the same template. Spec links resolve once branch `docs/review-gaps` merges.

Three parts:

1. Six new child issues, one per new item.
2. Changes to existing item issues: a body edit where the item's type or dependencies changed, otherwise one comment listing the scope it gained.
3. Parent issue edits, where a parent's order text names its children.

Every issue keeps the label `corpus-cleanup`.

## 1. New child issues

Each is created with the label `corpus-cleanup` and added as a sub-issue of its parent.

### 1.1 `[0.1d] Checks for the 6 Oct 2026 review findings`, sub-issue of #132

```markdown
Part of #132

**Spec:** [P0-checks-identity-research.md § 0.1d](https://github.com/carteratate/body-of-christ/blob/master/docs/corpus-cleanup/P0-checks-identity-research.md#01d-checks-for-the-6-oct-2026-review-findings)

**Type:** PR

**Depends on (per spec):** 2.1 (most check IDs are keyed by anchor, and 2.1 changes anchors), 0.1a, 0.1b, 0.1c. Merges before any Phase 1 PR.

**Goal:** Every defect the 6 Oct corpus reviews found that a check can see is measured before Phase 1 starts: each failing check is a `known_defects.json` entry with `fixed_by` its owning item, run as a strict xfail. The next snapshot export also copies `document_chapters`, so the stored reader outline is compared with the passages for the first time.

Findings: C-03, C-05 to C-08, C-11 to C-13, C-15 to C-17, C-20, C-22, C-26, C-27 (`docs/corpus-cleanup/REVIEW-GAPS-PLAN.md`, section 6).

---
Plan: [docs/2026-09-28-corpus-cleanup-plan.md](https://github.com/carteratate/body-of-christ/blob/master/docs/2026-09-28-corpus-cleanup-plan.md) (merged in #130). Before starting, follow [`docs/corpus-cleanup/README.md`](https://github.com/carteratate/body-of-christ/blob/master/docs/corpus-cleanup/README.md) and ask Carter this item's open entries in [`NEEDS-CARTER.md`](https://github.com/carteratate/body-of-christ/blob/master/docs/corpus-cleanup/NEEDS-CARTER.md).
```

### 1.2 `[R7] The Summa against an independent edition`, sub-issue of #143

```markdown
Part of #143

**Spec:** [P0-checks-identity-research.md § R7](https://github.com/carteratate/body-of-christ/blob/master/docs/corpus-cleanup/P0-checks-identity-research.md#r7-the-summa-against-an-independent-edition)

**Type:** research

**Depends on (per spec):** none; blocks 1.7.

**Goal:** Before 1.7 rebuilds the Summa, every place where the vendored English text differs in structure from an independent edition is dispositioned: the 263 core discrepancy candidates the 6 Oct review found, and a comparison of the Supplement. The five units the vendored edition omits get an existing English edition or are recorded as missing. The output includes `ingest/summa_corrections.json`, the reviewed role and target file 1.7 builds from.

Findings: C-04, C-07, C-14.

---
(plan footer as above)
```

### 1.3 `[1.6a] Catechism: restore dropped lines`, sub-issue of #150

```markdown
Part of #150

**Spec:** [P1b-adapters-catechism-summa-fathers.md § 1.6a](https://github.com/carteratate/body-of-christ/blob/master/docs/corpus-cleanup/P1b-adapters-catechism-summa-fathers.md#16a-catechism-restore-dropped-lines)

**Type:** PR

**Depends on (per spec):** 0.4, 2.1, 0.1a, 0.1c, 0.1d. Not on 1.10, so it may be the first Phase 1 PR.

**Goal:** Every word of every numbered Catechism paragraph reaches a passage. "What is an indulgence?" finds the Catechism's definition in CCC 1471, CCC 2053 no longer stops at "give to the", and the liturgical prayers the Catechism quotes are in the text. Anchors and IDs do not change.

Findings: C-03.

---
(plan footer as above)
```

### 1.4 `[2.4d] Rejected-voice role in the API and web`, sub-issue of #176

```markdown
Part of #176

**Spec:** [P2-P3-schema-reader-policy.md § 2.4d](https://github.com/carteratate/body-of-christ/blob/master/docs/corpus-cleanup/P2-P3-schema-reader-policy.md#24d-rejected-voice-role-in-the-api-and-web)

**Type:** PR

**Depends on (per spec):** 2.1, 2.2a, 2.2w, 2.4a, 2.4b. Must be deployed before 4.1b.

**Goal:** A passage that states a position its document rejects (a condemned proposition, a pagan's or a heretic's speech, a Summa objection) reaches the rerankers, the explanation model, the result card and the reader with that role, so it is never presented as the Church's or a Father's teaching. Prompts stay byte-identical until a passage carries the field.

Findings: C-01.

---
(plan footer as above)
```

### 1.5 `[3.4] Rejected-voice ranges`, sub-issue of #185

```markdown
Part of #185

**Spec:** [P2-P3-schema-reader-policy.md § 3.4](https://github.com/carteratate/body-of-christ/blob/master/docs/corpus-cleanup/P2-P3-schema-reader-policy.md#34-rejected-voice-ranges)

**Type:** PR (passage-registry values). Takes effect at the Phase 4 apply.

**Depends on (per spec):** 2.1, 2.2a, 2.2w, 1.3a, 1.8a, 1.8c, and 1.2a, 1.2c and 1.2e for council anchors. Visible only with 2.4d.

**Goal:** About 270 passages that state a position their document rejects carry `voice = "rejected"` and a label saying whose position it is and who rejects it: Exsurge Domine §1 to §41, the Syllabus §1 to §80, Constance's condemned articles, Nestorius's letter at Ephesus, Caecilius in the Octavius, and Mani's teaching in the Acts of Archelaus.

Findings: C-01.

---
(plan footer as above)
```

### 1.6 `[RF-1] Dedup threshold for chapter-keyed collections`, sub-issue of #131

```markdown
Part of #131

**Spec:** [P4-P5-republish-expand.md § RF-1](https://github.com/carteratate/body-of-christ/blob/master/docs/corpus-cleanup/P4-P5-republish-expand.md#rf-1-dedup-threshold-for-chapter-keyed-collections)

**Type:** PR (a pipeline setting, default unchanged), then an arm in 4.2, then a decision.

**Depends on (per spec):** 2.2w; must merge before 4.2's pre-cutover run.

**Goal:** Test whether a 0.97 near-duplicate threshold for canon law, the Catechism, the Summa and the Bible returns distinct neighbouring passages (35.7% of nearby canon pairs and 20.5% of Summa pairs collide at today's 0.9) without letting true duplicates through, and change it only on 4.2's evidence.

Findings: C-09.

---
(plan footer as above)
```

## 2. Existing item issues

"Body edit" means replacing the line named. "Comment" is posted as written. Every comment ends with the same line, shown once here:

> Routed by [`REVIEW-GAPS-PLAN.md`](https://github.com/carteratate/body-of-christ/blob/master/docs/corpus-cleanup/REVIEW-GAPS-PLAN.md); decided by Carter on 9 Oct 2026. The spec states the details.

| Issue | Item | Change | Text |
|---|---|---|---|
| #139 | 2.1 | Comment | Scope added by the 6 Oct corpus reviews. Summa anchors come from the source's paragraph IDs, not the part labels (C-04, C-07, C-14). A split piece is named by the first source unit it holds and the release report checks each piece on its own (`release.piece_stability`); the 44 pieces that already drifted between live and master are paired by text in the freeze (C-10). `Passage` gains `voice` (C-01). |
| #151 | 1.10a | Comment | Scope added: fold æ and œ; rejoin reviewed line-end broken words; no two titles alike in a collection ("Fragments" twice after the periods go) (C-15, C-16). |
| #152 | 1.10b | Comment | Scope changed: pieces follow 2.1's first-unit rule, and the release report checks each piece on its own. A simulation of this item under numbered pieces moved 558 Fathers pieces onto other paragraphs, 67 with saved rows; under the new rule each becomes a redirect (C-10). |
| #153 | 1.10c | Comment | Scope added: ThML references drop the embedded author ("Clement of Rome — …"), so relabels and per-letter credits reach every citation (C-15); anchors follow 2.1's piece rule (C-10). |
| #154 | 1.1 | Comment | Scope added: Lumen Gentium chapter VII and Sacrosanctum Concilium chapter VI restored to the reader, Gaudium et Spes's Part II chapters prefixed, chapter labels with titles (C-20); strip the starred "(N*)" callers (C-17). |
| #162 | 1.2a | Comment | Scope added: mark council texts the council condemned rather than issued (Nestorius's second letter at Ephesus, Wyclif's and Hus's articles at Constance), so 3.4 can label them (C-01). |
| #163 | 1.2b | Comment | Scope added: `council-of-trent/sec-0/21` is a web-editor advert; drop it with a removal entry (C-05). |
| #167 | 1.2e | Comment | Scope added: list the anchors of condemned articles in the text this item builds, for 3.4 (C-01). |
| #155 | 1.3a | Comment | Scope added: unnumbered headings move to the next section and define chapters, so about 950 passages lose a glued heading and 115 documents lose bucket chapters (C-08, C-26); drop `<sup>` and "[ N ]" callers (C-17); end the Syllabus after §80 (C-06); cut the Cum Sancta Mater and Exsurge Domine site text (C-05); remove editors' matter in Haerent Animo, Menti Nostrae and Africae Munus (C-18); end Exsurge §41 and Syllabus §80 at the proposition (C-01); fix one broken entity (C-30). |
| #159 | 1.4a | Comment | Scope added: restore the 138 Psalm titles as the unnumbered opening of their psalm's first passage, and the Sirach prologue as `sirach/prologue` (C-11). The web and API strings that name "Song of Solomon" are now 2.4b's and 2.4a's (C-24). |
| #157 | 1.5a | Comment | Scope added: chapter keys from the full heading path and chapter numbers from the source's table of contents (17 merged keys over 209 canons; 100 canons showing "Chapter I") (C-13); the c. 297 footer, mid-text `n§` and broken lines (C-19); reviewed fixes for the 18 canons with V or Y for "ff" or "ffi" (C-16). |
| #168 | 1.6 | Body edit | "**Depends on (per spec):** 0.4, 2.1, 0.1a, 0.1c, 1.10 (1.10c's `piece_reference` in particular)" becomes "**Depends on (per spec):** 0.4, 2.1, 0.1a, 0.1c, 1.6a, 1.10 (1.10c's `piece_reference` in particular)". |
| #169 | 1.7 | Body edit and comment | Depends on gains "0.1d, R7". Comment: Scope reworked: roles come from R7's reviewed corrections file, then bold markers, then exact unbold openings; editorial and editor-supplied text is excluded before roles are assigned; the three two-article divs are split; replies record real targets; the five omitted units are restored from an existing English edition or flagged; citations keep the article's question; objections set `voice` (C-01, C-04, C-07, C-14, C-22, C-27, C-29). |
| #170 | 1.8a | Comment | Scope added: the 138 "Argument" summaries in works that stay and the editor's letter title lines in Cyprian's Epistles (C-12); later editors' chapter titles in the Banquet, To His Wife and On the Apparel of Women move into labels; unbracketed provenance lines in fragment collections (C-22). The PR lists every passage whose only speaker signal it removes, for 3.4 and 1.8c. |
| #172 | 1.8b | Comment | Scope added: the Benedictine editors' chapter titles in On the Trinity and On Christian Doctrine move into labels; City of God's ancient capitula stay. |
| #173 | 1.8c | Comment | Scope added: each letter in Cyprian's Epistles is a work credited to its sender, for example "Firmilian of Caesarea, to Cyprian" (C-02); the Epitome of the Divine Institutes becomes its own work (C-15). |
| #175 | 1.9 | Comment | Scope added: the label helpers keep Roman numerals in capitals ("Ii." becomes "II.") (C-22). |
| #178 | 2.2a | Comment | Scope added: `chunks.voice` (NULL or `rejected`) with its check constraint (C-01). |
| #179 | 2.2w | Comment | Scope added: the neighbour window skips unsearchable passages (C-21); the embedding prefix uses the resolved display author (C-15); `voice` and `embed_model` in the payload, the model recorded per publish (C-01, C-23); the staged report adds `index.dedup_collision_rate` and `index.embedding_input_hash` (C-09, C-23); CLAUDE.md section 4's Qdrant claim corrected (C-28). |
| #181 | 2.2c | Body edit and comment | "**Type:** decision" becomes "**Type:** PR (a migration), then ops: applied by hand in 4.0's window". Goal becomes "Keyword search stops treating Bible verse markers as words and can find a passage by its citation ('John 3:16', 'canon 1055', 'CCC 2267')." Comment: Carter chose the rebuild on 9 Oct 2026 (C-16). |
| #182 | 2.3 | Comment | Scope added: Cum Sancta Mater Ecclesia's year is 1859, not 1858; papal years are checked against their dating lines (C-05). |
| #183 | 2.4a | Comment | Scope added: the evaluate prompt names "Song of Songs (Song of Solomon)" so it reads right before and after the rename (C-24). |
| #184 | 2.4b | Comment | Scope added: the mobile citation parses both Summa citation forms (1.7 changes the format); no doubled title on Fathers cards; `BOOK_ORDER` ranks both names of the Song of Songs (C-15, C-24). |
| #177 | 2.4c | Comment | Scope added: four more claims to correct: the Fathers' period, "canonists", "post-synodal", and the papal-documents description (C-25). |
| #188 | 3.1 | Comment | Scope added: Novatian's Epistle XXX in Cyprian's Epistles is removed under rule A; a research step checks Epistle XXIX and each other correspondent under rule A (C-02). |
| #187 | 3.2 | Comment | Scope added: the Martyrdom of Polycarp credited to the Church of Smyrna and the Martyrdom of Justin to an anonymous author; a "Preserved in …" work note on fragment collections; credit wording for Cyprian's correspondents (C-02, C-15). |
| #190 | 4.0 | Comment | Scope added: the window also applies 2.2c's `search_vector` migration, which rewrites the table; measure before deciding whether `VACUUM FULL` is still needed (C-16). |
| #191 | 4.1a | Comment | Scope added: redirects for split pieces under 2.1's rule may raise the rows to move into the low hundreds (C-10). |
| #192 | 4.1b | Body edit and comment | Depends on gains "2.2c's migration applied in 4.0's window", "2.4d live" and "3.4 included". Comment: the build-freeze PR also applies the rejected-voice fallback (3.4's ranges unsearchable if 2.4d is not deployed) (C-01). |
| #193 | 4.2 | Comment | Scope added: the RF-1 dedup arm, and targeted checks for CCC 1471, Psalm 51's title, citation lookups by keyword, rejected-voice explanations, Summa article citations, Cyprian's correspondents, and reference-style questions through vector retrieval (C-01 to C-03, C-07, C-09, C-11, C-16). |
| #131 | RF | Comment | Children added to the candidate list: RF-1 (opened now, because 4.2 runs it as an arm), archaic verb forms in keyword search (Opus A-020), and stitching that reads 1.7's reply targets (C-14). |

Issues that gain nothing: #140 (0.3), #141 (0.5), #142 (0.6), #156 (1.3b), #158 (1.5b), #160 (1.4b), #161 (1.4c), #164 (1.2c), #165 (1.2d), #166 (1.2f), #171 (1.8d), #174 (1.8e), #180 (2.2b), #186 (3.3) and every P5 issue.

## 3. Parent issues

| Issue | Change |
|---|---|
| #132 (P0) | Body edit. "Wave 3, one at a time: 0.1a, 0.1b, 0.1c, then 2.1 (which also needs 0.2)." becomes "Wave 3, one at a time: 0.1a, 0.1b, 0.1c, then 2.1 (which also needs 0.2), then 0.1d (checks for the 6 Oct review findings)." and "Phase 1 starts when 0.4, 0.1a, 0.1c and 2.1 have merged." becomes "Phase 1 starts when 0.4, 0.1a, 0.1c, 2.1 and 0.1d have merged." |
| #143 (P0 research) | Body edit. Append: "R7 (added 9 Oct 2026, the Summa against an independent edition) can start any time and blocks 1.7." |
| #150 (P1) | Body edit. Append: "1.6a (added 9 Oct 2026) restores the Catechism's dropped lines and may be the first Phase 1 PR. 1.7 also waits for R7. The 6 Oct corpus reviews extended most items here; see `docs/corpus-cleanup/REVIEW-GAPS-PLAN.md`." |
| #176 (P2) | Body edit. Append: "2.4d (added 9 Oct 2026) carries the rejected-voice role to the models and the screen and must be live before Phase 4. 2.2c is now a migration applied in 4.0's window." |
| #185 (P3) | Body edit. Append: "3.4 (added 9 Oct 2026) records the rejected-voice ranges." |
| #189 (P4) | Comment: "4.0's window also applies 2.2c's migration; 4.2 adds the RF-1 arm and the review's targeted checks; 4.1b needs 2.4d live and 3.4 included." |

## 4. How to apply, once Carter approves

Run from the repo, after `docs/review-gaps` merges so the spec links resolve:

1. Create each new issue with `gh issue create --label corpus-cleanup --title … --body-file …`, using the bodies in section 1.
2. Link each as a sub-issue of its parent through the REST API (`POST /repos/carteratate/body-of-christ/issues/<parent>/sub_issues` with the new issue's ID).
3. Apply the body edits with `gh issue edit <n> --body-file …`, built from each issue's current body with the named line replaced.
4. Post the comments with `gh issue comment <n> --body …`.
