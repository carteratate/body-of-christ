import type {
  ChunkResult,
  CollectionOutcome,
  SearchOutcome,
} from "@/lib/search-stream";

export type Audience = "authenticated" | "guest";

/** Domain-facing view of the existing transport payload; no duplicate shape. */
export type Passage = Readonly<ChunkResult>;

export interface SearchRequest {
  readonly query: string;
  readonly collections: readonly string[];
  readonly translation: string;
  readonly quota: number;
  readonly origin: "fresh" | "explore";
  readonly exploreLabel?: string;
}

export type SearchPhase = "searching" | "ranking";

export interface SearchRateLimit {
  readonly type: "per_minute" | "daily";
  readonly retryAfter: number | null;
  readonly open: boolean;
}

export interface SearchCompletionFailure {
  readonly message: string;
  readonly code: string | null;
  readonly stage: string | null;
  readonly collectionOutcomes: Readonly<Record<string, CollectionOutcome>>;
  readonly rateLimit: SearchRateLimit | null;
}

export type SearchTransportState =
  | { readonly status: "preparing" }
  | { readonly status: "searching"; readonly phase: SearchPhase }
  | {
      readonly status: "ranked-ready";
      readonly resultCount: number;
      readonly completionFailure: SearchCompletionFailure | null;
    }
  | {
      readonly status: "complete";
      readonly searchId: string | null;
      readonly resultCount: number;
      readonly outcome: SearchOutcome;
      readonly collectionOutcomes: Readonly<Record<string, CollectionOutcome>>;
      readonly persisted: boolean;
    };

export type SearchPresentationState =
  | {
      readonly status: "animating";
      readonly filtersReady: boolean;
      readonly resultsReady: boolean;
    }
  | { readonly status: "fading"; readonly filtersReady: true }
  | { readonly status: "revealed"; readonly filtersReady: true };

interface SnapshotCapabilities {
  readonly canSubmit: boolean;
  readonly canRetry: boolean;
}

export interface IdleSnapshot extends SnapshotCapabilities {
  readonly status: "idle";
  readonly runId: number;
  readonly canSubmit: true;
  readonly canRetry: false;
}

export interface RestoringSnapshot extends SnapshotCapabilities {
  readonly status: "restoring";
  readonly runId: number;
  readonly searchId: string;
  readonly canSubmit: true;
  readonly canRetry: false;
}

export interface ActiveSearchSnapshot extends SnapshotCapabilities {
  readonly status: "active-search";
  readonly runId: number;
  readonly audience: Audience;
  readonly request: SearchRequest;
  readonly transport: SearchTransportState;
  readonly presentation: SearchPresentationState;
  /** Passages are empty until the owning animation reaches ready-to-reveal. */
  readonly passages: readonly Passage[];
  readonly saveWarning: string | null;
  readonly canSubmit: true;
  readonly canRetry: false;
}

export interface RestoredResultsSnapshot extends SnapshotCapabilities {
  readonly status: "restored-results";
  readonly runId: number;
  readonly searchId: string;
  readonly request: SearchRequest;
  readonly passages: readonly Passage[];
  readonly warning: string | null;
  readonly canSubmit: true;
  readonly canRetry: false;
}

export interface SearchFailure {
  readonly kind: "search" | "restore";
  readonly message: string;
  readonly code: string | null;
  readonly stage: string | null;
  readonly collectionOutcomes: Readonly<Record<string, CollectionOutcome>>;
  readonly rateLimit: SearchRateLimit | null;
}

export interface FailureSnapshot extends SnapshotCapabilities {
  readonly status: "failure";
  readonly runId: number;
  readonly request: SearchRequest | null;
  readonly restoreId: string | null;
  readonly failure: SearchFailure;
  readonly canSubmit: true;
  readonly canRetry: boolean;
}

export type SearchExperienceSnapshot =
  | IdleSnapshot
  | RestoringSnapshot
  | ActiveSearchSnapshot
  | RestoredResultsSnapshot
  | FailureSnapshot;

export type AnimationMilestone =
  | "filters-ready"
  | "ready-to-reveal"
  | "fade-complete";

export type SearchExperienceCommand =
  | { readonly type: "submit"; readonly request: SearchRequest }
  | { readonly type: "restore"; readonly searchId: string }
  | { readonly type: "retry" }
  | { readonly type: "animation"; readonly runId: number; readonly milestone: AnimationMilestone }
  | { readonly type: "dismiss-rate-limit" }
  | { readonly type: "guest-visible-collections-changed"; readonly collections: readonly string[] }
  | { readonly type: "cancel" }
  | { readonly type: "reset" }
  | { readonly type: "identity-changed"; readonly userId: string | null }
  | { readonly type: "dispose" };

