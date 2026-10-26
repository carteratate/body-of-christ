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

Make the most minimal possible changes to appease Sol. Be careful of scope
creep and don't be scared to push back.

## Budget

- Default: 3 rounds total. Round 1 is full. Later rounds check only
  changed code and open findings.
- Extend to 5 only for security, permissions, auth, data loss, or
  state/concurrency, while a blocker or should stays open with evidence. Or when
  the user asks.
- Stop early if a round returns only nits. Declined nits and comment,
  doc, or format-only fixes need no new round.
- One reviewer only. Sol must not start subagents or reviewers.
- Keep a ledger: id, severity, outcome, usage per round from Codex's output.
  Never guess it.

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
`model`, `reasoning_effort` and `sandbox_policy`. Read-only and high are what
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
perf, extra compat: nits.
blocker = intended case wrong. should = real bug callers will hit, in intent. nit = rest.
Would you merge this code as it stands? Answer that first.
Reply:
VERDICT: MERGE or CHANGES
S1 [blocker|should|nit] <file>:<line> <claim>. Fix: <suggestion> (stable ids)
```

## 3. Answer findings

You fix; Sol never does. Check each finding and severity yourself. Another
path, rare case, or small cost is a nit, whatever label it came with.

- Agree: smallest fix. Prefer delete or narrow over new lock, cache,
  helper, or option. Fix the case that happened. Add one focused test
  that fails without the fix, if intent needs it.
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

## 5. Stop and ship

Agreed: MERGE on the current behavior diff, no blocker or should open,
no concern of your own. Stuck: an item stays disputed after two replies,
or budget ends. Do not ask the user mid-loop; put both sides in the report,
2-3 lines each, and the user decides. Budget end is not approval.

Do not push during the loop. Push after agreement only if the user asked
to push, ship, or update the PR. If you push to a PR, add above the model
blurb:

`Reviewed with sol-loop: <N> rounds with <model> on high. Sol verdict: would merge`.

Write `on high` only if every round's session log showed it.

Report: rounds, model and effort, what Sol changed, diff size before/after,
fixed and declined findings with reasons, disputes with both sides, usage per
round, pushed or not.

---

Adapted from `skills/sol-loop` in [t3dotgg/tstack](https://github.com/t3dotgg/tstack),
MIT License, Copyright (c) 2026 Theo Browne.
