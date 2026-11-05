# What Carter needs to approve, decide or supply

29 September 2026. This file gathers every "Needs Carter" entry in the five spec files of `docs/corpus-cleanup/`, with duplicates merged, into one list. Section A holds the approvals for steps that touch live data or production systems, section B the decisions, and section C the things only Carter can supply. Each section runs in phase order.

Each entry starts with the spec item it comes from, so the details can be found there, followed by a tag that says when the answer is needed:

- **[Phase 0]** means the answer is needed before or during Phase 0, the checks and safety work that comes first.
- **[Phase 1]** means a Phase 1 adapter PR waits for it.
- Later tags name the phase that waits for it.

Where a spec recommends an answer, the entry gives it. Where it gives none, the entry says so.

When Carter answers an entry, the implementer adds a line under it, `Answered <YYYY-MM-DD>: <the answer>`, in the same change set as the work (`README.md`, step 1.4). An entry with that line is closed. New entries that implementation uncovers are added here and to their spec.

## Terms used below

- **Live data** is the production Supabase database (project hvmgffvimqgiejmxwhwq) and the production Qdrant search index. Users see both.
- **Qdrant** is the service that stores the numeric "embeddings" behind meaning-based search. An **embedding** is a list of numbers OpenAI computes for a passage, paid per token (a token is about three quarters of a word).
- **Publish lock** is a file in the repo, `PUBLISH_LOCK.json`, that blocks every datapipeline command from writing to the live corpus or search index unless a reviewed PR has added an entry naming the collection and the release. Steps done by hand (a migration, creating a Qdrant alias or index, `VACUUM FULL`, deletions after a rollback window) are outside the lock and approved one by one in section A. A **release** is a named publish, such as `republish-2026-10`.
- **Staging** is a separate copy of the corpus built inside the production database, which users never see, so a new version can be checked before it replaces the old one in one step (the **apply**).
- **Rollback window** is the period after an apply during which one command can put the old corpus back.
- **Tombstone** is the short notice a user sees in place of a passage that was removed, giving the reason and the Church act if there is one. Removed passages are hidden, never deleted, so saved searches and bookmarks keep working.
- **pg_dump** is a full copy of the production database, made so a rehearsal can run on Carter's Mac. It contains user data, stays on his Mac, and is deleted afterwards.
- **Migration** is a change to the database's structure (new columns or tables). These specs only add things; none removes data.
- **Registry** is a tracked file in the repo that freezes each document's and passage's ID, so links and bookmarks survive fixes.
- **Supabase Pro** is the paid plan. The organization is on it (checked 30 Oct 2026, 0.6), so the Free plan's 500 MB read-only limit, which these specs once planned around, does not apply.
- **Qdrant Free** is the vector database's free plan, which the production cluster runs on: 1 GiB of RAM, 4 GiB of disk, and no backups.

---

## A. Approvals of steps that touch live data, production systems or the public repo

### Phase 0

- **Plan, all phases** [Phase 0]. Approve opening the GitHub issues from these specs, one parent per phase. Every push, issue and PR on the public repo needs his yes first.
- **0.0** [Phase 0]. Approve the first push and PR, which adds automated tests on GitHub and a PR template. After it merges, turn on branch protection for `master` in GitHub settings so the three test jobs must pass (only Carter can change that setting).
- **0.4** [Phase 0]. Approve the publish-lock PR. It must merge before any Phase 1 PR.
- **0.1c** [Phase 0]. Run, or approve running, `export_live_snapshot.py`. It reads production without changing anything and copies the corpus text and anonymous counts of saved rows (no user IDs, no query text) to his Mac. It is re-run before Phase 4 and whenever a report needs fresh counts.
  Answered 2026-10-05: approved for the 0.1c PR's run, which exported once on 6 Oct 2026 (UTC; 5 Oct evening on Carter's Mac) to `datapipeline/releases/snapshots/2026-10-06/`. Each later run is asked for again.
