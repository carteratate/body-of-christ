# Corpus review brief

**Your reviewer name.** Two reviewers run this same brief independently and at the same time, in the same checkout: `opus` (Claude Opus 5.5) and `sol` (GPT-6.1 Sol). Use the name of the model you are as `<reviewer>` wherever this brief says `<reviewer>`. Do not read, open or search for the other reviewer's report or scratch folder (`docs/research/2026-10-06-corpus-review-*.md`, `datapipeline/releases/local/review-*/`) until your own report is finished: Carter compares the two, so they must be independent.

You are reviewing the corpus of TheoCorpus, a Catholic theology search and reading app, before it is fixed and republished. Carter Tate, who owns the project, wants this to be the last time anyone has to open up the existing corpus. After the planned cleanup ships, every passage that is live today should be either correct or deliberately removed, and nothing should be left that degrades search, misleads a reader, or breaks a link.

Your job is to find everything wrong with the corpus that the plan does not already handle. Be exhaustive and pedantic. Assume every collection has defects nobody has noticed. Check every claim you make against the data. A short list of verified problems is worth more than a long list of guesses, but stopping early is the bigger risk: Carter would rather triage forty real findings than miss the one that ships.

Work date: from 6 October 2026. Repo: `/Users/cartertate/repos/body-of-christ` (branch `master`). Use `python3`.

---

## 1. What TheoCorpus is for

TheoCorpus (production: theo-corpus.com) lets a person ask a question in plain English and get back the passages of the Catholic tradition that answer it: Scripture, the Catechism, canon law, councils, popes, the Church Fathers, medieval writers and Aquinas's Summa. Each passage comes with a short explanation of why it answers the question. The person can then open the passage in a reader to see it in its document, save it, and come back to it later.

The promise, from the About page, is to bring two thousand years of the Church's conversations "together into one place" so a reader can "explore the Catholic tradition through the people who built, defended, and passed down the fullness of the faith". Users include Catholics, students, catechists, clergy and the curious. They trust that what they read is the actual text of an authoritative or orthodox source, correctly attributed. A passage that puts a heretic's words, an editor's note or an objection Aquinas refutes in the mouth of a saint or pope is a trust failure, not a cosmetic one.

The corpus today: 54,568 live passages in 421 documents, across 10 collections (`bible`, `catechism`, `canon-law`, `councils`, `encyclicals`, `apostolic-exhortations`, `papal-documents`, `church-fathers`, `medieval`, `summa`). The master build produces 54,778.

Read these first:
- `CLAUDE.md`: architecture, the data model, the search pipeline, the routes, focused search.
- `CONTEXT.md`: the domain vocabulary (Passage, Source adapter, Reader store, Search index, My Passages, Study).
- `docs/2026-09-28-corpus-cleanup-plan.md`: the cleanup plan. Read all of it: the Inclusion rules A to H (what may be in the corpus at all), the Decision log, the "Verified corpus problems" section, and D1 to D11.
- `docs/corpus-cleanup/README.md` and the five spec files in `docs/corpus-cleanup/` (P0, P1a, P1b, P2-P3, P4-P5): every planned fix, item by item.
- `docs/corpus-cleanup/NEEDS-CARTER.md`: what is still waiting on Carter.

## 2. Every job the corpus does

A defect matters if it breaks any of these. Read the code each one names before you judge a defect against it.

