// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The loader caches its promise per module, so each test gets a fresh copy.
let createNonce: typeof import("./google-identity").createNonce;
let loadGoogleIdentity: typeof import("./google-identity").loadGoogleIdentity;

beforeEach(async () => {
  vi.resetModules();
  ({ createNonce, loadGoogleIdentity } = await import("./google-identity"));
});

function lastScript() {
  const scripts = document.head.querySelectorAll<HTMLScriptElement>(
    'script[src="https://accounts.google.com/gsi/client"]',
  );
  return scripts[scripts.length - 1];
}

afterEach(() => {
  delete window.google;
  document.head.replaceChildren();
  vi.useRealTimers();
});

describe("createNonce", () => {
  it("returns the SHA-256 hex of the raw nonce, as Supabase expects", async () => {
    const { raw, hashed } = await createNonce();
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(raw));
    const expected = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");

    expect(raw).toMatch(/^[A-Za-z0-9-_]{40,}$/);
    expect(hashed).toBe(expected);
  });

  it("differs on every call", async () => {
    const [a, b] = await Promise.all([createNonce(), createNonce()]);
    expect(a.raw).not.toBe(b.raw);
  });
});

describe("loadGoogleIdentity", () => {
  it("resolves with google.accounts.id once the script loads", async () => {
    const promise = loadGoogleIdentity();
    const id = { initialize: vi.fn(), renderButton: vi.fn() };
    window.google = { accounts: { id } };
    lastScript().dispatchEvent(new Event("load"));

    await expect(promise).resolves.toBe(id);
  });

  it("rejects when the script fails, and a later call can retry", async () => {
    const first = loadGoogleIdentity();
    lastScript().dispatchEvent(new Event("error"));
    await expect(first).rejects.toThrow("failed to load");

    const second = loadGoogleIdentity();
    expect(second).not.toBe(first);
    window.google = { accounts: { id: { initialize: vi.fn(), renderButton: vi.fn() } } };
    lastScript().dispatchEvent(new Event("load"));
    await expect(second).resolves.toBeDefined();
  });

  it("rejects when the script never loads", async () => {
    vi.useFakeTimers();
    const promise = loadGoogleIdentity(5000);
    vi.advanceTimersByTime(5000);
    await expect(promise).rejects.toThrow("timed out");
  });
});
