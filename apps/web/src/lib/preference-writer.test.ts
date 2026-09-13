import { describe, expect, it, vi } from "vitest";

import { createPreferenceWriter } from "./preference-writer";
import type { Preferences } from "./api";


function preferences(quota: number): Preferences {
  return {
    preferred_translation: "CPDV",
    default_collections: ["bible"],
    default_quota: quota,
    last_standard_quota: quota === 10 ? 5 : quota,
    theme: "dark",
  };
}


function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}


describe("createPreferenceWriter", () => {
  it("serializes rapid changes and only confirms the newest response", async () => {
    const first = deferred<Preferences>();
    const second = deferred<Preferences>();
    const write = vi.fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const onSaved = vi.fn();
    const writer = createPreferenceWriter({ write, onSaved, onFailure: vi.fn() });

    writer.save(preferences(3));
    writer.save(preferences(5));

    expect(write).toHaveBeenCalledTimes(1);
    first.resolve(preferences(3));
    await Promise.resolve();
    expect(write).toHaveBeenCalledTimes(2);
    expect(onSaved).not.toHaveBeenCalled();

    second.resolve(preferences(5));
    await writer.whenIdle();
    expect(onSaved).toHaveBeenCalledOnce();
    expect(onSaved).toHaveBeenCalledWith(preferences(5));
  });

  it("retries the newest state once and reports only the final failure", async () => {
    const write = vi.fn().mockRejectedValue(new Error("offline"));
    const onFailure = vi.fn();
    const writer = createPreferenceWriter({ write, onSaved: vi.fn(), onFailure });

    writer.save(preferences(10));
    await writer.whenIdle();

    expect(write).toHaveBeenCalledTimes(2);
    expect(onFailure).toHaveBeenCalledOnce();
  });

  it("changes credentials without creating an overlapping writer", async () => {
    const first = deferred<Preferences>();
    const oldCredentialWrite = vi.fn().mockReturnValue(first.promise);
    const newCredentialWrite = vi.fn().mockResolvedValue(preferences(5));
    const writer = createPreferenceWriter({
      write: oldCredentialWrite,
      onSaved: vi.fn(),
      onFailure: vi.fn(),
    });

    writer.save(preferences(3));
    writer.setWrite(newCredentialWrite);
    writer.save(preferences(5));

    expect(newCredentialWrite).not.toHaveBeenCalled();
    first.resolve(preferences(3));
    await writer.whenIdle();
    expect(newCredentialWrite).toHaveBeenCalledOnce();
  });
});
