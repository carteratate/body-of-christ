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
- **Supabase Pro** is the paid plan. The free plan turns the database read-only above 500 MB, and the cleanup may briefly pass that.

---

## A. Approvals of steps that touch live data, production systems or the public repo

### Phase 0

- **Plan, all phases** [Phase 0]. Approve opening the GitHub issues from these specs, one parent per phase. Every push, issue and PR on the public repo needs his yes first.
- **0.0** [Phase 0]. Approve the first push and PR, which adds automated tests on GitHub and a PR template. After it merges, turn on branch protection for `master` in GitHub settings so the three test jobs must pass (only Carter can change that setting).
- **0.4** [Phase 0]. Approve the publish-lock PR. It must merge before any Phase 1 PR.
- **0.1c** [Phase 0]. Run, or approve running, `export_live_snapshot.py`. It reads production without changing anything and copies the corpus text and anonymous counts of saved rows (no user IDs, no query text) to his Mac. It is re-run before Phase 4 and whenever a report needs fresh counts.
- **0.6** [Phase 0]. Approve read-only size queries against production.
- **0.3** [Phase 0]. Approve the baseline search evaluation, which costs about $12 in AI provider fees. Confirm it runs before any live change (the 0039 migration, the alias step or an early retirement), so it records the corpus as it is today. The run changes nothing in the database.
- **R6** [Phase 0, blocks Phase 1 items 1.2c, 1.2d, 1.8d]. Approve each set of source downloads. The request states the file names and sizes each time.

### Phase 1

- **1.2f** [Phase 1]. Approve a spend ceiling per work for the AI step that corrects scanning errors in scanned books (first used on councils 8 to 18). No spec proposes a figure.

### Phase 2

