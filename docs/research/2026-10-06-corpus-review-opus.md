# Corpus review (reviewer: opus)

6 October 2026. Reviewer: Claude Opus 5.5, working alone from the brief in `docs/corpus-cleanup/CORPUS-REVIEW-PROMPT.md`. Not committed; for Carter to review.

Inputs:

- **Live**: the 6 Oct 2026 snapshot of production Postgres, `datapipeline/releases/snapshots/2026-10-06/` (54,568 passages, 421 documents).
- **Build**: a master build of all ten adapters on `7bd2b66` with the vendored sources (54,778 passages, 421 documents).
- **Index**: a read-only dump of the production Qdrant collection `chunks` (54,568 points with payloads and vectors), taken 6 Oct 2026. Only `get_collections`, `get_aliases`, `get_collection`, `count` and `scroll` were called.

"Live" means what users see today; "build" means what the adapters produce now and what Phase 4 will publish unless a Phase 1 item changes it.

## 1. Summary

The planned cleanup is broad and mostly well aimed, but it is not yet enough for the corpus never to need reopening. I found 24 problems the plan does not handle or handles only in part. Four are serious enough that I would fix them before the republish.

**1. The Catechism is missing text, and no check notices.** The Catechism's own definition of an indulgence (CCC 1471, "An indulgence is a remission before God of the temporal punishment…") is not in the corpus. The opening of the Ten Commandments section (CCC 2052 to 2074, "Teacher, what must I do…?") keeps only about 120 characters of each paragraph: one card stops at "give to the" and the next starts "are inseparable from the Commandments". The ordination prayers and other liturgical prayers the Catechism quotes (CCC 1217–1221, 1299, 1381–1383, 1541–1543, 1586–1587) are dropped. At least 43 numbered paragraphs lose text, live and in the build. The coverage check reports 98.96% and passes, because the loss is about 1% of the whole book, concentrated in a few places. The cause is one function in the Catechism adapter, and the Catechism spec (1.6) does not mention it. Catechism passages are the most heavily used in the corpus: about one in two has been returned to a user.

**2. Some cards show a heretic's words under a pope's or council's name.** Exsurge Domine is stored as 41 numbered paragraphs, and each one is a proposition of Luther's that Leo X condemned ("In every good work the just man sins."). A card reads "Pope Leo X — Exsurge Domine, §31" with nothing saying the sentence is condemned. Users have already saved three of these passages (six saved rows). The Syllabus of Errors (80 condemned propositions) has the same shape, softened only by its title, and the Council of Constance holds about 120 condemned articles of Wyclif and Hus. The Summa's objections carry a role label that tells the ranking and explanation models what they are. These carry none, and no spec covers them.

**3. Papal documents have the wrong structure.** In 982 passages across 63 papal documents, the heading of the *next* section is glued onto the end of the passage ("…Seminaries", "DARK CLOUDS OVER A CLOSED WORLD"). Meanwhile 115 papal documents (4,265 passages) show the reader chapter list as "Paragraphs 1–20, 21–40…", including Fratelli Tutti, Dilexit Nos and Menti Nostrae, whose real section titles are exactly those glued headings. Spec 1.3a handles only numbered headings and documents of 20 paragraphs or fewer, so this survives the planned fix.

**4. Search drops distinct canons and Summa parts as "duplicates".** A dedup step (deduplication: removing near-copies from the results) discards one of any two passages from the same document within two positions whose search vectors are more than 90% similar. A search vector (embedding) is the list of numbers the search index uses to find a passage by meaning. Because each canon's vector is built mostly from its neighbours' text (300 characters on each side), 36% of nearby canon pairs pass that bar, as do 21% of nearby Summa parts (44% of objection pairs). Two different canons that both answer a question can therefore not both be shown. The republish rebuilds the vectors the same way, so this persists.

Other findings, in brief:

- A site advertisement ("Web content composed with the free online wysiwyg HTML editor…") is a whole Trent passage. Exsurge Domine §41 contains 1,833 characters taken from a 1964 secondary translation, plus a "Webmaster comment".
- Canon-law chapter keys omit the Part, so unrelated titles merge: 17 reader chapters span separate runs (209 canons). Book IV "Title I" puts sacramentals and sacred places in one chapter.
- Full-text search (Postgres keyword matching) indexes verse markers and footnote numbers as words and never sees references. A search for "John 3:16" matches passages from Maccabees, and "canon 1055" matches nothing. Spec 1.6's planned "§2267" marker will not match "CCC 2267".
- The Martyrdom of Polycarp and the Martyrdom of Justin are credited to the martyrs themselves. In 16 fragment collections (448 passages), the words of the Father who quotes the fragment, such as Eusebius, appear under the fragment's author.
- Editors' matter survives in places the specs do not list: the introduction to Haerent Animo, the translator credit in Menti Nostrae, the table of contents of Africae Munus, 40 "Argument" chapter summaries in the Octavius, and source lines in the Hippolytus fragments.
- Smaller items: inline footnote callers in 668 papal passages; 12 points that share another passage's identical vector; footers and markers spec 1.5a misses; About-page claims that 2.4c leaves standing.

**How many users this touches.** Saved rows are few. 1,925 passages hold any saved row (3,491 retrievals, 25 bookmarks, 260 guest results, 3 labels). The findings above touch at most a few dozen of those rows. The harm is mostly to future results, not to saved data.

**Is the cleanup enough?** Not yet. It needs at least:

- a Catechism fix and a per-paragraph completeness check;
- a role label for condemned propositions;
- heading-aware papal structure;
- a decision on the dedup threshold;
- the attribution additions.

**Index health.** The search index itself is consistent with the reader store: no orphans, no missing points, and payloads equal to Postgres except the 21 known blank Summa rows. The August re-embed of mismatched vectors evidently ran; I found no vector built from unrelated text except the 12 identical vectors.

Counts by severity: critical 2, high 3, medium 8, low 11.

## 2. Findings

Each finding states live and build counts. Commands are in section 5; every script is in `datapipeline/releases/local/review-opus/`.