1. **Semantic search.** Each passage is a Qdrant point in the collection `chunks` (1,536-dimension OpenAI `text-embedding-3-large` vectors). The embedded text is not just the passage: it is `"<author> — <title>, <chapter_label>"` plus the passage plus some neighbouring passages, per collection (`datapipeline/stages/embed.py`, `settings.overlap_for`). The payload stored for display is the clean passage. Search filters points by the payload field `collection` (`services/api/app/rag/steps/retrieve_vector.py`). So a wrong title, author or chapter label, or a wrong neighbour, changes what a passage is found for.
2. **Lexical search.** Postgres full-text search over `chunks.search_vector`, which is generated as `to_tsvector('english', content)` (migration 0004), queried with `plainto_tsquery('english', …)` per collection (`retrieve_fts.py`). Non-English text, glued words, markup, footnote numbers and hyphenation all degrade it silently.
3. **Fusion and reranking.** Vector and lexical candidates are merged by reciprocal rank fusion, reranked by Cohere per collection, then ranked by one LLM call over "cards" built from the passage, its reference, title, author and role (`rerank_docs.py`, `llm_rerank/`, `passage_role.py`). The role comes from `unit_label`; for the Summa it says whether a passage is an objection Aquinas refutes.
4. **Explanations.** An LLM writes the prose the user reads about each result, from the passage text and its role (`steps/explain.py`). A passage that is a fragment, mislabelled or mostly notes produces a misleading explanation.
5. **Result selection.** Deduplication caps results per source, where a source is the reader chapter for `summa`, `catechism`, `canon-law` and `bible` (`services/api/app/rag/dedup.py`, `steps/dedup.py`). There is also a guaranteed slot per selected collection, the quota cap, and a minimum floor. Wrong `chapter_key` values change what counts as one source.
6. **Summa stitching.** An objection is shown with Aquinas's answer, and a reply with the objection it answers. The results are found by scanning the passages around them within one `chapter_key`, by `unit_label` and position (`steps/stitch.py`, `steps/fetch_context.py`; their docstrings record known irregularities).
7. **HyDE.** Before retrieval, an LLM writes hypothetical passages per collection, and for the Bible it picks genres of books (`steps/hyde_s25.py`, `hyde_luna.py`). Book-to-genre mapping and collection descriptions depend on the corpus being what the prompts assume.
8. **Result cards and deep links.** A card shows the reference, title, author, collection and content, and links to `/reader/<docId>?anchor=` or `?chapter=` (`apps/web/src/components/search/ChunkCard.tsx`). Bible content carries inline verse markers such as `{{v:N}}` that the frontend parses.
9. **The reader.** `/reader/<docId>` shows a document's chapter list from the precomputed outline (`documents.chunk_count`, `document_chapters`, migrations 0037 and 0038) and one chapter at a time (`services/api/app/routes/documents.py`). Reading position is saved per document as `chapter_key` and `anchor` (`reading_progress`).
10. **The sources page.** `/sources` lists every document with title, author, year, translation and passage count (`routes/sources.py`).
11. **Saved user data.** Search history (`searches`, `retrievals`), bookmarks ("My Passages"), guest results and relevance labels all store passage IDs, and cascade on delete. Restoring a past search re-reads those passages. The planned Studies feature will store snapshots of passages.
12. **Discover and the retrieval lab.** `/v1/evaluate` scores collections for a question. `/search/compare` and the gold sets in `docs/eval/` reference passage IDs to measure retrieval quality.
13. **Trust and credit.** Attribution (author, certainty labels), the planned source credit line on opened passages, and the About page's description of each collection.

## 3. What is already known: do not report these as new

The cleanup plan and its specs already cover a great deal. Before you report a finding, check that it is not already there. If a known issue is worse than its spec says (more passages, another cause, another collection), report that as a finding of its own, labelled "known, underestimated".

Already planned, in outline:
- **Phase 0 checks, merged:**
  - **Coverage (0.1a):** compares how much source body text reaches a passage, per file, and checks numbered sequences for gaps and duplicates (verses, Catechism paragraphs, canons, Summa articles, paragraph numbers, ThML chapters).
  - **Health rules (0.1b):** blank or debris passages, broken positions or anchors, and counts of short fragments, footer and note leakage, duplicated text, repeated references, joined paragraphs, non-English text and anchor suffixes.
  - **Release report (0.1c):** maps every live passage to a build passage and fails when an ID would show different text.

  Their known failures are in `datapipeline/checks/known_defects.json`, each with the item that fixes it.
- **Identity and registries (2.1, not built yet):** frozen document and passage IDs, anchors built from source structure, and a removal registry.
- **Phase 1 adapter fixes:**
  - Vatican II continuation paragraphs.
  - Council sources replaced with public-domain translations.
  - Papal list markup.
  - Canon law parsing and current text.
  - Missing Bible verses, Esther, and Nova Vulgata numbering.
  - Catechism, the Summa prologues and debris.
  - Church Fathers: editorial text (rule G), translators' notes, Ignatian recensions, labels and greetings.
  - Medieval texts and split-piece citations.
