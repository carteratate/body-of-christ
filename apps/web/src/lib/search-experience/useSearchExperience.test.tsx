// @vitest-environment jsdom

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { createSearchExperience } from "./runtime";
import { useSearchExperience } from "./useSearchExperience";

afterEach(cleanup);

describe("useSearchExperience", () => {
  it("adapts subscription and disposes page-scoped work on unmount", () => {
    const signals: AbortSignal[] = [];
    const runtime = createSearchExperience({
      audience: {
        kind: "guest",
        search: async (_request, _callbacks, currentSignal) => {
          signals.push(currentSignal);
        },
      },
    });
    const { result, unmount } = renderHook(() => useSearchExperience(runtime));
    expect(result.current.status).toBe("idle");

    act(() => runtime.send({
      type: "submit",
      request: {
        query: "grace",
        collections: ["bible"],
        translation: "CPDV",
        quota: 3,
        origin: "fresh",
      },
    }));
    expect(result.current.status).toBe("active-search");

    unmount();
    expect(signals[0].aborted).toBe(true);
    const disposed = runtime.read();
    runtime.send({ type: "reset" });
    expect(runtime.read()).toBe(disposed);
  });
});
