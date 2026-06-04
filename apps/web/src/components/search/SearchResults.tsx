"use client";

import { type ChunkResult } from "@/lib/api";
import { ChunkCard } from "./ChunkCard";
import { SearchProgress } from "./SearchProgress";

interface SearchResultsProps {
  results: ChunkResult[];
  loading: boolean;
  searchId: string | null;
  token: string;
  onExploreMore: (content: string, label: string) => void;
  phase?: "searching" | "ranking" | null;
  collections?: string[];
}

export function SearchResults({
  results,
  loading,
  searchId,
  token,
  onExploreMore,
  phase = null,
  collections = [],
}: SearchResultsProps) {
  if (loading && results.length === 0) {
    return <SearchProgress phase={phase} collections={collections} />;
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
