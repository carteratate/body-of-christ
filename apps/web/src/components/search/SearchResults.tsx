"use client";

import { type ChunkResult } from "@/lib/api";
import { ChunkCard } from "./ChunkCard";
import { ResultsSkeleton } from "./ResultsSkeleton";

interface SearchResultsProps {
  results: ChunkResult[];
  loading: boolean;
  searchId: string | null;
  token: string;
  onExploreMore: (content: string) => void;
}

export function SearchResults({
  results,
  loading,
  searchId,
  token,
  onExploreMore,
}: SearchResultsProps) {
  if (loading && results.length === 0) {
    return <ResultsSkeleton />;
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
