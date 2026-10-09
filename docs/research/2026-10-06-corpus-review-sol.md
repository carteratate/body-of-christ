# Independent corpus review by sol

6 October 2026. Reviewed master `7bd2b66`, the production reader snapshot exported at `2026-10-06T02:52:14Z`, and the production Qdrant index by read-only calls. No production writes, paid provider calls, outside contact or commits. The other reviewer's report and scratch folder were never opened or searched. All scripts and large text evidence remain in `datapipeline/releases/local/review-sol/`.

## Summary

The planned cleanup is not sufficient yet. It fixes many mechanical parsing problems, but misses places where the corpus reverses who is speaking or what an authoritative author endorses. There are condemned propositions presented without condemnation roles, pagan and Manichaean speeches without opponent roles, incoming letters credited to Cyprian, and two Aquinas replies labeled as objections. These are trust failures even when every word survives the parser correctly.

I verified **19 findings: eight critical, five high and six medium**. Critical means the stored content or its attribution can mislead a user, or the citation is wrong. High means a defect damages retrieval or reading across a substantial set of passages, or the specified fix would create such a defect. The findings implicate **859 distinct current passages in live and 859 in the master build**. That count includes complete articles whose integrity is broken by missing arguments, and opening passages affected by absent Psalm titles. It is not a count of 859 entirely false texts. Findings overlap, so adding their individual counts overstates the total. A-016 separately concerns one currently correct passage that the proposed rewrite would mislabel; it is excluded from the 859.

Those passages have **101 saved search-result rows, three bookmarks and four guest-result rows**, with no relevance-label rows. The snapshot provides counts per passage, so I cannot count distinct users or say anyone actually saw an incorrect explanation. A model's misleading answer is a predicted consequence of verified input defects, not a claim that I ran a paid search experiment.

Three structural defects also need attention before publication. Canon law has 17 reader keys combining unrelated sections, covering 209 passages. Three Summa keys contain two articles, giving 24 passages the wrong article citation. The vendored Summa itself lacks two verified argument bodies. Coverage against that same source cannot discover an omission already in the source. The Bible adapter also drops 138 Psalm superscriptions, the introductory biblical titles, in 117 Psalms.

The current index is better synchronized than its history suggests. I compared all 54,568 points with all live passages: no missing or orphan points, and no unexpected payload mismatch. A payload is the readable text and metadata stored beside a numeric search vector. The 21 content differences are the already-documented Summa objection prefixes beside blank reader rows. Numeric and neighbor checks found no additional proved wrong vector. They cannot establish which text originally produced every vector, because the index has no input-provenance hash. The old 86 wrong embeddings still require the planned fresh embedding pass.

The existing reports all exit successfully because their failures are registered as known. They do not detect the new context, hierarchy or independent-source defects below. I would extend the named items, add source roles and independent structure checks, then require a clean staged release and outline comparison. I cannot certify that nobody will ever need to reopen the corpus: a completed review of independent-edition Summa discrepancies, the actual stored reader outline and universal vector provenance remain unverified. Those limits are explicit in the coverage map.

## Findings

IDs remain stable despite sorting by severity. Unless stated otherwise, "live" refers to the 6 October snapshot, not a production Postgres read. The evidence JSON named in each finding contains every counted ID, its full anchor, reference and document metadata. Existing planned defects are discussed in coverage rather than repeated as findings.

### A-001. Condemned propositions appear as papal teaching

**Severity:** critical. **Status:** new. **Owner:** new item, coordinated with 1.3a and 2.4. **Collections:** encyclicals and papal-documents. **Affected:** 119 isolated passages in live and 119 in the build: Syllabus of Errors propositions 1–79 and Exsurge Domine propositions 1–40. Two additional mixed passages contain proposition 80 or 41 with following prose; these need the same role handling. They are Syllabus `syllabus-of-errors/80/p1`, identified in A-004, and Exsurge `exsurge-domine/41/p1`, `65a4f983-ce39-5437-add3-9cf92189bc8f`. They are Syllabus `syllabus-of-errors/80/p1`, identified in A-004, and Exsurge `exsurge-domine/41/p1`, `65a4f983-ce39-5437-add3-9cf92189bc8f`. Six saved retrieval rows point to the 119 isolated passages; counts cannot reveal distinct users.

These are statements the document condemns, but `unit_label` says only `§N`. The Syllabus card's title hints at errors; Exsurge's title does not. More seriously, the reranker and explanation prompts receive reference, role and text, without the document's contextual condemnation. Nothing marks these statements as rejected. `steps/passage_role.py` suppresses the redundant `§N` role. Examples personally read: Exsurge `/2`, `68bebf83-8f20-5692-bdaf-5d33f5f6a014`; `/5`, `a96c8de2-a4c7-594a-abc8-7ea8dc62ea67`; `/39`, `de0942b5-5e0b-5122-a432-a614cf81c63c`. Syllabus `/1`, `9e63e50a-58d7-5fb0-a614-207043ca3f55`; `/2`, `0185d07b-c305-552c-ae7f-3283684a270e`; `/3`, `05608512-25fb-5487-953f-e3de5dd9dd39`. References are the named document and `§N`.

The user can receive a denial of God's action or a claim about souls sinning in purgatory under a pope's name. This is a verified attribution/context defect, not a claim that a paid search experiment produced that answer. The plan corrects the Syllabus's genre but does not specify rejected-proposition roles. Preserve the authoritative condemnation document, attach explicit `Condemned proposition N` roles, and carry the role through embeddings, ranking, explanations, cards and reader. Future check: `roles.papal.condemned-propositions`, asserting each enumerated proposition's role and testing inversion-aware prompt rendering. Reproduce with `evidence.py`, outputs `live-papal-condemned-isolated.json` and `build-papal-condemned-isolated.json`, and the vendored source's framing prose.

### A-003. Three Summa articles contain the following article under the wrong citation

**Severity:** critical. **Status:** known, underestimated: documented in `fetch_context.py`, omitted from 1.7's source-repair scope. **Owner:** expand 1.7 and 2.1. **Affected:** Summa, 51 passages in both live and build across three combined article keys. Of these, 24 belong to the following article and bear the wrong article's citation. Two saved retrieval rows point to the 51; no bookmarks, guest results or labels.

The vendored XML itself places two complete disputations inside a single `div4`: II-II q.64 a.7 also contains a.8; q.66 a.5 also contains a.6; q.123 a.10 also contains a.11. These are not duplicate source element keys. A paragraph walk inside the existing div4, as specified by 1.7, still gives both disputations the first article's identity and citation. The second heading is an ordinary paragraph after the first article's replies.

Personally read the second determinations: `e287939c-c0dd-5182-ba78-051d8aa8e583` concerns accidental killing but cites self-defense a.7; `714ce55f-d88c-5564-bdf9-e100d91e9f29` concerns mortal sin but cites whether theft is always sinful a.5; `6861a408-c5b4-596b-babf-c7955c5b9d2e` concerns cardinal virtues but cites anger a.10. All are `I answer that`, and their anchors end in the first article's key plus a numeric subunit. Read the corresponding source paragraphs, e.g. `SS_Q64_A7-p13` starts the second article's heading. Local output retains full anchors and references in `live-summa-double-articles.json`.

Users cite the wrong Aquinas article; reader sections combine distinct questions, and source caps suppress their separate result slots. Stitching's neighbor scan mitigates attachment confusion but does not repair citation, reader identity or source granularity. Reproduce `evidence.py` and count separated runs of `I answer that`, rather than counting split pieces as separate answers. Introduce explicit source corrections/synthetic structural article IDs for the three trailing articles and preserve old links through the registry. Future check: `structure.summa.one-disputation-per-article`, with exactly one contiguous determination run and no second objection sequence after replies, allowing documented joint replies.

### A-004. Syllabus proposition 80 absorbs extracts from other documents

**Severity:** critical. **Status:** new. **Owner:** expand 1.3a. **Affected:** encyclicals, two Syllabus passages in live and two in build, with no saved references.

`syllabus-of-errors/80/p1`, `a00ffcaa-fe05-5c49-b66a-b6ce2c45f39f`, and `/80/p2`, `00dcaf85-caa1-5ed7-86f1-719db29694b8`, continue past the actual proposition into unrelated extracts about Church/state, European and American persecution, Freemasonry and Prussian legislation. The source HTML has four unnumbered paragraphs after numbered proposition 80; the parser appends them to it. Both cards cite "Syllabus of Errors, §80". I read both passages and all four source paragraphs. There are only two affected passages, so no third example exists.

