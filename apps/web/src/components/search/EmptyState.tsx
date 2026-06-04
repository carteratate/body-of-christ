"use client";

import { useEffect, useState } from "react";
import { trackSuggestedQueryClicked } from "@/lib/analytics";

const TAGLINES = [
  "Query the Body of Christ",
  "What Does the Church Teach?",
  "Search Scripture and Tradition",
  "Seek Wisdom from the Church",
  "Explore the Catholic Tradition",
  "Ask Across 2,000 Years",
  "Search the Communion of Saints",
  "Seek and You Shall Find",
] as const;

const SUGGESTED_QUERIES = [
  "What is the nature of the soul?",
  "How do I forgive someone who hurt me?",
  "The purpose of suffering",
  "What does the Church teach about prayer?",
  "How should I understand the Trinity?",
  "Dealing with doubt in faith",
  "Preparing for confession",
  "Finding peace in anxious times",
] as const;

interface EmptyStateProps {
  onSelectQuery: (query: string) => void;
}

export function EmptyState({ onSelectQuery }: EmptyStateProps) {
  const [tagline, setTagline] = useState<string>(TAGLINES[0]);

  useEffect(() => {
    setTagline(TAGLINES[Math.floor(Math.random() * TAGLINES.length)]);
  }, []);

  function handleChipClick(query: string) {
    trackSuggestedQueryClicked({ queryText: query });
    onSelectQuery(query);
  }

  return (
    <div className="flex flex-col items-center justify-center h-full py-16 px-4">
      <p className="text-brand-muted text-2xl mb-8 tracking-wide font-brand" suppressHydrationWarning>{tagline}</p>
      <div className="grid grid-cols-2 gap-3 w-full max-w-2xl">
        {SUGGESTED_QUERIES.map((query) => (
          <button
            key={query}
            onClick={() => handleChipClick(query)}
            className="rounded-xl border border-brand-surface bg-brand-surface px-4 py-3 text-sm text-brand-muted text-left transition-colors hover:text-brand-primary hover:border-brand-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent"
          >
            {query}
          </button>
        ))}
      </div>
    </div>
  );
}
