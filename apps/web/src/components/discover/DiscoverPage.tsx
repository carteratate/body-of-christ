"use client";

import { useCallback, useState } from "react";
import { Search } from "lucide-react";
import { useAppContext } from "@/components/layout/AppShell";
import { RelevanceChart } from "@/components/discover/RelevanceChart";
import {
  evaluateCollections,
  EvaluateRateLimitError,
  type CollectionScore,
} from "@/lib/api";

export function DiscoverPage() {
  const { token } = useAppContext();

  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [scores, setScores] = useState<CollectionScore[] | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = useCallback(async () => {
    const q = query.trim();
    if (!q || !token || loading) return;

    setLoading(true);
    setError(null);
    setScores(null);
    setSubmittedQuery(q);

    try {
      const res = await evaluateCollections(token, q);
      setScores(res.scores);
      setRemaining(res.remaining);
      setQuery("");
    } catch (err) {
      if (err instanceof EvaluateRateLimitError) {
        setError("You've reached the daily limit of 10 evaluations. Try again tomorrow.");
        setRemaining(0);
      } else {
        setError(err instanceof Error ? err.message : "Evaluation failed");
      }
      setScores(null);
    } finally {
      setLoading(false);
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
          <h1 className="text-2xl font-semibold text-brand-primary mb-1">Custom Source Scores</h1>
          <p className="text-brand-muted text-sm mb-6">
            Type a question to see which sources are most likely to have relevant answers.
          </p>

          {/* Input */}
          <div className="flex gap-2 mb-6">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g. What does the Church teach about the Eucharist?"
              className="flex-1 bg-brand-surface border border-brand-bg rounded-lg px-3 py-2 text-sm text-brand-primary placeholder:text-brand-muted focus:outline-none focus:border-brand-accent"
              disabled={loading}
              maxLength={500}
            />
            <button
              onClick={handleSubmit}
              disabled={loading || !query.trim()}
              className="bg-brand-accent text-brand-bg rounded-lg px-4 py-2 text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-40 font-brand"
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

          {/* Loading state */}
          {loading && (
            <div className="flex items-center gap-2 text-sm text-brand-muted py-8">
              <Search size={14} className="animate-pulse" />
              Evaluating sources...
            </div>
          )}

          {/* Results */}
          {scores && submittedQuery && (
            <div>
              <div className="flex justify-end mb-4">
                <div className="max-w-[70%] rounded-2xl bg-brand-surface px-4 py-2.5 text-sm text-brand-primary">
                  {submittedQuery}
                </div>
              </div>
              <RelevanceChart scores={scores} />
            </div>
          )}

          {/* Empty state */}
          {!scores && !loading && !error && !submittedQuery && (
            <div className="text-center py-12 text-brand-muted text-sm">
              Enter a theological question above to discover which sources
              in the corpus are best equipped to answer it.
            </div>
          )}
      </div>
    </div>
  );
}
