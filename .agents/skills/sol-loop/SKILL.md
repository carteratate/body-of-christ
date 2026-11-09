---
name: sol-loop
description: Sol loop. Use whenever the user asks for a sol loop, or for Sol to review a change or PR — Sol reviews through the Codex CLI, you fix its findings, and the loop repeats until Sol would merge it.
---

# sol-loop

Get a change or PR into shape before the user looks at it. Sol (OpenAI's GPT
Sol, run through the `codex` CLI) is the only reviewer; you are the author.
Each round Sol reviews, you fix what holds up, and Sol checks again.

The user is not in the loop. Fix, decline, and dispute findings yourself; the
user reviews once, at the end, from your report.

Fix the cause, not the reported scenario: state the rule the code should
follow, make the smallest change that makes it hold, and check the
neighbouring cases that rule covers. Stay out of code the finding does not
touch, and don't be scared to push back.

## Budget

- Default: 3 rounds total. Round 1 is full. Later rounds check only
  changed code and open findings.
- Extend to 5 only for security, permissions, auth, data loss, or
  state/concurrency, while a blocker or should stays open with evidence. Or when
  the user asks.
- Stop early if a round returns only nits. Declined nits and comment,
  doc, or format-only fixes need no new round.
- One reviewer only. Sol must not start subagents or reviewers.
- Up to 3 loops per change. Each agreement is followed by a fresh review of
  the whole diff (step 6); if it finds a blocker or should, it is round 1 of
  the next loop, with the round budget reset.
- Keep a ledger: id, severity, outcome, usage per round from Codex's output.
  Never guess it. Number rounds across loops (r1, r2, ...) and note where each
  loop starts and its `thread_id`.

## 1. Scope

Run `git status --short`. Do not stash, discard, or include unrelated
changes. Limit review to the change paths if they separate cleanly.
Otherwise stop and ask; this is the one question allowed, and it comes before
round 1.

Find the base after `git fetch origin`:

- PR: `gh pr view <n> --json baseRefName,headRefOid`. Check out the branch
  only if clean. Confirm `HEAD` is the PR head, or ahead only by this
  change. Base: `git merge-base HEAD origin/<baseRefName>`.
- Local: `git merge-base HEAD origin/<default-branch>`. No remote: a base
  the user names, or `HEAD` for uncommitted changes only.

The change is base to working tree in those paths, with untracked files.
Use one diff command all rounds. State intent and out-of-scope in 1-2
sentences. Run the covering checks the repo's `CLAUDE.md` / `AGENTS.md` names.
Do not send code this change breaks. Note missing or pre-failing checks in the
brief.

## 2. Start Sol

Before round 1, `codex --version` must match `npm view @openai/codex version`.
If it is behind, run `npm i -g @openai/codex@latest` first: a stale CLI lists
an older Sol first, and the loop silently reviews with it (0.154.0 picked
`gpt-5.6-sol` over `gpt-6.1-sol`).

Pick the model once: the first `*-sol` slug in `codex debug models`, unless
the user named one. Pass it with `-m` on every call, resumes included: a resume
without `-m` falls back to the config default. If Codex rejects the model or
login, report the blocker. Do not substitute a model.

