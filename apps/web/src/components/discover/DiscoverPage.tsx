"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useAppContext } from "@/components/layout/AppShell";
import { RelevanceChart } from "@/components/discover/RelevanceChart";
import { COLLECTIONS } from "@/lib/collections";
import {
  evaluateCollections,
  streamExplanations,
  EvaluateRateLimitError,
  type CollectionScore,
} from "@/lib/api";

export function DiscoverPage() {
  const { token } = useAppContext();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const explainAbortRef = useRef<AbortController | null>(null);

  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [scores, setScores] = useState<CollectionScore[] | null>(null);
  const [explanations, setExplanations] = useState<Record<string, string>>({});
  const [explanationsDone, setExplanationsDone] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Abort any in-flight explain stream on unmount
  useEffect(() => {
    return () => { explainAbortRef.current?.abort(); };
  }, []);

  function autoResize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }

  // Runs before first paint too (not just on value change), so the box already
  // accounts for the wrapped "e.g. ..." placeholder height on initial render.
  useLayoutEffect(() => {
    autoResize();
  }, [query]);

  const handleSubmit = useCallback(async () => {
    const q = query.trim();
    if (!q || !token || loading) return;

    // Abort any previous explain stream
    explainAbortRef.current?.abort();
    explainAbortRef.current = null;

    setLoading(true);
    setError(null);
    setScores(null);
    setExplanations({});
    setExplanationsDone(false);

    let fetchedScores: CollectionScore[] | null = null;

    try {
      const res = await evaluateCollections(token, q);
      fetchedScores = res.scores;
      setScores(res.scores);
      setRemaining(res.remaining);
    } catch (err) {
      if (err instanceof EvaluateRateLimitError) {
        setError("You've reached the daily limit of 10 evaluations. Try again tomorrow.");
        setRemaining(0);
      } else {
        setError("We couldn't compare the collections right now. Please try again.");
      }
      setScores(null);
      setLoading(false);
      return;
    }

    setLoading(false);

    // Phase 2: stream explanations immediately after scores arrive
    if (fetchedScores && fetchedScores.length > 0) {
      const controller = new AbortController();
      explainAbortRef.current = controller;

      streamExplanations(
        token,
        q,
        fetchedScores,
        {
          onExplanation: (collection, explanation) => {
            setExplanations((prev) => ({ ...prev, [collection]: explanation }));
          },
          onDone: () => {
            setExplanationsDone(true);
            explainAbortRef.current = null;
          },
          onError: () => {
            // Silently ignore — scores already shown, explanations are best-effort
            setExplanationsDone(true);
            explainAbortRef.current = null;
          },
        },
        controller.signal,
      );
    }
  }, [query, token, loading]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-6 py-6 max-w-3xl w-full mx-auto">
        <h1 className="text-2xl font-semibold text-brand-primary mb-1">Source Guide</h1>
        <p className="text-brand-muted text-sm mb-6">
          Type a question to see which sources are most likely to have relevant answers.
        </p>

        {/* Input */}
        <div className="flex gap-2 items-end mb-6">
          <textarea
            ref={textareaRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g. What does the Church teach about the Eucharist?"
            className="flex-1 bg-brand-surface border border-brand-bg rounded-lg px-3 py-2 text-sm text-brand-primary placeholder:text-brand-muted focus:outline-none focus:border-brand-accent resize-none overflow-hidden"
            disabled={loading}
            maxLength={500}
            rows={1}
          />
          <button
            onClick={handleSubmit}
            disabled={loading || !query.trim()}
            className="bg-brand-accent text-brand-bg rounded-lg px-4 py-2 text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-40 font-brand shrink-0"
          >
            {loading ? "Scoring..." : "Score"}
          </button>
        </div>

        {/* Remaining count */}
        {remaining !== null && (
          <p className="text-xs text-brand-muted mb-4">
            {remaining} evaluation{remaining !== 1 ? "s" : ""} remaining today
          </p>
        )}

        {/* Error */}
        {error && (
          <div className="text-sm text-red-400 mb-4">{error}</div>
        )}

        {/* Loading skeleton — mirrors RelevanceChart layout exactly */}
        {loading && (
          <>
            <style>{`
              @keyframes bar-pulse {
                0%, 100% { opacity: 0.2; transform: scaleX(0.85); }
                50% { opacity: 0.7; transform: scaleX(1); }
              }
            `}</style>
            <div className="space-y-3 py-4">
              <p className="text-sm text-brand-muted mb-4 animate-pulse">
                Evaluating {COLLECTIONS.length} sources...
              </p>
              {COLLECTIONS.map((c, i) => (
                <div key={c.key}>
                  <div className="flex items-center gap-3 mb-1">
                    <span className="text-sm text-brand-muted w-44 shrink-0 truncate">
                      {c.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="w-44 shrink-0" />
                    <div className="flex-1 h-6 bg-brand-bg rounded-md overflow-hidden">
                      <div
                        className="h-full rounded-md origin-left"
                        style={{
                          width: `${30 + ((i * 17) % 50)}%`,
                          backgroundColor: c.hex,
                          animation: `bar-pulse 1.5s ease-in-out ${i * 120}ms infinite`,
                        }}
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Results */}
        {scores && !loading && (
          <RelevanceChart
            scores={scores}
            explanations={explanations}
            explanationsDone={explanationsDone}
          />
        )}

        {/* Empty state */}
        {!scores && !loading && !error && (
          <div className="text-center py-12 text-brand-muted text-sm">
            Enter a theological question above to discover which sources
            in the corpus are best equipped to answer it.
          </div>
        )}
      </div>
    </div>
  );
}
