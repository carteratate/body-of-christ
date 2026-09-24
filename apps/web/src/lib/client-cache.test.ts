import { afterEach, describe, expect, it, vi } from "vitest";

import { createRequestCache } from "./client-cache";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("createRequestCache", () => {
  it("coalesces concurrent requests and serves later ones from memory", async () => {
    const cache = createRequestCache<string>({ maxEntries: 2 });
    const load = vi.fn(async () => "value");

    const [first, second] = await Promise.all([cache.get("a", load), cache.get("a", load)]);
    const third = await cache.get("a", load);

    expect([first, second, third]).toEqual(["value", "value", "value"]);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("does not store a failure", async () => {
    const cache = createRequestCache<string>({ maxEntries: 2 });
    const load = vi.fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce("value");

    await expect(cache.get("a", load)).rejects.toThrow("offline");
    expect(cache.has("a")).toBe(false);
    await expect(cache.get("a", load)).resolves.toBe("value");
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("drops the least recently used entry past its size", async () => {
    const cache = createRequestCache<string>({ maxEntries: 2 });
    await cache.get("a", async () => "a");
    await cache.get("b", async () => "b");
    await cache.get("a", async () => "unused");
    await cache.get("c", async () => "c");

    expect(cache.has("a")).toBe(true);
    expect(cache.has("b")).toBe(false);
    expect(cache.has("c")).toBe(true);
  });

  it("hands a request over to a caller that joins in the same task", async () => {
    const cache = createRequestCache<string>({ maxEntries: 2 });
    const response = deferred<string>();
    const load = vi.fn(() => response.promise);
    const leaving = new AbortController();

    const first = cache.get("a", load, leaving.signal);
    leaving.abort();
    const second = cache.get("a", load);
    response.resolve("value");

    await expect(first).rejects.toMatchObject({ name: "AbortError" });
    await expect(second).resolves.toBe("value");
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("measures TTL from when a value was stored, not last read", async () => {
    vi.useFakeTimers();
    const cache = createRequestCache<string>({ maxEntries: 2, ttlMs: 1000 });
    const load = vi.fn(async () => "value");
    await cache.get("a", load);

    vi.advanceTimersByTime(500);
    await cache.get("a", load);
    vi.advanceTimersByTime(500);

    expect(cache.has("a")).toBe(false);
  });

  it("cancels a request detached by eviction once nobody waits on it", async () => {
    vi.useFakeTimers();
    const cache = createRequestCache<string>({ maxEntries: 2 });
    let sharedSignal: AbortSignal | undefined;
    const waiter = new AbortController();
    const pending = cache.get("a", (signal) => { sharedSignal = signal; return new Promise<string>(() => {}); }, waiter.signal);

    cache.evict("a");
    waiter.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    vi.advanceTimersByTime(0);

    expect(sharedSignal?.aborted).toBe(true);
  });

  it("treats an entry past its TTL as absent", async () => {
    vi.useFakeTimers();
    const cache = createRequestCache<string>({ maxEntries: 2, ttlMs: 1000 });
    const load = vi.fn(async () => "value");
    await cache.get("a", load);

    vi.advanceTimersByTime(999);
    expect(cache.has("a")).toBe(true);
    vi.advanceTimersByTime(1);
    expect(cache.has("a")).toBe(false);
    await cache.get("a", load);
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("rejects only the waiter whose signal aborts", async () => {
    const cache = createRequestCache<string>({ maxEntries: 2 });
    const response = deferred<string>();
    let sharedSignal: AbortSignal | undefined;
    const load = vi.fn((signal: AbortSignal) => { sharedSignal = signal; return response.promise; });
    const prefetch = new AbortController();

    const prefetched = cache.get("a", load, prefetch.signal);
    const real = cache.get("a", load);
    prefetch.abort();

    await expect(prefetched).rejects.toMatchObject({ name: "AbortError" });
    expect(sharedSignal?.aborted).toBe(false);
    response.resolve("value");
    await expect(real).resolves.toBe("value");
    expect(cache.has("a")).toBe(true);
  });

  it("cancels the shared request once every waiter has left, and does not store it", async () => {
    const cache = createRequestCache<string>({ maxEntries: 2 });
    const response = deferred<string>();
    let sharedSignal: AbortSignal | undefined;
    const first = new AbortController();
    const second = new AbortController();
    const load = (signal: AbortSignal) => { sharedSignal = signal; return response.promise; };

    const a = cache.get("a", load, first.signal);
    const b = cache.get("a", load, second.signal);
    const aborted = [
      expect(a).rejects.toMatchObject({ name: "AbortError" }),
      expect(b).rejects.toMatchObject({ name: "AbortError" }),
    ];
    first.abort();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(sharedSignal?.aborted).toBe(false);
    second.abort();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(sharedSignal?.aborted).toBe(true);

    response.resolve("late");
    await Promise.all(aborted);
    expect(cache.has("a")).toBe(false);
  });

  it("rejects at once for a signal that is already aborted", async () => {
    const cache = createRequestCache<string>({ maxEntries: 2 });
    const load = vi.fn(async () => "value");
    const controller = new AbortController();
    controller.abort();

    await expect(cache.get("a", load, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(load).not.toHaveBeenCalled();
  });

  it("does not let a request evicted in flight repopulate the cache", async () => {
    const cache = createRequestCache<string>({ maxEntries: 2 });
    const response = deferred<string>();
    const pending = cache.get("a", () => response.promise);

    cache.evict("a");
    response.resolve("stale");

    await expect(pending).resolves.toBe("stale");
    expect(cache.has("a")).toBe(false);
  });

  it("evicts every key a predicate matches", async () => {
    const cache = createRequestCache<string>({ maxEntries: 4 });
    await cache.get("doc-1/a", async () => "a");
    await cache.get("doc-1/b", async () => "b");
    await cache.get("doc-2/a", async () => "c");

    cache.evictWhere((key) => key.startsWith("doc-1/"));

    expect(cache.has("doc-1/a")).toBe(false);
    expect(cache.has("doc-1/b")).toBe(false);
    expect(cache.has("doc-2/a")).toBe(true);
  });
});