- **2.2a** [Phase 2]. Approve a pg_dump of production for a local timing rehearsal of the new database structure. Then approve applying migration 0039 to the live database. It adds columns and tables only and changes nothing users see.
- **2.2b** [Phase 2]. Approve two steps on live systems. The first creates the Qdrant alias `chunks_live` (a second name for today's search index, so later switches take one step) and an index on the new "searchable" field. The second sets one environment variable on Railway and restarts the API.
- **2.2w and 4.1a** [Phase 2, repeated in Phase 4]. Approve the pg_dump for the full local rehearsal of the new publish process. The 2.2a timing rehearsal can share this dump if the two run close together.
- **2.2w** [Phase 2 to 4]. Approve the embedding spend for the first full local rehearsal stage (2.2w's or 4.1a's, whichever runs first), about 11 million tokens, about $1.40 at today's list price (to be checked before the run). It fills a local cache, so later rehearsals and the production run cost between $0 and the same amount, depending on how much the build changed in between.
- **1.8d and 2.2w, only if B-1.8d below is yes** [Phase 2]. Approve the lock-file PR, the one live step that retires On the Incarnation early, the API restart, and the later PR that removes the lock entry.

### Phase 4

- **4.0** [Phase 4]. Approve the time and the run of `VACUUM FULL`, which compacts the main table. Search and the reader pause for about a minute while it runs.
- **4.1b** [Phase 4]. Approve, one at a time:
  - the PR that freezes the Phase 4 build, including any council that shows a "translation in preparation" notice because its public-domain text is not ready;
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
- **4.2** [Phase 4]. Approve the spend for the before and after search evaluation. The report states the amount.

### Phase 5

- **5.1a** [Phase 5]. Approve creating a Qdrant index, only if the check finds one missing.
- **5.1b.3** [Phase 5]. Approve the migration, the lock-file PR, the apply and index switch, the script that rewrites collection names in saved preferences and searches, and the API restart.
- **5.1b.4** [Phase 5]. Approve the migration that removes the old collection names.
- **5.3a, 5.3b, 5.4, 5.5, 5.6a, 5.6b, 5.6c** [Phase 5]. For every addition, approve its lock-file PR and its apply, and for 5.3a also its migration and the PR that makes the Roman Curia collection visible.

---

## B. Decisions

### Phase 0

- **0.4** [Phase 0]. Agree to the lock rules. Every datapipeline write to the live corpus or search index, including emergency repairs, needs a reviewed PR adding a lock entry. The only exception is a rehearsal where the database and Qdrant both run on his own Mac. Steps done by hand (migrations, alias and index creation, `VACUUM FULL`, post-window deletions) are outside the lock and approved one at a time. An entry stays until its rollback window closes. No entry is added before Phase 4 except, if he chooses, the On the Incarnation retirement. Recommended answer is yes.
- **2.1** [Phase 0]. Approve four things about the new ID registry.
  - Passages get anchors from the source's own structure (the ID of each section in the source file) instead of from label text. A choice remains on how dots in those IDs are written, kept as dots or turned into dashes. The spec recommends no option; either works.
  - The passage registry, about 7 MB of IDs and anchors and no text, goes into the public repo.
  - The removal-registry format, whose tombstone sentences are public.
  - One new removal reason, `rolled-back`, used only for passages that an undone publish had added. The plan's decision D11 lists the reasons and does not name this one, so the plan needs a one-line update if he agrees.

  Recommended answer is yes to all four.
- **0.1a** [Phase 0]. Review the list of known defects that the new tests start out expecting. No decision beyond checking it.
- **0.2** [Phase 0]. Confirm that the fields of the public rights file (edition, translator, public-domain basis, renewal search, credit line) are safe to publish. Also decide what to do with Amoris Laetitia, which is downloaded but was never published and has no decision on record. The spec gives no recommendation.
- **0.3** [Phase 0]. Approve the list of about 30 targeted test questions, written fresh rather than taken from users' searches.
- **R1** [Phase 0 research, answer needed by Phase 3]. Decide these points.
  - Hippolytus led a rival group in Rome, outside communion, from about 217 to about 235. The Refutation of All Heresies (377 passages) is dated to the 220s. Under rule A a work written outside communion is removed, and he is not a Doctor of the Church. The spec gives no recommendation.
  - Where standard chronologies disagree on a date, which one to use.
  - Any other finding R1 lists "for Carter".
  - The Pseudo-Chrysostom question, which 5.6b also needs. The Catena Aurea quotes a commentary most scholars now credit to an Arian writer. Keep those quotations labeled "Pseudo-Chrysostom", or leave them out. No recommendation yet.
- **R2 and 1.5b** [Phase 1]. Approve the English sources found for canons printed in Latin, and the label for unofficial English. Suggested label is "Unofficial English translation (L'Osservatore Romano). The Latin text is official."
  Answered 2026-10-04: Approved, with the suggested label, for 111, 112, 535 §2 and 868 §1 2° (and 868 §3 and the six marriage canons below), using the L'Osservatore Romano English of 23 Sep 2016, p. 9, but only once its text has been checked against the printed page; the EWTN reprint has typesetting errors and is not used unchecked. Any canon whose print text cannot be checked follows rule E. 295 and 296 follow rule E (current Latin, out of search): the only English, a Vatican News article, mistranslates 295 §2. 579, 695 §1 and 700 follow rule E. Add canon 868 §3 (De concordia art. 5) in 1.5b. No reader note on 360, 361 or 948, whose text is in force. Extend 1.5b to the marriage canons 1108, 1109, 1111, 1112, 1116 and 1127 (De concordia arts. 6-11).
- **R3** [Phase 1]. Choose how the Greek additions to Esther are numbered, if no Church source settles it. R3 will give a recommendation.
  Answered 2026-10-04: No Church source settles it (R3). Keep WEB-C chapter and verse numbers and title the restored passages by addition letter; record the Nova Vulgata and NAB ranges in metadata for whole additions only.
- **R4** [Phase 1]. Decide whether the "Contents" summaries in the Refutation of All Heresies are the author's own, only if the sources disagree.
- **R5** [Phase 1]. If the translator of On Loving God cannot be traced, approve the replacement translation R5 proposes.

### Phase 1

- **1.1** [Phase 1]. Keep the "Preliminary Note of Explanation" as part of Lumen Gentium. Recommended answer is yes, as its own chapter.
- **1.2a** [Phase 1]. Approve the register of council texts that have no public-domain English translation. Those texts show a "translation in preparation" notice instead. Chiefly Florence's doctrinal decrees are affected.
- **1.3b** [Phase 1]. Confirm which three documents are the "Jubilee bulls" filed as encyclicals. Also decide whether Ineffabilis Deus and Munificentissimus Deus are labeled "apostolic constitution" or "bull". The spec gives no recommendation.
- **1.4a** [Phase 1]. Keep `song-of-solomon` inside link addresses while the book's title changes to "Song of Songs". Users never see the address. Recommended answer is keep.
- **1.4b** [Phase 1]. Renumber only Joel and Malachi to the Church's official Latin Bible numbering, or every place where Church documents cite a different chapter. Recommended answer is Joel and Malachi now, the rest as a later issue.
- **1.4c** [Phase 1]. Give the deuterocanonical books' new shorter passages titles from the old Douay-Rheims chapter summaries, or leave them untitled. Recommended answer is untitled for now.
- **1.6** [Phase 1]. Show Catechism paragraph numbers inside passage text as "§2267". Recommended answer is yes; the work goes ahead with this if there is no answer.
- **1.7** [Phase 1]. Add Aquinas's own short introductions at the start of 611 questions and 3 treatises (about 297,000 characters), which are missing today. Recommended answer is yes, since they are his own words.
- **1.8b** [Phase 1]. Split two Augustine volumes ("Doctrinal Treatises", "Moral Treatises") into their 16 separate works, so On Lying is cited as On Lying. Bookmarks survive either way. Recommended answer is yes.
- **1.8c** [Phase 1]. Two points.
  - Label the Shepherd of Hermas's author as "Hermas" and its books "The Shepherd: Visions", "Commandments" and "Similitudes".
  - Remove the Balsamon and Zonaras commentary printed inside Peter of Alexandria's canons, rather than keep it under their own names.

  The spec proposes yes to both.
- **1.8d** [Phase 1, acted on in Phase 2]. The current translation of Athanasius's On the Incarnation (Lawson, 1944) is still under copyright. Hide it before Phase 4 (early retirement), or leave it visible until Phase 4 replaces it with Robertson's public-domain translation. Hiding it waits for 0.3, 2.2a, 2.2b, 2.4a and 2.4b to ship. Deleting it is not an option, because that would erase a user's saved search. The spec gives no recommendation.
- **1.8e** [Phase 1]. About 30 whole works in the downloaded Fathers volumes never reach the corpus. Choose which to add. Recommended answer is none before Phase 4 except Asterius Urbanus, and the rest later with normal rule checks.
- **1.9** [Phase 1]. Add Anselm's reply to Gaunilo ("Anselm's Apologetic"). Default is no. Gaunilo's own piece would need its own rule check.

### Phase 2

- **2.2c** [Phase 2]. Confirm that the keyword-search index needs no rebuild, because fixed text updates it automatically. Recommended answer is confirm.
- **2.3** [Phase 2]. Set the wording of the source credit line wherever 0.2 has not settled it (for example "Text: Libreria Editrice Vaticana", "Sourced via CCEL.org").
- **2.4a** [Phase 2]. When a saved search or bookmark points at a removed passage, show no text (title, author, reference and one sentence of reason), or keep showing the text under a "removed" banner. Recommended answer is no text.
- **2.4b** [Phase 2]. Approve the wording pattern of tombstones.
- **2.4c** [Phase 2]. Approve the corrected names on the About page. Origen, Chrysostom, Bonaventure, Hildegard and Duns Scotus come out; Irenaeus, Bernard of Clairvaux and Thomas à Kempis go in.
- **2.2w and 4.1b** [Phase 2, needed by Phase 4]. Set the rollback window length. Recommended answer is 14 days.

### Phase 3

- **3.1** [Phase 3]. Approve each tombstone sentence for the removed authors and works. Also approve the final list of editor-written passages removed under rule G once 1.8a to 1.8c are done. Tertullian's To His Wife and On the Apparel of Women stay or go by R1's dating.
- **3.2** [Phase 3]. Approve every attribution label and note for works that stay, such as "Pseudo-Justin" and the Apostolic Canons note.
- **3.3** [Phase 3]. Approve the list of Latin and Italian passages that stay readable but leave search (about 59), and the note shown on them.

### Phase 4

- **4.0** [Phase 4]. If compaction may push the database above 480 MB, choose between running it anyway and accepting a possible short read-only period, and a month of Supabase Pro. After the rehearsal measures the real peak of the apply, make the same choice for the apply. No recommendation; the rehearsal numbers decide.
- **4.1a** [Phase 4]. Approve the rules for merging duplicates when a moved passage lands where a user already has the same bookmark or result (for bookmarks, keep the earliest and join both notes when they fit), and the rules for undoing them in a rollback: a user's deletions and edits made since the cutover are kept, and a skipped row never blocks the rollback.
- **4.1b** [Phase 4]. Choose the quiet hour for the cutover, and give go or no-go the day before.
- **4.2** [Phase 4]. Give go or no-go after the evaluation on the staging copy. Also confirm that 0.3 ran with AI judging, which the comparison needs.

### Phase 5

- **5.1a** [Phase 5]. Approve how genre names appear on screen (for example "Apostolic exhortation" for `apostolic-exhortation`).
- **5.1b.1** [Phase 5]. Confirm the three new collection keys and labels: `papal` for "Papal documents", `church-law` for "Church law" and `theologians` for "Theologians and spiritual writers". Approve the merged search prompt for papal documents.
- **5.1b.2** [Phase 5]. Approve the new collection colors and the interim About and Discover wording.
- **5.1b.4** [Phase 5]. Keep a five-line translation of old collection names in the browser so guests' saved drafts do not reset, or delete it too. The spec keeps it.
- **5.2, 5.6a** [Phase 5]. Choose between Supabase Pro and reordering the additions once the projected database size passes 450 MB.
- **5.3b** [Phase 5]. Include the International Theological Commission in the Roman Curia collection, or leave it out. Default is out.
- **5.4** [Phase 5]. Confirm that Universi Dominici Gregis (the law on electing a pope) goes in Church law, as the plan's collection table says.
- **5.6b and 5.6c** [Phase 5]. Choose Rickaby's abridged Summa contra Gentiles or the complete English Dominican edition.
- **5.7** [Phase 5]. Approve the final About page wording, especially the list of excluded authors.
- **5.8** [Phase 5]. Choose when to revisit paid licences (the Decision log says after the free phase ships). This blocks the Eastern Catholic code.
- **RF** [after Phase 4]. Put the retrieval follow-up issues in priority order.

---

## C. Things only Carter can supply

### Phase 0

- **0.0** [Phase 0]. The Node.js major version Vercel builds with, if not 20.
  Answered 2026-10-04: Node 24.x, read from the Vercel project settings (`nodeVersion`); CI uses 24.
- **0.2 and R6** [Phase 0, each work before its ingestion PR]. The copyright renewal searches, or approval of them, and the entries in the public rights file that depend on his private rights memos. The Imitation of Christ renewal search is first.
- **0.5** [Phase 0, needed before Phase 4]. The Qdrant plan's memory, disk and backup settings, read from the Qdrant console he has access to, plus a few read-only requests.
- **0.6** [Phase 0, needed before Phase 4]. The Supabase plan tier and database size limit, read from the dashboard.

### Phase 1

- **1.8a** [Phase 1]. About 30 minutes to mark 196 bracketed passages in the Fathers as "editor" or "translation".
- **1.5b** [Phase 1]. Someone with access to the printed L'Osservatore Romano weekly English edition of 23 Sep 2016 (p. 9; library copy or subscriber archive) checks the De concordia inter Codices English against it, so 1.5b can use it. Without that check those canons follow rule E (R2).
- **1.2f, 1.2e and 5.6c** [Phase 1 for councils 8 to 18, Phase 5 for scanned books]. About 30 to 60 minutes of a person's time per scanned work, to check 20 random passages against the page images.

### Phase 5

- **R6, 5.2 and 5.6c** [Phase 5, some earlier]. All correspondence with rights holders: CCEL, ecatholic2000.com, NINS for the Newman Reader, and the Aquinas Institute if its Summa contra Gentiles text is used.
