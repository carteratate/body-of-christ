# Production logs and settings review (19 to 26 Nov 2026)

Read-only review of the API on Railway, the web on Vercel, Supabase and PostHog over the
seven days that include the 20 Nov republish and the 23 to 26 Nov publishes. Nothing was
changed in any service. Written 26 Nov 2026.

## What was read, and what could not be

| Source | Read | Gaps |
|---|---|---|
| Railway, `gentle-achievement` / production / `body-of-christ` | Runtime logs, the HTTP log, the 5xx/4xx rate, 50 deployments, the live service config, the variable names (no values), and the build log of the live deploy | Runtime logs reach back only to 20 Nov 20:12 UTC. The republish apply ran inside that window |
| Supabase `body-of-christ-dev` (production) | Postgres, Auth, PostgREST and Supavisor logs per day, the security and performance advisors, and read-only size queries | There are no `edge_logs` (API gateway) in the stream. The API talks to Postgres directly, so those logs would show only browser Auth traffic |
| PostHog | Project settings and the all-time event count | — |
| Vercel | The live site's response headers and JavaScript, GitHub's deployment records, and a local `npm run build` of the same commit | **The Vercel connector refuses the `carter-tates-projects` team scope** (403). Runtime errors, runtime logs and the Vercel build log were not read. See "Still to read" at the end |

Traffic for scale: 226 requests reached the API in seven days, with 7 signed-in searches and
2 guest trials. **The API returned no 5xx.** It returned twelve 4xx, all accounted for below.

## Recommendations, ranked by impact against effort

**Setting** means only Carter can make the change, in a dashboard. **Code** means a thread
can make it in a PR. Effort runs from XS (one line) to M (a small feature with tests).

