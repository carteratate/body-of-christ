"use client";

import { AlertTriangle, CloudOff, KeyRound, RotateCcw } from "lucide-react";

interface SearchFailureScreenProps {
  code?: string | null;
  stage?: string | null;
  onRetry: () => void;
  onReport?: () => void;
}

export function SearchFailureScreen({
  code,
  stage,
  onRetry,
  onReport,
}: SearchFailureScreenProps) {
  const connectionFailure = code === "stream_interrupted" || stage === "connection";
  const authFailure = code === "auth_error" || stage === "authentication";
  const rateLimited = code === "rate_limit";
  const restoreUnavailable = code === "restore_unavailable";
  const restoreNotFound = code === "restore_not_found";
  const restoreFailure = stage === "restore";
  const invalidRequest = code === "invalid_request" || stage === "validation";
  const Icon = connectionFailure ? CloudOff : authFailure ? KeyRound : AlertTriangle;
  const title = connectionFailure
    ? "The search stopped before it finished"
    : authFailure
      ? "Please sign in again"
      : rateLimited
        ? "Search limit reached"
      : restoreUnavailable
        ? "Saved results are no longer available"
      : restoreNotFound
        ? "Saved search not found"
      : restoreFailure
        ? "This saved search couldn’t be loaded"
      : invalidRequest
        ? "This search couldn't be submitted"
        : "We couldn't complete this search";
  const guidance = connectionFailure
    ? "Check your connection and try again."
    : authFailure
      ? "Your session expired. Your saved searches and passages will still be available after you sign in."
    : rateLimited
      ? "Wait until the limit resets, then try again."
    : restoreUnavailable
      ? "The search record still exists, but some or all of its linked passages have since been removed or replaced."
    : restoreNotFound
      ? "It may have been deleted, or this link may not be available to your account. Return to Search History and choose another search."
    : restoreFailure
      ? "The saved search is still in your history. Retry the request or return to Search History and choose another search."
    : invalidRequest
      ? "Check the question and selected sources, then try again."
      : "Try again. If it keeps happening, report the problem.";

  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center max-w-lg mx-auto">
      <Icon size={24} className="text-brand-accent mb-4" aria-hidden="true" />
      <p className="text-brand-primary text-base font-medium mb-3">{title}</p>
      <p className="text-brand-muted text-sm leading-relaxed mb-5">{guidance}</p>
      {!authFailure && !restoreUnavailable && !restoreNotFound && !invalidRequest && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-lg border border-brand-accent/40 px-4 py-2 text-sm text-brand-accent hover:bg-brand-accent/10"
        >
          <RotateCcw size={14} aria-hidden="true" />
          {restoreFailure ? "Retry saved search" : "Retry search"}
        </button>
      )}
      {onReport && (
        <button type="button" onClick={onReport} className="mt-3 text-xs text-brand-muted hover:text-brand-accent hover:underline">
          Report this problem
        </button>
      )}
    </div>
  );
}
