"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";
import { BookOpen } from "lucide-react";
import { trackSuggestedQueryClicked } from "@/lib/analytics";
import { useGuestGate } from "@/components/layout/guestGate";

const TAGLINES = [
  "Query TheoCorpus",
  "What Does the Church Teach?",
  "Search Scripture and Tradition",
  "Seek Wisdom from the Church",
  "Explore the Catholic Tradition",
  "Ask Across 2,000 Years",
  "Seek and You Shall Find",
] as const;

const SUGGESTED_QUERIES = [
  "Is it ever right to lie? Does intention matter, or is deception always wrong?",
  "Why does God allow suffering?",
  "If God knows everything that will happen, how can our choices be free?",
  "Is it a sin to be wealthy? What is the proper relationship between a Christian and money?",
  "What does the tradition say about spiritual dryness, when God feels absent?",
  "What is the soul, and what happens to it after death?",
  "What is the intellect and the will? How are they different, and how do they interact?",
  "Can a person be obligated to disobey a law or authority? When does conscience override obedience?",
  "What is prayer, and how does a person actually learn to pray well?",
  "Is despair a sin?",
  "What is the purpose of confession? How does absolution actually work?",
  "What does the Church teach about killing in war and in self-defense?",
  "What are the cardinal virtues, and why those four specifically?",
  "What is the relationship between the body and the soul?",
  "What does it mean that God is love? How is divine love different from human love?",
  "Is anger ever justified? How do we know when it is right to be angry?",
  "What does the Church teach about death and what comes after?",
  "How should a Christian think about fear?",
  "Are emotions good, bad, or neither? How should a Christian handle emotions?",
  "Give me non heretical analogies for the Trinity",
  "What exactly does it mean to be poor in spirit? What does this tell us about the Beatitudes?",
] as const;

const DISPLAYED_QUERY_COUNT = 4;

// Fisher-Yates over a copy, so every query in the pool can be shown.
function pickRandom<T>(items: readonly T[], count: number): T[] {
  const pool = [...items];
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool.slice(0, count);
}

// One random pick per page load. The server snapshot is the first four, so the
// hydrating render matches the server HTML before React swaps in the client pick.
const SERVER_QUERIES = SUGGESTED_QUERIES.slice(0, DISPLAYED_QUERY_COUNT);
let clientQueries: readonly string[] | null = null;

function getClientQueries(): readonly string[] {
  clientQueries ??= pickRandom(SUGGESTED_QUERIES, DISPLAYED_QUERY_COUNT);
  return clientQueries;
}

function subscribe(): () => void {
  return () => {};
}

interface EmptyStateProps {
  onSelectQuery: (query: string) => void;
}

export function EmptyState({ onSelectQuery }: EmptyStateProps) {
  const tagline = TAGLINES[0];
  const guestGate = useGuestGate();
  const displayedQueries = useSyncExternalStore(
    subscribe,
    getClientQueries,
    () => SERVER_QUERIES,
  );

  function handleChipClick(query: string) {
    trackSuggestedQueryClicked({ queryText: query });
    onSelectQuery(query);
  }

  // Guests can't open /sources (AppShell would bounce them to /login), so the
  // link opens the signup modal for them instead, as the sidebar's Library does.
  function handleLibraryClick(event: React.MouseEvent<HTMLAnchorElement>) {
    if (!guestGate) return;
    event.preventDefault();
    guestGate.requestSignup("library");
  }

  return (
    <div className="flex flex-col items-center justify-center h-full py-12 px-4">
      <p className="text-brand-muted text-2xl mb-7 tracking-wide font-brand">{tagline}</p>
      <div className="grid grid-cols-2 gap-3 w-full max-w-2xl max-sm:grid-cols-1">
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
      <Link href="/sources" onClick={handleLibraryClick} prefetch={guestGate ? false : undefined} className="mt-6 flex min-h-11 items-center gap-2 rounded-md border border-brand-muted/30 px-4 text-sm text-brand-muted transition-colors hover:border-brand-accent hover:text-brand-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent">
        <BookOpen size={17} /> Browse the Library
      </Link>
    </div>
  );
}
