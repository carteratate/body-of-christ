# Prompt: plan the work that closes the corpus-review gaps

You are planning, not implementing. Repo: `/Users/cartertate/repos/body-of-christ` (branch `master`, `python3`). Carter Tate owns the project. Work date: from 9 October 2026.

## Why this thread exists

The corpus cleanup plan is partway through Phase 0. 0.0, 0.4, 0.1a, 0.1b and 0.1c are merged, and the next item in the plan is **2.1** (frozen IDs, structural anchors, the removal registry). Before 2.1 started, four corpus reviews ran on 6 October 2026 and found about 30 problems that the plan and its specs do not handle, or handle only in part. A synthesis merged and verified them.

Your job is to turn those findings into planned work, so the gaps are closed by the items that should own them **before the rest of the plan resumes**. Concretely:

1. Decide which findings must change a spec before 2.1 starts, because 2.1 freezes IDs, anchors and passage fields that the fixes depend on.
2. Decide which become new items, and where they sit in the phase order and the existing GitHub issue tree.
3. Record each remaining finding as an extension of an existing item.
4. Get Carter's decisions.
5. Draft the spec edits and issue texts.

Do not re-audit the corpus. The findings were verified twice. Re-check a fact only when a planning decision turns on it, and say so when you do.

## Read these, in this order

1. `CLAUDE.md`. Architecture and the active-work note.
2. `docs/research/2026-10-06-corpus-review-synthesis.md`. **The primary input.** It has merged findings C-01 to C-30 with severity, evidence, suggested owner and check; the saved-user-data impact; the disagreements and how they were settled; what is still unverified; 11 questions for Carter; and a suggested next step.
3. The plan, `docs/2026-09-28-corpus-cleanup-plan.md`, all of it: the inclusion rules A to H, the Decision log, D1 to D11, and the phase and PR table.
4. `docs/corpus-cleanup/README.md`. The procedure every item follows, including what an implementer may change in other specs (§3) and the review-before-PR rule.
5. `docs/corpus-cleanup/NEEDS-CARTER.md`. What is already decided ("Answered" lines) and what is open.
6. The specs, as each finding sends you there:
   - `P0-checks-identity-research.md`: 0.1a, 0.1b, 0.1c "As built", 2.1, R1 to R6.
   - `P1a-adapters-councils-papal-bible-canon.md`: 1.10a to c, 1.1, 1.2a to f, 1.3a and b, 1.4a to c, 1.5a and b.
   - `P1b-adapters-catechism-summa-fathers.md`: 1.6, 1.7, 1.8a to e, 1.9.
   - `P2-P3-schema-reader-policy.md`: 2.2a, 2.2w, 2.2b, 2.2c, 2.3, 2.4a to c, 3.1 to 3.3.
   - `P4-P5-republish-expand.md`: 4.0, 4.1a, 4.1b, 4.2, RF.
7. The four review reports. Use them for detail the synthesis summarises; their finding IDs are cited in each C-finding.
   - `docs/research/2026-10-06-corpus-review-opus.md` (A-001 to A-024).
   - `docs/research/2026-10-06-corpus-review-opus-2.md` (B-001 to B-015).
   - `docs/research/2026-10-06-corpus-review-sol.md` (Sol A-001 to A-019).
   - `docs/research/2026-10-06-corpus-review-sol-followup.md` (Sol B-001 to B-005).
8. Reproduction material, only if you need to re-check a fact. These folders are gitignored, local to Carter's Mac, and hold scripts and pickles. `datapipeline/releases/local/review-opus/corpus.pkl` holds the master build plus the 6 Oct snapshot; `qvecs.npy` and `qpayloads.pkl` are a dump of the production vectors.
   - `datapipeline/releases/local/review-opus/`
   - `datapipeline/releases/local/review-opus-2/`
   - `datapipeline/releases/local/review-sol/`
   - `datapipeline/releases/local/review-sol-followup/`
9. `datapipeline/checks/known_defects.json` and `datapipeline/checks/health_patterns.json`, where new checks will land.

## Recommended starting position

This is the first reviewer's view, written for this thread. Test it against the plan and the specs, change it where they disagree, and give your reasons.

**A. Settle before 2.1 starts.** These touch what 2.1 freezes or defines.

| Finding | Why it is pre-2.1 | Likely change |
|---|---|---|
| C-10, split pieces shift paragraphs | 2.1 and 0.1c define what "same ID, same text" means | Per-piece stability in 0.1c; 2.1's rule for which piece keeps an ID when boundaries move; 4.1a redirects for shifted pieces |
| C-07, three Summa keys hold two articles | 2.1 assigns structural Summa anchors and IDs | 2.1 gives the three trailing articles their own anchors and new IDs, plus redirects |
| C-04, C-14, Summa roles and the 1.7 rework | 2.1's Summa anchor scheme is built from the article parts 1.7 recognises | Agree the part model, including reply targets and supplied or editorial parts, before 2.1 freezes Summa anchors |
| C-01, rejected-voice role | D11 says passage fields are defined once, in 2.1 | Add a `role` (or `voice`) field to the `Passage` model and the passage registry beside `searchable`, `language` and `passage_author` |
| C-02, C-15, credits | 2.1 owns the attribution fields and the work model (D6) | Per-letter works for the Epistles of Cyprian; references and the embedding prefix built from the registry credit, not the raw author |
| C-13, canon-law chapter keys | 2.1 records `live_anchor` and the chapter remap baseline | Decide full-path canon chapter keys now, so the registry and chapter redirects are built once |