### A-001. Catechism adapter drops liturgical prayers, the indulgence definition and most of CCC 2052–2074

- **Severity:** critical
- **Collections and counts:** catechism. 43 numbered paragraphs lose whole source lines with no overlap in any passage (1,321 words in the build, 1,351 live), plus partial losses I did not count, such as CCC 1471. The worst node is `toc-278` (CCC 2052 to 2074): 782 of 2,004 source words absent in the build (39%), 827 live. Other nodes: `toc-190` (CCC 1581–1589) 203 of 914 words, `toc-185` (1539–1553) 169 of 1,351, `toc-172` (1471–1479) 95 of 846, `toc-138` (1217–1228) 74 of 852. Live and build.
- **Evidence:**
  - The source sentence beginning "An indulgence is a remission before God" exists once in `sources/catechism/ccc.json` (node `toc-172`, under "What is an indulgence?") and in no live or build passage. `ccc/1478` holds only the later "An indulgence is obtained through the Church…".
  - Build `ccc/2053` is 120 characters and ends "give to the"; `ccc/2054` starts "are inseparable from the Commandments". The source has five lines between them ("poor, and you will have treasure in heaven…", "the Law has not been abolished…").
  - The live passages `ccc/2052` to `ccc/2057` are 112 to 197 characters each.
  - Dropped lines by source attribute (build): 84 indented lines (liturgical texts, 759 words), 36 plain lines (484 words, almost all `toc-278`), 13 headings (78 words).
  - Cause: `ingest/catechism.py:is_section_header` tests `"indent" in paragraph`, but the source keeps `indent` under `paragraph["attrs"]`. It also treats any line under 120 characters with no paragraph number as a header. `toc-278` stores each printed line as its own "paragraph", so most of its lines become "headers", and header-only sections are later dropped. I did not trace the drop step itself.
  - The 0.1a coverage report gives `ccc.json` 98.96% (pass). The sequence check finds every CCC number present, because each paragraph keeps its first line.
  - Reproduce: `ccc_loss.py`, `ccc_loss2.py`.
- **What a user sees:** "What is an indulgence?" cannot retrieve the Catechism's definition. CCC 2053 shows a sentence cut off mid-phrase ("…sell what you possess and give to the"). The reader skips the Church's baptismal and ordination prayers that the Catechism quotes as teaching. Catechism passages are the most heavily used per passage (378 saved retrievals on 800 passages).
- **Status:** new. 1.6 covers 2267, lowercase starts, chapters and references, not this.
- **Owner:** 1.6 (extend it): fix `is_section_header` to read `attrs.indent`, join line-per-paragraph nodes before header detection, and add a per-paragraph completeness assertion.
- **Check:** `coverage.catechism.paragraph_words:<n>`. For every CCC number, the words of its source paragraphs, joined across lines, must be 99% present in the passages citing it. This replaces sentence matching, which line-broken sources defeat. Also `sentinel.ccc_1471_definition`.

### A-002. Condemned propositions are presented as the teaching of the pope or council that condemned them

- **Severity:** critical
- **Collections and counts:**
  - papal-documents: Exsurge Domine §1 to §41, 41 numbered passages of Luther's propositions (live and build).
  - encyclicals: Syllabus of Errors §1 to §80, 80 passages (live and build).
  - councils: Council of Constance sessions 8 and 15, about 120 passages: Wyclif's 45 articles (`council-of-constance/sec-10/*`) and Hus's 30 (`sec-17/*`). Live and build.
- **Evidence:**
  - Exsurge Domine passages carry `unit_label` "§N" and reference "Exsurge Domine, §N", e.g. §31 "In every good work the just man sins." and §10 "Sins are not forgiven to anyone, unless when the priest forgives them he believes they are forgiven…". Saved rows: §7 1, §10 1, §11 4 (live).
  - Constance `sec-10/3` reads "Christ is not identically and really present in the said sacrament…" under "Council of Constance — SESSION 8"; 2 saved rows in sessions 8 and 15.
  - Nothing in `unit_label`, the title (except "Syllabus of Errors") or `passage_role.display_role` tells the reranker or the explanation model that the passage is a condemned error.
  - Exsurge's chapter labels are "Paragraphs 1–20" and "Paragraphs 21–40".
