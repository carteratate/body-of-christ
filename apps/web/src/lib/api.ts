const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

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
  translation: string;
}

export interface SearchSummaryV2 {
  id: string;
  query: string;
  filters: Record<string, unknown> | null;
  result_count: number | null;
  created_at: string;
}

export interface SearchResultsResponse {
  search_id: string;
  query: string;
  results: ChunkResult[];
}

// ── V2 Documents ───────────────────────────────────────────────────────────

export interface DocumentInfo {
  id: string;
  collection: string;
  title: string;
  author: string | null;
  year: number | null;
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
  onDone: (searchId: string, resultCount: number) => void;
  onError: (message: string) => void;
  onRateLimit: (retryAfter: number | null, limitType: "per_minute" | "daily") => void;
  onStatus?: (phase: "searching" | "ranking", collections?: string[]) => void;
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
            | { type: "done"; search_id: string; result_count: number }
            | { type: "error"; detail: string }
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
            callbacks.onDone(event.search_id, event.result_count);
          } else if (event.type === "error") {
            callbacks.onError(event.detail ?? "Search failed");
          } else if (event.type === "status") {
            callbacks.onStatus?.(event.phase, event.collections);
          }
        } catch {
          // malformed SSE line — skip
        }
      }
    }
  } catch (err) {
    if ((err as DOMException).name === "AbortError") return;
    throw err;
  }
}

export async function streamGuestSearch(
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
      body: JSON.stringify({ query, filters, quota }),
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
        try { evt = JSON.parse(raw); } catch { continue; }

        const type = evt.type as string;
        if (type === "status" && callbacks.onStatus) {
          callbacks.onStatus(
            evt.phase as "searching" | "ranking",
            evt.collections as string[] | undefined,
          );
        } else if (type === "chunk") {
          callbacks.onChunk(evt as unknown as ChunkResult);
        } else if (type === "explanation_delta") {
          callbacks.onExplanationDelta(evt.chunk_id as string, evt.delta as string);
        } else if (type === "done") {
          callbacks.onDone(evt.search_id as string, evt.result_count as number);
        } else if (type === "error") {
          callbacks.onError(evt.detail as string);
        }
      }
    }
  } catch (err) {
    if ((err as DOMException).name !== "AbortError") throw err;
  }
}

export async function getSearchHistory(token: string): Promise<SearchSummaryV2[]> {
  const res = await fetch(`${API_URL}/v1/searches`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json() as { searches: SearchSummaryV2[] };
  return data.searches;
}

export async function getSearchResults(token: string, searchId: string): Promise<SearchResultsResponse> {
  const res = await fetch(`${API_URL}/v1/searches/${searchId}/results`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<SearchResultsResponse>;
}

export async function getDocument(token: string, docId: string): Promise<DocumentInfo> {
  const res = await fetch(`${API_URL}/v1/documents/${docId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<DocumentInfo>;
}

export async function getToc(token: string, docId: string): Promise<TocResponse> {
  const res = await fetch(`${API_URL}/v1/documents/${docId}/toc`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<TocResponse>;
}

export async function getReaderChapter(
  token: string,
  docId: string,
  opts: { anchor?: string; chapter?: string },
): Promise<ReaderChapter> {
  const params = new URLSearchParams();
  if (opts.anchor) params.set("anchor", opts.anchor);
  if (opts.chapter) params.set("chapter", opts.chapter);
  const qs = params.toString();
  const res = await fetch(`${API_URL}/v1/documents/${docId}/reader${qs ? `?${qs}` : ""}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<ReaderChapter>;
}

export async function getBookmarks(token: string): Promise<Bookmark[]> {
  const res = await fetch(`${API_URL}/v1/bookmarks`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const data = await res.json() as { bookmarks: Bookmark[] };
  return data.bookmarks;
}

export async function addBookmark(token: string, chunkId: string): Promise<{ id: string; created_at: string }> {
  const res = await fetch(`${API_URL}/v1/bookmarks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ chunk_id: chunkId }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<{ id: string; created_at: string }>;
}

export async function removeBookmark(token: string, bookmarkId: string): Promise<void> {
  const res = await fetch(`${API_URL}/v1/bookmarks/${bookmarkId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
}

export async function updateBookmarkNote(
  token: string,
  bookmarkId: string,
  note: string | null,
): Promise<void> {
  const res = await fetch(`${API_URL}/v1/bookmarks/${bookmarkId}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error(`Failed to update note: ${res.status}`);
}

export async function submitLabel(
  token: string,
  chunkId: string,
  label: "up" | "down",
  searchId: string,
  rank: number,
): Promise<void> {
  const res = await fetch(`${API_URL}/v1/labels`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ chunk_id: chunkId, label, search_id: searchId, rank }),
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
