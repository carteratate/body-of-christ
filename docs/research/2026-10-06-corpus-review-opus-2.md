# Corpus review, second pass (reviewer: opus-2)

6 October 2026. Reviewer: Claude Opus 5.5, working alone from the brief in `docs/corpus-cleanup/CORPUS-REVIEW-PROMPT.md`, as a second reviewer after `docs/research/2026-10-06-corpus-review-opus.md` (findings A-001 to A-024). Not committed; for Carter to review.

Inputs are the same as the first review: the 6 Oct snapshot of production Postgres ("live", 54,568 passages, 421 documents), a master build of all ten adapters on `7bd2b66` ("build", 54,778 passages), and the first review's read-only dump of the production Qdrant collection `chunks`. I reused the first review's pickles in `datapipeline/releases/local/review-opus/` and wrote my own scripts and outputs in `datapipeline/releases/local/review-opus-2/`.

Anything in A-001 to A-024, the plan, or the specs is treated as known. A finding here is either new, or "known, underestimated" where the data shows the known item is materially larger or differently caused than stated.

## 1. Summary

I found 15 problems that neither the first review nor the plan covers, or that are bigger than they say. None is critical in the first review's sense of broken links or search. Two are high. The planned cleanup is close, but these items need owners before the republish, and two of them are gaps in the specs themselves rather than in the data.

**1. Letters to Cyprian are filed as Cyprian's, and one is Novatian's (B-001).** The Epistles of Cyprian hold 16 letters written by other people: the Roman clergy, Pope Cornelius, the confessors, Firmilian of Caesarea. Every card credits Cyprian. One of them, Epistle XXX, was written by Novatian, and the corpus says so itself in Cyprian's letter to Antonianus. The plan removes Novatian "entirely" under rule A, but this letter is on no list. Firmilian's letter calls Pope Stephen a Judas, under Cyprian's name. 45 passages, no saved rows.

**2. A saved passage can reopen on a different paragraph after Phase 1 (B-002).** Long chapters are split into numbered pieces (`…/p2`, `…/p3`). The frozen-ID rule (D1) says an ID keeps naming the same text, but the release report compares a unit's pieces as one block, so text sliding from one piece to the next passes. I simulated the planned note strip (1.10b): 918 surviving Fathers pieces change what they open with, 558 of them to a different paragraph, and 67 of those carry saved rows. Every later item that changes text length (1.10c's repacking, 1.1, 1.3a, 1.6) moves boundaries again. About 700 saved rows sit on pieces today.

