# P1a work specs: shared hygiene, councils, papal, Bible, canon law

Written 29 September 2026 against `body-of-christ` master at `5475c49`, the vendored sources on Carter's Mac, and read-only queries on Supabase project `hvmgffvimqgiejmxwhwq`. The plan in `docs/2026-09-28-corpus-cleanup-plan.md` is the source of truth. Nothing here reopens its decision log.

## Overview

1. Every item in this file is a datapipeline change. None of them writes to production, because the publish lock (0.4) merges first and the republish waits for P4.
2. The worst defects are text that never reaches the corpus. Vatican II keeps 443,397 of 921,233 body characters (48%). Trent keeps 206,307 of about 548,711. Annus Qui Hunc keeps 2,277 of 64,743.
3. The next worst is text that should not be there. 32,211 translator notes, about 1.97 million characters, sit inline in Fathers and medieval passages. Endnotes are glued to the last paragraph of at least 18 papal documents.
4. Canon law loses 5 canons, keeps superseded text for 5, and leaks page footers into 11. The live count of 1,747 canons looks plausible but is 5 short of 1,752.
5. The Bible drops 244 verses in the current build (245 live), including all of Susanna, Bel and the Dragon, and most of the Song of the Three.
6. The council replacement (Percival, Schroeder, Schaff, Waterworth) is the largest item. Schroeder is mostly scan-only, so councils 8 to 18 depend on the OCR tooling of 5.6c or on a Carter decision about the gap.
7. ID effects are mostly anchor churn inside frozen documents. Three things need explicit remap rules: the Song of Songs rename, Joel and Malachi renumbering (same anchor, different verse), and council anchors rebuilt by session.
8. Research items R2 (canons) and R3 (Esther) are specified here and block 1.5b and 1.4a.
9. Recommended order: 1.10a, 1.10b, 1.10c, 1.1, 1.3a, 1.3b, 1.5a, R2 then 1.5b, R3 then 1.4a, 1.4b, 1.4c, 1.2a, 1.2b, 1.2d, 1.2c, 1.2e.
10. Start with 1.10 and 1.1: they are small, they touch every collection or the most-cited one, and they unblock the Nostra Aetate 4 fix that motivated this cleanup.

## Common ground for every item

These apply to every PR below and are not repeated in each item.

- Measurement environment: `cd datapipeline` with `DATABASE_URL=x OPENAI_API_KEY=x QDRANT_URL=http://x QDRANT_API_KEY=x` exported, then import the adapter's `build_documents`. The numbers in this file came from that setup on 29 Sep.
- Tests that need vendored files use the existing pattern `@pytest.mark.skipif(not _vendored, ...)` (see `tests/test_councils.py:12-13`). Synthetic HTML or USFM fixtures cover the same behaviour so GitHub Actions (0.0) runs something for every fix.
- Every PR description carries the locally run source-check section from the 0.0 template, the 0.1c release report for the touched collections, and the 0.1a coverage numbers before and after.
- Anchors: follow the structural anchor rules of 2.1. Where this file proposes an anchor shape, 2.1 wins if they disagree.
- Split pieces keep today's convention (`base/p1`, `base/p2`) unless 2.1 changes it. Where a fix makes a short unit long enough to split, its old anchor `base` becomes `base/p1`. The remap tool (0.1c, 4.1a) must map `base` to `base/p1`.
- Document IDs come from the frozen registry (2.1). Where a fix would change the computed ID, the registry keeps the old one and this file says so.
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
  - Authors: 54 documents, 3,862 passages, have an author ending in a period. The shared cause is `thml_doc.make_doc` (`ingest/thml_doc.py:35-91`), which passes the ThML div title through unchanged. Container names such as "Tertullian: Part Fourth.", "Anatolius and Minor Writers." and "Appendix." are wrong authors, not just bad punctuation. They belong to 1.8c.
- **Changes:**
  - Add `repair_sentence_joins(text)` to `normalize/text.py` and call it first inside `clean_text`. Rule: insert one space in `([a-z][.?!;:][”"’)]?)([A-Z][a-z])` and in `([.;:])(§)`. Skip any whitespace-delimited token containing `://`, `www.` or `@`.
  - Do not touch initials or abbreviations with a capital before the dot ("U.S.", "S.C.P.F."). The rule already requires a lowercase letter before the punctuation.
  - In `make_doc`, set `author = author.rstrip(" .")` and the same for `title`. `identity.slugify` drops punctuation, so `document_id(collection, author, title)` does not change. Test that too.
  - Fixtures: `"consecration.The Synod"`, `"said.”The"`, `"parentibus.§2. An infant"`, `"see www.vatican.va"`, `"U.S.Bishops"` (unchanged), `"St.Augustine"` (becomes "St. Augustine", accepted).
