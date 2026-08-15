const TOKEN_KEY = "tc_guest_session";
const COUNT_KEY = "tc_guest_search_count";
const SAVED_KEY = "tc_guest_saved_chunks";
const CURRENT_RESULTS_KEY = "theocorpus-guest-current-results";
const MAX_GUEST_SEARCHES = 2;

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
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(COUNT_KEY);
  window.localStorage.removeItem(SAVED_KEY);
  window.sessionStorage.removeItem(CURRENT_RESULTS_KEY);
  document.cookie = "tc_trial_count=; path=/; max-age=0; SameSite=Lax";
}

export const GUEST_SEARCH_LIMIT = MAX_GUEST_SEARCHES;