- **0.6** [Phase 0]. Approve read-only size queries against production.
  Answered 2026-10-30: approved; run from the home server the same day (results in 0.6's section of the P0 spec).
- **0.1d** [Phase 0, before P1]. Approve the next run of `export_live_snapshot.py`, which now also copies `document_chapters` (the stored reader outline: each document's chapter list, its order and labels). It reads production without changing anything and copies corpus text and anonymous counts to his Mac, as the 6 Oct export did. The outline comparison then runs offline.
  Answered 2026-10-31: approved for 0.1d's run, exported as `datapipeline/releases/snapshots/2026-10-31/`. Each later run is asked for again.
- **R7** [Phase 0, blocks 1.7]. Approve each set of downloads for the independent Summa comparison: the Leonine Latin pages of the Supplement (the four core parts were fetched by the 6 Oct review), and any English edition or scan that holds a unit the vendored edition omits. The request states file names and sizes.
  Answered 2026-10-30: all R7 downloads approved.
- **0.3** [Phase 0]. Approve the baseline search evaluation, which costs about $12 in AI provider fees. Confirm it runs before any live change (the 2.2a migration, the alias step or an early retirement), so it records the corpus as it is today. The run changes nothing in the database.
  Answered 2026-10-30: 0.3 is dropped; no baseline is run (Decision log "Baseline eval (0.3)").
- **R6** [Phase 0, blocks Phase 1 items 1.2c, 1.2d, 1.8d]. Approve each set of source downloads. The request states the file names and sizes each time.
  Answered 2026-10-05: the 154 text, XML and HTML files of R6's download list (about 153 MB) are approved; the 91 page-image PDFs and the hOCR file are approved per work later. They are vendored to `datapipeline/sources/_incoming/<Vendored as path>` and locked there; each ingesting PR moves its files unchanged (Decision log "Holding folder for approved downloads"). 152 are vendored; 2 archive.org texts for 5.6c returned HTTP 500 on 5 Oct 2026 and are not.

### Phase 1

- **#279** [Phase 1]. Fetch the US edition's text once from Catholic Cross Reference's Catechism search (about 116 requests). Recommended: yes, spaced further apart than its robots.txt asks, at night, with a plain User-Agent and no retries.
  Answered 2026-10-28: yes, 30 seconds apart, run at night US time, stopping at the first error.
- **1.2f** [Phase 1]. Approve a spend ceiling per work for the AI step that corrects scanning errors in scanned books (first used on councils 8 to 18). No spec proposes a figure.
  Answered 2026-11-02: $2.00 per work, with Claude Sonnet 5.5 and thinking off; the tool stops before any call that could pass it (Decision log "OCR clean-up: model, spend, sample and inputs"). Estimated about $0.14 for the smallest council and under $5 for councils 8 to 18 and 1.3d together; the demo on Lateran I cost $0.18 per pass.
- **1.2f** [Phase 1]. Which Internet Archive files the OCR tool reads for a scan: the word-position file and page-number map (about 25 MB for Schroeder), a page-break file only, or nothing beyond the OCR text already vendored. Found while building 1.2f: the vendored `_djvu.txt` has no page breaks or positions.
  Answered 2026-11-02: the word-position file `_djvu.xml` and the page-number map `_page_numbers.json`, vendored per work through the holding folder; no page images, since the check uses the Internet Archive's viewer. Schroeder's two files were vendored and locked on 2 Nov 2026.
- **R8, 1.3d** [Phase 1, just before 1.3d]. After R8's pilot, choose its scope: search for other public-domain translations of all the Carlen-only older papal documents, search by group, or retire the rest. Then approve 1.3d's downloads and its list of documents to retire.
  Answered 2026-10-31: scope B of `docs/research/R8-papal-translations.md`: search the 38 remaining Pius IX and Gregory XVI documents; the 1740–1799 group and Exsurge Domine retire. Reading public sources (OCR text, catalogue records) into a scratch folder for comparison no longer needs approval; vendoring into the repo still does.
  Answered 2026-10-31 (later): Etsi Multa uses its undated 1874 printing. Nostis et Nobiscum: search for a complete printing, else publish the abridgement with the gaps marked. 1800–1830: one hour of search (three found). A document with no public-domain printing is retired with a link to papalencyclicals.net, recorded in `docs/adr/0001-retire-papal-documents-without-public-domain-english.md`. Still open: approval of the 15 draft rights rows.
  Answered 2026-11-01: every document without a printing was searched in full (ADR 0001 lists where); 26 have a printing and 30 draft rows, including the four extracts. Carlen's translations are registered (TXu000087711), so there is no public-domain basis for them. Documents with no printing are **held for permission** (removal reason `awaiting-permission`: kept, never shown or searched, with a link to papalencyclicals.net); the four extracts are published and only their missing paragraphs held. Permission from Pierian Press is to be asked once the site is complete. Still open: approval of the 30 draft rights rows.
  Answered 2026-11-01 (later): all 30 rows approved, including the seven extract or abridged printings and the two Clement XIV documents translated from the French (rows set `checked_by: Carter`, `checked_on: 2026-11-01`).
  Answered 2026-11-01 (later): "Scan: Internet Archive" is dropped from all credit lines, R6's rows included. This leaves 80 planned 5.6c rows with no credit line; their wording is due with 5.6c (see R6-editions.md, Credit lines).
- **1.3c** [Phase 1]. Approve vendoring the vatican.va English pages of the 25 modern papal documents, and review the PR's paragraph-alignment mismatch list.

### Phase 2

- **2.2a** [Phase 2]. Approve a pg_dump of production for a local timing rehearsal of the new database structure. Then approve applying migrations 0042 and 0043 to the live database, 0043 right after 0042. They add columns and tables only and change nothing users see.
  Answered 2026-11-02 (2.2a's questions, asked before the code): the migration is renumbered 0042 (schema, catalog changes only) plus 0043 (validation and the staging tables, including `document_contents`), and 0039 stays unused; `corpus_publishes` gains `embed_model`, `embed_dimensions`, `snapshot_sha256`, `cleaned_up_at` and `discarded_at` now; read-only catalogue checks of production are approved; running a local Postgres from downloaded binaries on the Lenovo, for the tests, is approved. The pg_dump and the apply are still to be asked.
  Answered 2026-11-02 (rehearsal): approved as a read-only copy of the four corpus tables (`documents`, `chunks`, `document_chapters`, `document_contents`; corpus text, no user data) instead of a full pg_dump, which this machine could not restore (no pgvector, no version 17 client). Loaded locally, timed, deleted. Timings are in PR #309.
  Answered 2026-11-02 (apply): approved and done. 0042 applied 20:30:47 UTC (1.2 s), 0043 at 20:31:12 UTC (1.1 s), both by `psql --single-transaction` and recorded in `supabase_migrations.schema_migrations`. Checked afterwards: 54,555 passages and 421 documents all live and searchable, outline and user-row counts unchanged, all ten constraints validated, staging identical to live, client roles shut out. Each statement cost a ~40 ms round trip, so 0042 held its read-blocking locks about 0.55 s, not the rehearsed 30 ms; the API logged no requests in that window.
- **2.2b** [Phase 2]. Approve two steps on live systems. The first creates the Qdrant alias `chunks_live` (a second name for today's search index, so later switches take one step) and an index on the new "searchable" field. The second sets one environment variable on Railway and restarts the API.
- **2.2w and 4.1a** [Phase 2, repeated in Phase 4]. Approve the pg_dump for the full local rehearsal of the new publish process. The 2.2a timing rehearsal can share this dump if the two run close together.
  Answered 2026-11-04 (2.2w): instead of a full pg_dump, which this machine cannot restore, a read-only export of production restored into a local Postgres 17 on the Lenovo: the corpus tables (`documents`, `chunks` without the two unused pgvector columns, `document_chapters`, `document_contents` and the 2.2a tables) and the user tables cut to keys only (which passage or document each row points at), with user, search and guest IDs replaced by placeholders and no query text, notes, emails or other user content. It stays on the Lenovo, not Carter's Mac as D8 says, and is deleted after the rehearsal. Also a read-only copy of production's Qdrant points (about 55,000) into a local file-based Qdrant, copied in small batches at a quiet time because production is a small Free cluster, and deleted afterwards. 4.1a's rehearsal asks again.
- **2.2w** [Phase 2 to 4]. Approve the embedding spend for the first full local rehearsal stage (2.2w's or 4.1a's, whichever runs first), about 11 million tokens, about $1.40 at today's list price (to be checked before the run). It fills a local cache, so later rehearsals and the production run cost between $0 and the same amount, depending on how much the build changed in between.
  Answered 2026-11-04: approved, with real embeddings to fill the cache, provided the price checked before the run is not materially higher (checked 4 Nov 2026: $0.13 per million tokens, unchanged).
- **1.8d and 2.2w, only if B-1.8d below is yes** [Phase 2]. Approve the lock-file PR, the one live step that retires On the Incarnation early, the API restart, and the later PR that removes the lock entry.
  Answered 2026-11-04: not needed: Carter left On the Incarnation until the Phase 4 apply (1.8d).

### Phase 4

- **4.0** [Phase 4]. Approve the time and the run of `VACUUM FULL`, which compacts the main table. Search and the reader pause for about a minute while it runs.
- **2.2c and 4.0** [Phase 4]. Approve applying 2.2c's migration in the same window. It changes how the keyword-search column is computed (no verse markers, references added), which rewrites the main table once, like `VACUUM FULL`; the window may then need only one rewrite. Search and the reader pause while it runs.
- **4.1b** [Phase 4]. Approve, one at a time:
  - the PR that freezes the Phase 4 build, including any council that shows a gap notice because its public-domain text is not ready;
  - the lock-file PR for the republish;
  - the staging build and its embedding spend (step 1);
  - the backups (step 4);
  - the apply (step 6);
  - a hand-run outline refresh (step 7), only if one is needed;
  - the switch of the search index (step 8);
  - the API restart (step 9);
  - the smoke checks and dropping the staging tables in production (step 10);
  - the rollback (step 12), only if it is needed;
  - each clean-up step after the rollback window (step 13): deleting hidden passages no user points at, deleting the old Qdrant index (this cannot be undone), deleting the private backups, and the PR that removes the lock entry.
- **4.2** [Phase 4]. Approve the spend for the accuracy checks on staging and on production (pipeline calls only, no judge). The report states the amount.

### Phase 5

- **5.1a** [Phase 5]. Approve creating a Qdrant index, only if the check finds one missing.
- **5.1b.3** [Phase 5]. Approve the migration, the lock-file PR, the apply and index switch, the script that rewrites collection names in saved preferences and searches, and the API restart.
- **5.1b.4** [Phase 5]. Approve the migration that removes the old collection names.
- **5.3a, 5.3b, 5.4, 5.5, 5.6a, 5.6b, 5.6c** [Phase 5]. For every addition, approve its lock-file PR and its apply, and for 5.3a also its migration and the PR that makes the Roman Curia collection visible.

---

## B. Decisions

### Phase 0

- **0.4** [Phase 0]. Agree to the lock rules. Every datapipeline write to the live corpus or search index, including emergency repairs, needs a reviewed PR adding a lock entry. The only exception is a rehearsal where the database and Qdrant both run on his own Mac. Steps done by hand (migrations, alias and index creation, `VACUUM FULL`, post-window deletions) are outside the lock and approved one at a time. An entry stays until its rollback window closes. No entry is added before Phase 4 except, if he chooses, the On the Incarnation retirement. Recommended answer is yes.
  Answered 2026-10-04: Yes to all three: every live datapipeline write goes through a reviewed lock entry, emergency repairs included, with only local rehearsals exempt and hand-run ops steps approved one at a time; an entry stays until its rollback window closes and a second PR removes it; no entry before the P4 apply, except possibly On the Incarnation, decided separately.
  Answered 2026-10-04 (after review): allow a lone `pipeline.py --stage enrich --sample N` run without a lock entry; it writes only local files under `samples/`.
- **2.1** [Phase 0]. Approve four things about the new ID registry.
  - Passages get anchors from the source's own structure (the ID of each section in the source file) instead of from label text. A choice remains on how dots in those IDs are written, kept as dots or turned into dashes. The spec recommends no option; either works.
  - The passage registry, about 7 MB of IDs and anchors and no text, goes into the public repo.
  - The removal-registry format, whose tombstone sentences are public.
  - One new removal reason, `rolled-back`, used only for passages that an undone publish had added. The plan's decision D11 lists the reasons and does not name this one, so the plan needs a one-line update if he agrees.

  Recommended answer is yes to all four.
  Answered 2026-10-30: yes to all four. Anchors keep the source ids exactly as written (dots, underscores and capitals; no mapping). The passage registry goes into the public repo as specified, with `live_anchor` on every row; measured on 30 Oct it is about 18.5 MB uncompressed (the Summa's live anchors average 191 characters), not 7 MB, and about 1.7 MB compressed. The removal-registry format is approved as specified. `rolled-back` is added, and D11 now names it.
- **Review gaps (6 Oct 2026 corpus reviews)** [Phase 0, before 2.1]. Six questions and nine defaults from `docs/corpus-cleanup/REVIEW-GAPS-PLAN.md` section 7, each with its recommended answer.
  - Q1. Should passages that state a position the document rejects (condemned propositions in Exsurge Domine, the Syllabus and Constance; Nestorius's letter at Ephesus; Caecilius in the Octavius; Mani in the Acts of Archelaus, about 270 passages) stay in search with a "rejected voice" label, or move to the reader only? Recommended: label them.
  - Q2. Should a split piece's ID follow its own opening paragraph when piece boundaries move? Recommended: yes.
  - Q3. Should 2.1 anchor Summa passages on the source's paragraph IDs instead of the part labels? Recommended: yes.
  - Q4. Should keyword search drop verse markers and index references, with one table rewrite in 4.0's window? Recommended: yes.
  - Q5. Should 1.7, and so Phase 4, wait for a full independent Summa comparison (R7), with omitted units restored only from an existing English edition or else flagged by a reader note? Recommended: yes.
  - Q6. May the four review reports, the synthesis and the two prompt files be committed with the plan? Recommended: yes.
  - Defaults: Epistle XXX removed under rule A and the other letters credited per sender; Summa citations keep the article's question; Psalm titles and the Sirach prologue restored; the Catechism fix first as 1.6a; reader outlines checked from the next snapshot export; no embedding-input change beyond skipping unsearchable neighbours, with the dedup threshold tested as RF-1; editors' chapter titles moved into labels; real Summa reply targets; a work note for fragment collections.
  Answered 2026-10-09: yes to all six recommendations and all nine defaults. Recorded as Decision log rows dated 9 Oct 2026; the specs now state the chosen options.
- **0.1a** [Phase 0]. Review the list of known defects that the new tests start out expecting. No decision beyond checking it.
- **0.1a** [Phase 0]. Should the coverage check stop flagging editor-written ThML sections (introductory notices, elucidations, editors' prefaces) that the corpus correctly leaves out under rule G? Recommended: yes, through a tracked list Carter reviews once.
  Answered 2026-10-05: yes. The list is `datapipeline/checks/editorial_divs.json`, 112 divs; a listed div that reaches a passage fails the check.
- **0.1b** [Phase 0]. Should the debris rule (H2: a passage that is only a page number, a numeral or punctuation) block publication now, with the one such passage on master, a lone "." in Summa III q.16 a.3, accepted as a known defect until 1.7 removes it? The alternative is report-only until 1.7, as one sentence of the spec says. Either way the master build publishes the same; the difference is that a Phase 1 PR adding a new debris passage elsewhere is refused instead of reported. The spec says both, so this needs his choice. Recommended: block now (as built).
  Answered 2026-10-05: block now. The Summa "." stays a known defect until 1.7 removes it and deletes the entry.
- **0.1c** [Phase 0]. For passages under 16 words, should the release report's drift check (does a passage ID still show the same text?) compare words rather than the characters its spec named? On the 6 Oct snapshot, characters let 15% of genuinely different short Summa parts pass as the same text; words let 2% pass and still passed every small real edit. Recommended: words.
  Answered 2026-10-05: words.
- **2.1** [Phase 0]. Three points the 0.1c report (6 Oct 2026 snapshot) raised.
  - 408 Summa passage IDs name a different part in the master build than on the live site, in 81 articles: live kept a blank passage in 21 of them and printed "On the contrary" and "I answer that" as one passage in 60, so the later parts carry their neighbours' running numbers. Carter decided on 5 Oct 2026 that 2.1 gives each of these IDs to the part it names live (Decision log "Summa passage IDs shifted in the live publication (0.1c)"). They are the `release.stability:summa/…` entries in `checks/known_defects.json`; one saved search result points at them today. Open: how 2.1 finds that part. 2.1's freeze takes each ID from the anchor the master build gives the passage, which is the wrong part here. (a) Take the pairing from 0.1c's `remap.jsonl`: for each of these units, the build part holding the live passage's text gets the live ID, and parts live never had (the split-out "I answer that") get new IDs. (b) Write the 408 pairs by hand into the registry. Recommended: (a), checked against the 408 entries, which the 0.1c report then shows as fixed.
  - First Lateran `sec-0/1` is a different case, added by the implementer without asking. Live, that ID names the editor's introduction (papalencyclicals.net's, which rule G removes); the build no longer has the introduction and gives the ID to canon 1, whose live ID is `sec-0/1-2`. Its `known_defects.json` entry says 2.1, for the pairing part: canon 1 should keep `sec-0/1-2`'s ID. The introduction's own ID then needs a removal entry (`rule-g-editorial`), which 2.1 does not add. Recommended: 2.1 pairs canon 1; the council item that rebuilds First Lateran (1.2b, or 1.2e if Schroeder replaces it first) adds the removal entry.
  - 2.1's acceptance check says the report shows `moved`, `split`, `merged` and `renumbered` (a passage whose text now sits in other passages) at 0 apart from the 163 live passages a master build lacks. Those 163 are themselves 134 `split`, 22 `moved` and 7 `merged`, none `removed`. Once 2.1 adds `registry/redirects.json` (the file of declared "this old ID now lives at that new ID" rows), each of them fails as `release.unbacked` (a changed ID nobody declared) until a redirect row or a removal entry explains it. Recommended: read the check as "0 beyond those 163"; 2.1 lists each of the 163 in `known_defects.json`, and the item that rebuilds each passage's document adds its redirect or removal entry before Phase 4.
  Answered 2026-10-30:
  - The 408 Summa IDs are paired by text, (a). On the 30 Oct build 387 pair to exactly one part each. The other 21 name live passages with no text (an empty "Objection N" part, printed in the source just before an "On the contrary" in the same paragraph); each gets a `merged` redirect to the part that now holds that paragraph. The same pass returns their live IDs to 21 more Summa parts that a build no longer emitted under their old anchors (exact text matches).
  - First Lateran: canon 1 keeps its own live ID (`sec-0/1-2`'s), and the editor's introduction, which the build still emits, keeps `sec-0/1`'s. The council item that rebuilds First Lateran adds the introduction's `rule-g-editorial` entry.
  - The 163: 13 were Catechism passages that the 30 Oct publish deleted. Of the other 150, 2.1's own rules keep 145 (123 by the first-piece rule, 21 Summa parts by the text pass, First Lateran's canon 1), and the 5 units that now need one piece fewer get `merged` redirects. No `release.unbacked` exception is needed.
- **2.1** [Phase 0]. Four points raised while starting 2.1 (30 Oct 2026).
  - 14 Summa parts open inside a source paragraph, after prose (a sed contra or a determination), so the paragraph-ID anchor would name two parts.
  - Live changed on 30 Oct (the Catechism's US-edition publish, #295), so the 6 Oct snapshot no longer describes what users see.
  - The Catechism passage IDs that publish deleted.
  - The early publish has no Decision log row.
  Answered 2026-10-30: the second part opening in a paragraph takes the in-paragraph suffix (`…/p6-2`), as a cut inside a long paragraph does. A fresh read-only snapshot export was approved and ran on 30 Oct 2026 (`releases/snapshots/2026-10-30/`): the other nine collections equal the 6 Oct snapshot passage for passage, the Catechism equals the master build, and 54 Catechism IDs were deleted (#295 says 53). The deleted IDs are not recorded in the registry, since nothing can point at them. The early publish gets a Decision log row.
- **2.1** [Phase 0]. Three points 2.1's fresh-context review raised (30 Oct 2026).
  - Accept the acceptance checks as built: 20 saved search results sit on redirected IDs until 4.1a moves them; 65 live pieces whose cut moved get redirects beyond those already answered (Bible 9, Summa 13 among them); units never live take IDs from their new anchors; three duplicated §1s become visible (1.3a). Recommended: accept.
  - Units sharing a base anchor: keep naming unsplit units first (every live anchor kept except First Lateran's two, swapped; IDs stay on their text), or name by document order (First Lateran kept, 7 other live anchors move, 2 of them with saved rows). Recommended: keep, and tell 1.2e about the swap.
  - Should 2.1 make the publish path refuse a live write while open redirects exist or a built anchor differs from its frozen anchor, until 2.2w replaces the writer? Today only the publish lock prevents a publish that would delete the 87 redirected IDs and their saved rows. Recommended: yes.
  Answered 2026-10-30: accept the acceptance checks as built; keep naming unsplit units first, with 1.2e's spec told about the First Lateran swap. No guard is built: no publish runs with today's writer once 2.1 has merged, and any exception waits for 2.2w or adds this guard first (Decision log "No publish with today's writer after 2.1").
- **0.2** [Phase 0]. Confirm that the fields of the public rights file (edition, translator, public-domain basis, renewal search, credit line) are safe to publish. Also decide what to do with Amoris Laetitia, which is downloaded but was never published and has no decision on record. The spec gives no recommendation.
  Answered 2026-10-04: the fields are safe to publish (edition, translator, first published, source URL, status, renewal search, credit line). In-copyright works get a new status, `in-copyright`, with a field naming the rights holder; that covers the papal and Vatican texts, Vatican II, the Catechism and the canon law English. Other texts stay `unknown` unless their file or page establishes a public-domain edition. The WEB-C Bible gets a new status, `pd-dedicated`. Amoris Laetitia is scheduled for 5.4 with the other two unpublished papal files.
- **0.3** [Phase 0]. Approve the list of about 30 targeted test questions, written fresh rather than taken from users' searches.
  Answered 2026-10-30: 0.3 is dropped, so there is no list to approve. 4.2 writes its own check questions.
- **R1** [Phase 0 research, answer needed by Phase 3]. Decide these points.
  - Hippolytus led a rival group in Rome, outside communion, from about 217 to about 235. The Refutation of All Heresies (377 passages) is dated to the 220s. Under rule A a work written outside communion is removed, and he is not a Doctor of the Church. The spec gives no recommendation.
  - Where standard chronologies disagree on a date, which one to use.
  - Any other finding R1 lists "for Carter".
  - The Pseudo-Chrysostom question, which 5.6b also needs. The Catena Aurea quotes a commentary most scholars now credit to an Arian writer. Keep those quotations labeled "Pseudo-Chrysostom", or leave them out. No recommendation yet.
  - Added by R1 (5 Oct 2026), each with a recommendation in `docs/research/R1-rule-a-dating.md`, "For Carter": Gregory Thaumaturgus's Panegyric to Origen (37 passages; delivered 238, baptism undated); Lactantius's poem The Phoenix (4; not datable against his conversion); the Catena Aurea's quotations of Origen (319 in Matthew and Mark; Origen is condemned by name), of Theophylact (a Byzantine writer after 1054) and of Josephus (not a Christian); whether Theologia Germanica in an English translation from the German is barred (only Castellio's Latin version was prohibited, in 1621, and that entry is gone from the 1900 Index); whether a papal bull that names an author while condemning his propositions (Eckhart, Abelard) counts as condemning the author by name, which would exclude all his works; and the extra key for works inside container documents (document ID plus the source's section id), which is R1's proposal.
  Answered 2026-10-04: R1's rule A file is keyed by the frozen document ID for works already in the corpus and by author and title for planned works not yet in the corpus (Carter's choice, since 2.1's work IDs do not exist yet). The container key above is not covered by this answer.
  Answered 2026-10-05: every recommendation in R1's "For Carter" is accepted. Hippolytus: rule A applies as written, so the Refutation of All Heresies (377 passages) and the 115 undated passages of his other works go, and Christ and Antichrist (26) and On Daniel (29) stay. Gregory Thaumaturgus's Panegyric to Origen (37) and Lactantius's Phoenix (4) are excluded. Chronology: Quasten's Patrology vol. II for the early writers, with the "sources disagree" exclusions kept (Tertullian 192); date of reception plus first edition for modern converts. Catena Aurea (5.6b): the Pseudo-Chrysostom, Origen, Theophylact and Josephus quotations are excluded, and Eusebius is checked before 5.6b. Theologia Germanica in an English translation from the German is not barred by rule A. A bull that names an author while condemning his propositions (Eckhart, Abelard) is a condemnation by name; Joachim is not. The container key (document ID plus ThML div id) is accepted.
- **R2 and 1.5b** [Phase 1]. Approve the English sources found for canons printed in Latin, and the label for unofficial English. Suggested label is "Unofficial English translation (L'Osservatore Romano). The Latin text is official."
  Answered 2026-10-04: Approved, with the suggested label, for 111, 112, 535 §2 and 868 §1 2° (and 868 §3 and the six marriage canons below), using the L'Osservatore Romano English of 23 Sep 2016, p. 9, but only once its text has been checked against the printed page; the EWTN reprint has typesetting errors and is not used unchecked. Any canon whose print text cannot be checked follows rule E. 295 and 296 follow rule E (current Latin, out of search): the only English, a Vatican News article, mistranslates 295 §2. 579, 695 §1 and 700 follow rule E. Add canon 868 §3 (De concordia art. 5) in 1.5b. No reader note on 360, 361 or 948, whose text is in force. Extend 1.5b to the marriage canons 1108, 1109, 1111, 1112, 1116 and 1127 (De concordia arts. 6-11).
  Answered 2026-10-04 (later): the print check is replaced by two-copy agreement; canon 868 stays wholly under rule E until 868 §3 is checked; see the 1.5b entry in section C.
  Revised 2026-10-29: under rule E as revised, a canon with no English is retired with an English tombstone linking to the Latin, not shown in Latin.
- **R3** [Phase 1]. Choose how the Greek additions to Esther are numbered, if no Church source settles it. R3 will give a recommendation.
  Answered 2026-10-04: No Church source settles it (R3). Keep WEB-C chapter and verse numbers and title the restored passages by addition letter; record the Nova Vulgata and NAB ranges in metadata for whole additions only.
  Answered 2026-10-04 (after review): also record the Septuagint range, and correct the Decision log reason: the Catechism and the Italian Lectionary share the Septuagint's letters.
- **R4** [Phase 1]. Decide whether the "Contents" summaries in the Refutation of All Heresies are the author's own, only if the sources disagree.
  Answered 2026-10-04: Not needed. The sources agree that the summaries are the author's own (`docs/research/R4-refutation-contents.md`); 1.8a keeps them and strips only the ANF heading lines.
- **R5** [Phase 1]. If the translator of On Loving God cannot be traced, approve the replacement translation R5 proposes.
  Answered 2026-10-04: Traced, so no replacement. Approved: the translation is William Harman van Allen's (Caldey Abbey, 1909); credit line "Translated by William Harman van Allen (1909). Sourced via CCEL.org"; the Decision log row is updated; 1.9 restores the 1909 Chapter VIII title ("loves Self for Self's sake").
- **R9 and 1.2e** [Phase 1, before 1.2e's last four councils]. Deferrari's book is a translation of a German-published compilation. Take only the translated decree text, or also Denzinger's headings, notes and numbers. Recommended answer: decree text only, with a note on each passage that it is an extract.
  Answered 2026-11-04: decree text only, as recommended.
- **R9 and 1.2e** [Phase 1, before 1.2e's last four councils]. Approve the draft row for Deferrari's *The Sources of Catholic Dogma* (`pd-us-non-renewal`). Choose which of its texts come in, and how 1.2e gets its pages, since no clean scan is openly available. Recommended answer: approve; take its Constance and Florence texts and Constantinople IV's six canons, keep Schroeder for Lateran V's shared bulls; buy a 1957 printing and scan the pages (about 30). Details are in `docs/research/R9-council-gap-leads.md`.
  Answered 2026-11-04: approved: with no evidence of a renewal, use it, as extracts placed in their own documents for now. All its council extracts come in with a note, and Wyclif's and Hus's lists with the rejected label and a note. 1.2e gets the pages from the free PDF of the reprint, saved and hashed on 4 Nov 2026, with every passage checked against the page image and the 1957 scan; buying a 1957 copy is the fallback.
- **R9 and 1.3d** [Phase 1, before 1.3d]. R9 found four papal documents held for permission in Deferrari's book. Exsurge Domine's 41 condemned propositions on the site are his translation; Vix Pervenit, Singulari Nos and Quanto Conficiamur Moerore have shorter extracts in a different translation. Keep or publish these, with the rest of each still held. Recommended answer: yes (`docs/research/R9-council-gap-leads.md`, section 5).
  Answered 2026-11-04: yes. Exsurge Domine's propositions carry the rejected label and a note.
- **R9 and 1.2c** [Phase 1, before 1.2c reaches Nicaea II]. Approve the draft rows for Hefele vol. 5 (Nicaea II's four anathemas) and Chrystal vol. 1 (Nestorius's letter), both `pd-us-pre-1931`, and choose whether 1.2c uses them. Recommended answer: use Hefele, with a note that the anathemas come from his narrative of the session; use Chrystal at low priority, without his summaries or notes.
  Answered 2026-11-04: use both, as recommended; rows approved, and 1.2c may vendor the two scans.

### Phase 1

- **1.1** [Phase 1]. Keep the "Preliminary Note of Explanation" as part of Lumen Gentium. Recommended answer is yes, as its own chapter.
  Answered 2026-11-04: yes, as its own chapter.
- **1.2a** [Phase 1]. Approve the register of council texts that have no public-domain English translation. Those texts show a "translation in preparation" notice instead. Chiefly Florence's doctrinal decrees are affected. The register is the last section of `docs/research/council-translation-inventory.md` (G1 to G10): besides Florence, most of Constance and Lateran V, Constantinople IV's Definition, Lyons I's deposition bull, Vienne's Templar bulls, Vatican I's session 1 (session 2's profession is partial and has its own 1.2d entry), Nestorius's second letter at Ephesus and Nicaea II's four anathemas.
  Answered 2026-11-04: approved, with Vatican I's session 2 added as G11. The text stays available to us but is not retrievable: retired rows are never hard-deleted and the vendored Tanner files stay for good.
  Answered 2026-11-04: gap notices say "This text is not available on TheoCorpus at present.", not "translation in preparation", and link to the council's page at papalencyclicals.net, as ADR 0001 does for papal documents.
- **1.2a** [Phase 1]. Leads were found for three gaps, in books published before 1931 that are not planned sources: Chrystal (1895) for Nestorius's letter, Mendham (1850) or the English Hefele (1896) for Nicaea II's anathemas, Foxe's *Acts and Monuments* (Cattley's edition) for Constance's sentences against Wyclif and Hus. Pursue them (an edition and rights check like R6's, then a download request), or leave those texts on the register. Recommended answer: pursue Chrystal and Mendham, which translate the acts; leave Foxe, whose book is a polemic and whose translation cannot be checked against a planned edition.
  Answered 2026-11-04: pursue them through R9: Hefele first, then Mendham, for Nicaea II; Chrystal at low priority; and books after 1930 never renewed, starting with Deferrari's English Denzinger. Foxe is not pursued.
- **1.2e** [Phase 1]. Schroeder condenses or excerpts some council texts: all 27 canons of Constantinople IV (about 40% of Tanner's length), Constance's first reform statute, Vienne's Exivi de paradiso, Lyons II's crusade constitution (one part missing), Lateran V's seven bulls; and for Lateran I's canons 15 and 16 Schroeder translates another recension than Tanner's main text (introductions and conclusions left out). Publish these as the council's text with a label saying they are abridged, or treat them as gaps. Recommended answer: publish with the label, as 1.3d does for partial papal documents; Constantinople IV's canons are the case to look at, since none is printed whole.
  Answered 2026-11-04: publish them, with a note on each passage. Constantinople IV's say they are summarised by Schroeder.
- **1.2d** [Phase 1]. Vatican I's session 2 profession of faith is the 1564 Tridentine profession that Pius IX recited. Schaff prints that 1564 profession (`creeds2` `v.i.ii`) as Pius IV's act, with the creed abbreviated to "etc.", a blank name, the 1564 closing, and an oath of obedience to the pope that Pius IX did not make (Tanner gives it as the other fathers' addition). Use it, labelled, for session 2, or retire session 2 as a gap. Recommended answer: retire it as a gap, since the text Schaff prints is a different act with a different closing, and the reader would show Pius IV's words as the council's.
  Answered 2026-11-04: retire it as a gap (G11), as recommended.
- **1.2c** [Phase 1]. Percival prints council texts that Tanner does not: letters and decrees of Ephesus, Chalcedon and Constantinople III, Chalcedon's canons 29 and 30 (extracts of the acts), the fifteen anathemas against Origen (attributed to Constantinople II, disputed) and an abridged copy of the iconoclast definition that Nicaea II condemned. Include them in 1.2c's allowlist. Recommended answer: include the letters and decrees the inventory marks "yes"; leave out canons 29 and 30, the Origen anathemas and the iconoclast definition.
  Answered 2026-11-04: as recommended: include the letters and decrees the inventory marks "yes"; leave out canons 29 and 30, the Origen anathemas and the iconoclast definition.
- **1.2e** [Phase 1]. A scanned work's final text cannot be rebuilt, since a model correction run does not repeat, and `ocr_work/` is gitignored and on one machine. Keep it in the repository (`ocr/texts/<work>.json`), or vendor it under `sources/` with a lock entry. Recommended answer: the repository, so every checkout and CI build the same text. 1.2e-1 is built that way.
- **1.2e and 5.5** [Phase 1]. Fordham's transcriptions of Schroeder's Lateran I, II and IV and of the 1923 Roman Catechism carry a notice that their electronic form is copyright and not licensed for commercial use. Use them as the text, or only to check our own OCR of the scans. Recommended answer: only to check the OCR, as with ecatholic2000 (R6).
  Answered 2026-10-05: use Fordham's transcriptions only to check the OCR of the Schroeder and 1923 Catechism scans, as with ecatholic2000.
- **1.3b** [Phase 1]. Confirm which three documents are the "Jubilee bulls" filed as encyclicals. Also decide whether Ineffabilis Deus and Munificentissimus Deus are labeled "apostolic constitution" or "bull". The spec gives no recommendation.
  Answered 2026-11-04: the three are Peregrinantes (1749), Salutis Nostrae (1774) and Quod Hoc Ineunte (1824), all `bull`. Ineffabilis Deus is `bull`, Munificentissimus Deus is `apostolic-constitution`, and Apostolica Constitutio stays `encyclical`.
- **1.4a** [Phase 1]. Keep `song-of-solomon` inside link addresses while the book's title changes to "Song of Songs". Users never see the address. Recommended answer is keep.
  Answered 2026-11-04: keep. The address can appear in a reader link's URL, which does no harm.
- **1.4b** [Phase 1]. Renumber only Joel and Malachi to the Church's official Latin Bible numbering, or every place where Church documents cite a different chapter. Recommended answer is Joel and Malachi now, the rest as a later issue.
  Answered 2026-11-04: Joel and Malachi now, the rest as a later issue.
  Answered 2026-11-04 (later the same day): add Jonah and Romans's doxology to 1.4b, after citation counts showed Church documents cite them. The rest is #317.
- **1.4c** [Phase 1]. Give the deuterocanonical books' new shorter passages titles from the old Douay-Rheims chapter summaries, or leave them untitled. Recommended answer is untitled for now.
  Answered 2026-11-04: no titles. A passage is labelled by its verse range, in the form "Sirach 3:1–16".
- **1.10a** [Phase 1]. 1.10a changes the title or author of 65 Church Fathers documents ("Methodius." to "Methodius", "Irenæus" to "Irenaeus", "Fragments." to "Fragments of Methodius"). The rights inventory found documents by their title and author, so it could match either the live documents (old labels until Phase 4) or the new build, not both: the live reader-access sync would refuse to run, or the publish would make those works excerpt-only. Match by the frozen document ID instead, accept both labels until Phase 4, or skip the renames? Recommended: match by document ID, in its own PR before 1.10a.
  Answered 2026-10-31: match by document ID, in its own PR before 1.10a (Decision log "Rights inventory matched by document ID").
- **1.10b** [Phase 1]. Should 1.10b, which already rewrites how Fathers and medieval paragraphs are read, also read `<verse>` blocks? Today the adapter reads only `<p>`, so about 135,000 characters of poems and quoted verse are missing, such as the pagan poets and the Sibyl that Justin, Theophilus and Clement quote as testimony, and Clement's hymn to Christ. Recommended: yes, as part of the work's own text (rule G keeps an author's quotations). If no, the 11 `known_defects.json` entries move to another item.
  Answered 2026-10-05: yes. 1.10b's Changes and Acceptance checks now include `<verse>` blocks.
- **1.10c** [Phase 1]. Two points, raised while building it.
  - Two chapters of one Fathers or medieval document often share a label (Augustine's treatise volumes, Hippolytus, Gregory's two volumes, the Banquet, Cur Deus Homo), so 406 Fathers and 16 medieval citations are still shared after every split piece cites its own text. Fix them in 1.10c, or leave them to the items that relabel those documents? Recommended: leave them, tracked by a new check.
    Answered 2026-11-02: leave them to 1.8b, 1.8c and 1.9, as known defects of `labels.unique_reference`.
  - Keep the splitter's 500-character allowance where a piece ends on a whole verse or paragraph, or cap pieces strictly at 3,500? Recommended: keep it (467 redirects against 1,429, and no 176-character cards).
    Answered 2026-11-02: keep it.
- **1.8b** [Phase 1]. 1.10b found that the Confessions' footnote callers in `viii.xi` ("remains immutably.2 It is good") are plain digits in the source, with no `<note>`, so its note strip cannot remove them. The `known_defects.json` entry now names 1.8b, the NPNF Augustine clean-up. Is 1.8b the right owner? Recommended: yes, as four digits in one paragraph of an NPNF Augustine volume.
  Answered 2026-11-01: yes. 1.8b removes them.
- **#279** [Phase 1]. Two points.
  - Mark the parts of 1.6a and 1.6 that the US-edition text delivers as covered by #279. Recommended answer is yes.
    Answered 2026-10-28: yes, for the parts the US text actually changes, and update every overlapping issue and spec.
  - CCC 2267: (a) publish waits until 1.6 can ship the 1997 text as its history passage, or (b) publish the 2018 text first, the 1997 text staying in the vendored `ccc.json` and in #279's report, and 1.6 adds the history passage later. Recommended answer is (b).
    Answered 2026-10-28: (b).
- **1.6** [Phase 1]. Show Catechism paragraph numbers inside passage text as "§2267". Recommended answer is yes; the work goes ahead with this if there is no answer.
  Answered 2026-11-04: yes.
- **1.7** [Phase 1]. Add Aquinas's own short introductions at the start of 611 questions and 3 treatises (about 297,000 characters), which are missing today. Recommended answer is yes, since they are his own words.
  Answered 2026-10-05: yes, as passages labeled "Question N, prologue" before Article 1. The Supplement's prologues are its compiler's and follow the Supplement's treatment (3.2).
- **1.7 (R7 question 2)** [Phase 1]. In I q.117 a.2 and I q.112 a.2 the text CCEL lost begins or ends inside a paragraph it kept, so it cannot be added as a separate passage without putting the article out of order. Restore the printed words in place, inside the existing passage, and split I q.117 a.2's determination off as its own "I answer that" part (`p5-2`)? Or add the recovered words as a new passage (`recovered-<n>`)? Recommended answer: in place. Whole missing units stay new `recovered-<n>` passages.
  Answered 2026-10-31: in place (asked during 0.1d). R7's questions 1, 3 and 4 stay open for 1.7.
- **1.8b** [Phase 1]. Split two Augustine volumes ("Doctrinal Treatises", "Moral Treatises") into their 16 separate works, so On Lying is cited as On Lying. Bookmarks survive either way. Recommended answer is yes.
  Answered 2026-11-04: yes.
- **1.8c** [Phase 1]. Two points.
  - Label the Shepherd of Hermas's author as "Hermas" and its books "The Shepherd: Visions", "Commandments" and "Similitudes".
  - Remove the Balsamon and Zonaras commentary printed inside Peter of Alexandria's canons, rather than keep it under their own names.

  The spec proposes yes to both.
  Answered 2026-11-04: yes to both.
- **1.8d** [Phase 1, acted on in Phase 2]. The current translation of Athanasius's On the Incarnation (Lawson, 1944) is still under copyright. Hide it before Phase 4 (early retirement), or leave it visible until Phase 4 replaces it with Robertson's public-domain translation. Hiding it waits for 2.2a, 2.2b, 2.4a and 2.4b to ship. Deleting it is not an option, because that would erase a user's saved search. The spec gives no recommendation.
  Answered 2026-11-04: leave it visible until Phase 4 replaces it. The work is already excerpt-only.
- **1.8e** [Phase 1]. About 30 whole works in the downloaded Fathers volumes never reach the corpus. Choose which to add. Recommended answer is none before Phase 4 except Asterius Urbanus, and the rest later with normal rule checks.
  Answered 2026-11-04: as recommended: none before Phase 4 except Asterius Urbanus; the rest through 5.6a with normal rule checks.
- **1.9** [Phase 1]. Add Anselm's reply to Gaunilo ("Anselm's Apologetic"). Default is no. Gaunilo's own piece would need its own rule check.
  Answered 2026-11-04: add both Anselm's reply and Gaunilo's piece after Phase 4, with 5.6b, once Gaunilo has his rule check.

### Phase 2

- **2.2c** [Phase 2]. Confirm that the keyword-search index needs no rebuild, because fixed text updates it automatically. Recommended answer is confirm.
  Answered 2026-10-09: no. The 6 Oct reviews showed verse markers indexed as words and references not indexed (C-16); 2.2c becomes a migration that drops the markers and adds the reference at lower weight, run in 4.0's window (Decision log "Keyword search (2.2c, C-16)").
- **2.4d** [Phase 2]. Approve how a rejected-voice passage looks on the result card and in the reader (a small label above the text carrying its `unit_label`, such as "Condemned proposition 10"), and the one sentence the rerankers and the explanation model are given about it. The label texts themselves are approved under 3.4.
- **2.3** [Phase 2]. Set the wording of the source credit line wherever 0.2 has not settled it (for example "Text: Libreria Editrice Vaticana", "Sourced via CCEL.org").
- **2.4a** [Phase 2]. When a saved search or bookmark points at a removed passage, show no text (title, author, reference and one sentence of reason), or keep showing the text under a "removed" banner. Recommended answer is no text.
- **2.4b** [Phase 2]. Approve the wording pattern of tombstones.
- **2.4c** [Phase 2]. Approve the corrected names on the About page. Origen, Chrysostom, Bonaventure, Hildegard and Duns Scotus come out; Irenaeus, Bernard of Clairvaux and Thomas à Kempis go in.
- **2.2w** [Phase 2]. Found by 2.2a (2 Nov 2026). Staging now holds `staging.document_contents` (0040's contents tree), but 2.2w's stage step 4, apply, before-snapshot and rollback list `documents`, `chunks`, `document_works` and `document_chapters` only. Should the writer stage, snapshot, apply and roll back the contents tree with the chunks, as `reader_writer.write_document` does today? Recommended answer is yes; otherwise an apply would leave each document's tree pointing at the old chapters, and `/toc` would fall back to the flat list.
  Answered 2026-11-02: yes. The tree is staged, snapshotted, applied and rolled back with the chunks.
- **2.2w** [Phase 2]. Found by 2.2w (2 Nov 2026). Should the apply and the rollback derive each touched document's `reader_access` again from the rights inventory, so neither can reopen a text whose rights are not cleared? Recommended answer is yes, with the apply refusing when the value differs from the staged one.
  Answered 2026-11-02: yes to all three: stage writes it, apply re-derives it and refuses on a difference, rollback re-derives it rather than restoring the snapshot's value.
- **2.2w** [Phase 2]. Found by 2.2w (2 Nov 2026). Ship 2.2w as one PR, or split it? Recommended answer is three PRs: (a) CLI, lock gates, stage and report; (b) snapshot, apply, switch, rollback and cleanup; (c) the read override, the other writers and the docs.
  Answered 2026-11-02: three PRs as recommended, each merged before the next is based on master.
- **2.2w** [Phase 2]. Found by 2.2w (2 Nov 2026). 2.2b is not merged, so the alias `chunks_live` does not exist yet. Should a stage refuse until it exists, or create it? Recommended answer is refuse, pointing at 2.2b's ops step.
  Answered 2026-11-02: refuse.
- **2.2w and 4.1b** [Phase 2, needed by Phase 4]. Set the rollback window length. Recommended answer is 14 days.
  Answered 2026-11-04: 14 days.
- **2.2w** [Phase 2]. Found by 2.2w part (b) (4 Nov 2026). The rehearsal's "run the eval harness once against staging" needs the `CORPUS_READ_SCHEMA` override, which part (c) adds. Move that step to part (c)?
  Answered 2026-11-04: yes; part (c) runs it.
  Answered 2026-11-04 (later the same day, on starting part (c)): no eval in part (c). Carter cares about the corpus being correct, which the release report and 4.2's targeted checks decide, and 2.2b, which the eval's vector reads need, is not merged. So part (c) makes no production export, Qdrant copy or provider spend.
- **2.2w** [Phase 2]. Found by 2.2w part (b) (4 Nov 2026). `chunks` has a unique key on `(document_id, anchor)` that covers retired rows, so when a retired passage's anchor is taken by a current one (a returning text, or a piece whose text moved), the retired row's anchor gains the suffix `#retired-<release>`. Accept the suffix?
  Answered 2026-11-04: accepted. 2.4a gains a check that a suffixed link opens the tombstone notice cleanly, including the `#` through `readerHref` and the reader's anchor lookup.
- **2.2w and 4.2** [Phase 2, needed by Phase 4]. Found by 2.2w part (c) (4 Nov 2026). `CORPUS_READ_SCHEMA` sets `search_path` through connection startup settings, and nothing has yet confirmed that Supabase's pooler on port 5432 passes them on. The pool now refuses to start if it does not, so 4.2 could not silently read live, but it could fail on its first run. Approve one production connection that only runs `SHOW search_path`, reading no tables? Recommended answer is yes, before 4.2.
  Answered 2026-11-04: yes. The pooler passed `search_path` but dropped `default_transaction_read_only`, so the session could have written. Carter chose to set both inside the session on every acquire, and approved a second connection to prove it: through the pooler, read-only held across a reuse of the connection and `CREATE TEMP TABLE` was refused. Neither connection read a table.

### Phase 3

- **3.1** [Phase 3]. Approve each tombstone sentence for the removed authors and works. Also approve the final list of editor-written passages removed under rule G once 1.8a to 1.8c are done. Tertullian's To His Wife and On the Apparel of Women stay or go by R1's dating.
- **3.2** [Phase 3]. Approve every attribution label and note for works that stay, such as "Pseudo-Justin" and the Apostolic Canons note.
- **3.3** [Phase 3]. Approve the list of Latin and Italian passages that stay readable but leave search (about 59), and the note shown on them.
- **3.4** [Phase 3]. Approve the list of rejected-voice ranges (about 270 passages) and each label text, for example "Condemned proposition 10 (condemned by Leo X, Exsurge Domine)" and "Caecilius, pagan objection; answered by Octavius".
- **3.1** [Phase 3]. Approve the result of the rule A check on Cyprian's correspondents: Epistle XXIX (which some editors give to Novatian) and each other sender of a letter in Cyprian's Epistles (C-02).

### Phase 4

- **4.0** [Phase 4]. If search on the new Qdrant collection is too slow in 4.2's pre-cutover run, choose between a paid Qdrant tier for the cutover month and the slower search. The Supabase Pro choice this entry used to hold is settled: the organization is already on Pro (0.6, 30 Oct 2026).
- **4.1a** [Phase 4]. Approve the rules for merging duplicates when a moved passage lands where a user already has the same bookmark or result (for bookmarks, keep the earliest and join both notes when they fit), and the rules for undoing them in a rollback: a user's deletions and edits made since the cutover are kept, and a skipped row never blocks the rollback.
- **4.1b** [Phase 4]. Choose the quiet hour for the cutover, and give go or no-go the day before.
- **4.2** [Phase 4]. Give go or no-go after the accuracy checks on the staging copy. Review the check questions in 4.2's PR.
- **RF-1** [after the republish; it was Phase 4 until 0.3 was dropped on 30 Oct 2026]. Approve the spend for a judged comparison on the republished corpus, then decide whether to change the dedup threshold for chapter-keyed collections (canon law, the Catechism, the Summa, the Bible) from 0.9 to the tested value. The comparison report gives the effect on judge scores and on how often distinct neighbouring passages are dropped.

### Phase 5

- **5.0** [Phase 5, before any addition starts]. Decide how Denzinger is handled for good: its own collection, all its parts placed where they belong, or both. The research listed in 5.0 comes first.
- **5.1a** [Phase 5]. Approve how genre names appear on screen (for example "Apostolic exhortation" for `apostolic-exhortation`).
- **5.1b.1** [Phase 5]. Confirm the three new collection keys and labels: `papal` for "Papal documents", `church-law` for "Church law" and `theologians` for "Theologians and spiritual writers". Approve the merged search prompt for papal documents.
- **5.1b.2** [Phase 5]. Approve the new collection colors and the interim About and Discover wording.
- **5.1b.4** [Phase 5]. Keep a five-line translation of old collection names in the browser so guests' saved drafts do not reset, or delete it too. The spec keeps it.
- **5.2, 5.6a** [Phase 5]. Choose between a paid Qdrant tier and reordering the additions once a publish's projected Qdrant peak passes 3.4 GB of the Free cluster's 4 GiB disk (5.2 step 5). Supabase Pro already covers the database.
- **5.2** [Phase 5]. LEV texts from vatican.va have a basis (Decision log "LEV texts from vatican.va", 29 Oct 2026). Still open: whether to ask the LEV rights office (diritti.lev@spc.va) to confirm the use before any LEV document opens in the full reader; and the Pontifical Biblical Commission and social-doctrine Compendium rows, blocked until confirmed. The papalencyclicals.net translations have no basis and are listed for a decision.
  Answered 2026-10-29 (in part): no permission request has been sent. Carter will ask once everything is working, so nothing yet constrains the full-reader step.
- **5.3b** [Phase 5]. Include the International Theological Commission in the Roman Curia collection, or leave it out. Default is out.
- **5.4** [Phase 5]. A New Hope for Lebanon has no English on vatican.va, only French and Italian, and the vendored file is an empty English page. Recommended answer: keep the French text in the reader with a note, out of search, under the Decision log row "Non-English with no usable English" (R6).
  Answered 2026-10-05: recommendation accepted: the French text, in the reader with a note, out of search (Decision log "Non-English with no usable English").
  Revised 2026-10-29: rule E now keeps all non-English text out of the corpus, so A New Hope for Lebanon is not added.
- **5.4** [Phase 5]. Amoris Laetitia's English exists on vatican.va only as a PDF; the vendored HTML has no text. Recommended answer: vendor the PDF and extract its text (R6).
  Answered 2026-10-05: recommendation accepted: vendor the English PDF and extract its text in 5.4.
- **5.4** [Phase 5]. Confirm that Universi Dominici Gregis (the law on electing a pope) goes in Church law, as the plan's collection table says.
- **5.6b and 5.6c** [Phase 5]. Choose Rickaby's abridged Summa contra Gentiles or the complete English Dominican edition.
- **5.6c** [Phase 5]. The English Dominican Summa contra Gentiles has open scans of books 1 to 3 only; book 4 (1929) has none. Choose the edition knowing that gap, or supply a scan of book 4 from a printing of 1930 or earlier. No recommendation (R6).
- **5.6c** [Phase 5]. Spiritual Combat: both editions the memos named (Burns 1846, Rivingtons 1875) were translated for the Church of England. Recommended answer: the Catholic edition, Philadelphia, Dornin, 1817 (R6).
  Answered 2026-10-05: recommendation accepted: the Catholic Dornin edition, Philadelphia 1817.
- **5.6c** [Phase 5]. Tanquerey: the scans read "Second and revised edition" with no year, and catalogues say 1930 or 1932. Check the title-page verso before ingesting; ingest only a 1930 printing (R6).
  Answered 2026-10-05: recommendation accepted: check the title-page verso before 5.6c starts Tanquerey, and ingest only a 1930 printing.
- **5.6c** [Phase 5]. Catherine of Genoa: the clean CCEL text is a different translation (New York, 1907) from the 1858 Burns one the memo named. Recommended answer: use CCEL 1907 (R6).
  Answered 2026-10-05: recommendation accepted: the CCEL 1907 text; the row now uses it.
- **5.7** [Phase 5]. Approve the final About page wording, especially the list of excluded authors.
- **5.8** [Phase 5]. Choose when to revisit paid licences (the Decision log says after the free phase ships). This blocks the Eastern Catholic code.
- **RF** [after Phase 4]. Put the retrieval follow-up issues in priority order.

---

## C. Things only Carter can supply

### Phase 0

- **0.0** [Phase 0]. The Node.js major version Vercel builds with, if not 20.
  Answered 2026-10-04: Node 24.x, read from the Vercel project settings (`nodeVersion`); CI uses 24.
- **0.2 and R6** [Phase 0, each work before its ingestion PR]. The copyright renewal searches, or approval of them, and the entries in the public rights file that depend on his private rights memos. The Imitation of Christ renewal search is first.
  Answered 2026-10-04: Claude may run the renewal searches (Stanford Copyright Renewal Database, scanned Catalog of Copyright Entries) and record date, place, query and result for Carter to approve, the Imitation of Christ first. 0.2 fills all 421 inventory rows with the facts the files, manifests and memos establish, `unknown` otherwise, each a draft until Carter approves it.
  Answered 2026-10-04: the Imitation of Christ search against NYPL's transcription of the Catalog of Copyright Entries renewals is accepted without a Stanford search, and the same method serves later searches. The inventory key adds the author to collection, source path and title (two ANF01 works share a title) until 2.1's `work_id` replaces it. The canon-law row's rights holder records only what vatican.va shows. A source URL with no record is filled only when the file at that URL matches the locked hash.
  Answered 2026-10-04: planned works get rows in `rights_inventory.json` now, with a `planned_for` field naming the item that will ingest each one; it is null for built works and the ingesting PR clears it (R6).
  Answered 2026-10-05: R6's remaining recommendations are accepted (Little Flowers from the 1899 scan, Rolle's CCEL text with a note, the mixed Pohle-Preuss and Koch-Preuss printings, Alphonsus volumes without an open scan left out, Bellarmine's 1616 text without the 1928 introduction, More's Dialogue of Comfort held). The Schroeder 1937 and Creeds 1931 renewal searches and their 12 rows are approved. The other draft rows stay drafts until approved; the Summa contra Gentiles choice stays open.
- **0.5** [Phase 0, needed before Phase 4]. The Qdrant plan's memory, disk and backup settings, read from the Qdrant console he has access to, plus a few read-only requests.
  Answered 2026-10-30: Free cluster, 1 GiB RAM, 4 GiB disk, 0.5 vCPU, no backups (console screenshots); the read-only requests ran from the home server. The new collection keeps today's in-memory vectors (4.0 step 5, decided by Carter on 30 Oct 2026).
- **0.6** [Phase 0, needed before Phase 4]. The Supabase plan tier and database size limit, read from the dashboard.
  Answered 2026-10-30: Pro, Micro compute, disk 36% used, daily backups (dashboard screenshot and the Supabase connector).

### Phase 1

- **1.8a** [Phase 1]. About 30 minutes to mark 196 bracketed passages in the Fathers as "editor" or "translation".
- **1.5b** [Phase 1]. Someone with access to the printed L'Osservatore Romano weekly English edition of 23 Sep 2016 (p. 9; library copy or subscriber archive) checks the De concordia inter Codices English against it, so 1.5b can use it. Without that check those canons follow rule E (R2).
  Answered 2026-10-04: The print issue could not be reached, but the Canon Law Society of Great Britain and Ireland's English Code prints the same English word for word for 111, 112, 535 §2, 868 §1 2°, 1108 §3, 1109, 1111 §1, 1112 §1, 1116 §3 and 1127 §1 (R2, "Follow-up"). Carter accepts that agreement in place of the print check. Because rule E works on whole canons, all of canon 868 (including the agreed §1 2°) stays under rule E until 868 §3 is checked, and so does all of 695, whose §1 has no English; the other nine texts use the English. Still needed: the print check for 868 §3 only.
- **1.2f, 1.2e and 5.6c** [Phase 1 for councils 8 to 18, Phase 5 for scanned books]. About 30 to 60 minutes of a person's time per scanned work, to check 20 random passages against the page images.
  Answered 2026-11-02: the sample is a quarter of a work's passages, at least 5 and at most 20, instead of 20 per work (Decision log "OCR clean-up: model, spend, sample and inputs"). For councils 8 to 18 and 1.3d that is about 230 passages, 6 to 11 hours, instead of about 640.

### Phase 5

- **R6, 5.2 and 5.6c** [Phase 5, some earlier]. All correspondence with rights holders: CCEL, ecatholic2000.com, NINS for the Newman Reader, and the Aquinas Institute if its Summa contra Gentiles text is used.
