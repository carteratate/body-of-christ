import { parseFootnotes, type Footnote } from "./footnotes";
import { parseHeadings } from "./passage-headings";
import { readerAccessValue, type ReaderAccess } from "./reader-access";
import { parseFacts, type DocumentFacts } from "./attribution";
import { parsePassageCard, type PassageCard } from "./card-notes";
import {
  parsePassageLifecycle,
  type PassageStatus,
  type Redirect,
  type Tombstone,
} from "./corpus-lifecycle";

/**
 * "rejected": the passage states a position its own document rejects — a condemned
 * proposition, an opponent's speech, a Summa objection (corpus cleanup 2.4d). The UI
 * shows its `unit_label` above the text so it is never read as the document's teaching.
 */
export type PassageVoice = "rejected";

/** The voice a payload names, or null for anything else (the API sends only these). */
export function passageVoice(value: unknown): PassageVoice | null {
  return value === "rejected" ? value : null;
}

/** "ocr": the passage's text came from a scanned edition (corpus cleanup 1.2f). */
export type TextSource = "ocr";
/** "unofficial_english": a canon shown in the L’Osservatore Romano English; its Latin,
 *  at `official_latin_url`, is the official text (1.5b). */
export type TextStatus = "unofficial_english";

/** Where a passage's text came from, shown when it is opened (corpus cleanup 2.4f). */
export interface PassageTextLabels {
  text_source: TextSource | null;
  text_status: TextStatus | null;
  official_latin_url: string | null;
}

/**
 * The text labels a payload names: the known values only, and the Latin link only when
 * it is a web address. The one decoder for these fields; restored searches, bookmarks
 * and reader passages skip `consumeSearchStream`, so their components call it too.
 */
export function passageTextLabels(source: {
  text_source?: unknown;
  text_status?: unknown;
  official_latin_url?: unknown;
}): PassageTextLabels {
  const url = source.official_latin_url;
  return {
    text_source: source.text_source === "ocr" ? "ocr" : null,
    text_status: source.text_status === "unofficial_english" ? "unofficial_english" : null,
    official_latin_url: typeof url === "string" && /^https?:\/\//.test(url) ? url : null,
  };
}

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
  /** "excerpt": the document's rights are not cleared, so the card links to
   *  `source_url` instead of the reader (issue #265). Absent means full. */
  reader_access?: ReaderAccess | null;
  source_url?: string | null;
  /** The rights holder's credit line, shown right after an excerpt-only passage. */
  source_credit?: string | null;
  /** Translation, date, attribution, notes and credit (corpus cleanup 2.4a). Absent
   *  from an older API and when the facts query failed; the card then shows today's. */
  facts?: DocumentFacts | null;
  /** ISO 639 code; null means English. */
  language?: string | null;
  passage_note?: string | null;
  /** A quoted author (a Father in the Catena Aurea), shown instead of `author`. */
  passage_author?: string | null;
  /** See PassageVoice. Absent from an older API and for every passage until the
   *  corpus cleanup's Phase 4 apply. */
  voice?: PassageVoice | null;
  /** See PassageTextLabels. Absent from an older API and for every passage until the
   *  corpus cleanup's Phase 4 apply. */
  text_source?: TextSource | null;
  text_status?: TextStatus | null;
  official_latin_url?: string | null;
  /** The notes under the opened passage (corpus cleanup 4.4). Absent from an older API
   *  and for a passage whose document no 4.4 publish has written; the card then shows
   *  the fields above as before. */
  card?: PassageCard | null;
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
  /** The passage's footnotes, shown with it (issue #279). Absent means none. */
  footnotes?: Footnote[];
  /** Headings marked inside the passage (issue #445). Absent means none. Typed loosely
   *  because restored searches skip this decoder; `parseHeadings` checks it where shown. */
  headings?: unknown;
  /** A saved result whose passage left the corpus or moved (2.4a). "removed": the
   *  tombstone says why and `content` is empty. "moved": `content` and `source` are
   *  the passage it moved to. Absent means current. */
  status?: PassageStatus;
  tombstone?: Tombstone | null;
  redirect?: Redirect | null;
}

export type SearchOutcome = "success" | "degraded_success" | "no_candidates";

export type DeliveryOutcome = "complete" | "underfilled" | "minimum_floor";

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
    deliveryOutcome?: DeliveryOutcome,
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

export function isSearchOutcome(value: unknown): value is SearchOutcome {
  return SEARCH_OUTCOMES.has(value as SearchOutcome);
}

const COLLECTION_OUTCOMES = new Set<CollectionOutcome>([
  "results",
  "results_degraded",
  "no_candidates",
  "below_threshold",
  "retrieval_failed",
  "corpus_sync_failed",
  "ranking_failed",
]);

export function parseCollectionOutcomes(
  value: unknown,
): Record<string, CollectionOutcome> | null {
  if (!isRecord(value)) return null;
  const entries = Object.entries(value);
  if (!entries.every(([, outcome]) => COLLECTION_OUTCOMES.has(outcome as CollectionOutcome))) {
    return null;
  }
  return Object.fromEntries(entries) as Record<string, CollectionOutcome>;
}

const DELIVERY_OUTCOMES = new Set<DeliveryOutcome>([
  "complete",
  "underfilled",
  "minimum_floor",
]);

export function isDeliveryOutcome(value: unknown): value is DeliveryOutcome {
  return DELIVERY_OUTCOMES.has(value as DeliveryOutcome);
}

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

function optionalText(value: unknown): string | null {
  return typeof value === "string" ? value : null;
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
  return parseCollectionOutcomes(value) ?? invalid();
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
  const content = requiredString(event.content);

  return {
    chunk_id: requiredString(event.chunk_id),
    content,
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
      reader_access: readerAccessValue(source.reader_access),
      source_url: nullableString(source.source_url),
      source_credit: nullableString(source.source_credit),
      // Display-only extras: a malformed one is dropped, never the passage.
      facts: parseFacts(source.facts),
      language: optionalText(source.language),
      passage_note: optionalText(source.passage_note),
      passage_author: optionalText(source.passage_author),
      voice: passageVoice(source.voice),
      ...passageTextLabels(source),
      card: parsePassageCard(source.card),
    },
    reranker_score: nullableNumber(event.reranker_score),
    explanation: nullableString(event.explanation),
    context: normalizeContext(event.context),
    // Never fail a passage over its notes: a bad entry is dropped, not the passage.
    footnotes: parseFootnotes(event.footnotes, content),
    // Likewise headings (issue #445): sent only for a passage that has some.
    ...(event.headings !== undefined ? { headings: parseHeadings(event.headings, content) } : {}),
    ...parsePassageLifecycle(event),
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
      if (!isSearchOutcome(outcome)) invalid();
      if (event.persisted !== undefined && typeof event.persisted !== "boolean") invalid();
      if (event.delivery_outcome !== undefined && !isDeliveryOutcome(event.delivery_outcome)) invalid();
      state.terminal = "done";
      const completion = [
        searchId,
        resultCount,
        outcome as SearchOutcome,
        optionalCollectionOutcomes(event.collection_outcomes) ?? {},
        (event.persisted as boolean | undefined) ?? Boolean(searchId),
      ] as const;
      if (event.delivery_outcome === undefined) callbacks.onDone(...completion);
      else callbacks.onDone(...completion, event.delivery_outcome as DeliveryOutcome);
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
