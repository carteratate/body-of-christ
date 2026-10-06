# P0: checks, provenance, identity, safety, and research

**Before implementing any item in this file, follow `README.md` in this folder. It says to ask Carter the item's open questions first, record the answers, and update other specs only in the ways it allows.**

1. Phase 0 builds the guard rails every later corpus change is measured against. It changes no live data.
2. First CI and a PR template (0.0), so each later PR shows green source-free tests and a pasted local source-check report.
3. Then the publish lock (0.4), which must merge before any Phase 1 adapter PR. Today a routine `run_collection.py` run would cascade-delete saved user rows. The lock stays in force after P4: every publish, then and later, needs a reviewed lock-file change that names its collection and release (D2).
4. Then the source checks, in this order: coverage and sequence tests (0.1a), health rules (0.1b, whose H2 rule uses 0.1a's `known_defects.json`), and the release report with its old-to-new remap (0.1c). 0.1c defines the remap vocabulary (`same`, `moved`, `split`, `merged`, `renumbered`, `removed`, D5) and fails any build where an unchanged anchor's text drifts without a redirect (D1).
5. Then provenance: a tracked hash lock for every vendored file plus a public-facts rights inventory (0.2).
6. Then identity: the work registry (2.1). It freezes today's 421 document IDs and today's passage IDs, moves anchors to source structure without re-keying any passage (D1), holds the rule A and attribution fields, and holds the one removal registry that every later removal is recorded in (D4). It also defines, in Python, the genre list, the work model and the passage fields `searchable`, `language` and `passage_author`, so Phase 1 adapters can use them before Phase 2 (D11). Its PR is the first real user of the 0.1c remap.
7. Then the baseline eval (0.3), run with judging against the live corpus before any live change (D7), and the Qdrant limits read (0.5) and storage snapshot (0.6), both read-only ops.
8. Research items R1 to R6 need no code and can start on day one in parallel. Each entry names the items it blocks. R1 blocks 3.1, 3.2 (the Refutation of All Heresies), 5.6a and 5.6b. R6 blocks 1.2c, 1.2d, 1.8d and every 5.x addition. R2 and R3 are specified only here; the P1a file points to them.
9. Recommended merge order: 0.0, 0.4, 0.1a, 0.1b, 0.1c, 0.2, 2.1, then the 0.3 run. Ops 0.5 and 0.6 any time before P4. R1 to R6 in parallel.
10. Nothing in P0 to P3 writes to live data (D7). The one possible exception is retiring On the Incarnation (1.8d) before P4, and only if Carter approves it.
11. Evidence below was gathered on 29 Sep 2026 from master at `5475c49`, a fresh clone in a scratch directory, the vendored sources, and read-only SELECTs against Supabase project hvmgffvimqgiejmxwhwq.

Conventions used in this file:

- Paths are relative to the repo root of `body-of-christ` unless they start with `/`.
- "Live" means the production Supabase project hvmgffvimqgiejmxwhwq and the production Qdrant cluster.
- "Master build" means running every adapter in `datapipeline/publication.py` `SOURCE_ADAPTERS` on master against the vendored sources, touching no store.
- D1 to D11 are the "Cross-cutting design decisions" in `docs/2026-09-28-corpus-cleanup-plan.md`. Where this file and those decisions disagree, the decisions win.
- Every SQL count quoted here came from a read-only SELECT on 29 Sep 2026. Counts that move (retrievals, guest rows) must be re-read when used.

---

### 0.0. GitHub Actions for source-free tests, and a PR template

- **Type:** PR
- **Depends on:** none
- **Goal:** Every PR runs the tests that need no vendored sources and no secrets, on GitHub's free runners for public repos. Checks that need the gitignored sources run on Carter's Mac, and their output becomes a required section of the PR description. This makes "tests pass" visible and repeatable for every later cleanup PR, and it fixes the three environment gaps that would otherwise make CI red on day one.
- **Current state:**
  - No `.github/` directory exists on master (`ls .github` fails). `docs/ci-cd-plan.md` (drafted 9 Sep, not adopted) proposes a five-job workflow but targets branch `main`. The default branch is `master`.
  - Datapipeline, fresh clone with no `datapipeline/.env` and no `datapipeline/sources/`: 744 passed, 19 skipped, 14 failed. With the sources symlinked in and still no `.env`: 773 passed, 4 failed.
  - The 4 order-dependent failures are `tests/test_enrichment_sample_run.py::test_run_end_to_end_against_single_mocked_chunk`, `::test_run_isolates_failures_and_continues`, `tests/test_pass1_pilot_diff_report.py::test_run_end_to_end_against_single_mocked_chunk`, and `tests/test_pass1_questions_cosine_audit.py::test_run_end_to_end_against_single_mocked_chunk`. All 35 tests in those three files pass when run alone. Root cause, verified: `datapipeline/config.py:147-154` builds the frozen `settings` object once at first import and reads `ANTHROPIC_API_KEY` then. Earlier test modules (for example `tests/test_apostolic_exhortations.py:2-5`) import `config` after setting only the four required variables, so the later `os.environ.setdefault("ANTHROPIC_API_KEY", ...)` in `tests/test_enrichment_sample_run.py:7` has no effect, and `settings.require_anthropic()` (`config.py:138-144`) raises. On Carter's Mac a real `datapipeline/.env` hides this.
  - The other 10 failures without sources are `FileNotFoundError` in tests that lack the `skipif(not _vendored)` guard used elsewhere: `tests/test_catechism_passages.py` (3 tests), `tests/test_church_fathers.py` (5), `tests/test_summa.py` (2). Nineteen tests in other files already skip correctly (for example `tests/test_encyclicals.py:60`).
  - `tests/test_bm25_fit.py` carries the `smoke` marker (network or disk heavy, `datapipeline/pytest.ini:4-5`). `enrichment/validation.py:20` downloads the `cl100k_base` tokenizer at import, so CI needs network (GitHub runners have it).
  - API, fresh clone: collection stops at `tests/test_hyde_steps.py:6` (`import httpx2`, `ModuleNotFoundError`). With that file ignored, 777 passed. `httpx2` is not declared in `services/api/pyproject.toml`. The test arrived in commit `d89a671` (29 Aug), which also pinned `anthropic==1.2.0`. Whether `anthropic==1.2.0` pulls `httpx2` in transitively is **not verified** (the local interpreter has `anthropic 0.111.0`, which does not). `httpx2 2.13.1` exists on PyPI.
  - API conftest already solves the settings-at-import problem correctly: `services/api/tests/conftest.py:5-21` sets stub variables in `pytest_configure`.
  - Web, fresh clone with `node_modules` linked: `npm run lint` gives 0 errors and 4 warnings (2 in `src/components/common/ErrorBoundary.tsx`, 2 in `src/app/icon-preview/`). `npx vitest run` passes 392 tests in 42 files. `npx tsc --noEmit` reports one error, `src/lib/preference-writer.test.ts(12,5)`, where a `number` is assigned to `default_quota` whose type is `3 | 4 | 5 | 10`-like.
  - `apps/web/package.json:5-7` declares `node >=20`. Vercel builds with Node 24.x (project setting `nodeVersion`, read 4 Oct), so CI uses 24.
  - The API Docker image uses `python:3.11-slim` (`services/api/Dockerfile:1`). The datapipeline has no pinned Python.
- **Changes:**
  - Add `.github/workflows/ci.yml`, triggered on `pull_request` and on `push` to `master`, with three parallel jobs and `permissions: contents: read`. No secrets are used by any job.
    - `web`: `actions/setup-node` with Node 24, the Vercel project's major, `npm ci` in `apps/web`, then `npm run lint`, `npx tsc --noEmit`, `npx vitest run`. Cache `~/.npm` keyed on `apps/web/package-lock.json`. Do not run `next build` in CI; Vercel already builds every PR preview, and the build may need public env vars.
    - `api`: `actions/setup-python` 3.11, `pip install -e "services/api[dev]"`, then `python -m pytest -q` in `services/api`. Do not add ruff or a Docker build in this PR.
    - `datapipeline`: `actions/setup-python` 3.11, `pip install -r datapipeline/requirements.txt`, then `python -m pytest -q -m "not smoke"` in `datapipeline`. Cache the tiktoken directory (`TIKTOKEN_CACHE_DIR` set to a workspace path) keyed on `requirements.txt`.
  - Fix the order dependence at its cause. Add a `pytest_configure` hook to `datapipeline/tests/conftest.py` that calls `os.environ.setdefault` for `DATABASE_URL`, `OPENAI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY` and `ANTHROPIC_API_KEY` with obviously fake values, mirroring `services/api/tests/conftest.py`. Leave the per-module `setdefault` lines alone (they become redundant but harmless). Note that `load_dotenv()` at `config.py:15` does not override variables that are already set, so on Carter's Mac the real `.env` values still win only for variables the conftest does not set first. Because `setdefault` never overwrites an existing value, a developer who exports real keys in their shell keeps them.
  - Mark the source-dependent tests. Add a `sources` marker to `datapipeline/pytest.ini`, and guard them with `pytest.mark.skipif(not <path>.exists(), reason="<collection> sources not vendored")` using the same pattern as `tests/test_medieval.py:12`: module-level `pytestmark` in `test_catechism_passages.py` and `test_church_fathers.py`, where every test reads sources (all six in the Fathers file; one passes vacuously without them), and per-test on the two `build_document` tests in `test_summa.py`, whose `_split_article` tests use inline text and must keep running in CI. Paths are `sources/catechism/ccc.json`, `sources/church-fathers/` (the six tests read `apostolic fathers.xml`, `city-of-god.xml`, `confessions.xml`, the other ANF volumes, and the whole folder through `build_all()`), and `sources/summa/summa.xml`.
  - Fix `httpx2`. First, in a fresh virtualenv run `pip install -e "services/api[dev]"` and `python -c "import httpx2"`. If it imports (arrives through `anthropic==1.2.0`), add `"httpx2"` to the `dev` extra anyway so the test's direct import is declared. If it does not import, add it to `dev` with a lower bound matching the version pip resolves. Do not change `test_hyde_steps.py` itself; its point is to exercise the real SDK transport.
  - Fix the `tsc` error in `apps/web/src/lib/preference-writer.test.ts:7-15` by typing the helper's parameter as the existing quota type from `src/lib/search-draft.ts` (`SearchQuota`) instead of `number`. Test-only change.
  - Add `.github/pull_request_template.md` with these sections, in this order:
    - "What changed and why" (free text).
    - "Production safety" checklist: no migration, or migration is additive and nullable or defaulted; API tolerates the change being absent; no datapipeline run against live stores; no Qdrant change.
    - "Source checks (run locally)", required whenever the diff touches `datapipeline/`. It holds the output of `python3 scripts/vendor_sources.py --collection all --verify` (from 0.2 on, `python3 scripts/source_lock.py --verify`), the coverage and sequence summary (0.1a), the health summary (0.1b), and the release report summary (0.1c), each pasted in a collapsed `<details>` block. The section states "Not applicable: this PR does not touch datapipeline/" when that is true.
    - "About page" checkbox: "This PR changes an inclusion rule or what a collection holds; the About page item is updated or ticketed" (from the Decision log row "About page").
    - "Spec changes", required whenever the diff touches `docs/corpus-cleanup/`. One line per edited spec: the file, the item, what changed and why, per `docs/corpus-cleanup/README.md` section 3. It also names the `NEEDS-CARTER.md` entries this PR answered, and states "No spec changes" when that is true.
    - "Review", quoting the fresh-context reviewer's findings and what was done about each (`README.md` section 4).
  - Update `docs/ci-cd-plan.md` only by adding one line at the top noting that its Phase 1 CI shipped in this PR with the scope above; do not rewrite it.
- **Acceptance checks:**
  - The workflow runs green on the PR itself, all three jobs.
  - In a fresh clone with no `datapipeline/.env` and no sources, `python -m pytest -q -m "not smoke"` in `datapipeline` reports 0 failures. Expected shape is about 744 passed and about 29 skipped (19 existing skips plus the 10 newly guarded tests); the PR description quotes the real numbers.
  - The same command with sources present and no `.env` reports 0 failures (previously 4).
  - `python -m pytest -q` in `services/api` collects `test_hyde_steps.py` and reports 0 failures in a fresh virtualenv built from `pyproject.toml`.
  - `npx tsc --noEmit` exits 0; `npm run lint` still reports 0 errors and exactly 4 warnings.
  - Add `datapipeline/tests/test_conftest_env.py::test_optional_anthropic_key_is_stubbed_before_config_import`, which asserts `config.settings.ANTHROPIC_API_KEY` is not `None` inside the test session. It fails on master's conftest and passes after the change.
  - The PR description lists the before and after test counts for all three suites and pastes the job URLs.
- **Production safety:** CI runs only on GitHub's runners, uses no secrets, and deploys nothing. The only non-test code change is a dev-extra dependency line, which the production Docker image does not install (`pip install --no-cache-dir .` in `services/api/Dockerfile:9` skips extras). Vercel and Railway deploy exactly as today.
- **Needs Carter:**
  - Approve the push and PR on the public repo.
  - After merge, turn on branch protection for `master` requiring the three jobs (a GitHub settings change only Carter can make).
  - Confirm the Node major Vercel uses, if not 20.
- **Out of scope:** Migration validation against Postgres, Docker builds, secret scanning, `npm audit`, ruff, deploy workflows (all in `docs/ci-cd-plan.md` for later). Any source-dependent check in CI. Changing `config.py` to lazy settings.

---

### 0.4. Publish lock

- **Type:** PR
- **Depends on:** 0.0 (so the PR runs in CI); must merge before any P1 PR
- **Goal:** Nobody can write to the live reader store or search index by accident or by routine repair. Adapter fixes will add, retire and redirect passages, and today's publish path prunes by deleting, which removes users' saved history rows through foreign-key cascades. After this PR, the only way a datapipeline command (a publish, an apply, a rollback, a repair script, a V5 stage or a one-off data script a spec names) can write to the corpus tables or Qdrant in production is a reviewed change to the lock file that lists the collection and release, plus matching CLI flags. That rule is permanent. The lock does not cover ops steps done by hand, such as applying a migration, creating a Qdrant alias or payload index, `VACUUM FULL`, or the deletions after a rollback window; Carter approves each of those separately when it runs. It governs the P4 cutover (4.1b) and every steady-state publish after P4, which also runs stage then apply (D2, 2.2w). Nothing is listed in the lock file before the P4 apply (D7), with one possible exception, retiring On the Incarnation (1.8d), and only if Carter approves it.
- **Current state:**
  - `datapipeline/run_collection.py:62-86` builds a `PublicationRequest` and calls `production_runner().publish(...)` with no lock. `publication.py:121-187` prunes reader passages (`reader.write(..., prune=True)`), reader documents (`prune_documents`), and Qdrant points (`search.prune`) on every unlimited run.
  - The only safety nets are `_validate_build` (`publication.py:224-248`), which refuses more than 10% shrink or more than 10% identity churn per collection, and the exact-name confirmation for `--wipe-reader` (`publication.py:204-211`). A change that replaces 9% of a collection's IDs passes both.
  - Live foreign keys, read from `information_schema` on 29 Sep: `retrievals.chunk_id`, `bookmarks.chunk_id`, `retrieval_labels.chunk_id`, `guest_trial_retrievals.chunk_id` all `ON DELETE CASCADE` to `chunks`; `reading_progress.document_id` and `document_chapters.document_id` cascade from `documents`; `product_feedback` uses `SET NULL`.
  - Measured risk today: live user tables reference 1,685 distinct passage IDs (retrievals, bookmarks, guest_trial_retrievals, retrieval_labels). A master build emits 54,778 passage IDs; 12 of the 1,685 are not among them (in apostolic-exhortations, catechism, encyclicals, medieval). Publishing those collections from master today would cascade-delete 19 `retrievals` rows and 2 `guest_trial_retrievals` rows, with no refusal, because each collection's churn is under 10%.
  - Other entry points that write live stores:
    - `scripts/backfill_missing_vectors.py`, `scripts/reembed_drifted_vectors.py`, `scripts/reconcile_qdrant_payloads.py`, each gated only by `--apply` (dry run by default).
    - `pipeline.py` (V5 stage engine), whose `reader`, `embed` and `bm25-index` stages obtain `asyncpg` pools or the Qdrant client at `pipeline.py:156-167`. `stages/reader.py` calls `reader_writer.clear_collection`, which deletes a whole collection. `stages/embed.py` upserts and deletes points, and `stages/bm25_index.py` calls `update_vectors` on `QDRANT_COLLECTION`. `stages/enrich_io.py:24-27` writes to Postgres (`UPDATE chunks SET annotation` and `annotation_vector`), verified 29 Sep.
- **Changes:**
  - Add a tracked file `datapipeline/PUBLISH_LOCK.json`. It ships with an empty list:
    ```json
    {
      "since": "2026-09-29",
      "reason": "Live writes only for a collection and release listed below, added in a reviewed PR. See docs/2026-09-28-corpus-cleanup-plan.md, D2 and D7.",
      "approved_applies": []
    }
    ```
    Each item in `approved_applies` has the form `{"collection": "councils", "release": "2026-11-cleanup", "steps": ["stage", "apply", "rollback"], "reason": "...", "approved_by": "Carter", "pr": "<PR number>"}`. This is the only lock format (D11). `collection` is one registered collection name, or `"all"` for a run that touches every collection. `release` is the release name, which is also the publish ID (`corpus_publishes.id`, 2.2a) and names the staging Qdrant collection `chunks-<release>`. `steps` names what the entry allows:
    - `stage`: build into the `staging` schema and the new Qdrant collection (2.2w).
    - `apply`: the one-transaction apply, the `chunks_live` alias switch, and dropping the staging tables afterwards.
    - `rollback`: 2.2w's `rollback` command for this release.
    - `repair`: a narrow write outside stage then apply, meaning one of the repair scripts, a V5 stage listed below, or a one-off data script that a spec names and gates this way (5.1b.3's collection-key rewrite). This step value is the whole repair mechanism; there is no other.

    A PR that adds an entry is the review. An entry that allows `apply` also lists `rollback`, and stays in the file until that release's rollback window closes (4.1b sets the window). A later reviewed PR removes it, so the file is empty between publishes.
  - Add `datapipeline/publish_lock.py` with:
    - `class PublishLocked(ValueError)` (a `ValueError` so `run_collection.main` reports it through `parser.error`, exit code 2, like other refusals).
    - `def load_lock(path: Path = DEFAULT_PATH) -> PublishLock` returning a frozen dataclass holding the entries. A missing or unparsable file, or one without an `approved_applies` list, counts as an empty list (fail closed).
    - `def assert_live_write_allowed(action: str, collection: str, release: str | None, step: str, lock: PublishLock | None = None, targets: WriteTargets | None = None) -> None`. `WriteTargets` holds the database URL and the Qdrant URL the command will write to, read from settings when not passed. It passes in two cases only:
      1. Both URLs name a loopback host (`localhost`, `127.0.0.1` or `::1`). Local rehearsals against a restored `pg_dump` and a local Qdrant (D8) therefore need no lock entry. One loopback URL and one remote URL does not count, and the check fails closed.
      2. `release` is a non-empty string and some entry has the same `collection`, the same `release` and `step` in its `steps`.

      Otherwise it raises `PublishLocked` with the action, the lock reason, and how to get approval (add an entry in a reviewed PR and pass `--collection <name> --release <same value>`). There is no other bypass: no environment variable, flag or setting skips the check.
  - `publication.py` (as built: `publish_lock_guard()`, `production_runner(lock_path=None)`, and a `build()` method that runs the adapter and document checks without a store, used by the dry run): add an optional `write_guard: Callable[[PublicationRequest], None] | None` parameter to `CollectionPublicationRunner.__init__`, called at the top of `publish` right after `_validate_request` and before any source adapter runs or store is acquired. `production_runner()` passes a guard that calls `assert_live_write_allowed(f"publish {collection} to {target}", request.collection, request.release, "apply")`. Add `release: str | None = None` to `PublicationRequest`. Test fakes construct the runner without a guard, so existing tests keep their meaning. When 2.2w replaces today's delete-based publish with stage then apply, it calls the same function with step `stage` before writing staging tables and with step `apply` before the transaction and the alias switch. The staging schema lives in the production database, so staging counts as a live write too.
  - `run_collection.py`: add `--release RELEASE_ID` (passed into the request) and `--dry-run`. Dry run builds the documents, runs `_validate_documents` (and from 0.1b the health rules), prints collection, document count, passage count, and never acquires a store. Dry run is allowed while nothing is listed. It is the command 0.1c and every P1 PR use.
  - The three repair scripts: at the start of the `--apply` branch, call `assert_live_write_allowed(f"<script> --apply", args.collection, args.release, "repair")` and add a `--release` argument. Each script already has `--collection` (`backfill_missing_vectors.py:272`, `reembed_drifted_vectors.py:240`, `reconcile_qdrant_payloads.py:302`), and a run over every collection already passes `all`. Dry runs stay allowed.
  - `pipeline.py`: in `_main`, after `resolve_stages`, if any resolved stage is in `{"reader", "embed", "bm25-index", "enrich"}` and neither `--dry-run` nor `--status` is set, call the guard with step `repair`, using the existing `--collection` argument (`pipeline.py:311`) and a new `--release` argument. As built (`_guard_live_writes`), a lone `--stage enrich --sample N` run is also exempt, because it writes only under `samples/` (`pipeline.py`, `_run_enrich`). `enrich` is in the set because `stages/enrich_io.py` writes to Postgres (verified above).
  - This PR only guards these entry points. 2.2w later points each one at `QDRANT_WRITE_COLLECTION` or retires it (D11, "Other writers").
  - Update `datapipeline/README.md` (sections "Publish one collection" and "Narrow repair commands") and `datapipeline/SOURCES.md` ("Publishing a collection") with one paragraph each on the lock, the dry run, and how an apply is approved. Update the repo `CLAUDE.md` Quick Commands comment for the datapipeline to show `--dry-run`.
- **Acceptance checks:**
  - `tests/test_publish_lock.py`:
    - `test_missing_lock_file_counts_as_empty`
    - `test_unparsable_lock_file_counts_as_empty`
    - `test_empty_list_refuses_every_write_even_with_flags` (the state this PR ships)
    - `test_refuses_without_release`
    - `test_refuses_wrong_release`
    - `test_listed_release_refuses_other_collection`
    - `test_listed_entry_refuses_step_it_does_not_name` (an entry with `["stage"]` refuses `apply`)
    - `test_matching_collection_release_and_step_pass`
    - `test_all_entry_is_needed_for_all_collections`
    - `test_rollback_step_is_its_own_permission` (an entry with `["stage", "apply"]` refuses `rollback`)
    - `test_loopback_database_and_qdrant_pass_without_entry`
    - `test_one_remote_target_is_refused` (loopback database with remote Qdrant, and the reverse)
    - `test_no_environment_bypass` (no environment variable other than the two URLs changes the result)
  - `tests/test_collection_publication.py::test_write_guard_runs_before_adapters_and_store_acquisition`: a guard that raises must leave the fake adapter uncalled and no store acquired.
  - `tests/test_run_collection.py::test_dry_run_acquires_no_store_and_prints_counts` and `::test_live_publish_is_refused_while_locked` (uses the real `production_runner` guard with a temp lock file, and asserts exit code 2 and the word "locked" on stderr without any network call).
  - One test per repair script, `test_apply_is_refused_while_locked`, and for `pipeline.py`, `test_reader_stage_is_refused_while_locked` and `test_enrich_stage_is_refused_while_locked`.
  - Manual check pasted into the PR: `python3 run_collection.py --collection catechism --target both` exits 2 with the lock message, and `python3 run_collection.py --collection catechism --dry-run` prints about 809 passages.
  - The shipped `PUBLISH_LOCK.json` has an empty `approved_applies` list (asserted by `test_repository_ships_with_no_approved_applies`).
- **Production safety:** Adds refusals only; removes no capability that Phase 0 to 3 is allowed to use. API and web are untouched. Nothing runs against live stores.
- **Needs Carter:**
  - Approve the PR.
  - Agree that every production write to the corpus tables or Qdrant by a datapipeline command, before and after P4, goes through a reviewed PR that adds a lock-file entry naming the collection and release. That covers emergency repairs too. The only exemption is a run whose database and Qdrant are both on the local machine (a rehearsal). There is no other bypass. Hand-run ops steps (migrations, alias and index creation, `VACUUM FULL`, post-window deletions) are outside the lock and approved one by one.
  - Agree that an entry stays in the file through its release's rollback window and is removed by a second reviewed PR afterwards.
  - Agree that no entry is added before the P4 apply (D7), except possibly one for retiring On the Incarnation (1.8d), which he decides separately.
- **Out of scope:** Any change to pruning or churn thresholds (2.2w replaces the delete-based prune). Remap tooling (0.1c, 4.1a). Qdrant alias work (2.2b). Removing the V5 `stages/` engine.

---

### 0.1a. Coverage and sequence tests

- **Type:** PR
- **Depends on:** 0.0, 0.4
- **Goal:** Measure, for every collection, how much of the source's body text reaches a passage, and whether numbered units (verses, paragraphs, canons, articles, sections) are all present exactly once. The Vatican II loss shows that the existing tests check the adapter's own output shape and can pass while half a document is missing. These checks compare against the source, independently of the adapter, and every P1 PR must show its numbers move the right way.
- **Current state:**
  - No source-completeness check exists. `scripts/audit_sources.py` (166 lines) prints structural statistics for sources but compares nothing to adapter output.
  - Known losses from the 28 Sep audits, to be reproduced by these checks:
    - Vatican II: 436 of 614 numbered sections lose continuation paragraphs, about 542,560 characters, plus 76 spurious footnote passages (`docs/research/2026-09-28-corpus-health-and-retrieval-audit.md`, table "The Nostra Aetate failure"). The plan gives Gaudium et Spes 74,319 of 216,676 characters kept.
    - Other councils: Trent keeps 204,107 of about 549,814 characters, Vatican I 6,053 of about 54,223, Nicaea 4 passages.
    - Bible: 245 verses missing against WEB-C live (244 in the current build, see 1.4a), including Daniel 3:24-90 region, Daniel 13 and 14, Esther 4:18-47 and 10:4-14. Verified for Esther on 29 Sep: `sources/bible/eng-web-c_usfm/43-ESGeng-web-c.usfm` has chapter 4 verse markers up to 47 and chapter 10 up to 14, while live Esther passages stop at "Esther 4:4–17" and "Esther 10:1–3".
    - Canon law: 266 and 1330 missing; 112, 238, 689, 1308 (new), 1310 (new) glued into the previous canon.
    - Summa: Part I questions 71 and 72 missing.
    - Ignatius letters: pre-chapter greeting paragraphs skipped (plan cites line 9621 of `sources/church-fathers/apostolic fathers.xml`).
    - Papal: list text dropped (In Dominico Agro 224 characters, Annus Qui Hunc 2,277). The cause is `<ol>`/`<li>` markup the adapter does not read, not Roman-numeral headings (1.3a).
  - Master build counts (29 Sep, scratch clone): 54,778 passages in 382 plus 39 documents across 10 collections, matching the audit's per-collection rows. (The audit's total row first read 54,776, but its collection rows sum to 54,778, and live 54,568 minus 163 plus 373 is 54,778. Corrected by 0.1c, which built 5475c49 again with the same sources and got 54,778.)
  - `thml_doc.make_doc` skips chapter elements with less than 100 characters of direct text (`datapipeline/ingest/thml_doc.py:47-48`); coverage must count those as intentionally dropped only if they are headings.
- **Changes:**
  - New package `datapipeline/checks/`:
    - `checks/source_text.py`. One extractor per source format, written independently of `ingest/` (no imports from `ingest/` except path constants). Each returns `list[SourceUnit]`, where `SourceUnit = (source_file: str, unit_id: str | None, text: str, region: str)` and `region` is `"body"`, `"note"`, `"toc"`, `"heading"`, or `"apparatus"`. Formats:
      - ThML XML (church-fathers, medieval, summa). Body is `<p>` text inside `div1` to `div6`; `<note>` is `"note"`; `<scripCom>` and `<pb>` are ignored. `unit_id` is the nearest ancestor div's `id` attribute.
      - vatican.va and papalencyclicals.net HTML (encyclicals, apostolic-exhortations, papal-documents, councils, canon-law). Body is visible `<p>`, `<li>` and `<div>` text in the main content element; text after the first notes marker (a horizontal rule followed by numbered notes, or an element whose text starts "Notes" or "NOTES") is `"note"`. `unit_id` is the leading paragraph or canon number when present.
      - USFM (bible). One unit per `\v`, with `unit_id` `"<BOOK>/<chapter>/<verse>"`.
      - `ccc.json` (catechism). One unit per numbered paragraph, `unit_id` the CCC number.
    - `checks/coverage.py`. `def coverage(collection: str, documents: list[Document], units: list[SourceUnit]) -> CoverageResult`. Normalization is NFKC, lowercase, curly quotes to straight, footnote markers like `[12]` and `{{v:N}}` removed, whitespace collapsed. Body units are split into sentences at `[.!?]` followed by whitespace and an uppercase letter, keeping sentences of 30 or more characters. A sentence counts as covered when its normalized form is a substring of the normalized concatenation of all passages built from the same source file (`Document.metadata["source_file"]` where the adapter sets it, otherwise the manifest mapping of file to document). `CoverageResult` holds per source file and per document the body characters, covered characters, coverage percentage, the count of "note" sentences that appear in passages (note leakage), and up to 20 uncovered sentence locations (unit_id plus the first 60 characters, printed locally only).
    - `checks/sequence.py`. One function per numbered family, each returning `SequenceResult(missing: list[str], duplicated: list[str], out_of_range: list[str])`:
      - `bible_verses`: every `unit_id` in the USFM must fall inside some passage's verse range, read from the passage `reference` (for example "Esther 4:4–17") or from `metadata` if the adapter records verse bounds.
      - `ccc_paragraphs`: 1 to 2865 each present once, read from passage references and `unit_label`.
      - `canons`: 1 to 1752 each the subject of exactly one passage anchored `can/<n>`, and no passage whose text contains a second "Can. <m>" heading.
      - `summa_articles`: every (part, question, article) in `summa.xml` present.
      - `numbered_paragraphs`: for each encyclical, exhortation, papal document and Vatican II document, the § numbers found in the source body match the § numbers in built passage references, with no gaps, duplicates, or numbers above the source maximum (catches footnotes read as sections).
      - `thml_chapters`: every ThML chapter div with 100 or more characters of body text is represented by at least one passage.
    - `checks/known_defects.json` (tracked). One entry per currently failing check, keyed by a stable check id (for example `"sequence.canons.missing:266"`, `"coverage.councils.vat2-nostra-aetate.html"`), with `"fixed_by"` (the P1 PR id such as `"1.5"`) and a one-line description. No corpus text.
    - `checks/baselines/coverage-master-2026-09.json` (tracked). Per source file and per document, body characters, covered characters and percentage, measured on master. Numbers and IDs only, no text, so it is safe in the public repo.
    - `checks/report.py`, CLI: `python3 -m checks.report --collection all|<name> [--baseline checks/baselines/<file>] [--out <dir>]`. Builds documents through `SOURCE_ADAPTERS`, runs coverage and sequence, and writes `<out>/coverage.json`, `<out>/sequence.json`, and `<out>/summary.md` (a table per collection with coverage percentage, delta against the baseline, sequence gaps, and known-defect status). `--out` defaults to `datapipeline/releases/local/checks-<timestamp>/`, which this PR adds to `.gitignore`. `summary.md` is what gets pasted into the PR template.
  - Tests in `datapipeline/tests/source_checks/`, each module guarded by `skipif` on the relevant `sources/` path so CI skips them:
    - `test_coverage.py`, parametrized per collection. Each source file's coverage must be no lower than its baseline minus 0.5 percentage points, unless the file has a `known_defects.json` entry whose `"expected_direction"` is `"down"` (used later by rule G removals, which intentionally cut editorial text).
    - `test_sequence.py`, parametrized per numbered family. Each known defect is marked `pytest.mark.xfail(strict=True)`, so a P1 PR that fixes one must delete its entry or the suite fails (xpass under strict fails). Anything not listed must pass.
    - `test_sentinels.py`, minimum sizes for units the audits named, written as numbers rather than quoted text: Nostra Aetate §4 at least 2,000 characters, Dei Verbum §12 at least 1,500, Gaudium et Spes total at least 200,000, Trent total at least 500,000, Vatican I total at least 50,000, Daniel chapters 13 and 14 present, Summa I q.71 and q.72 present. All start as strict xfail with `fixed_by`.
  - Unit tests that run in CI, in `datapipeline/tests/test_checks_unit.py`, using tiny inline fixtures written for the test (no corpus text): normalization, sentence split, a covered and an uncovered sentence, a gap, a duplicate, an out-of-range number, and the xfail bookkeeping (a known defect that now passes is reported as "fixed, remove entry").
- **Acceptance checks:**
  - CI runs `test_checks_unit.py` green.
  - Locally with sources, `python3 -m pytest tests/source_checks -q` passes (all known defects xfail, nothing unexpected).
  - `python3 -m checks.report --collection all` on master reproduces the audit to within 5%: Vatican II coverage near 42% of body characters, Gaudium et Spes near 74,319 of 216,676 characters if the extractor includes notes (report both with and without notes), 245 missing Bible verses, canons 266 and 1330 missing, Summa I q.71 and q.72 missing. Where it does not reproduce, the PR explains the difference.
  - The PR description pastes `summary.md` and lists every `known_defects.json` entry with its `fixed_by` PR.
  - Runtime on Carter's Mac under 3 minutes for `--collection all` (the master build alone takes about 14 seconds).
- **Production safety:** Read-only against local files. No store is touched; the checks call adapters directly and the publish lock is untouched. Nothing ships to API or web.
- **Needs Carter:** Nothing, beyond reviewing the known-defect list.
- **Out of scope:** Fixing any defect. Rule G classification of editorial text (1.8a, 1.8b). Comparing against editions other than the vendored files.
- **As built (5 Oct 2026):** facts recorded by the implementing PR.
  - Matching. Sentences are compared on their letters and digits only, after the normalization above. Adapters join inline markup with spaces (`get_text(" ")`), print ellipses differently, and move markers such as "Objection 1:" into `unit_label`, so spacing and punctuation are not evidence. A sentence with no letters or digits (a rule of asterisks) is not measured. A passage's text for matching is its `unit_label` followed by its content. A bracketed number after the Summa's reference tokens ("Q[1]", "AA[3]") is kept; `[Page N]` markers are removed with footnote markers.
  - Extractors. The HTML main element is papalencyclicals.net's `div.entry-content`, the current vatican.va `div.documento`, or the old vatican.va layout's largest table cell. The notes markers also include papalencyclicals.net's "REFERENCES:" heading and a block opening with "[1]" (Verbum Domini's rule sits outside the main element). Blocks that are entirely links (language bars, tables of contents) are "toc"; site footers are "apparatus". A leading paragraph or canon number is the unit id and is removed from the measured text. ThML text has entities the source escaped twice (`&amp;gt;`) unescaped. ThML body includes `<verse>` blocks (poems and quoted hymns as `<l>` lines) as well as `<p>`. The Summa is read as the reader sees it: its editor's `[*…]` notes are "note" units, and its reference shorthand ("FS, Q[24], A[3]", "OBJ[2]") is spelled out as the adapter prints it ("First Part of the Second Part, Q. 24, A. 3", "Objection 2"); `checks/source_text.py` holds its own copy of the rules. Without this the Summa read 93.4% instead of 97.8%, and its articles 95.6% instead of 99.97%. Coverage measures the files the vendored manifests list; files downloaded but never published (Amoris Laetitia, A New Hope for Lebanon, Ubicumque et Semper) are not measured.
  - Sequence rules. A source section number counts when it advances the count by 1 to 3, or jumps further and the next number follows on, so list items and restarted note numbers are not read as sections. A built § number is `out_of_range` when it is above the source's last section or appears nowhere in the source body as a leading number (invented inside a gap). A leading number needs no space after its full stop ("131.Later" in Dilexit Nos), but "1.5" is not one. A canon heading inside another canon's passage is "Can. N" after a line break, a full stop or the "n" amendment marker; it is reported as `duplicated`. A built Summa article is the group of passages sharing a `chapter_key` (its objections, answer, replies and split pieces). Each group is matched by its reference to the source article whose question number and title it holds, the longest such title winning, with the editor's `[*…]` notes removed from the source title; questions that hold their text in the `div3` (FP_Q71, FP_Q72, the Prologue `FS.i.i`) count as articles. A source article no group matches is `missing`, one matched by two groups is `duplicated`, and a group matching no source article is `out_of_range`. Repeated text inside one group is left to 0.1b's duplicate-text rule. Per Carter on 5 Oct 2026, because units differ in size by two orders of magnitude, a ThML div counts as represented when at least half of its own measured characters reach a passage, not when any one sentence does: one shared Scripture quotation made the 66,000-character "Who is the Rich Man" look present.
  - Check ids. Canons, Catechism paragraphs, Summa articles and ThML divs are one check per unit (`sequence.thml_chapters.missing:<collection>/<file>#<div id>`); Bible verses one per chapter (`sequence.bible_verses.missing:DAG/13`); § numbers one per source file and kind; sentinels `sentinel.<name>`; coverage entries `coverage.<collection>.<file>`. A coverage entry is listed for every file under 95% (`report.COVERAGE_ENTRY_BELOW`) and is a strict xfail like the others: once the file reaches 95% the suite fails until the entry is deleted, and a file under 95% with no entry fails too. An entry whose check id groups several units (a source file's § numbers, a Bible chapter's verses) lists them in `"units"`, and a unit outside the list fails the suite, so a known defect cannot hide a new one in the same file.
  - Baseline. The baseline is `checks/baselines/coverage.json`, not `coverage-master-2026-09.json`, because it moves: besides the regression test, the suite fails when a file's coverage rises more than 0.5 points above the baseline, its measured body changes by more than 1%, or a file is new. A PR that fixes a file therefore rewrites the baseline (`python3 -m checks.report --write-baseline`) in the same PR, so a later PR cannot lose the fix again. A run of one collection replaces only that collection's rows and keeps the rest. `measured_on` names the branch and commit per collection.
  - Editorial divs. Per Carter on 5 Oct 2026 (Decision log "Editorial divs in the coverage check (0.1a)"), `checks/editorial_divs.json` lists 112 ThML divs written by editors or translators. They are measured as apparatus, not body, and `thml_chapters` reports one in `out_of_range` if any of its sentences (or a nested div's) reaches a passage, unless the file holds the same sentence outside the editorial divs: an editor quoting the Creed, or repeating a translator's note the adapter prints inline, which coverage measures as note leakage and 1.10b strips. On master no editorial div reaches a passage by its own text. Author text the adapters drop as front matter (Augustine's and Anselm's own prefaces) is not on the list.
  - CLI. `python3 -m checks.report` sets placeholder store credentials when none are in the environment, because `config.settings` requires them at import and the report never connects. `--write-baseline [<file>]` writes a run's numbers as the baseline. The report lists the Summa articles with the lowest share of characters kept.
  - Measured on master `c987d48` plus this PR: 217 known defects (1.1 37, 1.10b 11, 1.2b 2, 1.2c 6, 1.2d 2, 1.2e 3, 1.3a 42, 1.4a 25, 1.5a 14, 1.7 5, 1.8b 4, 1.8c 19, 1.8e 31, 1.9 16). Summa 97.84% of body characters; the rest is mostly the question prologues 1.7 adds. `--collection all` takes about 58 s, and so do the source tests. Vatican II passages hold 443,397 characters and cover 40.5% of 918,286 body characters (35.8% counting 119,913 note characters); Gaudium et Spes 74,319 passage characters, covering 29.6% of 195,616 body characters, 27.1% with its 18,049 note characters; Bible 244 verses missing; canons 112, 238, 266, 689 and 1330 missing and 112, 238, 689, 1308 and 1310 glued; Summa FP_Q71, FP_Q72 and FS.i.i missing.

---

### 0.1b. Health rules

- **Type:** PR
- **Depends on:** 0.4, 0.1a (the H2 rule starts as a `known_defects.json` entry, and that file comes from 0.1a)
- **Goal:** Reject passages that are never useful (blank text, pure page-number or punctuation debris, broken positions) before they can be published, and report the softer problems (footer leakage, note leakage, short fragments, duplicated text, repeated citations) with counts per collection so P1 PRs can show them falling. The live corpus has 21 blank Summa passages with Qdrant points; a rule would have refused them.
- **Current state:**
  - Live, 29 Sep, per collection: blank passages 21 (all Summa); passages under 20 characters apostolic-exhortations 10, bible 2, councils 1, encyclicals 17, medieval 1, papal-documents 1, summa 24 (21 of them blank).
  - Prototype rules run on live with SQL: pure digits, Roman numerals and punctuation (regex `^[0-9IVXLCivxlc .,;:()\[\]"“”'’-]*$` after trim) apostolic-exhortations 3, encyclicals 4, medieval 1, papal-documents 1, summa 23 (includes blanks). Canon-law footer markers (`(n: indicates`, `[Earlier version]`, `[Original version`, 5 or more underscores) canon-law 12, church-fathers 4, apostolic-exhortations 1, encyclicals 1. Passages starting "Cf." or "See " councils 333, encyclicals 11, church-fathers 8, bible 4, apostolic-exhortations 2. Example footer leak verified in canon 123 and canon 694 text tails.
  - Same prototype on the master build (29 Sep): blank 0 in every collection, debris 1 (summa), under 20 characters apostolic-exhortations 7 and encyclicals 11, footer markers the same as live (12, 4, 1, 1), 0 duplicate anchors, 0 documents with non-contiguous positions. So the 21 blanks exist only in the stale live publication.
  - Anchors are already unique per document in live (unique index `chunks_document_anchor_uniq`, 26 MB). Anselm's Cur Deus Homo has 27 of 71 anchors carrying the `--N` disambiguation suffix from `thml_doc.py:64-68`; this is the "27 duplicate anchors" in the plan, and 2.1 removes the cause.
  - `publication.py:213-222` `_validate_documents` checks only that each document belongs to the requested collection.
- **Changes:**
  - Add `datapipeline/health.py`:
    - `@dataclass(frozen=True) class Violation: rule: str; severity: Literal["block", "report"]; collection: str; document_id: str; anchor: str | None; detail: str`.
    - `def check_documents(collection: str, documents: list[Document]) -> list[Violation]`.
    - Block rules (refuse publication):
      - `H1_blank`: content empty after `strip()`.
      - `H2_debris`: stripped content matches the debris regex above.
      - `H3_positions`: positions not exactly `0..n-1` in order.
      - `H4_anchor_unique`: duplicate anchor inside a document.
      - `H5_anchor_nonempty`: empty anchor, chapter_key, or chapter_label.
    - Report rules (counted, never block):
      - `R1_short`: under 20 characters with at least one letter. Allowed without report for `bible` and `canon-law`, where short verses and canons are real.
      - `R2_footer`: the canon-law footer markers above, plus a per-collection list in `health_patterns.json`.
      - `R3_note_start`: starts with `Cf.`, `See `, `Ibid`, or a bare citation such as `Eph. 1:10).`.
      - `R4_dup_text`: two passages in one document with identical normalized text of 100 or more characters.
      - `R5_repeated_reference`: more than one passage in a document with the same `reference` string (the plan counts Bible 495, apostolic exhortations 412, encyclicals 411, medieval 240, Catechism 98, papal documents 91, councils 1,282, Fathers 5,941, and every Summa passage).
      - `R6_joined_paragraphs`: a lowercase letter, sentence punctuation, then an uppercase letter with no space (the Vita Consecrata defect, 188 joins in 86 passages per the plan).
      - `R7_non_english`: share of the 50 most common English function words below 5% in a passage of 200 or more characters, to flag Latin and Italian (plan lists Clement Stromata III 33, Instructor II.10 4, Lactantius 5, Ubi Lutetiam 17).
      - `R8_anchor_suffix`: anchor contains `--` (label-derived disambiguation).
    - `datapipeline/health_patterns.json` (tracked) holds the per-collection regexes and allowlists, so P1 PRs change data, not code.
  - Wire block rules into `CollectionPublicationRunner._validate_documents` (`publication.py:213`), raising `ValueError("REFUSING: ...")` listing the first 10 violations, before any store is acquired. Because the master build has 0 blanks, 0 anchor duplicates and 0 position errors, only `H2_debris` (1 Summa passage) would trip. Handle that one explicitly: `H2` blocks from this PR, and that one passage is accepted through a `known_defects.json` entry with `fixed_by` 1.7, which deletes the entry when it removes the passage (decided by Carter on 5 Oct 2026).
  - Add `python3 -m checks.health --collection all|<name> [--out <dir>]`, which builds documents and writes `health.json` plus a `health.md` table (rule by collection, counts, first 5 anchors each). Also `--from-snapshot <path>` to run the same rules on the live snapshot exported in 0.1c, so reports can show live against build.
- **Acceptance checks:**
  - `tests/test_health.py` in CI with synthetic documents: one test per rule id asserting it fires on a crafted bad passage and stays silent on a crafted good one, `test_bible_and_canon_short_passages_are_allowed`, and `test_block_rule_refuses_before_store_acquisition` using the runner with fakes.
  - Locally, `python3 -m checks.health --collection all` on master prints the counts listed under Current state (blank 0, debris 1, footer 12/4/1/1, short 7/11); the PR description pastes them next to the live counts.
  - `python3 run_collection.py --collection summa --dry-run` still succeeds on master (the Summa "." is a known defect until 1.7).
- **Production safety:** Adds refusals to a runner that is already locked by 0.4; no store is touched; no API or web change.
- **Needs Carter:** Nothing left. Whether H2 blocks from this PR was answered on 5 Oct 2026: it does (`NEEDS-CARTER.md`, B, 0.1b).
- **Out of scope:** Fixing the violations. Removing the 21 live blank rows (that happens at the P4 republish). Language detection beyond the function-word heuristic.
- **As built (5 Oct 2026):** facts recorded by the implementing PR.
  - Counts. On master `8336e61` (54,778 passages) `python3 -m checks.health --collection all` reproduces Current state: blank 0, debris 1 (Summa), footer markers canon-law 12, church-fathers 4, apostolic-exhortations 1, encyclicals 1, short apostolic-exhortations 7 and encyclicals 11, no position or anchor errors. Three of the four church-fathers footer hits are underscore rules followed by an editor's note (all Lactantius); the fourth is the title-page rule before Book I of Augustine's On the Trinity. Report rules on the build: R3 councils 337, encyclicals 10, church-fathers 4, apostolic-exhortations 1, papal-documents 1; R4 councils 2, Summa 2; R6 apostolic-exhortations 91, medieval 14, church-fathers 10, encyclicals 7, canon-law 5; R7 church-fathers 42, encyclicals 17, canon-law 1, councils 1. The runs take about 24 s.
  - H2. The rule's severity is `block` from this PR on (Carter, 5 Oct 2026; the spec had read both "starts as a report rule" and "with a `known_defects.json` entry"). Its one hit on master, the lone "." piece at Summa III q.16 a.3, is a `known_defects.json` entry (`fixed_by` 1.7), and the publish gate accepts a block violation only when its check id is listed there. The strict xfail in `tests/source_checks/test_health_sources.py` fails once 1.7 removes the passage, until the entry is deleted, and from then on H2 refuses that passage like any other. Debris anywhere else blocks at once. The Summa dry run therefore passes because of that entry, not because H2 is report-only.
  - Check ids. One per passage, `health.<rule>:<collection>/<document_id>#<anchor>`, with `@<position>` added when the anchor is empty or shared, or per document for H3 (`health.H3_positions:<collection>/<document_id>`). `pipeline.py` runs the block rules too, on every collection a `reader`, `embed` or full `enrich` run parses, before its first stage and in its dry run. Because ids are keyed by anchor, an item that changes a listed passage's anchor (2.1 changes most Summa anchors) must re-key its `health.` entry, or the strict xfail reports it fixed and the gate refuses the passage. Only block rules can have `known_defects.json` entries. `checks.report` counts the block violations among its failing checks, and `report.check_scope` reads the collection from the id.
  - R1 skips text with no letter, which H2 covers when it is digits, numerals or punctuation, and blank text (H1's). Text made only of other symbols ("* * *", "…") is caught by neither; the build has none.
  - R3. "Cf." and "cf." both count, as do a note number before them ("49. Cf.") and an opening "AAS" citation. "See " counts only before "the note", "also", "above", "below" or a possessive name ("See Cave's"), because every other "See " opening in the build is the author's own imperative ("See how great a love…", "See Jesus as happy…"). The Bible is skipped. The bare-citation patterns are a book abbreviation, chapter and verse, then a closing parenthesis ("Lk 1: 31-37).") or an endnote list ("John 2:22; 12:16", "Jn. 1:14. 2. Jn. 3:16."). The patterns are in `health_patterns.json`.
  - R5 counts every passage in a group of two or more that share a `reference`. On the build: church-fathers 5,941 and Summa 26,792 (every passage), as the plan says; Bible 555, apostolic-exhortations 463, encyclicals 491, medieval 260, Catechism 118, papal-documents 105, councils 1,311. The plan's other figures were taken on live.
  - R6 ignores a full stop after a single letter or after an abbreviation listed in `health_patterns.json` ("Ph.D.", "cf.Rom", "St.Gregory"). Vita Consecrata has 188 joins in 91 passages on the build; the plan says 188 in 86.
  - R7 uses a 50-word list without "a", "i" and "in", which Italian and Latin share with English. With them, Ubi Lutetiam and Stromata III passages scored just above 5%. It skips passages R3 reports and citation lists (15% or more of tokens are numbers). On the build it finds exactly the plan's examples: Clement's Stromata III 33, Instructor II 4, Lactantius 5, Ubi Lutetiam 17. It also finds canon 111's Latin and one Latin bibliography passage in Constantinople IV. English passages with a Latin tail (canons 695 and 700, Instructor II.10) score above 5%, so R7 at 0 does not mean no Latin is left.
  - R8. The build has 625 anchors with a `--` suffix, not only Cur Deus Homo's: medieval 28, all in Cur Deus Homo (28 of its 74 passages), church-fathers 597 (Moral Treatises of St. Augustin 310, Doctrinal Treatises 122, The Banquet of the Ten Virgins 80, Hippolytus 71, Dubious or Spurious Writings 11, three others 1 each). 2.1's check that R8 reports 0 covers all of them.
  - CLI. `--from-snapshot` takes a 0.1c snapshot directory or its `passages.jsonl.gz` and puts each document's passages in position order before H3 runs. `health.json` keeps build and snapshot results apart and holds numbers, IDs, anchors and rule details, no passage text. A run replaces only the source and collections it covered, so a build run and a snapshot run into one `--out` give `health.md` a build column and a live column. The command exits 1 when the build has a block violation not in `known_defects.json`. `--out` defaults to `datapipeline/releases/local/health-<timestamp>/`.

---

### 0.1c. Release report with remap-based ID diff

- **Type:** PR
- **Depends on:** 0.4, 0.1a, 0.1b (reuses both outputs)
- **Goal:** One command that tells a reviewer exactly what a build would change compared with what users see today. It maps every live passage to one outcome from a fixed vocabulary, counts the saved user rows that each outcome affects, and summarizes coverage and health. It enforces D1: a build fails when a passage ID that survives names noticeably different text and no redirect says so, or when a live anchor string comes to name a different unit. It produces the chapter remap that 4.1a uses to move `reading_progress` rows and 2.4a uses for `?chapter=` redirects. Every P1 PR attaches this report. The same remap is what 4.1a later uses to move bookmarks and history, and what 2.2w's release report runs on staging against live, so building it now tests it months before cutover.
- **Current state:**
  - Passage ID is `uuid5(DOCUMENT_NS, f"{document_id}#{anchor}")` (`datapipeline/identity.py:40-43`); document ID is `uuid5` of slugified work-key parts (`identity.py:24-27`), for example `document_id(collection, author, title)` for ThML works (`ingest/thml_doc.py:89`) and `document_id("bible", translation, name)` for Bible books (`ingest/bible.py:557`). Any relabel of author, title, or anchor text changes IDs.
  - No remap exists. `reconcile.py` compares Qdrant payloads with Postgres for existing IDs only.
  - Live versus master build, 29 Sep: live 54,568 passages, build 54,778 (the audit's total row first said 54,776; see 0.1a). The audit measured 373 build IDs missing from live, 163 live IDs not in the build, and 2,439 content differences under equal IDs. All 421 live document IDs are reproduced exactly by the master build (md5 of the sorted ID list `851d07063f85e4c612be1b2d44b695fb` on both sides).
  - User references, 29 Sep: `retrievals` 3,029 rows over 1,605 distinct passages; `bookmarks` 25 rows, 25 passages; `guest_trial_retrievals` 274 rows, 241 passages; `retrieval_labels` 3 rows; together 1,685 distinct passages. `reading_progress` 25 rows keyed by `document_id`, `chapter_key`, `anchor`. `product_feedback` has 0 rows with a chunk or document reference.
  - Reader deep links carry `?anchor=` or `?chapter=` (`apps/web/src/components/search/ChunkCard.tsx:185-186`, `BookmarkCard.tsx:82`), so anchor and chapter-key changes break shared URLs unless redirected (2.4a).
- **Changes:**
  - `datapipeline/scripts/export_live_snapshot.py`. Read-only export, run by Carter or with his approval, opening one connection with `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`. Writes to `datapipeline/releases/snapshots/<YYYY-MM-DD>/` (gitignored):
    - `passages.jsonl.gz`: one row per chunk with `id, document_id, collection, title, author, anchor, chapter_key, chapter_label, reference, position, content`.
    - `documents.jsonl`: `id, collection, title, author, year, translation, chunk_count, metadata`.
    - `references.json`: per passage ID, counts from `retrievals`, `bookmarks`, `guest_trial_retrievals`, `retrieval_labels`; per document ID, the count of `reading_progress` rows and the distinct `(chapter_key, anchor)` pairs they hold. Counts only, no `user_id`, no query text.
    - `snapshot.json`: timestamp, row counts per table, sha256 of each file.
    - Also write a tracked `datapipeline/releases/snapshots.json` index with date, row counts and sha256s (no content), so a report can name the snapshot it used and a reviewer can confirm Carter's local copy matches.
  - `datapipeline/release/remap.py`:
    - `def remap(old: list[OldPassage], new: list[Document], registry: Registry | None = None) -> RemapResult`.
    - The outcome vocabulary is defined here and nowhere else (D5). 4.1a's user-data remap uses the same words. Redirect kinds (2.1's `redirects.json`, 2.2a's `corpus_redirects`) are the four middle words only, `moved`, `split`, `merged` and `renumbered`; `same` and `removed` are release-report outcomes and never redirect kinds (D11). The six outcomes:
      1. `same`: the old passage ID is in the build. Once 2.1 lands, IDs come from its frozen passage registry, so a unit keeps its ID even when its anchor string changes (D1). Its text may have been corrected in place, within the stability check below.
      2. `moved`: the old passage ID is gone and its text is in exactly one new passage with a different ID, which holds no other old passage's text. After 2.1 this is rare, because anchor changes alone keep the ID, and so does a passage moved to another document (D11; 2.2w updates its `document_id` in place), which is therefore `same`.
      3. `split`: the old text is spread over 2 or more new passages. The primary successor is the one holding the old passage's first shingle.
      4. `merged`: the old text is inside one new passage that also holds text from at least one other old passage.
      5. `renumbered`: the build declares a redirect of kind `renumbered` for the old ID, because the unit's numbering changed and its passages were regrouped (Joel and Malachi in 1.4b). The redirect names the successor.
      6. `removed`: no successor. Every `removed` passage must be explained by an entry in the removal registry (2.1, D4), or the report fails.
    - Matching evidence, per document, recorded in a `method` field next to the outcome: `id` (same passage ID), `redirect` (a redirect the build declares, see below), `text_hash` (identical normalized content), `containment` (old text at least 90% contained in one new passage, measured on 8-word shingles), `union` (old text at least 90% covered by 2 or more consecutive new passages), `jaccard` (best 8-word-shingle Jaccard of at least 0.5 against one new passage). Each old passage takes exactly one outcome. Declared redirects win over computed matches. Once 2.1 lands, every outcome other than `same` must be backed by a redirect row or a removal entry, so computed matches become the evidence a reviewer checks the declared rows against.
    - Stability check (D1). For every `same` outcome, compare the old text with the new text under the same passage ID. Similarity is the larger of two containments, old shingles found in the new text and new shingles found in the old text, so a unit that only gained restored prose or only lost notes scores near 1. Where either side is under 16 words, they are compared word by word instead: the best `difflib.SequenceMatcher` ratio between the shorter text's words and any window of the longer text with as many words (decided by Carter on 5 Oct 2026; a character-level ratio let 15% of different short Summa parts pass). Pieces of one unit (`base/p1` to `base/pN`) are compared as one unit, by joining all pieces on each side, because a piece is a display slice of one unit. The threshold is `ANCHOR_STABILITY_THRESHOLD = 0.5`, printed in every report. A `same` passage below it fails the build unless the new passage's metadata declares `text_replaced` (a reason string such as "Percival translation replaces Tanner" or "2023 amendment", set by the adapter for the same numbered unit in a new translation or a new legal text). Every declared replacement is listed in the report so a reviewer sees each one. When the ID would now name a different unit, the declaration is not allowed; the fix gives that unit a new anchor and a new ID, and the old ID gets a redirect (D1).
    - Anchor-string check. A live anchor string may only name the unit that holds it today. The report fails when a build passage carries an anchor that was live for a different passage ID, or an anchor the removal registry lists as retired. This keeps old `?anchor=` links from landing on different text.
    - Redirects the build declares come from `datapipeline/registry/redirects.json`, and removals from `datapipeline/registry/removals.json`. Both files belong to 2.1; until 2.1 merges, a missing file counts as empty. Each redirect row is `{document_id, old_passage_id, old_anchor, new_passage_id, new_anchor, kind, reason, added_by}` with `kind` one of `moved`, `split`, `merged`, `renumbered`.
    - Successor document: same document ID; else, once 2.1 lands, the registry's `supersedes` mapping; else none.
    - `RemapResult` rows: `old_id, outcome, method, new_ids (primary first), score, old_document_id, new_document_id, old_anchor, new_anchor, old_chapter_key, new_chapter_key`. Serialize as `remap.jsonl`, plus `chapter_remap.jsonl`, one row per old `(document_id, chapter_key)` with the new `document_id` and `chapter_key` chosen by majority of its passages' primary successors (the document differs only when passages moved to another document, as in 1.8b's split), the share of passages that agree, and the old anchors in that chapter that `reading_progress` rows hold. 4.1a rewrites `reading_progress` (`document_id`, `chapter_key` and `anchor`) from this file and `remap.jsonl`; 2.2w turns every row whose chapter changed into a chapter redirect (2.2a) for old `?chapter=` links.
    - Pure functions over in-memory data; no database access.
  - `datapipeline/release/report.py`, CLI: `python3 -m release.report --snapshot releases/snapshots/<date> --collection all|<name> [--out <dir>]`. Builds the collection with `SOURCE_ADAPTERS`, runs remap, 0.1b health and, if present, 0.1a checks, and writes to `<out>` (default `datapipeline/releases/local/report-<collection>-<timestamp>/`, gitignored) the files `remap.jsonl`, `chapter_remap.jsonl`, `report.json`, `report.md`. `report.md` sections:
    - Totals per collection: documents, passages, characters, live against build.
    - Outcomes per collection: `same`, `moved`, `split`, `merged`, `renumbered`, `removed`, and `new` (build passages that are no old passage's successor), with a count per matching method.
    - Checks that fail the report (non-zero exit): stability failures, `removed` passages the removal registry does not explain, outcomes other than `same` with no redirect row (once 2.1 lands), and anchor-string reuse. Each is listed with document, passage ID, anchor and score.
    - Declared text replacements (`text_replaced`), listed by anchor with their reason.
    - User impact: for `removed` and for every outcome whose primary ID differs from the old ID, the sum of `retrievals`, `bookmarks`, `guest_trial_retrievals`, `retrieval_labels` rows, and the `reading_progress` rows whose anchor or chapter key changes.
    - Up to 30 sample rows per non-trivial outcome (IDs, references, anchors; content excerpts only in the local file, never pasted into a public PR).
    - Health and coverage summaries.
  - `report.md` is written to be pasted as the "release report" block of the PR template with excerpts removed.
- **Acceptance checks:**
  - `tests/test_remap.py` in CI with synthetic passages: one test per outcome (`same`, `moved`, `split`, `merged`, `renumbered`, `removed`), `test_outcome_vocabulary_is_exactly_six_words`, `test_each_old_passage_has_exactly_one_outcome`, `test_split_primary_is_first_piece`, `test_new_passages_are_reported`, `test_cross_document_match_is_not_attempted_without_registry`, `test_declared_redirect_wins_over_computed_match`, and `test_remap_is_deterministic` (same input, byte-identical `remap.jsonl`).
  - Stability tests in the same file: `test_restored_prose_under_same_id_passes`, `test_stripped_notes_under_same_id_passes`, `test_different_text_under_same_id_fails_without_redirect`, `test_declared_text_replacement_passes_and_is_listed`, `test_pieces_compared_as_one_unit`, `test_anchor_string_change_with_frozen_id_is_same`, `test_live_anchor_reused_for_other_unit_fails`, `test_reused_retired_anchor_fails`, `test_unexplained_removal_fails`.
  - `test_chapter_remap_majority_and_reading_progress_anchors`: on synthetic data, each old chapter maps to the majority successor chapter, and the file lists the anchors `reading_progress` holds there.
  - `tests/test_release_report.py` in CI: user-impact sums on a synthetic `references.json`; the Markdown contains no passage content when `--public` (default) is set.
  - Locally, the report for all collections from master against a fresh snapshot reproduces the audit: live 54,568, build 54,778, `same` about 54,405 (54,568 minus 163), and user impact for the 163 unmatched passages equal to the 12 referenced passages, 19 `retrievals` rows and 2 `guest_trial_retrievals` rows measured on 29 Sep (re-read at run time). The PR description pastes the public summary.
  - Master against live will fail the new checks, because the live publication is stale: expect unexplained removals (up to 163) and some anchor-stability failures among the 2,439 content differences under equal IDs. The PR lists them and records each as a `known_defects.json` entry, to be cleared by a redirect or a removal-registry entry before P4. Later PRs fail only on new ones.
  - `export_live_snapshot.py` has a test that the SQL it issues is SELECT only, and that the session is set read only before the first query.
- **Production safety:** The export is a read-only transaction on live Supabase; everything else is local. Nothing is published (the lock stands). No API or web change.
- **Needs Carter:** Run, or approve running, `export_live_snapshot.py` against the production database (read only; it copies corpus text and anonymous reference counts to his Mac). The snapshot is refreshed before P4 and whenever a report needs current reference counts. Answered 5 Oct 2026: approved for this PR's run, exported on 6 Oct 2026 (UTC); later runs are asked for again. Also answered 5 Oct 2026: short passages are compared by words (Decision log "Short passages in the drift check (0.1c)"), and 2.1 clears the 408 shifted Summa IDs (Decision log "Summa passage IDs shifted in the live publication (0.1c)"; how is a Needs Carter entry on 2.1).
- **Out of scope:** Applying the remap to user tables and the merge policy for unique constraints (4.1a). The redirect and tombstone tables and their display (2.2a, 2.4a); this item only reads the redirect and removal files that 2.1 owns. Qdrant.
- **As built (5 Oct 2026):** facts recorded by the implementing PR.
  - Export. `scripts/export_live_snapshot.py` sets the session read only, then reads everything in one `READ ONLY`, `REPEATABLE READ` transaction, so the passages and the counts describe one moment, and refuses unless `current_setting('transaction_read_only')` is `on`. After its last query it resets the session's read-only default, because the `.env` connection goes through Supabase's session pooler (port 5432), which may hand the server connection to its next client. The first export ran before that reset existed; the API's Railway logs show no read-only errors since, but also no database writes to show one, so a leak is unconfirmed either way. `--date` must be `YYYY-MM-DD`, and a bad or existing date is refused before connecting. Its tests check the statement list against a fake connection (CI) and run it against a throwaway local PostgreSQL, where a `DELETE` on the same connection afterwards fails as read only. `passages.jsonl.gz` also carries `unit_label` (below); `checks.health.load_snapshot` reads it and keeps each passage ID as `metadata["passage_id"]`. `references.json` lists only passages with a saved row, as counts per table, and per document the `reading_progress` rows grouped as `{chapter_key, anchor, rows}`. The gzip header carries no time, so equal content gives an equal hash. A snapshot directory is never overwritten. Only the default root writes the tracked index; an export to another `--root` keeps its own `snapshots.json` inside it. The first snapshot is `2026-10-06` (UTC date; 5 Oct evening on Carter's Mac): chunks 54,568, documents 421, retrievals 3,491, bookmarks 25, guest_trial_retrievals 260, retrieval_labels 3, reading_progress 29.
  - Matching. Texts are compared as their letters and digits after NFKC and lowercasing, so `text_hash` is equality of those words. An old passage under 8 words is `containment` when its word sequence occurs in one new passage. `union` is measured on the joined text of the run, so shingles that cross a cut count; measured piece by piece, a 60-word passage split in two scores 0.87. "Holds no other old passage's text" is judged by successors: a new passage that is the primary successor of an old passage that keeps its ID and at least the stability threshold of its text there, or a successor (any piece of a split included) of two or more old passages, makes each single-passage computed match into it `merged`. In a `union` run, a piece under 8 words, which has no shingles, bridges the passages on either side. Removal-registry entries are applied before computed matching, as redirects are; an entry explains a passage by its `passage_id`, and by `(document_id, anchor)` only when it names no ID. `removed` rows have `method` null and name their entry in an added `removal` field, and every row carries its `collection`, so a run of one collection can replace its own rows in an existing `--out`.
  - Units. For the stability check, consecutive passages are pieces of one unit when they share `chapter_key`, `reference` and `unit_label`, and their anchors match once a trailing piece number (`/pN`, `-pN`, the Bible's `-N`, the Summa's `/N`) is removed. Anchor suffixes alone cannot say this: the Summa numbers every part of an article in one running sequence (`…/0`, `…/1`), and `-N` is also the end of slugs such as `chapter-2`. A bare trailing `/N` counts as a piece number only when the passage has a `unit_label`, as Summa parts do; unlabelled council paragraphs sharing a reference (`council-of-nicaea/sec-4/3`, `/4`) are separate units, as 347 council passages in 82 groups would otherwise be joined. Without `unit_label` a whole Summa article would be one unit (3,120 units on the build instead of 26,609), and a shifted part would go unseen. The three groups left that are not display pieces are a section number a source prints twice (Menti Nostrae §126, Africae Munus §1, Second Lyons §20). A unit is checked when any of its passages keeps its ID; the build side is every build unit holding one of those IDs. A failure is keyed by the first passage of the live unit that keeps its ID.
  - Short texts compare words, as decided by Carter. Known limit: a build passage of a few words scores by its best window inside a long old text, so two Summa "On the contrary" fragments of 6 words score 0.5 and 0.6 against the long "I answer that" whose ID they hold. Both lie in articles that fail on other parts.
  - Check ids are `release.<check>:<collection>/<passage id>`, with checks `stability`, `removed`, `unbacked`, `anchor_reuse`, `bad_redirect` (a redirect whose kind is not one of the four, whose target is not built, or whose old ID is still built), `duplicate_id` (two build passages with one ID) and `bad_removal` (a removal entry naming a passage or document the build still emits). A split redirect's primary successor is its first target in build order. They are keyed by passage ID, never by anchor, so 2.1's re-anchoring leaves them valid. `checks.report.check_scope` reads their collection, and 0.1a judges only the `coverage.`, `sequence.`, `sentinel.` and `health.` ids it computes. The report exits 1 on a failure not in `known_defects.json` and on a listed `release.` entry that now passes, for the collections it ran. Outcomes other than `same` need a redirect row from the moment `registry/redirects.json` exists, that is once 2.1 lands.
  - User impact adds a row `same, text below threshold`: saved rows on passages that keep their ID but would show different text.
  - CLI. `--public` (default) or `--no-public`. Before anything else the report checks each snapshot file against `snapshot.json` and `snapshot.json` against the tracked `releases/snapshots.json`, and on a mismatch writes nothing and exits 1. It runs 0.1a when the vendored sources are present (`checks.report.run` now accepts a prebuilt build) and writes `health.json` and `health.md` with a build and a live column. `--collection all` takes about 92 s. Each collection section records the snapshot and build it was measured on, and `report.md` names any kept from an earlier run against another. A passage moved to another collection is found only when both are in the run.
  - Measured on master `81861f2` against the 6 Oct snapshot. Live 54,568 passages, build 54,778. `same` 54,405, `split` 134, `merged` 7 (Bible 4, Catechism 2, encyclicals 1), `moved` 22 (Summa 21, councils 1: text landing on a shifted ID, whose own passage keeps none of its text there), `renumbered` 0, `removed` 0, `new` 105. Every split is a live passage of 3,491 characters or more that the 22 Aug splitter now prints as two pieces, covered in full. The 163 live IDs the build lacks all have computed successors, so no removal is unexplained before 2.1. Text differs under 2,439 equal IDs, the audit's figure collection by collection. Outside the Summa, all but one of them keep 95% or more of their text. Stability failures: 409. One is First Lateran `sec-0/1`, which live is the editor's introduction and in the build canon 1 (0.00 kept). The other 408 are Summa, in 81 articles. Live kept a blank passage in 21 of them and printed "On the contrary" and "I answer that" as one passage in 60 (the 22 Aug dialectical-marker fix splits them), so each later part's ID now names a neighbouring part. They are 409 `known_defects.json` entries with `fixed_by` 2.1: the 408 by Carter's decision of 5 Oct 2026, and First Lateran's for its ID pairing only, an open Needs Carter point on 2.1 (its introduction also needs a removal entry from a council item). User impact: 12 passages, 21 `retrievals` rows and 2 `guest_trial_retrievals` rows on changed IDs, against 12, 19 and 2 on 29 Sep. `retrievals` grew from 3,029 to 3,491 rows meanwhile, and the snapshot holds no timestamps to show when the two were added. Plus 1 `retrievals` row on the 409 shifted passages (none on First Lateran's); no bookmarks, labels or `reading_progress` rows are touched. Health on live matches 0.1b's Current state: blank 21 (Summa), debris apostolic-exhortations 3, encyclicals 4, medieval 1, papal-documents 1 and Summa 2 (one of them the known "." at the same anchor), footer markers 12, 4, 1, 1.

---

### 0.2. Source hashes, manifests, and rights inventory

- **Type:** PR
- **Depends on:** 0.0
- **Goal:** Every vendored file that feeds a publication is pinned by a hash in a tracked file, so any later build can prove it used the same inputs, and every work carries a tracked record of its edition, translator and public-domain basis. Today the manifests are gitignored and four of seven collections have no hashes at all.
- **Current state:**
  - `.gitignore:29` ignores `datapipeline/sources/`, which is where the manifests live, so no manifest is in git.
  - `scripts/vendor_sources.py` writes `manifest.json` (or `pages.json` for canon-law) with `sha256` and `bytes` per entry (`_stamp`, lines 576-589) and verifies with `--verify` (`verify_manifest`, lines 600-626). `VENDORS` (lines 629-637) covers only 7 collections; bible, catechism and summa have no vendor function and no manifest.
  - `python3 scripts/vendor_sources.py --collection all --verify` on 29 Sep:
    - church-fathers ok (10 of 10 hashed), medieval ok (4 of 4), canon-law ok (45 of 45 in `pages.json`).
    - encyclicals: 131 entries, 0 hashed.
    - apostolic-exhortations: 30 entries, 0 hashed, plus `amoris-laetitia.html` and `a-new-hope-for-lebanon.html` on disk but absent from the manifest.
    - papal-documents: 14 entries, 0 hashed, plus `ubicumque-et-semper.html` unmanifested.
    - councils: 36 entries, 0 hashed.
    - 211 "no recorded hash" messages in total; the command exits 1.
  - Amoris Laetitia is not in the live database (0 documents with that title), not in any manifest, and not covered by the Decision log row that schedules the other two unmanifested files for PR 5.4.
  - `sources/roman-curia/` (61 files) exists on disk from the parked `feat/roman-curia-collection` branch; it is not a registered collection on master.
  - Bible inputs are `sources/bible/eng-web-c_usfm/` (77 files including `copr.htm`, `keys.asc`, `signature.txt.asc`) and `PericopeGroupedKJVVerses.json`. Catechism is `sources/catechism/ccc.json`. Summa is `sources/summa/summa.xml`. Their provenance is described only in prose in `datapipeline/SOURCES.md`.
  - The rights review is private and outside git (plan, Decision log "Rights review"). The plan requires a renewal search record per work for "public domain by non-renewal" (Decision log "Public domain by non-renewal") and a rights status per planned work before ingestion (Decision log "Editions for planned sources").
- **Changes:**
  - Add a tracked `datapipeline/source_lock.json`, one entry per file that any registered adapter reads:
    ```json
    {"collection": "encyclicals", "path": "encyclicals/rerum-novarum.html",
     "sha256": "...", "bytes": 123456, "url": "https://...",
     "acquired": "unknown-before-2026-09-29", "hashed_on": "2026-09-29",
     "role": "adapter-input"}
    ```
    `role` is `adapter-input`, `adapter-auxiliary` (for example `PericopeGroupedKJVVerses.json`, `copr.htm`), or `vendored-unregistered` (the three unmanifested files and anything under `sources/roman-curia/`). `acquired` is the known fetch date, or `unknown-before-<date>` for files hashed from the on-disk copy. Sorted by `collection`, then `path`.
  - Add `datapipeline/scripts/source_lock.py`:
    - `--write`: hash every file under `sources/<registered collection>/` (plus `role: vendored-unregistered` rows for unregistered files and directories) and rewrite `source_lock.json`, preserving `url` and `acquired` from existing entries and from each collection's `manifest.json` where present.
    - `--verify`: re-hash, exit 1 on any missing file, changed hash, or unlocked file; print `ok` per collection otherwise. This replaces `vendor_sources.py --verify` in the PR template.
    - `--collection <name>` limits either mode.
  - `vendor_sources.py`: after writing a manifest, call the lock writer for that collection so a re-vendor updates the tracked lock in the same step; keep `--verify` working for compatibility.
  - Add a tracked `datapipeline/rights_inventory.json`, one entry per work (keyed by the 2.1 registry `work_id` once it exists; until then by `collection` plus source path plus title plus author, since title alone is not unique: ANF volume 1 holds both Polycarp's and Ignatius's "Epistle to the Philippians"). A work built from many files (the Bible books, the Code of Canon Law) takes its directory as source path:
    ```json
    {"work": "...", "author": "...", "collection": "medieval", "source_path": "medieval/imitation-of-christ.xml",
     "edition": "Bruce, Milwaukee, 1940", "translator": "...", "first_published": 1940,
     "source_url": "https://ccel.org/...", "status": "pd-us-non-renewal", "rights_holder": null,
     "renewal_search": {"date": "2026-..", "where": "...", "query": "...", "result": "no renewal found"},
     "credit_line": "Sourced via CCEL.org", "checked_by": "Carter", "checked_on": "2026-.."}
    ```
    `status` is one of `pd-us-pre-1931`, `pd-us-non-renewal`, `pd-us-government`, `pd-dedicated` (dedicated to the public domain by its owner, as eBible.org did the WEB-C), `in-copyright`, `permission`, `licence`, `unknown`. An `in-copyright` entry names its `rights_holder` (for example Libreria Editrice Vaticana); this covers the papal and Vatican texts taken from vatican.va, Vatican II, the Catechism and the canon law English (Carter, 4 Oct 2026). Texts whose translation is not established from the file or page itself, including the papalencyclicals.net translations, stay `unknown`. Only public facts go in this file; no reasoning, risk assessment, or correspondence (those stay in Carter's private memos, per the Decision log "Rights review"). The Imitation of Christ renewal search from Open items is the first entry to complete. An entry with `checked_by` null is a draft that Carter has not yet approved.
    - `planned_for` (added by R6; Carter's choice, 4 Oct 2026): a planned work, not yet built, gets a row whose `planned_for` names the item that will ingest it (for example `"1.2c"`, `"5.6b"`) and whose `source_path` is where its file will be vendored. Built works have null. The coverage test ignores planned rows when looking for stale entries, still requires a row for every built work, and requires that row to have `planned_for` null, so the ingesting PR clears it.
  - Record the four unregistered cases as `vendored-unregistered` with a `note` field: the two files scheduled for 5.4, `amoris-laetitia.html`, which Carter scheduled for 5.4 with them on 4 Oct 2026, and `roman-curia/` with "parked for 5.3".
  - Update `datapipeline/SOURCES.md` (replace the "orphans" paragraph with a pointer to `source_lock.json`) and the PR template's source-check instructions.
- **Acceptance checks:**
  - `tests/test_source_lock.py` in CI with a temp directory: `--write` then `--verify` passes; a changed byte fails; a deleted file fails; an unlocked new file fails; entries are sorted and stable across two writes.
  - `tests/test_rights_inventory.py` in CI: every entry has the required fields and a known `status`; every `pd-us-non-renewal` entry has a complete `renewal_search`; every work emitted by a master build has an inventory entry (this part skips without sources).
  - Locally, `python3 scripts/source_lock.py --verify` exits 0 on Carter's Mac, and the PR description pastes its per-collection summary and the count of entries per `role`.
  - A check that a master build still reproduces the 421 live document IDs (hash `851d07063f85e4c612be1b2d44b695fb`: the md5 of the sorted document IDs joined with commas), proving the hashed files are the ones in use.
- **Production safety:** Adds tracked metadata files and local scripts. No store, API or web change. File hashes and URLs of public sources are safe to publish.
- **Needs Carter:**
  - Approve the renewal-search entries and the drafted inventory rows (he holds the private rights memos). Answered 4 Oct 2026: Claude may run the renewal searches and record them for his approval, the Imitation of Christ first.
  - Answered 4 Oct 2026: the field list of `rights_inventory.json` is safe for the public repo; `amoris-laetitia.html` goes to 5.4 with the other two unpublished papal files.
- **Out of scope:** Re-downloading any source. Adding the two 5.4 papal files to manifests or the database. Completing the rights inventory for planned sources (5.2 and R6). Storing source files in git.

---

### 2.1. Work registry: frozen IDs, structural anchors, rule A and attribution fields, removal registry

- **Type:** PR
- **Depends on:** 0.1c (its release report must show every live passage keeping its ID), 0.2
- **Goal:** Document and passage IDs stop depending on labels and anchor text. Today's 421 document IDs and today's passage IDs are written into tracked registries and adapters look them up, so fixing an author name, renaming "Song of Solomon", moving Boethius to the Fathers, or rebuilding anchors from source structure keeps every reader URL, bookmark and saved result. Anchors are rebuilt from the source's own structure instead of label text. The structural anchor decides which unit a passage is; the passage registry decides its ID (D1). Rebuilding anchors must not re-key the corpus: done naively, as first drafted, it would have re-keyed about 37,000 passages (68%). Only genuinely new units (restored verses, recovered prose, split recensions) get new IDs. This item owns six things, all tracked files under `datapipeline/registry/`:
  1. Frozen document IDs and frozen passage IDs.
  2. Structural anchors, plus the redirect file for the few units whose identity genuinely changes (D1).
  3. Rule A fields (communion dates, chronology source, Church acts), which R1 fills and 3.1 enforces.
  4. Attribution and certainty fields (rule H), which 1.8a fills first by copying the authenticity judgments from editorial text before rule G deletes it, and which 3.2 completes.
  5. The removal registry (D4). Every removal in any phase is recorded there by anchor, with its reason and tombstone text, and the D2 writer refuses to retire an ID the registry does not explain.
  6. The Python side of three shared definitions that Phase 1 adapters need before Phase 2 exists (D11): the genre module, the work model (`Passage.work_key` and the `document_works` registry shape), and the passage fields `searchable`, `language` and `passage_author`. 2.2a adds only their database side.
- **Current state:**
  - Document IDs derive from label text: `document_id(collection, author, title)` for every ThML work (`ingest/thml_doc.py:89`); `document_id("bible", translation, name)` (`ingest/bible.py:557`); `document_id("councils", council, council)` and `document_id("councils", "Second Vatican Council", title)` (`ingest/councils.py:88,153`); slug-based for encyclicals, exhortations and papal documents (`encyclicals.py:172`, `apostolic_exhortations.py:155`, `papal_documents.py:155`); constants for catechism, canon-law and summa.
  - A master build reproduces all 421 live document IDs exactly (verified 29 Sep by comparing md5 of the sorted lists). So freezing can be done by computing, not by copying from the database.
  - Planned relabels that would change IDs without a registry include 54 Fathers documents whose author ends in a period (plan, "Church Fathers and medieval"), "Song of Solomon" to "Song of Songs", and Boethius moving collection (Decision log: "Boethius's document ID stays frozen").
  - ThML anchors come from slugified chapter labels (`thml_doc.py:56-68`), with `--N` suffixes when labels repeat; Cur Deus Homo has 27 such anchors live. On the master build of 5 Oct 2026 (0.1b's `R8_anchor_suffix`) 625 passages carry one: Cur Deus Homo 28, and 597 in church-fathers, mostly the Moral (310) and Doctrinal (122) Treatises of St. Augustin. ThML sources do carry structural ids: `sources/church-fathers/apostolic fathers.xml` has 931 `div1` to `div6` elements with an `id` attribute (for example `i`, `i.i`, `ii.i`). Other adapters already anchor on structure (`can/<n>`, `<book>/<chapter>/<verse>`, `<slug>/<n>`, `ccc/<n>`).
  - Live `documents` columns: `id, collection, title, author, year, metadata, created_at, translation, chunk_count` (29 Sep). `year` is empty for 202 of 421 documents and `author` for 109; `metadata ? 'document_type'` for 16. Unique constraint `(collection, title, translation, author)` from migration 0014.
  - Passage IDs are `uuid5` of document ID and anchor (`identity.py:40-43`), so any anchor change changes the ID. Another spec measured that switching to structural anchors with that formula would re-key about 37,000 passages (68% of the corpus), which D1 forbids.
  - `reading_progress` stores `chapter_key` and `anchor`; reader URLs carry `anchor` or `chapter`. Anchor-string changes therefore need each unit's live anchor kept for resolving old links (2.4a) and the 0.1c chapter remap (4.1a), even when the passage ID does not change.
- **Changes:**
  - Add a tracked `datapipeline/registry/works.json`, a list sorted by `collection`, then `work_id`. Each entry:
    ```json
    {"work_id": "church-fathers/anf01/ii.iii",
     "document_id": "<frozen uuid>",
     "collection": "church-fathers",
     "source_key": "church-fathers/apostolic fathers.xml#ii.iii",
     "title": "...", "author": "...",
     "frozen_on": "2026-..", "status": "active",
     "supersedes": [],
     "rule_a": {
       "applies": false,
       "communion_start": null, "communion_end": null,
       "work_date": null, "chronology_source": null,
       "church_acts": [],
       "decision": null, "decision_basis": null
     },
     "attribution": {
       "credited_as": null,
       "certainty": null,
       "clavis": null,
       "basis": null,
       "editorial_judgments": []
     }}
    ```
    `source_key` is structural: file plus ThML div `id` for ThML works; `bible/<USFM book code>` (for example `bible/DAG`); `<collection>/<manifest slug>` for HTML collections; the collection name for the three single-document collections. `status` is `active`, `removed` (kept for tombstones), or `moved`. `rule_a.church_acts` items are `{"issuer": "...", "date": "YYYY-MM-DD", "act": "...", "effect": "condemn|prohibit|warn|lift", "citation": "<url>"}`. `rule_a.decision` is `include`, `exclude`, or null until R1 fills it.
    `attribution.credited_as` is the display credit under rule H, for example "Pseudo-Justin". `certainty` is `genuine`, `disputed`, `pseudonymous`, `anonymous`, or null until set. `clavis` is the CPG or CPL number where one exists. `basis` cites the Church text or Clavis entry the credit follows. `editorial_judgments` is where 1.8a copies each authenticity judgment found in editorial text before rule G removes that text, as `{"source_file": "...", "element_id": "...", "quote": "<the judgment, 300 characters at most>", "verdict": "genuine|spurious|dubious|interpolated|attributed", "overridden_by_plan": false}`. A judgment the plan's "Labels for works that stay" overrides is kept with `overridden_by_plan: true`, so the audit trail stays complete. 3.2 sets `credited_as` and `certainty` from these and from the plan.
  - Add `datapipeline/registry/__init__.py` with `load_registry()`, `frozen_document_id(collection, source_key) -> str | None`, and `register_new_work(...)`. Adapters call `resolve_document_id(collection, source_key, fallback_parts)`: the frozen ID if the source key is registered, otherwise `identity.document_id(*fallback_parts)` (new works). A test forbids two source keys resolving to one ID.
  - Add `datapipeline/scripts/freeze_registry.py`, run once in this PR: build every collection on master adapters, pair each document's current ID with its structural source key (adapters expose it through `Document.metadata["source_key"]`, added in this PR), write `works.json`, and write the passage registry as described below. It refuses to write unless exactly 421 documents are produced and their sorted-ID md5 equals `851d07063f85e4c612be1b2d44b695fb` (or the hash of a fresh read-only query, if the live set has changed).
  - Change every adapter's `Document(id=...)` to `resolve_document_id(...)`. With the registry frozen, a master build still yields the same 421 IDs.
  - Structural anchors, per adapter:
    - ThML (`thml_doc.make_doc`): anchor is the chapter div's `id` (dots kept as `.`, which the anchor charset must then allow; or mapped to `-`, one rule applied everywhere), plus `/p<k>` for split parts. `chapter_key` is the same div id; `chapter_label` keeps its current text. No `--N` suffixes remain.
    - Summa: anchor from `part/question/article` numbers and the article part (objection, sed contra, corpus, reply) as the XML structures them, not from `a_title` (`ingest/summa.py:104`).
    - Catechism: unchanged where anchors are already `ccc/<first paragraph number>`; replace the `meta.get("path", str(pos))` fallback (`ingest/catechism.py:267`) with a structural path.
    - Bible, canon law, HTML numbered collections: already structural; unchanged in this PR.
    - Record the anchor scheme version in `Document.metadata["anchor_scheme"] = 2`.
  - Add the passage registry, one tracked file per collection, `datapipeline/registry/passages/<collection>.jsonl`, sorted by `document_id`, then `anchor`. One row per unit that exists today:
    ```json
    {"passage_id": "<frozen uuid>", "document_id": "<frozen uuid>",
     "anchor": "<current structural anchor>", "live_anchor": "<anchor when frozen>",
     "status": "active", "frozen_on": "2026-.."}
    ```
    `status` is `active`, `retired` (a removal-registry entry explains it) or `redirected` (a redirect row names its successor). Rows also carry `work_key` (null unless the passage belongs to a work inside a container document, below) and, where 3.3 or another item sets them, the overrides `searchable`, `language`, `passage_author` and `note`. IDs, anchors and these short fields only, no passage text, so the files are safe in the public repo. At about 54,800 rows they come to roughly 7 MB, split by collection so each P1 PR's diff stays readable.
  - Passage ID resolution: add `resolve_passage_id(document_id, anchor)` to `registry/__init__.py`. It returns the frozen ID when the registry has a row for that document and current anchor, and otherwise `identity.passage_id(document_id, anchor)`, which only genuinely new units reach. `identity.passage_id` itself stays unchanged. Every adapter and the writer take passage IDs from `resolve_passage_id`. A test forbids a new unit's computed ID colliding with any frozen ID.
  - How the freeze pairs units: during this PR each adapter emits both anchors for every passage, the structural anchor as `anchor` and today's label-derived anchor as `metadata["live_anchor"]`. `freeze_registry.py` (below) writes one row per master-build passage with `passage_id = identity.passage_id(document_id, live_anchor)`, which is exactly today's ID. The 163 live passages that a master build no longer emits (0.1c) get rows with `status` left for their `known_defects.json` entry to settle before P4, by a removal entry or a redirect. After the freeze the adapters drop `live_anchor`; the registry keeps it.
  - When a later item changes a unit's anchor string without changing the unit (a label fix, Sacrosanctum Concilium's misprinted "81" becoming 87, a short unit that now splits into `base/p1` and `base/p2`), it edits the registry row's `anchor` and keeps the ID. The first piece of a newly split unit keeps the unit's ID; later pieces are new. No redirect is needed, because the ID does not change.
  - Genre module (D5, D11). Add `datapipeline/registry/genres.py`, the one definition of the genre vocabulary. It holds `PAPAL_GENRES` (`encyclical`, `apostolic-exhortation`, `apostolic-letter`, `apostolic-constitution`, `motu-proprio`, `bull`, `letter`), `CURIA_GENRES` (`declaration`, `instruction`, `doctrinal-note`, `note`, `response`, `norms`, `considerations`, `commentary`), `CATECHISM_AND_LAW_GENRES` (`catechism`, `compendium`, `code`, `law`), `WRITER_GENRES` (`treatise`, `manual`, `sermon`, `commentary`, `poem`, `rule`), `OTHER = "other"`, and `ALL_GENRES`, the ordered union without duplicates (`commentary` appears once). A test checks every value is lowercase and hyphenated. 1.3b and every later adapter import from here. 2.2a seeds its `corpus_genres` table from this module and tests that the two match. Adding a genre is a PR that changes this module and adds the matching row to `corpus_genres` in a migration.
  - Work model (D6, D11). Container documents (an ANF volume, "Treatises Attributed to Cyprian", "Dubious or Spurious Writings") hold several works. The model here is what 2.2a's `document_works` table and `chunks.work_key` column store:
    - `datapipeline/model.py`: `Passage` gains `work_key: str | None = None`, and `Document` gains `works: list[Work] = []`, where `Work` is a frozen dataclass with `work_key, ordinal, title, author, certainty, attribution_note, notes, date_display, year, genre, clavis_ref`. `genre` must be in `ALL_GENRES`.
    - Registry shape: each `works.json` document entry gains `"works": []`, a list of objects with the same fields as `Work`, sorted by `ordinal`. Which passages belong to which work is recorded per passage, as `work_key` in the passage registry, never as an anchor or position range. A validator checks every passage `work_key` names a work of the same document, and every work has at least one passage.
    - This PR ships the shape with no works filled in. 1.8b and 1.8c fill the container documents; 2.3 and 3.2 fill the attribution values.
  - Passage fields adapters set (D11). `Passage` also gains `searchable: bool = True`, `language: str | None = None` (an ISO 639 code, null meaning English) and `passage_author: str | None = None` (a passage-level author, such as a Father quoted in the Catena Aurea). An adapter may set them from its source, as 1.5b does for Latin canons. A value in the passage registry overrides the adapter's value (3.3), and 2.2w applies the override at stage time, so the registry always wins.
  - Superseded text at passage level (rule F, D11). Where an adapter keeps an older text of a unit as history (CCC 2267, amended canons), it emits the older text as its own passage, never as metadata of the current one:
    - anchor `<anchor of the current passage>/history-<year>`, where `<year>` is the year the older text took effect (for example `can/295/history-1983`);
    - `searchable = False`;
    - `Passage.superseded_by_anchor` (a further new field, `str | None = None`) set to the current passage's anchor in the same document. 2.2w resolves it to the current passage's ID and writes `chunks.superseded_by` (2.2a).
    A history passage is a new unit with a new ID. It is not a removal, so it has no removal-registry entry. Whole-document history (Universi Dominici Gregis, 5.4) uses `documents.superseded_by` instead.
  - Add the redirect file `datapipeline/registry/redirects.json`, a list sorted by `document_id`, then `old_anchor`. Each row is `{"document_id": "<uuid>", "old_passage_id": "<uuid>", "old_anchor": "...", "new_passage_id": "<uuid>", "new_anchor": "...", "kind": "moved|split|merged|renumbered", "reason": "...", "added_by": "<item id>"}`. The kinds are 0.1c's outcome words (D5). Redirects are only for units whose identity genuinely changes: a unit whose text now lives in other units (piece anchors that disappear when a unit needs fewer pieces), passages regrouped at new chapter boundaries (1.4b Joel and Malachi), councils rebuilt by session (1.2b to 1.2e), and a split recension (1.8c). This PR adds none. The writer loads the file into 2.2a's redirects table.
  - Add the removal registry `datapipeline/registry/removals.json` (D4). It is the one record of everything any phase removes: rule A to C removals, rule G editorial text, endnotes split off, duplicate passages, debris, commentary by other authors, Tanner council texts, and superseded translations. Entries are by anchor, never by position. Format, one object per entry, sorted by `collection`, `document_id`, `anchor`:
    ```json
    {"id": "rm-0001",
     "scope": "passage",
     "collection": "church-fathers",
     "document_id": "<frozen uuid>",
     "anchor": "<live anchor>",
     "passage_id": "<frozen uuid>",
     "reason": "rule-g-editorial",
     "detail": "Elucidation by the American editor, not the author's text.",
     "tombstone": "This passage was an editor's note and was removed because TheoCorpus shows only the authors' own words.",
     "church_act": null,
     "span": null,
     "judgment": null,
     "added_by": "1.8a",
     "added_on": "2026-10-.."}
    ```
    - `scope` is one of:
      - `document`: the whole document is retired (rule A works such as Origen's); `anchor` is null.
      - `passage`: one live passage is retired; `anchor` is the anchor as the 0.1c snapshot holds it (the passage registry's `live_anchor`) and `passage_id` its frozen ID, and the registry validator checks the two agree.
      - `span`: text cut from inside a passage that survives (commentary lines, an editor's bracket); `anchor` is the build anchor of that passage, and `span` holds `{"sha1": "<of the removed text>", "excerpt": "<first 120 characters, public-domain editorial matter only>"}`. Nothing is retired for a span entry; it is the audit record.
      - `class`: one rule applied across a collection that removes text inside passages in bulk, such as 1.10b's inline `<note>` strip; `span` holds `{"rule": "<the pattern or function name>", "count": <units removed>}`.
    - `reason` is one of `rule-a`, `rule-b`, `rule-c`, `rule-g-editorial`, `note-split-off`, `duplicate`, `debris`, `other-author`, `superseded-translation`, `translation-in-preparation`, `not-current-law`. This is the only list of removal reasons (D11); 2.2a's tombstone table and 3.1 use it. One more value, `rolled-back`, is reserved for tombstones that 2.2w's `rollback` writes for rows a rolled-back publish had inserted; it never appears in `removals.json`, and the validator rejects it there. (D11's list names 11 values; `rolled-back` is an addition this spec needs, flagged for Carter in NEEDS-CARTER.md.) New reasons are added here, in this file's validator, not in the item that needs them. The long Ignatian recension is `rule-b`.
    - `tombstone` is required for `document` and `passage` scope and null otherwise. It is one sentence of reason, plus the Church act where one applies, with no text of the removed passage (D3). For `rule-a` and `rule-b` entries `church_act` holds `{"issuer", "date", "act", "citation"}` in the rule A format above.
    - `judgment` holds any authenticity judgment found in the removed text (1.8a), which must also appear in the work's `attribution.editorial_judgments`.
    - Entries are never deleted, because the file is the one record of every removal. When a removed unit comes back (On the Incarnation's document after the early retirement, 1.8d), its entry gains `"closed_by": "<item id>"` and `"closed_on": "<date>"`. The writer ignores closed entries, and the unit's rows are then explained by the build (un-retired) or by redirects.
    - `registry/__init__.py` validates the file. Every entry's document ID is in `works.json`. No two entries retire the same anchor. A retired anchor never appears in `redirects.json` as a `new_anchor`. `tombstone` is present where required and under 300 characters. `reason` is in the list. A build that emits an anchor listed here with scope `passage` fails (0.1c), so a retired anchor string is never reused.
    - This PR ships the file empty, since an anchor-scheme change removes no text. Each later item adds the entries for what it removes, in the same PR. 3.1 adds the rule A to C entries. Nothing is applied until 4.1b (D2, D7).
- **Acceptance checks:**
  - CI tests in `datapipeline/tests/test_registry.py`:
    - `test_registry_has_421_entries_and_unique_ids`
    - `test_registry_is_sorted_and_stable`
    - `test_frozen_id_wins_over_label_derived_id` (a relabeled synthetic work keeps its ID)
    - `test_unregistered_work_falls_back_to_identity_document_id`
    - `test_two_source_keys_cannot_share_an_id`
    - `test_rule_a_fields_validate` (dates ISO, `effect` in the allowed set, `citation` present for each act)
    - `test_attribution_fields_validate` (`certainty` in the allowed set; every `editorial_judgments` item has a source file, element id and verdict)
    - `test_frozen_passage_id_survives_anchor_change` (a synthetic unit whose anchor string changes keeps its ID)
    - `test_new_unit_gets_computed_id_that_collides_with_no_frozen_id`
    - `test_first_piece_of_newly_split_unit_keeps_unit_id`
    - `test_passage_registry_is_sorted_and_stable`
    - `test_redirect_kinds_are_remap_words`
    - `test_removal_entries_validate` (scope, reason, tombstone rules above)
    - `test_removal_entry_needs_anchor_not_position` (an entry with a `position` field and no anchor fails)
    - `test_no_anchor_is_both_retired_and_a_redirect_target`
    - `test_rolled_back_reason_is_rejected_in_removals_file`
    - `test_closed_entry_is_kept_and_ignored_by_writer`
    - `test_genre_values_are_lowercase_hyphenated_and_unique`
    - `test_passage_work_key_names_a_work_of_its_document` and `test_every_work_has_a_passage`
    - `test_registry_override_wins_over_adapter_fields` (an adapter sets `searchable=True` and the registry row sets `false`; the resolved passage has `false`)
    - `test_history_passage_shape` (anchor ends `/history-<year>`, `searchable` is false, `superseded_by_anchor` names a passage in the same document)
  - CI tests in `test_thml_doc.py`: `test_anchor_is_div_id` and `test_no_anchor_suffixes` on a synthetic ThML fixture with repeated labels.
  - Locally with sources: a master build with this PR produces the same 421 document IDs (md5 unchanged) and the same set of passage IDs as the pre-PR master build (sorted-ID md5 equal), although most church-fathers, medieval and summa anchors change. `R8_anchor_suffix` from 0.1b reports 0.
  - Every passage live today keeps its ID unless the removal registry or a redirect explains it. The 0.1c report against the current snapshot shows every live passage as `same`, except the known pre-existing drift recorded in `known_defects.json` (the 163 live passages a master build already lacks); `moved`, `split`, `merged` and `renumbered` are 0; no new stability failures; and user impact 0. The PR description pastes both reports' summaries side by side.
  - `checks.report` coverage and sequence numbers unchanged from the pre-PR run.
- **Production safety:** Nothing is published; the publish lock holds. Passage IDs do not change, so bookmarks and saved results need no remap for this item. Anchor strings do change, and they reach users only at the P4 cutover. There, 2.2w writes an anchor redirect for every passage-registry row whose `anchor` differs from its `live_anchor` (about 37,000 rows, a few MB), 2.4a resolves old `?anchor=` and `?chapter=` links through those redirects, and 4.1a moves `reading_progress` anchors with the chapter remap. No API or web change; `reading_progress` and shared URLs keep working against today's data until then.
- **Needs Carter:**
  - Approve the anchor scheme change and the character mapping for div ids. Passage IDs stay frozen, so the one-time ID churn the Decision log "Document identity" once accepted does not happen.
  - Approve adding the passage registry (about 7 MB of IDs and anchors, no text) to the public repo.
  - Approve the removal registry format. Tombstone sentences and reasons are public in this repo and are what users see on a removed passage.
  - Approve the reserved reason `rolled-back`, which D11's list does not name.
  - Added by 0.1c (6 Oct 2026 snapshot). 408 Summa passage IDs name a different part in the master build than live, in 81 articles (a live blank passage in 21; "On the contrary" and "I answer that" printed as one passage live in 60), so freezing them from the build's anchors would make each show its neighbouring part after the republish. Carter decided on 5 Oct 2026 that this item gives each of them to the part it names live (Decision log "Summa passage IDs shifted in the live publication (0.1c)"). Open: how. Recommended: take the pairing from 0.1c's `remap.jsonl` (the build part holding the live passage's text keeps the live ID; parts live never had get new IDs) rather than writing 408 pairs by hand. They are the `release.stability:summa/…` entries in `checks/known_defects.json`.
  - Added by 0.1c. First Lateran `sec-0/1` names the editor's introduction live and canon 1 in the build. Recommended: this item gives canon 1 the live ID of `sec-0/1-2`; the council item that rebuilds First Lateran adds the introduction's `rule-g-editorial` removal entry. Its `known_defects.json` entry names this item for the pairing.
  - Added by 0.1c. The acceptance check below expects `moved`, `split`, `merged` and `renumbered` at 0 apart from the 163 live passages a master build lacks, but those 163 are themselves 134 `split`, 22 `moved` and 7 `merged`, none `removed`; once this item adds `registry/redirects.json` each fails as `release.unbacked` until a redirect row or removal entry backs it. Recommended: read the check as "0 beyond those 163"; this item lists each of the 163 in `known_defects.json`, and the item that rebuilds each passage's document adds its redirect or removal entry before P4.
- **Out of scope:** Filling `rule_a` (R1). Filling attribution values (1.8a copies editorial judgments; 3.2 sets labels). Adding removal entries beyond this PR's own (each P1 item adds its own; 3.1 adds rules A to C). Label, author or collection changes (P1, P3, P5). Adding registry columns to the database (2.2a). Applying the remap or retiring anything in live data (4.1a, 4.1b).

---

### 0.3. Baseline eval run

- **Type:** PR (runner changes and question file), then ops (a Carter-approved run)
- **Depends on:** 0.0. The run must happen before any live change (D7), which includes the possible early retire of On the Incarnation (1.8d), not only the P4 apply.
- **Goal:** A measured "before" picture of search on today's live corpus, so 4.2 can show what the cleanup improved and what it cost users (removed works, changed rankings). 4.2 compares judge scores, so the baseline is judged too. It uses the existing 80-question set plus new targeted questions for the Vatican II recovery, the other repairs, and the removals. It never uses stored user queries.
- **Current state:**
  - `.gitignore` ignores `docs/eval/*` except `ROUND3_REPORT.md` and `eval80-round3-final.jsonl`; `luna6-cost-and-quality-2026-09-23.md` is also tracked. The per-query artifacts with passage IDs exist only on Carter's Mac.
  - The "gold sets" are question sets with LLM-judge scores, not gold passage IDs. `eval80-round3-final.jsonl` has 80 rows over collections bible, catechism, church-fathers, encyclicals, summa at quota 4; per pipeline it stores `top` as `rank, collection, reference, score` without passage IDs. The 80 questions are `QUERIES` in `services/api/scripts/run_eval_suite.py` (80 entries). Passage IDs appear only in the gitignored artifacts (`shared.candidate_pools[<pipeline>][<collection>][].chunk_id`).
  - The runner (`run_eval_suite.py`) uses `shared_runner.capture` and `replay` and the judge, and writes nothing to the database (no INSERT in `app/rag/compare/shared_runner.py`, `app/rag/pipelines/`, `app/rag/steps/`; only `app/rag/compare/persist.py` inserts, and the script does not import it). It fixes `COLLECTIONS` to the five above, so councils, canon-law, papal, apostolic-exhortations and medieval are never evaluated.
  - Production pipeline is `hyde_cohere_luna` (`services/api/app/rag/pipeline.py:30`).
  - Round 3 cost for `hyde_cohere_luna` over 80 queries was about $2.92 of retrieval spend at launch Luna prices, and the judge about $16.34 across three pipelines (computed from `eval80-round3-final.jsonl`). `ROUND3_REPORT.md` notes Luna's later price cut.
- **Changes:**
  - `run_eval_suite.py`:
    - Add `chunk_id` and `document_id` to each `top` entry (lines 677-680) and raise `top` from 5 to `--top-k` (default 10).
    - Add `--collections` (default the current five) and `--query-file <path>` to load questions from JSONL instead of the in-file list.
    - Make judging work for a single pipeline. Read `judge.run` first. If it scores each result on its own, record those per-result scores as they are. If it only ranks pipelines against each other, add a single-pipeline mode that records a per-result relevance score and a per-question score in the same scale 4.2 will use. Record the judge model and prompt version in the run fingerprint, so 4.2 can refuse to compare against a baseline judged differently.
    - Add `--no-judge` for local dry runs of the runner only. The baseline run does not use it.
    - Include the live corpus fingerprint in the run fingerprint: passage count and sorted-document-ID md5, read with one SELECT at start.
  - Add `docs/eval/targeted-2026-10.jsonl` (tracked; add a `!docs/eval/targeted-2026-10.jsonl` line to `.gitignore`). About 30 questions, each written fresh in neutral wording (not copied from the `searches` table or from the wording in the gap audit), with `collections`, `quota` (5, or 10 with one collection), and `expect` as structural patterns such as `{"document": "Nostra Aetate", "section": "4"}` or `{"collection": "church-fathers", "author": "Origen"}`. Groups:
    - Vatican II recovery (8): Nostra Aetate 4; Dei Verbum 10 to 12; Unitatis Redintegratio 3 to 4; Lumen Gentium 25; Gaudium et Spes 16; Dignitatis Humanae 2; Ad Gentes 7; Presbyterorum Ordinis 16.
    - Other councils (4): Trent session VI on justification; Trent session XIII on the Eucharist; Vatican I Pastor Aeternus chapter 4; Nicaea canons.
    - Bible (3): Susanna (Daniel 13); Bel and the Dragon (Daniel 14); the Greek additions of Esther.
    - Canon law (3): canon 112; canon 266; canon 1330.
    - Catechism and Summa (3): CCC 2267; Summa I q.71 and q.72; one exact-paragraph question on a Catechism section known to sit inside a larger passage.
    - Papal (2): In Dominico Agro; Quanta Cura.
    - Removals (6), to record what users lose: Origen on the senses of Scripture; Tertullian on baptism or prayer; the Apostolic Constitutions on liturgy; Novatian on the Trinity; the Ignatian letters on the bishop and the Eucharist (genuine and forged letters both present today); Arnobius against the pagans.
    - Non-English (1): a question whose best answer today is one of the Latin Stromata III passages.
  - Output layout, all local and gitignored except the summaries: `docs/eval/baseline-2026-10/eval80.jsonl`, `targeted.jsonl`, artifacts directories, and a tracked `docs/eval/baseline-2026-10-summary.jsonl` holding per question the ranked `chunk_id`, `document_id`, `collection`, `reference`, retrieval score and judge score (no passage text), plus `expect` hit@5 and hit@10 for targeted questions.
  - Add `services/api/scripts/baseline_summary.py`, which reads the two JSONL outputs and writes the tracked summary and a short `docs/eval/BASELINE-2026-10.md` (hit rates and mean judge scores per group, collections covered, degraded-query count, total spend split into retrieval and judge).
  - Ops run, on Carter's approval, from `services/api` with its `.env`:
    - `python scripts/run_eval_suite.py --pipelines hyde_cohere_luna --top-k 10 --out ../../docs/eval/baseline-2026-10/eval80.jsonl`
    - `python scripts/run_eval_suite.py --pipelines hyde_cohere_luna --top-k 10 --query-file ../../docs/eval/targeted-2026-10.jsonl --collections all --out ../../docs/eval/baseline-2026-10/targeted.jsonl` (the `--query-file` rows carry their own collections; `--collections all` only widens the default)
    - `python scripts/baseline_summary.py docs/eval/baseline-2026-10`
- **Acceptance checks:**
  - API tests in CI: `tests/test_run_eval_suite_cli.py::test_query_file_rows_validate` (fields, collections valid against `VALID_COLLECTIONS`, quota in 3, 4, 5, 10, focused rows have exactly one collection), `::test_top_entries_carry_chunk_and_document_ids` (with a stubbed `shared_runner`), `::test_single_pipeline_judging_records_per_result_scores` (with a stubbed judge), `::test_no_judge_skips_judge_init_and_calls`, `::test_fingerprint_includes_corpus_and_judge_fingerprint`.
  - A lint test that no targeted question string appears in a fixture of the `searches` query texts is not possible without exporting user data, so instead the PR description states how the questions were written and Carter reviews them.
  - After the ops run: 80 eval rows and about 30 targeted rows, all quality-eligible and all judged, or the ineligible ones listed; the summary file committed; `BASELINE-2026-10.md` shows, at minimum, that Nostra Aetate 4's continuation text is not retrievable today (expected hit 0) and which removed works appear in the top 10.
  - The corpus fingerprint in the run equals the live fingerprint read at the time, showing no live change had happened yet.
  - Total provider spend reported and under the ceiling Carter sets (estimate below).
- **Production safety:** The runner reads live Postgres and Qdrant and writes nothing to them (verified by grep above). It calls OpenAI, Cohere and Anthropic (the judge) with eval questions only, as earlier rounds did. The script changes are in `services/api/scripts/`, which the Docker image does not copy (`COPY app/ app/` only, `services/api/Dockerfile:11`).
- **Needs Carter:**
  - Approve the targeted question list.
  - Approve the spend. Estimate about $3 for the 80 retrieval runs at round-3 rates (less after the Luna price cut) and about $1.50 for the targeted set, plus judging. Round 3 judged 3 pipelines for about $16.34, so one pipeline is about $5.50 for the 80 questions and about $2 for the targeted set. Total about $12.
  - Confirm the run happens before any live change, including an approved early retire of On the Incarnation (1.8d), while the live corpus is unchanged (the corpus fingerprint records it).
- **Out of scope:** Pipeline changes, retrieval tuning (a separate parent after the new baseline). Replaying stored user searches. The 4.2 comparison itself.

---

### 0.5. Ops: read the Qdrant plan's memory and disk limits

- **Type:** ops (Carter-run)
- **Depends on:** none
- **Goal:** Know whether the Qdrant cluster can hold today's `chunks` collection and a second, rebuilt collection at the same time during the P4 cutover (2.2b alias, 4.1b), and whether that second collection must keep vectors on disk (Decision log "Storage (4.0)").
- **Current state:**
  - Both the pipeline and the API name a single collection `"chunks"` (`datapipeline/writers/qdrant.py:15`, `services/api/app/rag/qdrant_client.py:10`). `qdrant_schema.py:17-30` creates it with HNSW `m=16`, `ef_construct=64`.
  - Plan (measured 28 Sep): one collection, 54,568 points at 1,536 dimensions, about 335 MB of raw float32 vectors (54,568 × 1,536 × 4 bytes), no quantization, no alias. A second full collection during cutover needs about 670 MB of raw vectors plus two HNSW graphs and payloads.
  - The cluster tier, RAM, disk, and whether `facets` or `questions` collections exist in production are **not verified** in this spec (no Qdrant access was used).
- **Changes:** No code. Carter records the answers in a short section appended to this item (or in the P4 runbook):
  - From the Qdrant Cloud console: cluster tier, RAM, disk, vCPU, region, and backup settings.
  - `GET {QDRANT_URL}/collections` and `GET {QDRANT_URL}/collections/chunks` (read only, with the API key): collection list, `points_count`, `indexed_vectors_count`, `config.params.vectors` (`size`, `distance`, `on_disk`), `hnsw_config`, `quantization_config`, `optimizer_status`, `segments_count`.
  - `GET {QDRANT_URL}/aliases`: confirm no aliases exist.
  - `GET {QDRANT_URL}/telemetry` if the tier exposes it: current RAM use.
  - Decision rule to record: if free RAM with today's collection loaded is under about 1.2 times the estimated size of a second in-memory collection (about 400 MB with graph and payload), build the new collection with `on_disk: true` vectors (and consider scalar quantization only as a separate, evaluated change).
- **Acceptance checks:** The recorded section lists every value above with the date read, and states the decision rule's outcome (in memory, or on disk).
- **Production safety:** Read-only console views and GET requests. Nothing is created, changed or deleted.
- **Needs Carter:** Run it (he holds the Qdrant credentials and console access).
- **Out of scope:** Creating the alias or new collection (2.2b, 4.0, 4.1b). Changing the plan tier.

---

### 0.6. Storage headroom snapshot (prep for 4.0)

- **Type:** ops (Carter-approved, read-only)
- **Depends on:** none; repeat after 0.1c's first full report
- **Goal:** Put numbers next to the 4.0 storage decision before P4, so the `VACUUM FULL` window and any Supabase Pro purchase are sized from measurements, not guesses. The `VACUUM FULL` measurement itself belongs to 4.0 and is not specified here.
- **Current state (read-only SELECTs, 29 Sep):**
  - Database 401 MB. `chunks` total 380 MB, heap 89 MB, indexes 88 MB, TOAST 203 MB; `n_dead_tup` 0, `n_live_tup` estimate 52,003 (the table holds 54,568 rows).
  - Largest `chunks` indexes: `chunks_document_chapter_pos_idx` 27 MB, `chunks_search_vector_idx` 26 MB, `chunks_document_anchor_uniq` 26 MB, `chunks_document_id_position_key` 5.3 MB.
  - The Supabase plan's database size limit and current plan tier are **not verified** here (memory note `project_supabase_storage_ceiling.md` says the free tier will not hold the enriched corpus).
- **Changes:** No code. Record, in this item or the 4.0 spec:
  - The same size query (`pg_database_size`, `pg_total_relation_size('chunks')`, heap, index, TOAST sizes) and per-table sizes for `documents`, `document_chapters`, `retrievals`, `guest_trial_retrievals`.
  - The plan tier and its database size limit from the Supabase dashboard.
  - An estimate of the rebuilt corpus from the 0.1c report: build passage and character counts (master build today is 54,778 passages; the Vatican II and council repairs add roughly 0.9 MB of text), and, during cutover, the one staging copy that stage then apply builds in schema `staging` (D2; about 123 MB of live row data plus up to 88 MB of indexes, so about 210 MB, per 4.0's projection), before compaction. Retired rows stay in `chunks` until the rollback window ends (D3), so count them too.
- **Acceptance checks:** The recorded numbers, the limit, and the estimated peak during cutover, with the gap to the limit stated in MB.
- **Production safety:** Read-only catalogue queries.
- **Needs Carter:** Approve running the queries and read the plan limit from the dashboard.
- **Out of scope:** `VACUUM FULL`, buying Pro (4.0). The rehearsal, which runs on a local Postgres restored from a `pg_dump` of production, not a Supabase branch (4.1a, D8).

---

### R1. Rule A dating and Church-act check

- **Type:** research
- **Depends on:** none to start; results land in the 2.1 registry's `rule_a` fields. Blocks 3.1 (removals); 3.2 for the Refutation of All Heresies, whose label waits on the Hippolytus dating below and not only on R4 (D10); 5.6a (Fathers additions); 5.6b (spiritual writers, including the Catena Aurea's Pseudo-Chrysostom quotations)
- **Goal:** For every author in the corpus and the planned candidates, establish the facts rule A needs, each with a citation, so that PR 3.1 removes exactly what the rules remove and nothing else, and 5.6a and 5.6b add only authors who pass. There are two parts. The Church-act check finds any formal act of the Holy See naming the author or a work (condemnation, prohibition, Index entry, monitum) and any later lifting. The dating part, only for authors whose communion changed while they were writing, places each work before or after baptism or reception, and before or after any break, from one named standard chronology.
- **Current state:**
  - The rules and the Decision log are settled; do not reopen them. Decided outcomes to record, not re-research: Origen, Novatian, Tatian, Arnobius, Alexander of Lycopolis out; Tertullian judged per work, with To His Wife (22 passages) and On the Apparel of Women (28) provisionally in; Loisy, Tyrrell, Teilhard, the Provincial Letters, Maxims of the Saints, Spiritual Guide and Augustinus out; Rosmini and Faustina in; Chesterton's Orthodoxy, Newman's Parochial and Plain Sermons and Edith Stein's pre-1922 works out; Newman's Development in the 1878 edition.
  - Named as unverified in the plan's Open items: Theologia Germanica on the Index; the exact form of Tyrrell's 1907 excommunication; the Pensées' Index status. The candidates memo (`docs/research/2026-09-28-theologians-spiritual-writers-candidates.md`, section 4) also leaves unconfirmed the Provincial Letters decree text, Erasmus's Index entries, and Ockham's reconciliation. All six are answered in `docs/research/R1-rule-a-dating.md`, section 3 (R1, 5 Oct 2026).
  - Sources already gathered for the patristic persons are in `docs/research/2026-09-28-rule-1-authorship-verification.md` section 7.
  - One case the plan does not address: Hippolytus led a rival community in Rome, in schism from about 217 to his reconciliation around 235 (rule-1 memo, section 7(f)), and the Refutation of All Heresies (377 live passages) is dated to the 220s by the scholarship that memo cites. Under rule A a work written outside communion goes, and Hippolytus is not a Doctor. R1 must date his works and report the result; the decision is Carter's. 3.2 cannot label the Refutation until this is settled.
  - A second case for 5.6b: the Catena Aurea (Decision log "Catena Aurea") quotes many passages as "Chrysostom" that come from the Opus imperfectum in Matthaeum, usually credited today to an anonymous Arian writer ("Pseudo-Chrysostom"). Each quotation is to be attributed to the Father quoted, so R1 must say how rules A and B treat those quotations (keep with a Pseudo-Chrysostom label, or exclude), with the scholarship cited, and list it under "For Carter".
- **Changes (deliverables):**
  - `docs/research/R1-rule-a-dating.md` (plan repo), with:
    - An author list built from the 2.1 registry plus the candidates memo, each classified as `born-in-communion`, `convert-no-pre-baptism-writing`, `convert-with-possible-pre-baptism-writing`, `later-break`, or `break-and-return`, with one citation per classification. Expect about 20 in the last three classes (Decision log "Rule A dating method"). Patristic converts to check include Justin, Athenagoras, Theophilus, Clement of Alexandria, Minucius Felix, Cyprian, Lactantius, Gregory Thaumaturgus, Commodian, and Augustine (his Cassiciacum works predate baptism; confirm none are in the corpus). Modern ones include Newman, Chesterton, Stein, Knox, Faber, Brownson and Manning if on the candidate list.
    - For each author in those three classes, the one standard chronology used (named edition and page), the communion dates, and per work the date range and the resulting `include` or `exclude`, excluding when standard sources disagree about which side of the line a work falls on.
    - For every author in the corpus and candidates, the Church-act search result: acts found (issuer, date, act, effect, citation URL to an official or scholarly text of the act) or "none found", with the sources searched (at minimum the 1948 Index Librorum Prohibitorum, De Bujanda's Index volumes where reachable, and the Holy Office and CDF notifications on vatican.va).
    - The three open Index questions answered with the decree cited.
  - `datapipeline/registry/rule_a_R1.json`, entries keyed by `work_id` holding exactly the `rule_a` object shape from 2.1, for merge into `works.json` by PR 3.1 (or by 2.1 if R1 finishes first). Because `work_id` did not exist yet, Carter decided on 4 Oct 2026 that entries are keyed by the frozen `document_id` for corpus works and by `{author, title}` for planned candidate works. R1 also proposes keying the works inside container documents by `document_id` plus ThML `div_id`; Carter accepted that key on 5 Oct 2026 (R1 findings, "For Carter" item 10).
- **Acceptance checks:**
  - Every corpus and candidate author appears once with a classification and citation.
  - Every `exclude` names the act or the chronology entry that causes it; every Tertullian work has a date range and source.
  - The passage count each decision removes is computed from the registry and a master build and matches, or explains differences from, the plan's "What the rules remove" table (Tertullian 192, and so on).
  - Findings that would change a Decision log outcome (Hippolytus is the known one) are listed separately under "For Carter", with no change made to the plan. The Pseudo-Chrysostom question is listed there too.
- **Production safety:** Research only; nothing touches code or data.
- **Needs Carter:** Decide the Hippolytus question and any other finding listed under "For Carter". Approve the chronology choices where two standards exist. R1 (5 Oct 2026) adds: Gregory Thaumaturgus's Panegyric to Origen (37 passages, baptism undated), Lactantius's Phoenix (4, undatable); for 5.6b, the Catena Aurea's Origen quotations (limit 1) and Theophylact and Josephus quotations; whether Theologia Germanica in an English translation from the German is barred (only Castellio's Latin version was prohibited, 1621); how limit 1 reads where a bull names an author while condemning his propositions (Eckhart, Abelard); and the container sub-work key. See the findings file's "For Carter". Answered 5 Oct 2026: all of R1's recommendations accepted (see NEEDS-CARTER.md); `rule_a_R1.json` records the resulting decisions.
- **Out of scope:** Removing anything (3.1). Rules B, C, D labels (3.2). Re-arguing decided authors.

---

### R2. Canons 295, 296, 360, 361 and 948 against iuscangreg.it, and English sources for the Latin canons

- **Type:** research. This entry is the only spec for R2; the P1a file points here.
- **Depends on:** none; blocks 1.5b
- **Goal:** Before 1.5b swaps in current text, two questions have cited answers. First, for each of five canons, whether it was amended after the vendored vatican.va text, and if so the current text and the amending act, so 1.5b loads current law (rule F) instead of guessing. Second, for each canon that the English Code prints in Latin, whether an English text published by the Holy See exists, so 1.5b can show it labelled unofficial or apply rule E.
- **Current state:**
  - Decision log "Canon law amendments": current text comes from iuscangreg.it (the Pontifical Gregorian University canon law faculty's amendment register, not a Vatican site), checked against the amending documents on vatican.va, verified per canon.
  - Canon 295 is pre-2023 in the vendored source itself (plan, "Corrections to the handoff doc", confirmed on 28 Sep), so no parser fix can produce the current text.
  - Live text read on 29 Sep: canon 296 begins "Lay persons can dedicate themselves to the apostolic works of a personal prelature by agreements..."; canon 360 names "the Secretariat of State or the Papal Secretariat, the Council for the Public Affairs of the Church, congregations..."; canon 361 refers to "the Secretariat of State, the Council for the Public Affairs of the Church, and other institutes of the Roman Curia"; canon 948 reads "Separate Masses are to be applied for the intentions of those for whom a single offering, although small, has been given and accepted." None carries the source's "n" amendment marker in live text.
  - Latin in the English Code, live: 111, 579 and 700 in full; 112 in full (glued to 111 today, split out by 1.5a); 535 §2, 695 §1 and 868 §1 2° only (695 §2 is English in the source; R2 checked the vendored page). The plan's rule is that 111, 112, 535 and 868 show the L'Osservatore Romano English, labelled unofficial, with the Latin as the official text. For the others, rule E applies if no English exists.
- **Changes (deliverables):** one file, `docs/research/R2-canons.md`, with two parts.
  - Part 1, amendments. Per canon 295, 296, 360, 361 and 948:
    - Whether iuscangreg.it lists an amendment, with the amending act's name, date and vatican.va URL.
    - The current text per iuscangreg.it and the amended Latin text from the act.
    - The English text if the Holy See published one (official, or L'Osservatore Romano), otherwise "no English published", and whether only Latin or Italian exists on vatican.va.
    - Whether the vendored `sources/canon-law/` page already has the new text, which file, and how it differs.
    - The treatment 1.5b should apply under rules F and E.
  - Part 2, English for the Latin canons. Per canon 111, 112, 535 (§2), 579, 695, 700 and 868 (§1 2°):
    - The English source found (L'Osservatore Romano English edition issue and page, a vatican.va English page, or none), with URL or scan reference.
    - Its status for the reader label: official English, or unofficial English with the Latin official.
    - Where none exists, "rule E: Latin kept in the reader, out of search".
- **Acceptance checks:**
  - Part 1: five entries, each with at least two sources (iuscangreg.it and the vatican.va act) or an explicit "no amendment found in either", and a stated reason when one source is missing.
  - Part 2: seven entries, each with its source or an explicit "none found" and the places searched.
  - Any English text quoted is the Holy See's own, never our translation (Decision log "Rights review": TheoCorpus makes no translations).
  - Carter closes the issue.
- **Production safety:** Research only.
- **Needs Carter:** Approve the English sources found in part 2, and close the issue. A canon with no English follows rule E as decided.
- **Out of scope:** Canons outside the two lists, unless the check finds a new amendment; list any such finding for Carter rather than fixing it. The parser fixes (1.5a). The Eastern code.

---

### R3. Esther: what the WEB-C text contains and how it maps to the Nova Vulgata

- **Type:** research. This entry is the only spec for R3; the P1a file points here.
- **Depends on:** none; blocks 1.4a
- **Goal:** Before 1.4a restores the missing Esther verses, settle exactly which text is in the source, where each Greek addition sits, which verses are missing, and how the additions should be numbered and labelled in a Catholic reader, so 1.4a restores the right text with references that match Church documents.
- **Current state:**
  - Plan claims Esther 4:18-47 and 10:4-14 are missing, among 245 missing verses (244 in the current build).
  - Verified 29 Sep: the vendored `sources/bible/eng-web-c_usfm/43-ESGeng-web-c.usfm` ("Esther (Greek)") has 205 verses in 10 chapters, with 22, 23, 15, 46, 14, 14, 10, 17, 30 and 14 verse markers. Chapter 4's 46 markers run up to 47 and chapter 9's 30 markers run up to 32. The gaps are 4:6, 9:5 and 9:30, never marked: Hebrew verses the Greek lacks, present in the Nova Vulgata (R3 findings, section 1). No verses are combined. Live Esther (26 passages) has references "Esther 4:1–3", "Esther 4:4–17", "Esther 9:1–10", "Esther 9:11–17", "Esther 9:18–32", "Esther 10:1–3". So 4:18-47 and 10:4-14 are absent from live, as claimed. The KJV pericope file skips them, which accounts for 41 of the 244 missing verses.
  - The file's introduction says the 5 additions are merged "as extensions at the beginning of 1:1 and after 3:13, 4:17, 8:12, and 10:3". The file does not do that for all of them:
    - Addition A is inside 1:1, in brackets.
    - Addition B follows 3:13 inside the same verse.
    - Addition C is numbered as new verses 4:18 to 4:47.
    - Addition E is inside verse 8:13 (USFM line 226), not after 8:12.
    - Addition F is numbered 10:4 to 10:14.
  - The introduction counts 5 additions. The standard count is 6, A to F. Addition D (Esther before the king) is 5:1-2 (USFM lines 145-149), not bracketed; the introduction counts C and D as one (verified by R3).
  - Other Catholic editions number the additions with lettered verses (for example 4:17a to 4:17z) or as chapters 11 to 16. Verified by R3: the Nova Vulgata uses lettered verses (1:1a-k, 3:13a-h, 4:8a, 4:17a-kk, 5:2a-p, 8:12a-cc, 10:3a-k) (also 3:15a-i and 9:19a, Old Latin with no Greek counterpart) over an Old Latin text form; the Catechism cites "Esth 4:17b" and the Italian Lectionary "Est 4,17k-u", both in the Septuagint's lettering; the English Lectionary cites "Esther C:12, 14-16, 23-25" (NAB letter chapters). The Decision log adopts Nova Vulgata numbering for the Bible (Esther additions excepted; see Decision log, R3).
- **Changes (deliverables):** one file, `docs/research/R3-esther.md`, with:
  - The full verse inventory of `43-ESGeng-web-c.usfm` per chapter, including combined or skipped verse numbers, produced by a script.
  - For each addition A to F, its WEB-C verse range and its Nova Vulgata range, with the Nova Vulgata page on vatican.va cited.
  - Whether any Greek text in WEB-C has no counterpart in the Nova Vulgata, or the reverse, and whether any Hebrew-Esther-only content is duplicated in the Greek book.
  - The list of live Esther verses missing (should reproduce 4:18-47 and 10:4-14 or correct them).
  - How the Catechism and the Lectionary cite Esther's additions, with 2 or 3 examples.
  - A recommendation for 1.4a: keep WEB-C numbers with a Nova Vulgata alias in metadata, or renumber. If renumbering changes which text an existing anchor names, say which anchors need new names and redirects (D1).
  - Which of the plan's Esther claims (the handoff doc's list) hold.
- **Acceptance checks:** The inventory is produced by a script whose output is pasted, not by hand. Every claim cites the USFM line or a Nova Vulgata page on vatican.va. Every claim in the plan's Bible row about Esther is either confirmed or corrected with the evidence. Carter closes the issue.
- **Production safety:** Research only.
- **Needs Carter:** The numbering recommendation, and the choice itself if no Church source settles it.
- **Out of scope:** Daniel's additions, which already follow Nova Vulgata-compatible numbering in WEB-C (3:24 to 90, chapters 13 and 14) and are handled in 1.4a. Pericope chunking.

---

### R4. Are the Refutation's book contents authorial?

- **Type:** research
- **Depends on:** none; blocks 1.8a
- **Goal:** Decide whether the "Contents" summaries at the head of books of the Refutation of All Heresies were written by the author (keep, rule G does not apply) or added by the translator or editor (remove under rule G), so PR 1.8a strips only editorial material.
- **Current state:**
  - Live document "The Refutation of All Heresies." (author "Hippolytus.") has 377 passages, 8 of them contents-like, with chapter labels "Book I · Contents", "Book V · Contents", "Book VI · Contents", "Book VII · Contents", "Book VIII · Contents", "Book IX · Contents", "Book X · Contents" (read-only query, 29 Sep). Book I's contents div is long enough to be two passages (anchors `.../book-i/contents/p1` and `/p2`), so 7 divs give 8 passages; Book IV has none because the start of that book is lost (R4 memo, 4 Oct). The source is ANF05 (`sources/church-fathers/third-century-2.xml`, per the vendor manifest file names).
  - Plan, "Labels for works that stay": check whether the book contents are authorial before removing them under rule G.
- **Changes (deliverables):** `docs/research/R4-refutation-contents.md` with:
  - What the Greek manuscript tradition contains at the head of each book, from the critical edition's introduction (Marcovich, PTS 25, 1986) or Litwa (2016), and what the ANF translator (J. H. MacMahon) says about them in the vendored volume's own notes.
  - For each of the 8 live passages, a verdict (authorial, translator-added, or mixed) with the source.
  - The exact rule for 1.8a (keep all, remove all, or remove named paragraphs), expressed as ThML div ids from the vendored file.
- **Acceptance checks:** Each verdict cites a critical edition or the translator's own statement; if neither is reachable, the entry says so and recommends the conservative outcome under rule G's "text that is only mislabeled stays with its label fixed".
- **Production safety:** Research only.
- **Needs Carter:** Only if the sources conflict.
- **Out of scope:** The Refutation's authorship label (3.2) and any rule A question about Hippolytus (R1).

---

### R5. Trace the On Loving God translator

- **Type:** research
- **Depends on:** none; blocks 1.9
- **Goal:** Identify the translation of Bernard's On Loving God in the vendored file, so the reader can credit it correctly, or confirm that the trace fails and 1.9 swaps to a verified public-domain translation (Decision log "On Loving God translation").
- **Current state:**
  - Vendored `sources/medieval/on-loving-god.xml` (sha256 `b26350f4...d92`, 109,926 bytes, from `https://ccel.org/ccel/b/bernard/loving_god.xml`). Its ThML head has empty `firstPublished`, `pubHistory`, `published` and `editorialComments`. The only provenance line is a paragraph stating the text was made available by Paul Halsall (Fordham address). Its generalInfo description is a CCEL staff blurb (never shown or indexed, Decision log "CCEL staff descriptions").
  - The file has a "Title Page", a "DEDICATION" and chapters whose titles begin "Chapter I. Why we should love God and the measure of that love". The plan states it is not Patmore's 1884 translation because the chapter titles differ.
  - Live document "On Loving God", 28 passages.
- **Changes (deliverables):** `docs/research/R5-on-loving-god.md` with:
  - Comparison of the vendored chapter titles and three opening sentences against candidate translations available in public domain (for example the Internet Medieval Sourcebook page's stated source, Marianne Caroline and Coventry Patmore 1881 or 1884, Edmund Gardner's 1916 edition, and the Cistercian "Terence Connolly 1937" line of editions), with the edition that matches or "no match".
  - If identified, the edition's bibliographic record and the rights inventory entry to add in 0.2's format. If Connolly (1937) or another post-1930 edition, the renewal-search requirement.
  - If not identified, the replacement translation recommended for 1.9 and its source file.
- **Acceptance checks:** Matching is shown with side-by-side chapter titles; any conclusion names at least one bibliographic source (library catalogue or scan).
- **Production safety:** Research only.
- **Needs Carter:** Approve the replacement if the trace fails.
- **Out of scope:** Other medieval works' translators (Boethius is already identified as Cooper 1902).

---

### R6. Edition and provenance check for each planned source

- **Type:** research
- **Depends on:** 0.2 (the inventory format). Blocks 1.2c (Percival), 1.2d (Schaff), 1.8d (Robertson) and every 5.x addition; each work's part blocks the PR that ingests it. Schroeder's row also supplies the renewal search that 1.2e needs through 0.2.
- **Goal:** Before any new or replacement source is ingested, confirm that the file we would vendor is the edition the Decision log names, that it is public domain on a recorded basis, and that it is clean text or which OCR route it takes. This keeps a Peers translation or a 1932 Tanquerey from entering by accident.
- **Current state:**
  - Decision log fixes the editions: David Lewis and pre-1931 Stanbrook for John of the Cross and Teresa (no Peers); Lewis 1864 for the Spiritual Canticle, not CCEL's 1995 modernization; Gutenberg 13871 for Brother Lawrence, not 5657; a 1930 printing of Tanquerey; Robertson's NPNF On the Incarnation (npnf204); Percival for councils 1 to 7, Schroeder 1937 for 8 to 18, Schaff 1877 for Vatican I; Pascal's Pensées in Trotter 1910.
  - `docs/research/2026-09-28-scan-only-works-text-sources.md`: of 48 scan-only works, clean text for 19 (4 flagged), partial for 6, OCR only for 23. ecatholic2000.com claims copyright on its pages (use only to check our OCR or with permission, Decision log "OCR and scanned works").
  - The candidates memo lists 27 CCEL ThML works (A1) and 58 Gutenberg or Internet Archive works (A2).
  - Schroeder 1937 is after 1930, so its public-domain status needs a renewal search under the Decision log's non-renewal rule. R6 ran it on 5 Oct 2026 (NYPL's transcription of the renewal records, complete for 1964 and 1965): no renewal found; recorded in the 11 Schroeder rows for Carter's approval.
  - Downloads (5 Oct 2026): the 154 text, XML and HTML files of the download list are approved and vendored to `datapipeline/sources/_incoming/<Vendored as path>`, which no adapter reads, and locked in `source_lock.json` with their download date and URL; the 91 PDFs and the hOCR file are approved per work later and go to the same place. 152 files, 151,731,711 bytes, each matching the list's size; 2 archive.org texts for 5.6c (`theologians/exercisessaintg00gertgoog/exercisessaintg00gertgoog_djvu.txt`, `theologians/bwb_W9-CTR-079/bwb_W9-CTR-079_djvu.txt`) returned HTTP 500 and are not vendored. Each ingesting item's spec has a "Source files" line saying the PR moves its files unchanged to the final path (Decision log "Holding folder for approved downloads").
  - Findings: `docs/research/R6-editions.md` (230 planned rows covering every work in 1.2c, 1.2d, 1.2e, 1.8d and 5.3 to 5.6c; download list of 246 files, 2.01 GB).
- **Changes (deliverables):** One row per planned work in `datapipeline/rights_inventory.json` (0.2 format, with `planned_for` set to the ingesting item and `source_path` set to where the file will be vendored; Carter's choice, 4 Oct 2026) plus `docs/research/R6-editions.md` with, per work:
  - Title page facts from the actual file or scan: translator, publisher, place, year, printing.
  - Match against the Decision log edition, or the mismatch.
  - Public-domain basis and, for 1927 to 1963 US publications, the renewal search record.
  - Text route: clean ThML, clean text, partial, or OCR, with the file URL and its sha256 once downloaded (downloading requires Carter's approval per file set).
  - Flags from the scan-only memo resolved (Spiritual Combat Rivingtons 1875 compared with a Catholic edition; Little Flowers Hudleston revision; Summa contra Gentiles Aquinas Institute edition licence; Catherine of Genoa 1907 printing).
  - Order of work: first the P1 replacements (Robertson npnf204, Percival, Schroeder 1937, Schaff 1877) because 1.2 needs them; then the P5 works in the order the phase plan adds them (5.3 Roman Curia, 5.4, 5.5, 5.6a, 5.6b, then 5.6c per work starting with John of the Cross and Teresa).
- **Acceptance checks:** No planned work reaches an ingestion PR without a complete inventory row and a verdict "edition matches"; each row's evidence can be re-checked from the cited scan page or file.
- **Production safety:** Research only; downloads go to local disk.
- **Needs Carter:**
  - Approve downloads (each source set, with file names and sizes stated).
  - Run or approve the renewal searches that the private rights memos depend on.
  - Handle any correspondence with rights holders (Decision log "Rights review").
- **Out of scope:** The OCR clean-up tool and gate (1.2f) and its per-work use (1.2e, 5.6c), adapter code, licensed works (Decision log "Licences": no spending).
