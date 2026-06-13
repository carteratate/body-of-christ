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
  "Seek and You Shall Find",
] as const;

const SUGGESTED_QUERIES = [
  "Is it ever right to lie? Does intention matter, or is deception always wrong?",
  "Why does God allow suffering? What is the Christian answer to evil and pain?",
  "How do grace and free will coexist? If God knows everything, how can choices be free?",
  "What is the relationship between faith and reason? Can reason reach God without revelation?",
  "Is it a sin to be wealthy? What is the proper relationship between a Christian and money?",
  "What does the tradition say about spiritual dryness, when God feels absent?",
  "What is the soul, and what happens to it after death?",
  "How do the intellect and will work together? Why do we choose things we know are bad for us?",
  "Can a person be obligated to disobey a law or authority? When does conscience override obedience?",
  "What is prayer, and how does a person actually learn to pray well?",
  "Is despair a sin? What does the Church say about a person who has lost all hope?",
  "What is the purpose of confession? How does absolution actually work?",
  "What does the Church teach about killing in war and in self-defense?",
  "What are the cardinal virtues, and why those four specifically?",
  "What is the relationship between the body and the soul? Is the body good or a burden?",
  "What does the Church teach about angels?",
  "What does it mean that God is love? How is divine love different from human love?",
  "Is anger ever justified? How do we know when it is right to be angry?",
  "What does the Church teach about death and what comes after?",
  "How should a Christian think about fear?",
  "What is the nature of conscience, and how do we form it well?",
  "Scripture says God is love and God is truth. In what sense does God not merely have these qualities but is them, and are there other things God simply is?",
] as const;

interface EmptyStateProps {
  onSelectQuery: (query: string) => void;
}

function pickRandom<T>(arr: readonly T[], n: number): T[] {
  const shuffled = [...arr].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, n);
}

export function EmptyState({ onSelectQuery }: EmptyStateProps) {
  const [tagline, setTagline] = useState<string>(TAGLINES[0]);
  const [displayedQueries, setDisplayedQueries] = useState<string[]>(
    SUGGESTED_QUERIES.slice(0, 6) as unknown as string[]
  );

  useEffect(() => {
    setTagline(TAGLINES[Math.floor(Math.random() * TAGLINES.length)]);
    setDisplayedQueries(pickRandom(SUGGESTED_QUERIES, 6));
  }, []);

  function handleChipClick(query: string) {
    trackSuggestedQueryClicked({ queryText: query });
    onSelectQuery(query);
  }

  return (
    <div className="flex flex-col items-center justify-center h-full py-16 px-4">
      <p className="text-brand-muted text-2xl mb-8 tracking-wide font-brand" suppressHydrationWarning>{tagline}</p>
      <div className="grid grid-cols-2 gap-3 w-full max-w-2xl">
        {displayedQueries.map((query) => (
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
