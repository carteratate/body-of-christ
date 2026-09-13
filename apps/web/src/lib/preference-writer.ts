import type { Preferences, SearchPreferenceDraft } from "./api";


interface PreferenceWriterOptions {
  write: (preferences: SearchPreferenceDraft) => Promise<Preferences>;
  onSaved: (preferences: Preferences) => void;
  onFailure: () => void;
}


export interface PreferenceWriter {
  save: (preferences: SearchPreferenceDraft) => void;
  whenIdle: () => Promise<void>;
  dispose: () => void;
  resume: () => void;
  setWrite: (write: PreferenceWriterOptions["write"]) => void;
}


export function createPreferenceWriter(options: PreferenceWriterOptions): PreferenceWriter {
  let latestVersion = 0;
  let queue: Array<{ version: number; value: SearchPreferenceDraft }> = [];
  let version = 0;
  let running: Promise<void> | null = null;
  let disposed = false;

  async function pump(): Promise<void> {
    while (!disposed && queue.length > 0) {
      let pending = queue.shift()!;
      let attempts = 0;
      let saved: Preferences | null = null;

      while (attempts < 2) {
        attempts += 1;
        try {
          saved = await options.write(pending.value);
          break;
        } catch {
          if (queue.length > 0) {
            pending = queue.at(-1)!;
            queue = [];
            attempts = 0;
            continue;
          }
          if (attempts === 2 && !disposed) options.onFailure();
        }
      }

      if (saved && pending.version === latestVersion && !disposed) options.onSaved(saved);
    }
  }

  function ensureRunning(): void {
    if (running) return;
    running = pump().finally(() => {
      running = null;
      if (!disposed && queue.length > 0) ensureRunning();
    });
  }

  return {
    save(preferences) {
      if (disposed) return;
      latestVersion = ++version;
      queue.push({ version: latestVersion, value: preferences });
      ensureRunning();
    },
    async whenIdle() {
      while (running) await running;
    },
    dispose() {
      disposed = true;
      queue = [];
    },
    resume() {
      disposed = false;
    },
    setWrite(write) {
      options.write = write;
    },
  };
}