- **Acceptance checks:**
  - `test_repair_sentence_joins_inserts_space`, `test_repair_sentence_joins_ignores_urls_and_initials`, `test_clean_text_only_adds_whitespace`: for every fixture, `re.sub(r"\s", "", out) == re.sub(r"\s", "", inp)`.
  - Vendored check across all ten collections: after the fix, zero matches of the join pattern outside URLs. For every passage, content with whitespace removed is identical before and after. The PR prints the per-collection before and after counts.
  - `test_make_doc_strips_trailing_period_keeps_id`: author "Methodius." yields "Methodius" and the same `document_id` as before.
- **Production safety:** Content changes in about 150 passages across collections. No anchor or ID changes, because splitting happens on the same text plus a few spaces and the cap is 3,500 characters. The release report must still confirm zero anchor churn.
- **Needs Carter:** nothing.
- **Out of scope:** container authors ("Tertullian: Part Fourth.") and all other Fathers labels, which are 1.8c. Lowercase "the" sentence starts in the Catechism, which is 1.6.

### 1.10b. Strip inline translator notes from ThML text

- **Type:** PR
- **Depends on:** 1.10a
- **Goal:** Fathers and medieval passages read as the author wrote them, without ANF and NPNF footnotes such as "Matt. xxiv. 15" or "Literally, 'bidding farewell to'" in the middle of a sentence.
- **Current state:**
  - `ingest/common.py:37-50` `_direct_p_text` serializes each `<p>` and `_strip_tags` (`common.py:16-23`) removes tags but keeps their text. ThML keeps footnotes as `<note>` elements inside the paragraph, so every note's text lands inline.
  - Measured across the paragraphs the adapters actually read: 32,211 `<note>` elements, about 1,967,600 characters, in 4,986 chapters. By file: ANF01 4,841 notes, ANF02 3,641, ANF04 4,411, ANF05 5,436, ANF06 4,923, the third and fourth century volume 3,967, NPNF1-02 2,009, NPNF1-03 2,770, Incarnation 71, Consolation 75, Imitation 55, Anselm 12. Confessions and On Loving God have none.
  - Live confirms it: 1,838 Fathers passages contain a Roman-numeral scripture note such as "Matt. xxiv. 15.", and 284 contain "Literally, “". The plan's "at least 584" was a lower bound.
  - Stripping notes in the current build changes 7,415 of 10,232 Fathers and medieval passages. Because passages get shorter, split points move: 724 anchors disappear and 210 new ones appear.
  - `<scripRef>` elements in body text are the author's own citations or quotations and stay.
- **Changes:**
  - In `common.py`, add `_p_text_without_notes(p)`. Copy the element, remove every `note` descendant while keeping its `tail` text, then serialize and strip tags. Use it in `_direct_p_text` and `_extract_p_text`. Summa has no `<note>` elements, so `_chunk_summa` output is unchanged. Assert that in a test.
  - Record the removed notes in passage metadata as `editor_note_count` only. The note text is editor material under rule G and should not be stored for display.
  - Fixture: `<p>He said<note n="1" place="end">Matt. xxiv. 15.</note> this, and<note n="2">Literally, "to."</note> left.</p>` becomes "He said this, and left."
- **Acceptance checks:**
  - `test_direct_p_text_drops_notes_keeps_tail` and `test_extract_p_text_drops_notes` on the fixture.
  - Vendored check: zero passages in church fathers and medieval contain the text of any `<note>` whose text is 20 characters or longer. The check builds the note-text set from the sources, so it cannot pass by accident.
  - Coverage: characters kept equals the old build minus note text, within 1%. The PR reports both numbers.
  - The release report lists the anchor churn (expected about 724 removed and 210 added `/pN` anchors). The PR must say that none of the 50 retrievals and 0 bookmarks the plan found at risk sit on a removed anchor, or list the ones that do.
- **Production safety:** Datapipeline only. Document IDs do not change. Passage IDs change only where a split point moved. The 0.1c remap maps each removed `/pN` passage to the new passage that holds its first 200 characters.
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
  - `piece_reference(base, first_label, last_label, part, parts)` returns `"Genesis 1:14 to 1:31"` style ranges when labels exist. It returns `base + " (part 2 of 3)"` when they do not. Use a proper range separator in the real string; this file avoids dashes.
  - Apply it in `thml_doc.make_doc` (Fathers and medieval), the three papal adapters, `councils._Builder.add` and the Bible builder. The Bible gets verse units, so a split never cuts inside a verse and each piece cites its own verses.
  - Keep anchors exactly as today: `base`, or `base/pN` for pieces. Only `reference` changes, plus Bible piece boundaries, which now fall between verses.
  - 1.1 to 1.5 rewrite several of these adapters. They must keep calling `pack_units` and `piece_reference`, not a private copy.
  - Summa (1.7) and Catechism (1.6) adopt the helper in their own PRs.