- **Phase 2:** schema for document facts, tombstones and redirects, the stage-then-apply writer, the Qdrant alias, and search flags.
- **Phase 3:** non-English text out of search, labels and notes, and removals under rules A to C.
- **Phase 4:** the republish.

Read the specs for the exact scope; the outline above is not enough to decide that something is covered.

Earlier findings live in:
- `docs/research/2026-09-28-corpus-health-and-retrieval-audit.md`
- `docs/research/2026-09-28-question-set-corpus-gap-audit.md`
- `docs/research/2026-09-28-rule-1-authorship-verification.md`
- `docs/research/2026-10-04-*.md`
- `docs/research/R1` to `R6`
- `docs/2026-06-10-codebase-issue-inventory.md`
- `docs/2026-08-20-retrieval-integrity-work.md`
- `docs/2026-08-22-summa-reingest-scope.md`
- the long docstring of `datapipeline/scripts/reconcile_qdrant_payloads.py`, which records 86 Qdrant points embedded from text unrelated to their Postgres row, and a stale Summa `"Objection 1"` prefix still in Qdrant payloads.

What the existing checks cannot see is your main hunting ground:
- the search index;
- the relation between the search index and the reader store;
- metadata (titles, authors, years, translations, labels, references);
- duplicates across documents and collections;
- text quality inside passages that otherwise pass the rules;
- whether a passage makes sense on its own;
- whether the reader shows a document correctly.

## 4. Your inputs and what you may touch

**The live reader store, as a snapshot.** `datapipeline/releases/snapshots/2026-10-06/` is a read-only export of production Postgres taken on 6 October 2026:
- `passages.jsonl.gz`: every chunk with `id, document_id, collection, title, author, anchor, chapter_key, chapter_label, reference, unit_label, position, content`.
- `documents.jsonl`: `id, collection, title, author, year, translation, chunk_count, metadata`.
- `references.json`: how many saved user rows point at each passage. Counts only.
- `snapshot.json`: row counts and hashes.

`checks.health.load_snapshot` reads it. The snapshot lacks per-chunk `metadata` and `annotation`; `annotation` is empty in every live row. To test full-text behaviour, load the snapshot into a throwaway local Postgres and build the same `to_tsvector('english', content)`. `datapipeline/tests/test_reader_writer_outline.py` shows how to start one.

**The master build.** Run every adapter in `datapipeline/publication.SOURCE_ADAPTERS` against the vendored sources in `datapipeline/sources/` (gitignored, present on this Mac). This touches no store. It needs placeholder environment variables:

```bash
cd datapipeline
DATABASE_URL=postgresql://x:x@localhost/x OPENAI_API_KEY=u QDRANT_URL=http://localhost QDRANT_API_KEY=u ANTHROPIC_API_KEY=u python3 -c "from publication import SOURCE_ADAPTERS; ..."
```

**The existing reports.** Run them against the build and the snapshot:
- `python3 -m checks.report --collection all`
- `python3 -m checks.health --collection all`, then `--from-snapshot releases/snapshots/2026-10-06` into the same `--out`
- `python3 -m release.report --snapshot releases/snapshots/2026-10-06 --collection all`

Use the same placeholder variables, and give each report `--out datapipeline/releases/local/review-<reviewer>/<name>` so the two reviewers never write into one folder. `datapipeline/releases/local/` is gitignored.

**The production Qdrant index: read only. Carter approved this on 6 October 2026.** Use the real `QDRANT_URL` and `QDRANT_API_KEY` from `datapipeline/.env` through `qdrant_client`.
- Allowed: listing collections and aliases, `get_collection`, `count`, `scroll`, `retrieve`, and `query_points` using an existing point's own vector (for near-duplicate and neighbour checks).
- Forbidden: anything that writes or changes the cluster, including `upsert`, `delete`, `set_payload`, `overwrite_payload`, `delete_payload`, `update_vectors`, creating or deleting collections, indexes, aliases or snapshots, and changing collection settings.
- Scroll in pages, with `with_vectors` only when you need the vectors.
- Expect `chunks` plus the V5 `facets` and `questions` collections. Find out what each holds and whether it is used.

