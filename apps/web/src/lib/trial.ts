import type { GuestPreferenceDraft } from "./api";
import {
  createSearchDraft,
  DEFAULT_GUEST_SEARCH_PREFERENCES,
  type SearchDraftInitial,
} from "./search-draft";

const TOKEN_KEY = "tc_guest_session";
const COUNT_KEY = "tc_guest_search_count";
const SAVED_KEY = "tc_guest_saved_chunks";
const CURRENT_RESULTS_KEY = "theocorpus-guest-current-results";
const PREFERENCES_KEY = "tc_guest_preferences:v1";
const LEGACY_PREFERENCES_KEY = "tc_guest_preferences";
const MAX_GUEST_SEARCHES = 2;

const DEFAULT_GUEST_PREFERENCES: GuestPreferenceDraft = DEFAULT_GUEST_SEARCH_PREFERENCES;

export function getGuestPreferenceDraft(): GuestPreferenceDraft {
  if (typeof window === "undefined") return { ...DEFAULT_GUEST_PREFERENCES };
  try {
    const currentValue = window.localStorage.getItem(PREFERENCES_KEY);
    const legacyValue = currentValue === null
      ? window.localStorage.getItem(LEGACY_PREFERENCES_KEY)
      : null;
    const value = JSON.parse(currentValue ?? legacyValue ?? "null") as unknown;
    const initial = value !== null && typeof value === "object" && !Array.isArray(value)
      ? value as SearchDraftInitial
      : {};
    const preferences = createSearchDraft(initial).preferences!;
    if (legacyValue !== null) {
      try {
        window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
        window.localStorage.removeItem(LEGACY_PREFERENCES_KEY);
      } catch {}
    }
    return preferences;
  } catch {
    return { ...DEFAULT_GUEST_PREFERENCES, default_collections: [...DEFAULT_GUEST_PREFERENCES.default_collections] };
  }
}

export function saveGuestPreferenceDraft(preferences: GuestPreferenceDraft): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
  } catch {}
}

export function clearGuestPreferenceDraft(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(PREFERENCES_KEY);
    window.localStorage.removeItem(LEGACY_PREFERENCES_KEY);
  } catch {}
}

function encodeToken(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((value) => { binary += String.fromCharCode(value); });
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

export function getGuestSessionToken(): string {
  if (typeof window === "undefined") return "";
  const existing = window.localStorage.getItem(TOKEN_KEY);
  if (existing && existing.length >= 32) return existing;
  const bytes = new Uint8Array(32);
  window.crypto.getRandomValues(bytes);
  const token = encodeToken(bytes);
  window.localStorage.setItem(TOKEN_KEY, token);
  return token;
}

export function peekGuestSessionToken(): string | null {
  if (typeof window === "undefined") return null;
  const token = window.localStorage.getItem(TOKEN_KEY);
  return token && token.length >= 32 ? token : null;
}

export function getGuestSearchCount(): number {
  if (typeof window === "undefined") return 0;
  const value = Number.parseInt(window.localStorage.getItem(COUNT_KEY) ?? "0", 10);
  return Number.isFinite(value) ? Math.max(0, Math.min(MAX_GUEST_SEARCHES, value)) : 0;
}

export function markGuestSearchCompleted(): number {
  if (typeof window === "undefined") return 0;
  const count = Math.min(MAX_GUEST_SEARCHES, getGuestSearchCount() + 1);
  window.localStorage.setItem(COUNT_KEY, String(count));
  document.cookie = `tc_trial_count=${count}; path=/; max-age=2592000; SameSite=Lax`;
  return count;
}

export function guestSearchesExhausted(): boolean {
  return getGuestSearchCount() >= MAX_GUEST_SEARCHES;
}

export function getGuestSavedChunkIds(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(SAVED_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string").slice(0, 100) : [];
  } catch {
    return [];
  }
}

export function toggleGuestSavedChunk(chunkId: string): boolean {
  const saved = new Set(getGuestSavedChunkIds());
  if (saved.has(chunkId)) saved.delete(chunkId);
  else saved.add(chunkId);
  window.localStorage.setItem(SAVED_KEY, JSON.stringify([...saved].slice(0, 100)));
  return saved.has(chunkId);
}

export function clearGuestSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(COUNT_KEY);
    window.localStorage.removeItem(SAVED_KEY);
  } catch {}
  clearGuestPreferenceDraft();
  try {
    window.sessionStorage.removeItem(CURRENT_RESULTS_KEY);
  } catch {}
  document.cookie = "tc_trial_count=; path=/; max-age=0; SameSite=Lax";
}

export const GUEST_SEARCH_LIMIT = MAX_GUEST_SEARCHES;
