"use client";

import { getCollectionMeta } from "@/lib/collections";

interface NoResultsScreenProps {
  submittedCollections: string[];
  allFiltered: boolean;
}

export function NoResultsScreen({ submittedCollections, allFiltered }: NoResultsScreenProps) {
  if (allFiltered) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
        <p className="text-brand-muted text-sm">
          Select at least one collection in the filter bar below to see results.
        </p>
      </div>
    );
  }

  const collectionLabel =
    submittedCollections.length === 1
      ? (getCollectionMeta(submittedCollections[0])?.label ?? submittedCollections[0])
      : `the ${submittedCollections.length} selected collections`;

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center max-w-lg mx-auto">
      <p className="text-brand-primary text-base font-medium mb-3">
        No passages were found
      </p>
      <p className="text-brand-muted text-sm leading-relaxed mb-4">
        TheoCorpus completed the search successfully, but did not retrieve any candidate
        passages from {collectionLabel}.
      </p>
      <p className="text-brand-muted text-sm leading-relaxed">
        Try rephrasing your question, enabling additional collections, or increasing the
        passages-per-source quota.
      </p>
    </div>
  );
}
