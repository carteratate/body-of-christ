export interface ChunkSource {
  collection: string;
  document_title: string;
  author: string | null;
  reference: string | null;
  document_id: string;
  position: number | null;
  anchor?: string | null;
  chapter_key?: string | null;
  /**
   * The passage's role inside its document — "Objection 1", "I answer that",
   * "Reply to Objection 2", "Can. 1055 §1". Null for collections with no such
   * structure and for results saved before this field existed.
   *
   * A Summa objection is a position Aquinas states in order to refute. The UI must
   * identify it rather than presenting it as his teaching.
   */
  unit_label?: string | null;
  metadata?: Record<string, unknown> | null;
}

/** One passage attached to a matched Summa passage to make it intelligible. */
export interface ContextPart {
  content: string;
  reference: string | null;
  unit_label: string | null;
  anchor: string | null;
}

/**
 * What completes a matched Summa passage, and where it belongs on the card.
 *
 * `answered_by` attaches Aquinas's determination below a matched objection.
 * `answers` attaches the objection above a matched reply. Placement comes from this
 * relation alone; attached passages are presentation context, not scored passages.
 */
export interface AttachedContext {
  relation: "answered_by" | "answers";
  parts: ContextPart[];
}

export interface ChunkResult {
  chunk_id: string;
  content: string;
  source: ChunkSource;
  reranker_score: number | null;
  explanation: string | null;
  /** The passage completing this result, or null. See AttachedContext. */
  context?: AttachedContext | null;
}

export type SearchOutcome = "success" | "degraded_success" | "no_candidates";

export type CollectionOutcome =
  | "results"
  | "results_degraded"
  | "no_candidates"
  | "below_threshold"
  | "retrieval_failed"
  | "corpus_sync_failed"
  | "ranking_failed";

export interface SearchStreamCallbacks {
  onChunk: (chunk: ChunkResult) => void;
  onExplanationDelta: (chunkId: string, delta: string) => void;
  onDone: (
    searchId: string | null,
    resultCount: number,
    outcome: SearchOutcome,
    collectionOutcomes: Record<string, CollectionOutcome>,
    persisted: boolean,
  ) => void;
  onError: (
    message: string,
    code?: string,
    stage?: string,
    collectionOutcomes?: Record<string, CollectionOutcome>,
  ) => void;
  onRateLimit: (retryAfter: number | null, limitType: "per_minute" | "daily") => void;
  onStatus?: (phase: "searching" | "ranking", collections?: string[]) => void;
  onResultsReady?: (resultCount: number) => void;
}

export class SearchStreamProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SearchStreamProtocolError";
  }
}

const SEARCH_OUTCOMES = new Set<SearchOutcome>([
  "success",
  "degraded_success",
  "no_candidates",
]);

const COLLECTION_OUTCOMES = new Set<CollectionOutcome>([
  "results",
  "results_degraded",
  "no_candidates",
  "below_threshold",
  "retrieval_failed",
  "corpus_sync_failed",
  "ranking_failed",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalid(): never {
  throw new SearchStreamProtocolError("The search service sent an invalid stream event.");
}

function requiredString(value: unknown): string {
  if (typeof value !== "string") invalid();
  return value;
}

function nullableString(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  return requiredString(value);
}

function optionalString(value: unknown): string | undefined {
  if (value === undefined) return undefined;
  return requiredString(value);
}

function nullableNumber(value: unknown): number | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) invalid();
  return value;
}

function nonnegativeInteger(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) invalid();
  return value;
}

function optionalStringArray(value: unknown): string[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) invalid();
  return value;
}

function optionalCollectionOutcomes(
  value: unknown,
): Record<string, CollectionOutcome> | undefined {
  if (value === undefined) return undefined;
  if (!isRecord(value)) invalid();
  const entries = Object.entries(value);
  if (!entries.every(([, outcome]) => COLLECTION_OUTCOMES.has(outcome as CollectionOutcome))) {
    invalid();
  }
  return Object.fromEntries(entries) as Record<string, CollectionOutcome>;
}

function normalizeContext(value: unknown): AttachedContext | null {
  if (value === undefined || value === null) return null;
  if (!isRecord(value) || (value.relation !== "answered_by" && value.relation !== "answers")) {
    invalid();
  }
  if (!Array.isArray(value.parts)) invalid();
  return {
    relation: value.relation,
    parts: value.parts.map((part) => {
      if (!isRecord(part)) invalid();
      return {
        content: requiredString(part.content),
        reference: nullableString(part.reference),
        unit_label: nullableString(part.unit_label),
        anchor: nullableString(part.anchor),
      };
    }),
  };
}