**Not approved: ask Carter first.**
- **Production Postgres:** use the snapshot. If a finding needs a live read, write the exact read-only SELECT into your report and ask.
- **Paid API calls** (OpenAI, Anthropic, Cohere, the production search endpoint): no embedding of new queries, no running the search pipeline. If a test would need one, describe it and estimate its cost.
- **Changes to the repo:** do not change code, specs, `known_defects.json` or any tracked file. You may write scratch scripts and outputs only under `datapipeline/releases/local/review-<reviewer>/` or a temporary directory of your own.
- **Outside contact:** no pushes, issues, PR comments or messages.

**Copyright and privacy.**
- **In-copyright text:** much of the corpus is Vatican text (papal documents, Vatican II, the Catechism, the canon law English). Your report file goes into a public repo, so identify passages by ID, document, anchor and reference, and quote at most a few words where a quote is the evidence.
- **Rights analysis:** never put an opinion about rights or licensing in a file; say it in your chat reply to Carter. Rights research is private.
- **User data:** `references.json` holds counts only. Do not try to learn anything about individual users.

## 5. What to hunt for

Treat this as a starting list, not a boundary. For each collection and document, ask how each job in section 2 could go wrong.

**The search index against the reader store**
- Every Qdrant point against every live passage: points with no passage (orphans, which crashed search before), passages with no point, and points whose payload `content`, `reference`, `anchor`, `chapter_key`, `chapter_label`, `unit_label`, `document_title`, `author` or `collection` differs from the snapshot.
- Points whose vector was embedded from different text. Compare each vector with those of its own neighbours and with the text it should hold. Use cosine to its neighbouring passages, and near-duplicate search with the point's own vector; this needs no new embeddings.
- Duplicate or near-duplicate vectors pointing at different text, and identical text with distant vectors.
- Payload fields with the wrong type, missing values or stale values. Which payload indexes exist, and whether the `collection` filter is indexed.
- What the `facets` and `questions` collections hold, whether search reads them, and whether they hold orphans.

**Metadata and labels**
- Titles, authors and years per document: wrong, inconsistent across documents of one author, trailing punctuation, "Anonymous" where a name is known, a translator credited as author, an author credited as translator, empty years where the source gives one.
- References that do not match the content they cite: an off-by-one verse range, a paragraph number belonging to the next passage, a Summa reference naming another article.
- Chapter labels and chapter keys: labels that are page furniture, numbers or debris; keys that group unrelated units or split one unit; reader chapter order that does not follow the source.
- `unit_label` values the Summa stitching depends on: missing, wrong, or out of order (an objection after a reply, a reply number with no matching objection), and articles with two determinations. The `fetch_context.py` docstring names some.
- Documents whose `chunk_count` or outline disagrees with their passages.

**Text quality inside passages**
- Mojibake, HTML entities and tags, escaped characters, stray markup, `[Page N]` and page headers, OCR errors, and soft hyphens or line-break hyphenation.
- Verse markers, footnote numbers or note callers glued to words; broken `{{v:N}}` markers (unbalanced, duplicated, out of order).
- Sentences cut in the middle at a passage boundary. Passages that start mid-sentence with no preceding piece.
- Text belonging to another unit: the next canon's heading, the previous verse, a footnote from another page.
- Editorial or apparatus text that rule G removes but that the 0.1a list (`checks/editorial_divs.json`) and the specs miss: headings like "Chapter Summary", "Argument", or translator glosses in brackets.
- Passages whose text is mostly citations, lists of references, or tables.

**Whether each passage can be found and is worth finding**
- The distribution of passage lengths per collection: passages too long to embed well, and passages too short to mean anything.
- Passages whose meaning depends on something not in them: bare replies, "the same", "as above", lists of questions.
- Passages that will mislead when shown alone: a heretic quoted in a refutation, a pagan argument in an apologetic work, an interlocutor in a dialogue, an objection outside the Summa. Say whether `unit_label` or anything else tells the models so.
- Collections where full-text search can match nothing for a common query, because of non-English text, archaic spelling (Douay-style forms, "thee"), or tokenisation problems.

