import type { AttachedContext, ChunkResult, CollectionOutcome } from "@/lib/search-stream";
import type {
  ActiveSearchSnapshot,
  GuestContinuitySnapshot,
  Passage,
  SearchExperience,
  SearchExperienceCommand,
  SearchExperiencePorts,
  SearchExperienceSnapshot,
  SearchCompletionFailure,
  SearchFailure,
  SearchRequest,
  SearchTransportCallbacks,
  SavedSearchResult,
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
  const unchecked = ports as SearchExperiencePorts & {
    readonly credentials?: unknown;
    readonly savedSearch?: unknown;
    readonly pendingHistory?: unknown;
    readonly ids?: unknown;
    readonly guestAccess?: unknown;
    readonly guestContinuity?: unknown;
    readonly time?: unknown;
  };
  if (ports.audience.kind === "authenticated") {
    if (!unchecked.credentials) {
      throw new Error("Authenticated search experience requires a credential port.");
    }
    if (unchecked.guestAccess || unchecked.guestContinuity || unchecked.time) {
      throw new Error("Authenticated search experience cannot use guest capabilities.");
    }
    return;
  }
  if (unchecked.credentials || unchecked.savedSearch || unchecked.pendingHistory || unchecked.ids) {
    throw new Error("Guest search experience cannot use authenticated capabilities.");
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
  let userId: string | null = null;
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
    const ownedRun = run;
    run = null;
    ownedRun.controller.abort();
    clearPending(ownedRun);
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
    bestEffort(() => {
      const complete = current.transport.status === "complete" ? current.transport : null;
      const continuity: GuestContinuitySnapshot = Object.freeze({
        savedAt: ports.time?.now() ?? Date.now(),
        request: current.request,
        searchId: complete?.searchId ?? null,
        passages: current.passages,
        outcome: complete?.outcome ?? null,
        collectionOutcomes: complete?.collectionOutcomes ?? EMPTY_OUTCOMES,
      });
      return ports.guestContinuity!.save(continuity);
    });
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

  const preserveGuestCompletionFailure = (
    ownedRun: ActiveRun,
    current: ActiveSearchSnapshot,
    failure: SearchCompletionFailure,
  ): boolean => {
    if (ports.audience.kind !== "guest" || current.transport.status !== "ranked-ready") {
      return false;
    }
    ownedRun.terminal = true;
    clearPending(ownedRun);
    const next: ActiveSearchSnapshot = {
      ...current,
      transport: { ...current.transport, completionFailure: failure },
    };
    emit(next);
    if (ports.analytics && ownedRun.request) {
      bestEffort(() => ports.analytics!.searchFailed({
        audience: "guest",
        request: ownedRun.request!,
        code: failure.code,
      }));
    }
    saveGuestContinuity(ownedRun, next);
    return true;
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
        transport: { status: "ranked-ready", resultCount, completionFailure: null },
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
      const current = activeSnapshot(ownedRun.id);
      if (ownedRun.terminal) throw new Error("An error cannot follow a terminal search event.");
      const failure = {
        kind: "search",
        message,
        code: code ?? classifyError(message),
        stage: stage ?? null,
        collectionOutcomes: freezeOutcomes(collectionOutcomes ?? {}),
        rateLimit: null,
      } as const;
      if (preserveGuestCompletionFailure(ownedRun, current, failure)) return;
      failSearch(ownedRun, failure);
    },
    onRateLimit(retryAfter, type) {
      if (!isCurrent(ownedRun.id)) return;
      const current = activeSnapshot(ownedRun.id);
      if (ownedRun.terminal) throw new Error("A rate limit cannot follow a terminal search event.");
      const failure = {
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
      } as const;
      if (preserveGuestCompletionFailure(ownedRun, current, failure)) return;
      failSearch(ownedRun, failure);
    },
  });

  const resetToIdle = () => {
    abortCurrent();
    generation += 1;
    emit({ status: "idle", runId: generation, canSubmit: true, canRetry: false });
  };

  const emitPreparingSearch = (ownedRun: ActiveRun, request: SearchRequest) => {
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
  };

  const startSearch = (requestInput: SearchRequest) => {
    if (!isValidRequest(requestInput)) return;
    const request = freezeRequest(requestInput);
    if (ports.audience.kind === "guest" && ports.guestAccess) {
      let canSearch: boolean;
      try {
        canSearch = ports.guestAccess.canSearch();
      } catch (error: unknown) {
        const ownedRun = nextRun(request, null, null);
        emitPreparingSearch(ownedRun, request);
        const message = error instanceof Error ? error.message : "Guest access could not be checked.";
        failSearch(ownedRun, {
          kind: "search",
          message,
          code: classifyError(message),
          stage: "guest_access",
          collectionOutcomes: EMPTY_OUTCOMES,
          rateLimit: null,
        });
        return;
      }
      if (!canSearch) {
        resetToIdle();
        bestEffort(() => ports.guestAccess!.requestSignup("limit"));
        return;
      }
    }

    let pendingEntryId: string | null = null;
    if (ports.pendingHistory) {
      try {
        pendingEntryId = ports.ids?.pendingEntry() ?? `search-${generation + 1}`;
      } catch {
        pendingEntryId = `search-${generation + 1}`;
      }
    }
    const ownedRun = nextRun(request, null, pendingEntryId);
    if (ports.audience.kind === "guest" && ports.guestContinuity) {
      bestEffort(() => ports.guestContinuity!.clear());
    }
    if (pendingEntryId && ports.pendingHistory) {
      bestEffort(() => ports.pendingHistory!.begin(pendingEntryId, request.query));
    }
    emitPreparingSearch(ownedRun, request);

    const callbacks = transportCallbacks(ownedRun);
    const audience = ports.audience;
    const rejectSearch = (error: unknown) => {
      if (!isCurrent(ownedRun.id) || ownedRun.controller.signal.aborted || ownedRun.terminal) return;
      const message = error instanceof Error ? error.message : "Search failed";
      callbacks.onError(message, classifyError(message), "connection");
    };
    try {
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
      void Promise.resolve(search()).catch(rejectSearch);
    } catch (error: unknown) {
      rejectSearch(error);
    }
  };

  const startRestore = (searchIdInput: string) => {
    const searchId = searchIdInput.trim();
    if (!searchId || ports.audience.kind !== "authenticated" || !ports.savedSearch) return;
    const ownedRun = nextRun(null, searchId, null);
    emit({
      status: "restoring",
      runId: ownedRun.id,
      searchId,
      canSubmit: true,
      canRetry: false,
    });
    let credential: string | null;
    try {
      credential = ports.credentials.current();
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Authentication could not be checked.";
      failSearch(ownedRun, {
        kind: "restore",
        message,
        code: classifyError(message),
        stage: "authentication",
        collectionOutcomes: EMPTY_OUTCOMES,
        rateLimit: null,
      }, false);
      return;
    }
    if (!credential) {
      failSearch(ownedRun, {
        kind: "restore",
        message: "Authentication is required.",
        code: "auth_error",
        stage: "authentication",
        collectionOutcomes: EMPTY_OUTCOMES,
        rateLimit: null,
      }, false);
      return;
    }
    let restoration: Promise<SavedSearchResult>;
    try {
      restoration = ports.savedSearch.restore(credential, searchId, ownedRun.controller.signal);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Saved search could not be loaded.";
      failSearch(ownedRun, {
        kind: "restore",
        message,
        code: classifyError(message),
        stage: "restore",
        collectionOutcomes: EMPTY_OUTCOMES,
        rateLimit: null,
      });
      return;
    }
    void Promise.resolve(restoration).then((result) => {
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
      if (current.presentation.status !== "animating" || current.presentation.filtersReady) {
        throw new Error("Filters-ready must occur once while the search animation is running.");
      }
      emit({ ...current, presentation: { ...current.presentation, filtersReady: true } });
      return;
    }
    if (command.milestone === "ready-to-reveal") {
      if (current.presentation.status !== "animating") {
        throw new Error("Ready-to-reveal must occur while the search animation is running.");
      }
      if (!current.presentation.resultsReady) {
        throw new Error("Ready-to-reveal cannot occur before ranked results are ready.");
      }
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
    if (current.presentation.status !== "fading") {
      throw new Error("Fade-complete must occur while the search animation is fading.");
    }
    emit({ ...current, presentation: { status: "revealed", filtersReady: true } });
  };

  const queuedCommands: SearchExperienceCommand[] = [];
  let dispatching = false;

  const dispatch = (command: SearchExperienceCommand) => {
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
      case "reset": resetToIdle(); break;
      case "identity-changed":
        if (command.userId !== userId) {
          userId = command.userId;
          resetToIdle();
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
  };

  const send = (command: SearchExperienceCommand) => {
    if (disposed) return;
    if (dispatching) {
      queuedCommands.push(command);
      return;
    }
    dispatching = true;
    try {
      let next: SearchExperienceCommand | undefined = command;
      while (next && !disposed) {
        dispatch(next);
        next = queuedCommands.shift();
      }
      if (disposed) queuedCommands.length = 0;
    } catch (error: unknown) {
      queuedCommands.length = 0;
      throw error;
    } finally {
      dispatching = false;
    }
  };

  return Object.freeze({
    read: () => snapshot,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    send,
  });
}
