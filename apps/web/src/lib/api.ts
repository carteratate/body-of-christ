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
