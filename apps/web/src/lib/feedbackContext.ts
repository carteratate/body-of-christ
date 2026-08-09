import type { ProductFeedbackCategory, ProductFeedbackInput } from "@/lib/api";

const STORAGE_KEY = "theocorpus-feedback-context";
const listeners = new Set<() => void>();

export type FeedbackOrigin = "navigation" | "search_result" | "search_error" | "reader";
export type FeedbackRoute = "/feedback" | "/search" | "/reader";

export interface FeedbackContext {
  category?: ProductFeedbackCategory;
  origin: FeedbackOrigin;
  route: FeedbackRoute;
  search_id?: string;
  chunk_id?: string;
  document_id?: string;
  error_code?: ProductFeedbackInput["error_code"];
  created_at?: number;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_CONTEXT_AGE_MS = 30 * 60 * 1000;
const ORIGINS: FeedbackOrigin[] = ["navigation", "search_result", "search_error", "reader"];
const ROUTES: FeedbackRoute[] = ["/feedback", "/search", "/reader"];
const CATEGORIES: ProductFeedbackCategory[] = ["bug", "content", "feature", "general"];
const ERROR_CODES = ["auth_error", "network_error", "rate_limit", "restore_not_found", "restore_unavailable", "server_error", "stream_interrupted", "unknown"];

export function saveFeedbackContext(context: FeedbackContext): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ ...context, created_at: Date.now() }));
    listeners.forEach((listener) => listener());
  } catch {}
}

export function parseFeedbackContext(raw: string | null): FeedbackContext | null {
  try {
    if (!raw) return null;
    const value = JSON.parse(raw) as FeedbackContext;
    if (!ORIGINS.includes(value.origin) || !ROUTES.includes(value.route)) return null;
    if (typeof value.created_at !== "number" || Date.now() - value.created_at > MAX_CONTEXT_AGE_MS || value.created_at > Date.now() + 60_000) return null;
    if (value.category && !CATEGORIES.includes(value.category)) return null;
    if ([value.search_id, value.chunk_id, value.document_id].some((id) => id !== undefined && (typeof id !== "string" || !UUID_RE.test(id)))) return null;
    if (value.error_code && !ERROR_CODES.includes(value.error_code)) return null;
    return value;
  } catch {
    return null;
  }
}

export function readFeedbackContextRaw(): string | null {
  try { return sessionStorage.getItem(STORAGE_KEY); } catch { return null; }
}

export function subscribeFeedbackContext(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function clearFeedbackContext(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
    listeners.forEach((listener) => listener());
  } catch {}
}
