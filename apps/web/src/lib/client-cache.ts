// In-memory request cache shared by the reader (and any later client cache).
//
// It holds successful responses only, in least-recently-used order, and
// coalesces concurrent requests for one key into a single fetch. Each caller
// keeps its own AbortSignal: aborting one waiter rejects that waiter alone, and
// the shared fetch is cancelled only once every waiter has gone. That is what
// lets a background prefetch be cancelled without failing a real request that
// joined it. The cancellation waits one task, so a component that unmounts and
// the one that replaces it (reader -> overview) can hand a request over.
//
// Nothing here survives a full page load. AppShell reloads the page when the
// signed-in user changes, so an in-memory cache cannot carry one user's data
// into another's session.

export interface RequestCacheOptions {
  /** Least-recently-used entries past this count are dropped. */
  maxEntries: number;
  /** Optional age after which a stored value is treated as absent. */
  ttlMs?: number;
}

export interface RequestCache<V> {
  /** Stored value, or a join on the in-flight request, or a new request. */
  get(key: string, load: (signal: AbortSignal) => Promise<V>, signal?: AbortSignal): Promise<V>;
  /** Store a value obtained elsewhere (e.g. under a key learned from the response). */
  set(key: string, value: V): void;
  /** Whether a fresh value is stored. Does not count as a use. */
  has(key: string): boolean;
  evict(key: string): void;
  evictWhere(predicate: (key: string) => boolean): void;
  clear(): void;
}

interface Stored<V> {
  value: V;
  storedAt: number;
}

interface InFlight<V> {
  promise: Promise<V>;
  controller: AbortController;
  waiters: number;
}

const registry = new Set<RequestCache<unknown>>();

function abortError(): DOMException {
  return new DOMException("The operation was aborted.", "AbortError");
}

export function createRequestCache<V>({ maxEntries, ttlMs }: RequestCacheOptions): RequestCache<V> {
  const values = new Map<string, Stored<V>>();
  const inFlight = new Map<string, InFlight<V>>();

  function fresh(key: string): Stored<V> | undefined {
    const stored = values.get(key);
    if (!stored) return undefined;
    if (ttlMs !== undefined && Date.now() - stored.storedAt >= ttlMs) {
      values.delete(key);
      return undefined;
    }
    return stored;
  }

  function store(key: string, value: V, storedAt = Date.now()) {
    values.delete(key);
    values.set(key, { value, storedAt });
    while (values.size > maxEntries) {
      const oldest = values.keys().next().value as string;
      values.delete(oldest);
    }
  }

  function start(key: string, load: (signal: AbortSignal) => Promise<V>): InFlight<V> {
    const controller = new AbortController();
    const entry: InFlight<V> = { promise: undefined as unknown as Promise<V>, controller, waiters: 0 };
    entry.promise = load(controller.signal).then(
      (value) => {
        // An eviction while this was in flight detaches it; its waiters still get
        // the value, but it must not repopulate the cache.
        if (inFlight.get(key) === entry) {
          inFlight.delete(key);
          store(key, value);
        }
        return value;
      },
      (error: unknown) => {
        if (inFlight.get(key) === entry) inFlight.delete(key);
        throw error;
      },
    );
    // Every waiter handles the rejection itself; this covers the case where all
    // of them have already left.
    entry.promise.catch(() => undefined);
    inFlight.set(key, entry);
    return entry;
  }

  function join(key: string, entry: InFlight<V>, signal?: AbortSignal): Promise<V> {
    entry.waiters += 1;
    return new Promise<V>((resolve, reject) => {
      let settled = false;
      const leave = () => {
        signal?.removeEventListener("abort", onAbort);
        if (settled) return;
        settled = true;
        entry.waiters -= 1;
      };
      const onAbort = () => {
        leave();
        reject(abortError());
        setTimeout(() => {
          if (entry.waiters > 0) return;
          if (inFlight.get(key) === entry) inFlight.delete(key);
          entry.controller.abort();
        }, 0);
      };
      signal?.addEventListener("abort", onAbort, { once: true });
      entry.promise.then(
        (value) => { leave(); resolve(value); },
        (error: unknown) => { leave(); reject(error); },
      );
    });
  }

  const cache: RequestCache<V> = {
    get(key, load, signal) {
      if (signal?.aborted) return Promise.reject(abortError());
      const stored = fresh(key);
      if (stored) {
        // A read refreshes the entry's LRU position, not its age.
        store(key, stored.value, stored.storedAt);
        return Promise.resolve(stored.value);
      }
      return join(key, inFlight.get(key) ?? start(key, load), signal);
    },
    set(key, value) {
      inFlight.delete(key);
      store(key, value);
    },
    has(key) {
      return fresh(key) !== undefined;
    },
    evict(key) {
      values.delete(key);
      inFlight.delete(key);
    },
    evictWhere(predicate) {
      for (const key of [...values.keys()]) if (predicate(key)) values.delete(key);
      for (const key of [...inFlight.keys()]) if (predicate(key)) inFlight.delete(key);
    },
    clear() {
      values.clear();
      inFlight.clear();
    },
  };
  registry.add(cache as RequestCache<unknown>);
  return cache;
}

/** Empties every cache created by this module. Tests call it in beforeEach. */
export function __resetClientCachesForTests(): void {
  for (const cache of registry) cache.clear();
}