function normalizePassage(event: Record<string, unknown>): ChunkResult {
  if (!isRecord(event.source)) invalid();
  const source = event.source;
  const metadata = source.metadata;
  if (metadata !== undefined && metadata !== null && !isRecord(metadata)) invalid();

  return {
    chunk_id: requiredString(event.chunk_id),
    content: requiredString(event.content),
    source: {
      collection: requiredString(source.collection),
      document_title: requiredString(source.document_title),
      author: nullableString(source.author),
      reference: nullableString(source.reference),
      document_id: requiredString(source.document_id),
      position: nullableNumber(source.position),
      anchor: nullableString(source.anchor),
      chapter_key: nullableString(source.chapter_key),
      unit_label: nullableString(source.unit_label),
      metadata: metadata ?? null,
    },
    reranker_score: nullableNumber(event.reranker_score),
    explanation: nullableString(event.explanation),
    context: normalizeContext(event.context),
  };
}

type TerminalState = "none" | "done" | "error";

function parseEvent(line: string): Record<string, unknown> | null {
  const normalized = line.endsWith("\r") ? line.slice(0, -1) : line;
  if (!normalized || normalized.startsWith(":")) return null;
  if (!normalized.startsWith("data:")) return null;
  const payload = normalized.slice(5).trimStart();
  if (!payload.trim()) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(payload);
  } catch {
    invalid();
  }
  if (!isRecord(parsed)) invalid();
  return parsed;
}

/** Consume TheoCorpus's single-line JSON data protocol from a successful response. */
export async function consumeSearchStream(
  body: ReadableStream<Uint8Array>,
  callbacks: SearchStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const state: { terminal: TerminalState } = { terminal: "none" };
  let cancellation: Promise<void> | undefined;

  const cancelReader = () => {
    cancellation ??= reader.cancel().then(() => undefined, () => undefined);
  };
  signal?.addEventListener("abort", cancelReader, { once: true });
  if (signal?.aborted) cancelReader();

  const dispatchLine = (line: string) => {
    const event = parseEvent(line);
    if (!event) return;
    const type = requiredString(event.type);

    if (state.terminal === "done" && type !== "explanation_delta") {
      throw new SearchStreamProtocolError(
        "The search service sent an event after search completion.",
      );
    }
    if (state.terminal === "error") {
      throw new SearchStreamProtocolError(
        "The search service sent conflicting terminal events.",
      );
    }

    if (type === "status") {
      if (event.phase !== "searching" && event.phase !== "ranking") invalid();
      callbacks.onStatus?.(event.phase, optionalStringArray(event.collections));
      return;
    }
    if (type === "chunk") {
      callbacks.onChunk(normalizePassage(event));
      return;
    }
    if (type === "explanation_delta") {
      callbacks.onExplanationDelta(
        requiredString(event.chunk_id),
        requiredString(event.delta),
      );
      return;
    }
    if (type === "results_ready") {
      callbacks.onResultsReady?.(nonnegativeInteger(event.result_count));
      return;
    }
    if (type === "done") {
      const resultCount = nonnegativeInteger(event.result_count);
      const searchId = nullableString(event.search_id);
      const outcome = event.outcome === undefined
        ? (resultCount > 0 ? "success" : "no_candidates")
        : event.outcome;
      if (!SEARCH_OUTCOMES.has(outcome as SearchOutcome)) invalid();
      if (event.persisted !== undefined && typeof event.persisted !== "boolean") invalid();
      state.terminal = "done";
      callbacks.onDone(
        searchId,
        resultCount,
        outcome as SearchOutcome,
        optionalCollectionOutcomes(event.collection_outcomes) ?? {},
        (event.persisted as boolean | undefined) ?? Boolean(searchId),
      );
      return;
    }
    if (type === "error") {
      state.terminal = "error";
      callbacks.onError(
        event.detail === undefined ? "Search failed" : requiredString(event.detail),
        optionalString(event.code),
        optionalString(event.stage),
        optionalCollectionOutcomes(event.collection_outcomes),
      );
      return;
    }
    throw new SearchStreamProtocolError("The search service sent an unknown stream event.");
  };

  try {
    while (!signal?.aborted) {
      let result: ReadableStreamReadResult<Uint8Array>;
      try {
        result = await reader.read();
      } catch (error) {
        if (signal?.aborted) return;
        if (state.terminal !== "none") return;
        throw error;
      }
      if (result.done) break;
      if (signal?.aborted) return;

      buffer += decoder.decode(result.value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) dispatchLine(line);
    }

    if (signal?.aborted) return;
    buffer += decoder.decode();
    if (buffer && state.terminal === "none") dispatchLine(buffer);
    if (state.terminal === "none") {
      callbacks.onError(
        "The connection closed before the search finished.",
        "stream_interrupted",
        "connection",
      );
    }
  } finally {
    signal?.removeEventListener("abort", cancelReader);
    await cancellation;
    reader.releaseLock();
  }
}