- **Acceptance checks:**
  - `test_pack_units_never_splits_a_unit_under_cap`, `test_pack_units_keeps_every_character`, `test_piece_reference_range_and_part_forms`.
  - Vendored check: zero duplicate `(document_id, reference)` pairs in Bible, papal, Fathers and medieval. Councils may keep duplicates until 1.1 and 1.2 land. The check prints the count per collection.
  - Bible: every piece's reference range equals the first and last verse numbers found in its text.
- **Production safety:** References and some Bible split points change. Document IDs do not. Bible piece anchors (`book/ch/v-2`) can move; the remap maps by first verse.
- **Needs Carter:** choose the citation form for pieces without real units. Recommended: "(part 2 of 3)". The alternative is ThML printed page numbers from `<pb n=...>` ("ANF 1, pp. 45 to 46"), which are real but edition-specific.
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
- **Production safety:** Datapipeline only. Document IDs unchanged. Anchors `<doc>/<n>` keep their meaning, so bookmarks on existing sections stay correct and gain text. Churn the remap must handle:
  - About 76 footnote anchors (`<doc>/<n>-2`, `<doc>/<n>-3`) disappear. They hold note text; map them to nothing and tombstone them.
  - Sections that now split change from `<doc>/<n>` to `<doc>/<n>/p1`. The remap maps old to `/p1`.
  - `sacrosanctum-concilium/81-2` maps to `sacrosanctum-concilium/87`.
  - Gravissimum Educationis bucket chapters (`bucket-0`) become heading chapters. That is a chapter-key change only, and passage IDs stay.
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
- **Production safety:** Datapipeline only. Document ID `e33e591b-...` is unchanged: the title is unchanged, and the registry freezes it anyway. Every passage anchor changes. The remap maps each old passage to the new passage holding its first 200 characters. Old anchors with no match are tombstoned and listed in the release report.
- **Needs Carter:** nothing.
- **Out of scope:** the Roman Catechism of Trent (5.5).

### 1.2c. Councils 1 to 7 from Percival (NPNF2 vol. 14)

- **Type:** PR
- **Depends on:** 1.2a, 0.2 (source hash and rights entry for `npnf214`), R6 (edition check for the new source)
- **Goal:** Nicaea through Nicaea II come from a public-domain translation with clear provenance, and carry the councils' own texts: creeds, definitions, canons, anathemas and synodal letters. Nicaea stops being 4 passages.
- **Current state:**
  - Current build from papalencyclicals.net (Tanner): Nicaea 4 passages and 5,993 characters. Constantinople I 16 and 22,451. Ephesus 32 and 39,713. Chalcedon 19 and 44,215. Constantinople II 12 and 27,885. Constantinople III 5 and 11,042. Nicaea II 27 and 32,322.
  - The Nicaea file has 31,900 characters inside `<li>` elements the adapter never reads, which is where Tanner's canons are.
  - NPNF2-14 mixes council text with editor material: historical introductions, Excursus, "Notes" by Percival, the "Ancient Epitome" of each canon, and extracts from Zonaras, Balsamon and Aristenus. Its ThML is not vendored. The structure described here comes from the CCEL table of contents and is unverified until 1.2a opens the file.
- **Changes:**
  - Vendor `https://ccel.org/ccel/s/schaff/npnf214.xml` through `scripts/vendor_sources.py` into `sources/councils/npnf214.xml`, with URL, SHA-256, retrieval date and "Rights: Public Domain" from the file header recorded in the councils manifest.
  - Write `ingest/councils_percival.py` with a per-council allowlist of ThML div ids taken from the 1.2a inventory, for example Nicaea: Creed, Canons I to XX, Synodal Letter. Allowlist rather than denylist, so an unrecognised Excursus is dropped by default.
  - Within allowed divs, drop child divs or paragraphs titled "Ancient Epitome", "Notes", "Excursus" or anything 1.2a marks as editor material. Strip `<note>` through the 1.10b helper.
  - Anchors: `council-of-nicaea/canon/5`, `council-of-nicaea/creed`, `council-of-nicaea/synodal-letter`, and `council-of-chalcedon/definition`. Keep `canon/N` wherever the old build had it, so those passages keep their IDs.
  - `author` is the council's name. Keep the manifest's `year` and `council_number`.
  - Route councils 1 to 7 in `build_documents` to the new builder. The Tanner HTML files stay vendored until 1.2e lands, but no builder reads them.