**Medium.**
- Fathers and medieval citations embed the author's name, so 3.2's new credits ("Pseudo-Justin") will sit next to a citation still saying "Justin Martyr" (B-003).
- The 138 Psalm titles (Psalm 51's "when Nathan the prophet came to him…") and the Sirach prologue never reach the corpus, and 1.4a's verse-count check cannot see them (B-004).
- 947 papal and council passages carry footnote numbers after sentences in a form A-012's patterns miss (B-005).
- 95 editor's "Argument" summaries, 82 of them atop Cyprian's letters, belong to no item (B-006).
- Nestorius's letter at Ephesus and Mani's speeches in the Acts of Archelaus have no role label (B-007).
- 1.7's new Summa citations drop the article's question ("Whether God wills evils?") from the only field the rerankers, the explanation model and the card read (B-011).

**Low.** A second HTML-editor advert and a wrong year (Cum Sancta Mater Ecclesia, B-008); Lumen Gentium's chapter VII and Sacrosanctum Concilium's chapter VI missing from the reader (B-009); stray bracketed numbers in 39 Summa citations (B-010); non-searchable passages still feeding their neighbours' vectors (B-012); Lactantius's Epitome filed as chapters of the Divine Institutes (B-013); ligature spellings like "Irenæus" that keyword search cannot match (B-014); the Song of Songs rename breaking the sources page order (B-015).

**Users touched.** B-002 is the one that reaches saved data at scale (about 700 rows on pieces, 99 already shown to move under 1.10b alone). B-005 sits on passages with 190 saved rows, B-009 on 6, B-006 and B-013 on 3 each. The rest affect future results and what cards say, not saved rows.

**Terms.** A *piece* is one of the cards a long unit is split into. A *frozen ID* is a passage ID the 2.1 registry keeps across releases. The *reranker* is the model step that orders candidates before the user sees them. *Keyword search* is the Postgres full-text half of retrieval.

Counts by severity: critical 0, high 2, medium 6, low 7.

## 2. Findings

Ordered by severity (high, medium, low). IDs follow the order I verified them, so B-011 sits with the other medium findings.

### B-001. Letters by other people filed under Cyprian, including one by Novatian, whom rule A excludes

- **Severity:** high
- **Collections and counts:** church-fathers, document "The Epistles of Cyprian." (`aaf1a0e4`). 16 of its 82 letters were written *to* Cyprian or by third parties: 45 passages, 118,055 characters, identical in live and build. No saved rows.
- **Evidence:**
  - The letters, by chapter key `the-epistles-of-cyprian/epistle-<n>` and the title line the source prints: II "From the Roman Clergy to the Carthaginian Clergy"; XVI "The Confessors to Cyprian"; XVIII "Caldonius to Cyprian"; XX "Celerinus to Lucian"; XXI "Lucian Replies to Celerinus"; XXV "Moyses, Maximus, Nicostratus, and the Other Confessors Answer…"; XXIX "The Presbyters and Deacons Abiding at Rome, to Cyprian"; XXX "The Roman Clergy to Cyprian"; XXXVIII "The Letter of Caldonius, Herculanus, and Others"; XLV and XLVII "Cornelius to Cyprian"; XLIX "Maximus and the Other Confessors to Cyprian"; LXXIV "Firmilian, Bishop of Cæsarea in Cappadocia, to Cyprian, Against the Letter of Stephen" (13 passages); LXXVII, LXXVIII, LXXIX, replies of the martyrs in the mines.
  - **Novatian.** Epistle XXX (Oxford numbering Ep. xxx, 5 passages, `epistle-xxx/p1` to `/p5`) was written by Novatian for the Roman clergy. The corpus itself says so: Cyprian's Epistle LI to Antonianus (`epistle-li/p2`) quotes "Ep. xxx" and adds that it was written with "Novatian then writing, and reciting with his own voice what he had written". The plan excludes Novatian "entirely" under rule A limit 1 (condemned by name, Roman synod of 251), including works written before the schism, and lists his two treatises and Treatises I and III inside "Treatises Attributed to Cyprian". This letter is on no list. Epistle XXIX (Oxford Ep. xxxvi, 3 passages) is attributed to Novatian by some modern editors as well; that needs the R1 check.
  - **Firmilian against Pope Stephen.** Epistle LXXIV is Firmilian's attack on Pope Stephen I, under the author "Cyprian." on every card: `epistle-lxxiv/p1` says Stephen "has not done anything deserving of kindness" and compares him to Judas; `/p9` speaks of "this so open and manifest folly of Stephen". The live text also carries the American editor's bracketed comments on the papacy inside the letter (`/p3`, `/p9`); those are inline notes that 1.10b removes, but Firmilian's own words stay.
  - Nothing in `author`, `unit_label` or `passage_role` marks any of these 45 passages as another writer's. The only signal is the editor's title line at the top of each letter's first piece, which rule G and 1.8a would remove.
  - Reproduce: `cyprian_letters.py`.
- **What a user sees:** "Cyprian — The Epistles of Cyprian" over Novatian's words, over Cornelius's report of the Novatianist schism, over the confessor Lucian's grant of peace to the lapsed (the indulgence Cyprian fought), and over Firmilian calling the Bishop of Rome a Judas. The explanation model is told Cyprian wrote it.
- **Status:** new. The plan's Novatian rows, 3.1's target table and 3.2's label table do not mention the letter collection. D5's `passage_author` is reserved for Catena quotations and combined pages; D6's `work_key` is for works inside containers, which 1.8c applies to "Treatises Attributed to Cyprian" and "the other container documents", but no spec says the letters by others are works.
- **Owner:** 3.1 (a `rule-a` removal entry for Epistle XXX's anchors, and XXIX if R1 confirms) and 3.2 (credit the other 14 letters: `passage_author` or a `work_key` per letter with its real author, for example "Firmilian of Caesarea, to Cyprian"). R1 should record the Novatian attribution and its source (Cyprian, Ep. 55.5).
- **Check:** `attribution.letter_sender:<document>`. For letter collections, the greeting line ("X to Y, greeting") or the title line names the sender; any sender other than the document author must carry `passage_author` or a work with that author. Registry test: no passage in a rule-A-excluded author's hand (Novatian) remains active.

### B-002. A frozen piece ID can show a different paragraph after Phase 1, and no check notices

- **Severity:** high
- **Collections and counts:** every collection with split pieces (anchors ending `/pN`, `-pN`, or the Bible's `-N`). Live: 7,722 piece passages; 408 of them hold saved rows (702 rows: Fathers 340, medieval 122, Catechism 83, encyclicals 44, exhortations 38, papal 32, Bible 24, councils 19).
- **Evidence:**
  - D1 promises that "an anchor names the same unit of text in every release", so a saved passage reopens on the same text. But the release report's stability check (`release/remap.py:_stability`) joins all pieces of a unit before comparing, by design: "piece boundaries move when text is restored". 1.10b's production-safety note relies on that ("0.1c compares all pieces of a unit together, so shorter text under the same anchors passes"), and 1.6 says the same for Catechism pieces. A piece keeps its frozen ID whatever text slides under it.
  - I simulated 1.10b (strip `<note>`, keep its tail, rebuild Fathers and medieval; `sim110b.py`). It reproduces the spec's numbers exactly: 9,718 passages, 724 piece anchors gone, 210 new. Of the 5,695 build piece anchors in these two collections, 4,971 survive (`piece_shift.py`):
    - 3,669 still open with the same sentence;
    - 384 mostly overlap;
    - 360 overlap only partly (30 to 80% of their new text was in the old piece);
    - 558 hold a different paragraph (under 30%).
  - 67 of the shifted pieces (those whose opening sentence moved) carry 99 saved rows. Examples: `against-heresies-book-iii/chapter-xxi/p2` was §2 ("For before the Romans possessed their kingdom…") and becomes §3 ("Since, therefore, the Scriptures have been interpreted…"); `the-treatises-of-cyprian/treatise-vii/p5` moves from §10 (Job) to §12 (Abraham); `city-of-god/book-xiv/chapter-9/p2` (3 saved rows) opens on a different paragraph.
  - 1.10b gives redirects only to the 724 anchors that disappear. 1.10c then repacks every split unit in every collection by whole paragraphs or verses (`pack_units`), and 1.1, 1.3a, 1.6 and 1.8a change text length again, so each of them moves piece boundaries without a check.
- **What a user sees:** a bookmark or a restored search opens on the right chapter but a different passage, with no notice. The explanation stored with the search no longer matches the text.
- **Status:** new. A design gap between D1 and 0.1c's unit-level check; no spec covers it.
- **Owner:** 2.1 and 0.1c (rule), 4.1a (remap). Either make the stability check per piece (a kept piece must retain most of its own old text, otherwise it is treated as `moved` and its ID follows a redirect to the piece now holding its first 200 characters, the rule already used for vanished pieces), or freeze piece boundaries by recording each piece's first and last source paragraph in the passage registry.
- **Check:** `release.piece_stability`: for every live piece anchor kept as `same`, at least 0.8 of its own 6-word shingles appear in the build piece with the same anchor; report the user rows on any that fail.

### B-003. Fathers and medieval citations contain the author's name, so the planned relabels leave stale credits on every card

- **Severity:** medium
- **Collections and counts:** church-fathers and medieval: every passage, 10,217 live and 10,232 build, has `reference` of the form "<author> — <title>, <chapter label>" (`ingest/thml_doc.py:make_doc`, `reference=f"{author} — {title}, {label}"`).
- **Evidence:**
  - 3.2 changes credits only in the registry ("No code change beyond registry values"), and 2.2w writes the new `author` to Postgres and the Qdrant payload. Nothing rebuilds `reference`. After the republish a card for `3f1d7ed1` will carry `author` "Pseudo-Justin" and the citation "Justin Martyr — Hortatory Address to the Greeks, Chapter I". The 3.2 targets I could locate hold 483 live passages; D5 `passage_author` and D6 work credits (B-001, the anonymous Cyprian treatises, the Apostolic Canons) have the same problem.
  - `ChunkCard.tsx:mobileCitation` strips the author from the citation only when the citation starts with the payload author, so a changed author leaves the old name showing on mobile. On desktop, `primaryReference` for church-fathers prepends the document title to a reference that already holds it: today every Fathers card reads like "City of God, Augustine — City of God, Book I · Chapter 1", and the copied citation adds "(Augustine)" again.
  - The embedding input's prefix is also "<doc.author> — <doc.title>, <label>" (`writers/search_writer.py:write_document`); 2.2w changes the payload author to `passage_author` but not the embedded prefix.
  - 3.2's acceptance check ("a search … shows the Pseudo-Justin label on the card") can pass while the citation on the same card says Justin Martyr.
- **What a user sees:** "Pseudo-Justin" above a citation that says "Justin Martyr"; "Cyprian" in the citation of Firmilian's letter even after it is credited.
- **Status:** new.
- **Owner:** 1.10c (it rebuilds every reference through `piece_reference`): build ThML references from the label only ("<title>, <label>") or from the registry credit, and make 2.2w's embedding prefix use the same credit as the payload. 2.4b for the card's duplicated title.
- **Check:** `labels.reference_author_consistent`: no passage's `reference` names an author other than its resolved display author.

### B-004. Psalm titles and the Sirach prologue are dropped, and 1.4a's completeness assertion cannot see them

- **Severity:** medium
- **Collections and counts:** bible. 138 Psalm superscriptions (USFM `\d`, 6,327 characters of text, `20-PSAeng-web-c.usfm`) and the Prologue of Sirach (`46-SIReng-web-c.usfm`, `\ip` after `\is1 The Prologue…`, about 1,600 characters). None of the text is in any live or build passage.
- **Evidence:**
  - `\c 51` is followed by "\d For the Chief Musician. A Psalm by David, when Nathan the prophet came to him, after he had gone in to Bathsheba." and then `\v 1`. Build `psalms/51/1` starts at "Have mercy on me, God". The same holds for Psalm 3 (Absalom), 18, 34, 51, 52, 54, 56, 57, 59, 60, 63, 142 and the other historical titles.
  - In the Nova Vulgata and in Catholic English Bibles (NABRE) these titles are numbered verses (Psalm 51's title is verses 1 and 2). They are Scripture, not editorial headings.
  - Sirach's prologue by the author's grandson ("Whereas many and great things have been delivered to us by the law and the prophets…") is printed in Catholic Bibles before chapter 1; build `sirach/1/1` starts "All wisdom comes from the Lord".
  - 1.4a's assertion compares `(chapter, verse)` sets with the USFM, so an unnumbered `\d` or `\ip` line can never fail it. The WEB-C's own editorial `\ip` notes ("…is recognized as Deuterocanonical Scripture by…") are correctly absent and must stay absent.
  - Reproduce: `grep -c '^\\d' sources/bible/eng-web-c_usfm/20-PSA*.usfm`; no passage contains "Chief Musician".
- **What a user sees:** Psalm 51 without the line that ties it to David and Bathsheba, a frequent question; Psalm references that cannot match Church documents citing the title verses.
- **Status:** new. 1.4a, 1.4b (psalm numbering out of scope) and R3 do not mention superscriptions.
- **Owner:** 1.4a. Keep `\d` as the opening line of the psalm's first passage, without a verse marker, and add the Sirach prologue as its own passage (`sirach/prologue`). Extend the completeness assertion to `\d` text.
- **Check:** `coverage.bible.superscriptions`: every `\d` line's text appears in the passage holding that psalm's verse 1; `sentinel.sirach_prologue`.

### B-005. Footnote numbers left after sentences in 947 papal and council passages

- **Severity:** medium
- **Collections and counts:** 947 build passages in 38 documents (921 live), 2,144 occurrences: encyclicals 741, exhortations 164, papal documents 25, councils 17. 190 saved rows sit on these passages. Worst: Pastores Gregis 95, Veritatis Splendor 82, Dominum et Vivificantem 75, Ut Unum Sint 71, Ecclesia in Asia 66, Evangelium Vitae 66, Mystici Corporis 63, Redemptoris Missio 63, Fides et Ratio 55.
- **Evidence:**
  - The form is a bare number after the closing quote or full stop, separated by a space: `veritatis-splendor/44` "…Ruler of the universe". 83 Man is able…"; `ut-unum-sint/8` "…the work of ecumenism". 7 In indicating…"; `mystici-corporis-christi/51` "…you can do nothing.” 89 If we grieve…".
  - In the source these are `<sup>` elements (`veritatis-splendor.html`: `…universe&quot;.<sup><a name="-2B"></a>83</sup>`), so the adapter can drop them structurally.
  - A-012's two patterns, "(N)" after a word and digits glued to a word, match only 2 of these 947 passages.
  - Spe Salvi adds a third form, "[ 3 ]", in 26 passages.
  - Reproduce: `callers2.py`.
- **What a user sees:** stray numbers mid-sentence on cards and in the reader; the keyword index stores each as a token (A-007), and the explanation model sees them.
- **Status:** known, underestimated (A-012; 1.3a does not mention callers).
- **Owner:** 1.3a: drop numeric `<sup>` content and "[ N ]" callers in `papal_common.tokens`.
- **Check:** extend A-012's `health.R12_note_caller` with `[.!?"”’)…]\s\d{1,3}(?=\s+[A-Z“"‘]|$)`, excluding a number followed by a Bible book abbreviation, and `\[\s?\d{1,3}\s?\]`.

### B-006. 95 editor's "Argument" summaries in Cyprian and the Re-baptism treatise belong to no item

- **Severity:** medium
- **Collections and counts:** church-fathers. 163 paragraphs in live and build open with "Argument.—" or "Chapter N.—Argument": Epistles of Cyprian 82 (the opening passage of every letter), Octavius 41, City of God 22, Treatises of Cyprian 10, On Christian Doctrine 4, Treatises Attributed to Cyprian 2, Enchiridion 1, Anonymous Treatise on Re-baptism 1. About 58,000 characters after the simulated note strip.
- **Evidence:**
  - 1.8b owns 27 of them (City of God, On Christian Doctrine, the Enchiridion) and its acceptance test checks only those two works. A-011 raised the Octavius's 41. The other 95 (Cyprian's letters and treatises, the Re-baptism treatise) are in no item: 1.8a's `strip_editorial_lines` drops title lines, rule lines and bracketed credits, not "Argument" paragraphs, and 1.8a's checks would pass with all 95 in place.
  - The editor's summaries also carry judgments: `epistle-lxxiv/p1` says Firmilian wrote "with a Little More Vehemence and Acerbity Than Becomes a Bishop". After the simulated 1.10b strip every Cyprian letter still opens with the editor's number line, the editor's title and the Argument (`sim110b.py`).
- **What a user sees:** an editor's paragraph-long summary as the first lines of a Cyprian card, under Cyprian's name. The 163 passages hold 3 saved rows.
- **Status:** known, underestimated (rule G names "Argument" summaries; A-011 counted 43).
- **Owner:** 1.8a. Apply 1.8b's `^Argument[.—]` pattern to ANF volumes too, and strip the editor's "Epistle N." number and title lines at the top of each letter, keeping the letter's own greeting ("Cyprian to … greeting").
- **Check:** `editorial.argument_lines` (A-011) across all ThML files: zero paragraphs matching `^(Chapter [IVXLC]+\.?\s*[—-]+\s*)?Argument\s*[.:—]`.

### B-007. Heretics' and opponents' own texts inside councils and Fathers, with no role

- **Severity:** medium
- **Collections and counts:**
  - councils: Council of Ephesus, "Second letter of Nestorius to Cyril", 5 build passages (4 live), 10,183 characters (`council-of-ephesus/sec-3/3/p1` to `/sec-3/6`), under the author of the council.
  - church-fathers: the Acts of Archelaus (`0e326c02`, 118 passages, plus 4 in "A Fragment of the Same Disputation"): 6 passages open "Manes said", 16 contain his speeches, and chapters 7 to 11 and 13 (10 passages) are Turbo's exposition of Mani's teaching ("When the living Father perceived that the soul was in tribulation…").
  - Firmilian's letter and Novatian's letter in Cyprian (B-001).
  - No saved rows on these.
- **Evidence:** `chapter_label` "Second letter of Nestorius to Cyril" is the only signal on the Ephesus cards; Tanner prints the letter because the council read and condemned it. `unit_label` is NULL, so `passage_role` says nothing. The Dialogue with Trypho, Cur Deus Homo (Boso), the Banquet and the Consolation, which I also read, mark their speakers inline and are not misleading.
- **What a user sees:** "Council of Ephesus — Second letter of Nestorius to Cyril" presenting Nestorius's Christology as a council text; Manichaean cosmology as a Father's text.
- **Status:** known, underestimated (A-002 covers condemned propositions in Exsurge Domine, the Syllabus and Constance). 1.2c's Percival allowlist would drop the Nestorius letter only if 1.2a classifies it as non-council text, which no spec says.
- **Owner:** A-002's role item, plus 1.2a (list the Nestorius letter explicitly as "condemned text read at the council").
- **Check:** A-002's `role.condemned_propositions` registry, extended with the Ephesus letter and the Archelaus speeches.

### B-011. 1.7's new Summa citations remove the article's question from every model input and card

- **Severity:** medium
- **Collections and counts:** summa, all 26,750 live passages (26,792 build) once 1.7 lands.
- **Evidence:**
  - Today a Summa `reference` reads "Summa Theologiae, First Part, Question 19 - The Will of God (TWELVE ARTICLES), Article 9 - Whether God wills evils?". 1.7 replaces it with "Summa Theologiae I, q. 19, a. 9, ad 1" and moves only the clean part name into metadata.
  - `reference` is the only provenance the models see: `rerank_docs.cohere_document` and `llm_card` put `[reference]` at the head of each card; `llm_rerank/pointwise.py` uses it as the "reference label"; `explain.py` uses `chunk_reference` as the passage's label. None of them reads `chapter_label`, which keeps the article title.
  - For an "I answer that" passage (3,107 in the source) or a "Reply to Objection N" (9,942), the article's question ("Whether God wills evils?") is the one piece of context the text itself does not state. The new citation drops it from the reranker, the explanation and the result card at once.
  - `ChunkCard.tsx:mobileCitation` parses "Question N … Article N" out of the Summa reference; after 1.7 that regex never matches and mobile shows the raw citation.
- **What a user sees:** a card titled "Summa Theologiae II-II, q. 64, a. 6, co." with no hint that the article asks whether it is lawful to kill the innocent; explanations that cannot say which question Aquinas is answering.
- **Status:** new (a side effect of 1.7).
- **Owner:** 1.7. Keep the article question in the reference ("Summa Theologiae II-II, q. 64, a. 6, co.: Whether it is lawful to kill the innocent?"), or have the API pass `chapter_label` to the cards. `display_role` still works either way, because "Objection 4" is not a substring of "obj. 4"; the role check should be kept in a test.
- **Check:** `labels.summa_reference_has_question`: every Summa reference contains its article's "Whether …" title.

### B-008. A second site advertisement, and a wrong year, in Cum Sancta Mater Ecclesia

- **Severity:** low
- **Collections and counts:** encyclicals, `cum-sancta-mater-ecclesia/4`, 1 passage, live and build. Document year 1858.
- **Evidence:** the passage ends "…in the 13th year of Our Pontificate." followed by "Perform bulk operations on your HTML document on any HTML tag. Choose to replace, delete the whole block…", an HTML-editor advert. A-005's proposed pattern list ("wysiwyg", "subscribe for a membership", "Webmaster", "promotional messages", "papalencyclicals") does not match it. The same passage's dating line is "Given in Rome at St. Peter’s, 27 April, 1859"; the 13th year of Pius IX (elected June 1846) ends in June 1859, so the year is 1859, not 1858. Of 164 papal documents with a dating line, this is the only year mismatch (`papal_years.py`; Salutis Nostrae prints "1744", a source misprint for 1774, which the metadata has right).
- **Status:** known, underestimated (A-005, the boilerplate class).
- **Owner:** 1.3a (cut the advert), 2.3 (year).
- **Check:** add "HTML document", "HTML tag", "bulk operations" to A-005's `health.R10_site_boilerplate`; `metadata.papal_year_matches_dating_line`.

### B-009. Lumen Gentium chapter VII and Sacrosanctum Concilium chapter VI do not exist in the reader

- **Severity:** low
- **Collections and counts:** councils. LG §48–51 (eschatology, purgatory, the communion of saints; 4 passages, 6 saved rows) sit under "Chapter VI" (religious life); SC §112–121 (sacred music, 10 passages) under "Chapter V" (the liturgical year). Live and build.
- **Evidence:** the vendored LG page prints only the title "THE ESCHATOLOGICAL NATURE OF THE PILGRIM CHURCH…" with no "CHAPTER VII" line, and the SC page prints "VI SACRED MUSIC" without the word "CHAPTER", so `_CHAPTER` misses both. The outlines jump from VI to VIII and from V to VII. Separately, Gaudium et Spes labels its Part II chapters "Chapter I" to "Chapter V" again, so the reader lists "Chapter I" three times (once for a notes block), and every Vatican II chapter label is a bare numeral with no title.
- **Status:** new. 1.1 keeps `_CHAPTER` detection and has no chapter-sequence check.
- **Owner:** 1.1. Recognise "N TITLE" and a bare all-caps title after a section run as chapter headings, label chapters "Chapter VII: The Eschatological Nature…", and prefix Part I/II in Gaudium et Spes.
- **Check:** `structure.chapter_sequence`: numbered chapter labels within a document run 1, 2, 3… with no gap.

### B-010. Summa citations with stray bracketed numbers

- **Severity:** low
- **Collections and counts:** summa, 39 passages live and build.
- **Evidence:** "De Anima iii, 21,[22]", "Mat. 1:20;[2]:13,[19]", "First Part, QQ[79] and following", "(QQ[83], qu. 35)", "Ethic. x, 2,[3]". `normalize/summa.py:expand_apparatus` expands `QQ[n]-[m]`, `Q[n]`, `A[n]` and `AA[n]` but not a lone `QQ[n]` or a bracketed number after a comma or semicolon, which the source uses for its own cross-reference links.
- **Status:** new. 1.7 puts apparatus expansion out of scope.
- **Owner:** 1.7 (one regex in `expand_apparatus`).
- **Check:** `health.summa_bracket_numbers`: no `\[\d+\]` in Summa content.

### B-012. Passages kept out of search still shape their neighbours' vectors

- **Severity:** low
- **Collections and counts:** planned, not live. Applies to every `searchable = false` passage the specs add: history passages (CCC 2267's 1997 text, each amended canon's superseded text, the pre-2016 marriage canons), whole Latin canons (579, 695, 700, 868, 295, 296), the 59 Latin and Italian passages of 3.3, and A New Hope for Lebanon.
- **Evidence:** `writers/search_writer.build_embedding_input` adds the last and first N characters of the previous and next passage in the same chapter key (canon law 300, Catechism 200, default 200). D5 makes every non-searchable passage a point in the same build list, and 2.2w reuses `build_embedding_input` unchanged. No spec says where a history passage sits in `position` order or that the neighbour window skips non-searchable passages. If `ccc/2266/history-1997` sits next to the passage holding the 2018 text, that passage's vector is built partly from "very rare, if not practically non-existent"; canons 578, 580, 694, 696, 699, 701, 867 and 869 would be embedded with 300 characters of Latin.
- **Status:** new (a gap between D5, D11 and 2.2w).
- **Owner:** 2.2w: skip `searchable = false` passages when choosing neighbours, and give history passages a position after the current text.
- **Check:** `index.no_unsearchable_neighbour_text`, a unit test on `build_embedding_input`.

### B-013. Lactantius's Epitome is filed as chapters of the Divine Institutes; Stromata fragments carry Eusebius's voice

- **Severity:** low
- **Collections and counts:** church-fathers.
  - "The Divine Institutes" (`9e03c96d`): after Book VII, 79 build passages (3 saved rows) are the separate Epitome of the Divine Institutes (source div `iii.ii.viii`, "The Epitome of the Divine Institutes, Addressed to His Brother Pentadius"), labelled only "The Preface" and "Chap. I" to "Chap. LXXIII". Live and build.
  - "The Stromata" (`3a68ef3f`): the 20-passage chapter "Fragments of Clemens Alexandrinus" opens with the translator credit "[Translated by Rev. William Wilson, M.A.]", and `/p11` and `/p12` are a later writer's reports ("as Clement the Stromatist relates in the fifth book of the Hypotyposes").
- **Evidence:** the Epitome's div title has no `type="Book"`, so `make_doc` gives its chapters no book prefix and the reference reads "Lactantius — The Divine Institutes, Chap. I" for the Epitome's first chapter, whose text ("First a question arises: Whether there is any providence…") is not Divine Institutes I.1. The only marker, the Epitome's title paragraph, is under 100 characters and is dropped by `make_doc`'s length check. A-009's fragment check keys on titles containing "Fragment", so it would not see the Stromata chapter.
- **What a user sees:** a citation to "Divine Institutes, Chap. XL" that no edition of the Divine Institutes has.
- **Status:** new (Epitome); known, underestimated (A-009, for the Stromata fragments).
- **Owner:** 1.8c (a `work_key` and title for the Epitome under D6, or label its chapters "Epitome · Chapter N"); A-009's owner for the Stromata fragments.
- **Check:** `structure.embedded_work_labelled`: in a ThML document, a run of chapters with no book prefix after booked chapters must carry a `work_key` or a book label.

### B-014. Ligature spellings ("Irenæus", "Cæsar", "æons") never match what users type

- **Severity:** low
- **Collections and counts:** church-fathers and medieval mostly: 2,051 live passages (2,030 Fathers) contain a word with æ or œ; 1,157 still do after the simulated 1.10b note strip. Most frequent after the strip: æons 293, quæ 231, Cæsar 158, æon 112, Æsculapius 94, Æneas 53, Cæcilius 42, Judæa 29, Manichæus 24, Irenæus 21. Six documents carry the author "Irenæus", and titles include "Of the Manichæans" and "Epistle to the Smyrnæans".
- **Evidence:** in a local Postgres with a UTF-8 locale (C.UTF-8 and en_US.UTF-8 both), `to_tsvector('english','Cæsar and Irenæus spoke of the æons')` gives `'cæsar' 'irenæus' 'æon'`, and `to_tsvector('english','Cæsar') @@ plainto_tsquery('english','Caesar')` is false, as is "Irenæus" against "Irenaeus". With a C locale the parser splits the words at the ligature instead (`'c' 'sar'`). Either way the keyword half of search cannot find these passages by the spelling users and Church documents use.
- **What a user sees:** a search naming Irenaeus, the Manichaeans or Caesar gets no keyword candidates from the ANF passages that name them; the author shows as "Irenæus" while Catholic sources write "Irenaeus".
- **Status:** new. A-020 covers unstemmed archaic verb forms, not ligatures.
- **Owner:** 1.10a: fold æ, œ, Æ, Œ to ae, oe, Ae, Oe in `clean_text` and in author and title labels (a whitespace-only check like 1.10a's will need an exception for this mapping).
- **Check:** `health.no_ligatures`: no æ or œ in content, author or title outside Greek or Latin quotations.

### B-015. Renaming "Song of Solomon" moves it to the end of the Bible on the sources page

- **Severity:** low
- **Collections and counts:** bible, 1 document (`9df0b246`), once 1.4a lands.
- **Evidence:** `apps/web/src/components/sources/SourcesPage.tsx` sorts the Bible grid by a hard-coded `BOOK_ORDER` that contains "Song of Solomon"; unknown titles "sort to the end". `services/api/app/routes/evaluate.py:44` names "Song of Solomon" in its prompt. 1.4a renames the title to "Song of Songs" and mentions neither file. The same will happen to any book title a later item changes.
- **Status:** new (a side effect of 1.4a).
- **Owner:** 1.4a (or 2.4b): update both strings in the same PR, or sort the grid by a canonical order carried in document metadata.
- **Check:** a web test that every Bible title returned by `/sources` has a rank in `BOOK_ORDER`.

## 3. Coverage map

What I examined in this second pass, on top of the first review's map. "Clean" means I looked and found nothing new beyond the items named.

| Area | What I checked | Result |
|---|---|---|
| Attribution inside container documents | Every letter of the Epistles of Cyprian (title line and greeting); the Acts of Archelaus and its fragment; the eight "Anatolius and Minor Writers" documents; Alexander of Alexandria's epistles; the early councils (Nicaea to Nicaea II) passage by passage; the Dialogue with Trypho, Cur Deus Homo, the Banquet and the Consolation for speaker marking | B-001, B-007, B-013. Malchion's synodal letter is his by Eusebius's report; Alexander's encyclical is his; Cyprian's council letters (LVII, LVIII, LXXI) name him as presiding: acceptable. Trypho, Boso, the virgins of the Banquet and Philosophy are marked inline and are not misleading. The Muratorian fragment inside "Fragments of Caius" is already in 3.2. |
| Whole documents read (first and last characters of every passage, in order) | Imitation of Christ, Gaudium et Spes, Lumen Gentium (outline and §38–60), Dei Verbum (outline), Sacrosanctum Concilium (§111–122), Veritatis Splendor, Spe Salvi, Deus Caritas Est, Salvifici Doloris, Porta Fidei, Misericordia et Misera, Cur Deus Homo, On Loving God (opening), Romans, Wisdom, the Epistles of Cyprian (openings of all 82 letters), the Divine Institutes and the Stromata (outlines and fragments) | B-005, B-006, B-009, B-013. Otherwise only known defects: trailing headings (A-003) in Deus Caritas Est ("PART I"), Salvifici Doloris ("II", "III"), Spe Salvi and Veritatis Splendor; bucket chapters (1.3a) in Porta Fidei and Misericordia et Misera; Romans lacks its doxology (1.4a, 1.4b); Wisdom is one passage per chapter (1.4c). The Imitation labels 49 Book III chapters and most of Book IV "Chapter N" although the source titles them; 1.9 says only Book I chapter 1 has this, but its fix ("prefer the full title") covers all of them. |
| Papal metadata | Year of all 164 papal documents with a dating line against that line; author against each source URL's pope; reign ranges | One wrong year (B-008). Authors all match their URLs. |
| Papal references | Whether the passage at `<slug>/<N>` starts at paragraph N of the source (8,022 checked) | Clean apart from known invented numbers (0.1a). 13 apparent mismatches were all repeated sentences found earlier in the source. |
| Council metadata | Years and titles of all 36 documents | Clean apart from the known first-or-last-year mix and missing authors. |
| Bible | Book list against the Catholic canon; USFM markers dropped by the adapter (`\d`, `\ip`, `\is`, `\s1`, `\ms1`, `\sp`); USFM residue, brackets and footnote text in verses; Psalm sample | B-004, B-015. No `\f` footnotes, Strong's numbers or backslashes reach content; the WEB-C's own introductions (`\ip` "…is recognized as Deuterocanonical Scripture…") are correctly absent. Esther's brackets and Daniel are known (R3, 1.4a). |
| Canon law | Embedded "Can. N" headings inside other canons | Only the known glued canons and footer (1.5a). |
| Non-English text outside the Fathers | Latin, Italian and French stopword ratios over every non-Fathers passage | Only known: Ubi Lutetiam (3.3), canon 111 (1.5b). The French in C'est la confiance is a short quoted title. |
| Site boilerplate and credits | Advertising, "Webmaster", publisher and translator credits across all collections | B-008; the rest are known (A-005, A-010, endnote walls in 1.3a, Tanner introductions in 1.2). |
| 1.10b simulation (first review's Next) | Rebuilt Fathers and medieval with `<note>` stripped (`sim110b.py`); recounted Greek, Latin and long brackets | Reproduces 1.10b's 724 and 210 anchor counts exactly. Passages with 3 or more Greek characters fall from 1,929 to 278 (4,460 Greek characters left, nearly all the authors' own Greek words, such as Augustine's λατρεία); Latin passages stay at 44 (the known 3.3 list plus one); bracketed spans of 6 or more words fall from 3,052 to 155, consistent with 1.8a's 196. Side effect: B-002. |
| "Chapter N.—Title" lines (first review's Next) | 1,625 such lines after the note strip, sampled per work | City of God 628: the ancient Latin capitula, keep. On the Trinity (in Doctrinal Treatises) 357 and On Christian Doctrine 150: chapter divisions and titles of the later (Benedictine) editors, editorial. Banquet 81, To His Wife 16, On the Apparel of Women 19: the ANF translators' titles, editorial. Refutation, Origen, other Tertullian works, Of the Manichæans and Novatian are removed by 3.1. Octavius: A-011. See Question 6. |
| Lumen Gentium "(N*)" (first review's Next) | Source markup | A second, starred series of note callers whose notes the vendored page does not print; pure noise, to strip with the other callers (A-012). |
| Split pieces and frozen IDs | Every surviving piece anchor after the simulated 1.10b; the release report's stability code; 1.6, 1.10b, 1.10c and 4.1a wording | B-002. |
| Model inputs and card fields | What `rerank_docs`, `llm_rerank`, `explain`, `passage_role` and `ChunkCard` read; how 1.7, 1.10c, 2.2w and 3.2 change those fields | B-003, B-011, B-012. `display_role` keeps emitting Summa roles after 1.7. |
| Structural anchors (2.1) | Every ThML file's div ids: duplicates, existing dashes, collisions if dots become dashes, unsafe characters | Clean: 0 duplicates and 0 collisions in all 15 files. |
| ThML chapters dropped for length | Chapters under 100 characters that `make_doc` skips | 5, of which one is author text (a one-sentence Methodius fragment) and one hides the Epitome's title (B-013). |
| Full-text behaviour | Ligatures under C, C.UTF-8 and en_US.UTF-8 locales | B-014. |
| Hard-coded names in the API and web | Author, title and book strings that relabels would break | B-015. "Catholic Church" (card) and "Second Vatican Council" (sources page grouping by metadata) survive the planned changes. |
| Search index | Not re-dumped; the first review's dump and its findings stand. I checked the planned writer and payload against the API's reads instead | B-003, B-012. |
| Pagan voices in City of God and the Consolation | City of God passages after the note strip whose text is more than 60% quotation and that name Varro, Porphyry, Cicero, Apuleius, Sallust, Hermes, Seneca or Plato; the Consolation's Book I and II openings | One City of God passage (VI.10, Seneca's attack on civic religion, which Augustine endorses). The Consolation's complaints against Fortune and Providence are Boethius's own persona, answered in the same book and marked by the dialogue. Acceptable. |
| Not checked | Every Dionysius fragment; production Postgres beyond the snapshot; any paid call (no vector test of reference queries) | See Next. |

## 4. Questions for Carter

1. **Should Cyprian's Epistle XXX, which Novatian wrote for the Roman clergy, be removed like Novatian's other works?**
   - (a) Remove it under rule A limit 1 (`rule-a`, citing Cyprian, Ep. 55.5 for the authorship and the Roman synod of 251 for the condemnation). Consistent with "Novatian: out entirely".
   - (b) Keep it, credited "Roman clergy (drafted by Novatian)". It is a short pastoral letter with no Novatianist doctrine, but the plan made no exception for pre-schism works.
   - Recommendation: (a), and ask R1 to settle Epistle XXIX (Oxford xxxvi), which some editors also give to Novatian.

2. **How should the 14 other letters written to Cyprian be credited?**
   - (a) A work per letter (`work_key`) with its real author (Cornelius, Firmilian, the Roman clergy, the confessors), shown on cards.
   - (b) `passage_author` on each passage.
   - (c) Remove letters not by Cyprian.
   - Recommendation: (a). D6's work model already exists for container documents, and Cornelius's and the confessors' letters are valuable history that a reader expects to find in this collection.

3. **Should a frozen piece ID follow its text when piece boundaries move (B-002)?**
   - (a) Yes: a per-piece stability check, and a redirect from a shifted piece to the piece now holding its first 200 characters, as for vanished pieces. About 700 saved rows sit on pieces today.
   - (b) Freeze piece boundaries in the passage registry, so Phase 1 text changes cannot move them.
   - (c) Accept that a bookmark on a piece may open on neighbouring text.
   - Recommendation: (a). It reuses the existing redirect machinery and keeps D1's promise for saved data.

4. **Should the Summa's new citations keep the article's question (B-011)?**
   - (a) "Summa Theologiae II-II, q. 64, a. 6, co.: Whether it is lawful to kill the innocent?"
   - (b) The short form 1.7 specifies, with the API sending `chapter_label` to the rerankers and the explanation model.
   - Recommendation: (a). One field change, and the card, the copy text and every model see the question.

5. **Should Psalm titles and the Sirach prologue be restored (B-004)?**
   - (a) Yes, as the unnumbered first line of each psalm's first passage and as a `sirach/prologue` passage, keeping WEB-C verse numbers.
   - (b) Leave them out.
   - Recommendation: (a). They are Scripture in every Catholic Bible, and Psalm 51's title is a common search.

6. **What should happen to the later editors' chapter titles printed at the top of passages in On the Trinity, On Christian Doctrine, the Banquet and Tertullian's two remaining works (about 640 lines)?**
   - (a) Move each into the passage's chapter label and out of the content.
   - (b) Strip them under rule G and keep bare "Chapter N" labels.
   - (c) Leave them in the content.
   - Recommendation: (a). The titles help a reader navigate, but in the content they put an editor's sentence under the author's name. City of God's ancient capitula stay in either case.

## 5. Reproduction

All scripts are in `datapipeline/releases/local/review-opus-2/` (gitignored). Run from that folder with `python3 <script>`; the two that rebuild adapters run from `datapipeline/` with the placeholder variables from the brief. No script calls Qdrant, Postgres in production, or a paid API. The first review's `corpus.pkl` is the input for most of them.

| Script | What it does | Time |
|---|---|---|
| `load.py` | Loads the first review's `corpus.pkl` (build, live, documents, saved-row counts); imported by the others | under 1 s |
| `cyprian_letters.py` | Letters by other writers in Cyprian's Epistles (B-001) | under 1 s |
| `sim110b.py` | Rebuilds Fathers and medieval with `<note>` stripped (1.10b simulation), writes `sim110b.pkl` | 4 s |
| `after110b.py` | Greek, Latin and long-bracket counts before and after the simulated strip | 2 s |
| `piece_shift.py` | Piece anchors whose text moves after the simulated strip, with saved rows (B-002) | 2 s |
| `callers2.py` | Spaced numeric footnote callers in papal and council passages (B-005); `callers.py` is the first, noisier version | under 1 s |
| `papal_years.py` | Papal years against reigns and dating lines (B-008); the "Given at" variant is inline in the session | under 1 s |
| `papal_refs.py` | Papal `<slug>/<N>` anchors against source paragraph numbers | 3 s |
| `short_chapters.py` | ThML chapters skipped for being under 100 characters | 4 s |
| `inline_checks.py` | The small checks behind B-004, B-006, B-007, B-008, B-009, B-010 and B-013 | 1 s |
| `dumpdocs.py` | Compact first/last-characters dump of chosen documents into `docs_read/` | under 1 s |
| local Postgres | `initdb` in a `mktemp -d /tmp/opg2.XXXX` folder with C, C.UTF-8 and en_US.UTF-8 locales; `to_tsvector` ligature tests (B-014); stopped and deleted after | about 10 s each |

## Next

Not yet checked, in priority order:

- Every passage of Dionysius's "Extant Fragments", to size Eusebius's framing exactly (first review's Next, still open).
- Other container volumes for B-001's class beyond Cyprian and Dionysius (Julius Africanus, the Hippolytus fragments). Dionysius's 14 letters are all his own; only A-009's Eusebius framing applies there.
- Run 1.10c's `pack_units` rule on the build (once written) to count piece shifts in the other collections (B-002).
- A vector test of reference-style queries, which needs about $0.001 of embeddings and Carter's approval.
