const API_URL = "";

export interface SessionSummary {
  id: string;
  title: string | null;
  updated_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ChatRequest {
  session_id?: string;
  message: string;
  filters: { collections: string[] };
}

export interface ChatResponse {
  session_id: string;
  message_id: string;
  answer: string;
  sources: unknown[];
  title: string | null;
}

export async function sendMessage(
  token: string,
  payload: ChatRequest,
): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/v1/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error((error as { detail?: string }).detail ?? `API error ${res.status}`);
  }

  return res.json();
}

export async function streamMessage(
  token: string,
  payload: ChatRequest,
  onToken: (text: string) => void,
): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/v1/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error((error as { detail?: string }).detail ?? `API error ${res.status}`);
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = JSON.parse(line.slice(6)) as
        | { type: "text"; text: string }
        | { type: "done"; session_id: string; message_id: string; sources: unknown[]; title: string | null }
        | { type: "error"; detail: string };

      if (data.type === "text") {
        onToken(data.text);
      } else if (data.type === "done") {
        return { session_id: data.session_id, message_id: data.message_id, answer: "", sources: data.sources, title: data.title };
      } else if (data.type === "error") {
        throw new Error(data.detail ?? "Streaming error");
      }
    }
  }

  throw new Error("Stream ended without completion");
}

