# P1a work specs: shared hygiene, councils, papal, Bible, canon law

**Before implementing any item in this file, follow `README.md` in this folder. It says to ask Carter the item's open questions first, record the answers, and update other specs only in the ways it allows.**

Written 29 September 2026 against `body-of-christ` master at `5475c49`, the vendored sources on Carter's Mac, and read-only queries on Supabase project `hvmgffvimqgiejmxwhwq`. The plan in `docs/2026-09-28-corpus-cleanup-plan.md` is the source of truth. Nothing here reopens its decision log.

## Overview

1. Every item in this file is a datapipeline change. None of them writes to production, because the publish lock (0.4) merges first and the republish waits for P4.
2. The worst defects are text that never reaches the corpus. Vatican II keeps 443,397 of 921,233 body characters (48%). Trent keeps 206,307 of about 548,711. Annus Qui Hunc keeps 2,277 of 64,743.
3. The next worst is text that should not be there. 32,211 translator notes, about 1.97 million characters, sit inline in Fathers and medieval passages. Endnotes are glued to the last paragraph of at least 18 papal documents.
4. Canon law loses 5 canons, keeps superseded text for 5, and leaks page footers into 11. The live count of 1,747 canons looks plausible but is 5 short of 1,752.
5. The Bible drops 244 verses in the current build (245 live), including all of Susanna, Bel and the Dragon, and most of the Song of the Three.
6. The council replacement (Percival, Schroeder, Schaff, Waterworth) is the largest item. Schroeder is mostly scan-only, so this file now includes the OCR clean-up tool and its quality gate (1.2f, D9), which councils 8 to 18 need. A council whose public-domain text is not ready at P4 has its Tanner text retired with a "translation in preparation" tombstone.
7. ID effects are mostly anchor churn inside frozen documents, and anchor churn alone no longer changes passage IDs, because 2.1 freezes them (D1). Where a fix changes which unit a passage is (Joel and Malachi renumbering, councils rebuilt by session), the new units get new anchors and new IDs and each old ID a redirect. The Song of Songs rename keeps its anchors.
8. Everything an item removes is recorded by anchor in the removal registry that 2.1 owns (D4), in the same PR.
9. Research items R2 (canons) and R3 (Esther) are specified in the P0 file, `P0-checks-identity-research.md`. They block 1.5b and 1.4a. R6 (edition checks) blocks 1.2c and 1.2d.
10. Recommended order, matching the plan's phase table: 1.10a, 1.10b, 1.10c, 1.1, 1.3a, 1.3b, 1.5a, 1.5b (after R2), 1.4a (after R3), 1.4b, 1.4c, 1.2a, 1.2b, 1.2c and 1.2d (after R6), 1.2f, 1.2e.
11. Start with 1.10 and 1.1. They are small, they touch every collection or the most-cited one, and they unblock the Nostra Aetate 4 fix that motivated this cleanup.

## Common ground for every item

These apply to every PR below and are not repeated in each item.

- Measurement environment: `cd datapipeline` with `DATABASE_URL=x OPENAI_API_KEY=x QDRANT_URL=http://x QDRANT_API_KEY=x` exported, then import the adapter's `build_documents`. The numbers in this file came from that setup on 29 Sep.
- Tests that need vendored files use the existing pattern `@pytest.mark.skipif(not _vendored, ...)` (see `tests/test_councils.py:12-13`). Synthetic HTML or USFM fixtures cover the same behaviour so GitHub Actions (0.0) runs something for every fix.
- Every PR description carries the locally run source-check section from the 0.0 template, the 0.1c release report for the touched collections, and the 0.1a coverage numbers before and after.
- D1 to D11 are the "Cross-cutting design decisions" in the plan. Where this file and those decisions disagree, the decisions win.
- Anchors: follow the structural anchor rules of 2.1. Where this file proposes an anchor shape, 2.1 wins if they disagree.
- One passage ID, one unit of text (D1). Passage IDs come from 2.1's frozen passage registry through `resolve_passage_id`, not from the anchor. Fixing a unit's text keeps its ID. Changing a unit's anchor string without changing the unit (a relabel, a corrected section number) means editing its registry row's `anchor`; the ID stays and no redirect is needed. Only genuinely new units (restored verses, recovered prose) get new IDs. If a fix changes which unit a passage is (passages regrouped at new chapter boundaries, a council rebuilt by session), the new units get new anchors and new IDs, and the PR adds rows to 2.1's `registry/redirects.json` from each old ID, with a kind from the remap vocabulary (`moved`, `split`, `merged`, `renumbered`). A live anchor string never comes to name a different unit, and a retired one is never emitted again. The 0.1c report fails the PR otherwise.
- Where the same numbered unit gets a new translation or new legal text (a Percival canon replacing a Tanner canon, an amended canon), the anchor stays and the adapter sets passage metadata `text_replaced` with the reason, so 0.1c's stability check lists it instead of failing.
- Split pieces keep today's convention (`base/p1`, `base/p2`) unless 2.1 changes it. Where a fix makes a short unit long enough to split, the registry row for `base` changes its anchor to `base/p1` and keeps the ID; later pieces are new. Where a unit now needs fewer pieces, each piece anchor that disappears gets a `merged` redirect to the piece holding its first 200 characters.
- Removals (D4). Every passage an item drops (notes split off, footnote cards, heading debris, duplicates, Tanner text with no successor) gets an entry in 2.1's `registry/removals.json` in the same PR, by live anchor, with reason and tombstone text. The 0.1c report fails on a removal the registry doesn't explain. Nothing is retired in live data until 4.1b (D2, D7).
- Document IDs come from the frozen registry (2.1). Where a fix would change the computed ID, the registry keeps the old one and this file says so.
- Passage fields (D11). `searchable`, `language` and `passage_author` are fields on the `Passage` model, added in 2.1, never keys in `metadata`. An adapter may set them; a value in 2.1's passage registry overrides the adapter's (3.3). Genres come from 2.1's genre module.
- Superseded text (rule F, D11). Where an item keeps an older text of a unit as history (an amended canon, CCC 2267), the older text is its own passage, never metadata: anchor `<anchor>/history-<year>`, `searchable = False`, and `superseded_by_anchor` naming the current passage. It is a new unit, not a removal, so it needs no removal-registry entry. The reader shows it as "earlier text" (2.4b).
- Every P1 PR depends on 0.4 (publish lock), 0.1a (coverage and sequence tests), 0.1c (release report) and 2.1 (registry). The "Depends on" lines below list only extra dependencies.

---

### 1.10a. Space joined sentences and trim trailing periods from authors

