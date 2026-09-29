# How to implement a corpus-cleanup item

Every item in this folder follows this procedure. Read it before starting any item, whoever asked you to start.

Sources of truth, in order:

1. The plan, `docs/2026-09-28-corpus-cleanup-plan.md`, above all its Inclusion rules, Decision log and Cross-cutting design decisions D1 to D11.
2. The item's spec in this folder.
3. The code on `master`.

Where two disagree, the higher one wins. If the higher one looks wrong, ask Carter; do not act on your own reading.

## 1. Before writing code

1. Read the plan's Inclusion rules, Decision log and D1 to D11, the item's spec, and the spec of every item it depends on. Check that each dependency is done in the way its "Depends on" line says: merged for a PR, closed for a research item, run for an ops step, deployed or applied where the spec says so. If one is not, stop and tell Carter.
2. Open `NEEDS-CARTER.md` and find every entry for the item in sections B (decisions) and C (things Carter supplies) that has no "Answered" line. Section A approvals are asked later (step 5).
3. Ask Carter about them in one message, before any code. For each question give:
   - the item ID;
   - one plain sentence he can answer without reading the spec, with any term defined;
   - the recommended answer, if the spec gives one.

   Do not ask about anything the plan or the Decision log already settles. If reading the code raises a new question that would change the design, add it to the same message. Questions that change nothing can be settled with the spec's default and mentioned in the PR.
4. Record every answer in the same change set as the work. For a PR item that is the PR. A research item records them in the PR that adds its findings file (`docs/research/R*.md`). An ops item with no PR (0.5, 0.6, 4.0 and the ops steps of 4.1b) records them in a small docs PR opened right after the step, and in the tracking issue.
   - In `NEEDS-CARTER.md`, add a line under the entry, `Answered <YYYY-MM-DD>: <the answer>`.
   - If the answer settles a design choice, also add a row to the plan's Decision log ("Decided by Carter on <date>"), and edit the item's spec so it states the chosen option instead of the choice.
5. Approvals in section A are not asked up front. Each live-data step, ops step or push is asked for when it is about to run, and approval of a PR is not approval of its live step (plan, "Start here").

## 2. While implementing

- Build what the spec says. Where the code shows a fact in the spec is wrong (a file path, a line number, a count, an "unverified" note), fix the spec as described in section 3.
- Where the code shows a design in the spec is wrong or cannot work, stop and ask Carter. Do not change the design and then edit the spec to match what was built.

## 3. Updating other specs

When an item is done, other specs that mention it may be out of date. Find them by searching this folder for the item's ID and for the names of what it defines, for example:

```bash
grep -n "2\.2w\|UserDataRemap\|publish\.py" docs/corpus-cleanup/*.md
```

**Allowed**, without asking:
- facts that are now known: paths, line numbers, function and field names as actually built, measured counts and sizes, and "unverified" or "not verified" notes that the work has resolved;
- cross-references that now point at the wrong item or section;
- a new "Needs Carter" entry the work uncovered, added both to the spec and to `NEEDS-CARTER.md`.

**Not allowed**, ask Carter instead:
- anything in the plan's D1 to D11, Inclusion rules or Decision log, except the Decision log rows that step 1.4 records;
- another item's design: its schema, interfaces, identifiers, file formats, lock format, removal reasons, vocabularies, dependencies or merge order;
- removing or rewording another item's "Needs Carter" entries or acceptance checks.

How:
- Put every spec edit in its own commit, separate from code.
- List each one in the PR description under "Spec changes": the file, the item, what changed and why.

## 4. Review before the PR

Before opening the PR, a fresh-context reviewer (one that has not seen the work) checks two things:
- the code against the item's spec and acceptance checks;
- the spec commit against D1 to D11 and the rules in section 3.

The PR description quotes the reviewer's findings and what was done about each.

## 5. One at a time for shared items

0.4 (publish lock), 2.1 (registry), 2.2a (migration) and 2.2w (writer) define mechanics every other item uses. While one of them is in progress, start no other item that depends on it, and no other item that edits its spec. For all other items, parallel work is fine. If two open PRs edit the same spec file, the one that merges second rebases and re-checks its spec changes against the first.