The planned parser deliberately appends unnumbered prose to the open section and cuts only notes/signatures/footer classes. It specifies no Syllabus body boundary. The source needs an explicit end after proposition 80, with the appended extracts excluded or independently identified before admission. Otherwise a correct parser rewrite preserves this wrong-document text and embeds it as proposition 80. Reproduce `evidence.py` and inspect `sources/encyclicals/syllabus-of-errors.html` after the paragraph beginning `80.`. Future check: `scope.encyclicals.syllabus-body-boundary`, asserting exactly the 80 proposition bodies, no appended extracts, and a source-specific terminal boundary.

### A-006. The pagan argument in Octavius has no opponent role

**Severity:** critical. **Status:** new. **Owner:** new role item, alongside A-001 and 1.8c. **Affected:** church-fathers, 11 live and 11 build passages, the nine chapters V–XIII of Minucius Felix's Octavius. No saved references.

These chapters are Cæcilius's argument against Christianity, followed by Octavius's reply starting at chapter XVI and Cæcilius's conversion in XL. The document is correctly admitted as a Christian apology, but every passage is attributed to Minucius Felix and `unit_label` is null. The first pieces often retain an editor's summary naming the speaker; second pieces do not, and the planned editorial cleanup must not remove that incidental safeguard without replacing it with a role.

Personally read: V/p2, `267c9485-f141-5f52-af82-d484474b8b21`, arguing against a creator/judge; IX/p2, `fffdfe18-bb00-5cc8-8f87-1926eef11ea7`; XI, `14dd4da4-5f18-5146-8327-301ec4c9df1e`, ridiculing bodily resurrection. The count comes from the complete bounded speech, not a keyword guess. Read the transitions IV–V, XIII–XVI and XL to verify speaker and refutation.

The user's result can quote the opponent's materialism or accusations against Christians as the Father's view. The code's `stitch.attachment_relation` even documents that no collection outside Summa is a staged debate; this corpus disproves that assumption. Mark these units "Cæcilius, pagan objection; answered by Octavius" and distinguish dialogue turns when a piece mixes speakers. Preserve the surrounding dialogue in the reader. Future check: `roles.church-fathers.octavius-speakers`, asserting source-bounded speaker roles and their presence in ranking/explanation inputs. Reproduce `trust.py`.

### A-007. Incoming letters to Cyprian are credited to Cyprian

**Severity:** critical. **Status:** new. **Owner:** expand 1.8c and 2.3's work attribution. **Affected:** church-fathers, 45 live and 45 build passages in 16 incoming letters. No saved references.

The 82-letter source explicitly names other senders, but every letter inherits `author='Cyprian.'`. The 16 letters in ANF numbering are II, XVI, XVIII, XX, XXI, XXV, XXIX, XXX, XXXVIII, XLV, XLVII, XLIX, LXXIV, LXXVII, LXXVIII and LXXIX. I reviewed all 82 source headings and the incoming salutations; LXII's heading names the recipient Cæcilius and is correctly excluded from this count.

Personally read: XVIII, `3fbb41f2-1157-5a69-b591-5c25c22b8bab`, Caldonius to Cyprian; XLV/p1, `83de14a5-2455-50e3-b7e2-0b815c2f97b6`, Cornelius to Cyprian; LXXIV/p1, `a71d8855-1752-5a97-8cdf-5aee0f2f6dad`, Firmilian to Cyprian. References name Cyprian's collected Epistles and the letter number; split continuations lose the opening salutation entirely. Firmilian's criticism of Stephen consequently appears under Cyprian's name, and a pope's incoming letter does too.

The planned generic container/work model could store the right authors but contains no sender inventory or acceptance check for this correspondence. The author-name cleanup simply removes Cyprian's trailing period. Assign per-letter authors, applying those facts to all pieces and embedding prefixes, without splitting the frozen collected document. The newly identified senders also require the existing inclusion-rule review; do not assume a volume's named author covers every correspondent. Reproduce `trust.py`; complete sender source ledger in `cyprian-senders-source.json`. Future check: `attribution.church-fathers.cyprian-correspondents`, matching every letter's sender to the source salutation and requiring all its pieces to inherit that sender.

### A-011. Manes's unmarked speeches remain in an admitted refutation

**Severity:** critical. **Status:** new. **Owner:** the new dialogue-role item proposed in A-006, coordinated with 3.2. **Affected:** church-fathers, five live and five build passages in Acts of the Disputation with the Heresiarch Manes. These are the unmarked letter continuation V/p2, all three pieces of chapter XIII, and XIV/p2. Mixed dialogue passages that still say who is speaking are excluded from this count. No saved references.

Chapter V begins with Manes's letter salutation, but its second piece independently denies the birth of Christ from Mary. The end of XII explicitly assigns the opening speech to Manes; XIII's three pieces then lose that framing. XIV/p1 says "Manes replied"; XIV/p2 continues his claim that humans are the workmanship of other powers. None of these five pieces has a speaker role. Changing the document author from Archelaus to Hegemonius under 3.2 does not identify the opponent's speech.

Personally read the complete bounded speech and its transitions. Examples: V/p2, `5d356685-665a-5317-8609-1681d7103d29`, denies Christ's human birth; XIII/p1, `741f9d97-8d65-50fc-b288-c021c969c02d`, claims the speaker is the Paraclete; XIII/p2, `671c2cdc-52d4-54ed-9c04-d93d486724b4`, attributes the law and prophets to Satan; XIV/p2, `bc7c7cde-397c-5927-84e5-1cf68d762d49`, continues the dualist creation argument. References name the work and the chapter; full anchors are the work slug followed by the locations above.

The plan admits this work as Hegemonius's genuine refutation, but its opponents' detached speech can still be presented as the author's teaching. Note removal makes the context problem sharper: XIII/p1 currently contains an editor's note naming Manes, which disappears under the planned cleanup. Preserve source-bounded speaker state across splitting, explicitly mark Manes's rejected teaching, and carry that role into the model inputs and reader. Future check: `roles.church-fathers.acts-archelaus-speakers`, including these five fixtures and requiring every split continuation to inherit its speaker. Reproduce `finishchecks.py`, outputs `live-manes-unmarked.json` and `build-manes-unmarked.json`.

### A-013. Two Aquinas replies are labeled as opponents' objections

**Severity:** critical. **Status:** known, underestimated: irregular labels are mentioned in the stitching docstrings, but 1.7's paragraph walk preserves these incorrect bold labels. **Owner:** expand 1.7 with reviewed role overrides. **Affected:** Summa, two live and two build passages. No saved references. There is no third example in this class.

`fdc9986a-7c4c-5329-adae-350ed2dd1032`, II-II q.172 a.1, is the reply explaining the dream argument from objection 2, positioned between replies 1 and 3. Its source paragraph `SS_Q172_A1-p11` says `Objection 2:`. `6db9d972-6fe2-553d-b19c-b615c46de104`, Suppl. q.77 a.4, is the reply explaining how the trumpet's sound takes effect, positioned between replies 2 and 4. Source paragraph `XP_Q77_A4-p11` says `Objection 3:`; the [New Advent text](https://www.newadvent.org/summa/5077.htm#article4) preserves that typo too. I read both complete articles, the original numbered objections, and the surrounding replies. The content directly answers the corresponding objection rather than advancing a new objection.

The current `unit_label` tells ranking and explanations these are views Aquinas refutes. Offline production stitching also attaches nothing, because they occur after the determination. This is a metadata inversion of Aquinas's own answer. Parsing only the bold start, as 1.7 requires, retains it and generates the wrong `obj. N` citation. Override these source roles to `Reply to Objection N` without silently rewriting their doctrinal text, reconcile their structural anchors, and document the source typo. Future check: `roles.summa.objection-after-replies`, flagging an objection occurring after the determination/reply run within one disputation; reviewed exceptions must explain actual multiple articles rather than hide a mislabeled reply. Reproduce `finishchecks.py`, outputs `live-inverted-reply.json` and `build-inverted-reply.json`.

### A-019. Later editors' writing is retained as Aquinas's answer

**Severity:** critical. **Status:** known, underestimated: rule G is settled, but 1.7 has no removal for these source units and 1.10b explicitly leaves Summa unchanged. **Owner:** expand 1.7's editorial/source-attribution ledger, coordinated with 2.1. **Affected:** Summa, three live and three build passages: two pieces carrying the Immaculate Conception editorial section and one later-supplied reply. One saved retrieval points into the three live passages; no bookmarks, guest rows or labels.

