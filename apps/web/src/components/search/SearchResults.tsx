"use client";

import { type ChunkResult } from "@/lib/api";
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
  isRestoring?: boolean;
  isGuest?: boolean;
}

function CollectionThresholdNotice({ collectionKey }: { collectionKey: string }) {
  const meta = getCollectionMeta(collectionKey);
  return (
    <div className="rounded-lg border border-brand-surface bg-brand-surface/50 px-4 py-3 text-sm text-brand-muted">
      No passages from{" "}
      <span className="text-brand-primary font-medium">{meta?.label ?? collectionKey}</span>{" "}
      met the relevance threshold for this query.
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
  isRestoring = false,
  isGuest = false,
}: SearchResultsProps) {
  if (loading && results.length === 0) {
    return isRestoring
      ? <ResultsSkeleton />
      : <SearchProgress phase={phase} collections={submittedCollections} />;
  }

  // Collections searched but with 0 results (threshold filtered them all out)
  const collectionsWithResults = new Set(results.map((r) => r.source.collection));
  const emptyCollections = !loading
    ? submittedCollections.filter((c) => !collectionsWithResults.has(c))
    : [];

  // All searched collections returned 0 results
  if (!loading && results.length === 0 && submittedCollections.length > 0) {
    return <NoResultsScreen submittedCollections={submittedCollections} allFiltered={false} />;
  }

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
        <CollectionThresholdNotice key={col} collectionKey={col} />
      ))}
    </div>
  );
}
