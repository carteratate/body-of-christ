# P0: checks, provenance, identity, safety, and research

1. Phase 0 builds the guard rails every later corpus change is measured against. It changes no live data.
2. First CI and a PR template (0.0), so each later PR shows green source-free tests and a pasted local source-check report.
3. Then the publish lock (0.4), which must merge before any Phase 1 adapter PR. Today a routine `run_collection.py` run would cascade-delete saved user rows.
4. Then the source checks: coverage and sequence tests (0.1a), health rules (0.1b), and the release report with its old-to-new remap (0.1c).
5. Then provenance: a tracked hash lock for every vendored file plus a public-facts rights inventory (0.2).
6. Then identity: the work registry that freezes today's 421 document IDs and moves anchors to source structure (2.1). Its PR is the first real user of the 0.1c remap.
7. Then the baseline eval (0.3), run once against the live corpus before anything is republished, and the Qdrant limits read (0.5) and storage snapshot (0.6), both read-only ops.
8. Research items R1 to R6 need no code and can start on day one in parallel. Each blocks one later PR, named in its entry.
9. Recommended merge order: 0.0, 0.4, 0.1b, 0.1a, 0.1c, 0.2, 2.1, 0.3. Ops 0.5 and 0.6 any time before P4. R1 to R6 in parallel.
10. Evidence below was gathered on 29 Sep 2026 from master at `5475c49`, a fresh clone in a scratch directory, the vendored sources, and read-only SELECTs against Supabase project hvmgffvimqgiejmxwhwq.

Conventions used in this file:

- Paths are relative to the repo root of `body-of-christ` unless they start with `/`.
- "Live" means the production Supabase project hvmgffvimqgiejmxwhwq and the production Qdrant cluster.
- "Master build" means running every adapter in `datapipeline/publication.py` `SOURCE_ADAPTERS` on master against the vendored sources, touching no store.
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
  - `apps/web/package.json:5-7` declares `node >=20`. The Node major Vercel builds with is **not verified**.
  - The API Docker image uses `python:3.11-slim` (`services/api/Dockerfile:1`). The datapipeline has no pinned Python.
