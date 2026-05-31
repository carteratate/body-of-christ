"use client";

interface RelevanceExplanationProps {
  explanation: string | null;
}

export function RelevanceExplanation({ explanation }: RelevanceExplanationProps) {
  if (explanation === null) {
    return (
      <div className="border border-brand-surface rounded-md p-3 mt-3">
        <p className="text-xs text-brand-muted uppercase tracking-wide mb-2">Why this is relevant</p>
        <div className="animate-pulse space-y-2">
          <div className="h-3 bg-brand-surface rounded w-full" />
          <div className="h-3 bg-brand-surface rounded w-5/6" />
          <div className="h-3 bg-brand-surface rounded w-3/4" />
        </div>
      </div>
    );
  }

  if (!explanation) {
    return null;
  }

  return (
    <div className="border border-brand-surface rounded-md p-3 mt-3">
      <p className="text-xs text-brand-muted uppercase tracking-wide mb-2">Why this is relevant</p>
      <p className="text-sm text-brand-primary leading-relaxed">{explanation}</p>
    </div>
  );
}