- **Acceptance checks:**
  - `test_percival_allowlist_drops_epitome_and_notes`, `test_percival_canon_anchors`, on a synthetic ThML fixture.
  - Vendored checks: Nicaea yields 20 canons plus the Creed and the Synodal Letter. Constantinople I 7 canons (Percival prints 7). Ephesus 8 canons, Cyril's letters and the 12 anathemas. Chalcedon 30 canons and the Definition. Constantinople II the 14 anathemas. Constantinople III the Definition. Nicaea II 22 canons and the Definition. Adjust these counts to what 1.2a finds and say so in the PR.
  - No passage contains "Ancient Epitome", "Excursus" or "Zonaras".
  - The release report lists every old Tanner anchor and whether it mapped.
- **Production safety:** Document IDs are unchanged (`document_id("councils", council, council)` and registry-frozen). Passage anchors change except `canon/N`. Tanner text stays live until P4.
- **Needs Carter:** nothing, if 1.2a is approved.
- **Out of scope:** the Apostolic Canons (Fathers, 1.8c). Local councils printed in NPNF2-14 (Ancyra, Neocaesarea, Gangra, Antioch, Laodicea, Sardica, Carthage and others), which are not ecumenical and are not in the plan.

### 1.2d. Vatican I from Schaff's Creeds of Christendom vol. 2

- **Type:** PR
- **Depends on:** 1.2a, 0.2, R6
- **Goal:** Dei Filius and Pastor Aeternus are searchable in full, chapter and canon, in Manning's public-domain English. Today Vatican I is 9 passages and 6,053 characters.
- **Current state:**
  - The vendored Tanner page keeps 86,381 characters in `<li>` elements (653 of them), which the adapter ignores.
  - CCEL `creeds2` section v.ii.i is a two-column table per page: Latin in a `<td>` with `<span lang="LA">`, English in the other `<td>`. Sentences run across tables at page breaks ("...placed over the universal" continues in the next table). Schaff's footnotes are inline notes ("From a Brief of Pius VI..."), which are editor material. Verified on the CCEL HTML page on 29 Sep.
- **Changes:**
  - Vendor `creeds2.xml` with hash and rights line into `sources/councils/`.
  - `ingest/councils_schaff.py`: take only the Vatican Council section. From each two-cell row keep the cell without `lang="LA"`. Concatenate English cells across page tables before splitting paragraphs. Strip notes (1.10b helper) and page-break spans.
  - Structure: Dei Filius prologue, chapters 1 to 4, canons grouped by chapter. Pastor Aeternus prologue, chapters 1 to 4. Anchors: `first-vatican-council/dei-filius/chapter-3`, `first-vatican-council/dei-filius/canons-3/canon-2`, `first-vatican-council/pastor-aeternus/chapter-4`.
  - The Latin cells are not stored. Rule E makes English searchable, and the official Latin is available elsewhere.
- **Acceptance checks:**
  - `test_schaff_keeps_english_cell_only`, `test_schaff_joins_english_across_page_tables`, on a fixture with 2 tables and a mid-sentence page break.
  - Vendored checks: 4 chapters and 18 canons in Dei Filius, 4 chapters in Pastor Aeternus. Chapter 4 of Pastor Aeternus contains "is possessed of that infallibility". No passage has more than 5% Latin stopwords ("et", "est", "quae", "non").
- **Production safety:** Document ID unchanged. All 9 current passages change anchor. The remap maps old chapter passages to new ones by chapter title. Sessions 1 and 2 material that has no Schaff equivalent is tombstoned and listed in the gap register.
- **Needs Carter:** nothing.
- **Out of scope:** the rest of Schaff vol. 2 (the Creed of Pius IV, Ineffabilis Deus, the Syllabus).

### 1.2e. Councils 8 to 18 from Schroeder 1937

