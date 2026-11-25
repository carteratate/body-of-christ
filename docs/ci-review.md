# CI review (23 Nov 2026)

What our CI does today, what it costs in time, what it misses, and what to change.
Research only: nothing here is adopted yet. Every number comes from GitHub's run
history for 9–23 Nov 2026 (308 runs; per-step timings sampled from 91 successful
runs), or from local runs on the Lenovo that reproduce CI's test counts exactly.

The September proposal `docs/ci-cd-plan.md` covers the same ground. Only its Phase 1
shipped (4 Oct). This review measures what shipped and re-ranks what that plan left
open.

---

## 1. CI in plain language

**What CI is.** When you push commits, GitHub rents a fresh, empty Linux machine (a
*runner*), copies the repository onto it, installs the dependencies, and runs a list of
commands. If every command succeeds, the commit gets a green tick; if one fails, a red
cross. The list lives in `.github/workflows/`. Each file there is a *workflow*. A
workflow has *jobs*, which run on separate machines at the same time. Each job has
*steps*, which run one after another.

A runner starts with nothing on it. It has no `.env` files, no `datapipeline/sources/`,
no database and no secrets (our workflow is given none). So CI can only run the checks
that work with nothing but the repository. The rest only run when somebody runs them
by hand.

**Because this repository is public**, GitHub's standard runners cost nothing. Minutes
are a question of waiting, not money.

### The one workflow: `ci.yml`

There is one workflow file, `.github/workflows/ci.yml`.

**When it runs:**
- on every pull request: opened, every new push to it, reopened;
- on every push to `master`, which includes every merged PR.

**Concurrency.** A new push to a PR cancels that PR's run still in progress (12 PR
runs were cancelled this way in the fortnight). Pushes to `master` never cancel each
other, so every merge keeps its own result.

**Timeouts.** Each job has one (15 or 20 minutes) so a hung test cannot run forever.

It has three jobs, which run side by side:

| Job | Steps | Median | p90 |
|---|---|---|---|
| `web` | checkout + Node 24 (8 s) · `npm ci` **55 s** · `npm run lint` 10 s · `tsc --noEmit` 6 s · `vitest run` **46 s** | 130 s | 159 s |
| `api` | checkout + Python 3.11 (6 s) · `pip install -e services/api[dev]` 18 s · `pytest` 11 s | 40 s | 46 s |
| `datapipeline` | checkout + Python 3.11 (6 s) · tokenizer cache 1 s · `pip install -r requirements.txt` 16 s · `pytest -m "not smoke"` **35 s** | 62 s | 68 s |

**Wall clock** (from start to green, i.e. how long a PR waits):

| | Runs | Median | p90 | Max |
|---|---|---|---|---|
| Pull requests (successful) | 168 | 132 s | 169 s | 186 s |
| Pushes to `master` (successful) | 105 | 138 s | 194 s | 310 s |

A job waits about 2 seconds for a machine, so queueing doesn't matter. **The `web` job
sets the pace:** it takes twice as long as the others, and more than half of it is
`npm ci` unpacking 751 MB of `node_modules`. Inside the 46 s vitest step, vitest
reports 27 s of its own time, most of it building jsdom for each test file.

**Outcomes over the fortnight:**

| | Success | Failure | Cancelled | Still running at capture |
|---|---|---|---|---|
| Pull requests | 168 | 11 | 12 | — |
| `master` pushes | 105 | 3 | 7 | 2 |

### What CI runs, and what it skips

CI runs **all web checks** (lint, types and every vitest test: 792 on the last measured run). The **API** and
**datapipeline** suites also run in CI, but large parts of each skip themselves:

| Suite | In CI | Skipped in CI | Why skipped |
|---|---|---|---|
| API (`services/api/tests`) | 1,205 pass | **279** | 273 need local PostgreSQL tools (`initdb`, `pg_ctl`); 6 need a live Qdrant (`QDRANT_TEST_URL`) |
| datapipeline (`datapipeline/tests`) | 1,890 pass | **566**, plus 1 deselected | 155 need local PostgreSQL; 411 need the gitignored `datapipeline/sources/` (241 of them are `tests/source_checks/`); 1 is a `smoke` test |

