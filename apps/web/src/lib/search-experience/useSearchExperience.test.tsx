// @vitest-environment jsdom

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { createSearchExperience } from "./runtime";
import { useSearchExperience } from "./useSearchExperience";

afterEach(cleanup);

describe("useSearchExperience", () => {
  it("only adapts the runtime subscription to React", () => {
    const runtime = createSearchExperience({
      audience: { kind: "guest", search: async () => undefined },
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
    runtime.send({ type: "reset" });
  });
});