- **Type:** PR, one per council or per source group
- **Depends on:** 1.2a, 0.2 (renewal search recorded for Schroeder), 5.6c OCR tooling for the councils without a clean text
- **Goal:** Constantinople IV through Lateran V come from Schroeder's public-domain translation. Where Schroeder has no text, the gap register says so.
- **Current state:**
  - Current build (Tanner): Constantinople IV 26 passages, Lateran I 29, Lateran II 33, Lateran III 33, Lateran IV 105, Lyons I 44, Lyons II 44, Vienne 112, Constance 201, Basel-Ferrara-Florence 130, Lateran V 87. The generic builder also loses text inside lists in several of these (Lateran I has 22,306 characters in `<li>`).
  - Clean text exists only for Lateran I, II and IV on Fordham's Internet Medieval Sourcebook. On Wikisource, 27 of 677 pages are proofread. The rest is an Internet Archive scan (`DisciplinaryCouncils`). Source: `docs/research/2026-09-28-scan-only-works-text-sources.md`.
  - Schroeder prints commentary after each canon. That is rule G material.
- **Changes:**
  - 1.2e-1: Lateran I, II and IV from Fordham. Vendor the three pages with hash and a check of Fordham's terms. Parse canon by canon. Drop Schroeder's commentary, which Fordham reproduces in places. Anchors `first-lateran-council/canon/N`, as today where Tanner had the same number.
  - 1.2e-2 onward: the other 8 councils through the 5.6c pipeline: OCR, furniture strip, model correction under the 2% word-change limit, gate on the unrecognized-word rate and a 20-passage check against page images. Proofread Wikisource pages replace OCR where they exist.
  - Constantinople IV: Schroeder prints its 27 canons. Florence: whatever Schroeder prints; the doctrinal decrees go in the gap register.
- **Acceptance checks:** per council, the canon count Schroeder prints (from 1.2a), the 5.6c quality gate, and no commentary text. A gap row exists for every Tanner document without a Schroeder equivalent.
- **Production safety:** Document IDs unchanged. Tanner text stays live until P4.
- **Needs Carter:**
  - Decide what P4 publishes for a council whose Schroeder text is not ready. Options: publish the council with only what is ready, publish nothing for it, or hold the councils republish.
  - Florence would lose Laetentur caeli and the Decree for the Armenians in every option. The plan already accepts recording that gap.
- **Out of scope:** Trent (1.2b), Vatican I (1.2d), any translation of our own.

---

### 1.3a. Papal documents: one parser that keeps list text, drops endnotes and debris

- **Type:** PR
- **Depends on:** 1.10c
- **Goal:** Whole papal documents are readable. In Dominico Agro and Annus Qui Hunc gain their bodies. Endnotes stop appearing as walls of citations. Cards such as "PAUL VI" and "146" disappear. Quanta Cura (1864) cites real paragraphs.
- **Current state:**
  - `encyclicals.py`, `apostolic_exhortations.py` and `papal_documents.py` are the same 250-line file with different paths and collection names (verified by `diff`). A fix in one silently misses the other two.
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
- **Production safety:** Document IDs unchanged, because each wrapper keeps its collection in `document_id`. Anchor changes the remap must handle:
  - Note anchors such as `redemptor-hominis/1/p2` to `/p4` and `fratelli-tutti/287/p2` to `/p9` are tombstoned.
  - Heading anchors (`ineffabilis-deus/4`, `redemptoris-mater/1-2`) are tombstoned.
  - `quanta-cura-1864/1` changes meaning, from the endnote to the real first paragraph. The release report must flag it as "same ID, different content". Check it against bookmarks and retrievals before P4.
- **Needs Carter:** nothing.
- **Out of scope:** genre labels (1.3b). Merging the three collections (5.1b). Adding A New Hope for Lebanon and Ubicumque et Semper (5.4). Amoris Laetitia, the third unmanifested file, which no plan item covers yet. OCR-style typos in the Annus Qui Hunc source ("Wehave", "inor- der").

### 1.3b. Papal genre metadata

- **Type:** PR
- **Depends on:** 1.3a
- **Goal:** Each papal document says what it is: encyclical, apostolic exhortation, apostolic letter, apostolic constitution, bull, motu proprio or other. The genre filter (5.1a) then works, and cards stop calling Evangelii Gaudium an encyclical.
- **Current state:**
  - No papal manifest entry has a genre. The collection is the only signal.
  - Misfiled in encyclicals, per the plan: Evangelii Gaudium and Evangelii Nuntiandi (apostolic exhortations), Ineffabilis Deus and Munificentissimus Deus (apostolic constitution or bull), the Syllabus of Errors (an annexed list), and three Jubilee bulls. The plan does not name the three. Candidates from the manifest: Peregrinantes (1749), Salutis Nostrae (1774), Quod Hoc Ineunte (1824). Unverified.
  - Apostolica Constitutio (1749) should also be checked.
  - Papal documents mixes bulls (Unam Sanctam, Exsurge Domine, Sublimis Deus), apostolic letters (Salvifici Doloris, Mulieris Dignitatem, Ordinatio Sacerdotalis, Tertio Millennio Adveniente, Orientale Lumen, Dies Domini, Novo Millennio Ineunte, Rosarium Virginis Mariae, Misericordia et Misera, Patris Corde) and a motu proprio (Porta Fidei).