- **What a user sees:** a card "Pope Leo X — Exsurge Domine, §10" stating that absolution depends on the priest's belief, with an explanation that may present it as papal teaching. This is the Summa objection problem in collections with no stitching or role label.
- **Status:** new. 1.3b gives genres only; Constance is replaced or retired by 1.2e and D9, but any Schroeder or later text of Constance or Vienne brings the class back.
- **Owner:** new item, or 3.2. Give these units a role (for example `unit_label` "Condemned proposition 10", or a passage note) that `passage_role` passes to the rerankers and the explanation prompt. Or exclude them from search and keep them in the reader. See Questions.
- **Check:** `role.condemned_propositions:<document>`. A registry of documents known to list condemned propositions (Exsurge Domine, Syllabus, Constance, Vienne's Beghard errors, and later Unigenitus or Auctorem fidei if added); every passage in their listed ranges must carry the role.

### A-003. Papal documents: next section's heading glued to the end of the passage; real sections replaced by "Paragraphs N–M" buckets

- **Severity:** high
- **Collections and counts:** encyclicals, apostolic-exhortations, papal-documents.
  - 982 build passages in 63 documents (952 live, 64 documents) end with a short heading line belonging to the next section: exhortations 452, encyclicals 433, papal documents 97.
  - 115 documents (4,265 build passages) use "Paragraphs N–M" bucket chapters. 24 of them carry 3 or more glued headings, e.g. Menti Nostrae 101, Fratelli Tutti 87, Dilexit Nos 50, Querida Amazonia 31, Quartus Supra 14.
  - Encyclicals alone have 3,855 passages under bucket or "Preamble" labels.
- **Evidence:**
  - `fratelli-tutti/8` ends "DARK CLOUDS OVER A CLOSED WORLD", which is the next section's title, while its chapter label is "Paragraphs 1–20". Similarly `ubi-primum/2` ends "Selecting Clerics", `salvifici-doloris/4` ends "II", and `dies-domini/18` ends "DIES CHRISTI".
  - A random sample of 25 hits gave 25 genuine headings.
  - Separately, 18 papal re-entries into a bucket chapter key (`laudate-deum/bucket-0` resumes at `/3-2`, `/4-2`, `/5-2`, `/6-2`) come from list items, which 1.3a already names.
  - Reproduce: `trailhead.py`, `reader.py`.
- **What a user sees:** a card about one topic ending with an unrelated title. The embedding, the keyword index and the explanation all carry the next section's words. In the reader, Fratelli Tutti lists 15 numbered buckets instead of its eight titled chapters, and each title appears as a stray last line.
- **Status:** known, underestimated (1.3a). 1.3a treats only a *numbered* short paragraph as a heading, and buckets only documents of 20 paragraphs or fewer. Vatican II's spec (1.1) does the right thing for its subheadings: it prepends them to the next section.
- **Owner:** 1.3a. Treat an unnumbered short line with no final punctuation, between numbered paragraphs, as a heading. Move it to the start of the next section and use the heading levels for chapters.
- **Check:** `health.R9_trailing_heading`: the last paragraph of a passage is under 90 characters, has no final punctuation and starts with a capital, and a following passage exists. Block in papal collections after 1.3a. Also `structure.bucket_chapters_with_headings`: a document that has headings in its source may not use "Paragraphs N–M".

### A-004. Dedup discards distinct adjacent canons and Summa parts as near-duplicates

- **Severity:** high
- **Collections and counts:** index plus pipeline. Same-document pairs within 2 positions whose vectors exceed the 0.9 cosine threshold in `services/api/app/rag/dedup.py` (cosine similarity is the measure of how alike two vectors are):
  - canon-law: 1,246 of 3,491 pairs (35.7%), all distinct canons;
  - summa: 10,983 of 53,497 (20.5%), including objection-to-objection 3,225 of 7,379 (44%) and "On the contrary" to "I answer that" 789 of 3,014;
  - councils: 376 (8.9%);
  - encyclicals: 513 (4.3%);
  - other collections under 3%.
  Live vectors; the build will be embedded the same way.
- **Evidence:**
  - The median cosine between adjacent canons is 0.910.
  - `content_embedding_input` (`datapipeline/stages/embed.py`) adds 300 characters of each neighbour to every canon (`PER_COLLECTION_OVERLAP["canon-law"] = (300, 300)`), so a canon of under 300 characters is embedded from text that is two-thirds its neighbours'. Canon 1583 is 84 characters.
  - For the Summa (overlap 0), parts share the prefix and article title.
  - `apply_dedup` drops the lower-scored of any such pair before the per-source cap.
  - Reproduce: the dedup collision block in section 5.
- **What a user sees:** for "who may be a sponsor", canons 872 to 874 and 892 to 893 cannot appear together if they sit within two positions. A focused Summa search (quota 10, cap 4 per article) loses a second objection or the respondeo when both rank.
- **Status:** new.
- **Owner:** retrieval follow-up (RF) with an eval. Either raise the threshold or compare the vectors of the *clean* passage text, or reduce the canon-law overlap. Decide before 4.1b so the republish embeds once.
- **Check:** `index.dedup_collision_rate:<collection>`. The share of nearby same-document pairs above the dedup threshold, reported in the release report; flag above 5%.

### A-005. Site junk and secondary-source interpolation in Trent and Exsurge Domine

- **Severity:** high
- **Collections and counts:** councils 1 passage, papal-documents 1 passage. Live and build.
- **Evidence:**
  - `council-of-trent/sec-0/21` (154 characters) is entirely "Web content composed with the free online wysiwyg HTML editor. Please subscribe for a membership to remove promotional messages…".
  - `exsurge-domine/41/p3` holds 1,833 characters in `{…}` braces followed by "* Webmaster comment: This added text in italics was obtained from a secondary source, translator Hans J. Hillerbrand, ed. … (London: SCM Press Ltd., 1964), pp80-84".
- **What a user sees:** an advert as a Council of Trent card. In Exsurge, text the site imported from a 1964 book, plus the webmaster's note, under Leo X's name.
- **Status:** new. 1.2b rebuilds Trent but keeps "the existing chrome filter" and has no check for this text. 1.3a does not mention the Exsurge interpolation.
- **Owner:** 1.2b (Trent) and 1.3a (Exsurge: cut `{…}` spans and the webmaster note; record them as `rule-g-editorial` spans).
- **Check:** `health.R10_site_boilerplate`, a blocking pattern list in `health_patterns.json`: "wysiwyg", "subscribe for a membership", "Webmaster", "promotional messages", "papalencyclicals".

### A-006. Canon-law chapter keys merge unrelated titles; amended canons sit under the wrong chapter

- **Severity:** medium
- **Collections and counts:** canon-law. 17 chapter keys span separate runs, holding 209 canons; 38 labels are bare "Book N — Title N" with no Part. Live and build.
- **Evidence:**
  - `canon-law/book-ii/title-i/c` holds cc. 208–223 (obligations of all the faithful) and cc. 573–606 (institutes of consecrated life).
  - `canon-law/book-iv/title-i/c` holds c. 849, cc. 1166–1172 (sacramentals) and cc. 1205–1213 (sacred places).
  - Book VI Part I and Part II titles share keys (cc. 1364, 1370, 1379, 1392, 1397 re-enter). Book VII Title III/IV keys re-enter at cc. 1526 and 1717.
  - c. 265 sits under "Special Norms for Associations of the Laity", and cc. 686 and 694 under "Conferences of Major Superiors".
  - Reproduce: `reader.py` and the canon-law block in section 5.
- **What a user sees:** opening "Book IV — Title I" in the reader shows baptism, sacramentals and sacred places in one chapter. Dedup counts canons from different titles as one source, so they compete for the same two slots.
- **Status:** new. 1.5a fixes canon text, not chapter keys. The misplaced 265 and 686 may move once 1.5a reads the amendment markers correctly; nothing checks that.
- **Owner:** 1.5a. Build chapter keys from the full Book/Part/Section/Title/Chapter path.
- **Check:** `structure.chapter_contiguous:<collection>`. Every chapter key's passages form one contiguous run. Blocking for canon law, the Catechism and the Summa, where dedup keys on chapter.

### A-007. Keyword search indexes verse markers and note numbers, and cannot see references

- **Severity:** medium
- **Collections and counts:** all. Every Bible passage (`{{v:N}}` becomes tokens `v` and `N`); 668 papal passages with "(N)" callers, and 432 such callers in Vatican II; references and titles appear in no `search_vector`.
- **Evidence:** in a local Postgres with the generated column from migration 0004 loaded from the snapshot:
  - `to_tsvector('english','… {{v:4}} …')` gives `'4'` and `'v'`.
  - The search for "John 3:16" in the Bible returns 1 and 2 Maccabees passages, which contain "John" and markers 3 and 16.
  - "psalm 23" returns Acts 1:12, Acts 13 and Judith 16, not Psalm 23.
  - "canon 1055" returns 0 rows.
  - 1.6 plans "§2267" markers so "exact-paragraph queries" match, but `plainto_tsquery('english','CCC 2267')` requires the token `ccc`, which no content holds.
  - The API sends the raw user question to `plainto_tsquery`, which requires every content word to match.
  - Reproduce: the full-text block in section 5.
- **What a user sees:** reference-style questions get irrelevant lexical candidates that then earn fusion credit, and lexical search never finds the cited unit itself.
- **Status:** new. 2.2c decides "no DDL" without considering this.
- **Owner:** 2.2c (reopen). Options: generate `search_vector` from `regexp_replace(content, '\{\{v:\d+\}\}', '', 'g')` plus the reference, weighted; or strip markers before FTS. This rewrites the table, so it belongs inside the 4.0 compaction window.
- **Check:** `fts.no_marker_tokens`: no tsvector holds the lexeme `v` produced from `{{v:`. Also `fts.reference_lookup` sentinels: "canon 1055", "CCC 1471", "John 3:16" each return their unit lexically.

### A-008. Martyrdom accounts credited to the martyrs

- **Severity:** medium
- **Collections and counts:** church-fathers. The Martyrdom of Polycarp (`f8faac83`, 22 passages, author "Polycarp") and The Martyrdom of Justin Martyr (`cf8278dd`, 5 passages, author "Justin Martyr"). Live and build.
- **Evidence:** the first passage of the Polycarp document opens "We have written to you, brethren, as to what relates to the martyrs, and especially to the blessed Polycarp…", the letter of the church of Smyrna. The Justin account narrates his trial and death. Neither is in 3.2's label table or in the plan's "Labels for works that stay"; only the Martyrdom of Ignatius gets a note (D10).
- **What a user sees:** "Polycarp — The Martyrdom of Polycarp" as if Polycarp described his own death.
- **Status:** new.
- **Owner:** 3.2. Add rows crediting the Church of Smyrna (Martyrdom of Polycarp) and an anonymous author (Acts of Justin), with certainty labels, under rule H.
- **Check:** `attribution.narrative_of_author_death`. A registry validator flags any work whose title starts "Martyrdom", "Passion" or "Acts of" with `author` equal to the martyr's name and no note.

### A-009. Fragment collections put the quoting Father's words under the fragment author's name

- **Severity:** medium
- **Collections and counts:** church-fathers. 16 fragment documents, 448 passages. At least 48 open with framing by the quoting author, and that heuristic undercounts. Live and build.
- **Evidence:**
  - Papias, `Fragments` I begins with Eusebius's bracketed account ("[The writings of Papias in common circulation are five in number…]").
  - "Other Fragments from the Lost Writings of Justin" I to V begin "The most admirable Justin rightly declared…", "And Justin well said…": the quoting writer's voice.
  - Caius's fragments carry "(Preserved in Eusebius' Eccles. Hist., ii. 25.)".
  - Dionysius, "Extant Fragments" (79 passages): 17 open with Eusebius's connecting narrative.
