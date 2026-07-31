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
      {visibleResults.map((result, index) => (
        <ChunkCard
          key={result.chunk_id}
          result={result}
          index={index}
          searchId={searchId}
          token={token}
          onExploreMore={onExploreMore}
          isGuest={isGuest}
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