Both rows match CI exactly when run on the Lenovo with the Postgres tools taken off
`PATH`, and, for the datapipeline, without the sources link. So the skip reasons above
are measured, not inferred.

**The skipped tests are the risky ones:**
- **The 428 local-Postgres tests** run real SQL. They cover our migrations (0037 outline,
  0042/0043 corpus schema and staging, 0044 form, 0045 search vector), the staging
  schema, the republish checks, keyword search SQL (`min_match`), corpus lifecycle
  (tombstones and redirects), held texts, collection keys and roles. A migration or SQL
  change can be green in CI and still broken.
- **The 411 source tests** check the corpus itself: text hygiene, coverage, sequence,
  structure, and the adapters against the real source files.

**What threads must run locally**, because CI can't:

| Check | Needs | Time on the Lenovo |
|---|---|---|
| Full API suite (`python3 -m pytest tests/` with `initdb` on `PATH`) | PostgreSQL tools | 2 min 36 s (1,478 pass, 6 skip). The 567 tests in the Postgres files alone take 2 min 42 s, about 1.1 s of setup each for a fresh database and migrations |
| datapipeline with Postgres, no sources | PostgreSQL tools | 1 min 56 s (2,045 pass) |
| Full datapipeline suite with sources (`pytest tests -n auto --dist loadscope`) | `datapipeline/sources/` (886 MB) | about 6 min in parallel, 22 min serially (CLAUDE.md figures; not re-measured today, because only about 5 GB of memory was free, so `-n auto` would have picked one worker) |
| `scripts/source_lock.py --verify`, `checks.report`, `checks.health`, the release report | sources, sometimes the live database (read only) | per PR template |
| Qdrant alias tests | `QDRANT_TEST_URL` | — |

**What CI catches:**
- TypeScript type errors and ESLint errors in the web app;
- broken unit and component tests in all three areas;
- registry and contract tests that need no data, e.g. a removal ID used twice, or web
  collection keys drifting from `constants.py`.

**What CI does not catch:**
- **SQL and migration bugs** (Postgres tests skipped, see above).
- **Corpus regressions** (source tests and checks skipped).
- **Two PRs that are each green but break when combined.** All three red `master` runs
  were this:

  | Broken by | Failure | Fixed by | Master red for |
  |---|---|---|---|
  | #342 | removal ID clash | #345 | 21 min |
  | #358 | removal ID clash | #359 | 71 min |
  | #379 | missing document facts | #383 | 4 h 41 min |

  PRs that branched from `master` in that window failed too (#253's and #254's runs on
  14 Nov).
- **Python mistakes a linter or type checker would find.** There is no Python linter or
  type checker.
- **Vulnerable dependencies and leaked secrets.** Nothing scans for either.
- **The production builds.** `next build` runs only in Vercel's preview deployment
  (its check appears on each PR, but nothing requires it). The API's Docker/Railway
  build is not tried at all before merge.
- **End-to-end browser flows.** There are no Playwright tests in the repo.

### What enforces CI: nothing, today

- **`master` has no branch protection and no rulesets**, so a red or unfinished CI
  doesn't block a merge. Discipline has held up: of 118 PRs merged in the fortnight,
  117 had green CI, 1 merged before CI finished (#347), and 1 merged with no CI run
  (#358, one of the three that broke `master`).
- **Deploys do not wait for CI.**
  - Railway's API service has `checkSuites: false`, so it builds and deploys every
    `master` push the moment it lands, in parallel with CI.
  - Vercel's production deploy likewise starts at once (on #467 both deploys went
    pending at 17:30:12, the same second CI started).
  - So a commit that turns `master` red is already in production by the time CI says
    so.
- **The API redeploys on every merge, whatever it touched.** Only 28 of the 118
  merged PRs changed `services/api/`, yet Railway rebuilt and restarted the API for
  all of them. That matters more than it sounds, for two reasons:
  - The API's Python dependencies are lower bounds only (`fastapi>=0.111.0`, etc.;
    only `anthropic` is pinned) with no lock file. **Each rebuild can install newer
    library versions that no test has seen**, even from a docs-only merge.
  - A restart can cut off a search mid-stream.