- **Changes:**
  - Add `genre` to every entry of the three manifests, set in `scripts/vendor_sources.py` so a re-vendor keeps it. Values: `encyclical`, `apostolic_exhortation`, `apostolic_letter`, `apostolic_constitution`, `bull`, `motu_proprio`, `list`, `other`.
  - Each value cites the document's own heading on vatican.va, or papalencyclicals.net where vatican.va has no English page. Record the citation in a tracked table `datapipeline/papal_genres.csv` (slug, genre, evidence URL). The manifests are gitignored, so the CSV is what reviewers read.
  - The builders copy `genre` into `Document.metadata["genre"]`.
  - Do not move documents between collections. Their IDs include the collection, and 5.1b merges the collections anyway.
- **Acceptance checks:** `test_every_papal_manifest_entry_has_genre`, which fails on a missing or unknown value. A vendored check prints a count per genre and per collection. The PR lists each document whose genre disagrees with its current collection.
- **Production safety:** Metadata only. No ID or anchor change. The API ignores unknown metadata keys.
- **Needs Carter:** confirm the three Jubilee bulls and whether Ineffabilis Deus and Munificentissimus Deus are labelled "apostolic constitution" (their own form) or "bull".
- **Out of scope:** the `genre` column and filter (2.2a, 5.1a). The collection merge (5.1b).

---

### R3. Esther: what the WEB-C text contains and how it maps to Nova Vulgata

- **Type:** research
- **Depends on:** none
- **Goal:** Before 1.4a restores the missing Esther verses, we know exactly which text is in the source, where each Greek addition sits, and how its verse numbers relate to the Nova Vulgata and to Church citations.
- **Current state:**
  - `sources/bible/eng-web-c_usfm/43-ESGeng-web-c.usfm` has 205 verses in 10 chapters: 22, 23, 15, 46, 14, 14, 10, 17, 30, 14.
  - Its introduction claims the 5 additions are merged "as extensions at the beginning of 1:1 and after 3:13, 4:17, 8:12, and 10:3". The file does not do that for all of them:
    - Addition A is inside 1:1, in brackets.
    - Addition B follows 3:13 inside the same verse.
    - Addition C is numbered as new verses 4:18 to 4:47.
    - Addition E follows 8:13 per its footnote, not 8:12.
    - Addition F is numbered 10:4 to 10:14.
  - The pericope file skips 4:18 to 4:47 and 10:4 to 10:14, which is 41 of the 244 missing verses.
  - The intro counts 5 additions. The standard count is 6, A to F. Addition D, the Esther-before-the-king scene, is probably the long 5:1. Unverified.
  - The Nova Vulgata prints the additions with lettered verses, such as 4:17a to 4:17z. Unverified here.
- **Changes:** Write `docs/research/esther-web-c-vs-nova-vulgata.md` with:
  - for each addition A to F, its WEB-C verse range and NV range
  - whether any Greek text in WEB-C has no counterpart in NV, or the reverse
  - how the Catechism and the Lectionary cite Esther's additions, with 2 or 3 examples
  - a recommendation for 1.4a: keep WEB-C numbers with an NV alias in metadata, or renumber
  - which of the plan's Esther claims (the handoff doc's list) hold
- **Acceptance checks:** every claim cites the USFM line or an NV page on vatican.va. Carter closes it.
- **Production safety:** No code.
- **Needs Carter:** the numbering recommendation.
- **Out of scope:** Daniel's additions, which follow NV-compatible numbering in WEB-C already (3:24 to 90, chapters 13 and 14).

### 1.4a. Bible: publish every verse and rename Song of Songs