- **Changes:**
  - Add `.github/workflows/ci.yml`, triggered on `pull_request` and on `push` to `master`, with three parallel jobs and `permissions: contents: read`. No secrets are used by any job.
    - `web`: `actions/setup-node` with Node 20 (or the Vercel project's major, if Carter confirms a different one), `npm ci` in `apps/web`, then `npm run lint`, `npx tsc --noEmit`, `npx vitest run`. Cache `~/.npm` keyed on `apps/web/package-lock.json`. Do not run `next build` in CI; Vercel already builds every PR preview, and the build may need public env vars.
    - `api`: `actions/setup-python` 3.11, `pip install -e "services/api[dev]"`, then `python -m pytest -q` in `services/api`. Do not add ruff or a Docker build in this PR.
    - `datapipeline`: `actions/setup-python` 3.11, `pip install -r datapipeline/requirements.txt`, then `python -m pytest -q -m "not smoke"` in `datapipeline`. Cache the tiktoken directory (`TIKTOKEN_CACHE_DIR` set to a workspace path) keyed on `requirements.txt`.
  - Fix the order dependence at its cause. Add a `pytest_configure` hook to `datapipeline/tests/conftest.py` that calls `os.environ.setdefault` for `DATABASE_URL`, `OPENAI_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY` and `ANTHROPIC_API_KEY` with obviously fake values, mirroring `services/api/tests/conftest.py`. Leave the per-module `setdefault` lines alone (they become redundant but harmless). Note that `load_dotenv()` at `config.py:15` does not override variables that are already set, so on Carter's Mac the real `.env` values still win only for variables the conftest does not set first. Because `setdefault` never overwrites an existing value, a developer who exports real keys in their shell keeps them.
  - Mark the 10 source-dependent tests. Add a `sources` marker to `datapipeline/pytest.ini`, and in each of the three files add `pytestmark = pytest.mark.skipif(not <path>.exists(), reason="<collection> sources not vendored")` using the same pattern as `tests/test_medieval.py:12`. Paths are `sources/catechism/ccc.json`, `sources/church-fathers/` (the five tests read `apostolic fathers.xml`, `city-of-god.xml`, `confessions.xml`), and `sources/summa/summa.xml`.
  - Fix `httpx2`. First, in a fresh virtualenv run `pip install -e "services/api[dev]"` and `python -c "import httpx2"`. If it imports (arrives through `anthropic==1.2.0`), add `"httpx2"` to the `dev` extra anyway so the test's direct import is declared. If it does not import, add it to `dev` with a lower bound matching the version pip resolves. Do not change `test_hyde_steps.py` itself; its point is to exercise the real SDK transport.
  - Fix the `tsc` error in `apps/web/src/lib/preference-writer.test.ts:7-15` by typing the helper's parameter as the existing quota type from `src/lib/search-draft.ts` (`SearchQuota`) instead of `number`. Test-only change.
  - Add `.github/pull_request_template.md` with these sections, in this order:
    - "What changed and why" (free text).
    - "Production safety" checklist: no migration, or migration is additive and nullable or defaulted; API tolerates the change being absent; no datapipeline run against live stores; no Qdrant change.
    - "Source checks (run locally)", required whenever the diff touches `datapipeline/`. It holds the output of `python3 scripts/vendor_sources.py --collection all --verify` (from 0.2 on, `python3 scripts/source_lock.py --verify`), the coverage and sequence summary (0.1a), the health summary (0.1b), and the release report summary (0.1c), each pasted in a collapsed `<details>` block. The section states "Not applicable: this PR does not touch datapipeline/" when that is true.
    - "About page" checkbox: "This PR changes an inclusion rule or what a collection holds; the About page item is updated or ticketed" (from the Decision log row "About page").
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
- **Goal:** Nobody can write to the live reader store or search index during Phases 0 to 3, by accident or by routine repair. Adapter fixes will change passage IDs, and a piecemeal publish would delete users' saved history rows through foreign-key cascades. After this PR, the only path to a production write is a reviewed code change that names a cutover release, plus a matching CLI flag, which the 4.1b runbook will do.
- **Current state:**
  - `datapipeline/run_collection.py:62-86` builds a `PublicationRequest` and calls `production_runner().publish(...)` with no lock. `publication.py:121-187` prunes reader passages (`reader.write(..., prune=True)`), reader documents (`prune_documents`), and Qdrant points (`search.prune`) on every unlimited run.
  - The only safety nets are `_validate_build` (`publication.py:224-248`), which refuses more than 10% shrink or more than 10% identity churn per collection, and the exact-name confirmation for `--wipe-reader` (`publication.py:204-211`). A change that replaces 9% of a collection's IDs passes both.
  - Live foreign keys, read from `information_schema` on 29 Sep: `retrievals.chunk_id`, `bookmarks.chunk_id`, `retrieval_labels.chunk_id`, `guest_trial_retrievals.chunk_id` all `ON DELETE CASCADE` to `chunks`; `reading_progress.document_id` and `document_chapters.document_id` cascade from `documents`; `product_feedback` uses `SET NULL`.
  - Measured risk today: live user tables reference 1,685 distinct passage IDs (retrievals, bookmarks, guest_trial_retrievals, retrieval_labels). A master build emits 54,776 passage IDs; 12 of the 1,685 are not among them (in apostolic-exhortations, catechism, encyclicals, medieval). Publishing those collections from master today would cascade-delete 19 `retrievals` rows and 2 `guest_trial_retrievals` rows, with no refusal, because each collection's churn is under 10%.
  - Other entry points that write live stores:
    - `scripts/backfill_missing_vectors.py`, `scripts/reembed_drifted_vectors.py`, `scripts/reconcile_qdrant_payloads.py`, each gated only by `--apply` (dry run by default).
    - `pipeline.py` (V5 stage engine), whose `reader`, `embed` and `bm25-index` stages obtain `asyncpg` pools or the Qdrant client at `pipeline.py:156-167`. `stages/embed.py` and `stages/bm25_index.py` contain write calls. Whether `stages/enrich_io.py` writes to Postgres or only reads is **not verified**.
- **Changes:**
  - Add a tracked file `datapipeline/PUBLISH_LOCK.json`:
    ```json
    {
      "locked": true,
      "since": "2026-09-29",
      "reason": "Corpus cleanup. No live writes until the P4 cutover. See docs/2026-09-28-corpus-cleanup-plan.md.",
      "cutover_release": null
    }
    ```
  - Add `datapipeline/publish_lock.py` with:
    - `class PublishLocked(ValueError)` (a `ValueError` so `run_collection.main` reports it through `parser.error`, exit code 2, like other refusals).
    - `def load_lock(path: Path = DEFAULT_PATH) -> PublishLock` returning a frozen dataclass `(locked: bool, reason: str, cutover_release: str | None)`. A missing or unparsable file counts as locked (fail closed).
    - `def assert_live_write_allowed(action: str, cutover: str | None, lock: PublishLock | None = None) -> None`. When `lock.locked` is true, it passes only if `cutover` is a non-empty string equal to `lock.cutover_release`. Otherwise it raises `PublishLocked` with the action, the lock reason, and how to unlock (set `cutover_release` in a reviewed PR and pass `--cutover <same value>`).
  - `publication.py`: add an optional `write_guard: Callable[[PublicationRequest], None] | None` parameter to `CollectionPublicationRunner.__init__`, called at the top of `publish` right after `_validate_request` and before any source adapter runs or store is acquired. `production_runner()` passes a guard that calls `assert_live_write_allowed(f"publish {collection} to {target}", request.cutover)`. Add `cutover: str | None = None` to `PublicationRequest`. Test fakes construct the runner without a guard, so existing tests keep their meaning.
  - `run_collection.py`: add `--cutover RELEASE_ID` (passed into the request) and `--dry-run`. Dry run builds the documents, runs `_validate_documents` (and from 0.1b the health rules), prints collection, document count, passage count, and never acquires a store. Dry run is allowed while locked. It is the command 0.1c and every P1 PR use.
  - The three repair scripts: at the start of the `--apply` branch, call `assert_live_write_allowed(f"<script> --apply", args.cutover)` and add a `--cutover` argument. Dry runs stay allowed.
  - `pipeline.py`: in `_main`, after `resolve_stages`, if any resolved stage is in `{"reader", "embed", "bm25-index"}` and neither `--dry-run` nor `--status` is set, call the guard with a `--cutover` argument. Before merging, read `stages/enrich_io.py` and add `"enrich"` to the set if it writes to Postgres or Qdrant.
  - Update `datapipeline/README.md` (sections "Publish one collection" and "Narrow repair commands") and `datapipeline/SOURCES.md` ("Publishing a collection") with one paragraph each on the lock, the dry run, and who unlocks it. Update the repo `CLAUDE.md` Quick Commands comment for the datapipeline to show `--dry-run`.
- **Acceptance checks:**
  - `tests/test_publish_lock.py`:
    - `test_missing_lock_file_counts_as_locked`
    - `test_unparsable_lock_file_counts_as_locked`
    - `test_locked_refuses_without_cutover`
    - `test_locked_refuses_wrong_cutover`
    - `test_locked_refuses_when_cutover_release_is_null_even_with_flag` (the state this PR ships)
    - `test_matching_cutover_passes_only_when_file_names_it`
    - `test_unlocked_file_allows_writes`
  - `tests/test_collection_publication.py::test_write_guard_runs_before_adapters_and_store_acquisition`: a guard that raises must leave the fake adapter uncalled and no store acquired.
  - `tests/test_run_collection.py::test_dry_run_acquires_no_store_and_prints_counts` and `::test_live_publish_is_refused_while_locked` (uses the real `production_runner` guard with a temp lock file, and asserts exit code 2 and the word "locked" on stderr without any network call).
  - One test per repair script, `test_apply_is_refused_while_locked`, and one for `pipeline.py`, `test_reader_stage_is_refused_while_locked`.
  - Manual check pasted into the PR: `python3 run_collection.py --collection catechism --target both` exits 2 with the lock message, and `python3 run_collection.py --collection catechism --dry-run` prints about 809 passages.
  - The shipped `PUBLISH_LOCK.json` has `"locked": true` and `"cutover_release": null` (asserted by `test_repository_ships_locked`).
- **Production safety:** Adds refusals only; removes no capability that Phase 0 to 3 is allowed to use. API and web are untouched. Nothing runs against live stores.
- **Needs Carter:** Approve the PR. Agree that from merge until the 4.1b cutover PR, emergency repairs to live data also go through a reviewed PR that sets `cutover_release` (there is no environment-variable bypass by design).
- **Out of scope:** Any change to pruning or churn thresholds. Remap tooling (0.1c, 4.1a). Qdrant alias work (2.2b). Removing the V5 `stages/` engine.

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
    - Bible: 245 verses missing against WEB-C, including Daniel 3:24-90 region, Daniel 13 and 14, Esther 4:18-47 and 10:4-14. Verified for Esther on 29 Sep: `sources/bible/eng-web-c_usfm/43-ESGeng-web-c.usfm` has chapter 4 verse markers up to 47 and chapter 10 up to 14, while live Esther passages stop at "Esther 4:4–17" and "Esther 10:1–3".
    - Canon law: 266 and 1330 missing; 112, 238, 689, 1308 (new), 1310 (new) glued into the previous canon.
    - Summa: Part I questions 71 and 72 missing.
    - Ignatius letters: pre-chapter greeting paragraphs skipped (plan cites line 9621 of `sources/church-fathers/apostolic fathers.xml`).
    - Papal: Roman-numeral prose dropped (In Dominico Agro 224 characters, Annus Qui Hunc 2,277).
  - Master build counts (29 Sep, scratch clone): 54,776 passages in 382 plus 39 documents across 10 collections, matching the audit.
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

---

### 0.1b. Health rules

- **Type:** PR
- **Depends on:** 0.4
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
  - Wire block rules into `CollectionPublicationRunner._validate_documents` (`publication.py:213`), raising `ValueError("REFUSING: ...")` listing the first 10 violations, before any store is acquired. Because the master build has 0 blanks, 0 anchor duplicates and 0 position errors, only `H2_debris` (1 Summa passage) would trip. Handle that one explicitly: `H2` starts as a report rule and flips to block in PR 1.7 (Summa), with a `known_defects.json` entry.
  - Add `python3 -m checks.health --collection all|<name> [--out <dir>]`, which builds documents and writes `health.json` plus a `health.md` table (rule by collection, counts, first 5 anchors each). Also `--from-snapshot <path>` to run the same rules on the live snapshot exported in 0.1c, so reports can show live against build.
- **Acceptance checks:**
  - `tests/test_health.py` in CI with synthetic documents: one test per rule id asserting it fires on a crafted bad passage and stays silent on a crafted good one, `test_bible_and_canon_short_passages_are_allowed`, and `test_block_rule_refuses_before_store_acquisition` using the runner with fakes.
  - Locally, `python3 -m checks.health --collection all` on master prints the counts listed under Current state (blank 0, debris 1, footer 12/4/1/1, short 7/11); the PR description pastes them next to the live counts.
  - `python3 run_collection.py --collection summa --dry-run` still succeeds on master (H2 is report-only for now).
- **Production safety:** Adds refusals to a runner that is already locked by 0.4; no store is touched; no API or web change.
- **Needs Carter:** Nothing.
- **Out of scope:** Fixing the violations. Removing the 21 live blank rows (that happens at the P4 republish). Language detection beyond the function-word heuristic.

---

### 0.1c. Release report with remap-based ID diff

- **Type:** PR
- **Depends on:** 0.4, 0.1b (reuses its health output); ideally 0.1a
- **Goal:** One command that tells a reviewer exactly what a build would change compared with what users see today. It maps every live passage to its successor in the new build (same passage, moved, merged, split, or removed), counts the saved user rows that each outcome affects, and summarizes coverage and health. Every P1 PR attaches this report. The same remap is what 4.1a later uses to move bookmarks and history, so building it now tests it months before cutover.
- **Current state:**
  - Passage ID is `uuid5(DOCUMENT_NS, f"{document_id}#{anchor}")` (`datapipeline/identity.py:40-43`); document ID is `uuid5` of slugified work-key parts (`identity.py:24-27`), for example `document_id(collection, author, title)` for ThML works (`ingest/thml_doc.py:89`) and `document_id("bible", translation, name)` for Bible books (`ingest/bible.py:557`). Any relabel of author, title, or anchor text changes IDs.
  - No remap exists. `reconcile.py` compares Qdrant payloads with Postgres for existing IDs only.
  - Live versus master build, 29 Sep: live 54,568 passages, build 54,776. The audit measured 373 build IDs missing from live, 163 live IDs not in the build, and 2,439 content differences under equal IDs. All 421 live document IDs are reproduced exactly by the master build (md5 of the sorted ID list `851d07063f85e4c612be1b2d44b695fb` on both sides).
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
    - Matching, per document, in this order, each old passage taken at most once as primary:
      1. `same_id`: identical passage ID.
      2. `same_text`: identical normalized content hash in the same successor document (anchor changed).
      3. `contained`: old normalized text is at least 90% contained in one new passage (merge or growth), measured on 8-word shingles.
      4. `split`: old text is at least 90% covered by the union of 2 or more consecutive new passages; the primary successor is the one holding the old passage's first shingle.
      5. `similar`: best 8-word-shingle Jaccard of at least 0.5 against one new passage.
      6. `removed`: none of the above.
    - Successor document: same document ID; else, once 2.1 lands, the registry's `supersedes` mapping; else none.
    - `RemapResult` rows: `old_id, outcome, new_ids (primary first), score, old_anchor, new_anchor, old_chapter_key, new_chapter_key`. Serialize as `remap.jsonl` plus `chapter_remap.jsonl` (old to new `chapter_key` per document, by majority of passages).
    - Pure functions over in-memory data; no database access.
  - `datapipeline/release/report.py`, CLI: `python3 -m release.report --snapshot releases/snapshots/<date> --collection all|<name> [--out <dir>]`. Builds the collection with `SOURCE_ADAPTERS`, runs remap, 0.1b health and, if present, 0.1a checks, and writes to `<out>` (default `datapipeline/releases/local/report-<collection>-<timestamp>/`, gitignored) the files `remap.jsonl`, `chapter_remap.jsonl`, `report.json`, `report.md`. `report.md` sections:
    - Totals per collection: documents, passages, characters, live against build.
    - Outcomes per collection: `same_id`, `same_text`, `contained`, `split`, `similar`, `removed`, and `new` (build passages that are no old passage's successor).
    - User impact: for `removed` and for every outcome whose primary ID differs from the old ID, the sum of `retrievals`, `bookmarks`, `guest_trial_retrievals`, `retrieval_labels` rows, and the `reading_progress` rows whose anchor or chapter key changes.
    - Up to 30 sample rows per non-trivial outcome (IDs, references, anchors; content excerpts only in the local file, never pasted into a public PR).
    - Health and coverage summaries.
  - `report.md` is written to be pasted as the "release report" block of the PR template with excerpts removed.
- **Acceptance checks:**
  - `tests/test_remap.py` in CI with synthetic passages: one test per outcome, `test_each_old_passage_has_exactly_one_outcome`, `test_split_primary_is_first_piece`, `test_new_passages_are_reported`, `test_cross_document_match_is_not_attempted_without_registry`, and `test_remap_is_deterministic` (same input, byte-identical `remap.jsonl`).
  - `tests/test_release_report.py` in CI: user-impact sums on a synthetic `references.json`; the Markdown contains no passage content when `--public` (default) is set.
  - Locally, the report for all collections from master against a fresh snapshot reproduces the audit: live 54,568, build 54,776, `same_id` about 54,405 (54,568 minus 163), and user impact for the removed set equal to the 12 passages, 19 `retrievals` rows and 2 `guest_trial_retrievals` rows measured on 29 Sep (re-read at run time). The PR description pastes the public summary.
  - `export_live_snapshot.py` has a test that the SQL it issues is SELECT only, and that the session is set read only before the first query.
- **Production safety:** The export is a read-only transaction on live Supabase; everything else is local. Nothing is published (the lock stands). No API or web change.
- **Needs Carter:** Run, or approve running, `export_live_snapshot.py` against the production database (read only; it copies corpus text and anonymous reference counts to his Mac). The snapshot is refreshed before P4 and whenever a report needs current reference counts.
- **Out of scope:** Applying the remap to user tables and the merge policy for unique constraints (4.1a). Redirects and tombstones (2.2a, 2.4a). Qdrant.

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
  - Add a tracked `datapipeline/rights_inventory.json`, one entry per work (keyed by the 2.1 registry `work_id` once it exists; until then by `collection` plus source path plus title):
    ```json
    {"work": "...", "collection": "medieval", "source_path": "medieval/imitation-of-christ.xml",
     "edition": "Bruce, Milwaukee, 1940", "translator": "...", "first_published": 1940,
     "source_url": "https://ccel.org/...", "status": "pd-us-non-renewal",
     "renewal_search": {"date": "2026-..", "where": "...", "query": "...", "result": "no renewal found"},
     "credit_line": "Sourced via CCEL.org", "checked_by": "Carter", "checked_on": "2026-.."}
    ```
    `status` is one of `pd-us-pre-1931`, `pd-us-non-renewal`, `pd-us-government`, `permission`, `licence`, `unknown`. Only public facts go in this file; no reasoning, risk assessment, or correspondence (those stay in Carter's private memos, per the Decision log "Rights review"). The Imitation of Christ renewal search from Open items is the first entry to complete.
  - Record the four unregistered cases as `vendored-unregistered` with a `note` field: the two files scheduled for 5.4, `amoris-laetitia.html` with "not published, no decision", and `roman-curia/` with "parked for 5.3".
  - Update `datapipeline/SOURCES.md` (replace the "orphans" paragraph with a pointer to `source_lock.json`) and the PR template's source-check instructions.
- **Acceptance checks:**
  - `tests/test_source_lock.py` in CI with a temp directory: `--write` then `--verify` passes; a changed byte fails; a deleted file fails; an unlocked new file fails; entries are sorted and stable across two writes.
  - `tests/test_rights_inventory.py` in CI: every entry has the required fields and a known `status`; every `pd-us-non-renewal` entry has a complete `renewal_search`; every work emitted by a master build has an inventory entry (this part skips without sources).
  - Locally, `python3 scripts/source_lock.py --verify` exits 0 on Carter's Mac, and the PR description pastes its per-collection summary and the count of entries per `role`.
  - A check that a master build still reproduces the 421 live document IDs (hash `851d07063f85e4c612be1b2d44b695fb`), proving the hashed files are the ones in use.
- **Production safety:** Adds tracked metadata files and local scripts. No store, API or web change. File hashes and URLs of public sources are safe to publish.
- **Needs Carter:**
  - Confirm the field list of `rights_inventory.json` is safe for the public repo, and fill in or approve the renewal-search entries (he holds the private rights memos).
  - Decide what to do with `amoris-laetitia.html` (vendored, never published, no Decision log row). This spec only records it.
- **Out of scope:** Re-downloading any source. Adding the two 5.4 papal files to manifests or the database. Completing the rights inventory for planned sources (5.2 and R6). Storing source files in git.

---

### 2.1. Work registry with frozen IDs, structural anchors, and rule A fields

- **Type:** PR
- **Depends on:** 0.1c (its release report must show every live passage remapped), 0.2
- **Goal:** Document IDs stop depending on labels. Today's 421 document IDs are written into a tracked registry and adapters look them up, so fixing an author name, renaming "Song of Solomon", or moving Boethius to the Fathers keeps every reader URL. Anchors are rebuilt from the source's own structure instead of label text, so later label fixes stop changing passage IDs. The registry also holds the rule A fields (communion dates, chronology source, Church acts) that R1 fills and 3.1 enforces.
- **Current state:**
  - Document IDs derive from label text: `document_id(collection, author, title)` for every ThML work (`ingest/thml_doc.py:89`); `document_id("bible", translation, name)` (`ingest/bible.py:557`); `document_id("councils", council, council)` and `document_id("councils", "Second Vatican Council", title)` (`ingest/councils.py:88,153`); slug-based for encyclicals, exhortations and papal documents (`encyclicals.py:172`, `apostolic_exhortations.py:155`, `papal_documents.py:155`); constants for catechism, canon-law and summa.
  - A master build reproduces all 421 live document IDs exactly (verified 29 Sep by comparing md5 of the sorted lists). So freezing can be done by computing, not by copying from the database.
  - Planned relabels that would change IDs without a registry include 54 Fathers documents whose author ends in a period (plan, "Church Fathers and medieval"), "Song of Solomon" to "Song of Songs", and Boethius moving collection (Decision log: "Boethius's document ID stays frozen").
  - ThML anchors come from slugified chapter labels (`thml_doc.py:56-68`), with `--N` suffixes when labels repeat; Cur Deus Homo has 27 such anchors. ThML sources do carry structural ids: `sources/church-fathers/apostolic fathers.xml` has 931 `div1` to `div6` elements with an `id` attribute (for example `i`, `i.i`, `ii.i`). Other adapters already anchor on structure (`can/<n>`, `<book>/<chapter>/<verse>`, `<slug>/<n>`, `ccc/<n>`).
  - Live `documents` columns: `id, collection, title, author, year, metadata, created_at, translation, chunk_count` (29 Sep). `year` is empty for 202 of 421 documents and `author` for 109; `metadata ? 'document_type'` for 16. Unique constraint `(collection, title, translation, author)` from migration 0014.
  - `reading_progress` stores `chapter_key` and `anchor`; reader URLs carry `anchor` or `chapter`. Anchor changes therefore need the 0.1c chapter remap and the 2.4a redirects before cutover.
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
     }}
    ```
    `source_key` is structural: file plus ThML div `id` for ThML works; `bible/<USFM book code>` (for example `bible/DAG`); `<collection>/<manifest slug>` for HTML collections; the collection name for the three single-document collections. `status` is `active`, `removed` (kept for tombstones), or `moved`. `rule_a.church_acts` items are `{"issuer": "...", "date": "YYYY-MM-DD", "act": "...", "effect": "condemn|prohibit|warn|lift", "citation": "<url>"}`. `rule_a.decision` is `include`, `exclude`, or null until R1 fills it.
  - Add `datapipeline/registry/__init__.py` with `load_registry()`, `frozen_document_id(collection, source_key) -> str | None`, and `register_new_work(...)`. Adapters call `resolve_document_id(collection, source_key, fallback_parts)`: the frozen ID if the source key is registered, otherwise `identity.document_id(*fallback_parts)` (new works). A test forbids two source keys resolving to one ID.
  - Add `datapipeline/scripts/freeze_registry.py`, run once in this PR: build every collection on master adapters, pair each document's current ID with its structural source key (adapters expose it through `Document.metadata["source_key"]`, added in this PR), and write `works.json`. It refuses to write unless exactly 421 documents are produced and their sorted-ID md5 equals `851d07063f85e4c612be1b2d44b695fb` (or the hash of a fresh read-only query, if the live set has changed).
  - Change every adapter's `Document(id=...)` to `resolve_document_id(...)`. With the registry frozen, a master build still yields the same 421 IDs.
  - Structural anchors, per adapter:
    - ThML (`thml_doc.make_doc`): anchor is the chapter div's `id` (dots kept as `.`, which the anchor charset must then allow; or mapped to `-`, one rule applied everywhere), plus `/p<k>` for split parts. `chapter_key` is the same div id; `chapter_label` keeps its current text. No `--N` suffixes remain.
    - Summa: anchor from `part/question/article` numbers and the article part (objection, sed contra, corpus, reply) as the XML structures them, not from `a_title` (`ingest/summa.py:104`).
    - Catechism: unchanged where anchors are already `ccc/<first paragraph number>`; replace the `meta.get("path", str(pos))` fallback (`ingest/catechism.py:267`) with a structural path.
    - Bible, canon law, HTML numbered collections: already structural; unchanged in this PR.
    - Record the anchor scheme version in `Document.metadata["anchor_scheme"] = 2`.
  - Keep `identity.passage_id` unchanged (so IDs remain a pure function of document ID and anchor).
  - Because this PR changes most church-fathers, medieval and summa passage IDs, the release report (0.1c) is the evidence: the PR attaches it and shows every live passage in those collections with an outcome other than `removed`.
- **Acceptance checks:**
  - CI tests in `datapipeline/tests/test_registry.py`:
    - `test_registry_has_421_entries_and_unique_ids`
    - `test_registry_is_sorted_and_stable`
    - `test_frozen_id_wins_over_label_derived_id` (a relabeled synthetic work keeps its ID)
    - `test_unregistered_work_falls_back_to_identity_document_id`
    - `test_two_source_keys_cannot_share_an_id`
    - `test_rule_a_fields_validate` (dates ISO, `effect` in the allowed set, `citation` present for each act)
  - CI tests in `test_thml_doc.py`: `test_anchor_is_div_id` and `test_no_anchor_suffixes` on a synthetic ThML fixture with repeated labels.
  - Locally with sources: a master build with this PR produces the same 421 document IDs (md5 unchanged); `R8_anchor_suffix` from 0.1b reports 0; the 0.1c report against the current snapshot shows, for each collection, `removed` equal to the pre-PR report's `removed` (anchor changes alone must remap as `same_text`, `contained` or `split`), and user impact limited to ID changes with successors. The PR description pastes both reports' summaries side by side.
  - `checks.report` coverage and sequence numbers unchanged from the pre-PR run.
- **Production safety:** Nothing is published; the publish lock holds, so the anchor change reaches users only at the P4 cutover, with remap and redirects. No API or web change; `reading_progress` and shared URLs keep working against today's data until then.
- **Needs Carter:** Approve the anchor scheme change (it is the one-time passage-ID churn the Decision log "Document identity" accepts) and the character mapping for div ids.
- **Out of scope:** Filling `rule_a` (R1). Label, author or collection changes (P1, P3, P5). Adding registry columns to the database (2.2a). Applying the remap to live data (4.1a).

---

### 0.3. Baseline eval run

- **Type:** PR (runner changes and question file), then ops (a Carter-approved run)
- **Depends on:** 0.0; must run before any republish (P4)
- **Goal:** A measured "before" picture of search on today's live corpus, so 4.2 can show what the cleanup improved and what it cost users (removed works, changed rankings). It uses the existing 80-question set plus new targeted questions for the Vatican II recovery, the other repairs, and the removals. It never uses stored user queries.
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
    - Add `--no-judge`, which skips `judge.run` and records retrieval output only (the baseline is a single pipeline; judging happens in 4.2 when there is something to compare).
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
  - Output layout, all local and gitignored except the summaries: `docs/eval/baseline-2026-10/eval80.jsonl`, `targeted.jsonl`, artifacts directories, and a tracked `docs/eval/baseline-2026-10-summary.jsonl` holding per question the ranked `chunk_id`, `document_id`, `collection`, `reference`, and score (no passage text), plus `expect` hit@5 and hit@10 for targeted questions.
  - Add `services/api/scripts/baseline_summary.py`, which reads the two JSONL outputs and writes the tracked summary and a short `docs/eval/BASELINE-2026-10.md` (hit rates per group, collections covered, degraded-query count, total spend).
  - Ops run, on Carter's approval, from `services/api` with its `.env`:
    - `python scripts/run_eval_suite.py --pipelines hyde_cohere_luna --no-judge --top-k 10 --out ../../docs/eval/baseline-2026-10/eval80.jsonl`
    - `python scripts/run_eval_suite.py --pipelines hyde_cohere_luna --no-judge --top-k 10 --query-file ../../docs/eval/targeted-2026-10.jsonl --collections all --out ../../docs/eval/baseline-2026-10/targeted.jsonl` (the `--query-file` rows carry their own collections; `--collections all` only widens the default)
    - `python scripts/baseline_summary.py docs/eval/baseline-2026-10`
- **Acceptance checks:**
  - API tests in CI: `tests/test_run_eval_suite_cli.py::test_query_file_rows_validate` (fields, collections valid against `VALID_COLLECTIONS`, quota in 3, 4, 5, 10, focused rows have exactly one collection), `::test_top_entries_carry_chunk_and_document_ids` (with a stubbed `shared_runner`), `::test_no_judge_skips_judge_init_and_calls`, `::test_fingerprint_includes_corpus_fingerprint`.
  - A lint test that no targeted question string appears in a fixture of the `searches` query texts is not possible without exporting user data, so instead the PR description states how the questions were written and Carter reviews them.
  - After the ops run: 80 eval rows and about 30 targeted rows, all quality-eligible, or the ineligible ones listed; the summary file committed; `BASELINE-2026-10.md` shows, at minimum, that Nostra Aetate 4's continuation text is not retrievable today (expected hit 0) and which removed works appear in the top 10.
  - Total provider spend reported and under the ceiling Carter sets (estimate below).
- **Production safety:** The runner reads live Postgres and Qdrant and writes nothing to them (verified by grep above). It calls OpenAI, Cohere and, without `--no-judge`, Anthropic with eval questions only, as earlier rounds did. The script changes are in `services/api/scripts/`, which the Docker image does not copy (`COPY app/ app/` only, `services/api/Dockerfile:11`).
- **Needs Carter:**
  - Approve the targeted question list.
  - Approve the spend. Estimate about $3 for the 80 retrieval-only runs at round-3 rates (less after the Luna price cut) plus about $1.50 for the targeted set; judging is deferred to 4.2.
  - Confirm the run happens before any P4 activity and while the live corpus is unchanged (the corpus fingerprint records it).
- **Out of scope:** Judging, pipeline changes, retrieval tuning (a separate parent after the new baseline). Replaying stored user searches. The 4.2 comparison itself.

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
  - An estimate of the rebuilt corpus from the 0.1c report: build passage and character counts (master build today is 54,776 passages; the Vatican II and council repairs add roughly 0.9 MB of text), and, during cutover, old and new rows coexisting per the plan's release column (roughly double the `chunks` live data, about 100 MB more, before compaction).
- **Acceptance checks:** The recorded numbers, the limit, and the estimated peak during cutover, with the gap to the limit stated in MB.
- **Production safety:** Read-only catalogue queries.
- **Needs Carter:** Approve running the queries and read the plan limit from the dashboard.
- **Out of scope:** `VACUUM FULL`, buying Pro, branch rehearsals (4.0, 4.1a).

---

### R1. Rule A dating and Church-act check

- **Type:** research
- **Depends on:** none to start; results land in the 2.1 registry's `rule_a` fields; blocks 3.1
- **Goal:** For every author in the corpus and the planned candidates, establish the facts rule A needs, each with a citation, so that PR 3.1 removes exactly what the rules remove and nothing else. There are two parts. The Church-act check finds any formal act of the Holy See naming the author or a work (condemnation, prohibition, Index entry, monitum) and any later lifting. The dating part, only for authors whose communion changed while they were writing, places each work before or after baptism or reception, and before or after any break, from one named standard chronology.
- **Current state:**
  - The rules and the Decision log are settled; do not reopen them. Decided outcomes to record, not re-research: Origen, Novatian, Tatian, Arnobius, Alexander of Lycopolis out; Tertullian judged per work, with To His Wife (22 passages) and On the Apparel of Women (28) provisionally in; Loisy, Tyrrell, Teilhard, the Provincial Letters, Maxims of the Saints, Spiritual Guide and Augustinus out; Rosmini and Faustina in; Chesterton's Orthodoxy, Newman's Parochial and Plain Sermons and Edith Stein's pre-1922 works out; Newman's Development in the 1878 edition.
  - Named as unverified in the plan's Open items: Theologia Germanica on the Index; the exact form of Tyrrell's 1907 excommunication; the Pensées' Index status. The candidates memo (`docs/research/2026-09-28-theologians-spiritual-writers-candidates.md`, section 4) also leaves unconfirmed the Provincial Letters decree text, Erasmus's Index entries, and Ockham's reconciliation.
  - Sources already gathered for the patristic persons are in `docs/research/2026-09-28-rule-1-authorship-verification.md` section 7.
  - One case the plan does not address: Hippolytus led a rival community in Rome, in schism from about 217 to his reconciliation around 235 (rule-1 memo, section 7(f)), and the Refutation of All Heresies (377 live passages) is dated to the 220s by the scholarship that memo cites. Under rule A a work written outside communion goes, and Hippolytus is not a Doctor. R1 must date his works and report the result; the decision is Carter's.
- **Changes (deliverables):**
  - `docs/research/R1-rule-a-dating.md` (plan repo), with:
    - An author list built from the 2.1 registry plus the candidates memo, each classified as `born-in-communion`, `convert-no-pre-baptism-writing`, `convert-with-possible-pre-baptism-writing`, `later-break`, or `break-and-return`, with one citation per classification. Expect about 20 in the last three classes (Decision log "Rule A dating method"). Patristic converts to check include Justin, Athenagoras, Theophilus, Clement of Alexandria, Minucius Felix, Cyprian, Lactantius, Gregory Thaumaturgus, Commodian, and Augustine (his Cassiciacum works predate baptism; confirm none are in the corpus). Modern ones include Newman, Chesterton, Stein, Knox, Faber, Brownson and Manning if on the candidate list.
    - For each author in those three classes, the one standard chronology used (named edition and page), the communion dates, and per work the date range and the resulting `include` or `exclude`, excluding when standard sources disagree about which side of the line a work falls on.
    - For every author in the corpus and candidates, the Church-act search result: acts found (issuer, date, act, effect, citation URL to an official or scholarly text of the act) or "none found", with the sources searched (at minimum the 1948 Index Librorum Prohibitorum, De Bujanda's Index volumes where reachable, and the Holy Office and CDF notifications on vatican.va).
    - The three open Index questions answered with the decree cited.
  - `datapipeline/registry/rule_a_R1.json`, entries keyed by `work_id` holding exactly the `rule_a` object shape from 2.1, for merge into `works.json` by PR 3.1 (or by 2.1 if R1 finishes first).
- **Acceptance checks:**
  - Every corpus and candidate author appears once with a classification and citation.
  - Every `exclude` names the act or the chronology entry that causes it; every Tertullian work has a date range and source.
  - The passage count each decision removes is computed from the registry and a master build and matches, or explains differences from, the plan's "What the rules remove" table (Tertullian 192, and so on).
  - Findings that would change a Decision log outcome (Hippolytus is the known one) are listed separately under "For Carter", with no change made to the plan.
- **Production safety:** Research only; nothing touches code or data.
- **Needs Carter:** Decide the Hippolytus question and any other finding listed under "For Carter". Approve the chronology choices where two standards exist.
- **Out of scope:** Removing anything (3.1). Rules B, C, D labels (3.2). Re-arguing decided authors.

---

### R2. Canons 296, 360, 361 and 948 against iuscangreg.it

- **Type:** research
- **Depends on:** none; blocks 1.5
- **Goal:** Know, for each of four canons whose current wording is unconfirmed, whether it was amended after the vendored vatican.va text, and if so the current English text and its source, so PR 1.5 loads current law (rule F) instead of guessing.
- **Current state:**
  - Decision log "Canon law amendments": current text comes from iuscangreg.it (the Gregorian University faculty's amendment register, not a Vatican site), checked against the amending documents on vatican.va, verified per canon.
  - Live text read on 29 Sep: canon 296 begins "Lay persons can dedicate themselves to the apostolic works of a personal prelature by agreements..."; canon 360 names "the Secretariat of State or the Papal Secretariat, the Council for the Public Affairs of the Church, congregations..."; canon 361 refers to "the Secretariat of State, the Council for the Public Affairs of the Church, and other institutes of the Roman Curia"; canon 948 reads "Separate Masses are to be applied for the intentions of those for whom a single offering, although small, has been given and accepted." None carries the source's "n" amendment marker in live text.
  - Canon 295 is known to be pre-2023 in the vendored source itself (plan, "Corrections to the handoff doc"); it is in 1.5's scope already, not R2's.
- **Changes (deliverables):** `docs/research/R2-canons.md` with, per canon:
  - Whether iuscangreg.it lists an amendment, with the amending act's name, date and vatican.va URL.
  - The amended Latin text from the act, and the English text if the Holy See published one (official or L'Osservatore Romano), otherwise "no English published".
  - Whether the vendored `sources/canon-law/` page already has the new text, and which file.
  - The treatment 1.5 should apply under rules F and E and the handoff rule for unofficial English (canons 111, 112, 535, 868 precedent).
- **Acceptance checks:** Four entries, each with at least two sources (iuscangreg.it and the vatican.va act) or an explicit "no amendment found in either". Any English text quoted is the Holy See's own, never our translation (Decision log "Rights review": TheoCorpus makes no translations).
- **Production safety:** Research only.
- **Needs Carter:** Nothing unless a canon has no English text, which then follows rule E as decided.
- **Out of scope:** Other canons, the parser fixes, and the Eastern code.

---

### R3. Esther claims

- **Type:** research
- **Depends on:** none; blocks 1.4
- **Goal:** Settle exactly which Esther verses are missing and how the Greek additions should be numbered and labeled in a Catholic reader, so PR 1.4 restores the right text with references that match Church documents.
- **Current state:**
  - Plan claims Esther 4:18-47 and 10:4-14 are missing, among 245 missing verses.
  - Verified 29 Sep: the vendored `sources/bible/eng-web-c_usfm/43-ESGeng-web-c.usfm` ("Esther (Greek)") has 10 chapters; chapter 4 has 46 verse markers numbered up to 47, chapter 9 has 30 markers up to 32, chapter 10 has 14. Live Esther (26 passages) has references "Esther 4:1–3", "Esther 4:4–17", "Esther 9:1–10", "Esther 9:11–17", "Esther 9:18–32", "Esther 10:1–3". So 4:18-47 and 10:4-14 are absent from live, as claimed. Chapter 9's gap between 30 markers and the top number 32 (some verses combined or missing in the source) is unexplained.
  - The additions A to F in other Catholic editions use lettered or chapter 11 to 16 numbering; which scheme the Nova Vulgata and the Church's documents cite is **not verified** here. The Decision log adopts Nova Vulgata numbering for the Bible.
- **Changes (deliverables):** `docs/research/R3-esther.md` with:
  - The full verse inventory of `43-ESGeng-web-c.usfm` per chapter, including combined or skipped verse numbers, and a map from WEB-C's inline numbering to the Nova Vulgata numbering, with the Nova Vulgata source cited.
  - The list of live Esther verses missing (should reproduce 4:18-47 and 10:4-14 or correct them), and whether any Hebrew-Esther-only content is duplicated in the Greek book.
  - The reference format 1.4 should display for the additions, with an example of a Church document citing Esther additions in that form.
- **Acceptance checks:** Inventory produced by a script whose output is pasted, not by hand; every claim in the plan's Bible row about Esther either confirmed or corrected with the evidence.
- **Production safety:** Research only.
- **Needs Carter:** Nothing, unless no Church source settles the numbering, in which case the choice is his.
- **Out of scope:** Daniel's additions (same PR 1.4, already verified in the plan), pericope chunking.

---

### R4. Are the Refutation's book contents authorial?

- **Type:** research
- **Depends on:** none; blocks 1.8a
- **Goal:** Decide whether the "Contents" summaries at the head of books of the Refutation of All Heresies were written by the author (keep, rule G does not apply) or added by the translator or editor (remove under rule G), so PR 1.8a strips only editorial material.
- **Current state:**
  - Live document "The Refutation of All Heresies." (author "Hippolytus.") has 377 passages, 8 of them contents-like, with chapter labels "Book I · Contents", "Book V · Contents", "Book VI · Contents", "Book VII · Contents", "Book VIII · Contents", "Book IX · Contents", "Book X · Contents" (read-only query, 29 Sep). The source is ANF05 (`sources/church-fathers/third-century-2.xml`, per the vendor manifest file names).
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
- **Depends on:** 0.2 (the inventory format); each part blocks the PR that ingests the source
- **Goal:** Before any new or replacement source is ingested, confirm that the file we would vendor is the edition the Decision log names, that it is public domain on a recorded basis, and that it is clean text or which OCR route it takes. This keeps a Peers translation or a 1932 Tanquerey from entering by accident.
- **Current state:**
  - Decision log fixes the editions: David Lewis and pre-1931 Stanbrook for John of the Cross and Teresa (no Peers); Lewis 1864 for the Spiritual Canticle, not CCEL's 1995 modernization; Gutenberg 13871 for Brother Lawrence, not 5657; a 1930 printing of Tanquerey; Robertson's NPNF On the Incarnation (npnf204); Percival for councils 1 to 7, Schroeder 1937 for 8 to 18, Schaff 1877 for Vatican I; Pascal's Pensées in Trotter 1910.
  - `docs/research/2026-09-28-scan-only-works-text-sources.md`: of 48 scan-only works, clean text for 19 (4 flagged), partial for 6, OCR only for 23. ecatholic2000.com claims copyright on its pages (use only to check our OCR or with permission, Decision log "OCR and scanned works").
  - The candidates memo lists 27 CCEL ThML works (A1) and 58 Gutenberg or Internet Archive works (A2).
  - Schroeder 1937 is after 1930, so its public-domain status needs a renewal search under the Decision log's non-renewal rule; that record does not exist yet.
- **Changes (deliverables):** One row per planned work in `datapipeline/rights_inventory.json` (0.2 format) plus `docs/research/R6-editions.md` with, per work:
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
- **Out of scope:** OCR clean-up (5.6c), adapter code, licensed works (Decision log "Licences": no spending).
