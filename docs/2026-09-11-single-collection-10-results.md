# Single-collection 10-passage mode: technical impact

> Research note, 2026-09-11. This describes the current repository and a proposed
> implementation. It does not describe shipped behavior. No production code was
> changed as part of this audit.

## Product decisions after grilling

This section is the authoritative product specification. It supersedes any earlier
recommendation later in this research note where the two disagree.

- Quota 10 is valid only with exactly one distinct valid collection. The API rejects
  any other quota-10 request with a 422 response before rate limiting.
- A focused search requests exactly ten Passages. It may return fewer when fewer
  Passages satisfy the relevance and diversity rules.
- The focused-search terminal reranker receives 25 candidates. This ships as the
  initial production value and will be monitored after release.
- Focused mode allows at most four Passages from one underlying document. The normal
  search cap remains unchanged.
- If no Passage survives the normal threshold, the existing minimum-floor behavior
  may return up to five closest Passages. The interface must label that fallback.
- A quota-10 search consumes one normal search allowance. This also applies to one of
  a guest's two trial searches.
- Guests receive the same collection and quota controls as authenticated users. New
  guests still start with the existing six collections and quota 3.
- Guest collections, quota, `last_standard_quota`, and Bible translation transfer to
  a newly created account. Local guest draft state clears only after the server
  confirms the preference save.
- Preferences persist quota 10 when exactly one collection is saved. Preferences also
  persist `last_standard_quota`, whose domain is 3, 4, or 5.
- Preference changes save immediately. The interface keeps an optimistic selection,
  retries the latest state after a transient failure, and shows a toast only if that
  retry fails.
- Adding a second collection while quota 10 is selected restores
  `last_standard_quota`. Returning to one collection reveals 10 unselected. A new
  session still restores a saved one-collection quota-10 default.
- Opening a restored search never changes current preferences. Restored focused
  searches retain their underfill or fallback outcome notice.
- Underfill and fallback notices render below the Passage cards, beside the existing
  collection-outcome, save, and incomplete-result notices.
- The chosen control is the joined-segment design. It remains right anchored. When a
  search becomes eligible, 3, 4, and 5 slide left over 250 ms and 10 enters at the
  right. The right edge of 5 becomes square while 10 is present.
- The 10 segment has the same dimensions as the other quota segments, a permanent
  4 px gold boundary, 40% collection-color fill while unselected, 90% while selected,
  and an automatically chosen light or dark numeral.
- Selecting 10 fires one 750 ms outward soft-bloom pulse. Selecting a standard quota
  does not pulse. Reduced-motion mode makes the transition and pulse immediate.
- The query animation uses its existing choreography and marks ten distinct winning
  Passage bubbles when focused mode is active.
- Analytics records eligibility, selection, requested quota, delivered count,
  underfill or fallback outcome, latency, and cost without recording query text.

## Initial research recommendation

Treat 10 as a contextual, authenticated-search mode, not as a fourth ordinary
preference value.

The rule should be one invariant shared by the interface and enforced again by the
API:

```text
quota is 3, 4, or 5
OR
quota is 10 and there is exactly one distinct valid collection
```

