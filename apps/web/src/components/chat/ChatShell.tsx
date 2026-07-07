"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { createClient } from "@/lib/supabase/client";
import {
  streamMessage,
  getSessions,
  getSessionMessages,
  type ChatMessage,
  type SessionSummary,
} from "@/lib/api";

export function ChatShell() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const pinnedToBottom = useRef(true);
  const isProgrammaticScroll = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pendingTokens = useRef("");
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    const supabase = createClient();

    supabase.auth.getSession().then(({ data }) => {
      setToken(data.session?.access_token ?? null);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_, session) => {
      setToken(session?.access_token ?? null);
      if (!session) router.replace("/login");
    });

    return () => subscription.unsubscribe();
  }, [router]);

  useEffect(() => {
    if (!token) return;
    getSessions(token).then(setSessions).catch(() => {});
  }, [token]);

  useEffect(() => {
    if (!pinnedToBottom.current) return;
    const el = scrollContainerRef.current;
    if (!el) return;
    isProgrammaticScroll.current = true;
    if (loading) {
      el.scrollTop = el.scrollHeight;
    } else {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
    requestAnimationFrame(() => { isProgrammaticScroll.current = false; });
  }, [messages, loading]);

  async function handleSend() {
    const text = input.trim();
    if (!text || !token || loading) return;

    setInput("");
    setError(null);
    pinnedToBottom.current = true;
    setMessages((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: "" }]);
    setLoading(true);

    try {
      const isNewSession = !sessionId;
      const res = await streamMessage(
        token,
        {
          session_id: sessionId ?? undefined,
          message: text,
          filters: { collections: [] },
        },
        (tokenText) => {
          pendingTokens.current += tokenText;
          if (rafRef.current === null) {
            rafRef.current = window.setTimeout(() => {
              const batch = pendingTokens.current;
              pendingTokens.current = "";
              rafRef.current = null;
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, content: last.content + batch };
                return updated;
              });
            }, 80);
          }
        },
      );
      setSessionId(res.session_id);
      if (isNewSession) {
        setSessions((prev) => [
          { id: res.session_id, title: res.title ?? null, updated_at: new Date().toISOString() },
          ...prev,
        ]);
      }
    } catch (err) {
      if (rafRef.current !== null) {
        clearTimeout(rafRef.current);
        rafRef.current = null;
      }
      pendingTokens.current = "";
      setMessages((prev) => prev.slice(0, -1));
      const message = err instanceof Error ? err.message : "Something went wrong.";
      if (message.includes("401")) {
        const supabase = createClient();
        await supabase.auth.signOut();
        return;
      }
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleLoadSession(id: string) {
    if (id === sessionId || loading || !token) return;
    try {
      const msgs = await getSessionMessages(token!, id);
      setSessionId(id);
      setMessages(msgs);
      setError(null);
      setInput("");
    } catch {
      // silently ignore — session list is still intact
    }
  }

  function handleNewChat() {
    setSessionId(null);
    setMessages([]);
    setError(null);
    textareaRef.current?.focus();
  }

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
  }

  return (
    <div className="flex h-full bg-brand-bg text-brand-primary">
      {/* Sidebar */}
      <aside className="flex w-60 flex-col border-r border-brand-surface bg-brand-surface">
        <div className="flex-shrink-0 px-4 pt-4 pb-2">
          <div className="text-xl font-semibold tracking-tight text-brand-accent">TheoCorpus</div>
        </div>

        <div className="flex-shrink-0 px-4 pb-2">
          <button
            onClick={handleNewChat}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-brand-muted transition-colors hover:bg-brand-bg hover:text-brand-primary"
          >
            <span className="text-lg leading-none">+</span>
            New conversation
          </button>
        </div>

        {sessions.length > 0 && (
          <div className="flex-shrink-0 px-4 pb-1">
            <p className="px-3 text-xs font-medium uppercase tracking-wider text-brand-muted">
              Conversations
            </p>
          </div>
        )}
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          <div className="flex flex-col gap-0.5">
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => handleLoadSession(session.id)}
                disabled={loading}
                className={`w-full truncate rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  session.id === sessionId
                    ? "bg-brand-bg text-brand-primary"
                    : "text-brand-muted hover:bg-brand-bg hover:text-brand-primary"
                }`}
              >
                {session.title ?? "New Conversation"}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-shrink-0 border-t border-brand-bg px-4 py-3">
          <button
            onClick={handleSignOut}
            className="w-full rounded-md px-3 py-2 text-left text-sm text-brand-muted transition-colors hover:bg-brand-bg hover:text-brand-primary"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Main chat area */}
      <main className="flex flex-1 flex-col overflow-hidden">
        <div
          ref={scrollContainerRef}
          className="flex-1 overflow-y-auto px-6 py-6"
          onScroll={() => {
            if (isProgrammaticScroll.current) return;
            const el = scrollContainerRef.current;
            if (!el) return;
            pinnedToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
          }}
        >
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
              <p className="text-3xl font-semibold text-brand-accent">TheoCorpus</p>
              <p className="max-w-sm text-brand-muted">
                Ask about scripture, doctrine, or Catholic tradition.
              </p>
            </div>
          ) : (
            <div className="mx-auto flex max-w-2xl flex-col gap-6">
              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex flex-col gap-1 ${
                    msg.role === "user" ? "items-end" : "items-start"
                  }`}
                >
                  <span className="text-xs text-brand-muted">
                    {msg.role === "user" ? "You" : "TheoCorpus"}
                  </span>
                  <div
                    className={`max-w-prose rounded-xl px-4 py-3 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-brand-accent/15 text-brand-primary whitespace-pre-wrap"
                        : "bg-brand-surface text-brand-primary prose-brand"
                    }`}
                  >
                    {msg.role === "user" ? (
                      msg.content
                    ) : (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          h1: ({ children }) => <h1 className="text-base font-semibold text-brand-primary mt-4 mb-2 first:mt-0">{children}</h1>,
                          h2: ({ children }) => <h2 className="text-base font-semibold text-brand-primary mt-4 mb-2 first:mt-0">{children}</h2>,
                          h3: ({ children }) => <h3 className="text-sm font-semibold text-brand-primary mt-3 mb-1 first:mt-0">{children}</h3>,
                          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
                          ul: ({ children }) => <ul className="mb-3 space-y-1 list-disc pl-5 last:mb-0">{children}</ul>,
                          ol: ({ children }) => <ol className="mb-3 space-y-1 list-decimal pl-5 last:mb-0">{children}</ol>,
                          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                          strong: ({ children }) => <strong className="font-semibold text-brand-primary">{children}</strong>,
                          em: ({ children }) => <em className="italic text-brand-muted">{children}</em>,
                          code: ({ children }) => <code className="rounded bg-brand-bg px-1 py-0.5 font-mono text-xs text-brand-accent">{children}</code>,
                          blockquote: ({ children }) => <blockquote className="border-l-2 border-brand-accent pl-3 text-brand-muted italic my-3">{children}</blockquote>,
                          hr: () => <hr className="border-brand-surface my-4" />,
                          a: ({ href, children }) => {
                            const safe = href && !href.trimStart().toLowerCase().startsWith("javascript:") ? href : "#";
                            return <a href={safe} target="_blank" rel="noopener noreferrer" className="text-brand-accent underline">{children}</a>;
                          },
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    )}
                  </div>
                </div>
              ))}

              {loading && messages[messages.length - 1]?.role !== "assistant" && (
                <div className="flex flex-col items-start gap-1">
                  <span className="text-xs text-brand-muted">TheoCorpus</span>
                  <div className="rounded-xl bg-brand-surface px-4 py-3">
                    <span className="inline-flex gap-1">
                      <span className="animate-bounce text-brand-accent" style={{ animationDelay: "0ms" }}>·</span>
                      <span className="animate-bounce text-brand-accent" style={{ animationDelay: "150ms" }}>·</span>
                      <span className="animate-bounce text-brand-accent" style={{ animationDelay: "300ms" }}>·</span>
                    </span>
                  </div>
                </div>
              )}

              {error && (
                <p className="text-center text-sm text-red-400">{error}</p>
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-brand-surface bg-brand-bg px-6 py-4">
          <div className="mx-auto flex max-w-2xl items-end gap-3">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about scripture, doctrine, or tradition…"
              rows={1}
              className="flex-1 resize-none rounded-xl border border-brand-surface bg-brand-surface px-4 py-3 text-sm text-brand-primary placeholder-brand-muted outline-none transition-colors focus:border-brand-accent"
              style={{ maxHeight: "160px", overflowY: "auto" }}
              disabled={loading}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || loading || !token}
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-accent text-brand-bg transition-opacity disabled:opacity-30"
              aria-label="Send"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 20 20"
                fill="currentColor"
                className="h-4 w-4"
              >
                <path d="M3.105 2.288a.75.75 0 0 0-.826.95l1.668 5.828a.75.75 0 0 0 .588.54l6.94 1.152a.75.75 0 0 1 0 1.483l-6.94 1.153a.75.75 0 0 0-.588.539l-1.668 5.828a.75.75 0 0 0 .826.95 28.896 28.896 0 0 0 15.293-7.154.75.75 0 0 0 0-1.115A28.897 28.897 0 0 0 3.105 2.288Z" />
              </svg>
            </button>
          </div>
          <p className="mx-auto mt-2 max-w-2xl text-center text-xs text-brand-muted">
            Press Enter to send · Shift+Enter for new line
          </p>
        </div>
      </main>
    </div>
  );
}