| # | Recommendation | Impact | Effort | Who |
|---|---|---|---|---|
| 1 | Turn analytics on: set `NEXT_PUBLIC_POSTHOG_KEY` and `NEXT_PUBLIC_POSTHOG_HOST` for Vercel Production, and add PostHog's US hosts to the CSP **before** that build goes live (item 1) | High: there has never been any analytics | S | Setting + Code |
| 2 | Let the API shut down gracefully: `exec` in the Dockerfile's `CMD`, and give Railway a draining time (finding A) | Medium: every deploy kills in-flight searches outright | XS + XS | Code + Setting |
| 3 | Deploy the API only when `services/api/` changes, using watch paths (finding B) | Medium: 50 API restarts in four days, 37 of them for merges that did not touch the API | XS | Setting |
| 4 | **Before 1 Dec 2026**, set the builder to Dockerfile and add a `/health` healthcheck in the Railway dashboard: `railway.toml` stops being read that day (finding C, corrected) | High on 1 Dec: a Railpack build would ignore the Dockerfile | XS | Setting |
| 5 | Keep `qdrant-client` within one minor version of the server (`>=1.18,<1.20`, which resolves to 1.19.1) in both dependency inputs, and re-lock (item 2) | Low today, but avoids a surprise | XS | Code |
| 6 | Turn on leaked-password protection in Supabase Auth (security advisor) | Low to medium: blocks passwords known from breaches | XS | Setting |
| 7 | Change the stored translation label from `CPDV` to `WEB-C`, accepting `CPDV` as an old alias (item 4) | Low: the label is wrong but steers nothing | M, plus a data backfill that needs Carter's OK | Code |
| 8 | Stop logging the last four characters of the Anthropic keys at startup (finding D) | Low: a tidy-up of key material in logs | XS | Code |
| 9 | Log the plan error code when a search is refused with 400 or 422 (finding E) | Low: the two guest 422s cannot be explained today | XS | Code |
| 10 | Rename `middleware.ts` to `proxy.ts` (Next 16's codemod) to clear the deprecation warning (item 3) | Low: a warning today, a break in a later Next major | S, touches auth routing, needs a careful test | Code |
| 11 | Pin `engines.node` to `"24.x"`, and use `npm ci` in `vercel.json` (item 3) | Low: clears the version-override warning and makes Vercel install the lockfile exactly | XS | Code |
| 12 | Remove the six Railway variables nothing reads (finding F) | Low: one of them, `RATE_LIMIT_PER_MINUTE`, suggests a setting that does nothing | XS | Setting |
| 13 | Index the foreign keys that `purge-retired` deletes against (performance advisor) | Low at today's table sizes | S, a migration that needs Carter's OK to apply | Code |

Nothing needs doing about the 20 Nov disk-full outage beyond what the runbook already does
(finding G).

---

## The four known items

### 1. PostHog: analytics are not working, and never have

**Plainly: no analytics event has ever reached PostHog.** The project reports
`ingested_event: false`, and a count over all events returns 0. The project holds no other
project that events could be going to.

Two separate faults explain this. The first one stops everything on its own, so the CSP
question never comes up today.

1. **The production build has no PostHog key.** Next.js inlines a `NEXT_PUBLIC_` variable
   into the browser bundle only when it is set at build time. In the live bundle,
   `NEXT_PUBLIC_SUPABASE_URL` is inlined but `NEXT_PUBLIC_POSTHOG_KEY` and
   `NEXT_PUBLIC_POSTHOG_HOST` are still unresolved `process.env` references. They are
   therefore undefined in the browser, so `PostHogProvider` never calls `posthog.init` and
   every `posthog.capture` is a no-op. Neither variable is in `.env.production.example`
   either, which suggests they were never added to Vercel. Their values could not be read
   because the Vercel connector is blocked.
2. **The CSP would block PostHog if it did start.** The live `connect-src` is `'self'
   https://app.posthog.com https://eu.posthog.com <supabase>`. `PostHogProvider` defaults
   the host to `https://us.i.posthog.com`, and the PostHog project's own `api_host` is
   `https://us.i.posthog.com`. **Setting the host to `app.posthog.com` would not help:** the
   bundled posthog-js rewrites `https://app.posthog.com` to `https://us.i.posthog.com`
   itself (`get apiHost()` in the live chunk). `script-src` is omitted, so script loads
   from `us-assets.i.posthog.com` are allowed, but every capture, flags and config call is a
   `fetch` or beacon to `us.i.posthog.com`, which `connect-src` blocks.

Fix, in this order:

- **Code:** in `apps/web/next.config.ts`, replace the two hosts with
  `https://us.i.posthog.com https://us-assets.i.posthog.com` (keep the EU hosts only if an
  EU project is planned), and update CLAUDE.md §16, which lists the old pair.
- **Setting (Carter):** in Vercel's Production environment, set `NEXT_PUBLIC_POSTHOG_KEY`
  to the project's public `phc_` key and `NEXT_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com`,
  then redeploy. A redeploy is needed because these values are inlined at build time.
  Adding them to `.env.production.example` would stop them going missing again.
- Check it worked: load theo-corpus.com and look for `$pageview` events in PostHog.

Related: the privacy page already says PostHog sets a cookie. That is untrue today, and
becomes true once this is fixed. The event code itself is careful: no query text is sent,
`$referrer` is stripped, and `$current_url` is reduced to the path.

### 2. Qdrant client 1.20.0 against server 1.18.2

The warning appears once at each API start: 69 times in the window, one per deploy. It is
logged at **warn** through the `py.warnings` logger (`logging.captureWarnings` in
`logging_setup.py`), so it reaches stdout as JSON and is not mislabelled as a Railway
error.

**Risk today: low.** Every Qdrant call in the window answered 200: query, alias reads,
collection info and point retrieval, with no exceptions logged. The API uses only APIs that
1.18 has (`query_points`, aliases, `retrieve`, collection info), and the publishes on 23 to
25 Nov ran the datapipeline on the same 1.20 client against the same server without
failures. Qdrant's stated policy, quoted in the warning, is that the client should be within
one minor version of the server. 1.20 is two minors ahead, so the combination is outside
what Qdrant tests. The risk is a future client release sending a field or default that a
1.18 server rejects. That would show up as a 4xx from Qdrant at API startup or during a
publish, not as silent bad results.

This did not start with the lock files: the same warning is in the logs from 20 Nov, before
#476. The lock files only fixed in place the version the open range had already drifted to.

**Recommendation: yes, pin, but to a range rather than one version.** Use
`qdrant-client>=1.18,<1.20` in both `services/api/pyproject.toml` and
`datapipeline/requirements.txt`, then run `scripts/lock_python_deps.sh`. That resolves to
1.19.1, which is within policy for a 1.18 server and silences the warning honestly. When
the cluster moves to 1.19 or later, raise the cap with it. Do not set
`check_compatibility=False`: it would hide exactly the signal that matters. The alternative
is for Carter to upgrade the Qdrant Cloud cluster to 1.20, if the Free tier allows it; then
the pin is unnecessary. Upgrading is the better long-term state, but it restarts the
cluster.

### 3. Vercel: "Node.js Version Override" and the build warnings

The Vercel build log could not be read (see Gaps), so this comes from the repository and a
local build of the same commit (`bab76f8`, Next 16.4.6, Node 24).

- **Node.js Version Override.** `apps/web/package.json` has `"engines": { "node": ">=20" }`.
  Vercel gives `engines` precedence over the project's Node setting and warns that an
  open-ended range will move to the next Node major automatically. **It matters a little:**
  a future Node major could arrive in a production build without anyone choosing it. Fix
  (code): `"node": "24.x"`, matching what the build uses today. Carter should check that the
  project setting says 24.x as well.
- **Build warnings found locally:**
  - `⚠ The "middleware" file convention is deprecated. Please use "proxy" instead.` (Next
    16). It works today, but a later major will drop it. The codemod is
    `npx @next/codemod@canary middleware-to-proxy .`. The middleware carries the session
    refresh and auth redirects, so the rename needs the auth flows tested afterwards.
  - Install: `npm warn install-scripts` for `core-js` and `unrs-resolver`, which have
    postinstall scripts not covered by `allowScripts`. This is noise: neither script is
    needed for the build.
- **The rest of the "7 warnings" could not be identified** without the Vercel log. The
  likely ones are Vercel's own notes on the `engines` range, the deprecated packages npm
  reports, and the items above. `vercel.json` uses `npm install` rather than `npm ci`, so
  Vercel can resolve differently from the lockfile CI tests. Switching to `npm ci` (code,
  XS) makes the two agree.

### 4. The translation label says CPDV, but the Bible is WEB-C

Every live Bible document is `translation = 'WEB-C'` (73 rows), yet:

- all 7 signed-in searches this week saved `filters.translation = "CPDV"`;
- all 9 `user_preferences` rows hold `preferred_translation = 'CPDV'`, the column default
  from migration 0006;
- the API's valid set is `{"CPDV", "douay-rheims"}`, falling back to `CPDV`
  (`routes/search.py:41,129`, `routes/guest_search.py:33,471`, `models/search.py:20`,
  `models/preferences.py:19`, `routes/preferences.py:23`);
- the web's draft does the same (`lib/search-draft.ts:43,47,172`), and
  `trackSearchPerformed` would send it to analytics.

The value is **only a label**. Nothing in retrieval reads it, which is why nothing is
broken. Neither translation it names exists in the corpus.

Recommended fix (code, M):

1. Make `WEB-C` the only valid value and the default in the API and in `search-draft.ts`.
   Keep `CPDV` and `douay-rheims` as accepted old values that both map to `WEB-C` on input,
   so old browsers, saved drafts and stored preferences keep working. Map them in one
   place on each side, rather than in each route.
2. Return `WEB-C` from `GET /preferences` whatever is stored, so the fix does not depend on
   a data change.
3. Optionally, with Carter's OK, because it writes to production: an additive migration
   setting the column default to `'WEB-C'`, and a one-line backfill of the 9 rows. Leave
   past searches' saved filters alone: they are history, and the restore path reads them as
   opaque.
4. Tests: an old value maps to `WEB-C`; a search saves `WEB-C`; restoring an old `CPDV`
   search still works.

---

## Other findings

### A. Every deploy kills the old container mid-request (code + setting)

`services/api/Dockerfile` ends with
`CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]`. With that,
`sh` is PID 1 and uvicorn is its child: the log says `Started server process [2]`. `sh`
does not pass SIGTERM on to its child, so when Railway stops the old deployment, uvicorn
never hears it. **None of the 69 shutdowns in the window logged uvicorn's
`Shutting down`**: each container just stops about 14 s after its successor starts.
Consequences:

- An in-flight search is cut off. A search takes 14 to 22 s to rank, and its explanations
  stream for up to 47 s more (`search delivery` lines). The user sees the stream die.
- The API's own shutdown code never runs: the lifespan teardown, and
  `drain_guest_search_tasks`, which exists to give guest searches 30 s to finish.
- `search_costs` relies on the generator's `finally`, which a SIGKILL skips. A search cut
  off this way leaves no cost row.

No search was actually cut off this week (9 of 9 `search_costs` rows are complete); traffic
is just low. The fix is small:

- **Code:** `CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]`.
  With `exec`, uvicorn becomes PID 1 and receives SIGTERM.
- **Setting or config:** give Railway a draining time longer than a search, for example
  120 s: `RAILWAY_DEPLOYMENT_DRAINING_SECONDS=120` on the service (#505 gives uvicorn 75 s,
  then the 30 s guest drain). Not in `railway.toml`: see finding C. Without it, Railway may
  follow SIGTERM with SIGKILL before the drain completes.

### B. 50 API deploys in four days, most of them unnecessary (setting or code)

Every merge to master redeploys the API, including docs-only merges. The image is
identical each time, since every Docker layer came from cache in the live build. Each
deploy restarts the container, clears in-memory caches (the 1 h `/sources` list, the JWKS,
schema detection), logs a Qdrant warning, and, until finding A is fixed, can cut off a
search. Of the 50 deploys listed (22 Nov 17:01 to 26 Nov 17:43), 13 changed anything under
`services/api/`, some of them only its tests. The other 37 restarted the API for nothing.

Fix: watch paths of `/services/api/**`. That covers everything the Dockerfile copies:
`requirements.lock`, `pyproject.toml` and `app/`. Carter can set this in the service's
settings. Not in `railway.toml`: see finding C. Note the side effect from Railway's docs: with watch paths set, an empty commit
no longer redeploys, so use "Deploy Latest Commit" to force one.

### C. Railway stops reading `railway.toml` on 1 Dec 2026 (setting) — corrected

*Corrected on 26 Nov 2026. The first version of this finding named a
`services/api/railway.toml`. No such file exists: the committed file is the root
`railway.toml`, and the first version also said it was very likely ignored. Railway's
docs, found during the review of #505, say otherwise.*

The repository's only config file is the root `railway.toml`. It asks for
`builder = "DOCKERFILE"` (with a `dockerfilePath = "Dockerfile"` that does not exist at
the root) and `restartPolicyType = "ON_FAILURE"` (3 retries). The service's root directory
is `services/api`, no config file path is set, and the dashboard shows `builder: RAILPACK`.
Railway's [Infrastructure as Code page](https://docs.railway.com/infrastructure-as-code)
says that with no path set, the builder still reads a `railway.toml` at the service root or
the repository root. So the root file may be in effect today. The dashboard view cannot tell.

Config as Code is deprecated. **Existing `railway.toml` files stop being read on
2026-12-01 (hard cutoff)**, and new services cannot opt in. Its replacement,
Infrastructure as Code, is a `.railway/railway.ts` file applied with the Railway CLI.

- **The risk on 1 Dec:** if the root file is what keeps the build on the Dockerfile, the
  first deploy after the cutoff could build with Railpack. That would ignore the Dockerfile
  and its `CMD`.
- **Setting (Carter), before 1 Dec:** in the service's settings, set the builder to
  Dockerfile, the healthcheck path to `/health`, the variable
  `RAILWAY_DEPLOYMENT_DRAINING_SECONDS=120`, watch paths to `/services/api/**`, and, if
  wanted, the restart policy to on failure with 3 retries. #505 lists them. There is no
  healthcheck today, so a deploy whose app fails after the container starts can still
  replace a working one. Startup takes about 1 to 2 s, so a healthcheck costs nothing.
- **Later (code):** delete the root `railway.toml` once the dashboard holds these values,
  or move to Infrastructure as Code if config in the repo is wanted.

### D. The startup line logs four key suffixes (code)

`app/rag/api_keys.py` logs `api_keys: A=...xxxx B=...xxxx C=...xxxx D=...xxxx`: the last
four characters of each Anthropic key, at every start (69 times). Four characters are not
enough to use a key, but CLAUDE.md §7 says no secrets in logs, and this line gives nothing
an operator needs. The line also shows that **B, C and D all fall back to key A**: the
four suffixes are identical, and no `ANTHROPIC_API_KEY_B/C/D` variables exist on Railway.
The key rotation it describes is inactive, and HyDE now runs on Luna by default anyway.
Replace the line with `api_keys: distinct keys=1` (a count, not characters).

### E. Refused searches leave no reason in the logs (code)

Two `POST /v1/search/guest` returned 422 (20 Nov 23:47 and 22 Nov 18:23, the second
four minutes after #438 deployed the new collection keys). Neither route logs a
`SearchPlanError` code, and FastAPI's request validation 422s are not logged either. One
`logger.info("search refused: code=%s", exc.code)` in each `except SearchPlanError` would
make such a 422 explainable. It logs a code, not the query.

### F. Six Railway variables are never read (setting)

`ANTHROPIC_MODEL`, `ANTHROPIC_TITLE_MODEL`, `CHAT_HISTORY_WINDOW`, `DAILY_MESSAGE_QUOTA`,
`LLM_MAX_TOKENS` and `RATE_LIMIT_PER_MINUTE` appear nowhere in `services/api/app`. They
belong to the V1 chat API removed in October. `RATE_LIMIT_PER_MINUTE` is misleading: the
search limits are not taken from it. Remove all six.

### G. The 20 Nov disk-full outage: already explained and handled

At 23:38:48 Postgres panicked with `could not write to file "pg_wal/…": No space left on
device`, and the database was down until 23:44:29. During that time the API logged 21
`asyncpg.pool` and `db_keepalive` warnings, Supavisor logged 62 auth errors, and Postgres
logged 275 `not accepting connections`. This is the outage recorded in
`docs/corpus-cleanup/P4-P5-republish-expand.md` (4.1b's as-built note), and the runbook
now measures free disk and estimates WAL before a live step. The logs agree with that
account: nothing failed afterwards, and the API recovered by itself with no restart.
Current state, for the next publish's disk check: database 549 MB, of which `chunks` is
474 MB; the WAL directory holds 1,024 MB; `max_wal_size` is 4 GB.

## Real errors, with counts

| What | Count | Where | Likely cause |
|---|---|---|---|
| Database down (disk full) | 1 outage, 5 min 41 s | Postgres; API pool warnings | Finding G. Known |
| `restore incomplete: expected=40 available=39` | 3 warns (21 Nov 00:33, 00:50 ×2) | `GET /v1/searches/{id}/results`, one search | A passage that search returned was retired by the republish. The restore shows 39 of 40 results, as designed (2.4a). Expected |
| 403 on `/reader` and `/toc` | 4 (22 Nov 19:05, two pairs) | Gaudium et Spes, `?anchor=gaudium-et-spes/79` | The document is `reader_access = excerpt`, so 403 `reader_restricted` is correct. Worth one check: which surface opened the reader for an excerpt document instead of linking to vatican.va (§4 says none should). Possibly an old bookmark or history link from before the republish |
| 422 on `POST /v1/search/guest` | 2 | Guest search | Unknown: finding E |
| 401 on `GET /v1/sources` | 2 (20 Nov 23:47, 22 Nov 16:25) | AppShell's first load | An expired access token sent before the browser refreshed it. The first came just after the outage. Harmless: AppShell fetches again with the new token |
| Auth `bad_jwt: token signature is invalid` | 96 in 11 s (23 Nov 11:44) | Supabase Auth, referer theo-corpus.com | One browser presented a token signed by a key the project no longer accepts, and something retried quickly, most likely the middleware's `getClaims` falling back to the Auth server on each request and prefetch. It happened once. If it recurs, look at the client's refresh loop |
| PostgREST `Thread killed by timeout manager` | 2 to 4 a day | PostgREST | Nothing in this app calls PostgREST (all data goes through FastAPI). These are its idle timeouts. Noise |
| Postgres `ERROR`s from `postgres` via Supavisor | 9 | Ad-hoc SQL | Operator and agent queries during publishes: wrong column names, statement timeouts on `corpus_redirects` during the 22 Nov redirect cleanup (#439), one multi-statement prepared query. Not the app |

## Noise that is not an error

- About 85% of the API's log volume is `httpx` / `httpx2` INFO lines, one per outbound
  request (OpenAI, Qdrant, Cohere, USCCB, JWKS). They are useful for tracing but noisy. Set
  those loggers to WARNING if the volume ever matters. The lines name provider hosts and
  the Qdrant cluster host, but no keys or query strings.
- 16 GETs per window of the previous Qdrant collection (`chunks-collection-keys-2026-11`
  and others): `/health/search` and startup resolving the alias's target. Expected.
- Supabase Auth's `DEPRECATION NOTICE: GOTRUE_JWT_ADMIN_GROUP_NAME / DEFAULT_GROUP_NAME`
  at an Auth restart: Supabase's own platform config, nothing to do.
- Postgres checkpoints, the pgbouncer TLS EOF, and Supavisor connection churn.
- `/v1/health`, `/v1/health/db` and `/v1/health/search` returned 404 (21 Nov 19:17). The
  health routes are at `/health`, not under `/v1`, so this was someone probing the wrong
  path. `GET /health` answers 200.
- One 404 from `GET /v1/reading-progress/{doc}`: no saved position, as designed.
- Security advisor, INFO: 12 tables with RLS on and no policies. This is intended (§4:
  "RLS on, no policies, revoked from anon/authenticated"). WARN `vector` extension in
  `public`: pgvector is unused (§4). Moving it is a migration with no benefit; leave it.
- Performance advisor: 15 `auth_rls_initplan` warnings. The API connects as `postgres` and
  bypasses RLS, so the per-row re-evaluation never runs on app traffic. Eight unused
  indexes, mostly on tables no longer written (`chat_sessions`, `compare_runs`); dropping
  them reclaims little. Unindexed foreign keys (recommendation 13): only the ones a
  `purge-retired` delete checks matter, namely `bookmarks.chunk_id`,
  `guest_trial_retrievals.chunk_id`, `product_feedback.chunk_id` / `document_id`,
  `reading_progress.document_id` and `search_costs.search_id`. Each deleted row scans
  those tables, which are tiny today.

## Logged at the wrong level

**Nothing found.** Every API line in the window is one-line JSON on stdout with a `level`
attribute. The only lines without a logger are Railway's own `Starting Container` and
`Stopping Container`. No line reached Railway as an error: the `@level:error` filter
returns nothing for the week, and the Qdrant warning arrives at warn through `py.warnings`
as intended. The two levels worth reconsidering are judgement calls, not violations:

- `restore incomplete` is a warn for a designed outcome (a retired passage). Info would fit
  better, keeping warn for a shortfall with no retirement behind it.
- `db_keepalive: ping failed` is a warn on every miss. During the outage it was the right
  signal; keep it.

## Data that should not leak

- **Keys:** the four key suffixes in finding D. No full keys, tokens or `Authorization`
  headers appear anywhere in the API or Supabase logs.
- **User content:** none in the API logs. Search lines carry counts, timings and costs,
  never the query; search, bookmark and preference routes log only exception class
  names. Access-log lines carry document UUIDs and chapter and anchor parameters, not
  query text. The client IPs in the access log are Railway's internal proxy addresses
  (`100.64.x.x`), not users'.
- **Emails:** none in the API logs. Railway's deployment metadata shows the deploying
  account's email, which is Railway's UI, not an application log.
- **Supabase:** the Postgres log keeps the full text of ad-hoc operator queries, which is
  normal. No user data appeared in them this week.
- **Analytics:** there is nothing to leak while PostHog is off. The event code already
  strips query text and referrers.

## Still to read

Vercel runtime errors, runtime logs and the latest production build log. Carter, if you
want these covered, either approve the Vercel connector for the `carter-tates-projects`
team (the consent link expires after 10 minutes, so ask a thread for one while you are at
a screen), or export the build log of the deployment for `bab76f8` and the last 7 days of
runtime errors. While doing that, you could also read the two PostHog variable names in
Vercel's Production environment, to confirm item 1's diagnosis from the dashboard side.