The button may promise "up to 10 passages." It should not promise ten distinct works
or ten guaranteed results. The current pipeline caps each collection, while a separate
deduplication rule allows two passages per work or per reader chapter. A quota of 10
therefore means ten passages from one collection, spread across at least five source
buckets when the corpus and scores permit it
([quota_cap.py:7](../services/api/app/rag/steps/quota_cap.py#L7),
[dedup.py:23](../services/api/app/rag/dedup.py#L23),
[dedup.py:195](../services/api/app/rag/dedup.py#L195)). The product copy currently
calls collections "Sources" and labels the control "Per source," so the word
"source" is overloaded. The feature tickets should settle the copy before code lands.

I recommend keeping a `lastStandardQuota` of 3, 4, or 5 in the page state. Selecting
10 changes only the current search draft. If the collection count changes away from
one, reset the draft to `lastStandardQuota`. Returning to one collection reveals 10
again but does not select it automatically. This avoids surprising spend and keeps a
contextual reward from becoming a sticky default.

## What the current application does

The quota selector renders the fixed values 3, 4, and 5. It accepts only a value and
an `onChange` callback, so it does not know whether the special choice is eligible
([QuotaControl.tsx:3](../apps/web/src/components/search/QuotaControl.tsx#L3),
[QuotaControl.tsx:5](../apps/web/src/components/search/QuotaControl.tsx#L5)).
`BottomBar` already owns both active collections and quota, which makes it the natural
place to pass an `allowTen` flag or the collection count
([BottomBar.tsx:8](../apps/web/src/components/search/BottomBar.tsx#L8),
[BottomBar.tsx:61](../apps/web/src/components/search/BottomBar.tsx#L61)). Guest search
replaces the selector with fixed "3 passages per source" copy, so the new mode should
remain unavailable to guests unless that product rule changes separately
([BottomBar.tsx:68](../apps/web/src/components/search/BottomBar.tsx#L68)).

`SearchPage` holds collections and quota in separate `useState` values. Collection
changes do not reconcile quota, and quota changes immediately emit analytics
([SearchPage.tsx:40](../apps/web/src/components/search/SearchPage.tsx#L40),
[SearchPage.tsx:199](../apps/web/src/components/search/SearchPage.tsx#L199),
[SearchPage.tsx:215](../apps/web/src/components/search/SearchPage.tsx#L215)). Submission
captures both values in an immutable request owned by the search runtime, so later UI
changes cannot mutate an in-flight run
([SearchPage.tsx:152](../apps/web/src/components/search/SearchPage.tsx#L152),
[runtime.ts:40](../apps/web/src/lib/search-experience/runtime.ts#L40)). That snapshot
boundary is already correct for this feature.

The frontend runtime only checks that quota is a positive integer. It does not enforce
the server's allowed values or the collection-count relationship
([runtime.ts:102](../apps/web/src/lib/search-experience/runtime.ts#L102)). The API
transport also types quota as a plain number and sends it unchanged
([api.ts:270](../apps/web/src/lib/api.ts#L270)). UI reconciliation is therefore useful
for behavior, but it cannot be the security boundary.

## API contract and validation

The authenticated request model currently accepts every integer from 3 through 5
([models/search.py:10](../services/api/app/models/search.py#L10)). Raising the upper
bound to 10 would accidentally admit 6, 7, 8, and 9. Use an explicit allowed-value
validator or `Literal[3, 4, 5, 10]`, then enforce the cross-field rule after collection
normalization.

Collection validation currently drops unknown values if at least one known collection
remains, preserves duplicates, and returns the resulting list
([routes/search.py:40](../services/api/app/routes/search.py#L40)). "Exactly one" should
mean one distinct valid collection. Normalize once, preserving order, before checking
the quota. This also prevents a crafted `['bible', 'bible']` request from causing
duplicate HyDE work. HyDE fans out directly over the supplied list
([hyde_s25.py:394](../services/api/app/rag/steps/hyde_s25.py#L394),
[hyde_s25.py:464](../services/api/app/rag/steps/hyde_s25.py#L464)).

Put the conditional check in the existing collection dependency so an invalid
quota-10 request fails before the rate-limit counter increments. The rate limiter
already depends on collection validation for that ordering
([routes/search.py:55](../services/api/app/routes/search.py#L55)). The route then passes
the normalized collections and quota to the pipeline without further transformation
([routes/search.py:117](../services/api/app/routes/search.py#L117)). Tests should pin
the chosen status code and message for these cases:

- 3, 4, and 5 with one or many valid collections succeed.
- 10 with one distinct valid collection succeeds.
- 10 with zero or two distinct valid collections fails before rate limiting.
- 6 through 9 and values outside 3 through 10 fail model validation.
- Duplicate and mixed valid/invalid collection inputs follow an explicit, tested
  normalization policy.
- Guest quota remains capped at 3. The guest route currently clamps any submitted
  value to its fixed maximum
  ([guest_search.py:459](../services/api/app/routes/guest_search.py#L459)).

## Draft state and preference persistence

There is a subtle failure in the obvious frontend implementation. `SearchPage` saves
collections, quota, and translation together after an 800 ms debounce
([SearchPage.tsx:73](../apps/web/src/components/search/SearchPage.tsx#L73)). The
preference request model rejects quota above 5
([models/preferences.py:12](../services/api/app/models/preferences.py#L12)), and the
database has the same 3-to-5 check
([0006_v2_bookmarks_feedback_prefs.sql:33](../supabase/migrations/0006_v2_bookmarks_feedback_prefs.sql#L33)).
Because the save catches and discards errors, simply setting draft quota to 10 would
also stop a simultaneous collection or translation change from being saved, with no
message to the user.

For the recommended contextual behavior, keep `default_quota` in the 3-to-5 domain.
When draft quota is 10, the debounced preference write should send
`lastStandardQuota`, not 10. No database migration is then needed. The submitted
search still records quota 10 in `searches.filters`, which is the correct historical
fact
([pipeline.py:229](../services/api/app/rag/pipeline.py#L229)).

If product instead decides that 10 must persist, this becomes a schema change. Add a
migration that replaces the old check with a cross-column constraint, such as quota
10 requiring `cardinality(default_collections) = 1`; widen the Pydantic preference
field; and validate the complete merged preference row. Validating only fields present
in a partial PUT is insufficient. The route merges partial updates before writing
([routes/preferences.py:97](../services/api/app/routes/preferences.py#L97)), so validating
only the request body would miss a saved quota of 10 followed by a multi-collection
update.

## Search pipeline impact

Production uses `hyde_cohere_luna`, a per-collection Cohere rerank followed by one
global listwise Luna rerank
([pipeline.py:23](../services/api/app/rag/pipeline.py#L23),
[registry.py:55](../services/api/app/rag/pipelines/registry.py#L55)). In this production
mode, increasing quota does not deepen initial retrieval. The runner derives a
100-candidate RRF target and a per-strategy limit from active retrieval paths, then
passes those fixed sizes into vector search, FTS, and RRF
([runner.py:147](../services/api/app/rag/pipelines/runner.py#L147),
[runner.py:326](../services/api/app/rag/pipelines/runner.py#L326)). With the defaults,
three common paths yield `ceil(100 / 3 * 1.5) = 50` candidates per strategy, clamped
between 10 and 60
([budget.py:97](../services/api/app/rag/steps/budget.py#L97),
[config.py:139](../services/api/app/config.py#L139)). Bible has extra HyDE vectors,
but the pool-sizing comment intentionally uses the common path count
([runner.py:164](../services/api/app/rag/pipelines/runner.py#L164)).

The quota does change what reaches Luna. Cohere keeps `quota + 3` candidates for each
collection before the global pool, so a normal quota of 5 sends up to 8 candidates
from a single collection and quota 10 sends up to 13
([budget.py:111](../services/api/app/rag/steps/budget.py#L111),
[config.py:80](../services/api/app/config.py#L80),
[rerank.py:103](../services/api/app/rag/steps/rerank.py#L103)). A single collection's
13 candidates fit below the global listwise cap of 40
([budget.py:120](../services/api/app/rag/steps/budget.py#L120),
[config.py:105](../services/api/app/config.py#L105)). Cohere itself still packs the
largest candidate prefix estimated to fit in one billed search unit, independent of
quota
([rerank_cohere.py:238](../services/api/app/rag/steps/rerank_cohere.py#L238),
[budget.py:71](../services/api/app/rag/steps/budget.py#L71)). A single-collection
quota-10 request should therefore remain one Cohere call and usually one Cohere search
unit, not twice the Cohere cost of quota 5.

Thirteen is thin slack for returning ten. After Luna scores those candidates, cosine
deduplication and the two-per-source cap can remove more than three, and the pipeline
does not refill from candidates that never reached Luna. `collection_guarantee` only
inserts a best candidate when the entire selected collection is absent; it does not
top a short result list back up
([rerank.py:217](../services/api/app/rag/steps/rerank.py#L217),
[collection_guarantee.py:8](../services/api/app/rag/steps/collection_guarantee.py#L8),
[runner.py:340](../services/api/app/rag/pipelines/runner.py#L340)). Before calling the
feature "10 passages," run an offline single-collection evaluation over all ten
collections and measure delivered-count, relevance, and redundancy distributions.
Likely fixes are extra keep slack specifically for quota 10, or a post-dedup refill
from terminally scored candidates. The latter cannot use Cohere-only scores in the
Luna ranking because the pipeline deliberately keeps guarantee candidates on the
terminal reranker's score scale
([rerank.py:141](../services/api/app/rag/steps/rerank.py#L141)).
Start the evaluation with 20 to 30 Luna candidates for the single-collection mode.
That range fits under the existing global cap and leaves enough room to observe when
extra depth stops improving delivered count or quality.

Two more under-fill cases need explicit acceptance criteria:

- The last-resort low-score path returns at most five passages regardless of quota
  ([min_floor.py:18](../services/api/app/rag/steps/min_floor.py#L18),
  [min_floor.py:46](../services/api/app/rag/steps/min_floor.py#L46)). This may be the
  right quality tradeoff, but the UI must say "up to 10."
- If chapter metadata is missing during a degraded search, Summa, Catechism, or Canon
  Law falls back to one title-level source bucket and the two-per-source cap can reduce
  the whole collection to two passages
  ([dedup.py:48](../services/api/app/rag/dedup.py#L48),
  [dedup.py:53](../services/api/app/rag/dedup.py#L53)).

The collection guarantee has no diversity job in a one-collection search. The per-source
cap and cosine dedup are the actual diversity controls. Do not weaken them merely to
hit ten. Ten repetitive passages would make the special mode feel broken even if the
counter is correct.

## SSE, latency, and cost

The SSE event shape does not need a new mode field. The request quota determines the
run, chunk events already stream one per final result, and `done.result_count` reports
the number actually delivered
([pipeline.py:69](../services/api/app/rag/pipeline.py#L69),
[pipeline.py:172](../services/api/app/rag/pipeline.py#L172),
[pipeline.py:260](../services/api/app/rag/pipeline.py#L260)). The server emits ranking
heartbeats every ten seconds while retrieval and reranking run
([pipeline.py:88](../services/api/app/rag/pipeline.py#L88)). Existing browser parsing
accepts arbitrary nonnegative result counts, so ten needs no protocol change
([search-stream.ts:276](../apps/web/src/lib/search-stream.ts#L276)).

Time to visible passages should stay close to current behavior because the server
streams all passage cards and `done` before explanations. Explanations then run
sequentially, one model stream and one best-effort database update per result
([pipeline.py:213](../services/api/app/rag/pipeline.py#L213),
[pipeline.py:271](../services/api/app/rag/pipeline.py#L271)). Moving from five to ten
can nearly double the tail time, explanation requests, and explanation writes. Each
explanation may generate up to 220 tokens and retry rate limits before any token is
emitted
([explain.py:73](../services/api/app/rag/steps/explain.py#L73),
[explain.py:102](../services/api/app/rag/steps/explain.py#L102)). The current pipeline
cost tracker covers embedding, HyDE, Cohere, and reranking, but explanation streaming
does not receive that tracker. Logged `total_cost` therefore cannot answer the launch
cost question by itself
([cost_tracker.py:47](../services/api/app/rag/steps/cost_tracker.py#L47),
[runner.py:380](../services/api/app/rag/pipelines/runner.py#L380),
[explain.py:73](../services/api/app/rag/steps/explain.py#L73)). Add measurement before
setting rollout or rate policy.

The authenticated limiter charges one daily search and one per-minute search regardless
of requested quota
([routes/search.py:72](../services/api/app/routes/search.py#L72)). That is coherent if
10 is a product reward, but it gives a quota-10 query roughly twice the explanation
work for the same allowance as quota 5. Decide whether the 30/day and 5/minute limits
remain acceptable after measuring. The existing counter is also shared with legacy
chat, a documented known issue
([routes/search.py:64](../services/api/app/routes/search.py#L64)).

## Loading and interaction behavior

The large search animation is already data-driven enough to show ten winners. It
renders 15 candidate chunk bubbles per selected collection, chooses `quota` distinct
winners, and clamps the winner count to the available 15
([LoadingAnimation.tsx:36](../apps/web/src/components/search/LoadingAnimation.tsx#L36),
[LoadingAnimation.tsx:46](../apps/web/src/components/search/LoadingAnimation.tsx#L46),
[LoadingAnimation.tsx:284](../apps/web/src/components/search/LoadingAnimation.tsx#L284)).
At quota 10 with one collection, ten of the 15 bubbles will flash twice and send colored
lines back to the collection node
([LoadingAnimation.tsx:266](../apps/web/src/components/search/LoadingAnimation.tsx#L266),
[LoadingAnimation.tsx:438](../apps/web/src/components/search/LoadingAnimation.tsx#L438),
[LoadingAnimation.tsx:498](../apps/web/src/components/search/LoadingAnimation.tsx#L498)).
No production logic change is required for the count. Add a deterministic test seam or
DOM marker and test that quota 10 produces ten distinct winners. The existing tests
cover timing gates and theme changes, not winner count
([LoadingAnimation.test.tsx:15](../apps/web/src/components/search/LoadingAnimation.test.tsx#L15)).

The selector reveal and selection animations need their own small motion contract.
Five design directions can share the same semantics: a width-and-opacity reveal, a
spring-like scale reveal, a gold light sweep, a collection-color bloom, or a small
badge that unfolds into the 10 segment. Selection can answer with a pressed scale,
halo pulse, border sweep, count-up, or a brief glow passed toward the search field.
Keep the reveal under about 300 ms and the click response under about 500 ms. The
button must become usable immediately, must not steal focus, and must remain legible
in both themes.

There is no repository-level `prefers-reduced-motion` rule. The existing global
animation CSS defines motion without a reduced-motion branch
([globals.css:3](../apps/web/src/app/globals.css#L3)). Add a reduced-motion treatment
for the new reveal and click response. An instant appearance plus a color or border
change preserves the state change. Consider a broader follow-up for the existing
multi-second loading animation, but do not hide this feature behind that larger cleanup.

Accessibility acceptance criteria should include:

- Keep the existing grouped toggle semantics and `aria-pressed`
  ([QuotaControl.tsx:17](../apps/web/src/components/search/QuotaControl.tsx#L17)).
- Give 10 a name that states both quantity and eligibility, such as "Up to 10 passages,
  available when one source is selected."
- Do not move focus when the button appears or disappears. If a user has focused 10
  and then activates another collection through another input method, move focus only
  if browser behavior proves focus becomes lost.
- Use `focus-visible` styling. The current quota buttons rely on default focus behavior
  and only declare color transitions
  ([QuotaControl.tsx:23](../apps/web/src/components/search/QuotaControl.tsx#L23)).
- Test keyboard navigation, 320 px width, dark and light themes, 200% zoom, and reduced
  motion. Four compact number segments fit on mobile, but the animated width must not
  force the collection row to jump or overflow.

The older `SearchProgress` component does not need a quota change. It reports pipeline
phase and collection count, while `LoadingAnimation` owns the winner bubbles
([SearchProgress.tsx:97](../apps/web/src/components/search/SearchProgress.tsx#L97),
[SearchResults.tsx:80](../apps/web/src/components/search/SearchResults.tsx#L80)).

## History, restore, and analytics

Search persistence already stores the submitted quota in the filters JSON for empty
and non-empty searches
([pipeline.py:28](../services/api/app/rag/pipeline.py#L28),
[pipeline.py:229](../services/api/app/rag/pipeline.py#L229)). No search-history schema
change is needed. The restore UI, however, only accepts persisted quotas 3, 4, or 5
and otherwise substitutes the current draft quota
([useSearchPageExperience.ts:272](../apps/web/src/lib/search-experience/useSearchPageExperience.ts#L272),
[useSearchPageExperience.ts:296](../apps/web/src/lib/search-experience/useSearchPageExperience.ts#L296)).
Add 10 only when the restored filter has exactly one valid collection. Old malformed
rows should keep using the safe fallback. Restored pages show the original passages
without rerunning the loading animation, so no special-mode reveal is needed there.

Current PostHog events already record `quota_per_source` on completion and `from`/`to`
on quota changes
([analytics.ts:9](../apps/web/src/lib/analytics.ts#L9),
[analytics.ts:45](../apps/web/src/lib/analytics.ts#L45)). That is enough to count
successful quota-10 searches, but not enough to measure whether the reveal works.
Add low-cardinality events for special-choice reveal and selection, or add a
`single_collection_ten_eligible` property to the existing quota event. Fire a reveal
once per transition into eligibility, not on every render. Keep query text out of the
event, following the existing analytics rule
([analytics.ts:5](../apps/web/src/lib/analytics.ts#L5)). Track delivered count alongside
requested quota so under-fill is visible.

## Test and rollout plan

The smallest responsible ticket set is:

1. **Measure retrieval headroom.** Add a single-collection evaluation matrix for all
   ten collections at quotas 5 and 10. Record final count, pre-dedup count, unique
   source buckets, relevance, redundancy, latency, Cohere units, Luna tokens, and
   explanation tail cost. Decide keep slack and whether five-result `min_floor` stays.
   The internal compare request and page already accept quota 10
   ([compare.py:27](../services/api/app/routes/compare.py#L27),
   [compare.py:140](../services/api/app/routes/compare.py#L140)). Its batch runner also
   accepts a quota argument, but the runner's fixed `$0.34` estimate does not scale
   with quota and should not be trusted for this study
   ([run_compare_batch.py:46](../services/api/run_compare_batch.py#L46),
   [run_compare_batch.py:58](../services/api/run_compare_batch.py#L58)).
2. **Enforce the backend contract.** Add explicit quota values, normalized distinct
   collections, conditional quota-10 validation before rate limiting, route tests,
   and pipeline tests proving at most ten persisted and streamed passages.
3. **Build the frontend state invariant.** Add typed quota values,
   `lastStandardQuota`, downgrade behavior on collection changes, contextual preference
   saving, restore parsing, analytics, and reducer/page tests. Test rapid toggle and
   debounce races with fake timers.
4. **Build and verify the interaction.** Implement the chosen reveal and selected
   treatment, focus states, reduced motion, both themes, mobile layout, and ten-winner
   loading-animation coverage. Attach browser screenshots and motion recordings to the
   ticket or PR.
5. **Run a full-story review.** Exercise a real authenticated search, saved-history
   restore, a transition from one to two collections while 10 is selected, retry and
   abort behavior, a low-result query, guest isolation, analytics payloads, and both
   deployments.

Use GitHub issues for the work. The repository's Matt Pocock conventions define one
`wayfinder:map` issue with child issues for research, prototype, grilling, and tasks;
native dependencies express blockers
([issue-tracker.md:27](agents/issue-tracker.md#L27)). Fully specified implementation
tickets receive `ready-for-agent`; questions that still need the grilling session stay
`needs-info` or under the map's Fog section
([triage-labels.md:5](agents/triage-labels.md#L5)). Do not create those issues until the
mockups and grilling decisions settle persistence, copy, animation, under-fill policy,
and rollout measurement.

Deploy in dependency order. For the recommended no-migration design, ship the API
acceptance and validation first, then the web UI. If persistent quota 10 is chosen,
ship the additive database migration first, then API, then web. A backend rollback
while the quota-10 UI remains live would turn those submissions into validation errors,
so either coordinate rollback or gate the frontend exposure. No new environment
variable is otherwise required; the current pool sizes and thresholds remain config
driven
([config.py:59](../services/api/app/config.py#L59)).

## Decisions for the grilling session

The mockups should be judged after these questions have explicit answers:

- Does 10 mean up to ten passages, or must a healthy search always fill ten?
- Is the special selection temporary, remembered only while one collection remains
  selected, or saved across sessions?
- When a second collection is selected, should 10 fall back to the user's last 3/4/5
  choice, always to 5, or block the collection change?
- Is the feature authenticated-only, or should guest behavior change from its fixed
  three-passage contract?
- Should quota 10 consume the same daily allowance as quota 5 after real cost is known?
- Should the special color be brand gold, the selected collection's color, or a new
  semantic token that works in both themes?
- Which matters more when the pipeline cannot produce ten strong, diverse passages:
  result count or quality?
- What is the success metric: reveal-to-selection rate, repeat use, saved/bookmarked
  passages, search satisfaction, or a cost-adjusted combination?
