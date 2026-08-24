import type { AttachedContext, ChunkResult, CollectionOutcome } from "@/lib/search-stream";
import type {
  ActiveSearchSnapshot,
  GuestContinuitySnapshot,
  Passage,
  SearchExperience,
  SearchExperienceCommand,
  SearchExperiencePorts,
  SearchExperienceSnapshot,
  SearchFailure,
  SearchRequest,
  SearchTransportCallbacks,
} from "./types";

interface ActiveRun {
  readonly id: number;
  readonly controller: AbortController;
  readonly request: SearchRequest | null;
  readonly restoreId: string | null;
  readonly pendingEntryId: string | null;
  bufferedPassages: Passage[];
  bufferedExplanations: Record<string, string>;
  terminal: boolean;
  revealed: boolean;
  guestCompletionRecorded: boolean;
  pendingCleared: boolean;
}

const EMPTY_OUTCOMES = Object.freeze({}) as Readonly<Record<string, CollectionOutcome>>;

function deepFreeze<T>(value: T): T {
  if (typeof value !== "object" || value === null) return value;
  Object.values(value).forEach((nested) => deepFreeze(nested));
  return Object.isFrozen(value) ? value : Object.freeze(value);
}

function freezeRequest(request: SearchRequest): SearchRequest {
  return Object.freeze({
    query: request.query.trim(),
    collections: Object.freeze([...request.collections]),
    translation: request.translation,
    quota: request.quota,
    origin: request.origin,
    ...(request.exploreLabel === undefined ? {} : { exploreLabel: request.exploreLabel }),
  });
}

function freezePassage(passage: ChunkResult): ChunkResult {
  const context: AttachedContext | null = passage.context
    ? {
        relation: passage.context.relation,
        parts: passage.context.parts.map((part) => Object.freeze({ ...part })),
      }
    : null;
  if (context) {
    Object.freeze(context.parts);
    Object.freeze(context);
  }
  return Object.freeze({
    ...passage,
    source: {
      ...passage.source,
      metadata: passage.source.metadata == null
        ? passage.source.metadata
        : structuredClone(passage.source.metadata),
    },
    context,
  });
}

function freezeOutcomes(
  outcomes: Record<string, CollectionOutcome>,
): Readonly<Record<string, CollectionOutcome>> {
  return Object.freeze({ ...outcomes });
}

function classifyError(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("unauthorized") || lower.includes("401") || lower.includes("403")) return "auth_error";
  if (lower.includes("network") || lower.includes("fetch")) return "network_error";
  return "server_error";
}

function validatePorts(ports: SearchExperiencePorts): void {
  if (ports.audience.kind === "authenticated" && !ports.credentials) {
    throw new Error("Authenticated search experience requires a credential port.");
  }
  if (ports.savedSearch && !ports.credentials) {
    throw new Error("Saved-search restoration requires a credential port.");
  }
}

function isValidRequest(request: SearchRequest): boolean {
  return request.query.trim().length > 0
    && request.collections.length > 0
    && request.translation.length > 0
    && Number.isInteger(request.quota)
    && request.quota > 0;
}