III q.26 a.2 ends its authentic reply 3 at `TP_Q26_A2-p9`. The following seven paragraphs start with the explicit source heading `ST. THOMAS AND THE IMMACULATE CONCEPTION (EDITORIAL NOTE)`, then a diagram and modern discussion of Aquinas's position. They are appended to reply 3. `48e8b0ec-8aad-5d2d-b0b2-08a55587d37a`, article `/7`, mixes the authentic reply with the editorial section. `fe980f6f-314a-5143-87d3-689a2ff7c5ea`, `/8`, consists of its concluding editorial discussion. Both say `Reply to Objection 3`; neither identifies the editor as speaker. The source explicitly calls this editorial, so no doctrinal inference or authorship guess is needed.

I-II q.102 a.6 reply 10 is a different failure. Source paragraph `FS_Q102_A6-p33` identifies its solution as supplied by Nicolai, not found in the codices. The [English edition](https://www.newadvent.org/summa/2102.htm#article6) preserves that warning. The normalizer strips the balanced bracket-star warning but retains the supplied answer. The live passage is `0c472a23-8ac8-57eb-83e6-5c85d4635a6a`, article `/23`; its build successor is `11c90432-d852-50e1-a6d4-74b3faec4613`, `/24`. This is part of the already-known ID drift under 2.1; that drift is not counted as another finding. The Latin inventory has no ad 10 at this article, consistent with the English edition's warning. I read the entire reply, its warning, the editorial section, all three current passages and their build counterparts.

A user opening the mediator article finds a modern theological defense and tabular summary credited to Aquinas. A result from the ceremonial-law article presents an editor's reconstructed answer as Aquinas's own reply. Balanced bracket-star notes are already removed correctly: there are zero literal `[*` markers in either current store. A blanket second note-removal pass does not fix either problem, and removing an authorship warning without acting on it makes the attribution less accurate.

Remove the later editorial section under rule G, preserving the authentic first part of reply 3. Retire or independently attribute the Nicolai solution according to the settled author-only scope; do not keep it in the Summa as Aquinas's own words. Preserve its authorship judgment before removing the note or unit, and map saved links through the registry. The proposed paragraph walk must perform editorial scope exclusion before assigning reply roles, so it cannot revive whole replies currently suppressed as footnotes elsewhere. Future checks: `editorial.summa.immaculate-conception-section` and `attribution.summa.editor-supplied-replies`, asserting the authentic boundary and acting on "supplied by" warnings before stripping them. Reproduce `extend-evidence.py`, `live-summa-editor-additions.json`, its build counterpart and the named source paragraph ranges. `summa-notes.py` is the negative control proving balanced inline note markers are already gone.
### A-002. Canon law reader keys combine unrelated sections and reorder reading

**Severity:** high. **Status:** new. **Owner:** expand 1.5a. **Affected:** canon-law, 209 passages in live and 209 in build, across 17 noncontiguous chapter keys. Twenty-eight saved retrieval rows point to them; no bookmarks, guest rows or labels.

The adapter discards Part and Article context, builds keys from Book/Title/Chapter display strings, then forward-fills old headings even after a new higher-level section resets them. Book II's Title I combines canons 208–223 with 573–606. Book IV's Title I combines baptism canon 849, sacramentals 1166–1172 and sacred places 1205–1213. The reader sorts chapters by their first position, then reads every passage sharing that key. It consequently jumps across intervening canon ranges; the search cap also treats unrelated subjects as one source.

Personally read examples: `can/265`, `3b2c1a63-ab51-5732-98d4-fbc7038e7980`, about incardination, is labeled "Special Norms for Associations of the Laity"; `can/849`, `dfb27bd8-5a5b-57ad-9690-79b46ae70881`, and `can/1166`, `e3cc702e-278a-5c7b-a612-fbbe5776e80d`, have the same Title I chapter key despite baptism versus sacramentals; `can/1717`, `78e90e64-e17f-5283-8e30-65f1c4a4474a`, preliminary penal investigation, shares Title III/Chapter I with trial evidence canons 1517–1525. All references are "Code of Canon Law, Can. N". The snapshot and build are identical for these rows.

This count covers every noncontiguous key. It is a lower bound on heading defects: I did not reconstruct an independent full hierarchy for every contiguous section. Reproduce `structure.py` and `evidence.py`; full groups in `canon-collision-rows.json`. Keep the complete structural hierarchy and reset lower levels at higher-level boundaries, with stable structural identifiers rather than ordinal labels reused under different Parts. Chapter redirects and reading-progress remaps must accompany the fix. Future checks: `structure.canon-law.chapter-contiguity` and `structure.canon-law.heading-path`, comparing each canon to the source hierarchy, not merely validating unique passage anchors.

### A-008. ANF editor Arguments are explicitly deferred despite rule G

**Severity:** high. **Status:** known, underestimated: 1.8a explicitly excludes chapter summary headings and proposes deciding after P1. **Owner:** bring into 1.8a before P4. **Affected:** church-fathers, 175 live and 175 build passages contain an explicit chapter/letter `Argument` summary; four saved retrieval rows, no bookmarks, guest rows or labels. The count is the explicit Argument class only, not every possible editor heading. Twenty-seven additional NPNF Argument passages are already handled by 1.8b and are excluded here.

Breakdown: Cyprian's Epistles 82, Octavius 41, Novatian's Trinity 30, Cyprian's Treatises 10, Jewish Meats 7, Treatises Attributed to Cyprian 2, Methodius's Banquet 2, Anonymous Re-baptism 1. Novatian's 37 passages will be removed under rule A; the remaining 138 still need rule G handling, with overlapping removal decisions applied afterward.

Personally read Cyprian's Epistles V/p1, `6b0a9789-e506-58b9-9ba1-9c68d4d3c097`, VII/p1, `fd046db3-1c9e-59aa-960a-23c9efcbd539`, and IX/p1, `a8a7e20b-3f91-5f08-b655-233562c42f8d`. The summaries discuss which letter the editor thinks is missing and describe the author's argument in the third person. They are body paragraphs outside `<note>` and outside the editorial div list, so the planned note/div removals leave them in the passage. Octavius's summaries likewise assert what the pagan interlocutor argues.

This leaves modern editors' words in saint-attributed text and embeds those summaries for retrieval. Rule G already settles their disposition; a post-P1 decision would leave the "last cleanup" promise unfinished. Remove the reviewed editorial spans, preserve actual authorial arguments such as R4's Refutation summaries, and retain speaker/context metadata where a removed summary was the sole context. Reproduce `trust.py`; `live-anf-arguments.json` holds every match. Future check: `editorial.church-fathers.anf-argument-headings`, using reviewed source paragraph IDs rather than deleting any prose mentioning an argument.

### A-009. Psalm superscriptions are discarded as headings

**Severity:** high. **Status:** new, extending 1.4a's verse completeness boundary. **Owner:** expand 1.4a and 0.1a. **Affected:** Bible, 138 missing descriptive-title paragraphs in 117 Psalms, affecting the first passage of each of those Psalms in both live and build. Those 117 passages have 49 retrieval rows, three bookmarks and three guest-result rows; distinct users are unknowable from the count-only snapshot.

The USFM `\d` lines contain the Psalms' Hebrew superscriptions, meaning their introductory titles describing authors, circumstances and musical directions. These are not modern section summaries. The [USFM specification](https://docs.usfm.bible/usfm/latest/para/titles-sections/d.html) classifies `\d` as `VerseText`, while the coverage reader `checks/source_text.py:usfm_units` explicitly calls it a heading. The Bible adapter discards it. Consequently the numbered-verse coverage report passes over this omission. The [Vatican's Psalm 51 text](https://www.vatican.va/archive/ENG0839/_PH7.HTM) itself numbers the Nathan/Bathsheba title as verses 1–2, establishing that this is biblical text rather than a translator's added topic label. This does not require changing the settled WEB-C numbering.

Personally read the source and complete opening passage for Psalms 3, 51 and 54. `psalms/3/1`, `3ba1ce78-0e6a-5aed-8b96-4d805ce0063a`, loses the flight from Absalom; `psalms/51/1`, `ceceeb0e-28f9-5b74-81a3-61ee9f656331`, loses Nathan and Bathsheba; `psalms/54/1`, `440b93bd-a6f3-5963-8925-4fc38e2208c8`, loses the Ziphites' report to Saul. The reader starts with the prayer, and neither lexical search nor the embedded passage can find those missing circumstances. All 73 USFM files were scanned; every `\d` occurrence is in Psalms.

Keep these titles with the Psalm's opening text, labeled as a superscription without inventing a WEB verse number. Their structural identity needs the same registry discipline as any recovered body text. Future check: `coverage.bible.psalm-superscriptions`, requiring each source `\d` text to reach its Psalm's opening unit and classifying it separately from editorial `\s` headings. Reproduce `psalms.py`; the live/build outputs list all 138 source paragraphs and 117 first-passage IDs.

### A-016. The bold-only Summa walk would turn a sed contra into an objection

**Severity:** high. **Status:** new defect in the proposed fix. **Owner:** correct 1.7 before implementing it. **Affected:** Summa, zero currently wrong live/build roles in this class; one currently correct passage in both stores would lose its role under the specified algorithm; a second unbold opening is an important passing control. No saved references.

The source has two ordinary paragraph openings without the required bold child: `SS_Q23_A2-p5`, an `On the contrary` about charity, and `TP_Q44_A1-p7`, the `I answer that` about Christ's miracles. Their current correctly parsed passage IDs are `4439ee4e-de05-5513-8571-402c25e50ccf` (II-II q.23 a.2, article `/3`) and `4409b66e-313a-5bf5-a4de-0ac9e09fcac6` (III q.44 a.1, `/5`). Only two such literal unbold canonical openings exist in the source scan; I read both and their neighboring paragraphs.

1.7 recognizes a new part only from the paragraph's first bold child. Its sole nonbold exception applies when no bold determination exists anywhere and the current part is a sed contra. In II-II q.23, the unbold sed contra would join objection 3 and be presented as the opponent's view. In III q.44, the unbold determination would begin correctly under the exception, but the exception includes only the four named articles in its explanation and fixture; a faithful general implementation must test this additional article. The unbold sed contra remains an unconditional regression unless an explicit fallback is added. The reported defect is the one certain sed-contra regression. The determination is a passing control for the same fallback boundary, not a second claimed regression.

Recognize an exact canonical opening at a paragraph boundary without splitting an inner quoted phrase. Keep fixtures for unbold sed contra and determination alongside the bold `Objection N: On the contrary` fixture that motivated the change. Future check: `roles.summa.unbold-paragraph-openings`, requiring these existing roles to survive the rewrite. Reproduce the all-paragraph scan in `role-scope.py` and the two IDs in `remaining-roles.py`; the latter saves `live-bold-walk-regression.json` and its build counterpart.

### A-018. The vendored Summa itself omits two argument bodies

**Severity:** high. **Status:** new. **Owner:** source corrections in 1.7; add an independent structure check to 0.1a. **Affected:** Summa, two missing source units, affecting the reader integrity of 18 live and 18 build passages in I q.76 a.3 (10) and I q.89 a.3 (8). No saved references. Only two verified omissions are claimed here.

I q.76 a.3 lacks the embryo argument that should be objection 3. Its source jumps from objection 2 to the genus/difference argument numbered 3, which is actually objection 4 in the [New Advent edition](https://www.newadvent.org/summa/1076.htm#article3). The reply about the embryo survives and currently gets attached to that unrelated genus/difference argument. Examples: `665b8eb5-64dc-57f5-bead-71af42bf509d`, purported objection 3; `b553ccb3-8d81-57aa-bc0e-b3900633b899`, reply 3; `37c95054-cf64-5d03-a169-4bdd6b061fcd`, reply 4 without its properly numbered counterpart.

I q.89 a.3 lacks the second counterargument about study becoming useless. The [Leonine Latin text, reproduced by Corpus Thomisticum](https://www.corpusthomisticum.org/sth1084.html), contains both `s. c. 1` and `s. c. 2`; source unit 32200 is the missing second argument. The vendored XML and New Advent both omit it, so comparing those two alone would falsely confirm completeness. `9a7357c6-2c6e-5980-b3e0-bb1680bd7e6e` holds only the first sed contra; `fb5cd066-9573-58b3-9c35-b13dc53ee3a0` retains the reply about study with no premise to attach. I read both complete vendored articles and the independent edition's argument structure.

Coverage against the vendored source cannot see text the source lacks. The proposed paragraph walk reproduces these losses and, in q.76, codifies the wrong number into a precise citation. Recover the reviewed missing English units from an approved witness, correct q.76's shifted argument number, and reconcile existing IDs/links. Future check: `coverage.summa.independent-argument-structure`, comparing each article's argument and counterargument inventory against a fixed independent edition, with explicit documented structural variants. Reproduce `remaining-roles.py` for affected IDs, inspect `FP_Q76_A3` and `FP_Q89_A3` in the vendored XML, and compare the linked editions. A full independent-edition comparison of every Summa article remains necessary before calling the source complete; this review verified these two, not an invented global count.
### A-005. Eighteen canons contain corrupted ligature spellings

**Severity:** medium. **Status:** new. **Owner:** expand 1.5a, with a source-transcription check. **Affected:** canon-law, 18 live and 18 build passages; 20 corrupted word occurrences. Two saved retrieval rows point to these passages; no bookmarks, guest results or labels.

The source and stored text have capital `V` where `ff` belongs and `Y` where `ffi` belongs. Examples personally read: `can/253`, `cbfe4ef9-b66a-5f01-95d2-513f31d4a70f`, `diVerent`; `can/771`, `d6218cdc-8131-59c8-b6d0-347afa2a4d23`, `suYcient`; `can/1095`, `d7b7050f-1edd-5310-8deb-9626311418d5`, `suVer`. Other affected canons: 761, 768, 820, 998, 1040, 1044, 1068, 1127, 1143, 1144, 1146, 1200, 1222, 1287, 1290. References are "Code of Canon Law, Can. N". This is embedded in source text, not an HTML spacing bug; `get_text(' ', strip=True)` cannot correct it.

The reader sees visibly corrupt words. A throwaway local Postgres loaded all 54,568 snapshot contents with production's English `to_tsvector`. All 20 corrupted tokens fail `@@ plainto_tsquery('english', corrected_word)`. For example the broken spelling yields `diver`, while "different" yields `differ`; "sufficient" and its corrupted form also have different lexemes (the normalized words Postgres searches). This is a measured lexical-search loss, without a paid search call.

Reproduce `trust.py` and `fts.py`; evidence in `live-canon-ligatures.json` and `fts-ligatures.json`. Fix through reviewed source overrides/normalization, not a blind global V/Y replacement. Future check: `text.canon-law.ligature-corruption`, rejecting lower-case words containing these isolated uppercase glyph substitutions and confirming corrected canon text against a clean authoritative witness.

### A-010. Broken words survive the planned spacing fixes

**Severity:** medium. **Status:** new, beyond the acknowledged Annus Qui Hunc source typos in 1.3a. **Owner:** expand 1.10a with reviewed transcription overrides. **Affected:** 34 live and 34 build passages: 30 encyclicals, two apostolic-exhortations, one papal-document and one medieval passage. Seven retrieval rows and one guest-result row; no bookmarks or labels.

A reviewed inventory of 41 broken word forms finds source line-break hyphens retained inside words. This count excludes grammatical compounds and punctuation dashes. Examples personally read in both source and passage: Evangelium Vitae §9, `84c6dfba-5691-5e8f-b366-bb45d8791679`, `pre- cisely`; Veritatis Splendor §41, `2605bfd6-38d7-5d56-9454-bc75faa8ecd0`, `ex- traneous`; Dies Domini §83, `076ed2eb-f190-5c48-a34e-0ba07e7d5700`, `brother- hood`; Consolation of Philosophy Book II introduction/p11, `f40aa84b-f3f3-573b-bf80-bd49550582ff`, `honour- able`. The damaged words are already in the source HTML/XML and are unchanged by whitespace insertion between HTML elements. The punctuation-glue fixes likewise do not join them.

The reader sees broken spellings; lexical search tokenizes the two fragments rather than the intended word. Correct reviewed source occurrences, preserving real compounds. Reproduce `hyphens.py`; its literal inventory and the live/build JSON outputs make the count reproducible. Future check: `text.all.reviewed-broken-word-hyphens`, rejecting this reviewed inventory across all collections; a broader candidate report should flag alphabetic hyphen-plus-space sequences for review without automatically deleting them.

### A-012. A duplicated Summa paragraph has no specified source correction

**Severity:** medium. **Status:** known, underestimated: health R4 detects it, but 1.7 does not specify fixing the source repetition. **Owner:** expand 1.7. **Affected:** Summa, two live and two build passages containing one duplicated paragraph in I-II q.20 a.6. Only two examples exist. No saved references.

The two adjacent `On the contrary` passages are exactly identical: `863923bd-26df-53c3-b001-f2d25045bd8c` at article anchor `/3`, position 6021, and `e4adf140-04ed-52b2-b2dc-6616049e76c3` at `/4`, position 6022. Both cite I-II q.20 a.6, whether one external action can be good and evil. The source has the same paragraph twice, `FS_Q20_A6-p5` and `-p6`; the [New Advent edition](https://www.newadvent.org/summa/2020.htm#article6) has one sed contra paragraph. I read both stored passages and the source paragraphs.

The planned paragraph walk preserves both bold starts. Packing them into one unit could conceal the duplicate from the passage-level R4 rule while still repeating it in the reader. The reader repeats the statement. Healthy search deduplication normally suppresses the adjacent pair: their existing vectors have cosine similarity effectively 1, above the 0.9 threshold. If the vector fetch fails, that protection is skipped and both can survive the source cap. The finding does not claim two slots are lost on the healthy path. Remove the verified extra source paragraph, map the retired ID to the survivor through the registry, and assert one occurrence in the cleaned article. Future check: `text.summa.adjacent-duplicate-parts`, comparing normalized source paragraphs as well as complete passages. Reproduce `census.py` and `finishchecks.py`; `live-duplicates.json` and `live-summa-duplicate-sed-contra.json` retain the complete locations.

### A-014. The Summa spec invents missing determinations in three reply-only articles

**Severity:** medium. **Status:** known, underestimated: 1.7's stated repair and acceptance condition contradict the source. **Owner:** correct 1.7 and define stitching for reply-only articles. **Affected:** Summa, 32 live and 32 build passages across I q.74 a.3 (14), I q.91 a.4 (11), and I q.117 a.2 (7). Their 15 objections cannot obtain a separate determination from current stitching. Two retrieval rows point into these articles; no bookmarks, guest rows or labels.

The spec names four articles with no determination marker and promises to recover the answer from the first unmarked paragraph after the sed contra. Only I q.68 a.2 has that unmarked answer. The other three proceed directly into labeled replies. I q.74 a.3 has no sed contra either; I q.91 a.4 and I q.117 a.2 have one but no intervening unmarked determination. Unmarked paragraphs later in replies are continuations of those replies. I read all four source articles. The [q.74 edition](https://www.newadvent.org/summa/1074.htm#article3) and [q.91 edition](https://www.newadvent.org/summa/1091.htm#article4) confirm that direct-reply structure.

Opening passage examples: `59797930-3bed-5d48-836d-cca24d3a8186`, I q.74 a.3 `/0`; `8dbc0908-bd6f-5db0-9363-20a50e3ad321`, I q.91 a.4 `/0`; `e414faa8-5cdb-5713-8290-8d95154010c7`, I q.117 a.2 `/0`. Full article anchors and references are in the evidence output. Offline production `assemble` confirms all 15 objections have no answer attachment. The spec's "at most one article lacks I answer that" test cannot pass faithfully: three legitimately lack it, even after the genuine I q.68 recovery. Moving a reply into an invented determination would corrupt its role and citation.

Keep the authentic structure, allowlist these three source-bounded exceptions, and attach the corresponding reply to an objection where that is the article's answer form. Future checks: `structure.summa.reply-only-articles` and `context.summa.reply-only-objection-answer`, using these three articles and the genuine I q.68 recovery as contrasting fixtures. Reproduce `finishchecks.py`, outputs `live-direct-reply-articles.json`, `build-direct-reply-articles.json` and the full offline stitching results.

### A-015. Twenty-seven Summa pieces retain wrong numbers or unrecognized reply markers

**Severity:** medium. **Status:** known, underestimated: stitching documents duplicate numbers, but 1.7's source-driven labels preserve the defects. **Owner:** expand 1.7 and its source-role ledger. **Affected:** Summa, 27 live and 27 build passages, with no saved references. Nine were verified in the initial source scan; independent-edition structure checking added six wrong reply numbers and 12 pieces containing 11 unrecognized shorthand replies.

Six source numerals are wrong: II-II q.36 a.2's second objection is numbered 1; III q.10 a.2's first is numbered 2; Suppl. q.41 a.1's second is numbered 1; Suppl. q.52 a.1's sixth is numbered 7; Suppl. q.71 a.14's second is numbered 3; Suppl. q.40 a.3's first reply is numbered 11. Two more pieces in II-II q.26 a.11 carry `Objection 2`, but the second, `1a951107-297e-5c13-b6a4-7998789f4c08`, is objection 3. This makes seven wrong-number pieces in total. II-II q.98 a.3's source instead writes `OBJ 2.`; that second argument is glued inside the first-objection piece, `c53c2642-296b-5652-b061-0113c8d676b3`. II-II q.4 a.8's third argument has no label at all; its `Further` paragraph is glued into the second-objection piece, `f1f9cf7c-78d4-5f99-a9b2-fb1e99e69f1d`. These first cases affect nine existing pieces. Six more reply numbers are wrong: I-II q.40 a.1 and q.81 a.3, and II-II q.41 a.1, repeat reply 1 where reply 2 belongs; II-II q.79 a.3 starts with reply 2 where reply 1 belongs; III q.50 a.3 repeats reply 2 where reply 3 belongs; III q.79 a.4 repeats reply 1 where reply 2 belongs. The independent Latin structure supplies the correct reply targets, and the English content answers the corresponding numbered objection. Examples are `4837b42b-89e5-5ac3-a30a-d340e5168967`, I-II q.40 a.1 `/6`; `bb40e5b6-8e58-53df-b933-37c1edfb9e8c`, I-II q.81 a.3 `/6`; and `656574fe-3be3-5d10-89a9-9124bc4a4cac`, III q.50 a.3 `/8`. I read all six source replies and their target objections.

Eleven further source paragraphs explicitly begin `Reply OBJ` or `Replies OBJ`, including joint replies. They are absorbed into the preceding determination or reply, across 12 current pieces because the I-II q.102 a.5 joint reply splits. I read every one of these explicit source paragraphs. They include I q.92 a.2 ad 1, `b230eb4f-eb16-5b5b-90a6-26c78221052b`, labeled `I answer that`; I q.93 a.4 ad 2 and 3, `3d3b8c45-5f79-57f3-9415-cf81efd4d474`, labeled reply 1; and III q.24 a.4 ad 1 and 2, `fbf7b51a-b578-58e7-9111-bb8c14e3b6cd`, labeled `I answer that`. Ordinary parenthetical cross-references such as `Reply OBJ 2)` are excluded. All 12 pieces need source-bounded reply targets, and joint replies must retain both targets. Total: 27 affected pieces, 9 + 6 + 12, in both stores.

Examples personally read with their corresponding replies: II-II q.36 a.2, `9837eafa-279f-546f-a540-222658c594e9`, second objection at `/1`; III q.10 a.2, `217480d4-068c-5c6c-a913-1c2724e0f72a`, first objection at `/0`; Suppl. q.41 a.1, `ac28b47e-005f-5f12-894b-59399a687c73`, second objection at `/1`. The reply about Damascene, the reply about Mark 13:32, and the reply about Tully identify the intended arguments. I checked the original nine pieces and the source paragraphs; the additional cases were verified as described above. Full anchors and citations are in the evidence file.

Users get wrong argument citations and missing or wrong attachments. III q.10 a.2's reply 2 can attach the first argument because the assembler truncates a same-number run at the next `Further`; reply 1 has no numbered argument. The bold-paragraph rewrite cannot repair literal wrong numbers or identify the bare third argument. Use reviewed per-source marker corrections, then check argument/reply correspondence rather than requiring output labels to reproduce every source typo. Future check: `structure.summa.argument-numbering`, with explicit handling of counterarguments and joint replies. Reproduce `role-scope.py` and `remaining-roles.py` for the original nine, `latin-inventory.py`/`latin-triage.py` and `extend-evidence.py` for six additional wrong numbers, and `shorthand-replies.py` for the 12 shorthand pieces. The three sets are disjoint; corresponding `live-`/`build-` JSON files list all 27 IDs. Other implicit prose replies remain structural review candidates rather than being silently counted in this finding.

### A-017. Fourteen legitimate counterargument replies cannot be stitched

**Severity:** medium. **Status:** new scope gap in 1.7; known missing-attachment behavior has no corpus/model remedy. **Owner:** expand 1.7's context model and the stitching acceptance checks. **Affected:** Summa, 14 live and 14 build reply passages, with no saved references. Wrong source numbers, missing source text and unmarked objections are excluded and handled separately.

Aquinas sometimes replies to the argument under `On the contrary`, numbering it after the ordinary objections. These are legitimate structures, not missing numbered objections to invent. The production assembler only searches for `Objection N`; it cannot attach a counterargument stored as `On the contrary`. All 14 returned no attachment in the offline run. Source inspection confirms the arguments are present under the sed contra, including its unmarked continuation paragraphs.

Examples personally read with their arguments: I q.13 a.10 ad 4, `e241b0aa-029f-5ec8-b179-364a03bd978e`, answering the true/pictured-animal argument; I-II q.11 a.2 ad 4, `a85c01f0-2997-5730-8674-2b6cc4b267fd`, answering Augustine on beasts enjoying food; II-II q.147 a.4 ad 5, `01bde4b2-8288-552c-bffc-7bd547779499`, answering the bridegroom/fasting argument. Full anchors and references are in `live-counterargument-replies.json`. I reviewed all 14 source reply/argument pairings, not just the three examples.

The user sees a bare qualification whose premise is absent, despite the product's effort to complete every reply. More specific citations do not give the assembler a matching argument. Preserve the source's numbered replies and add explicit argument-target metadata or a reviewed counterpart map that can point into the sed contra. Future check: `context.summa.counterargument-reply-targets`, requiring all 14 replies to resolve to their actual argument; do not rename the counterargument as an ordinary objection merely to satisfy today's scan. Reproduce `finishchecks.py`, `role-scope.py` and `remaining-roles.py`.



## Coverage map

### Inputs, code and existing checks

I read `CLAUDE.md`, `CONTEXT.md`, the entire cleanup plan including inclusion rules A to H and its Decision log, the cleanup README, all five specifications and `NEEDS-CARTER.md`. I checked the earlier named audits, R1 to R6 material, the issue inventory and retrieval-integrity/Summa reingest scope, and the reconciliation script's documented wrong embeddings. No October 6 report from another reviewer was accessed.

I read the embedding stage and input builder, overlap settings, vector and FTS retrieval, rerank cards and role formatting, listwise ranking, explanations, source deduplication, stitching and context fetching, HyDE descriptions, result-card links and Bible markers, reader and sources routes, outline schema, evaluate code and About descriptions. Findings use what those implementations actually receive. In particular, the ranking/explanation cards do not independently supply all title/author context assumed in the brief; the rejection or speaker role must travel with the passage.

The master was built once through every `publication.SOURCE_ADAPTERS` entry. The snapshot was loaded once through `checks.health.load_snapshot` and cached with the build. All three snapshot SHA-256 hashes match their manifest. Subsequent scripts reuse the pickle or flattened JSON. The existing coverage, health for build and snapshot, and release reports all ran. There are zero unexpected blocking failures; the release report accepts **409 known anchor-stability failures**. Its matching outcomes are 54,405 same, 22 moved, 134 split, seven merged, zero removed and 105 new build passages. This is baseline acceptance, not approval to republish before 2.1. The 408 known Summa identity drifts and the council drift remain the registry item's responsibility.

### Every collection

The scans in the next table cover all passages and document metadata. "No additional verified finding" means the stated examinations did not establish another defect; it does not mean every theological sentence received an independent authenticity review.

| Collection | Live/build passages; documents | Examined and result |
|---|---:|---|
| bible | 3,262 / 3,295; 73 | Every USFM file, verse-sequence report, marker syntax/order, source titles, reference structure and length distribution. A-009 adds lost superscriptions. The Daniel/Esther gaps and numbering work remain 1.4a. No malformed, duplicate or out-of-order inline verse marker was found. Marker absence alone is not a defect: single verses and split continuations explain the candidates. Settled WEB-C/Nova Vulgata policy was not reopened. |
| catechism | 800 / 809; 1 | Paragraph coverage/sequence, chapter grouping, markers, notes, length, text patterns and cross-document quotation candidates. The known 2267 update, capitalization, section/paragraph markers and split citations are covered by 1.6/1.10. No additional verified finding. |
| canon-law | 1,747 / 1,747; 1 | All canon references, chapter contiguity, heading keys, source corruption candidates, source/body matching, English FTS and metadata. A-002 and A-005. The existing five missing canons, five glued sections, current-law amendments, Latin and footer text remain 1.5. A full independent hierarchy mapping of every contiguous section was not completed; 209 is the verified collision count. |
| councils | 2,173 / 2,202; 36 | Coverage, numbered units, source metadata, short fragments, language, duplicate/overlap candidates and reader grouping. Known Vatican II continuation losses, translation replacement and council body boundaries remain 1.1/1.2. The two short duplicate-text health hits are known; no additional verified duplicate or wrong-author finding. |
| encyclicals | 6,110 / 6,154; 131 | Numbered sequences, introductory and terminal prose, rejected propositions, metadata, OCR/hyphen candidates, language and cross-document quotations. A-001, A-004 and 30 A-010 passages. Non-English documents, papal formatting/list loss, source credit and the known Annus Qui Hunc typos remain planned. |
| apostolic-exhortations | 3,024 / 3,053; 30 | Coverage/sequence, list and note candidates, metadata, lengths, hyphen candidates and quotations. Two A-010 passages. Known source body omissions, footnotes, debris and splitting remain 1.3a/1.10. No new standalone opponent-speech finding. |
| papal-documents | 485 / 494; 14 | Numbered sections, condemnation frame, preamble/terminal text, author/year metadata, hyphens and quotation overlap. A-001 and one A-010 passage. Planned genre regrouping does not by itself mark condemned propositions. |
| church-fathers | 9,783 / 9,783; 128 | All source chapter sequences and text-pattern candidates, editorial headings, retained incoming-letter headings, dialogue boundaries, notes/Greek candidates, attribution and overlap candidates. A-006, A-007, A-008 and A-011. All 82 Cyprian letter headings were read for sender/recipient direction. Ignatian recensions, Origen and other removals, NPNF container splitting, bracket editors and incidental notes remain known. I did not independently authenticate every sentence in all 128 documents. |
| medieval | 434 / 449; 6 | Chapter coverage, short/debris candidates, note/edition headings, authors, quotation overlap and hyphens. One A-010 passage. Existing Bernard/Eckhart concerns, editorial matter, Lawson replacement, work titles and split citations remain 1.9/1.10 and scope decisions. No additional verified opponent block. |
| summa | 26,750 / 26,792; 1 | Every article key and paragraph marker, source-key uniqueness, determination runs, objection/reply numbering candidates, all production offline attachments, duplicate paragraphs, source/model role agreement and selected independent-edition structure. A-003 and A-012 to A-019. Prologues, empty objection pieces, editor notes and frozen identities remain planned. The independent-edition scan covers the four core parts; discrepancy review and the Supplement remain incomplete. |

### Every hunting area

| Area from the brief | Scope and evidence | Result or limit |
|---|---|---|
| Index versus reader store | Every point ID and payload against every snapshot row; all displayed/filter fields, types, missing values; index configuration and exact count. | Zero orphans or missing points. Only 21 known Summa content differences. `unit_label` is absent on 1,193 points whose reader value is null; the code accepts absence and null equivalently. All other compared fields agree after null normalization. |
| Vector identity and quality | All 54,568 vectors checked for dimension, finite components and zero norm; byte-identical groups; cosine similarity of document neighbors; 64 nearest-neighbor queries using only each point's own vector. | All are finite 1,536-dimensional nonzero vectors. Six identical-vector pairs, 12 points, all have identical legitimate neighbor-augmented inputs under the current input builder. They are not evidence of text/vector corruption. The 64 probes include five lowest-neighbor cases per collection plus duplicate-vector/text fixtures. No additional proved wrong vector; no exhaustive all-pairs near-duplicate search or universal historical input proof. |
| Payload filtering and auxiliary collections | Listed all collections/aliases and inspected configuration and code paths. | Only `chunks` exists; there are no aliases, `facets` or `questions`. `collection` has a keyword payload index covering all points. Current production retrieval reads `chunks`; V5 code can create auxiliary collections but they are absent here. The physical indexed-vector count above point count is not an orphan count. |
| Metadata | All 421 title/author/year/translation records, all chapter labels and references through scans; targeted comparison to source headings and the attribution research. | A-002/A-003/A-007/A-013/A-015. No invalid non-null year. Years are null on 128 Fathers, 73 Bible books and Summa; translations are empty on 348 documents. These omissions and trailing punctuation are already 2.3/1.10a. Sender attribution is a new cause. Not every date or translator attribution was independently researched. |
| Text quality inside passages | Every live/build content scanned for replacement characters, common mojibake, HTML/entities, page markers, soft hyphens, note/editor headings, suspicious word/number joins, punctuation glue and line-break hyphens; hand-reviewed surviving classes. | No replacement-character, tested mojibake, escaped HTML/entity or page-header candidate survived. A-005/A-008/A-010. The 43 soft-hyphen Fathers passages are in Origen's planned removal. Existing glue, note and bracket-editor classes remain 1.8/1.9/1.10. Broad punctuation regex matches are candidates, not defect counts. |
| Passage lengths and self-contained meaning | All lengths and short fragments; source boundaries in every baseline sequence; dialogue and condemnation blocks; offline Summa assembly. | Table below. A-001/A-006/A-011/A-014/A-017 add missing semantic context. Mid-unit splitting and meaningless short tails remain 1.10c. No current passage exceeds 4,000 characters. The current input builder does not impose the obsolete 3,500-character truncation discussed in earlier audits. This is not proof that all long passages retrieve well. |
| Lexical search | Throwaway local Postgres, all 54,568 contents indexed with production English `to_tsvector`; 20 corrupt canon-token probes and collection query probes. | All 20 corrupted canon tokens fail the corresponding corrected-word query, A-005. Common Bible terms such as love, Holy Spirit and Isaiah do match; charity and Holy Ghost do not match this modern translation. That expected spelling/translation vocabulary gap is not evidence of missing source text. Non-English flags/removal remain 3.3/1.5. No paid semantic-search comparison was made. |
| Exact and near-text duplicates | All normalized contents longer than 100 characters; cross-document 16-word shingles, every fourth starting position, at least eight shared shingles and at least 70% overlap. | One long exact duplicate group, A-012, no long exact cross-document group. All 54 cross-document high-overlap candidates were inspected; they are biblical parallels, quotations, repeated council renewals or papal self-quotations rather than a second independently admitted copy of the same work. Top and targeted cases were read in full. This threshold does not rule out looser semantic duplicates. Healthy Summa vector dedup suppresses A-012's adjacent pair. |
| Reader structure and links | All document counts, chapter-key contiguity/label consistency and positions; URL-encoded anchor round trips for every live/build passage; identity report and reader lookup code. | All 421 stored non-null `chunk_count` values equal actual counts. URL round trips have zero loss. A-002/A-003 affect reader grouping/order. Huge NPNF container chapters and identity drift are already planned. Actual `document_chapters` rows were not exported, so their stored ordinals/labels cannot be verified. No browser rendering test was performed. |
| Saved user references and removals | Counts joined to verified finding IDs and known blank/debris/editorial candidates. | 859-ID union: 101 retrievals, three bookmarks, four guest results, zero labels. Known blank 21 and debris 11 have zero saved rows. A reviewed whole-editorial heading class of 115 passages has one retrieval and zero other references; this is a lower bound, not the complete future removal registry. The 175 embedded editorial Argument spans have four retrievals; those passages also carry authorial text and should be repaired rather than automatically retired. |
| Corpus scope, trust and collection descriptions | Inclusion rules and settled lists checked against source/editorial candidates, speaker runs, senders, HyDE/About descriptions and document collections. | New gaps concern A-001/A-006/A-007/A-008/A-011, without reopening the settled inclusion decisions. No additional verified whole-work removal was established beyond the plan's lists. Existing spurious/heretical works and collection regrouping remain planned. |
| Discover, HyDE and retrieval lab | Collection descriptions, guarantee/dedup behavior, evaluate and compare paths, provided `docs/eval` data and UUID-field scan. | No hard Bible-book genre filter exists in current vector retrieval; genres select HyDE prompt draws within Bible. The planned collection move must update prompts, constants and guaranteed slots together, as already specified. The provided evaluation output had no literal UUID passage target fields to validate. Snapshot lacks compare-run result bodies, so a live lab/history target audit is unverified. No paid evaluate/judge/search call. |
| Later regressions and spec interactions | Source-driven parser algorithms compared to actual paragraph/heading structure, current role propagation, packing, registry and outline refresh contracts. | A-003/A-004/A-008/A-014/A-015/A-016/A-018/A-019 show how specified fixes can preserve or worsen defects. Removing incidental editorial speaker clues must be coordinated with role metadata. The registry must handle recovered source units and chapter remaps. Future check IDs are specified per finding. Full re-embedding should store the embedding-input hash, model and dimensions to make later provenance audits possible. |

### Independent Summa structure extension

After the initial report draft, I downloaded all 87 Summa pages linked by the [Corpus Thomisticum index](https://www.corpusthomisticum.org/iopera.html), covering the four core parts I, I-II, II-II and III. The parser inventories argument, sed-contra, determination and reply units in 2,663 articles. The English div4 scan inventories 2,664 containers; four are one-article questions without a Latin article-number prefix, and the three missing English article containers are precisely A-003's combined articles. This is an independent structural census, not a comparison of every Latin sentence with every English sentence.

It produced 263 discrepancy candidates. Many are legitimate prose replies whose answer is clear from the determination, joint replies, unbold continuations or English edition variants. Four apparent short sed-contra runs were inspected in full: I q.66 a.1, q.97 a.4 and q.98 a.2 contain both arguments in one paragraph; q.89 a.3 really lacks the second, A-018. The only core argument-count deficits are I q.76 a.3's actual omission and the unrecognized arguments in II-II q.4 a.8 and q.98 a.3, already in A-015. The extension verifies six more wrong reply numbers and the later-supplied answer in A-019. An inventory mismatch alone is not a finding. Full disposition of every implicit prose reply and textual variant, and independent Supplement comparison, remain outstanding.

### Passage length census

Lengths are characters of display content, including any inline markers. P95 is the length at the 95th percentile: 95% of passages are no longer than that value. Short does not automatically mean defective.

| Collection | Live median | Live P95 | Live maximum | Live under 50 chars | Build median | Build P95 | Build maximum |
|---|---:|---:|---:|---:|---:|---:|---:|
| apostolic-exhortations | 966 | 3,555 | 3,999 | 25 | 1,021 | 3,137 | 3,993 |
| bible | 1,179 | 3,544 | 3,999 | 7 | 1,197 | 3,317 | 3,993 |
| canon-law | 330 | 952 | 2,031 | 5 | 330 | 952 | 2,031 |
| catechism | 1,369 | 3,530 | 3,999 | 0 | 1,365 | 3,240 | 3,964 |
| church-fathers | 2,291 | 3,876 | 4,000 | 0 | 2,291 | 3,876 | 4,000 |
| councils | 456 | 3,372 | 3,999 | 86 | 494 | 3,052 | 3,995 |
| encyclicals | 931 | 3,149 | 3,998 | 53 | 950 | 2,847 | 3,999 |
| medieval | 2,411 | 3,690 | 3,999 | 1 | 2,244 | 3,894 | 3,993 |
| papal-documents | 1,589 | 3,568 | 3,912 | 5 | 1,603 | 3,346 | 3,997 |
| summa | 335 | 1,521 | 3,999 | 80 | 336 | 1,550 | 3,987 |

The broad census's `brokenmarker` pattern deliberately collects all marker-bearing passages and is not a malformed-marker count. Likewise `glued` collects ordinary punctuation too. The later strict Bible validator and hand-reviewed hyphen inventory, not raw regex totals, support the conclusions above. Source labels legitimately vary across split pieces; conflicting labels in a broad chapter scan are not automatically new defects.

## Questions for Carter

### May I verify the stored reader outlines using an augmented snapshot or the read-only SELECT below?

Options: export `document_chapters` into the snapshot for a reproducible offline comparison; authorize the exact live SELECT; or leave this unverified until staging. I recommend the augmented snapshot. Every `chunk_count` matches, but that does not establish that the stored chapter ordinals and labels match. No production Postgres query was executed.

This query compares the stored outline to the first positioned passage of each chapter and the chapter order the current reader derivation uses. It returns only differences and no user data.

```sql
WITH firsts AS (
    SELECT DISTINCT ON (document_id, chapter_key)
           document_id, chapter_key, chapter_label, position
    FROM chunks
    WHERE chapter_key IS NOT NULL
    ORDER BY document_id, chapter_key, position, id
), expected AS (
    SELECT document_id, chapter_key, chapter_label,
           row_number() OVER (
               PARTITION BY document_id ORDER BY position, chapter_key
           )::integer AS ordinal
    FROM firsts
)
SELECT coalesce(e.document_id, a.document_id) AS document_id,
       coalesce(e.chapter_key, a.chapter_key) AS chapter_key,
       e.ordinal AS expected_ordinal, a.ordinal AS stored_ordinal,
       e.chapter_label AS expected_label, a.chapter_label AS stored_label
FROM expected e
FULL JOIN document_chapters a USING (document_id, chapter_key)
WHERE e.ordinal IS DISTINCT FROM a.ordinal
   OR e.chapter_label IS DISTINCT FROM a.chapter_label
ORDER BY document_id, expected_ordinal, stored_ordinal;
```

### Should detached opponent and condemned-proposition passages remain searchable before roles and context reach every model input?

Options: keep these passages reader-only temporarily; ship their explicit roles and counterpart context before publication; or retain current search exposure while implementing that later. I recommend completing role/context handling before publication, with reader-only treatment as an interim measure if needed. This preserves authentic refutations and condemnations while preventing isolated rejected propositions from being represented as endorsed teaching. It does not change the settled work-inclusion policy.

### Should publication wait for an independent inventory of every Summa article's argument structure?

Options: review the 263 core structural discrepancies, add the Supplement and compare source text against a fixed independent edition; repair only the two proved omissions now; or rely on coverage against the vendored source. I recommend completing that review. The 87-page core inventory now exists, but its candidate dispositions and the Supplement are unfinished. A-018 proves that the existing source and one familiar online edition can share an omission. Repairing two known units is worthwhile, but cannot justify the claim that this is the last corpus reopening.

## Reproduction

All paths in this section are relative to `datapipeline/releases/local/review-sol/`. Nothing here writes to production. Source text, Qdrant vectors and long excerpts stay in this gitignored directory. The public report uses small evidentiary snippets and passage identifiers.

Use the existing virtual environment through `python3` from the repository root:

```bash
PATH="$PWD/datapipeline/.venv/bin:$PATH" python3 datapipeline/releases/local/review-sol/baseline.py
```

`baseline.py` supplies the placeholder environment internally, builds every adapter once, loads the snapshot once, writes `corpus.pkl`, and invokes the actual coverage, health and release report entry points over that cache. Their output directories are `coverage/`, `health/` and `release/`. The health directory contains the combined build/live report from the second invocation. This avoids a second source build for each CLI. The release report itself verifies the snapshot hashes.

Run the remaining cached analyses with the same Python prefix and their full script paths. `replay-cached.py` reruns only the cached/local analyses listed below, saving individual logs and wall-clock times; it never reruns adapters, production network reads or FTS. The recorded replay times make the previously uninstrumented analyses reproducible. Scripts with instrumented initial runs retain their original times separately.

| Script | Purpose and principal output | Measured time |
|---|---|---:|
| baseline.py | SOURCE_ADAPTERS build and cache; original build 13.91 s, coverage 51.08 s, health build 9.09 s, health live 9.23 s, release 77.46 s | 160.77 s for measured phases |
| census.py | All row/document inventories, pattern candidates, lengths, exact duplicates and chapter/role/marker candidates | 21.02 s cached replay |
| structure.py | Source Summa key uniqueness, canon noncontiguous groups, shortest-piece census | 0.61 s cached replay |
| evidence.py | Complete papal-condemnation, canon-collision, combined-Summa and Syllabus-terminal ID sets | 0.61 s cached replay |
| trust.py | Canon ligatures, Cyprian incoming senders, Octavius speaker range, ANF Argument spans | 0.88 s cached replay |
| psalms.py | Every USFM descriptive title, missing-title evidence and first-passage IDs | 1.50 s cached replay |
| hyphens.py | Reviewed 41-form broken-word inventory across all collections | 3.24 s cached replay |
| overlaps.py | Cross-document shingle candidates in crossdoc-overlaps.json | 5.10 s cached replay |
| index-audit.py | All-point payload/vector audit, neighbor cosine and bit-identical vectors | 1.97 s cached replay |
| finishchecks.py | Exact production offline stitching; saved blank/debris/editorial counts; document counts; strict markers; duplicate-input validation | 5.35 s cached replay |
| role-scope.py | Every source Summa paragraph opening and reply without a numbered argument | 0.37 s cached replay |
| remaining-roles.py | Wrong markers, unbold fixtures, legitimate counterarguments and missing-source article sets | 0.65 s cached replay |
| final-verification.py | Snapshot hashes, public representative ID existence, all anchor URL round trips and finding-union consistency | 1.66 s cached replay |
| fts.py | Temporary local Postgres with production English vectors, all 54,568 contents; corrected-token and common-query probes | 7.20 s original, excluding cluster setup |
| index.py | Explicitly authorized read-only Qdrant metadata/count and paged scroll; vectors-chunks.npy and index-chunks.json | 127.15 s chunks scroll/export, excluding metadata calls |
| vector-probes.py | 64 existing-vector nearest-neighbor queries, no new embedding | 9.62 s original |
| replay-cached.py | Runs cached/local analyses, captures exits and times in replay-timings.json | Sum of per-script replay times |
| latin-inventory.py | Read-only download/cache of 87 core Latin pages; article/unit inventory and 263 candidates | 51.39 s original, 49.30 s downloading |
| latin-triage.py | Source paragraph boundaries and count/number differences; includes legitimate negative controls | Under 1 s; not separately timed |
| extend-evidence.py | Six additional wrong numbers and three editor-supplied/section passages | 0.47 s original |
| shorthand-replies.py | All 11 formal shorthand source replies and their 12 current pieces | 2.92 s original |
| summa-notes.py | Negative control: zero surviving balanced bracket-star note markers | 0.62 s original |
| extend-report.py | Records the extension in this report and updates union generation | Under 1 s; not separately timed |
| finish-report.py | Reconstructs the 859-ID union, sorts findings, writes this report and coverage | Under 1 s; not separately timed |

`fts.py` required local shared-memory access outside the sandbox to initialize its throwaway cluster. It used an isolated temporary directory and Unix socket, loaded no user content, and stopped the cluster afterwards. `index.py` and `vector-probes.py` required network access outside the sandbox; their source uses only the authorized read methods. Real credentials are read through dotenv and are never printed. These scripts should be reviewed before any rerun; do not substitute production Postgres or enable a write method.

Findings A-001 to A-019 each name the script and output that reproduces their counts. `finish-report.py` builds the union from those specific evidence sets, the unique first-passage IDs from the 138 Psalm title records, and the extra mixed Exsurge proposition. It excludes the A-016 future-regression fixtures. `final-verification.json` confirms every representative passage ID exists in both stores and every union ID exists. `timings.json`, `replay-timings.json`, `fts-timing.json`, `index-meta.json` and `vector-probes-timing.json` retain timings and configuration.

## Next

This review's verified findings and bounded checks are complete. The following work remains necessary for a broader certification, and should be resumed from these artifacts rather than rebuilding or rereading the other reviewer's report:

- Obtain `document_chapters` in an augmented snapshot, or explicit approval for the exact SELECT above; compare stored outline ordinals/labels.
- Complete review of the 263 core independent-inventory discrepancy candidates, add the Supplement, and collate source text where structure alone agrees. Prioritize cases where the English source and New Advent agree but the Leonine structure differs.
- Reconstruct the complete canon hierarchy against source headings, including contiguous sections; A-002 currently counts the 17 proved noncontiguous keys.
- Audit embedding provenance during the fresh full embedding pass, saving input hashes/model/dimensions. Current numeric/proximity checks cannot prove the historical input for every vector.
- Resolve all new/spec-underestimated findings before the staged release, then rerun coverage, health, identity remapping, roles, reader outlines and the new source-specific checks. The role fixtures must be exercised through ranking, explanation formatting and cards without requiring paid provider calls.
- If a full retrieval-lab ID audit is wanted, export compare-run result targets without user identities; those bodies are absent from the current snapshot. No paid end-to-end retrieval, judge, explanation or production search experiment was run.