---

## 2. Making it faster where the time buys no safety

PRs wait about 2¼ minutes, most of it in `npm ci`. Ranked by minutes saved per PR:

| # | Change | Saves | Safety cost |
|---|---|---|---|
| F1 | **Cache `node_modules`** in the web job, keyed on `package-lock.json` + Node version + OS; skip `npm ci` on a hit | about 40 s off the slowest job; web 130 s → about 90 s, so every PR finishes about 40 s sooner | None. A changed lock file misses the cache and runs `npm ci` |
| F2 | **Run the web job only when its inputs change**: `apps/web/**`, `datapipeline/registry/works.json`, `services/api/app/rag/constants.py` and `.github/**` (the only outside files the web tests read). Run everything on every `master` push regardless | 47% of merged PRs (55 of 118) touched only `datapipeline/` and docs; they would finish in about 62 s instead of about 130 s | Small: a cross-area dependency added later and missed by the filter is still caught on `master`. The filter list needs keeping up |
| F3 | **Docs-only PRs skip the test jobs** (`docs/**`, `*.md`, `docs/screenshots/**`) | 16% of merged PRs (19 of 118) go from about 2¼ min to about 10 s | None. Docs aren't executed. The API and datapipeline tests read code and data files, not Markdown |
| F4 | **Install Python dependencies with `uv`** instead of pip, in both Python jobs | about 12–15 s per Python job (pip takes 16–18 s with a warm cache) | None. Becomes worth doing after F1/F2, once the datapipeline job is the slowest |
| F5 | **Cancel superseded runs**: already done for PRs | — | Keep `master` as it is: each merge's own result is what tells you which merge broke it |

**Not worth doing:**
- Sharding vitest: 27 s of real test time doesn't repay the cost of a second runner,
  which repeats the install.
- Splitting lint and `tsc` into their own jobs: each new job pays checkout plus
  install again, so it gets slower, not faster.
- Making the API job faster: at 40 s, it is never the slowest job.

**Implementation note for F2/F3.** One small first job works out which areas changed
(`dorny/paths-filter` or a `git diff --name-only` against the base, about 5–10 s). The
other jobs read its answer in their `if:`. A job skipped this way counts as passing if
we later make the checks required (section 3, S0c).

**Outside CI, but the same idea: Railway watch paths.** Restricting the API service's
redeploys to `services/api/**` would stop 76% of API restarts (90 of 118 merges this
fortnight changed nothing the API image contains; the image is built from
`services/api` alone). It would also cut the rebuilds that pull untested dependency
versions.

---

## 3. Additions that keep bad code from shipping

Ranked by value against the minutes they add to a PR's wait.

**Value** asks how likely the problem is to reach production and how much it would
hurt. **Minutes** are added wall-clock time. A check that runs in parallel with the
web job and finishes before it adds nothing.

