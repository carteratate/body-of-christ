# CI/CD Plan for TheoCorpus

> **Author:** Muse — Meta's AI assistant. Drafted 2026-09-09 at Carter Tate's
> request as a starting proposal for review. This is a draft plan, not a
> decision: nothing here has been implemented yet, and every section marked
> "Open question" needs Carter's call before it becomes work.

## 0. Why this exists

TheoCorpus is a live product with real users, four deploy targets, 35 database
migrations, and 533 commits — all shipping with zero automated checks and fully
manual deploys. The goal of this plan is to make `main` always deployable,
make deploys boring, and catch the expensive mistakes (broken migrations,
failed Docker builds, lint regressions) before they reach production.

Design principles:

- **One workflow file to start** (`.github/workflows/ci.yml`), split into
  parallel jobs. Don't build a CI platform; build a checklist that runs itself.
- **Each deploy target keeps its natural CD path** (Vercel for web, Railway
  for API) — CI gates the merge, CD handles the ship.
- **Migrations are the scariest step**, so they get their own job in CI
  (validate) and their own job in CD (apply), in that order of caution.
- **Phase it.** Phase 1 is a day of work and pays off immediately. Phases 2–3
  can wait until Phase 1 is green and trusted.

## 1. Current state (as of 2026-09-09)

| Target | What it is | How it ships today |
|---|---|---|
| `apps/web` | Next.js 16, TypeScript | Vercel (auto-deploy; preview per PR) |
| `services/api` | FastAPI, Docker | Railway (manual/unknown trigger — see open questions) |
| `supabase/migrations` | 35 SQL migrations | Applied manually |
| `datapipeline/` | Local ingestion scripts | Run by hand, not deployed |

Test inventory that CI should run: 51 API pytest files, 31 web vitest files,
per-collection datapipeline tests. ESLint baseline is zero errors; `tsc` is
available. No `.github/workflows` exists at all.

## 2. CI — `.github/workflows/ci.yml`

Trigger: `pull_request` and `push` to `main`. All jobs run in parallel;
the workflow fails fast per job but lets the others finish so one PR shows
every problem at once.

### Job 1: `web`

```yaml
- setup-node (pin the Node major you deploy on Vercel)
- npm ci
- npm run lint          # ESLint — the repo baseline is ZERO errors
- npx tsc --noEmit
- npm test              # vitest run
- npm run build         # catches the errors tests miss
```

### Job 2: `api`

```yaml
- setup-python (3.11+, match the Dockerfile)
- pip install -e ".[dev]"   # or uv sync, if you adopt uv
- ruff check .              # add ruff config if you don't have one yet
- python -m pytest tests/   # asyncio_mode=auto is already configured
- docker build -t theocorpus-api:ci services/api   # build only, no push
```

### Job 3: `datapipeline`

```yaml
- setup-python
- pip install -r requirements (whatever the pipeline uses)
- python -m pytest datapipeline/tests/
```

### Job 4: `migrations`

This is the highest-value new check — it catches broken SQL before it ever
touches Supabase:

```yaml
services:
  postgres:
    image: postgres:16
    env: { POSTGRES_PASSWORD: postgres }
steps:
  - for f in supabase/migrations/*.sql (sorted); do
      psql -h postgres -U postgres -d postgres -f "$f";
    done
  - # optional: assert RLS is enabled on every user-owned table
```

If a migration can't apply cleanly to a fresh Postgres 16, the PR fails.

### Job 5: `security`

```yaml
- gitleaks detect --no-git   # secret scanning
- npm audit --audit-level=high        # apps/web
- pip-audit                           # services/api
```

### Branch protection (repo settings)

On `main`: require the `ci.yml` workflow to pass, require PR review
(even self-review forces a pause), require branches to be up to date.
This is the actual enforcement — without it, CI is advisory.

## 3. CD — per target

### 3a. Web (Vercel) — mostly done already

Vercel gives you preview deployments per PR and production deploys on merge
to `main` for free. Changes needed:

1. Add the CI status checks as required in branch protection so a red PR
   can't merge (and therefore can't auto-deploy a preview of broken code).
2. Confirm the production deploy trigger is "merge to main" and not
   "every push to any branch."

No new workflow needed here.

### 3b. API (Railway) — two options, pick one

**Option A (simplest): Railway's native GitHub integration.** Connect the
Railway service to the repo; it auto-deploys on merge to `main` after CI
passes. Downside: the image is built by Railway, not versioned anywhere
you control.

**Option B (recommended): build in Actions, ship the artifact.**