export function createSearchExperience(ports: SearchExperiencePorts): SearchExperience {
  validatePorts(ports);

  const listeners = new Set<() => void>();
  let generation = 0;
  let identity: string | null = null;
  let disposed = false;
  let run: ActiveRun | null = null;
  let snapshot: SearchExperienceSnapshot = deepFreeze({
    status: "idle",
    runId: generation,
    canSubmit: true,
    canRetry: false,
  });

  const emit = (next: SearchExperienceSnapshot) => {
    snapshot = deepFreeze(next);
    listeners.forEach((listener) => listener());
  };

  const bestEffort = (effect: () => void | Promise<void>) => {
    try {
      void Promise.resolve(effect()).catch(() => undefined);
    } catch {
      // Secondary adapters must never change the lifecycle outcome.
    }
  };

  const isCurrent = (runId: number) => run?.id === runId && generation === runId;

  const clearPending = (ownedRun: ActiveRun) => {
    if (ownedRun.pendingCleared || !ownedRun.pendingEntryId || !ports.pendingHistory) return;
    ownedRun.pendingCleared = true;
    bestEffort(() => ports.pendingHistory!.clear(ownedRun.pendingEntryId!));
  };

  const abortCurrent = () => {
    if (!run) return;
    run.controller.abort();
    clearPending(run);
    run = null;
  };

  const nextRun = (
    request: SearchRequest | null,
    restoreId: string | null,
    pendingEntryId: string | null,
  ): ActiveRun => {
    abortCurrent();
    generation += 1;
    const next: ActiveRun = {
      id: generation,
      controller: new AbortController(),
      request,
      restoreId,
      pendingEntryId,
      bufferedPassages: [],
      bufferedExplanations: {},
      terminal: false,
      revealed: false,
      guestCompletionRecorded: false,
      pendingCleared: false,
    };
    run = next;
    return next;
  };

  const activeSnapshot = (runId: number): ActiveSearchSnapshot => {
    if (!isCurrent(runId) || snapshot.status !== "active-search") {
      throw new Error("Search adapter emitted an event outside its active run.");
    }
    return snapshot;
  };

  const exposeBufferedPassages = (ownedRun: ActiveRun): readonly Passage[] =>
    Object.freeze(ownedRun.bufferedPassages.map((passage) => freezePassage({
      ...passage,
      explanation: ownedRun.bufferedExplanations[passage.chunk_id] ?? passage.explanation,
    })));

  const saveGuestContinuity = (ownedRun: ActiveRun, current: ActiveSearchSnapshot) => {
    if (ports.audience.kind !== "guest" || !ports.guestContinuity || !ownedRun.revealed) return;
    const complete = current.transport.status === "complete" ? current.transport : null;
    const continuity: GuestContinuitySnapshot = Object.freeze({
      savedAt: ports.time?.now() ?? Date.now(),
      request: current.request,
      searchId: complete?.searchId ?? null,
      passages: current.passages,
      outcome: complete?.outcome ?? null,
      collectionOutcomes: complete?.collectionOutcomes ?? EMPTY_OUTCOMES,
    });
    bestEffort(() => ports.guestContinuity!.save(continuity));
  };

  const failSearch = (
    ownedRun: ActiveRun,
    failure: SearchFailure,
    retryable = true,
  ) => {
    if (!isCurrent(ownedRun.id)) return;
    ownedRun.terminal = true;
    clearPending(ownedRun);
    const request = ownedRun.request;
    emit({
      status: "failure",
      runId: ownedRun.id,
      request,
      restoreId: ownedRun.restoreId,
      failure,
      canSubmit: true,
      canRetry: retryable,
    });
    if (request && ports.analytics) {
      bestEffort(() => ports.analytics!.searchFailed({
        audience: ports.audience.kind,
        request,
        code: failure.code,
      }));
    }
  };

  const transportCallbacks = (ownedRun: ActiveRun): SearchTransportCallbacks => ({
    onStatus(phase) {
      if (!isCurrent(ownedRun.id)) return;
      const current = activeSnapshot(ownedRun.id);
      if (ownedRun.terminal) throw new Error("Status cannot arrive after a terminal search event.");
      if (current.transport.status !== "preparing" && current.transport.status !== "searching") {
        throw new Error("Status cannot arrive after ranked results are ready.");
      }
      if (current.transport.status === "searching"
        && current.transport.phase === "ranking"
        && phase === "searching") {
        throw new Error("Search status cannot move backward from ranking to searching.");
      }
      emit({ ...current, transport: { status: "searching", phase } });
    },
    onPassage(passage) {
      if (!isCurrent(ownedRun.id)) return;
      const current = activeSnapshot(ownedRun.id);
      if (ownedRun.terminal) throw new Error("Passages cannot arrive after a terminal search event.");
      if (current.transport.status === "ranked-ready") {
        throw new Error("Passages cannot arrive after ranked results are ready.");
      }
      ownedRun.bufferedPassages.push(freezePassage({ ...passage, explanation: null }));
    },
    onResultsReady(resultCount) {
      if (!isCurrent(ownedRun.id)) return;
      const current = activeSnapshot(ownedRun.id);
      if (ports.audience.kind !== "guest") {
        throw new Error("Only the guest adapter may emit results-ready.");
      }
      if (ownedRun.terminal) throw new Error("Results-ready cannot arrive after completion.");
      if (current.transport.status === "ranked-ready") {
        throw new Error("A guest search cannot become results-ready twice.");
      }
      emit({
        ...current,
        transport: { status: "ranked-ready", resultCount },
        presentation: current.presentation.status === "animating"
          ? { ...current.presentation, resultsReady: true }
          : current.presentation,
      });
    },
    onExplanationDelta(passageId, delta) {
      if (!isCurrent(ownedRun.id)) return;
      const current = activeSnapshot(ownedRun.id);
      ownedRun.bufferedExplanations[passageId] = (ownedRun.bufferedExplanations[passageId] ?? "") + delta;
      if (!ownedRun.revealed) return;
      const passages = Object.freeze(current.passages.map((passage) =>
        passage.chunk_id === passageId
          ? freezePassage({ ...passage, explanation: (passage.explanation ?? "") + delta })
          : passage
      ));
      const next = { ...current, passages };
      emit(next);
      saveGuestContinuity(ownedRun, next);
    },
    onDone(searchId, resultCount, outcome, collectionOutcomes, persisted) {
      if (!isCurrent(ownedRun.id)) return;
      const current = activeSnapshot(ownedRun.id);
      if (ownedRun.terminal) throw new Error("A search run cannot complete twice.");
      if (ports.audience.kind === "guest" && current.transport.status !== "ranked-ready") {
        throw new Error("A guest search cannot complete before ranked results are ready.");
      }
      ownedRun.terminal = true;
      clearPending(ownedRun);
      const transport = {
        status: "complete" as const,
        searchId,
        resultCount,
        outcome,
        collectionOutcomes: freezeOutcomes(collectionOutcomes),
        persisted,
      };
      const next: ActiveSearchSnapshot = {
        ...current,
        transport,
        presentation: ports.audience.kind === "authenticated" && current.presentation.status === "animating"
          ? { ...current.presentation, resultsReady: true }
          : current.presentation,
        saveWarning: ports.audience.kind === "authenticated" && !persisted
          ? "Results are available now, but search history could not be saved."
          : null,
      };
      emit(next);
      if (ports.audience.kind === "authenticated" && searchId && ports.pendingHistory) {
        bestEffort(() => ports.pendingHistory!.refresh());
      }
      if (ports.audience.kind === "guest" && !ownedRun.guestCompletionRecorded) {
        ownedRun.guestCompletionRecorded = true;
        if (ports.guestAccess) bestEffort(() => ports.guestAccess!.recordCompletedSearch());
      }
      const completedRequest = ownedRun.request;
      if (ports.analytics && completedRequest) {
        bestEffort(() => ports.analytics!.searchCompleted({
          audience: ports.audience.kind,
          request: completedRequest,
          resultCount,
          outcome,
        }));
      }
      saveGuestContinuity(ownedRun, next);
    },
    onError(message, code, stage, collectionOutcomes) {
      if (!isCurrent(ownedRun.id)) return;
      if (ownedRun.terminal) throw new Error("An error cannot follow a terminal search event.");
      failSearch(ownedRun, {
        kind: "search",
        message,
        code: code ?? classifyError(message),
        stage: stage ?? null,
        collectionOutcomes: freezeOutcomes(collectionOutcomes ?? {}),
        rateLimit: null,
      });
    },
    onRateLimit(retryAfter, type) {
      if (!isCurrent(ownedRun.id)) return;
      if (ownedRun.terminal) throw new Error("A rate limit cannot follow a terminal search event.");
      failSearch(ownedRun, {
        kind: "search",
        message: type === "daily"
          ? "You have reached today’s search limit."
          : "Too many searches were submitted in a short period.",
        code: "rate_limit",
        stage: "rate_limit",
        collectionOutcomes: EMPTY_OUTCOMES,
        rateLimit: Object.freeze({
          type,
          retryAfter: type === "daily" ? null : (retryAfter ?? 60),
          open: true,
        }),
      });
    },
  });

  const startSearch = (requestInput: SearchRequest) => {
    if (!isValidRequest(requestInput)) return;
    if (ports.audience.kind === "guest" && ports.guestAccess && !ports.guestAccess.canSearch()) {
      bestEffort(() => ports.guestAccess!.requestSignup("limit"));
      return;
    }

    const request = freezeRequest(requestInput);
    const pendingEntryId = ports.pendingHistory
      ? (ports.ids?.pendingEntry() ?? `search-${generation + 1}`)
      : null;
    const ownedRun = nextRun(request, null, pendingEntryId);
    if (ports.audience.kind === "guest" && ports.guestContinuity) {
      bestEffort(() => ports.guestContinuity!.clear());
    }
    if (pendingEntryId && ports.pendingHistory) {
      bestEffort(() => ports.pendingHistory!.begin(pendingEntryId, request.query));
    }
    emit({
      status: "active-search",
      runId: ownedRun.id,
      audience: ports.audience.kind,
      request,
      transport: { status: "preparing" },
      presentation: { status: "animating", filtersReady: false, resultsReady: false },
      passages: Object.freeze([]),
      saveWarning: null,
      canSubmit: true,
      canRetry: false,
    });

    const callbacks = transportCallbacks(ownedRun);
    const audience = ports.audience;
    const search = audience.kind === "authenticated"
      ? (() => {
          const credential = ports.credentials!.current();
          if (!credential) {
            callbacks.onError("Authentication is required.", "auth_error", "authentication");
            return Promise.resolve();
          }
          return audience.search(credential, request, callbacks, ownedRun.controller.signal);
        })
      : (() => audience.search(request, callbacks, ownedRun.controller.signal));

    void search().catch((error: unknown) => {
      if (!isCurrent(ownedRun.id) || ownedRun.controller.signal.aborted || ownedRun.terminal) return;
      const message = error instanceof Error ? error.message : "Search failed";
      callbacks.onError(message, classifyError(message), "connection");
    });
  };

  const startRestore = (searchIdInput: string) => {
    const searchId = searchIdInput.trim();
    if (!searchId || !ports.savedSearch) return;
    const credential = ports.credentials?.current();
    if (!credential) return;
    const ownedRun = nextRun(null, searchId, null);
    emit({
      status: "restoring",
      runId: ownedRun.id,
      searchId,
      canSubmit: true,
      canRetry: false,
    });
    void ports.savedSearch.restore(credential, searchId, ownedRun.controller.signal).then((result) => {
      if (!isCurrent(ownedRun.id)) return;
      emit({
        status: "restored-results",
        runId: ownedRun.id,
        searchId: result.searchId,
        request: freezeRequest(result.request),
        passages: Object.freeze(result.passages.map(freezePassage)),
        warning: result.warning,
        canSubmit: true,
        canRetry: false,
      });
    }).catch((error: unknown) => {
      if (!isCurrent(ownedRun.id) || ownedRun.controller.signal.aborted) return;
      const message = error instanceof Error ? error.message : "Saved search could not be loaded.";
      failSearch(ownedRun, {
        kind: "restore",
        message,
        code: classifyError(message),
        stage: "restore",
        collectionOutcomes: EMPTY_OUTCOMES,
        rateLimit: null,
      });
    });
  };

  const retry = () => {
    if (snapshot.status !== "failure" || !snapshot.canRetry) return;
    if (snapshot.request) startSearch(snapshot.request);
    else if (snapshot.restoreId) startRestore(snapshot.restoreId);
  };

  const animation = (command: Extract<SearchExperienceCommand, { type: "animation" }>) => {
    if (!isCurrent(command.runId) || snapshot.status !== "active-search" || !run) return;
    const current = snapshot;
    if (command.milestone === "filters-ready") {
      if (current.presentation.status !== "animating" || current.presentation.filtersReady) return;
      emit({ ...current, presentation: { ...current.presentation, filtersReady: true } });
      return;
    }
    if (command.milestone === "ready-to-reveal") {
      if (current.presentation.status !== "animating" || !current.presentation.resultsReady) return;
      run.revealed = true;
      const next: ActiveSearchSnapshot = {
        ...current,
        passages: exposeBufferedPassages(run),
        presentation: { status: "fading", filtersReady: true },
      };
      emit(next);
      saveGuestContinuity(run, next);
      return;
    }
    if (current.presentation.status !== "fading") return;
    emit({ ...current, presentation: { status: "revealed", filtersReady: true } });
  };

  const reset = () => {
    abortCurrent();
    generation += 1;
    emit({ status: "idle", runId: generation, canSubmit: true, canRetry: false });
  };

  return Object.freeze({
    read: () => snapshot,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    send(command: SearchExperienceCommand) {
      if (disposed) return;
      switch (command.type) {
        case "submit": startSearch(command.request); break;
        case "restore": startRestore(command.searchId); break;
        case "retry": retry(); break;
        case "animation": animation(command); break;
        case "dismiss-rate-limit": {
          if (snapshot.status !== "failure" || !snapshot.failure.rateLimit?.open) break;
          const rateLimit = Object.freeze({ ...snapshot.failure.rateLimit, open: false });
          emit({ ...snapshot, failure: { ...snapshot.failure, rateLimit } });
          break;
        }
        case "cancel":
        case "reset": reset(); break;
        case "identity-changed":
          if (command.identity !== identity) {
            identity = command.identity;
            reset();
          }
          break;
        case "dispose":
          abortCurrent();
          generation += 1;
          disposed = true;
          listeners.clear();
          snapshot = deepFreeze({ status: "idle", runId: generation, canSubmit: true, canRetry: false });
          break;
      }
    },
  });
}