- **What a user sees:** Eusebius's or Irenaeus's sentences as Papias's or Justin's.
- **Status:** new. D5 creates `passage_author` only for Catena quotations and combined pages. 1.8a's bracket review covers editor and translation spans, not a third author's framing.
- **Owner:** 3.2 plus 1.8a. Mark framing spans with `passage_author`, or a work note "Fragments preserved in Eusebius, Church History", and strip ANF's provenance lines.
- **Check:** `attribution.fragment_framing`. In documents whose title contains "Fragment", flag passages whose first sentence names the author in the third person ("X says", "X rightly declared", "Preserved in").

### A-010. Editorial matter in papal documents not on any list

- **Severity:** medium
- **Collections and counts:** apostolic-exhortations. `haerent-animo/1` (1,067 characters), `menti-nostrae/preamble`, Africae Munus `africae-munus/1`, `/1-2`, `/1-3`, `/2`, `/2-5` (table of contents). Live and build.
- **Evidence:**
  - Haerent Animo §1 opens "This Exhortation, which the Holy Father addressed to the catholic clergy…": an editor's introduction under Pius X's name and "§1".
  - Menti Nostrae's Preamble begins with "Translation by the N.C.W.C. News Service … final translation editing by the Very Rev. John P. McCormick".
  - Africae Munus §1 is its table of contents ("Living in accordance with Christ's justice [24-25] 2. Creating a just order…"); two of these passages share one identical vector (A-019).
  - Haerent Animo is also one of the documents whose § numbers the adapter invents (0.1a).
- **What a user sees:** an editor's paragraph presented as the pope's first paragraph; a contents list as a result card.
- **Status:** new. Rule G applies; 1.3a and 1.8a do not list them.
- **Owner:** 1.3a. Add papal editorial patterns, and removal entries `rule-g-editorial`.
- **Check:** `health.R11_papal_editorial`: "Holy Father addressed", "Translation by", "translation editing", or a run of "[N-M]" range markers, in a papal passage.

### A-011. ANF "Argument" summaries are unowned; removing them deletes the only speaker signal in the Octavius