```yaml
# .github/workflows/deploy-api.yml — on push to main, after ci.yml passes
jobs:
  build-and-push:
    - docker build -t ghcr.io/carteratate/theocorpus-api:${{ github.sha }} services/api
    - docker push ghcr.io/carteratate/theocorpus-api:${{ github.sha }}
  deploy:
    needs: [build-and-push, migrate]   # migrations first — see 3c
    - trigger Railway redeploy of the API service pointed at the new image
      (Railway GraphQL API or deploy webhook; service token in Actions secrets)
```

Option B gives you reproducible, scannable images and one place (GHCR) that
records exactly what shipped for every deploy. It also makes rollback
"redeploy the previous image tag" instead of "rebuild from an old commit."

### 3c. Migrations — the careful one

Migrations ship in their own job, **before** the API redeploy, on every
merge to `main`:

```yaml
# part of deploy-api.yml, job `migrate`
- supabase db push --project-ref $SUPABASE_PROJECT_REF
  # with SUPABASE_ACCESS_TOKEN in Actions secrets
```

Rules that make this safe:

- **Expand before contract.** Additive changes (new tables, new nullable
  columns) ship in one release; destructive changes (drop column, rename)
  ship in a *later* release, after the old API version is gone. This keeps
  the old and new API both working during the deploy window.
- **Forward-fix preferred.** Roll a migration forward rather than rolling
  back, unless the migration itself is the breakage.
- **Staging first (Phase 3).** Once a staging project exists, migrations
  apply to staging on PR merge-queue, then prod after smoke tests pass.

### 3d. Datapipeline — CI only

It's not deployed and shouldn't be. CI runs its tests; optionally add a
scheduled workflow (`cron: weekly`) that runs a single-collection ingest
with `--target search --dry-run` (if such a mode exists — if not, that's a
small feature worth adding) to catch bit-rot in ingestion code.

## 4. Environments

| | Staging (Phase 3) | Production |
|---|---|---|
| Web | Vercel preview deployments (already free per PR) | Vercel production |
| API | Second Railway service | Railway production service |
| DB | Second Supabase project | Supabase production project |
| Vector store | Qdrant Cloud free tier / second collection prefix | Qdrant production |

Staging doesn't need production data — a small seeded corpus is enough to
prove the pipeline works end to end. The deploy workflow targets staging on
PRs labeled `deploy-staging` (or every merge to a `staging` branch) and
production on merge to `main`.

## 5. Secrets inventory

GitHub Actions secrets needed:

- `SUPABASE_ACCESS_TOKEN` + `SUPABASE_PROJECT_REF` (migration job)
- `RAILWAY_TOKEN` (deploy trigger, Option B)
- `GITHUB_TOKEN` (built in — for GHCR push)
- `GITLEAKS_LICENSE` only if you outgrow the free tier (you won't)

Nothing that currently lives in `services/api/.env` or Vercel env vars moves;
the migration job is the only new consumer of production credentials, and it
only runs on `main`.

## 6. Post-deploy smoke tests

After every production deploy, run:

1. `GET /health` and `GET /health/db` on the API through the Vercel proxy —
   proves proxy → API → DB connectivity (both endpoints are required by the
   project's AGENTS.md).
2. One canned search (`top_k` small, single collection) through the full
   `/v1/...` path — proves the retrieval pipeline is alive.
3. Check the Railway deploy logs for migration errors.

If smoke fails: Vercel → instant rollback to the previous deployment;
Railway → redeploy the previous image tag / previous deployment. Both are
one click; document the exact clicks in `docs/runbooks/` when you set this
up (that's a Phase 2 task).

## 7. Rollout order

- **Phase 1 (this week, ~1 day):** `ci.yml` with the five jobs + branch
  protection on `main`. Immediate payoff, zero deploy risk.
- **Phase 2 (next):** migration-apply job on merge to `main`, API deploy
  workflow (Option A or B), post-deploy smoke tests, rollback runbook.
- **Phase 3 (when it hurts):** staging environment, staging-first
  migrations, scheduled datapipeline dry-run.

## 8. Open questions for Carter

1. How are Railway deploys triggered today — native GitHub integration,
   manual redeploy, or CLI? (Determines whether Option A is already on.)
2. Does a staging Supabase project exist, or should Phase 3 create one?
3. Is `uv` acceptable for the API CI install, or stay with pip?
4. Any objection to GHCR for image storage, or prefer Docker Hub?
5. Deploy cadence goal: continuous on every merge, or batched releases?

## 9. What "done" looks like

- A PR that breaks a test, a migration, or the Docker build cannot merge.
- Merging to `main` ships web (Vercel), API (Railway), and migrations
  (Supabase) with no manual steps and a smoke test at the end.
- Any deploy can be rolled back in under five minutes with a documented
  procedure.
- This document gets updated when reality diverges from it — a stale
  CI/CD plan is worse than none.
