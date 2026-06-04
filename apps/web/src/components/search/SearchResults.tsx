"use client";

import { type ChunkResult } from "@/lib/api";
import { ChunkCard } from "./ChunkCard";
import { ResultsSkeleton } from "./ResultsSkeleton";
import { SearchProgress } from "./SearchProgress";

interface SearchResultsProps {
  results: ChunkResult[];
  loading: boolean;
  searchId: string | null;
  token: string;
  onExploreMore: (content: string, label: string) => void;
  phase?: "searching" | "ranking" | null;
  collections?: string[];
  isRestoring?: boolean;
}

export function SearchResults({
  results,
  loading,
  searchId,
  token,
  onExploreMore,
  phase = null,
  collections = [],
  isRestoring = false,
}: SearchResultsProps) {
  if (loading && results.length === 0) {
    return isRestoring
      ? <ResultsSkeleton />
      : <SearchProgress phase={phase} collections={collections} />;
  }

  return (
    <div className="space-y-3">
      {results.map((result, index) => (
        <ChunkCard
          key={result.chunk_id}
          result={result}
          index={index}
          searchId={searchId}
          token={token}
          onExploreMore={onExploreMore}
        />
      ))}
    </div>
  );
}