- **Severity:** medium
- **Collections and counts:** church-fathers. 43 passages open with "Chapter N.—Argument…" (Octavius 40; 14,226 characters). 1,669 more passages in 16 documents open with "Chapter N.—Title" heading lines: City of God 661, Doctrinal Treatises 380, Refutation 239, On Christian Doctrine 150, Banquet 73. Live and build.
- **Evidence:**
  - The decision log's rule G names "translators' 'Argument' summaries, in every edition".
  - 1.8a's out-of-scope says chapter heading lines with "the editor's summary title" are "editorial summaries in ANF, but removing them touches every passage… I'd raise that as its own decision after P1". No item owns that decision.
  - The Octavius's Caecilius (the pagan side of the dialogue) speaks in chapters V to XIII. The editor's line "Argument: Cæcilius begins his argument…" is today the only text that says the speaker is a pagan. Once rule G removes it, nothing tells the models.
  - City of God's chapter titles render the Latin capitula of the manuscript tradition, not Dods's own summaries, so a blanket rule would be wrong.
- **What a user sees:** today, editor prose atop each Octavius chapter. After rule G, the pagan attack on Christianity under "Minucius Felix".
- **Status:** known, underestimated (1.8a out of scope; plan rule G).
- **Owner:** new item after 1.8a. Per-work decision on chapter-title lines. Before stripping the Octavius "Argument" lines, record the speaker as a role or passage note for chapters V to XIII.
- **Check:** `editorial.argument_lines`: zero passages opening "—Argument" once the item lands; plus `role.dialogue_speaker` for listed dialogue works.

### A-012. Inline footnote callers left in papal texts and Lumen Gentium's starred notes

- **Severity:** medium
- **Collections and counts:**
  - "(N)" after a word or quote: apostolic-exhortations 530, papal-documents 120, encyclicals 18 build passages (516, 117, 18 live).
  - Glued digit callers ("Siena,6", "points out.9"): Mulieris Dignitatem, Quanta Cura (1864), Dilexit Nos, about 25.
  - Vatican II: 432 "(N)" and 102 "(N*)" in Lumen Gentium.
- **Evidence:** `signum-magnum/1` "…imitation of her virtues."(35)"; `salvifici-doloris/6` "the danger of death(5), the death of one's own children(6)"; `lumen-gentium/66` "…(21*)". The keyword index stores each as a number token (A-007).
- **What a user sees:** stray numbers in the text and the explanation input.
- **Status:** known, underestimated. 1.1 strips "(9)" and "[9]" only, not "(9*)". 1.3a cuts endnotes but says nothing about callers.
- **Owner:** 1.3a and 1.1.
- **Check:** `health.R12_note_caller`: `[A-Za-z.,;"”’)]\(\d{1,3}\*?\)` or `[a-z][.,;]\d{1,3}\s`, outside the Bible and canon law.

### A-013. Canon-law defects 1.5a's patterns miss

- **Severity:** medium
- **Collections and counts:** canon-law. Live and build.
  - c. 297 ends with a page footer (a rule line, then "Apostolic Letter issued 'Motu Proprio' … modifying Canons 295-296 … 8 August 2023 [Italian]"). It is not among 1.5a's 11 footer canons, and 1.5a's cut patterns ("(n: indicates", "For Can.", "[Earlier version]", "[Original version") do not match it.
  - c. 230 carries an inline "[Cf. Letter of the Holy Father … (10 January 2021)]".
  - 7 canons carry the amendment marker mid-text (`n§2`, `n§3`): 111, 237, 535, 604, 688, 699, 775. 1.5a's acceptance check tests only a leading "n".
  - 112 canons have hard line breaks inside sentences ("In the\nautonomous monasteries").
- **What a user sees:** a motu proprio title as the end of canon 297; "n§3" and broken lines in the reader.
- **Status:** known, underestimated (1.5a).
- **Owner:** 1.5a.
- **Check:** extend 1.5a's acceptance: zero `n§` anywhere, zero "Apostolic Letter issued" or "[Cf." in content, zero `[a-z,]\n[a-z(]`.

### A-014. The editor's source lines in fragment collections