export async function getSessions(token: string): Promise<SessionSummary[]> {
  const res = await fetch(`${API_URL}/v1/sessions`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json();
  return (data as { sessions: SessionSummary[] }).sessions;
}

export async function getSessionMessages(
  token: string,
  sessionId: string,
): Promise<ChatMessage[]> {
  const res = await fetch(`${API_URL}/v1/sessions/${sessionId}/messages`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json();
  return (data as { messages: ChatMessage[] }).messages;
}

// ── V2 Search ──────────────────────────────────────────────────────────────

export interface ChunkSource {
  collection: string;
  document_title: string;
  author: string | null;
  reference: string | null;
  document_id: string;
  position: number | null;
  anchor?: string | null;
  chapter_key?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface ChunkResult {
  chunk_id: string;
  content: string;
  source: ChunkSource;
  reranker_score: number | null;
  explanation: string | null;
}

export interface SearchFilters {
  collections: string[];
  translation?: string;
}

export interface SearchSummaryV2 {
  id: string;
  query: string;
  filters: Record<string, unknown> | null;
  result_count: number | null;
  created_at: string;
}

export interface SearchHistoryPage {
  searches: SearchSummaryV2[];
  next_cursor: string | null;
}

export interface SearchResultsResponse {
  search_id: string;
  query: string;
  filters: Record<string, unknown> | null;
  results: ChunkResult[];
  restore_status: "complete" | "results_unavailable";
  expected_result_count: number;
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

// ── V2 Documents ───────────────────────────────────────────────────────────

export interface DocumentInfo {
  id: string;
  collection: string;
  title: string;
  author: string | null;
  year: number | null;
  translation?: string | null;
  metadata: Record<string, unknown> | null;
  chunk_count: number;
}

export interface ReaderPassage {
  id: string;
  anchor: string;
  chapter_key: string;
  chapter_label: string;
  unit_label: string | null;
  reference: string | null;
  content: string;
}

export interface ReaderChapter {
  document: DocumentInfo;
  chapter_key: string;
  chapter_label: string;
  passages: ReaderPassage[];
  prev_chapter_key: string | null;
  next_chapter_key: string | null;
  highlight_anchor: string | null;
}

export interface TocEntry {
  chapter_key: string;
  chapter_label: string;
}

export interface TocResponse {
  document: DocumentInfo;
  chapters: TocEntry[];
}

// ── V2 Bookmarks ───────────────────────────────────────────────────────────

export interface BookmarkChunkInfo {
  content: string;
  source: {
    collection: string;
    document_title: string;
    author: string | null;
    reference: string | null;
    document_id: string;
    anchor: string | null;
    chapter_key: string | null;
  };
}

export interface Bookmark {
  id: string;
  chunk_id: string;
  created_at: string;
  note: string | null;
  chunk: BookmarkChunkInfo | null;
}

// ── V2 Preferences ─────────────────────────────────────────────────────────

export interface Preferences {
  preferred_translation: string;
  default_collections: string[];
  default_quota: number;
  theme: "dark" | "light";
}

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

export async function streamSearch(
  token: string,
  query: string,
  filters: SearchFilters,
  quota: number,
  callbacks: SearchStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/v1/search`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ query, filters, quota }),
      signal,
    });
  } catch (err) {
    if ((err as DOMException).name === "AbortError") return;
    throw err;
  }

  if (!res.ok) {
    if (res.status === 429) {
      const retryAfter = res.headers.get("Retry-After");
      const body = await res.json().catch(() => ({})) as { detail?: string };
      const limitType = (body.detail ?? "").toLowerCase().includes("daily") ? "daily" : "per_minute";
      callbacks.onRateLimit(retryAfter ? parseInt(retryAfter, 10) : null, limitType);
      return;
    }
    const error = await res.json().catch(() => ({}));
    callbacks.onError((error as { detail?: string }).detail ?? `API error ${res.status}`);
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let terminalEventReceived = false;

  // The backend keeps this stream open well past the "done" event to stream
  // per-chunk explanations one at a time — so an abort (e.g. the user starting
  // a new search) very often lands while a reader.read() is still pending.
  // That rejects with an AbortError same as the initial fetch() above; without
  // this try/catch it propagates uncaught out of streamSearch and gets treated
  // as a real search failure by the caller.
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (signal?.aborted) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const event = JSON.parse(line.slice(6)) as
            | { type: "chunk" } & ChunkResult & { reranker_score: number }
            | { type: "explanation_delta"; chunk_id: string; delta: string }
            | { type: "done"; search_id: string | null; persisted?: boolean; result_count: number; outcome?: SearchOutcome; collection_outcomes?: Record<string, CollectionOutcome> }
            | { type: "error"; detail: string; code?: string; stage?: string; collection_outcomes?: Record<string, CollectionOutcome> }
            | { type: "status"; phase: "searching" | "ranking"; collections?: string[] };

          if (event.type === "chunk") {
            callbacks.onChunk({
              chunk_id: event.chunk_id,
              content: event.content,
              source: event.source,
              reranker_score: event.reranker_score ?? null,
              explanation: null,
            });
          } else if (event.type === "explanation_delta") {
            callbacks.onExplanationDelta(event.chunk_id, event.delta);
          } else if (event.type === "done") {
            terminalEventReceived = true;
            callbacks.onDone(
              event.search_id,
              event.result_count,
              event.outcome ?? (event.result_count > 0 ? "success" : "no_candidates"),
              event.collection_outcomes ?? {},
              event.persisted ?? Boolean(event.search_id),
            );
          } else if (event.type === "error") {
            terminalEventReceived = true;
            callbacks.onError(
              event.detail ?? "Search failed",
              event.code,
              event.stage,
              event.collection_outcomes,
            );
          } else if (event.type === "status") {
            callbacks.onStatus?.(event.phase, event.collections);
          } else {
            throw new Error("The search service sent an unknown stream event.");
          }
        } catch (err) {
          if (err instanceof SyntaxError) {
            throw new Error("The search service sent an invalid stream event.");
          }
          throw err;
        }
      }
    }
  } catch (err) {
    if ((err as DOMException).name === "AbortError") return;
    if (terminalEventReceived) return;
    throw err;
  }
  if (!signal?.aborted && !terminalEventReceived) {
    callbacks.onError(
      "The connection closed before the search finished.",
      "stream_interrupted",
      "connection",
    );
  }
}

export async function streamGuestSearch(
  sessionToken: string,
  query: string,
  filters: SearchFilters,
  quota: number,
  callbacks: SearchStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/v1/search/guest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, filters, quota, session_token: sessionToken }),
      signal,
    });
  } catch (err) {
    if ((err as DOMException).name === "AbortError") return;
    throw err;
  }

  if (!res.ok) {
    if (res.status === 429) {
      const body = await res.json().catch(() => ({})) as { detail?: string };
      if ((body.detail ?? "") === "trial_exhausted") {
        callbacks.onError("trial_exhausted");
        return;
      }
      callbacks.onRateLimit(null, "per_minute");
      return;
    }
    const error = await res.json().catch(() => ({}));
    callbacks.onError((error as { detail?: string }).detail ?? `API error ${res.status}`);
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let terminalEventReceived = false;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (signal?.aborted) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;
        let evt: Record<string, unknown>;
        try {
          evt = JSON.parse(raw);
        } catch {
          throw new Error("The search service sent an invalid stream event.");
        }

        const type = evt.type as string;
        if (type === "status" && callbacks.onStatus) {
          callbacks.onStatus(
            evt.phase as "searching" | "ranking",
            evt.collections as string[] | undefined,
          );
        } else if (type === "chunk") {
          callbacks.onChunk(evt as unknown as ChunkResult);
        } else if (type === "results_ready") {
          callbacks.onResultsReady?.(evt.result_count as number);
        } else if (type === "explanation_delta") {
          callbacks.onExplanationDelta(evt.chunk_id as string, evt.delta as string);
        } else if (type === "done") {
          terminalEventReceived = true;
          callbacks.onDone(
            (evt.search_id as string | null | undefined) ?? null,
            evt.result_count as number,
            (evt.outcome as SearchOutcome | undefined)
              ?? ((evt.result_count as number) > 0 ? "success" : "no_candidates"),
            (evt.collection_outcomes as Record<string, CollectionOutcome> | undefined) ?? {},
            (evt.persisted as boolean | undefined) ?? Boolean(evt.search_id),
          );
        } else if (type === "error") {
          terminalEventReceived = true;
          callbacks.onError(
            evt.detail as string,
            evt.code as string | undefined,
            evt.stage as string | undefined,
            evt.collection_outcomes as Record<string, CollectionOutcome> | undefined,
          );
        } else {
          throw new Error("The search service sent an unknown stream event.");
        }
      }
    }
  } catch (err) {
    if ((err as DOMException).name !== "AbortError" && !terminalEventReceived) throw err;
  }
  if (!signal?.aborted && !terminalEventReceived) {
    callbacks.onError(
      "The connection closed before the search finished.",
      "stream_interrupted",
      "connection",
    );
  }
}

export class GuestClaimHttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "GuestClaimHttpError";
  }
}

export async function claimGuestSession(
  token: string,
  sessionToken: string,
  savedChunkIds: string[],
): Promise<{ searches_imported: number; passages_saved: number }> {
  const res = await fetch(`${API_URL}/v1/guest/claim`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ session_token: sessionToken, saved_chunk_ids: savedChunkIds }),
  });
  if (!res.ok) {
    let message = `API error ${res.status}`;
    try {
      const body = await res.json() as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {}
    throw new GuestClaimHttpError(res.status, message);
  }
  return res.json();
}

export async function getSearchHistory(token: string): Promise<SearchSummaryV2[]> {
  const page = await getSearchHistoryPage(token);
  return page.searches;
}

export async function getSearchHistoryPage(
  token: string,
  options: { cursor?: string; limit?: number; query?: string } = {},
): Promise<SearchHistoryPage> {
  const params = new URLSearchParams();
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.limit) params.set("limit", String(options.limit));
  if (options.query?.trim()) params.set("q", options.query.trim());
  const query = params.toString();
  const res = await fetch(`${API_URL}/v1/searches${query ? `?${query}` : ""}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json() as SearchHistoryPage;
  return { searches: data.searches, next_cursor: data.next_cursor ?? null };
}

export async function deleteSearch(token: string, searchId: string): Promise<void> {
  const res = await fetch(`${API_URL}/v1/searches/${searchId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  // Deletion is intentionally idempotent on the client. The same history row
  // can be visible in both the desktop sidebar and the full History page.
  if (res.status === 404) return;
  if (!res.ok) throw new Error(`API error ${res.status}`);
}

export class SearchRestoreHttpError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "SearchRestoreHttpError";
  }
}

export async function getSearchResults(
  token: string,
  searchId: string,
  signal?: AbortSignal,
  timeoutMs = 10_000,
): Promise<SearchResultsResponse> {
  const controller = new AbortController();
  let timedOut = false;
  const forwardAbort = () => controller.abort(signal?.reason);
  if (signal?.aborted) forwardAbort();
  else signal?.addEventListener("abort", forwardAbort, { once: true });
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);

  try {
    const res = await fetch(`${API_URL}/v1/searches/${searchId}/results`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({})) as { detail?: unknown };
      const detail = typeof body.detail === "string" ? body.detail : `API error ${res.status}`;
      throw new SearchRestoreHttpError(res.status, detail);
    }
    return await res.json() as SearchResultsResponse;
  } catch (error) {
    if (timedOut) {
      const timeoutError = new Error("This saved search took too long to load. Please try again.");
      timeoutError.name = "TimeoutError";
      throw timeoutError;
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", forwardAbort);
  }
}

export async function getDocument(token: string, docId: string): Promise<DocumentInfo> {
  const res = await fetch(`${API_URL}/v1/documents/${docId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<DocumentInfo>;
}

function readerHeaders(token: string, guestToken?: string): HeadersInit {
  return guestToken
    ? { "x-theocorpus-guest-token": guestToken }
    : { Authorization: `Bearer ${token}` };
}

export async function getToc(token: string, docId: string, signal?: AbortSignal, guestToken?: string): Promise<TocResponse> {
  const res = await fetch(`${API_URL}/v1/documents/${docId}/toc`, {
    headers: readerHeaders(token, guestToken),
    signal,
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<TocResponse>;
}

export async function getReaderChapter(
  token: string,
  docId: string,
  opts: { anchor?: string; chapter?: string; signal?: AbortSignal; guestToken?: string },
): Promise<ReaderChapter> {
  const params = new URLSearchParams();
  if (opts.anchor) params.set("anchor", opts.anchor);
  if (opts.chapter) params.set("chapter", opts.chapter);
  const qs = params.toString();
  const res = await fetch(`${API_URL}/v1/documents/${docId}/reader${qs ? `?${qs}` : ""}`, {
    headers: readerHeaders(token, opts.guestToken),
    signal: opts.signal,
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<ReaderChapter>;
}

// ── Reading progress ───────────────────────────────────────────────────────

export interface ReadingProgress {
  document_id: string;
  chapter_key: string;
  chapter_label: string;
  anchor: string | null;
  updated_at: string;
  collection: string;
  document_title: string;
  author: string | null;
}

export async function listReadingProgress(token: string, limit = 6, signal?: AbortSignal): Promise<ReadingProgress[]> {
  const res = await fetch(`${API_URL}/v1/reading-progress?limit=${limit}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json() as { items: ReadingProgress[] };
  return data.items;
}

export async function getReadingProgress(
  token: string,
  docId: string,
  signal?: AbortSignal,
): Promise<ReadingProgress | null> {
  const res = await fetch(`${API_URL}/v1/reading-progress/${docId}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<ReadingProgress>;
}

export async function putReadingProgress(
  token: string,
  docId: string,
  chapterKey: string,
  anchor?: string | null,
): Promise<ReadingProgress> {
  const res = await fetch(`${API_URL}/v1/reading-progress/${docId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ chapter_key: chapterKey, anchor: anchor ?? null }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<ReadingProgress>;
}

// ── Product feedback ───────────────────────────────────────────────────────

export type ProductFeedbackCategory = "bug" | "content" | "feature" | "general";

export interface ProductFeedbackInput {
  category: ProductFeedbackCategory;
  message: string;
  contact_allowed: boolean;
  route?: string;
  viewport_width?: number;
  viewport_height?: number;
  search_id?: string;
  chunk_id?: string;
  document_id?: string;
  error_code?: "auth_error" | "network_error" | "rate_limit" | "restore_not_found" | "restore_unavailable" | "server_error" | "stream_interrupted" | "unknown";
}

export async function submitProductFeedback(
  token: string,
  input: ProductFeedbackInput,
): Promise<{ feedback_id: string }> {
  const res = await fetch(`${API_URL}/v1/product-feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(body.detail ?? `API error ${res.status}`);
  }
  return res.json() as Promise<{ feedback_id: string }>;
}

const BOOKMARKS_CACHE_TTL_MS = 30_000;
const BOOKMARK_REQUEST_TIMEOUT_MS = 10_000;
const bookmarkMutations = new Map<string, Set<Promise<unknown>>>();

function bookmarkScope(token: string): string {
  try {
    const payload = token.split(".")[1];
    if (!payload) return `token:${token}`;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
    const subject = (JSON.parse(atob(padded)) as { sub?: unknown }).sub;
    return typeof subject === "string" && subject ? `user:${subject}` : `token:${token}`;
  } catch {
    return `token:${token}`;
  }
}

async function fetchBookmarkEndpoint(url: string, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BOOKMARK_REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("Bookmark request timed out. Please try again.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function trackBookmarkMutation<T>(token: string, mutation: Promise<T>): Promise<T> {
  const scope = bookmarkScope(token);
  let active = bookmarkMutations.get(scope);
  if (!active) {
    active = new Set();
    bookmarkMutations.set(scope, active);
  }
  active.add(mutation);
  const cleanup = () => {
    active.delete(mutation);
    if (active.size === 0) bookmarkMutations.delete(scope);
    invalidateBookmarksCache(token);
  };
  void mutation.then(cleanup, cleanup);
  return mutation;
}

export async function getBookmarks(token: string, forceRefresh = false): Promise<Bookmark[]> {
  const scope = bookmarkScope(token);
  const activeMutations = bookmarkMutations.get(scope);
  if (activeMutations?.size) {
    await Promise.allSettled([...activeMutations]);
    return getBookmarks(token, forceRefresh);
  }
  if (bookmarksCacheScope !== scope) {
    bookmarksCache = null;
    bookmarksRequest = null;
    bookmarksRequestScope = null;
    bookmarksCacheScope = scope;
    bookmarksCacheUpdatedAt = 0;
    bookmarksCacheGeneration += 1;
  } else if (forceRefresh) {
    bookmarksCache = null;
    bookmarksRequest = null;
    bookmarksRequestScope = null;
    bookmarksCacheUpdatedAt = 0;
    bookmarksCacheGeneration += 1;
  }
  if (
    !forceRefresh
    && bookmarksCache
    && Date.now() - bookmarksCacheUpdatedAt < BOOKMARKS_CACHE_TTL_MS
  ) return bookmarksCache;
  if (bookmarksRequest && bookmarksRequestScope === scope) return bookmarksRequest;
  const generation = bookmarksCacheGeneration;
  const request = fetchBookmarks(token).then((bookmarks) => {
    if (bookmarksCacheScope === scope && bookmarksCacheGeneration !== generation) {
      if (bookmarksRequest === request) {
        bookmarksRequest = null;
        bookmarksRequestScope = null;
      }
      return getBookmarks(token);
    }
    if (bookmarksCacheScope === scope) {
      bookmarksCache = bookmarks;
      bookmarksCacheUpdatedAt = Date.now();
    }
    return bookmarks;
  });
  bookmarksRequest = request;
  bookmarksRequestScope = scope;
  try {
    return await request;
  } finally {
    if (bookmarksRequest === request) {
      bookmarksRequest = null;
      bookmarksRequestScope = null;
    }
  }
}

let bookmarksCache: Bookmark[] | null = null;
let bookmarksRequest: Promise<Bookmark[]> | null = null;
let bookmarksCacheScope: string | null = null;
let bookmarksRequestScope: string | null = null;
let bookmarksCacheGeneration = 0;
let bookmarksCacheUpdatedAt = 0;

async function fetchBookmarks(token: string): Promise<Bookmark[]> {
  const res = await fetchBookmarkEndpoint(`${API_URL}/v1/bookmarks`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json() as { bookmarks: Bookmark[] };
  return data.bookmarks;
}

export function invalidateBookmarksCache(token?: string): void {
  if (token && bookmarksCacheScope !== bookmarkScope(token)) return;
  bookmarksCache = null;
  bookmarksCacheUpdatedAt = 0;
  bookmarksRequest = null;
  bookmarksRequestScope = null;
  bookmarksCacheGeneration += 1;
}

export async function addBookmark(token: string, chunkId: string): Promise<{ id: string; created_at: string }> {
  invalidateBookmarksCache(token);
  return trackBookmarkMutation(token, (async () => {
    const res = await fetchBookmarkEndpoint(`${API_URL}/v1/bookmarks`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ chunk_id: chunkId }),
    });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json() as Promise<{ id: string; chunk_id: string; created_at: string }>;
  })());
}

export async function removeBookmark(token: string, bookmarkId: string): Promise<void> {
  invalidateBookmarksCache(token);
  return trackBookmarkMutation(token, (async () => {
    const res = await fetchBookmarkEndpoint(`${API_URL}/v1/bookmarks/${bookmarkId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error(`API error ${res.status}`);
  })());
}

export async function updateBookmarkNote(
  token: string,
  bookmarkId: string,
  note: string | null,
): Promise<void> {
  invalidateBookmarksCache(token);
  return trackBookmarkMutation(token, (async () => {
    const res = await fetchBookmarkEndpoint(`${API_URL}/v1/bookmarks/${bookmarkId}`, {
      method: "PATCH",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ note }),
    });
    if (!res.ok) throw new Error(`Failed to update note: ${res.status}`);
  })());
}

export async function submitLabel(
  token: string,
  chunkId: string,
  label: "up" | "down",
  searchId: string,
): Promise<void> {
  const res = await fetch(`${API_URL}/v1/labels`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ chunk_id: chunkId, label, search_id: searchId }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
}

export async function getPreferences(token: string): Promise<Preferences> {
  const res = await fetch(`${API_URL}/v1/preferences`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<Preferences>;
}

export async function updatePreferences(token: string, update: Partial<Preferences>): Promise<Preferences> {
  const res = await fetch(`${API_URL}/v1/preferences`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(update),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<Preferences>;
}

// ── V2 Sources ─────────────────────────────────────────────────────────────

export interface SourceDocument {
  id: string;
  collection: string;
  title: string;
  author: string | null;
  year: number | null;
  translation: string | null;
  metadata: Record<string, unknown> | null;
  chunk_count: number;
}

export async function getSources(token: string): Promise<SourceDocument[]> {
  if (sourcesCache) return sourcesCache;
  if (sourcesRequest) return sourcesRequest;
  sourcesRequest = fetchSources(token);
  try {
    sourcesCache = await sourcesRequest;
    return sourcesCache;
  } finally {
    sourcesRequest = null;
  }
}

let sourcesCache: SourceDocument[] | null = null;
let sourcesRequest: Promise<SourceDocument[]> | null = null;

async function fetchSources(token: string): Promise<SourceDocument[]> {
  const res = await fetch(`${API_URL}/v1/sources`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json() as { sources: SourceDocument[] };
  return data.sources;
}

// ── V2 Evaluate (Custom Source Scores) ────────────────────────────────────

export class EvaluateRateLimitError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EvaluateRateLimitError";
  }
}

export interface CollectionScore {
  collection: string;
  score: number;
}

export interface EvaluateResponse {
  query: string;
  remaining: number;
  scores: CollectionScore[];
}

export async function evaluateCollections(
  token: string,
  query: string,
): Promise<EvaluateResponse> {
  const res = await fetch(`${API_URL}/v1/evaluate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) {
    if (res.status === 429) {
      throw new EvaluateRateLimitError("Daily evaluation limit reached");
    }
    const error = await res.json().catch(() => ({}));
    throw new Error(
      (error as { detail?: string }).detail ?? `API error ${res.status}`,
    );
  }
  return res.json() as Promise<EvaluateResponse>;
}

interface ExplainCallbacks {
  onExplanation: (collection: string, explanation: string) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

export async function streamExplanations(
  token: string,
  query: string,
  scores: CollectionScore[],
  callbacks: ExplainCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/v1/evaluate/explain`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ query, scores }),
      signal,
    });
  } catch {
    if (signal?.aborted) return;
    callbacks.onError("Explanation stream failed");
    return;
  }

  if (!res.ok || !res.body) {
    callbacks.onError("Explanation stream failed");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const lines = part.trim().split("\n");
        let event = "";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) event = line.slice(7).trim();
          if (line.startsWith("data: ")) data = line.slice(6).trim();
        }
        if (event === "explanation" && data) {
          try {
            const parsed = JSON.parse(data) as { collection: string; explanation: string };
            callbacks.onExplanation(parsed.collection, parsed.explanation);
          } catch { /* malformed line — skip */ }
        } else if (event === "done") {
          callbacks.onDone();
          return;
        } else if (event === "error" && data) {
          try {
            const parsed = JSON.parse(data) as { message?: string };
            callbacks.onError(parsed.message ?? "Explanation failed");
          } catch {
            callbacks.onError("Explanation failed");
          }
          return;
        }
      }
    }
    callbacks.onDone();
  } catch {
    if (signal?.aborted) return;
    callbacks.onError("Explanation stream interrupted");
  }
}
