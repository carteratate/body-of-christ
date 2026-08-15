"use client";

import {
  type ChunkResult,
  type CollectionOutcome,
  type SearchOutcome,
} from "@/lib/api";
import { getCollectionMeta } from "@/lib/collections";
import { ChunkCard } from "./ChunkCard";
import { ResultsSkeleton } from "./ResultsSkeleton";
import { SearchProgress } from "./SearchProgress";
import { NoResultsScreen } from "./NoResultsScreen";

interface SearchResultsProps {
  results: ChunkResult[];
  loading: boolean;
  searchId: string | null;
  token: string;
  onExploreMore: (content: string, label: string) => void;
  phase?: "searching" | "ranking" | null;
  submittedCollections: string[];
  visibleCollections: string[];
  outcome: SearchOutcome | null;
  collectionOutcomes: Record<string, CollectionOutcome>;
  isRestoring?: boolean;
  isGuest?: boolean;
  showFirstSearchHint?: boolean;
  onDismissFirstSearchHint?: () => void;
  showFirstContextHint?: boolean;
  onFirstResultExpanded?: () => void;
  onDismissFirstContextHint?: () => void;
}

function CollectionOutcomeNotice({
  collectionKey,
  outcome,
}: {
  collectionKey: string;
  outcome: CollectionOutcome;
}) {
  const meta = getCollectionMeta(collectionKey);
  const label = meta?.label ?? collectionKey;
  const message = {
    no_candidates: `No passages were retrieved from ${label} for this query.`,
    below_threshold: `No passages from ${label} met the relevance threshold for this query.`,
    retrieval_failed: `${label} could not be searched because its retrieval paths were unavailable.`,
    corpus_sync_failed: `${label} returned passages that are not currently available in the readable corpus.`,
    ranking_failed: `Passages from ${label} were retrieved, but could not be ranked.`,
    results_degraded: `${label} results are shown, but part of its preferred retrieval or ranking path was unavailable.`,
    results: "",
  }[outcome];
  if (!message) return null;
  return (
    <div className="rounded-lg border border-brand-surface bg-brand-surface/50 px-4 py-3 text-sm text-brand-muted">
      {message}
    </div>
  );
}

export function SearchResults({
  results,
  loading,
  searchId,
  token,
  onExploreMore,
  phase = null,
  submittedCollections,
  visibleCollections,
  outcome,
  collectionOutcomes,
  isRestoring = false,
  isGuest = false,
  showFirstSearchHint = false,
  onDismissFirstSearchHint,
  showFirstContextHint = false,
  onFirstResultExpanded,
  onDismissFirstContextHint,
}: SearchResultsProps) {
  if (loading && results.length === 0) {
    return isRestoring
      ? <ResultsSkeleton />
      : <SearchProgress phase={phase} collections={submittedCollections} />;
  }

  const emptyCollections = !loading
    ? submittedCollections.filter((c) => collectionOutcomes[c] && collectionOutcomes[c] !== "results")
    : [];

  // Only a successful backend terminal outcome may render an empty-results screen.
  if (
    !loading
    && results.length === 0
    && submittedCollections.length > 0
    && outcome === "no_candidates"
  ) {
    return <NoResultsScreen submittedCollections={submittedCollections} allFiltered={false} />;
  }

  if (!loading && results.length === 0) return null;

  // User toggled all filter buttons off
  if (!loading && results.length > 0 && visibleCollections.length === 0) {
    return <NoResultsScreen submittedCollections={submittedCollections} allFiltered={true} />;
  }

  const visibleResults = results.filter((r) => visibleCollections.includes(r.source.collection));

  return (
    <div className="space-y-3">
      {showFirstSearchHint && (
        <div role="status" className="relative mx-auto flex w-fit max-w-full items-center justify-between gap-3 rounded-lg border border-brand-accent/40 bg-brand-surface px-4 py-2.5 text-sm text-brand-primary shadow-lg after:absolute after:-bottom-1.5 after:left-1/2 after:h-3 after:w-3 after:-translate-x-1/2 after:rotate-45 after:border-b after:border-r after:border-brand-accent/40 after:bg-brand-surface">
          <span>Select any source card to expand and read the passage.</span>
          <button type="button" onClick={onDismissFirstSearchHint} aria-label="Dismiss search guidance" className="shrink-0 text-brand-muted hover:text-brand-primary">Got it</button>
        </div>
      )}
      {visibleResults.map((result, index) => (
        <ChunkCard
          key={result.chunk_id}
          result={result}
          index={index}
          searchId={searchId}
          token={token}
          onExploreMore={onExploreMore}
          isGuest={isGuest}
          onExpand={showFirstSearchHint ? onFirstResultExpanded : undefined}
          showOpenContextHint={showFirstContextHint}
          onDismissOpenContextHint={onDismissFirstContextHint}
        />
      ))}
      {emptyCollections.map((col) => (
        <CollectionOutcomeNotice
          key={col}
          collectionKey={col}
          outcome={collectionOutcomes[col]}
        />
      ))}
    </div>
  );
}