- **Severity:** low
- **Collections and counts:** church-fathers, 24 standalone paragraphs in 11 documents (Hippolytus Extant Works 8, Refutation 3, Peter's fragments 3, …). Build.
- **Evidence:**
  - `the-extant-works-and-fragments-of-hippolytus/on-luke`: "On Luke. Mai, Script. vet. collectio nova, vol. ix. p. 645, Rome, 1837."
  - Peter `fragment-vii`: "Ex Leontio et Joanne Rer. Sacr., lib. ii. Apud Mai…".
  - 1.8a's `strip_editorial_lines` drops bracketed credits and dates, not these unbracketed lines.
- **Status:** known, underestimated (1.8a).
- **Owner:** 1.8a.
- **Check:** `editorial.provenance_lines`, using the regex in `fathers_edit.py`.

### A-015. About page claims beyond 2.4c's fix

- **Severity:** low
- **Collections and counts:** product copy, `apps/web/src/components/about/AboutPage.tsx`.
- **Evidence:**
  - After 2.4c: the Fathers text still says "roughly the 1st through 8th centuries" (the corpus ends with Augustine and the Apostolic Constitutions, about 430).
  - The medieval text keeps "scholastic theologians, mystics, and canonists" (no canonist is in the corpus).
  - The exhortations text calls them all "post-synodal" (Haerent Animo, Menti Nostrae, Evangelica Testificatio, Gaudete in Domino, Marialis Cultus, Signum Magnum, Redemptionis Donum, Redemptoris Custos, Gaudete et Exsultate, Laudate Deum, C'est la confiance and Dilexi te are not).
  - The papal-documents text cites "defining dogmas (such as the Immaculate Conception)" and "reforming Church structures", but Ineffabilis Deus is filed under encyclicals and nothing in the collection reforms structures.
- **Status:** known, underestimated (2.4c).
- **Owner:** 2.4c.
- **Check:** none automated; the About-page checklist on rule-change PRs.

### A-016. 1.10a's period stripping makes Papias's and Methodius's "Fragments" one dedup source

- **Severity:** low
- **Collections and counts:** church-fathers. After 1.10a, two documents share the title "Fragments" (Papias 11 passages; Methodius "Fragments." 9). Today only the two "Epistle to the Philippians" share a title.
- **Evidence:** `source_key` in `services/api/app/rag/dedup.py` keys on `document_title`, deliberately, per its docstring. The bucket-merge script is in section 5.
- **Status:** new (a 1.10a side effect).
- **Owner:** 1.10a or 3.2. Give generic titles their author ("Fragments of Methodius"), or key dedup on document ID plus translation.
- **Check:** `registry.unique_title_per_collection` after normalization.

### A-017. Very large single reader chapters outside the councils

- **Severity:** low
- **Collections and counts:** `novo-millennio-ineunte/sec-0` (58 passages, 98,891 characters), `redemptoris-mater/sec-2` (37, 69,830), Stromata Book III introduction (33, 105,766, mostly the Latin passages), Hermas Similitude Nine (20, 60,542). Councils (Basel-Florence 318,534 characters in one chapter, Lateran V, Trent, Vienne) are rebuilt by 1.2b and 1.2e. Build.
- **Status:** new for the papal ones.
- **Owner:** 1.3a (with A-003's heading chapters).
- **Check:** `structure.chapter_size`: report chapters over 50,000 characters.

### A-018. Lowercase-start fragments and empty-looking sed contra parts in the Summa

- **Severity:** low
- **Collections and counts:** summa. 186 build passages start lowercase (151 "On the contrary", 32 "I answer that"), because the marker moved into `unit_label` mid-clause ("stands the authority of Scripture.", "suffices the authority of Scripture."). 217 live passages are under 12 words.
- **Evidence:** no saved retrieval points at a passage under 12 words (0 of 217), so the reranker already filters them. The cost is cosmetic on cards and in the reader.
- **Status:** known (1.7 rebuilds parts).
- **Owner:** 1.7. Keep "On the contrary," in the content or capitalise.
- **Check:** `health.R13_lower_start` per collection, report only.

### A-019. Twelve points share a byte-identical vector with a different passage

- **Severity:** low
- **Collections and counts:** 6 pairs, live index: Syllabus §75/§76; Africae Munus `1`/`1-2` and `1-3`/`2`; In Dominico Agro `1`/`2`; canons 892/893; canons 1582/1583.
- **Evidence:** identical float arrays (`exact_dup_vectors.json`). Neighbour-window inputs differ, so at least one vector of each pair was not built from its own text.
- **Status:** new. Fixed by any full re-embed (4.1b).
- **Owner:** 4.1b.
- **Check:** `index.duplicate_vectors`: no two points with identical vectors unless their embedding inputs are identical.

### A-020. Archaic verb forms are not stemmed by the English full-text configuration

- **Severity:** low
- **Collections and counts:** church-fathers 1,869 passages with "-eth" forms and 3,875 with "thee/thou/hath/saith"; summa 916 and 1,780; medieval 44 and 94.
- **Evidence:** `to_tsvector('english','He loveth thee and saith…')` keeps `loveth` and `saith` unstemmed. 27 Fathers passages contain "loveth" but do not match the query "love".
- **Status:** new.
- **Owner:** RF. A thesaurus or synonym dictionary for KJV-era forms.
- **Check:** none needed beyond an eval question.

### A-021. Hyphenation and spaced-hyphen remnants

- **Severity:** low
- **Collections and counts:** about 155 build passages: encyclicals 97, exhortations 28, councils 17, papal 5, Fathers 4, Summa 2, medieval 1, canon law 1.
- **Evidence:** "constitu- tions" (Constance, replaced), "be- seech" (Annus Qui Hunc), "pre- eminent" and "anti- religious" (Catechesi Tradendae), "quasi- domicile" (c. 100). Some are lost em dashes ("in her name- must").
- **Status:** known for Annus Qui Hunc only (1.3a out of scope).
- **Owner:** 1.10a.
- **Check:** `health.R14_hyphen_space`, report only, with an allowlist.

### A-022. Roman numerals mis-cased in labels and references

- **Severity:** low
- **Collections and counts:** church-fathers, 56 passages ("Ii.", "Iii.", "Vi." in Papias and other fragment labels and their references). Build.
- **Status:** new (title-casing).
- **Owner:** 1.9 (the label helpers).
- **Check:** `labels.roman_case`: no `\b[IVXLC][ivxlc]+\b` in labels.

### A-023. Repo docs describe Qdrant collections that do not exist

- **Severity:** low
- **Evidence:** CLAUDE.md §4 says Qdrant owns "the V5 `facets` and `questions` collections". Production has only `chunks`: no alias, one payload index (`collection`). `stages/embed.py` deletes from `facets` and `questions` on every run and would fail against this cluster. Nothing in the API reads them (`rerank_docs.py:44` says "the facets collection … does not exist yet").
- **Status:** new.
- **Owner:** docs, plus 2.2w (which already retires other writers).
- **Check:** `index.expected_collections`, a startup or report check listing collections and aliases.

### A-024. Summa replies numbered for an objection the article lacks (source edition)

- **Severity:** low
- **Collections and counts:** summa. 39 build keys (22 live) have a reply numbered for an objection absent from the article. Spot checks (FP_Q13_A10, FP_Q24_A1, FP_Q89_A3) show the source itself has these marker gaps.
- **Status:** known (the `stitch.py` docstring counts 26). Listed only because the build count is higher than the docstring says. 1.7's acceptance check matches objection counts to source markers, so these remain and stitching attaches nothing to them, which is the safe outcome.
- **Owner:** none needed, beyond 1.7 updating the docstring count.
- **Check:** existing.

## 3. Coverage map

| Area | What I checked | Result |
|---|---|---|
| Index against reader store | Every point against every live passage: IDs, `content`, `reference`, `anchor`, `chapter_key`, `chapter_label`, `unit_label`, `document_id`, `document_title`, `author`, `collection`; payload key sets and types | 0 orphans, 0 missing; only the 21 known blank Summa rows differ ("Objection N" in the payload). 1,193 points lack a `unit_label` key (all NULL live; harmless). |
| Index configuration | Collections, aliases, vector config, quantization, HNSW, payload indexes, counts | One collection `chunks`, cosine, 1,536 dimensions, no alias, no quantization; payload index only on `collection`; 54,604 indexed vectors against 54,568 points (36 soft-deleted, not yet vacuumed). No `facets`/`questions` (A-023). |
| Vectors built from other text | Adjacent-passage cosine per collection; lowest-coherence passages; lexical-neighbour against vector-neighbour agreement per document (TF-IDF); Gaudete in Domino specifically | Gaudete in Domino and the other August cases are re-embedded and coherent. No mis-embedded vector found except A-019. The low-coherence outliers I read were genuine topic shifts. |
| Near-duplicate vectors | All pairs above 0.97 cosine | 142 pairs; 139 with different text, mostly adjacent canons (A-004) and greeting formulas; 6 identical (A-019). |
| Identical text, distant vectors | 19 groups of identical text of 40+ characters | Lowest cosine 0.51, explained by different neighbours and prefixes. Not a defect. |
| Bible | Verse markers (order, gaps, duplicates, malformed, glued), reference ranges, split pieces, Esther verses, titles, translation | Markers sound. The three marker gaps (Esther 4:6, 9:5, 9:30) are absent from WEB-C itself. Known items only (missing verses, Song of Solomon, deuterocanonical chunking, shared piece references). |
| Catechism | Source-node coverage by word shingles, cut sentences, references, labels | A-001. Others known (2267, lowercase starts, buckets, "(part)"). |
| Canon law | Footers, markers, line breaks, chapter keys, contiguity, 2026 rescript | A-006, A-013. The c. 699 rescript is known (R2). |
| Councils | Footnote cards, Tanner editorial braces and credits, chapter sizes, condemned articles, duplicate decrees | Tanner material (`{…}` notes in Lateran I, III and V, "Introduction and translation taken from … Tanner", editor headings in Constantinople IV and Nicaea II) is replaced or retired by 1.2c, 1.2e and D9. Vatican II callers A-012. Constance A-002. Trent A-005. |
| Encyclicals, exhortations, papal documents | First passage of every document, trailing and leading headings, buckets, callers, endnotes, brackets, editorial lines, condemned lists | A-002, A-003, A-005, A-010, A-012, A-017. Endnote walls, debris cards, invented § numbers, list text and genres are known (1.3a, 1.3b). Ubi Lutetiam is known (3.3). |
| Church Fathers | Editorial labels, Argument lines, provenance lines, fragments, martyrdoms, container authors, Greek and Latin, dialogues, trailing credits | A-008, A-009, A-011, A-014, A-022. Container authors, Elucidations, notes, recensions, Peter's commentary, Asterius, Latin, removals and Pseudo- labels are known. Greek characters appear in 1,955 passages, nearly all inside translator notes that 1.10b strips. |
| Medieval | Labels, dates, editorial divs, verse | Known only (1.9). Anselm's chapter summaries are his own capitula; not editorial. |
| Summa | Structure per article (runs, determinations, duplicate and missing objection numbers, order), short parts, lowercase starts, `[*…]` notes, Greek glosses | `[*…]` translator notes are already stripped by `normalize/summa.py`. A-018, A-024. Two-determination keys (3) and others are known. |
| Metadata | Titles, authors, years, translations for all 421 documents; title collisions | Known gaps (Fathers years, translations, council authors, trailing periods, container authors, Hermas, Archelaus, Mathetes). New: A-008, A-016. Spot-checked about 15 papal years against their dates: all correct. Council years mix first and last year (Vienne 1311, Constance 1418): cosmetic. |
| References against content | Bible ranges against markers (non-piece passages: 0 mismatches); canon headings; Summa (1.7) | Clean apart from the known shared piece references. |
| Chapter labels and keys | Debris and bucket labels per collection, keys with several labels (none), labels shared by several keys, contiguity | A-003, A-006; duplicate labels in the Augustine treatises and Cur Deus Homo are known (1.8b, 1.9). |
| `chunk_count` and outline | `documents.chunk_count` against live passage counts | 0 drift; no NULL counts. |
| Anchors | URL-unsafe characters; collisions | None unsafe. Duplicate anchors are 0 per the 0.1b H4 rule. |
| Text quality | HTML entities and tags, mojibake, control and zero-width characters, soft hyphens, page markers, hyphenation, glued note numbers, brackets, stars and daggers, site boilerplate, double spaces | 1 malformed entity (Syllabus "&quuot;"); 43 Fathers passages with soft hyphens (Origen and Augustine's On the Trinity; Origen is removed). The rest are in the findings. No tags, no mojibake. |
| Length and meaning | Length distribution per collection; short-passage retrieval rates; mid-sentence ends and starts | Short passages are almost never retrieved (0 to 0.3%). Mid-sentence cuts are only at split pieces, except A-001. |
| Duplicates across documents | 8-word shingle containment of 50% or more between documents (build) | 145 pairs, all genuine quotation or parallels (Kings and Chronicles; papal documents quoting each other; CCC quoting SC 11 pairs). Low harm: they sit in different documents or collections. |
| Duplicates within documents | 6-word shingle containment of 80% or more | 73 pairs: Summa repeated citations (62, genuine), On Christian Doctrine "Contents" (known 1.8b), Numbers 16 (known), Vatican II note cards (known 1.1). |
| Full-text behaviour | Local Postgres with the 0004 generated column on the snapshot; tokenization tests; reference queries; archaic forms | A-007, A-020. |
| Saved user data | `references.json` against the kinds above; reading-progress chapter keys against the build | 1,925 passages with saved rows. Rule A to C whole-document targets including the Refutation: 48 passages, 65 rows. Condemned propositions: 5 passages, 8 rows. Note cards 4 passages, 5 rows; editorial labels 2 passages, 4 rows; live-not-build 12 passages, 23 rows. All 29 reading-progress rows resolve in the build; one is on Boethius's "editorial-note" chapter, which 1.9 retires, and 4.1a already repoints retired chapters. |
| Eval data | UUIDs in `docs/eval/*.jsonl` against live and build | The files hold run artifacts, not gold IDs. In `eval80-round3.attempts.jsonl`, 2 IDs are not live and 3 are live but not in the build. |
| Pipeline assumptions | Stitching after 1.7 (references now contain "obj. N": `display_role` still shows the label); dedup by chapter after 1.6 (about 96 Catechism chapters); `passage_role`; HyDE book genres (all named books exist) | No break found beyond A-004 and A-016. |
| Not checked | Production Postgres beyond the snapshot; any paid call; the 1.10b note strip's effect on Greek, simulated; every one of the 1,669 chapter-title lines by work; the Lumen Gentium "(N*)" notes' meaning | See Next. |

## 4. Questions for Carter

1. **Should condemned propositions be labelled as condemned, or kept out of search?**
   - Applies to Exsurge Domine §1 to §41, the Syllabus §1 to §80, and Constance's condemned articles.
   - (a) Label each as "Condemned proposition N" and teach `passage_role` and the explanation prompt what that means. They stay findable, which is useful for "what did Leo X condemn?".
   - (b) Keep them in the reader with a note and out of search. That is safer, but the condemnation is then never found by its content.
   - Recommendation: (a), with the role on the card. A card that says "condemned" is what a well-read reader expects, and the Summa already works this way.

2. **Should the dedup threshold change before the republish embeds everything?**
   - (a) Keep 0.9: about 36% of nearby canon pairs and 21% of nearby Summa parts stay at risk of being dropped.
   - (b) Compare vectors of the clean passage text, without neighbours, for dedup (this needs a second vector or a stored hash).
   - (c) Raise the threshold to about 0.97 for chapter-keyed collections.
   - (d) Reduce the canon-law overlap from 300 characters.
   - Recommendation: (c) now, evaluated in 4.2, because it needs no new embeddings. Then consider (b).

3. **Should the keyword index drop verse markers and include references?**
   - (a) No change (2.2c as written).
   - (b) Change the generated column to strip `{{v:N}}` and add the reference with a lower weight. That rewrites the table once, so it goes in the 4.0 compaction window.
   - Recommendation: (b), with the reference sentinels from A-007 as acceptance checks.

4. **How should fragment collections credit the quoting author?**
   - (a) `passage_author` on the framing spans ("Eusebius, quoting Papias").
   - (b) A work note only ("preserved in Eusebius, Church History").
   - Recommendation: (b) for Phase 4, (a) later, because (a) needs span-level splitting.

5. **Who should the Martyrdom of Polycarp and the Martyrdom of Justin be credited to?**
   - Recommendation: "Church of Smyrna" with certainty "genuine" and a note; "Anonymous (Acts of Justin)". Both follow rule H.

6. **Should the Catechism fix (A-001) wait for 1.6, or go first as its own small PR?**
   - Recommendation: its own PR before 1.6. It changes text under existing anchors, so IDs stay (D1), and 1.6's reference rebuild then works on complete text.

## 5. Reproduction

All scripts are in `datapipeline/releases/local/review-opus/` (gitignored). Run from `datapipeline/` with the placeholder variables from the brief. The Qdrant scripts read only `QDRANT_URL` and `QDRANT_API_KEY` from `datapipeline/.env` and call only read methods.

| Script | What it does | Time |
|---|---|---|
| `build.py` | Builds every adapter in `publication.SOURCE_ADAPTERS`, loads the snapshot, writes `corpus.pkl` | 16 s |
| existing reports | `checks.report`, `checks.health` (build and snapshot), `release.report`, outputs in `checks/`, `health/`, `release/` | 67 s, 25 s + 11 s, 98 s |
| `qd.py`, `qd_info.py` | Read-only Qdrant client; collections, aliases, config, payload indexes | 3 s |
| `qd_dump.py` | Scrolls all points with payload and vector to `qvecs.npy`, `qpayloads.pkl` | 233 s |
| `qcmp.py` | Point against passage comparison (W1) | 5 s |
| `vgeo.py` | Adjacent cosine, near-duplicate pairs, identical-text pairs | about 2 min |
| inline (exact duplicates) | Byte-identical vectors, writes `exact_dup_vectors.json` | 10 s |
| `lexvec.py` | Lexical against vector neighbour agreement per collection | about 8 min |
| inline (dedup collision) | Share of nearby pairs above 0.9 per collection and Summa role pairs | 20 s |
| `textscan.py` | Text-quality patterns live and build, writes `textscan.pkl` | about 2.5 min |
| `shape.py` | Length, fragment, start and end statistics | 5 s |
| `trailhead.py` | Glued trailing headings (A-003) | 5 s |
| `ccc_loss.py`, `ccc_loss2.py` | Catechism source-node coverage and dropped-line classes (A-001) | 10 s each |
| `bible.py` | Verse-marker checks | 3 s |
| `reader.py` | Chapter contiguity, labels, huge chapters, anchors, `chunk_count` | 5 s |
| `dups.py` | Cross-document duplicates (build), writes `dups_build.json` | about 1 min |
| `summa_short.py` | Short Summa passages | 3 s |
| `fathers_edit.py` | Fathers provenance lines (A-014) | 3 s |
| `userrows.py` | Saved rows by passage kind | 3 s |
| full-text block | `initdb` and `pg_ctl` in the scratchpad, snapshot loaded with the 0004 generated column, tokenization and query tests (A-007, A-020) | about 1 min |

## Next

Not yet checked, in priority order:

- Simulate 1.10b's note strip and re-run the Greek and Latin counts on the result.
- Classify the 1,669 "Chapter N.—Title" lines by work as authorial, ancient capitula or editorial.
- Check the meaning of Lumen Gentium's "(N*)" callers against vatican.va.
- Read every Dionysius "Extant Fragments" passage to size the Eusebius framing exactly.
- Test vector retrieval of reference-style queries. This needs embeddings, about $0.001 for 20 queries; not run.
