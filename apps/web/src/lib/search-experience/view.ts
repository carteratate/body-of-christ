import type { CollectionOutcome, SearchOutcome } from "@/lib/search-stream";
import type {
  ActiveSearchSnapshot,
  FailureSnapshot,
  Passage,
  RestoredPassagesSnapshot,
  SearchCompletionFailure,
  SearchExperienceSnapshot,
  SearchPhase,
  SearchRateLimit,
  SearchRequest,
  SearchTransportState,
} from "./types";

export interface SearchExperienceView {
  readonly active: ActiveSearchSnapshot | null;
  readonly restored: RestoredPassagesSnapshot | null;
  readonly restoring: boolean;
  readonly failure: FailureSnapshot | null;
  readonly request: SearchRequest | null;
  readonly transport: SearchTransportState | null;
  readonly completionFailure: SearchCompletionFailure | null;
  readonly loading: boolean;
  readonly passages: readonly Passage[];
  readonly searchId: string | null;
  readonly submittedQuery: string | null;
  readonly queryBubbleVisible: boolean;
  readonly error: string | null;
  readonly errorCode: string | null;
  readonly errorStage: string | null;
  readonly outcome: SearchOutcome | null;
  readonly collectionOutcomes: Readonly<Record<string, CollectionOutcome>>;
  readonly saveWarning: string | null;
  readonly phase: SearchPhase | null;
  readonly exploreLabel: string | null;
  readonly showAnimation: boolean;
  readonly animationRunId: number;
  readonly queryDone: boolean;
  readonly retrievalStarted: boolean;
  readonly filterBarActive: boolean;
  readonly submittedCollections: readonly string[];
  readonly submittedTranslation: string;
  readonly submittedQuota: number | null;
  readonly rateLimit: SearchRateLimit | null;
}

export function searchExperienceView(snapshot: SearchExperienceSnapshot): SearchExperienceView {
  const active = snapshot.status === "active-search" ? snapshot : null;
  const restored = snapshot.status === "restored-passages" ? snapshot : null;
  const restoring = snapshot.status === "restoring";
  const failure = snapshot.status === "failure" ? snapshot : null;
  const request = active?.request ?? restored?.request ?? failure?.request ?? null;
  const transport = active?.transport ?? null;
  const completionFailure = transport?.status === "ranked-ready"
    ? transport.completionFailure
    : null;
  const rateLimit = failure?.failure.rateLimit?.open
    ? failure.failure.rateLimit
    : completionFailure?.rateLimit?.open
      ? completionFailure.rateLimit
      : null;

  return {
    active,
    restored,
    restoring,
    failure,
    request,
    transport,
    completionFailure,
    loading: restoring || active?.presentation.status === "animating",
    passages: active?.passages ?? restored?.passages ?? [],
    searchId: restored?.searchId
      ?? (transport?.status === "complete" ? transport.searchId : null),
    submittedQuery: request?.query ?? null,
    queryBubbleVisible: restored !== null
      || failure?.request != null
      || (active !== null && active.presentation.status !== "animating"),
    error: failure?.failure.message ?? null,
    errorCode: failure?.failure.code ?? null,
    errorStage: failure?.failure.stage ?? null,
    outcome: restored
      ? restored.passages.length > 0 ? "success" : "no_candidates"
      : transport?.status === "complete"
        ? transport.outcome
        : transport?.status === "ranked-ready" && transport.resultCount === 0
          ? "no_candidates"
          : null,
    collectionOutcomes: failure?.failure.collectionOutcomes
      ?? completionFailure?.collectionOutcomes
      ?? (transport?.status === "complete" ? transport.collectionOutcomes : {}),
    saveWarning: restored?.warning ?? active?.saveWarning ?? null,
    phase: transport?.status === "searching" ? transport.phase : null,
    exploreLabel: request?.exploreLabel ?? null,
    showAnimation: active !== null && active.presentation.status !== "revealed",
    animationRunId: snapshot.runId,
    queryDone: active?.presentation.status === "animating"
      && active.presentation.resultsReady,
    retrievalStarted: transport !== null && transport.status !== "preparing",
    filterBarActive: active?.presentation.filtersReady ?? false,
    submittedCollections: request?.collections ?? [],
    submittedTranslation: request?.translation ?? "",
    submittedQuota: request?.quota ?? null,
    rateLimit,
  };
}
