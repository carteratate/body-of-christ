"use client";

interface ResultsSkeletonProps {
  count?: number;
}

function SkeletonCard() {
  return (
    <div className="rounded-lg bg-brand-surface border-l-4 border-brand-surface animate-pulse p-4 space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-5 bg-brand-muted/20 rounded-full w-20" />
          <div className="h-4 bg-brand-muted/20 rounded w-32" />
        </div>
        <div className="flex items-center gap-2">
          <div className="h-6 w-6 bg-brand-muted/20 rounded" />
          <div className="h-6 w-6 bg-brand-muted/20 rounded" />
          <div className="h-6 w-16 bg-brand-muted/20 rounded" />
        </div>
      </div>

      {/* Content lines */}
      <div className="space-y-2">
        <div className="h-3 bg-brand-muted/20 rounded w-full" />
        <div className="h-3 bg-brand-muted/20 rounded w-11/12" />
        <div className="h-3 bg-brand-muted/20 rounded w-4/5" />
        <div className="h-3 bg-brand-muted/20 rounded w-full" />
        <div className="h-3 bg-brand-muted/20 rounded w-3/4" />
      </div>

      {/* Explanation section */}
      <div className="border border-brand-surface rounded-md p-3 space-y-2">
        <div className="h-3 bg-brand-muted/20 rounded w-full" />
        <div className="h-3 bg-brand-muted/20 rounded w-5/6" />
        <div className="h-3 bg-brand-muted/20 rounded w-3/4" />
      </div>

      {/* Bottom action row */}
      <div className="flex justify-end gap-2">
        <div className="h-6 w-6 bg-brand-muted/20 rounded" />
        <div className="h-6 w-6 bg-brand-muted/20 rounded" />
        <div className="h-6 w-24 bg-brand-muted/20 rounded" />
      </div>
    </div>
  );
}

export function ResultsSkeleton({ count = 4 }: ResultsSkeletonProps) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