- **Type:** PR
- **Depends on:** R3, 1.10c
- **Goal:** Every verse in the WEB-C source is in some passage. Susanna, Bel and the Dragon, the Song of the Three and the Esther additions become findable. The book is called Song of Songs.
- **Current state:**
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
  - Label such a group from a small tracked table `datapipeline/bible_extra_pericopes.csv` (book, start, end, title). Seed it with "Prayer of Azariah and Song of the Three" (Daniel 3:24 to 90), "Susanna" (13), "Bel and the Dragon" (14) and the Esther additions per R3.
  - Daniel 3: replace the KJV ranges for chapter 3 with WEB-C-native ranges in the same CSV, so the chapter reads in order and cites correctly.
  - Rename to "Song of Songs" in both tables. The registry (2.1) keeps document ID `9df0b246-...` for the renamed book. Build anchors from a registry-supplied book slug that stays `song-of-solomon`, so no passage ID changes. The title shown is "Song of Songs".
  - Delete the dead stanza code and its tests, or move Sirach to it in 1.4c. Do not leave both.
  - Add a completeness assertion inside `build_documents`: the set of `(chapter, verse)` in passages equals the set in the USFM, excluding verses whose text is empty (24 in the current source, such as Sirach 1:5 and 1:7). If they differ, raise.
- **Acceptance checks:**
  - `test_every_usfm_verse_lands_in_a_passage` (synthetic USFM with a verse outside all pericopes).
  - `test_extra_pericope_labels_apply`.
  - `test_song_of_songs_title_keeps_frozen_id_and_anchor_slug`.
  - Vendored check: 0 missing verses in 73 books. Daniel has 14 chapters with 21, 49, 97, 37, 31, 28, 28, 27, 27, 21, 45, 13, 64 and 42 verses.
- **Production safety:** Document IDs unchanged, including Song of Songs through the registry. New passages for the restored verses. Changed passages: Daniel 3 and the pericopes bordering each gap. The remap maps each old Daniel 3 passage to the new passage holding its first verse by WEB-C number.
- **Needs Carter:** confirm keeping `song-of-solomon` in anchors. The alternative renames anchors and changes 9 passage IDs, which the remap can handle, but gains nothing a user can see.
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
  - Passage references, chapter keys and anchors use the target numbers. Metadata keeps `source_ref` in WEB-C numbers.
  - Emit `renumbered_refs.json` in the release artifacts: old anchor, new anchor, for every moved verse range. The remap consumes it.
- **Acceptance checks:** `test_versification_moves_joel_2_28_to_3_1`, `test_versification_moves_malachi_4_to_3_19`. Vendored: Joel has 4 chapters (20, 27, 5, 21 verses), Malachi 3 (14, 17, 24).
- **Production safety:** This is the one place in this file where an anchor survives with a different meaning. `joel/3/1` today is KJV Joel 3:1 (the judgment of the nations); after the change it is the Spirit poured out. Passage IDs are UUIDv5 of document and anchor, so the same ID would silently point at different text. Requirements for 4.1a:
  - Rewrite bookmarks, retrievals and guest retrievals from old IDs to new IDs using `renumbered_refs.json` before the new rows go live.
  - Treat a reused ID whose content differs as a move, not an update.
  - The 0.1c release report must list every "same ID, different content" pair, and the PR states the counts: 3 or so Joel passages and 1 or 2 Malachi passages.
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
- **Production safety:** Each chapter's first passage keeps `book/ch/1`. The old `book/ch/1-2` pieces are replaced by new first-verse anchors. The remap maps each old passage to the new passage holding its first verse.
- **Needs Carter:** whether to take pericope titles from Douay-Rheims summaries or ship without titles. Recommended: without, for now.
- **Out of scope:** Psalms, which already get one passage per psalm.

---

### R2. Verify canons 296, 360, 361 and 948 against iuscangreg.it