export interface SearchTransportCallbacks {
  readonly onStatus: (phase: SearchPhase) => void;
  readonly onPassage: (passage: Passage) => void;
  readonly onResultsReady: (resultCount: number) => void;
  readonly onExplanationDelta: (passageId: string, delta: string) => void;
  readonly onDone: (
    searchId: string | null,
    resultCount: number,
    outcome: SearchOutcome,
    collectionOutcomes: Record<string, CollectionOutcome>,
    persisted: boolean,
  ) => void;
  readonly onError: (
    message: string,
    code?: string,
    stage?: string,
    collectionOutcomes?: Record<string, CollectionOutcome>,
  ) => void;
  readonly onRateLimit: (
    retryAfter: number | null,
    type: "per_minute" | "daily",
  ) => void;
}

export type AudienceAdapter =
  | {
      readonly kind: "authenticated";
      readonly search: (
        credential: string,
        request: SearchRequest,
        callbacks: SearchTransportCallbacks,
        signal: AbortSignal,
      ) => Promise<void>;
    }
  | {
      readonly kind: "guest";
      readonly search: (
        request: SearchRequest,
        callbacks: SearchTransportCallbacks,
        signal: AbortSignal,
      ) => Promise<void>;
    };

export interface SavedSearchResult {
  readonly searchId: string;
  readonly request: SearchRequest;
  readonly passages: readonly Passage[];
  readonly warning: string | null;
}

interface SharedSearchExperiencePorts {
  readonly analytics?: {
    readonly searchCompleted: (event: SearchCompletedEvent) => void | Promise<void>;
    readonly searchFailed: (event: SearchFailedEvent) => void | Promise<void>;
  };
}

export interface AuthenticatedSearchExperiencePorts extends SharedSearchExperiencePorts {
  readonly audience: Extract<AudienceAdapter, { readonly kind: "authenticated" }>;
  readonly credentials: { readonly current: () => string | null };
  readonly savedSearch?: {
    readonly restore: (
      credential: string,
      searchId: string,
      signal: AbortSignal,
    ) => Promise<SavedSearchResult>;
  };
  readonly pendingHistory?: {
    readonly begin: (entryId: string, query: string) => void | Promise<void>;
    readonly clear: (entryId: string) => void | Promise<void>;
    readonly refresh: () => void | Promise<void>;
  };
  readonly ids?: { readonly pendingEntry: () => string };
  readonly guestAccess?: never;
  readonly guestContinuity?: never;
  readonly time?: never;
}

export interface GuestSearchExperiencePorts extends SharedSearchExperiencePorts {
  readonly audience: Extract<AudienceAdapter, { readonly kind: "guest" }>;
  readonly guestAccess?: {
    readonly canSearch: () => boolean;
    readonly requestSignup: (reason: "limit") => void | Promise<void>;
    readonly recordCompletedSearch: (resultCount: number) => void | Promise<void>;
  };
  readonly guestContinuity?: {
    readonly restore?: () => GuestContinuitySnapshot | null;
    readonly save: (snapshot: GuestContinuitySnapshot) => void | Promise<void>;
    readonly clear: () => void | Promise<void>;
  };
  readonly time?: { readonly now: () => number };
  readonly credentials?: never;
  readonly savedSearch?: never;
  readonly pendingHistory?: never;
  readonly ids?: never;
}

export type SearchExperiencePorts =
  | AuthenticatedSearchExperiencePorts
  | GuestSearchExperiencePorts;

export interface GuestContinuitySnapshot {
  readonly savedAt: number;
  readonly request: SearchRequest;
  readonly searchId: string | null;
  readonly passages: readonly Passage[];
  readonly outcome: SearchOutcome | null;
  readonly collectionOutcomes: Readonly<Record<string, CollectionOutcome>>;
  readonly visibleCollections?: readonly string[];
}

export interface SearchCompletedEvent {
  readonly audience: Audience;
  readonly request: SearchRequest;
  readonly resultCount: number;
  readonly outcome: SearchOutcome;
}

export interface SearchFailedEvent {
  readonly audience: Audience;
  readonly request: SearchRequest;
  readonly code: string | null;
}

export interface SearchExperience {
  readonly read: () => SearchExperienceSnapshot;
  readonly subscribe: (listener: () => void) => () => void;
  readonly send: (command: SearchExperienceCommand) => void;
}
