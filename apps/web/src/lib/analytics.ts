"use client";

import posthog from "posthog-js";

// All events are fired client-side only.
// User-typed query text is NEVER sent — only derived metadata (e.g. query length).
// Exception: suggested query chip labels ARE sent — they are hardcoded app strings, not user input.

export function trackSearchPerformed(params: {
  queryLength: number;
  collectionsUsed: string[];
  quotaPerSource: number;
  resultCount: number;
  translation: string;
}) {
  posthog.capture("search_performed", {
    query_length: params.queryLength,
    collections_used: params.collectionsUsed,
    quota_per_source: params.quotaPerSource,
    result_count: params.resultCount,
    translation: params.translation,
  });
}

export function trackChunkLiked(params: { collection: string; documentTitle: string; rankPosition: number; searchId: string }) {
  posthog.capture("chunk_liked", { collection: params.collection, document_title: params.documentTitle, rank_position: params.rankPosition, search_id: params.searchId });
}

export function trackChunkDisliked(params: { collection: string; documentTitle: string; rankPosition: number; searchId: string }) {
  posthog.capture("chunk_disliked", { collection: params.collection, document_title: params.documentTitle, rank_position: params.rankPosition, search_id: params.searchId });
}

export function trackDocumentOpened(params: { documentId: string; collection: string; source: "chunk_card" | "reader_nav" | "explore_more" }) {
  posthog.capture("document_opened", { document_id: params.documentId, collection: params.collection, source: params.source });
}

export function trackBookmarkCreated(params: { collection: string; rankPositionWhenSaved: number }) {
  posthog.capture("bookmark_created", { collection: params.collection, rank_position_when_saved: params.rankPositionWhenSaved });
}

export function trackBookmarkDeleted(params: { collection: string }) {
  posthog.capture("bookmark_deleted", { collection: params.collection });
}

export function trackCollectionToggled(params: { collection: string; enabled: boolean }) {
  posthog.capture("collection_toggled", { collection: params.collection, enabled: params.enabled });
}

export function trackTranslationChanged(params: { from: string; to: string }) {
  posthog.capture("translation_changed", { from: params.from, to: params.to });
}

export function trackQuotaChanged(params: { from: number; to: number }) {
  posthog.capture("quota_changed", { from: params.from, to: params.to });
}

export function trackExploreMoreClicked(params: { collection: string; source: "chunk_card" | "reader" }) {
  posthog.capture("explore_more_clicked", { collection: params.collection, source: params.source });
}

export function trackReaderNavigation(params: { documentId: string; collection: string; direction: "next" | "prev" | "jump" }) {
  posthog.capture("reader_navigation", { document_id: params.documentId, collection: params.collection, direction: params.direction });
}

export function trackRateLimitHit(params: { limitType: "per_minute" | "daily" }) {
  posthog.capture("rate_limit_hit", { limit_type: params.limitType });
}

export function trackErrorOccurred(params: { page: string; errorType: string }) {
  posthog.capture("error_occurred", { page: params.page, error_type: params.errorType });
}

export function trackSuggestedQueryClicked(params: { queryText: string }) {
  posthog.capture("suggested_query_clicked", { query_text: params.queryText });
}