**B. New items to add to the plan.** Give each a number in the phase table.

1. **Catechism text fix (C-03)** as its own small PR ahead of 1.6, since IDs do not move. It needs a per-paragraph word-completeness check and a CCC 1471 sentinel in 0.1a.
2. **Rejected-voice roles (C-01)**: registry ranges, `passage_role` and prompt changes in the API, and card display. It touches 1.3a, 1.2a, 1.8c, 3.2 and 2.4b. Carter must choose between labelling and keeping these passages out of search (synthesis Q1).
3. **Dedup and embedding decision (C-09, C-21, C-23)** before 4.1b, so the republish embeds once: threshold or clean-text comparison, the neighbour window skipping unsearchable passages, and an input hash stored per point. Evaluated in 4.2.
4. **Keyword index (C-16)**: reopen 2.2c to strip verse markers and add references, inside the 4.0 compaction window.
5. **Independent Summa comparison (synthesis §5)** as a research item (R7), blocking 1.7: the Leonine comparison of the four core parts plus the Supplement, and the five omitted units.
6. **Snapshot export with `document_chapters` (synthesis §5, Q9)**: a small 0.1c follow-up.

**C. Extensions of existing items.** Record each in its spec's "Current state", "Changes" and "Acceptance checks", with the finding ID. For example:
- 1.3a: C-05, C-06, C-08, C-17, C-18, C-26, C-30;
- 1.4a: C-11, C-24;
- 1.5a: C-13, C-19;
- 1.1: C-17, C-20;
- 1.8a: C-12, C-22;
- 1.10a: C-15, C-16;
- 1.10c: C-15;
- 2.4c: C-25;
- 3.1: C-02;
- 3.2: C-15;
- 1.2b: C-05.

Use the owners the synthesis suggests unless the specs show a better one.

## Procedure

1. **Read, then write the plan in a working file first**: `docs/corpus-cleanup/REVIEW-GAPS-PLAN.md`. For every C-finding, give:
   - the decision (pre-2.1 spec change, new item, extension, or no action);
   - the owning item;
   - the dependency and its place in the order;
   - the check id it adds;
   - the Carter question it waits on, if any.
   Add an ordered list of the work that must finish before 2.1 starts, and how the phase table changes.
2. **Ask Carter in one message, before editing any spec.** Ask the synthesis's 11 questions plus any new ones your planning raises. Follow his format:
   - lead with the literal question;
   - then the context and any term defined in plain words;
   - then the options and what each causes;
   - then your recommendation.
   Ask only about decisions that change the design; settle the rest with the recommended default and say so. Record the answers as `Answered <date>:` lines in `NEEDS-CARTER.md`, and in the plan's Decision log where they settle a rule.
3. **Then draft the edits on a branch** (for example `docs/review-gaps`):
   - the plan's phase table and Decision log;
   - each affected spec, within README §3's limits, citing the C-finding;
   - new item specs in the standard template (goal, current state with evidence, changes, acceptance checks, production safety, Needs Carter, out of scope);
   - new `NEEDS-CARTER.md` entries;
   - planned additions to `known_defects.json` described in the specs, not added yet.
   Commit locally, one commit per item.
4. **Draft the GitHub issue changes** in `docs/corpus-cleanup/ISSUES-DRAFT.md`. The cleanup issues already exist: 80 issues labelled `corpus-cleanup`, opened 29 Sep 2026, with parents #132 (P0) to #194 (P5). The plan's "GitHub issues: not opened" line is stale. Read them with `gh issue list --label corpus-cleanup --state all --limit 200` (read-only), then draft:
   - new child issues for the new items, each under its phase parent;
   - comment or body updates for existing item issues that gain scope from a C-finding.
   Do not create or edit issues. Carter approves every issue, push and PR.
5. **Before proposing a PR, run a fresh-context review** with a subagent on model `opus` that has a shell. Address its findings in the PR description.

## Rules

- No change to live data. That means production Supabase (project `hvmgffvimqgiejmxwhwq`) and production Qdrant. No paid API calls. No pushes, issues, PRs or messages without Carter's explicit yes.
- Never put rights or licensing opinions in a repo file; say them in chat. Quote copyrighted corpus text sparingly (a few words), since the repo is public.
- The five review files under `docs/research/2026-10-06-corpus-review-*.md` and `docs/corpus-cleanup/CORPUS-REVIEW-PROMPT.md` are untracked. Ask Carter whether to commit them with the plan before referencing them from tracked specs.
- The plan's order still holds: fix and republish the current corpus before reorganising or expanding. Do not pull Phase 5 work forward.
- Keep `CLAUDE.md`'s "Active work" note and the plan's "Current state" table accurate if the order changes.

## Deliverable at the end of the thread

- `REVIEW-GAPS-PLAN.md` complete.
- Carter's answers recorded.
- Spec and plan edits committed on the branch.
- `ISSUES-DRAFT.md` written.
- A short chat summary:
  - what must finish before 2.1, in order;
  - the new items and where they sit;
  - what is still waiting on Carter;
  - anything you found that the synthesis got wrong.