- **Type:** research
- **Depends on:** none
- **Goal:** Before 1.5b swaps in current text, each canon the plan flagged has a verified current wording and a cited amending act.
- **Current state:**
  - The vendored vatican.va pages give canon 295 in its pre-2023 form, so the source cannot produce the current text. That was confirmed on 28 Sep.
  - 296, 360, 361 and 948 are unverified.
  - The plan names iuscangreg.it (the Pontifical Gregorian University canon law faculty's register) as the source, checked against the amending documents on vatican.va.
- **Changes:** For each of 295, 296, 360, 361 and 948, record in `docs/research/canon-amendments.md`:
  - the current text per iuscangreg.it
  - the amending act, its date and its vatican.va URL
  - whether an English text of the act exists on vatican.va, or only Latin or Italian
  - whether the vendored text differs, and how
- **Acceptance checks:** every row has both sources, or says why one is missing. Carter closes it.
- **Production safety:** No code.
- **Needs Carter:** approve extending R2 to find the English source, official or L'Osservatore Romano, for the Latin-only canons 111, 112, 535 §2, 579, 695, 700 and 868 §1 2°. 1.5b needs that answer too.
- **Out of scope:** canons outside the list unless the check finds a new amendment. List any such finding for Carter rather than fixing it.

### 1.5a. Canon law parser: split glued canons, find missing ones, keep new text, drop footers

- **Type:** PR
- **Depends on:** 1.10a
- **Goal:** "Canon 112" finds canon 112. Every canon from 1 to 1752 exists once, with the text the source marks as current. Page footers are gone. Amended canons carry an "amended" flag for the badge.
- **Current state:**
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
  - Versions. Track the page region. Everything from an "[Earlier version]" or "[Original version]" line to the next canon heading that is not inside such a block is superseded. Keep those texts in metadata `superseded_text` and never as the canon's content. When a canon number appears twice, prefer the marked version, then the one outside a superseded block. Raise if both candidates are unmarked and outside such blocks.
  - Footer. Cut a canon's text at "(n: indicates", "For Can.", "[Earlier version]" or "[Original version", whichever comes first, and at the Italian legend "Indica che il testo".
  - Book VI: strip a leading U+2014 dash and following space from canon text.
  - Canon 700: drop a leading line that begins "Apostolic Letter issued".
  - Amended flag: `metadata["amended"] = True` and `metadata["amended_by"]`, the linked act's title and URL from the page's "Cf." line, for every canon with the marker.
  - Keep today's `can/N` anchors and `Can. N` references.
- **Acceptance checks:**
  - Synthetic fixtures in `tests/test_canon_law.py`: `test_canon_glued_after_br_is_split`, `test_marker_before_can_is_recognised`, `test_earlier_version_block_is_not_current`, `test_bold_canon_outside_p_is_found`, `test_footer_legend_is_cut`, `test_book_vi_leading_dash_removed`, `test_amended_flag_set_from_marker`.
  - Vendored checks:
    - Canon numbers are exactly 1 to 1752, each once.
    - Canon 686 §1 contains "five years".
    - Canon 265 contains "public clerical association". Canon 266 exists and starts "§1. Through the reception of the diaconate".
    - Canons 1308 and 1310 carry the post-2022 text: 1308 §1 names the diocesan bishop, not the Apostolic See.
    - Zero canons contain "Earlier version", "Original version", "indicates that" or "For Can.". Zero start with "n" followed by "§" or a capital letter, or with a U+2014 dash.
    - The amended list printed in the PR equals the marker list.
- **Production safety:** One document, ID `document_id("canon-law")`, unchanged. Anchors `can/N` unchanged for 1,747 canons. 5 new passages. About 25 contents change. The API shows `metadata` it already reads. The badge itself is 2.4b.
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
    - 695 and 700 in full.
    - 535 §2 and 868 §1 2° only. Live 868 contains "... parentibus.§2."
  - The plan's rule: canons 111, 112, 535 and 868 show the L'Osservatore Romano English, labelled unofficial, with the Latin as the official text. For the others, rule E applies if no English exists: the reader keeps the Latin with a note, and search excludes it.
- **Changes:**
  - Add a vendored override file `sources/canon-law/overrides.json`: canon, field (`content` or a paragraph such as "§2"), text, language, status (`official`, `unofficial_english`), source title, source URL, retrieval date, SHA-256 of the fetched page. Vendor it through `vendor_sources.py`, so it stays out of the public repo like the pages. A tracked `datapipeline/canon_overrides_index.csv` lists canon, status and source URL without the text, for review.
  - `build_documents` applies overrides after parsing. For `unofficial_english`, the English goes in `content` and the Latin in `metadata["official_latin"]`, with `metadata["text_status"] = "unofficial_english"`. For canons with no English, keep the Latin in `content` and set `metadata["searchable"] = False` and `metadata["language"] = "la"`. The 2.2b filter excludes only explicit `false`, so it will honour this. Until 2.2b ships nothing reads the flag, and that is fine because nothing publishes before P4.
  - Canon 295, and any of 296, 360, 361 and 948 that R2 finds amended, take the R2 text with `amended_by` set.
- **Acceptance checks:**
  - `test_override_replaces_content_and_keeps_latin`, `test_latin_without_english_is_not_searchable`, `test_override_file_hash_mismatch_fails`.
  - Vendored: canons 111, 112, 535 and 868 contain no Latin stopword run of 5 or more words. 295 matches R2's text. The PR lists every override with its source.
- **Production safety:** Same document and anchors. Content changes for 7 to 12 canons. The `searchable` flag is metadata until 2.2b.
- **Needs Carter:** approve the English sources R2 finds, and the label wording for unofficial English. Suggested: "Unofficial English translation (L'Osservatore Romano). The Latin text is official."
- **Out of scope:** the Eastern code (blocked on licence). Universi Dominici Gregis and other universal law (5.4).