Make a run directory (your scratchpad, else `mktemp -d`). Every round writes
`briefN.md`, `rN.md` (Sol's reply), `rN.jsonl` (events), `rN.err`, and you keep
`ledger.md` there, so the loop survives context compaction.

Run from the repo root, as a background command, and wait for its completion
notice. Do not poll, and do not edit scoped files while Sol runs.

Round 1:

```bash
codex exec --json -m <model> -s read-only -c model_reasoning_effort=high \
  -o <run>/r1.md - < <run>/brief1.md > <run>/r1.jsonl 2> <run>/r1.err
```

Later rounds resume the same Sol session. `resume` takes no `-s`, so the
sandbox goes through `-c`:

```bash
codex exec resume <thread_id> --json -m <model> -c sandbox_mode=read-only \
  -c model_reasoning_effort=high \
  -o <run>/rN.md - < <run>/briefN.md > <run>/rN.jsonl 2> <run>/rN.err
```

From `rN.jsonl`: `thread_id` is in the `thread.started` line (round 1; save
it), and token usage is in the `turn.completed` line (copy it to the ledger).
Verify each round actually ran as asked: the session log
(`grep -rl <thread_id> ~/.codex/sessions`) has `turn_context` lines carrying
`model`, `effort` and `sandbox_policy`. Read-only and high are what
you expect; anything else, stop and report.

After each round, `git status --short` must match what it was before Sol ran.
If Sol changed files, stop and report; never keep its edits.

A non-zero exit, a timeout, an empty `rN.md`, or a reply without a verdict is
not approval. Re-run that round once. If it fails again and resume is the
problem, start a fresh `codex exec` with the round 1 brief plus the ledger.
Otherwise report the blocker.

Round 1 brief:

```
Review only. Do not edit, commit, push, comment on PRs, or start subagents.
Repo: <abs path> Base: <sha> Intent: <intent> Out of scope: <scope> Checks: <results>
See: git diff <base> [-- <paths>]; git status --short (read untracked).
You own this codebase and you are the one who merges. Read surrounding code.
Find bugs, broken callers, mismatch with intent.
Skip style unless it hides a bug. Hold to the smallest change. Flag code,
tests, or guards the intent does not need. Other paths, rare cases, small
perf, extra compat: nits. Exception: in code that writes or publishes data
(migrations, publish, rollback, store repair), failure and recovery paths are
in intent.
blocker = intended case wrong. should = real bug callers will hit, in intent. nit = rest.
Would you merge this code as it stands? Answer that first.
Reply:
VERDICT: MERGE or CHANGES
S1 [blocker|should|nit] <file>:<line> <claim>. Fix: <suggestion> (stable ids)
```

## 3. Answer findings

You fix; Sol never does. Check each finding and severity yourself. Another
path, rare case, or small cost is a nit, whatever label it came with, except
a failure or recovery path in code that writes or publishes data.

- Agree: smallest fix that makes the rule hold. Prefer delete or narrow over
  new lock, cache, helper, or option. Before sending, check the cases next
  to the reported one that the fix changes (a new guard: what else does it
  refuse?). Add one focused test that fails without the fix, if intent needs
  it.
- Disagree: say why, with evidence (file:line, test, output).
- Out of scope or nit: decline in one line. List as follow-up.

Update the ledger. Re-run checks and `git diff --shortstat <base>`. If
review grew the diff, cut first. Do not agree just to end the loop.

## 4. Next round

Start one only if budget remains and a blocker or should is open, behavior code
changed, or the MERGE verdict does not cover the current behavior diff. Resume
the saved `thread_id`. Send the ledger (`fixed:` / `disagree:` / `declined:` +
evidence), the same base diff command, and the change since last round. Tell
Sol: open ids and changed code only. Mark each old id `resolved` or
`still open: <reason>`, then answer again: would you merge this code now?

## 5. End of a loop

Agreed: MERGE on the current behavior diff, no blocker or should open,
no concern of your own. Go to step 6. Stuck: an item stays disputed after
two replies, or budget ends. Go to step 7 with no fresh review. Do not ask
the user mid-loop; put both sides in the report, 2-3 lines each, and the
user decides. Budget end is not approval.

## 6. Fresh review

A resumed Sol checks its own findings; it does not re-read the whole change.
Before shipping, a new Sol reads all of it.

Skip this step if the loop agreed in its round 1 and behavior code has not
changed since: that round was already a fresh full review.

Otherwise start a new `codex exec` (not `resume`) with the round 1 brief:
same base and diff command, current checks, no ledger. Verify it as any
round (session log, `git status`).

- MERGE, or nits only: ship (step 7).
- A blocker or should: this review is round 1 of the next loop. Save its
  `thread_id` and continue at step 3. When a finding repeats one you
  declined, dispute it with the earlier reason; the round 2 brief carries the
  ledger.
- Stop and report instead of starting the loop if it would be loop 4. Say
  whether the cause looks like diff size or missing test coverage.

## 7. Ship and report

Do not push during the loop. Push after agreement only if the user asked
to push, ship, or update the PR. If you push to a PR, add above the model
blurb:

`Reviewed with sol-loop: <L> loops, <N> rounds with <model> on high. Fresh review: would merge`.

Write `on high` only if every round's session log showed it. Under it, list
each declined or disputed finding with its one-line reason, so a later reviewer
sees what was weighed.

Report: loops and rounds, each fresh review's verdict, model and effort, what
Sol changed, diff size before/after, fixed and declined findings with reasons,
disputes with both sides, usage per round, pushed or not.

---

Adapted from `skills/sol-loop` in [t3dotgg/tstack](https://github.com/t3dotgg/tstack),
MIT License, Copyright (c) 2026 Theo Browne.