| Rank | Addition | Value | Adds | Notes |
|---|---|---|---|---|
| **S0a** | **Turn on GitHub secret scanning and push protection** (currently disabled) | High | 0 | Free for public repos. Push protection refuses a push that contains a recognised key. Enabling it scans the whole history once. Our `.env` files hold live provider keys, and many threads commit on this machine |
| **S0b** | **Make deploys wait for CI**: set "Wait for CI" (`checkSuites`) on the Railway service | High | 0 to PRs; API deploys go out about 2 min later | A red `master` would stop reaching production. Vercel's production deploy would still go ahead. Vercel's project settings may offer an equivalent; I did not verify |
| **S0c** | **A ruleset on `master`** requiring `web`, `api` and `datapipeline` to pass | Medium–high | 0 | Makes today's good habits a rule, and would have blocked #358. Without S0b, a green PR merge still deploys before the `master` run finishes |
| **S1** | **Lock Python dependencies**: commit a lock file (e.g. `uv lock` or `pip-compile`) for `services/api` (which the production image installs) and `datapipeline`, and install from it in CI and in the Dockerfile | High | 0 (faster with F4) | Today production installs whatever is newest at build time, and builds happen on every merge. A lock file means production runs the versions CI tested, a rollback reproduces exactly, and S5's audit means something. Dependabot (S5) then proposes updates as reviewable PRs |
| **S2** | **Run the local-Postgres tests in CI**: give the API and datapipeline jobs `initdb`/`pg_ctl`/`psql` (from apt, or the runner's own PostgreSQL if its image ships one; add its `bin` directory to `PATH`) | Highest of the test additions | About 1–3 min on the API job, under or near the web job's 2 min if the API suite runs in parallel (`pytest-xdist`, already a datapipeline dependency) | Brings the 428 real-SQL tests into CI: migrations, staging, republish checks, keyword-search SQL. Measured serial cost on the Lenovo: API Postgres tests 2 min 42 s, datapipeline Postgres tests about 75 s extra. Each test builds its own database in a temporary directory, so they parallelise; a cluster per worker with template databases would cut setup further. Install cost on the runner is an estimate (about 20–40 s); the runner image is Ubuntu 26.04 and I have not checked whether it ships PostgreSQL |
| **S3** | **A migration check** (a short script, about 1 s) | High for the cost | About 0 | See the details below this table |
| **S4** | **Python lint and types**: `ruff check --select F` on `services/api` and `datapipeline`; pyright on `services/api/app` against a committed baseline | Medium | About 0 (ruff 0.04 s, pyright about 6 s, run beside the web job) | Today ruff's F rules find 30 trivial issues (19 unused imports, 8 f-strings without placeholders, 3 unused variables) and no undefined names. Fix those once and keep it at zero. Pyright in its default mode finds 146 errors in `app/` (mostly `Optional` access and argument types), so it needs a baseline file that fails only new errors |
| **S5** | **Dependency scanning**: turn on Dependabot alerts (currently disabled; free, 0 min). In CI, `npm audit --omit=dev --audit-level=critical` (blocking) and `pip-audit` on the locked files | Medium | About 10–15 s, beside the web job | Today, production npm dependencies have 0 critical and 2 high (`ws`, `source-map-js`); counting dev dependencies, 2 critical (`vitest`, `tinypool`) and 6 high. **Threshold:** block on *critical in production dependencies*, which passes today. Report high, and anything in dev dependencies, without blocking: a blocking `high` would fail every PR today over issues in transitive packages. `pip-audit` finds nothing today in either Python environment (13 s and 9 s), and only means something once S1 pins what ships |
| **S6** | **Corpus checks on a self-hosted runner on the Lenovo**: the full datapipeline suite with sources, `source_lock.py --verify`, `checks.report` and `checks.health`, run nightly, on every `master` push, and on demand (`workflow_dispatch`) for a PR branch | High for corpus correctness, after the fact | 0 to PRs (it doesn't block them) | See the details below this table |
| **S7** | **Catch PRs that clash when combined.** Options, cheapest first: | Medium | Varies | See the details below this table |
| **S8** | **Build the API image in CI** (`docker build services/api`, no push) | Low–medium | About 1–2 min, beside the web job | Catches a broken Dockerfile or dependency install before Railway does. Note: the Railway service reports builder RAILPACK, while the root `railway.toml` asks for the Dockerfile and the service's root directory is `services/api`. Worth confirming which builder production actually uses before relying on either |

**S3, the migration check, in detail:**
- **Non-additive statements.** Fail a new or changed `supabase/migrations/*.sql` that
  contains `DROP TABLE`, `DROP COLUMN`, `RENAME`, `ALTER COLUMN … TYPE`,
  `SET NOT NULL` or `DROP POLICY` outside the `staging` schema. A marker line such as
  `-- non-additive: <reason>, approved by Carter <date>` lets one through.
- **Edits to applied migrations.** Fail any change to a migration that is already on
  `master`.
- **Number collisions.** Fail a migration number that collides with an existing one
  (we have two collisions already).
- **Expected hit rate:** in the 45 migrations so far, 5 would have needed the marker
  (0022, 0030, 0034, 0045, and 0042's staging drop if the `staging` exemption is
  removed). That is rare enough that the marker means something.
- **What it adds.** The repo rule is "schema changes must be additive", and today only
  review enforces it. S2 runs some migrations against a reduced schema, not the whole
  chain in order, so S3 is not redundant.

**S6, the corpus checks on the Lenovo, in detail:**
- **Why not GitHub's runners.** The sources hold in-copyright text and can't go to
  GitHub-hosted runners for a public repository. Artifacts can be downloaded by anyone,
  and Actions caches can be read by workflows from fork PRs. The Lenovo already has the
  sources.
- **Time:** about 6 min when memory allows.
- **Security:** a self-hosted runner on a public repo must never run code from fork
  PRs, so trigger it only on `master`, on a schedule and by manual dispatch, and set
  "require approval for outside collaborators".
- **A cheaper first step:** a seconds-long CI check that the PR description contains
  the source-check blocks the template asks for whenever `datapipeline/` changes. That
  enforces today's manual process instead of replacing it.

**S7, PRs that clash when combined, in detail:**
1. **Change how the registry allocates IDs** so two PRs can't pick the same one. That
   removes the cause of two of the three breaks.
2. **"Require branches to be up to date before merging"** in the S0c ruleset. Each PR
   must re-run CI on top of the latest `master` before merging: about 2¼ min more
   whenever `master` has moved, which with about 8 merges a day and many parallel
   threads is often.
3. **GitHub's merge queue.** It does this automatically, but as far as I know it is
   offered only for organisation-owned repositories; I have not verified that.

Until then, a red `master` run emails only the person who pushed.

### Recommended order

1. **Do now. Free settings, no code:** S0a (secret scanning and push protection),
   Dependabot alerts (S5), S0b (Railway waits for CI), S0c (ruleset), Railway watch
   paths.
2. **Small PRs that cut waiting:** F1 (`node_modules` cache), then F2/F3 (path filters).
   PRs would go from about 2¼ min to about 1½ min, about 1 min for datapipeline-only
   changes, and seconds for docs.
3. **Small PRs that add safety, using the time freed:** S1 (lock files), S3 (migration
   check), S4 (ruff, then pyright with a baseline), S5's audit steps.
4. **The big safety win:** S2 (Postgres tests in CI), parallelised so it stays under
   the web job.
5. **Then:** S6 (corpus checks on the Lenovo), S7 (ID allocation first), S8.

After steps 1–4, a typical PR would still finish in about 2 minutes. CI would then
also prove that migrations apply and that SQL behaves, and production would run only
code and dependency versions that CI has passed.

---

## How the numbers were taken

- **Run history:** `gh run list --workflow ci.yml --created ">=2026-11-09"` (308 runs).
  Per-step timings come from the jobs API for every third successful run (91 runs).
  Failure causes come from `gh run view --log-failed`.
- **Skip counts:** reproduced on the Lenovo with the API's `.venv` and
  `datapipeline/.venv`, once with `~/.local/bin` (`initdb`, `pg_ctl`) removed from
  `PATH` and `datapipeline/sources` moved aside (exactly CI's 1,205/279 and 1,890/566),
  and once with the Postgres tools present.
- **Merged-PR history:** `gh pr list --state merged --search "merged:>=2026-11-09"` with
  each PR's check rollup and changed files.
- **Railway:** the service config and recent deployments, read through the Railway
  connector.
- **Audits:** `npm audit` in `apps/web`, and `pip-audit` on `pip freeze` of both Python
  environments.
- **Lint and types:** ruff and pyright from a scratch virtualenv. Nothing was installed
  into the repo.
