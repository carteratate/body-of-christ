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

export interface ReaderChunk {
  id: string;
  position: number;
  reference: string | null;
  content: string;
}

export interface ReaderResponse {
  document: DocumentInfo;
  chunks: ReaderChunk[];
  highlight_chunk_id: string;
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
  chunk: BookmarkChunkInfo | null;
}

// ── V2 Preferences ─────────────────────────────────────────────────────────

export interface Preferences {
  preferred_translation: string;
  default_collections: string[];
  default_quota: number;
}

export interface SearchStreamCallbacks {
  onChunk: (chunk: ChunkResult) => void;
  onExplanation: (chunkId: string, explanation: string) => void;
  onDone: (searchId: string, resultCount: number) => void;
  onError: (message: string) => void;
  onRateLimit: (retryAfter: number | null) => void;
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
      callbacks.onRateLimit(retryAfter ? parseInt(retryAfter, 10) : null);
      return;
    }
    const error = await res.json().catch(() => ({}));
    callbacks.onError((error as { detail?: string }).detail ?? `API error ${res.status}`);
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

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
          | { type: "explanation"; chunk_id: string; explanation: string }
          | { type: "done"; search_id: string; result_count: number }
          | { type: "error"; detail: string };

        if (event.type === "chunk") {
          callbacks.onChunk({
            chunk_id: event.chunk_id,
            content: event.content,
            source: event.source,
            reranker_score: event.reranker_score ?? null,
            explanation: null,
          });
        } else if (event.type === "explanation") {
          callbacks.onExplanation(event.chunk_id, event.explanation);
        } else if (event.type === "done") {
          callbacks.onDone(event.search_id, event.result_count);
        } else if (event.type === "error") {
          callbacks.onError(event.detail ?? "Search failed");
        }
      } catch {
        // malformed SSE line — skip
      }
    }
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

export async function getReader(
  token: string,
  docId: string,
  chunkId: string,
  context = 10,
): Promise<ReaderResponse> {
  const url = `${API_URL}/v1/documents/${docId}/reader?chunk_id=${encodeURIComponent(chunkId)}&context=${context}`;
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<ReaderResponse>;
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

export async function submitFeedback(
  token: string,
  chunkId: string,
  feedback: "up" | "down",
  searchId?: string,
): Promise<void> {
  const res = await fetch(`${API_URL}/v1/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ chunk_id: chunkId, feedback, search_id: searchId }),
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