**Duplicates and overlaps**
- The same text in two documents or two collections: a council text also inside an encyclical, a Scripture quotation as its own passage, a Father's work in two volumes, the Catechism quoting canon law.
- Repeated passages within one document beyond what 0.1b counts.
- Say whether each duplicate harms results, for example by taking two of a user's few result slots or splitting the guaranteed collection slot.

**The reader and links**
- A document whose reader view would show chapters out of order, an empty chapter, or one huge chapter.
- Anchors that collide, change meaning between builds, or contain characters that break URLs.
- Saved user rows (`references.json`) pointing at passages that are blank, debris or editorial, which the republish would retire. Count them per kind.

**Corpus scope and trust**
- Works or passages that inclusion rules A to H would remove but the plan's lists do not name.
- Documents in the wrong collection, or whose About-page description does not match what is there.
- Anything that would embarrass TheoCorpus in front of a well-read Catholic reader.

**Things that could go wrong later**
- Defects that no current check would catch if a later adapter change brought them back. For each class of defect you find, propose the automated check, with an id in the style of `checks/known_defects.json`, that would keep it fixed.
- Places where the planned fixes look incomplete or where two specs could undo each other's work.
- Assumptions in the search pipeline (the Summa stitching, dedup by chapter, Bible genres, the collection guarantee) that the planned corpus changes would break.

## 6. How to work

0. Work alone, in this one thread. Do not start subagents, parallel reviewers or research helpers: each one is a separate session that spends the same usage allowance, and an earlier attempt at this brief that split the work three ways used up the allowance in under two minutes and produced nothing. Prefer scripts that answer many questions in one run over many small reads, and do not paste large outputs into the conversation; write them to files and read the parts you need.
1. Read section 1's files and the code paths in section 2 before looking at data, so you know what each field is used for.
2. Build the master corpus once and load the snapshot once, and keep them in memory or a pickle under `datapipeline/releases/local/review-<reviewer>/` for your analyses.
3. Work collection by collection, then across collections, then the search index.
4. For every finding:
   - Count every affected passage.
   - Look at real examples, at least three where there are three, and read them yourself.
   - Check a sample of your count by hand before trusting it.
   - Say whether it appears in live, in the master build, or both, because the build is what will ship.
5. When something looks wrong, try to prove it is fine before reporting it. Report what survives.
6. Keep going past the obvious. When a class of defect turns up in one collection, look for it in all ten.
7. Save as you go. This run may be paused by a usage limit and resumed with "continue". Add each verified finding to the report file (section 7) as soon as it is verified, keep the coverage map current, and keep a short "Next" list at the end of the file naming what you have not checked yet. On resuming, read that file first and carry on from "Next" rather than starting over.

## 7. What to deliver

Write one file, `docs/research/2026-10-06-corpus-review-<reviewer>.md`, and do not commit it. Carter reviews it first.

It has these parts:

1. **Summary.** In plain English for Carter: the most serious problems, how many passages and users they touch, and whether the planned cleanup is enough for the corpus never to need reopening. Define any technical term the first time you use it.
2. **Findings**, most serious first. Each has:
   - an id (A-001…);
   - a title;
   - a severity: `critical` (wrong or misleading content in front of users, or search or links broken), `high` (degrades retrieval or the reader for many passages), `medium` or `low`;
   - the collections and the number of passages affected, in live and in the build;
   - the evidence: passage IDs, anchors, references, counts, and the command or query that reproduces it;
   - what a user would see;
   - its status: `new`, `known, underestimated` (naming the item) or `known` (name it, and only include it when the spec is wrong about it);
   - a suggested owner: an existing item such as `1.8a`, or "new item";
   - the check that would catch it in future.
3. **Coverage map.** Every area of section 5 and every collection, with what you checked and found clean. Silence is not evidence: Carter needs to know what was examined.
4. **Questions for Carter.** Each leads with the literal question, then the options and their effects, then your recommendation.
5. **Reproduction.** The scripts you wrote (paths under `datapipeline/releases/local/review-<reviewer>/`) and how long each took.

In your chat reply, give the summary, the number of findings by severity, any rights concerns, and anything you could not check and why.