- **Type:** PR
- **Depends on:** none beyond the common set
- **Goal:** Words that the source runs together ("consecration.The Synod") get their space back, so keyword search finds both words. Author labels lose stray trailing periods ("Methodius." becomes "Methodius").
- **Current state:**
  - The joins are in the source text itself, not in our markup handling. Vita Consecrata on vatican.va has "by a special consecration.The Synod was a tangible sign" in one text node.
  - Live counts of `[a-z][.?!][A-Z][a-z]` per collection: apostolic exhortations 181 joins in 83 passages, encyclicals 11 in 9, medieval 16 in 14, church fathers 12 in 11, canon law 11 in 16 passages (mostly "parentibus.§2" style joins before a section sign), councils 2, summa 1. The current build gives Vita Consecrata 181 joins in 88 passages (the plan's 188 in 86 is the live count).
  - `normalize/text.py:33-38` `clean_text` is the one cleaner every adapter calls, so it is the right place.
  - Authors: 54 documents, 3,862 passages, have an author ending in a period, and 53 titles end in one. The labels are read from ANF `div1` and `div2` titles (`church_fathers.py:70-74`), and every ThML adapter passes them through `thml_doc.make_doc` (`ingest/thml_doc.py:35-91`) unchanged, so `make_doc` is the one place to fix them. This item owns trailing periods for every collection (D10); 1.8c does not repeat the fix. Container names such as "Tertullian: Part Fourth.", "Anatolius and Minor Writers." and "Appendix." are wrong authors, not just bad punctuation. After this item they read without the period, and 1.8c replaces them.
- **Changes:**
  - Add `repair_sentence_joins(text)` to `normalize/text.py` and call it first inside `clean_text`. Rule: insert one space in `([a-z][.?!;:][”"’)]?)([A-Z][a-z])` and in `([.;:])(§)`. Skip any whitespace-delimited token containing `://`, `www.` or `@`.
  - Do not touch initials or abbreviations with a capital before the dot ("U.S.", "S.C.P.F."). The rule already requires a lowercase letter before the punctuation.
  - In `make_doc`, set `author = author.rstrip(" .")` and the same for `title`. `identity.slugify` drops punctuation, so `document_id(collection, author, title)` does not change. Test that too.
  - Fixtures: `"consecration.The Synod"`, `"said.”The"`, `"parentibus.§2. An infant"`, `"see www.vatican.va"`, `"U.S.Bishops"` (unchanged), `"St.Augustine"` (becomes "St. Augustine", accepted).
- **Acceptance checks:**
  - `test_repair_sentence_joins_inserts_space`, `test_repair_sentence_joins_ignores_urls_and_initials`, `test_clean_text_only_adds_whitespace`: for every fixture, `re.sub(r"\s", "", out) == re.sub(r"\s", "", inp)`.
  - Vendored check across all ten collections: after the fix, zero matches of the join pattern outside URLs. For every passage, content with whitespace removed is identical before and after. The PR prints the per-collection before and after counts.
  - `test_make_doc_strips_trailing_period_keeps_id`: author "Methodius." yields "Methodius" and the same `document_id` as before.
  - Vendored check: zero authors and zero titles ending in a period across church fathers and medieval (54 authors and 53 titles before). The frozen registry IDs (2.1) are unchanged.
- **Production safety:** Content changes in about 150 passages across collections, all `same` in the 0.1c report and far above its stability threshold. No anchor or ID changes, because splitting happens on the same text plus a few spaces and the cap is 3,500 characters. The release report must still confirm zero anchor churn.
- **Needs Carter:** nothing.
- **Out of scope:** container authors ("Tertullian: Part Fourth.") and all other Fathers labels, which are 1.8c. Lowercase "the" sentence starts in the Catechism, which is 1.6.

### 1.10b. Strip inline translator notes from ThML text

- **Type:** PR
- **Depends on:** 1.10a
- **Goal:** Fathers and medieval passages read as the author wrote them, without ANF and NPNF footnotes such as "Matt. xxiv. 15" or "Literally, 'bidding farewell to'" in the middle of a sentence.
- **Current state:**
  - Also found by 0.1a's checks (5 Oct 2026): `_direct_p_text` reads only `<p>`, so `<verse>` blocks (poems and quoted hymns as `<l>` lines) are dropped: 828 blocks, about 135,000 characters, in the Fathers, and about 850 characters in medieval. Examples: the Sibyl's and the poets' testimonies in Justin's Hortatory Address (`apostolic fathers.xml` `viii.vi.xv` to `xviii`) and On the Sole Government of God (`viii.vii.ii` to `v`), Theophilus To Autolycus II.36 and 37, Clement's Exhortation ch. VII, and the hymn closing Clement's Instructor. `second-century.xml` is 94.1% covered. Each is a `known_defects.json` entry with `fixed_by` 1.10b, pending Carter's answer in `NEEDS-CARTER.md`.
  - `ingest/common.py:37-50` `_direct_p_text` serializes each `<p>` and `_strip_tags` (`common.py:16-23`) removes tags but keeps their text. ThML keeps footnotes as `<note>` elements inside the paragraph, so every note's text lands inline.
  - Measured across the paragraphs the adapters actually read: 32,211 `<note>` elements, about 1,967,600 characters, in 4,986 chapters. By file: ANF01 4,841 notes, ANF02 3,641, ANF04 4,411, ANF05 5,436, ANF06 4,923, the third and fourth century volume 3,967, NPNF1-02 2,009, NPNF1-03 2,770, Incarnation 71, Consolation 75, Imitation 55, Anselm 12. Confessions and On Loving God have none.
  - Live confirms it: 1,838 Fathers passages contain a Roman-numeral scripture note such as "Matt. xxiv. 15.", and 284 contain "Literally, “". The plan's "at least 584" was a lower bound.
  - Stripping notes in the current build changes 7,415 of 10,232 Fathers and medieval passages. Because passages get shorter, split points move: 724 anchors disappear and 210 new ones appear.
  - `<scripRef>` elements in body text are the author's own citations or quotations and stay.
- **Changes:**
  - In `common.py`, add `_p_text_without_notes(p)`. Copy the element, remove every `note` descendant while keeping its `tail` text, then serialize and strip tags. Use it in `_direct_p_text` and `_extract_p_text`. Summa has no `<note>` elements, so `_chunk_summa` output is unchanged. Assert that in a test.
  - Record the removed notes in passage metadata as `editor_note_count` only. The note text is editor material under rule G and should not be stored for display.
  - Add one `class` entry to 2.1's removal registry: reason `rule-g-editorial`, rule `common._p_text_without_notes`, and the count of `<note>` elements removed. No passage is retired by this item, so no `passage` entries are needed.
  - Piece anchors that disappear because split points moved (`base/pN` with N above the new piece count) get `merged` redirects to the new piece that holds their first 200 characters.
  - Fixture: `<p>He said<note n="1" place="end">Matt. xxiv. 15.</note> this, and<note n="2">Literally, "to."</note> left.</p>` becomes "He said this, and left."
- **Acceptance checks:**
  - `test_direct_p_text_drops_notes_keeps_tail` and `test_extract_p_text_drops_notes` on the fixture.
  - Vendored check: zero passages in church fathers and medieval contain the text of any `<note>` whose text is 20 characters or longer. The check builds the note-text set from the sources, so it cannot pass by accident.
  - Coverage: characters kept equals the old build minus note text, within 1%. The PR reports both numbers.
  - The release report lists the anchor churn (expected about 724 removed and 210 added `/pN` anchors). The PR must say that none of the 50 retrievals and 0 bookmarks the plan found at risk sit on a removed anchor, or list the ones that do.
- **Production safety:** Datapipeline only. Document IDs do not change. Surviving anchors keep their IDs; 0.1c compares all pieces of a unit together, so shorter text under the same anchors passes its stability check. Passage IDs disappear only where a split point moved, and each has a redirect.
- **Needs Carter:** nothing.
- **Out of scope:** whole editorial passages (Elucidations, introductions, Shedd's essay) and bracketed editor comments inside the text, which are 1.8a, 1.8b and 1.9. Note markup in papal and council HTML, which 1.1 and 1.3a handle.

### 1.10c. Give every split passage its own citation

- **Type:** PR
- **Depends on:** 1.10b
- **Goal:** A citation points at exactly the text on the card. Today a long pericope, paragraph or chapter split into 3 cards shows the same citation on all 3.
- **Current state:**
  - Live rows sharing a citation within one document: Bible 495, apostolic exhortations 412, encyclicals 411, papal documents 91, councils 1,282, church fathers 5,941, medieval 240, Catechism 98, and all 26,750 Summa rows.
  - Each adapter copies the same loop: call `split_display_passage` (`common.py:158-202`) and reuse `ref` for every piece. Examples: `bible.py:575-586`, `councils.py:70-81`, `encyclicals.py:185-196`, `thml_doc.py:75-82`.
  - The Bible pieces contain `{{v:N}}` verse markers, so their real verse range is recoverable. ANF and NPNF chapters have no printed paragraph numbers.
- **Changes:**
  - New module `ingest/pieces.py` with `pack_units(units, max_chars)`. A unit is `(label, text)`: a verse, a canon section, a numbered paragraph, or a source `<p>`. It packs whole units into pieces of at most `max_chars`. Only a single unit longer than the cap falls back to `split_display_passage`.
  - `piece_reference(base, first_label, last_label, part, parts)` returns `"Genesis 1:14 to 1:31"` style ranges when labels exist. It returns `base + " (part 2 of 3)"` when they do not. That form is settled (D5) and is the only piece suffix in the corpus; the Catechism (1.6) and the Summa (1.7) use it too. Use a proper range separator in the real string; this file avoids dashes.
  - Apply it in `thml_doc.make_doc` (Fathers and medieval), the three papal adapters, `councils._Builder.add` and the Bible builder. The Bible gets verse units, so a split never cuts inside a verse and each piece cites its own verses.
  - Keep anchors exactly as today: `base`, or `base/pN` for pieces. Only `reference` changes, plus Bible piece boundaries, which now fall between verses.
  - 1.1 to 1.5 rewrite several of these adapters. They must keep calling `pack_units` and `piece_reference`, not a private copy.
  - Summa (1.7) and Catechism (1.6) adopt the helper in their own PRs and depend on this one.
- **Acceptance checks:**
  - `test_pack_units_never_splits_a_unit_under_cap`, `test_pack_units_keeps_every_character`, `test_piece_reference_range_and_part_forms` (asserts the exact string "(part 2 of 3)").
  - Vendored check: zero duplicate `(document_id, reference)` pairs in Bible, papal, Fathers and medieval. Councils may keep duplicates until 1.1 and 1.2 land. The check prints the count per collection.
  - Bible: every piece's reference range equals the first and last verse numbers found in its text.
- **Production safety:** References and some Bible split points change. Document IDs do not. Bible piece anchors (`book/ch/v-2`) can move. A piece anchor that no longer exists gets a `merged` or `split` redirect to the piece holding its first verse.
- **Needs Carter:** nothing. The citation form "(part 2 of 3)" is decided (D5).
- **Out of scope:** Summa objection and reply citations (1.7). Catechism paragraph labels (1.6).

---

### 1.1. Vatican II: keep every paragraph of each section, stop at the notes

- **Type:** PR
- **Depends on:** 1.10c
- **Goal:** Each Vatican II section holds all of its paragraphs. Nostra Aetate 4 goes from 155 characters live to about 3,650, including the passage on Jewish responsibility for the Passion. Footnote cards disappear.
- **Current state:**
  - `ingest/councils.py:149-213` `build_vatican2` keeps only `<p>` elements matching `_NUM` (`councils.py:27`, a leading "N. "). Unnumbered continuation paragraphs fall through `councils.py:193-195` and are dropped. After the notes heading, numbered footnotes ("4. Cf 2 Cor 5:18-19") match `_NUM` and become passages when they are 40 characters or more.
  - Body text before the notes heading: 921,233 characters over 16 documents. The current build keeps 443,397 (48%). Worst cases: Nostra Aetate 2,253 of 9,326 (24%), Gaudium et Spes 74,319 of 196,411 (38%), Gravissimum Educationis 8,894 of 23,644 (38%), Unitatis Redintegratio 16,331 of 41,160 (40%).
  - Notes headings vary: "NOTES", "ENDNOTES", "FOOTNOTES". Ad Gentes uses "ENDNOTES" followed by per-chapter headings and restarted numbering. Optatam Totius has no notes section.
  - Unnumbered text before section 1 exists in 3 documents: Optatam Totius preface (780 characters), Gravissimum Educationis introduction (2,199), Dignitatis Humanae subtitle (207). Gravissimum Educationis numbers some sections as headings ("12. Coordination to be Fostered in Scholastic Matters") with the body below.
  - Source typo: Sacrosanctum Concilium section 87 is printed "81." in the vendored file (paragraph index 167). Today it becomes anchor `sacrosanctum-concilium/81-2`.
  - Lumen Gentium carries the Nota explicativa praevia after section 69, with its own numbers 1 to 4. Today those collide with LG 1 to 4 and get `-2` suffixes.
  - Sacrosanctum Concilium ends with the Council's declaration on revising the calendar, after section 130.
  - Orientalium Ecclesiarum and Unitatis Redintegratio end with the promulgation formula ("Each and all these matters... Given in Rome at St. Peter's, November 21, 1964").
  - All 36 council documents have `author = None` (`councils.py:144`, `:212`).
  - Tests encode the bug: `test_vatican2_numbered_paragraphs_under_chapter` never has a continuation paragraph.
- **Changes:**
  - Rewrite `build_vatican2` as a two-pass walk over `soup.find_all("p")`. Pass 1 finds the cut: the first paragraph matching `^(END|FOOT)?NOTES?$`, case-insensitive. With no such heading, the end of the document. Pass 2 walks paragraphs before the cut.
  - Keep a running section number. A paragraph opens a section only when its number is the expected next one. Any other numbered paragraph is continuation text. This also blocks the LG Nota numbers from resetting the count.
  - Add `_SECTION_NUMBER_FIXES = {("Sacrosanctum Concilium", "81. In order that the divine office"): 87}`, keyed by the paragraph's opening words. Log each applied fix.
  - Unnumbered paragraphs attach to the open section. Paragraphs before section 1, excluding the language bar and the all-caps masthead, become one passage with anchor `<doc>/preface`, labelled "Preface" or "Introduction" to match the source heading.
  - Headings: keep `_CHAPTER` detection. A short unnumbered paragraph with no final punctuation and mostly capitals ("THE URGENT FOSTERING OF PRIESTLY VOCATIONS") is a subheading. Prepend it as the first line of the next section rather than creating a card. A numbered heading ("12. Coordination to be Fostered...", no final punctuation, under 120 characters) opens section 12 with that text as its first line.
  - Named appendices get their own anchor namespace and chapter:
    - Lumen Gentium: from the paragraph "Preliminary Note of Explanation" to the cut. Anchors `lumen-gentium/nota-praevia/1` to `/4`, chapter "Preliminary Note of Explanation", references "Lumen Gentium, Preliminary Note of Explanation, 1". The Nota is part of the Council's acts, announced by the Secretary General, so rule G does not remove it.
    - Sacrosanctum Concilium: the calendar declaration, anchor `sacrosanctum-concilium/appendix`.
    - Promulgation formulas: anchor `<doc>/promulgation`, chapter "Promulgation".
  - Set `author="Second Vatican Council"` on every Vatican II document. The document ID is `document_id("councils", "Second Vatican Council", title)` and does not include author, so it is unchanged.
  - Use `pack_units` with the section's paragraphs as units. 40 sections exceed 3,500 characters, so they split: 12 in Lumen Gentium, 7 in Presbyterorum Ordinis, 6 in Gaudium et Spes, 6 in Ad Gentes, and Nostra Aetate 4 among the rest.
  - Keep the existing footnote-marker strip. Marker forms in these files are "(9)" and "[9]". Add the parenthesised form only after a word or closing quote, so "(Rom. 12:10)" stays.
- **Acceptance checks:**
  - Replace the fixture in `test_vatican2_numbered_paragraphs_under_chapter` with one that has a continuation paragraph and a NOTES section. New tests: `test_vatican2_continuations_join_their_section`, `test_vatican2_stops_at_notes_heading`, `test_vatican2_notes_numbering_restart_is_not_a_section`, `test_vatican2_preface_before_section_one`, `test_vatican2_nota_praevia_has_own_anchors`, `test_vatican2_section_number_fix_applied`.
  - Vendored checks:
    - Every document has sections 1 to N with no gap and no duplicate. The expected N per document: Dei Verbum 26, Lumen Gentium 69, Sacrosanctum Concilium 130, Gaudium et Spes 93, Ad Gentes 42, Presbyterorum Ordinis 22, Apostolicam Actuositatem 33, Optatam Totius 22, Perfectae Caritatis 25, Christus Dominus 44, Unitatis Redintegratio 24, Orientalium Ecclesiarum 30, Inter Mirifica 24, Gravissimum Educationis 12, Nostra Aetate 5, Dignitatis Humanae 15.
    - Characters kept are at least 99% of the body characters before the cut, 921,233 in total, reported per document.
    - Zero passages start with "Cf.", "See " or "Ibid".
    - The Nostra Aetate 4 text contains "what happened in His passion cannot be charged against all the Jews".
  - The prototype run on 29 Sep got 86 sections for Sacrosanctum Concilium before the "81." fix. The test must show 130 after it. Optatam Totius printed 21 in the prototype; confirm the true count of 22 against vatican.va, or correct this expectation in the PR.
- **Production safety:** Datapipeline only. Document IDs unchanged. Anchors `<doc>/<n>` keep their meaning and IDs, so bookmarks on existing sections stay correct and gain text. Churn this PR must record:
  - About 76 footnote anchors (`<doc>/<n>-2`, `<doc>/<n>-3`) disappear. They hold note text. Each gets a removal-registry entry (reason `note-split-off`, tombstone "This card was a footnote to the Council's text, not the text itself").
  - Sections that now split change anchor from `<doc>/<n>` to `<doc>/<n>/p1`. The registry row keeps the section's ID; the later pieces are new.
  - `sacrosanctum-concilium/81-2` already holds section 87's text. Its registry row changes anchor to `sacrosanctum-concilium/87` and keeps its ID.
  - Where today's build emits Nota praevia paragraphs under `lumen-gentium/<n>-2` style anchors, their registry rows move to `lumen-gentium/nota-praevia/<n>` and keep their IDs the same way. Nota paragraphs that were dropped today are new units.
  - Gravissimum Educationis bucket chapters (`bucket-0`) become heading chapters. That is a chapter-key change only, and passage IDs stay. The 0.1c chapter remap carries it to `reading_progress`.
- **Needs Carter:** confirm the Nota explicativa praevia stays as part of Lumen Gentium. Recommended: yes, as its own chapter.
- **Out of scope:** councils 1 to 20 (1.2). Genre and "document type" fields beyond the existing metadata (2.3).

---

### 1.2a. Council translation inventory and gap register

- **Type:** research
- **Depends on:** none
- **Goal:** Before anyone writes an adapter, a table says for each council document which public-domain translation covers it, and which documents have none. The gap register is what the About page and the release report will cite.
- **Current state:**
  - All 19 non-Trent council documents come from papalencyclicals.net, which uses Tanner's *Decrees of the Ecumenical Councils*, including Tanner's editorial introductions. For example, the Nicaea passage at `council-of-nicaea/sec-1/1` begins "This council opened on 19 June", which is Tanner's text, not the Council's.
  - The plan's replacements are Percival (NPNF2 vol. 14, CCEL `npnf214`) for councils 1 to 7, Schroeder 1937 for 8 to 18, Schaff's *Creeds of Christendom* vol. 2 for Vatican I, and Waterworth 1848 for Trent (already the vendored text).
  - Schroeder is titled *Disciplinary Decrees*. Florence's doctrinal decrees (Laetentur caeli, the decrees for the Armenians and the Jacobites) are the plan's known gap. Whether Schroeder includes Constance's session decrees, Vienne's doctrinal constitution or Lateran V's doctrinal bulls is unverified.
  - Schaff's Vatican I section has Dei Filius and Pastor Aeternus in Manning's English. The current Tanner document also has the opening decree and the profession of faith of sessions 1 and 2; those are likely gaps. Unverified.
  - `npnf214` is not vendored. Its structure is known from the CCEL table of contents but was not opened for this spec.
- **Changes:** Produce `docs/research/council-translation-inventory.md` in the plan repo with one row per document in Tanner's table of contents for councils 1 to 20. Columns:
  - council and document
  - Tanner section
  - replacement source and location (CCEL section id, Schroeder page, Fordham URL, Wikisource page)
  - status: covered, partial or gap
  - for partial: what is missing
  - rights note, pointing at the 0.2 rights inventory
  - Also classify each Percival and Schroeder unit as council text or editor material (Percival's Historical Introductions, Excursus, "Notes", Ancient Epitomes; Schroeder's commentary), so 1.2c and 1.2e know what to drop.
- **Acceptance checks:** Every document in the current 19 non-Trent council documents appears. Every "gap" row names what was searched. Carter reviews and closes the issue.
- **Production safety:** No code.
- **Needs Carter:** approve the gap register.
- **Out of scope:** making translations (the plan forbids it). Latin text for gaps (rule E would keep it reader-only).

### 1.2b. Trent: parse the whole Waterworth text

- **Type:** PR
- **Depends on:** 1.10c
- **Goal:** All 25 sessions of Trent are searchable, with decrees, chapters and canons cited by session.
- **Current state:**
  - The vendored file is Waterworth 1848 ("Waterworth translation, 1848 edition." appears in the file). The body text is bare text nodes separated by `<br>` inside the article `<div>`. Headings are `<center>` elements (338 of them, such as "SESSION THE SIXTH", "DECREE ON JUSTIFICATION", "CANON I."). `build_ecumenical` (`councils.py:84-146`) reads only `h1` to `h4` and `p`.
  - Text outside `<p>` and headings: 339,324 of 548,711 characters. The current build keeps 206,307 characters in 188 passages, all under one chapter "Text", 73 of them with `-k` suffix anchors.
  - Canon numbers restart in every session, so today's anchors `council-of-trent/canon/1`, `canon/1-2`, and so on depend on order.
- **Changes:**
  - Add `build_trent(entry, soup)` and route the Trent manifest entry to it. Walk the article element's descendants in document order. Treat `<center>` and `<strong>`-only lines as headings. Split text on runs of 2 or more `<br>` into paragraphs. Keep the existing chrome filter.
  - Structure: session, then document (decree, doctrine, canons, decree on reformation, indiction), then chapter or canon. Anchors: `council-of-trent/session-6/decree-on-justification/chapter-7`, `council-of-trent/session-6/canons-on-justification/canon-9`. Chapter keys per session and document.
  - The bull of indiction and the closing bulls and oath (Benedictus Deus, the Profession of Faith) keep their own anchors under `council-of-trent/bulls/...`.
  - Drop Waterworth's editorial matter if any (preface, "Translator's Introduction"), under rule G.
  - `author="Council of Trent"`.
- **Acceptance checks:**
  - `test_trent_bare_text_between_br_is_kept`, `test_trent_center_headings_become_structure`, `test_trent_canon_anchor_includes_session`, on a synthetic fixture copied from the file's markup shape.
  - Vendored checks: 25 sessions found. Characters kept are at least 97% of the article text minus chrome and minus headings. Session 6 has 16 chapters and 33 canons on justification. Session 7 has 13 canons on the sacraments in general. Session 13 has 8 chapters and 11 canons on the Eucharist.
  - Zero anchors with a `-k` collision suffix.
- **Production safety:** Datapipeline only. Document ID `e33e591b-...` is unchanged, because the title is unchanged and the registry freezes it anyway. This is a council rebuilt by session (D1). The old 188 passages cut the text at arbitrary points under one chapter, so the new session, document and canon units are new units with new IDs, not relabels. The PR commits a redirect row for each old ID to the new passage holding its first 200 characters (`moved`, `split` or `merged`, from the 0.1c evidence). Old passages with no successor get removal-registry entries (for example `rule-g-editorial` for Waterworth's own matter) and are listed in the release report.
- **Needs Carter:** nothing.
- **Out of scope:** the Roman Catechism of Trent (5.5).

### 1.2c. Councils 1 to 7 from Percival (NPNF2 vol. 14)

- **Type:** PR
- **Depends on:** 1.2a, 0.2 (source hash and rights entry for `npnf214`), R6 (edition check for the new source)
- **Source files (decided by Carter, 5 Oct 2026):** Its approved R6 downloads are vendored in `datapipeline/sources/_incoming/`, under the path R6's "Vendored as" column gives (`_incoming/<path>`), where no adapter reads them. This PR moves each file it ingests, unchanged, to `sources/<path>` and runs `python3 scripts/source_lock.py --write`; the hash stays the same and the lock keeps the file's download date and URL. Its `rights_inventory.json` row already names `<path>` as `source_path`. Files: `councils/npnf214.xml`.
- **Goal:** Nicaea through Nicaea II come from a public-domain translation with clear provenance, and carry the councils' own texts: creeds, definitions, canons, anathemas and synodal letters. Nicaea stops being 4 passages.
- **Current state:**
  - Current build from papalencyclicals.net (Tanner): Nicaea 4 passages and 5,993 characters. Constantinople I 16 and 22,451. Ephesus 32 and 39,713. Chalcedon 19 and 44,215. Constantinople II 12 and 27,885. Constantinople III 5 and 11,042. Nicaea II 27 and 32,322.
  - The Nicaea file has 31,900 characters inside `<li>` elements the adapter never reads, which is where Tanner's canons are.
  - NPNF2-14 mixes council text with editor material: historical introductions, Excursus, "Notes" by Percival, the "Ancient Epitome" of each canon, and extracts from Zonaras, Balsamon and Aristenus. Its ThML is not vendored. The structure described here comes from the CCEL table of contents and is unverified until 1.2a opens the file. R6 found the file is 3,196,008 bytes, its header says "Rights: Public Domain", and the original edition is Oxford: James Parker; New York: Christian Literature Company, 1900 (`docs/research/R6-editions.md`).
- **Changes:**
  - Vendor `https://ccel.org/ccel/s/schaff/npnf214.xml` through `scripts/vendor_sources.py` into `sources/councils/npnf214.xml`, with URL, SHA-256, retrieval date and "Rights: Public Domain" from the file header recorded in the councils manifest.
  - Write `ingest/councils_percival.py` with a per-council allowlist of ThML div ids taken from the 1.2a inventory, for example Nicaea: Creed, Canons I to XX, Synodal Letter. Allowlist rather than denylist, so an unrecognised Excursus is dropped by default.
  - Within allowed divs, drop child divs or paragraphs titled "Ancient Epitome", "Notes", "Excursus" or anything 1.2a marks as editor material. Strip `<note>` through the 1.10b helper.
  - Anchors: `council-of-nicaea/canon/5`, `council-of-nicaea/creed`, `council-of-nicaea/synodal-letter`, and `council-of-chalcedon/definition`. Keep `canon/N` wherever the old build had it, so those canons keep their IDs. The canon is the same unit in a new translation, so set passage metadata `text_replaced: "Percival (NPNF2-14) replaces Tanner"` for 0.1c's stability check.
  - Old Tanner passages that are not the same numbered unit (Tanner's introductions, section cuts such as `council-of-nicaea/sec-1/1`) get a redirect to the Percival passage holding the same text where one exists, or a removal-registry entry with reason `superseded-translation` (or `rule-g-editorial` for Tanner's introductions) and a tombstone naming the replacement edition.
  - `author` is the council's name. Keep the manifest's `year` and `council_number`.
  - Route councils 1 to 7 in `build_documents` to the new builder. The Tanner HTML files stay vendored until 1.2e lands, but no builder reads them.
- **Acceptance checks:**
  - `test_percival_allowlist_drops_epitome_and_notes`, `test_percival_canon_anchors`, on a synthetic ThML fixture.
  - Vendored checks: Nicaea yields 20 canons plus the Creed and the Synodal Letter. Constantinople I 7 canons (Percival prints 7). Ephesus 8 canons, Cyril's letters and the 12 anathemas. Chalcedon 30 canons and the Definition. Constantinople II the 14 anathemas. Constantinople III the Definition. Nicaea II 22 canons and the Definition. Adjust these counts to what 1.2a finds and say so in the PR.
  - No passage contains "Ancient Epitome", "Excursus" or "Zonaras".
  - The release report lists every old Tanner anchor and its outcome. Every outcome other than `same` has a redirect row or a removal entry.
- **Production safety:** Document IDs are unchanged (`document_id("councils", council, council)` and registry-frozen). Canon IDs are unchanged; other old passages are redirected or retired as above. Tanner text stays live until the P4 apply.
- **Needs Carter:** nothing, if 1.2a is approved.
- **Out of scope:** the Apostolic Canons (Fathers, 1.8c). Local councils printed in NPNF2-14 (Ancyra, Neocaesarea, Gangra, Antioch, Laodicea, Sardica, Carthage and others), which are not ecumenical and are not in the plan.

### 1.2d. Vatican I from Schaff's Creeds of Christendom vol. 2

- **Type:** PR
- **Depends on:** 1.2a, 0.2, R6
- **Source files (decided by Carter, 5 Oct 2026):** Its approved R6 downloads are vendored in `datapipeline/sources/_incoming/`, under the path R6's "Vendored as" column gives (`_incoming/<path>`), where no adapter reads them. This PR moves each file it ingests, unchanged, to `sources/<path>` and runs `python3 scripts/source_lock.py --write`; the hash stays the same and the lock keeps the file's download date and URL. Its `rights_inventory.json` row already names `<path>` as `source_path`. Files: `councils/creeds2.xml`.
- **Goal:** Dei Filius and Pastor Aeternus are searchable in full, chapter and canon, in Manning's public-domain English. Today Vatican I is 9 passages and 6,053 characters.
- **Current state:**
  - The vendored Tanner page keeps 86,381 characters in `<li>` elements (653 of them), which the adapter ignores.
  - R6 (5 Oct 2026): CCEL's `creeds2.xml` (4,065,931 bytes) is Schaff's sixth edition (Harper, 1931, revised by David S. Schaff); no renewal was found in the complete 1958 and 1959 renewal records, and its Vatican I text matches the 1877 edition word for word. The rights row is `pd-us-non-renewal`.
  - CCEL `creeds2` section v.ii.i is a two-column table per page: Latin in a `<td>` with `<span lang="LA">`, English in the other `<td>`. Sentences run across tables at page breaks ("...placed over the universal" continues in the next table). Schaff's footnotes are inline notes ("From a Brief of Pius VI..."), which are editor material. Verified on the CCEL HTML page on 29 Sep.
- **Changes:**
  - Vendor `creeds2.xml` with hash and rights line into `sources/councils/`.
  - `ingest/councils_schaff.py`: take only the Vatican Council section. From each two-cell row keep the cell without `lang="LA"`. Concatenate English cells across page tables before splitting paragraphs. Strip notes (1.10b helper) and page-break spans.
  - Structure: Dei Filius prologue, chapters 1 to 4, canons grouped by chapter. Pastor Aeternus prologue, chapters 1 to 4. Anchors: `first-vatican-council/dei-filius/chapter-3`, `first-vatican-council/dei-filius/canons-3/canon-2`, `first-vatican-council/pastor-aeternus/chapter-4`.
  - The Latin cells are not stored. Rule E makes English searchable, and the official Latin is available elsewhere.
- **Acceptance checks:**
  - `test_schaff_keeps_english_cell_only`, `test_schaff_joins_english_across_page_tables`, on a fixture with 2 tables and a mid-sentence page break.
  - Vendored checks: 4 chapters and 18 canons in Dei Filius, 4 chapters in Pastor Aeternus. Chapter 4 of Pastor Aeternus contains "is possessed of that infallibility". No passage has more than 5% Latin stopwords ("et", "est", "quae", "non").
- **Production safety:** Document ID unchanged. The 9 current passages are Tanner cuts, not the new chapter and canon units, so the new units get new IDs (D1). Each old ID gets a redirect to the new passage for the same chapter, matched by chapter title. Sessions 1 and 2 material that has no Schaff equivalent gets removal-registry entries (reason `translation-in-preparation`, tombstone "A public-domain English translation of this text is not yet available") and is listed in the gap register.
- **Needs Carter:** nothing.
- **Out of scope:** the rest of Schaff vol. 2 (the Creed of Pius IV, Ineffabilis Deus, the Syllabus).

### 1.2f. OCR clean-up tool and quality gate

- **Type:** PR
- **Depends on:** 1.10a (the shared text cleaner). Nothing else; it is a tool plus its tests.
- **Goal:** Councils 8 to 18 can be replaced before P4 even though Schroeder's text exists mostly as page scans (D9). This item builds, once, the OCR clean-up method the Decision log "OCR and scanned works" settles, and the gate a work must pass before ingestion. 1.2e uses it per council, and 5.6c later uses it per scanned work. OCR means software reading letters off page photographs; its output mixes in page numbers, running headers, margin notes and misread letters.
- **Current state:**
  - No OCR handling exists in `datapipeline/`. Every current source is born-digital HTML, ThML, USFM or JSON.
  - Schroeder's *Disciplinary Decrees of the General Councils* (1937) is an Internet Archive scan (`DisciplinaryCouncils`); on Wikisource 27 of 677 pages are proofread (`docs/research/2026-09-28-scan-only-works-text-sources.md`). Clean text exists only for Lateran I, II and IV (Fordham).
  - The Decision log fixes the method and the gate. This item implements them and adds no new rules.
- **Changes:**
  - New package `datapipeline/ocr/`:
    - `ocr/furniture.py`, the script clean-up step. It removes page furniture (running heads, page numbers, printer's signature marks, line-end catchwords) by position and by patterns repeated across pages, and rejoins words hyphenated across line breaks when the joined form is a dictionary word or occurs elsewhere in the work. It keeps paragraph breaks and records each removal in a per-page log.
    - `ocr/correct.py`, the constrained model correction step. It sends one passage at a time to a language model with instructions to fix character-level OCR errors only. A word-level diff then measures the change. Any edit that changes more than about 2% of the passage's words is rejected and the script-cleaned text is kept. The raw OCR and the script-cleaned text are stored beside the corrected text (`raw_ocr`, `cleaned`, `corrected` per passage in a local, gitignored work directory), so every change can be audited and reverted. Model, prompt version and cost are recorded per run. Model calls need Carter's spend approval like any other provider call.
    - `ocr/gate.py`, the quality gate a work must pass before its adapter PR can merge:
      1. The unrecognized-word rate on body text, measured against a fixed English word list plus a per-work list of proper names, is within 1 percentage point of the clean baseline. The baseline is the rate on a comparable clean text of the same period (for councils, the Fordham Lateran text).
      2. 20 passages chosen at random with a recorded seed are checked by a person against the page images. The gate records, per passage, the page reference and "matches" or the differences found. Any wording change fails the work.
    - `ocr/report.py` writes a `gate.md` per work with both results, the rejection count from step 2 of the clean-up, and the seed. It is pasted into the adapter PR.
  - Source label. Every passage built from scanned text carries `metadata["text_source"] = "ocr"` plus the scan identifier, so 2.4b can show a label such as "Text from a scanned edition" when the passage is opened. Passages from clean typed text do not carry it.
  - Fixtures. `tests/fixtures/ocr/` holds 3 synthetic page texts written for the test (no scan text): a running head, a page number, a hyphenated line end, and 2 character errors.
- **Acceptance checks:**
  - `tests/test_ocr.py::test_furniture_removed_keeps_paragraphs`, `::test_hyphen_rejoined_only_for_known_words`, `::test_correction_over_word_limit_is_rejected_and_cleaned_text_kept` (with a stubbed model), `::test_raw_ocr_kept_beside_corrected`, `::test_gate_fails_above_baseline_plus_one_point`, `::test_gate_requires_twenty_checked_passages`, `::test_scanned_passages_carry_source_label`.
  - A dry run on one Schroeder council (the smallest by page count) produces a `gate.md` with both numbers, pasted into the PR as a demonstration. It does not ingest anything.
- **Production safety:** Tooling only. Nothing is ingested or published by this item. The model calls send only public-domain scan text to the provider, never user data.
- **Needs Carter:**
  - Approve the spend ceiling for model correction per work.
  - Know that each work's 20-passage check takes about 30 to 60 minutes of a person's time (Decision log).
- **Out of scope:** Running the tool on any council (1.2e) or scanned work (5.6c). Re-typing or translating any text. Choosing between OCR and a clean copy for a work, which R6 records.

### 1.2e. Councils 8 to 18 from Schroeder 1937

- **Type:** PR, one per council or per source group
- **Depends on:** 1.2a, 1.2f (the OCR tool and gate, for every council without a clean text), 0.2 (renewal search recorded for Schroeder, supplied by R6)
- **Source files (decided by Carter, 5 Oct 2026):** Its approved R6 downloads are vendored in `datapipeline/sources/_incoming/`, under the path R6's "Vendored as" column gives (`_incoming/<path>`), where no adapter reads them. This PR moves each file it ingests, unchanged, to `sources/<path>` and runs `python3 scripts/source_lock.py --write`; the hash stays the same and the lock keeps the file's download date and URL. Its `rights_inventory.json` row already names `<path>` as `source_path`. Files: `councils/fordham-lateran1.html`, `councils/fordham-lateran2.html`, `councils/fordham-lateran4.html`, `councils/DisciplinaryCouncils/DisciplinaryCouncils_djvu.txt`. Its PDF and its hOCR word-position file are approved per work later and are vendored to `_incoming/` the same way. The Fordham pages are for checking the OCR only and are not ingested; they move to their paths when 1.2e first uses them, like the other files, and no adapter reads them there because the councils adapter builds only what its manifest lists.
- **Goal:** Constantinople IV through Lateran V come from Schroeder's public-domain translation. Where Schroeder has no text, the gap register says so. Where a council's Schroeder text is not ready at P4, its Tanner text is retired and a "translation in preparation" tombstone shows the gap (D9).
- **Current state:**
  - Current build (Tanner): Constantinople IV 26 passages, Lateran I 29, Lateran II 33, Lateran III 33, Lateran IV 105, Lyons I 44, Lyons II 44, Vienne 112, Constance 201, Basel-Ferrara-Florence 130, Lateran V 87. The generic builder also loses text inside lists in several of these (Lateran I has 22,306 characters in `<li>`).
  - Clean text exists only for Lateran I, II and IV on Fordham's Internet Medieval Sourcebook. On Wikisource, 27 of 677 pages are proofread. The rest is an Internet Archive scan (`DisciplinaryCouncils`). Source: `docs/research/2026-09-28-scan-only-works-text-sources.md`.
  - Schroeder prints commentary after each canon. That is rule G material.
  - R6 (5 Oct 2026): title page St. Louis and London, B. Herder Book Co., 1937, "Copyright 1937", printed in U.S.A. Renewal search found no renewal; the 11 rights rows are drafts for Carter's approval. Fordham's three pages cite Schroeder's page ranges and carry Halsall's notice that the electronic form is copyright and not licensed for commercial use. The IA OCR text is 2,032,979 bytes and the page-image PDF 52,002,596.
- **Changes:**
  - 1.2e-1: Lateran I, II and IV from the Schroeder scan through the 1.2f tool, like the other councils. Fordham's three transcriptions are vendored only as a reference to check the OCR against and are never ingested (Carter, 5 Oct 2026). Parse canon by canon. Drop Schroeder's commentary. Anchors `first-lateran-council/canon/N`, as today where Tanner had the same number.
  - 1.2e-2 onward: the other 8 councils through the 1.2f tool, which strips furniture, applies model correction under the 2% word-change limit, and gates on the unrecognized-word rate and a 20-passage check against page images. Proofread Wikisource pages replace OCR where they exist. Every passage from OCR text carries the 1.2f source label.
  - Constantinople IV: Schroeder prints its 27 canons. Florence: whatever Schroeder prints; the doctrinal decrees go in the gap register.
  - Identity. Where the old Tanner anchor names the same canon (`first-lateran-council/canon/N`), the anchor and ID stay and the passage sets `text_replaced`. Councils Tanner cuts by session (Constance, Basel-Ferrara-Florence, Lateran V) are rebuilt by session, so their new units get new anchors and new IDs, and each old ID gets a redirect to the passage holding its text (D1). Tanner text with no successor, including every Tanner document on the gap register, gets a removal-registry entry: reason `superseded-translation` where Schroeder covers it elsewhere, `translation-in-preparation` where no public-domain text exists yet.
  - Fallback at P4 (D9, D11). If a council has not passed the 1.2f gate when the P4 build is cut, its adapter emits no passages for that council. 4.1b step 1 owns this fallback: the PR there that freezes the P4 build adds removal-registry entries of reason `translation-in-preparation` for all of the council's Tanner passages, with the tombstone "A public-domain English translation of this council is in preparation; TheoCorpus makes no translations of its own." This item only makes the adapter able to emit nothing for a council. The document ID stays frozen, so the council can be published later by a normal stage-then-apply publish.
- **Acceptance checks:** per council, the canon count Schroeder prints (from 1.2a), a passing 1.2f `gate.md`, and no commentary text. A gap row exists for every Tanner document without a Schroeder equivalent. Every old Tanner passage has an outcome backed by a redirect or a removal entry.
- **Production safety:** Document IDs unchanged. Tanner text stays live until the P4 apply, where it is replaced or retired. Nothing is deleted (D3).
- **Needs Carter:** Use Fordham's transcriptions of Lateran I, II and IV directly, or only to check the OCR of the scan, given the copyright notice on Fordham's pages (R6 recommends checking only, as for ecatholic2000). Answered 5 Oct 2026: checking only; 1.2e-1 states it. Florence loses Laetentur caeli and the Decree for the Armenians until a public-domain translation exists. The plan already accepts recording that gap. What P4 publishes for a council that is not ready is now settled by D9 (retire with a tombstone), so no decision is needed there.
- **Out of scope:** Trent (1.2b), Vatican I (1.2d), any translation of our own. Building the OCR tool (1.2f).

---

### 1.3a. Papal documents: one parser that keeps list text, drops endnotes and debris

- **Type:** PR
- **Depends on:** 1.10c
- **Goal:** Whole papal documents are readable. In Dominico Agro and Annus Qui Hunc gain their bodies. Endnotes stop appearing as walls of citations. Cards such as "PAUL VI" and "146" disappear. Quanta Cura (1864) cites real paragraphs.
- **Current state:**
  - Also found by 0.1a's checks (5 Oct 2026): prose after a bold heading is dropped until the next numbered paragraph (Allatae Sunt 86% of body kept, Vix Pervenit 68%); prose before §1 is dropped (Signum Magnum 50%, Patris Corde 86%); the inline-footnote reset at `encyclicals.py:122-131` cuts real paragraphs (Inscrutabile §10 to §17, Inter Praecipuas §17 to §24, Quartus Supra §52 to §66); numbered list items inside a section become second passages for §1 to §7 (Dominum et Vivificantem, Redemptoris Mater, Laudate Deum, C'est la confiance, Familiaris Consortio, Africae Munus); and 10 documents whose source has no paragraph numbers get § numbers the adapter invents (Mysterium Fidei 95, Haerent Animo 102, Ineffabilis Deus 58, Gaudete in Domino 78, among others). Each is a `known_defects.json` entry.
  - `encyclicals.py` (257 lines), `apostolic_exhortations.py` (231) and `papal_documents.py` (231) are three copies of one parser, not one file. With comments and docstrings removed, they differ only in the source directory and the collection name (verified by `diff` on 29 Sep); `encyclicals.py` carries 26 more lines of comments and docstrings. A fix in one silently misses the other two.
  - List bodies. `_tokens` reads only `<p>` (`encyclicals.py:77`). In Dominico Agro keeps 224 of 10,422 characters; its body is 8 `<li>` items. Annus Qui Hunc keeps 2,277 of 64,743; 62,378 characters sit in 15 `<li>` items. Five more documents lose short lists inside paragraphs: Familiaris Consortio 1,155 characters, Reconciliatio et Paenitentia 1,038, Pascendi 910, Rerum Novarum 609, Immortale Dei 584. The plan described this as Roman-numeral headings. It is `<ol>` list markup.
  - Endnotes. The notes trim at `encyclicals.py:79-83` needs a "NOTES" heading. vatican.va Word exports instead put notes after an `<hr>` as paragraphs starting with `<a name="_ftnN">`. A citation-density check finds at least 82 passages in 18 documents made of notes. Examples: Fratelli Tutti §287 is 9 pieces, 8 of them notes (`fratelli-tutti/287/p2` to `/p9`). Redemptor Hominis notes land under a duplicate §1 anchored `redemptor-hominis/1/p2` to `/p4`, positions 49 to 51. Others: Redemptoris Mater, Redemptoris Missio, Veritatis Splendor, Dominum et Vivificantem, Evangelii Gaudium, Laudato Si, Dilexit Nos, Magnifica Humanitas, Christifideles Laici, Ecclesia in Medio Oriente, Gaudete et Exsultate, Laudate Deum, C'est la confiance, Dilexi te, Dies Domini, Patris Corde.
  - Fratelli Tutti §287 also absorbs the two closing prayers and the dating line.
  - Tiny passages. Live has 28 under 20 characters. The current build has 18, because 10 were page-number fragments fixed on 22 Aug. The remaining 18 are:
    - bold headings in unnumbered documents turned into paragraphs by the fallback at `encyclicals.py:134-146` (8 in Ineffabilis Deus, such as "Liturgical Argument")
    - numbered headings ("1. Full of Grace" in Redemptoris Mater, "2. Education" in Familiaris Consortio, "Islam" in Africae Munus, 2 in C'est la confiance)
    - dates and signatures ("May 9, 1975", "PAUL VI", "Paul VI, Pope.")
  - Quanta Cura (1864): the source leaves the first paragraph unnumbered and numbers 2 to 12. The adapter puts that first paragraph in the Preamble and turns the lone endnote into §1 at position 12 ("Gregory XVI, encyclical epistle 'Mirari vos'"). Every passage has chapter label "Paragraphs 1 to 12" (printed with an en dash). Live matches exactly.
  - Italian Ubi Lutetiam is rule E work (3.3).
- **Changes:**
  - Move the shared code into `ingest/papal_common.py`: `tokens(soup)` and `build_document(entry, collection, src_dir)`. The three adapter modules become thin wrappers that keep their `document_id(collection, slug)` calls, so IDs do not move.
  - Element stream: walk `p`, `li` and `h2` to `h4` in document order. Skip an element whose ancestor is already in the stream. An `<li>` inside the body is a paragraph or continuation like a `<p>`.
  - Notes cut. Stop at the first of:
    - a "NOTES", "ENDNOTES" or "FOOTNOTES" heading
    - an element whose first child is `<a name="_ftn\d+">` or `<a name="_edn\d+">`, the note target, not the `_ftnref` link
    - an `<hr>` followed within 3 elements by a paragraph starting `[1]` or `1.`
    - Keep the existing numbering-reset rule as a fallback.
  - Headings: a numbered paragraph under 80 characters without final punctuation, followed by another numbered paragraph, is a section heading, not a paragraph. In the unnumbered fallback, bold-only and centered-italic paragraphs are sections.
  - Closing matter: "Given at ..." dating lines and signature lines (a pope's name, all caps or bold, under 40 characters) join the last passage as its final lines. They no longer make their own card. Prayers after the last numbered paragraph ("A Prayer to the Creator") become passages with anchors `<slug>/prayer-1`, `/prayer-2` under a chapter named by their heading.
  - Implicit first paragraph: when numbering starts at 2 and the first unnumbered paragraph after the greeting is over 200 characters, it is §1. The preamble keeps only the greeting ("To Our Venerable Brethren ... Health and Apostolic Benediction.").
  - Bucket chapters: a document with no section headings and at most 20 paragraphs gets one chapter named for the document, not "Paragraphs 1 to 12".
  - Health rule: after building, no passage under 20 characters, unless it is a numbered paragraph whose source text really is that short. Log each exception.
  - Metadata `pope` stays. Add `source_url`.
- **Acceptance checks:**
  - Synthetic fixtures and tests: `test_li_body_is_kept`, `test_word_export_footnotes_are_cut`, `test_hr_then_numbered_notes_are_cut`, `test_numbered_heading_is_section`, `test_dating_and_signature_join_last_passage`, `test_implicit_first_paragraph_when_numbering_starts_at_2`, `test_three_adapters_share_one_tokenizer` (the modules import `papal_common`).
  - Vendored checks:
    - In Dominico Agro at least 9,500 characters. Annus Qui Hunc at least 60,000.
    - Across all 175 documents, characters kept at least 98% of visible body text before the notes cut. The check prints the 10 worst documents.
    - Zero passages where citation markers ("AAS", "Ibid.", "op. cit.", "Cf.") occur at 4 or more per 1,000 characters. Report any that remain.
    - Zero passages under 20 characters except logged exceptions.
    - Quanta Cura (1864) has §1 to §12 in order, the Preamble under 250 characters, and no passage containing "Mirari vos" as its whole text.
- **Production safety:** Document IDs unchanged, because each wrapper keeps its collection in `document_id`. Changes this PR must record:
  - Note anchors such as `redemptor-hominis/1/p2` to `/p4` and `fratelli-tutti/287/p2` to `/p9` get removal-registry entries (reason `note-split-off`).
  - Heading anchors (`ineffabilis-deus/4`, `redemptoris-mater/1-2`) and date or signature cards get entries with reason `debris`. Where a heading's words now open the next section, that section keeps its own ID.
  - `quanta-cura-1864/1` holds the endnote today. Under D1 its ID keeps naming that text, so it is retired (reason `note-split-off`). The real first paragraph is a new unit: it gets a new ID and an anchor that has never been live (`quanta-cura-1864/para-1`), so old `?anchor=quanta-cura-1864/1` links never land on different text. The release report confirms the old ID is `removed` with a registry entry and the new one is `new`.
  - Paragraphs recovered from `<li>` markup are new text inside existing numbered units; those units keep their IDs and pass 0.1c's stability check because their old text is contained in the new.
- **Needs Carter:** nothing.
- **Out of scope:** genre labels (1.3b). Merging the three collections (5.1b). Adding A New Hope for Lebanon and Ubicumque et Semper (5.4). Amoris Laetitia, the third unmanifested file, which Carter scheduled for 5.4 on 4 Oct 2026. OCR-style typos in the Annus Qui Hunc source ("Wehave", "inor- der").

### 1.3b. Papal genre metadata

- **Type:** PR
- **Depends on:** 1.3a
- **Goal:** Each papal document says what it is, using the papal genres from D5: encyclical, apostolic exhortation, apostolic letter, apostolic constitution, motu proprio, bull, letter, or other. The genre filter (5.1a) then works, and cards stop calling Evangelii Gaudium an encyclical.
- **Current state:**
  - No papal manifest entry has a genre. The collection is the only signal.
  - Misfiled in encyclicals, per the plan: Evangelii Gaudium and Evangelii Nuntiandi (apostolic exhortations), Ineffabilis Deus and Munificentissimus Deus (apostolic constitution or bull), the Syllabus of Errors (an annexed list), and three Jubilee bulls. The plan does not name the three. Candidates from the manifest: Peregrinantes (1749), Salutis Nostrae (1774), Quod Hoc Ineunte (1824). Unverified.
  - Apostolica Constitutio (1749) should also be checked.
  - Papal documents mixes bulls (Unam Sanctam, Exsurge Domine, Sublimis Deus), apostolic letters (Salvifici Doloris, Mulieris Dignitatem, Ordinatio Sacerdotalis, Tertio Millennio Adveniente, Orientale Lumen, Dies Domini, Novo Millennio Ineunte, Rosarium Virginis Mariae, Misericordia et Misera, Patris Corde) and a motu proprio (Porta Fidei).
- **Changes:**
  - Add `genre` to every entry of the three manifests, set in `scripts/vendor_sources.py` so a re-vendor keeps it. Values come from `PAPAL_GENRES` in 2.1's genre module (`datapipeline/registry/genres.py`, D11), imported, never retyped: `encyclical`, `apostolic-exhortation`, `apostolic-letter`, `apostolic-constitution`, `motu-proprio`, `bull`, `letter`, and `other` for anything else. The Syllabus of Errors, an annexed list, is `other`. A value outside that list needs a PR to 2.1's module first; this item adds none.
  - Each value cites the document's own heading on vatican.va, or papalencyclicals.net where vatican.va has no English page. Record the citation in a tracked table `datapipeline/papal_genres.csv` (slug, genre, evidence URL). The manifests are gitignored, so the CSV is what reviewers read.
  - The builders copy `genre` into `Document.metadata["genre"]` so the release report can show it. 2.3 then copies these values into the 2.1 registry, and the registry value is the one 2.2w writes to `documents.genre`; after 2.3 nothing reads the metadata key.
  - Do not move documents between collections. Their IDs include the collection, and 5.1b merges the collections anyway.
- **Acceptance checks:** `test_every_papal_manifest_entry_has_genre`, which fails on a missing value or one outside `PAPAL_GENRES` plus `other` (imported from 2.1's module, the same one 2.2a seeds `corpus_genres` from). A vendored check prints a count per genre and per collection. The PR lists each document whose genre disagrees with its current collection.
- **Production safety:** Metadata only. No ID or anchor change. The API ignores unknown metadata keys. The genre reaches live data only through the P4 apply (D7).
- **Needs Carter:** confirm the three Jubilee bulls and whether Ineffabilis Deus and Munificentissimus Deus are labelled "apostolic constitution" (their own form) or "bull".
- **Out of scope:** the `genre` column and filter (2.2a, 5.1a). The collection merge (5.1b).

---

### R3. Esther (specified in the P0 file)

R3 is specified once, in `P0-checks-identity-research.md` under "R3. Esther: what the WEB-C text contains and how it maps to the Nova Vulgata" (D10). Its deliverable is `docs/research/R3-esther.md`. It blocks 1.4a. The details first gathered here (the additions' positions in the USFM file, the 41 skipped verses, the lettered-verse question) now live in that entry.

### 1.4a. Bible: publish every verse and rename Song of Songs

- **Type:** PR
- **Depends on:** R3, 1.10c
- **Goal:** Every verse in the WEB-C source is in some passage. Susanna, Bel and the Dragon, the Song of the Three and the Esther additions become findable. The book is called Song of Songs.
- **Current state:**
  - Also found by 0.1a's checks (5 Oct 2026): Numbers 16:28 to 16:37 sit in two KJV pericopes ("Korah, Dathan, and Abiram" ends at 16:37; "The Earth Swallows and Fire Consumes" starts at 16:28), so those 10 verses are published twice.
  - `ingest/bible.py:563-586` builds passages only from the KJV pericope file's ranges. A verse outside every range is dropped. Books with no pericopes use the chapter fallback at `bible.py:589-610`.
  - The current build drops 244 verses:
    - Daniel 173 (3:31 to 3:97, all of 13, all of 14)
    - Esther 41 (4:18 to 4:47, 10:4 to 10:14)
    - Isaiah 6 (16:14, 55:9 to 55:13)
    - 1 Kings 5 (8:62 to 8:66)
    - Deuteronomy 4 (1:5 to 1:8)
    - Romans 4 (14:24 to 14:26, 16:24)
    - Exodus 3 (6:28 to 6:30)
    - Mark 2 (2:28, 11:26)
    - Judges 2 (4:24, 19:30)
    - Joshua 22:34, 2 Kings 4:18, 2 Chronicles 35:27, Jeremiah 20:18
  - The plan's 245 is the live count.
  - Daniel 3 is worse than missing verses. KJV ranges 3:1 to 3:30 pull WEB-C 3:1 to 3:30, which in WEB-C's Greek numbering is the start of the Prayer of Azariah. KJV 3:24 to 30 corresponds to WEB-C 3:91 to 97. So the live Daniel 3 passage is also mislabelled.
  - "Song of Solomon" is hard-coded at `bible.py:48` and `bible.py:80`. The document ID is `document_id("bible", "WEB-C", name)` (`bible.py:557`), and anchors start with the book slug (`bible.py:574`).
  - `_STANZA_BOOKS` and `chunk_stanza_book` (`bible.py:111`, `482-514`) are unused by `build_documents`.
- **Changes:**
  - Drive the build from the USFM verse list. For each book, walk verses in order and assign each to the first pericope range that contains it by WEB-C number. Verses in no range form their own group, closed at chapter ends and at the next pericope start.
  - Label such a group from a small tracked table `datapipeline/bible_extra_pericopes.csv` (book, start, end, title, nv_ref, lxx_ref, nab_ref; the last three are empty except for Esther). Each row also bounds its group, so the Esther C rows split C at 4:28/4:29. Seed it with "Prayer of Azariah and Song of the Three" (Daniel 3:24 to 90), "Susanna" (13), "Bel and the Dragon" (14) and the Esther additions per R3 (Decision log "Esther additions numbering (R3)"): 4:18 to 28 "Addition C: Mordecai's prayer", 4:29 to 47 "Addition C: Esther's prayer", 10:4 to 14 "Addition F: Mordecai's dream explained". References keep WEB-C numbers. Passage metadata carries `nv_ref`, `lxx_ref` and `nab_ref` from those columns, at the level R3 maps (R3 section 6): Mordecai's prayer "Esther 4:17a–m", "Esther 4:17a–i" and "Esther C:1–11"; Esther's prayer "Esther 4:17n–kk", "Esther 4:17k–z" and "Esther C:12–30"; Addition F "Esther 10:3a–k", "Esther 10:3a–l" and "Esther F:1–11". `lxx_ref` uses Rahlfs' lettering (the one the Catechism and the Italian Lectionary cite), checked against the CCAT Rahlfs text (R3, "Septuagint letters checked"). C is split at the change of speaker, which falls at the same point in both texts (Nova Vulgata 4:17m/17n, WEB-C 4:28/4:29; R3 section 2, row C), so each prayer's range is still a whole unit. Never per-verse aliases. They are new units, so no existing anchor changes text and no redirect is needed.
  - Daniel 3: replace the KJV ranges for chapter 3 with WEB-C-native ranges in the same CSV, so the chapter reads in order and cites correctly.
  - Rename to "Song of Songs" in both tables. The registry (2.1) keeps document ID `9df0b246-...` for the renamed book. Build anchors from a registry-supplied book slug that stays `song-of-solomon`, so no passage ID changes. The title shown is "Song of Songs".
  - Delete the dead stanza code and its tests, or move Sirach to it in 1.4c. Do not leave both.
  - Add a completeness assertion inside `build_documents`: the set of `(chapter, verse)` in passages equals the set in the USFM, excluding verses whose text is empty (24 in the current source, such as Sirach 1:5 and 1:7). If they differ, raise.
- **Acceptance checks:**
  - `test_every_usfm_verse_lands_in_a_passage` (synthetic USFM with a verse outside all pericopes).
  - `test_extra_pericope_labels_apply`, which also asserts the Esther passages' `nv_ref`, `lxx_ref` and `nab_ref`.
  - `test_song_of_songs_title_keeps_frozen_id_and_anchor_slug`.
  - Vendored check: 0 missing verses in 73 books. Daniel has 14 chapters with 21, 49, 97, 37, 31, 28, 28, 27, 27, 21, 45, 13, 64 and 42 verses.
- **Production safety:** Document IDs unchanged, including Song of Songs through the registry. The restored verses are new units with new IDs (Susanna, Bel and the Dragon, the Song of the Three, the Esther additions). A Bible anchor `book/ch/firstverse` names the pericope that starts at that verse, so a passage that still starts at the same verse keeps its ID even if its span grows to take in a restored verse. Changed passages are Daniel 3 and the pericopes bordering each gap. An old passage whose first verse no longer starts a passage (Daniel 3's KJV ranges) gets a `merged` or `split` redirect to the passage now holding that verse by WEB-C number.
- **Needs Carter:** confirm keeping `song-of-solomon` in anchors. With 2.1's frozen passage IDs, renaming the anchors would change no ID, but old links would then depend on `live_anchor` resolution and nothing a user sees would improve. Recommended: keep.
- **Out of scope:** renumbering (1.4b), deuterocanonical chunking (1.4c).

### 1.4b. Bible: Nova Vulgata chapter numbering for Joel and Malachi

- **Type:** PR, plus a decision
- **Depends on:** 1.4a
- **Goal:** Joel has 4 chapters and Malachi 3, so "Joel 3:1" means the outpouring of the Spirit, as it does in the Catechism and the Lectionary.
- **Current state:**
  - WEB-C uses KJV numbering: Joel has 3 chapters (20, 32 and 21 verses), Malachi 4 (14, 17, 18, 6).
  - Nova Vulgata: KJV Joel 2:28 to 32 is NV 3:1 to 5, and KJV Joel 3 is NV 4. KJV Malachi 4:1 to 6 is NV 3:19 to 24.
  - Other places where WEB-C and Church documents differ, found while measuring, not verified against the NV text: Daniel 4:1 to 3 (NV 3:98 to 100), 1 Kings 4:21 to 34 (NV 5:1 to 14), Romans 14:24 to 26 (the doxology, NV 16:25 to 27, with no 16:24 in NV), Jonah 1:17 (NV 2:1), Hosea 11 to 14 boundaries, Job 40 to 41. The plan names only Joel and Malachi.
- **Changes:**
  - Add a tracked versification table `datapipeline/bible_versification.csv` (book, source chapter:verse range, target chapter:verse range, authority) and apply it in `load_usfm_directory` before chunking. Start with Joel and Malachi only.
  - Passage references and chapter keys use the target numbers. Metadata keeps `source_ref` in WEB-C numbers.
  - New anchors (D1). Renumbering regroups passages at the new chapter boundaries (a pericope never crosses a chapter), so every Joel and Malachi passage becomes a new unit with a new ID. Its anchor carries a versification segment, `joel/nv/3/1` and `malachi/nv/3/19`, so no anchor string live today (`joel/3/1` meant the judgment of the nations) comes to name different text. Apply the segment to every passage of both books, including chapters whose numbers do not change, so each book has one scheme.
  - Redirects. For every old Joel and Malachi passage, add a row to 2.1's `registry/redirects.json` with kind `renumbered` (or `split` or `merged` where the regrouping split or joined pericopes), pointing to the new passage that holds its first verse under the target numbering. Old `joel/3/1` goes to `joel/nv/4/1`; old `joel/2/28` goes to `joel/nv/3/1`.
- **Acceptance checks:** `test_versification_moves_joel_2_28_to_3_1`, `test_versification_moves_malachi_4_to_3_19`, `test_renumbered_books_use_nv_anchor_segment`, `test_every_old_joel_and_malachi_passage_has_a_redirect`. Vendored: Joel has 4 chapters (20, 27, 5, 21 verses), Malachi 3 (14, 17, 24). The 0.1c report shows every old Joel and Malachi passage as `renumbered`, `split` or `merged`, none as `same` or `removed`, and no anchor-string reuse.
- **Production safety:** Without the new anchors, `joel/3/1` would survive with a different meaning and the same passage ID would silently point at different text. With them, old IDs are redirected, never reused. 4.1a moves bookmarks, retrievals and guest retrievals along the redirects before the new rows go live. The PR states how many old passages carry user rows; the renumbered ranges touch about 3 Joel passages and 1 or 2 Malachi passages.
- **Needs Carter:** decide the versification scope. Options:
  - Joel and Malachi only, as the plan says.
  - All NV chapter divisions that Church documents cite in English, with Hebrew psalm numbering kept, since English Church documents cite "Psalm 51" and not "Psalm 50". Each addition needs its own row and evidence in the table.
  - Recommended: the first now, with the audit list above as a follow-up issue.
- **Out of scope:** psalm numbering. Verse-level differences inside chapters.

### 1.4c. Bible: pericope passages for the deuterocanonical books

- **Type:** PR
- **Depends on:** 1.4a
- **Goal:** Tobit, Judith, Wisdom, Sirach, Baruch and 1 and 2 Maccabees get focused passages like the other books, instead of one passage per chapter.
- **Current state:**
  - These 7 books have no pericopes in the KJV file, so `bible.py:589-610` makes one passage per chapter, split at 3,500 characters. Counts: 1 Maccabees 47 passages (average 2,733 characters), 2 Maccabees 37 (2,639), Sirach 59 (2,543), Wisdom 25 (2,416), Judith 25 (2,427), Tobit 16 (2,298), Baruch 12 (2,326). Other books average about 1,450.
  - The USFM has no section headings (`\s`) in these books. It has paragraph and stanza markers: Tobit 82 `\p`, Judith 84, 1 Maccabees 185, 2 Maccabees 125, Baruch 24, Wisdom 50 `\b`, Sirach 245 `\b`.
- **Changes:**
  - Boundaries come from the USFM. Group consecutive `\p` paragraphs, or `\b` stanzas for Wisdom and Sirach, into passages of 600 to 1,800 characters. Never cross a chapter. Never split a verse.
  - Titles: record them in `bible_extra_pericopes.csv` only where a public-domain source gives them. The Douay-Rheims chapter summaries are a candidate; check with R6. Otherwise the passage has no pericope title and its reference is the verse range.
  - Anchors `book/chapter/firstverse`, like the protocanonical books.
- **Acceptance checks:** `test_deutero_groups_paragraphs_within_cap`, `test_deutero_never_crosses_chapter`. Vendored: every passage in the 7 books is 300 to 2,200 characters, except where a single paragraph is longer. No verse is lost (1.4a's assertion).
- **Production safety:** Each chapter's first passage keeps `book/ch/1` and its ID. The old `book/ch/1-2` pieces disappear; each gets a `split` or `merged` redirect to the new passage holding its first verse. The new first-verse passages are new units with new IDs.
- **Needs Carter:** whether to take pericope titles from Douay-Rheims summaries or ship without titles. Recommended: without, for now.
- **Out of scope:** Psalms, which already get one passage per psalm.

---

### R2. Canons (specified in the P0 file)

R2 is specified once, in `P0-checks-identity-research.md` under "R2. Canons 295, 296, 360, 361 and 948 against iuscangreg.it, and English sources for the Latin canons" (D10). Its deliverable is `docs/research/R2-canons.md`, in two parts: current text for canons 295, 296, 360, 361 and 948, and English sources for the Latin canons 111, 112, 535, 579, 695, 700 and 868. It blocks 1.5b.

### 1.5a. Canon law parser: split glued canons, find missing ones, keep new text, drop footers

- **Type:** PR
- **Depends on:** 1.10a
- **Goal:** "Canon 112" finds canon 112. Every canon from 1 to 1752 exists once, with the text the source marks as current. Page footers are gone. Amended canons carry an "amended" flag for the badge.
- **Current state:**
  - Also found by 0.1a's checks (5 Oct 2026): on `cic_lib7-cann1671-1716_en.html`, canons 1671 to 1691 carry the 2015 amended text (Mitis Iudex) and the kept text is not that one; the page's body is 78.6% covered.
  - `parse_canon_page` (`ingest/canon_law.py:259-312`) reads `p.get_text(strip=True)` per `<p>` and recognises a canon only at the start of a paragraph (`can_re`, line 271). `build_documents` keeps the first occurrence of each number (`canon_law.py:78-84`).
  - Live has 1,747 canons. Missing: 112, 238, 266, 689 and 1330.
  - Glue: in the source, canon 112 follows canon 111 after `<br><br>` inside the same `<p>`, so it is appended to 111. Same mechanism for 238 in 237, 689 in 688, new 1308 in 1307, new 1310 in 1309.
  - Superseded text: where the amendment marker comes first (`<font color="#663300">n</font> Can. 265`), the paragraph text begins "nCan. 265" and fails `can_re`. The new text is lost or appended to the previous canon, and the later "[Earlier version]" block supplies the old text. Affected: 265, 686 §1 (live says 3 years, current law says 5), 694, 1308, 1310. Canon 266 is lost because it is glued inside the new 265 paragraph.
  - Canon 1330 sits in a `<b>Can. 1330</b>` outside any `<p>` on the Book VI page.
  - Page footers leak into the last canon of 11 pages: 123, 329, 572, 606, 694, 709, 730, 780, 878, 1165 and 1309. They carry the marker legend ("indicates that the text corresponds to a new version"), "For Can. 111 and Can. 112: Cf.", and "[Earlier version]" or "[Original version ...]". The plan named only 123 and 694.
  - 10 live canons start with a stray "n", the marker: 111, 242, 579, 695, 700, 729, 838, 1008, 1117 and 1124.
  - All 88 Book VI canons (1311 to 1399) start with an em dash character (U+2014) and a space, copied from the 2021 page, which prints "Can. 1330" followed by that dash.
  - Canon 700 begins with the title of the motu proprio rather than the canon.
  - About 30 canons carry the "n" marker in the source. The PR must print the exact list.
- **Changes:**
  - Segment first, then match. For each `<p>`, and for each `<b>` or `<strong>` whose text starts "Can." outside any `<p>`, split the HTML on `<br>\s*<br>` into segments. Remove marker `<font>` elements (colour `#663300` with text "n") and set a flag on the segment. Match `^Can\.\s*(\d+)` per segment.
  - Versions. Track the page region. Everything from an "[Earlier version]" or "[Original version]" line to the next canon heading that is not inside such a block is superseded. Never use those texts as the canon's content. Emit each as its own history passage (rule F, D11): anchor `can/<N>/history-<year>`, where `<year>` is the year that version took effect (1983 for an "[Original version]"; for an "[Earlier version]", the year of the act that introduced it, from the page's "Cf." line), `searchable = False`, `superseded_by_anchor = "can/<N>"`, reference "Can. <N> (text in force from <year>)". When a canon number appears twice, prefer the marked version, then the one outside a superseded block. Raise if both candidates are unmarked and outside such blocks.
  - Footer. Cut a canon's text at "(n: indicates", "For Can.", "[Earlier version]" or "[Original version", whichever comes first, and at the Italian legend "Indica che il testo".
  - Book VI: strip a leading U+2014 dash and following space from canon text.
  - Canon 700: drop a leading line that begins "Apostolic Letter issued".
  - Amended flag: `metadata["amended"] = True` and `metadata["amended_by"]`, the linked act's title and URL from the page's "Cf." line, for every canon with the marker.
  - Keep today's `can/N` anchors and `Can. N` references. Canons whose content switches from the superseded version to the current one (265, 686, 694, 1308, 1310) keep their IDs and set `text_replaced: "current text replaces superseded version"`. The five restored canons (112, 238, 266, 689, 1330) are new units with new IDs; the canons they were glued into keep theirs.
- **Acceptance checks:**
  - Synthetic fixtures in `tests/test_canon_law.py`: `test_canon_glued_after_br_is_split`, `test_marker_before_can_is_recognised`, `test_earlier_version_block_is_not_current`, `test_earlier_version_becomes_unsearchable_history_passage` (anchor `can/<N>/history-<year>`, `superseded_by_anchor` `can/<N>`), `test_bold_canon_outside_p_is_found`, `test_footer_legend_is_cut`, `test_book_vi_leading_dash_removed`, `test_amended_flag_set_from_marker`.
  - Vendored checks:
    - Canon numbers are exactly 1 to 1752, each once.
    - Canon 686 §1 contains "five years".
    - Canon 265 contains "public clerical association". Canon 266 exists and starts "§1. Through the reception of the diaconate".
    - Canons 1308 and 1310 carry the post-2022 text: 1308 §1 names the diocesan bishop, not the Apostolic See.
    - Zero canons contain "Earlier version", "Original version", "indicates that" or "For Can.". Zero start with "n" followed by "§" or a capital letter, or with a U+2014 dash.
    - The amended list printed in the PR equals the marker list.
- **Production safety:** One document, ID `document_id("canon-law")`, unchanged. Anchors `can/N` unchanged for 1,747 canons. 5 new canon passages, plus one new history passage for each superseded version the source prints (not searchable). About 25 contents change. The API shows `metadata` it already reads. The badge itself is 2.4b.
- **Needs Carter:** nothing.
- **Out of scope:** replacing Latin text and the 295 update (1.5b). Renaming the collection to Church law (5.1b).

### 1.5b. Canon law: current text for 295 and the verified canons, English for the Latin canons

- **Type:** PR
- **Depends on:** 1.5a, R2
- **Goal:** Users read the law in force, in English, with an honest label where the English is unofficial.
- **Current state:**
  - Canon 295 is pre-2023 in the vendored page.
  - Latin in the English Code, live:
    - 111 in full. The new text of the 2016 motu proprio De concordia inter Codices is given only in Latin on the page.
    - 112, which is glued to 111 today, the same.
    - 579 in full, with the citation of Authenticum charismatis (2020) appended.
    - 700 in full.
    - 695 §1 only; §2 is English in the vendored page (R2).
    - 535 §2 and 868 §1 2° only. Live 868 contains "... parentibus.§2."
  - R2 (`docs/research/R2-canons.md`): 295 and 296 were amended in 2023 (Le Prelature personali, Latin text only); 360, 361 and 948 are unchanged in wording. Canon 868 §3 (added 2016) is missing from the vendored page. The marriage canons 1108, 1109, 1111, 1112, 1116 and 1127 still carry pre-2016 English.
  - The plan's rule (Decision log "Canon law English and amendments (R2)" for the current list): canons 111, 112, 535 and, once 868 §3 is print-checked, 868 show the L'Osservatore Romano English, labelled unofficial, with the Latin as the official text. For the others, rule E applies if no English exists: the reader keeps the Latin with a note, and search excludes it.
- **Changes:**
  - Add a vendored override file `sources/canon-law/overrides.json`: canon, field (`content` or a paragraph such as "§2"), text, language, status (`official`, `unofficial_english`), source title, source URL, retrieval date, SHA-256 of the fetched page. Vendor it through `vendor_sources.py`, so it stays out of the public repo like the pages. A tracked `datapipeline/canon_overrides_index.csv` lists canon, status and source URL without the text, for review.
  - `build_documents` applies overrides after parsing. For `unofficial_english`, the English goes in `content` and the Latin in `metadata["official_latin"]`, with `metadata["text_status"] = "unofficial_english"`. For canons with no English, keep the Latin in `content` and set the `Passage` fields `searchable = False` and `language = "la"` (2.1, D11), not metadata keys. A passage-registry row may override them (3.3). The 2.2b filter excludes only explicit `false`, so it will honour this. Until 2.2b ships nothing reads the fields, and that is fine because nothing publishes before P4.
  - Canons 295 and 296 take the 2023 Latin text from R2 with `amended_by` set, under rule E (Latin in `content`, `language = "la"`, `searchable = False`). The Vatican News English is not used. 360, 361 and 948 are unchanged and get no override and no reader note.
  - The Latin for every De concordia canon comes from the act itself on vatican.va (https://www.vatican.va/content/francesco/la/apost_letters/documents/papa-francesco-lettera-ap_20160531_de-concordia-inter-codices.html), since the vendored page has no 2016 text for 868 §3 or the marriage canons in any language. It goes in `metadata["official_latin"]` for `unofficial_english` canons and in `content` under rule E. The pre-2016 English of the marriage canons becomes `can/<N>/history-2016` passages (rule F), as for 295 and 296.
  - The De concordia inter Codices canons 111, 112, 535 §2 and the marriage canons 1108, 1109, 1111, 1112, 1116 and 1127 take the L'Osservatore Romano English of 23 Sep 2016, p. 9, as `unofficial_english` with the label "Unofficial English translation (L'Osservatore Romano). The Latin text is official." The override text is taken from the EWTN reprint (https://www.ewtn.com/catholicism/library/de-concordia-inter-codices-7264), whose canon texts match the CLSGBI English Code word for word; that agreement stands in for the print check (R2 "Follow-up", Decision log).
  - Rule E applies to whole canons; a canon is never part English and part Latin. Canon 868 follows rule E as a whole until 868 §3 is checked against the printed page (NEEDS-CARTER section C): `content` is the current Latin of the whole canon (§1 1° and §2 from vatican.va's Latin Code, §1 2° and the new §3 from the act), `language = "la"`, `searchable = False`, with the rule E reader note. §3 is a paragraph the vendored page lacks entirely; it goes in canon 868's passage. When the print check is done, 868 takes the ORE English for §1 2° and §3 like the other De concordia canons.
  - 579, 695 and 700 have no Holy See English for their amended text (R2) and follow rule E as whole canons. For 695 that includes §2, which has English, because §1 does not.
  - Identity. Each override is the same canon in new text, so it keeps its `can/N` anchor and ID, and the passage sets `text_replaced` ("2023 amendment", "unofficial English replaces Latin") for 0.1c's stability check. The superseded text of an amended canon becomes a history passage `can/<N>/history-<year>`, as in 1.5a (rule F, D11). It is kept, not removed, so it has no removal-registry entry.
- **Acceptance checks:**
  - `test_override_replaces_content_and_keeps_latin`, `test_latin_without_english_is_not_searchable`, `test_override_file_hash_mismatch_fails`.
  - Vendored: every canon whose override status is `unofficial_english` (111, 112, 535, 1108, 1109, 1111, 1112, 1116, 1127) contains no Latin stopword run of 5 or more words. Canons 868, 579, 695 and 700 have `language = "la"` and `searchable = False`, and 868 contains a §3. 295 matches R2's text. The PR lists every override with its source.
- **Production safety:** Same document and anchors. Content changes for about 15 canons (295, 296, 579, 695, 700, 868, and the nine other De concordia canons), plus one new history passage per amended canon. Nothing reads `searchable` until 2.2b.
- **Needs Carter:** Answered 4 Oct 2026 (sources, label, 295 and 296, 868 §3, marriage canons; see Decision log "Canon law English and amendments (R2)"). The print check is replaced by two-copy agreement, and 868 and 695 follow rule E as whole canons (Decision log, 4 Oct). Still needed: the print-page check for 868 §3, which would move 868 to English (NEEDS-CARTER section C).
- **Out of scope:** the Eastern code (blocked on licence). Universi Dominici Gregis and other universal law (5.4).
