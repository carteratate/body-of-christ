// @vitest-environment jsdom

import { act, cleanup, renderHook } from "@testing-library/react";
import { StrictMode, type ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { createSearchExperience } from "./runtime";
import { useSearchExperience } from "./useSearchExperience";

afterEach(cleanup);

describe("useSearchExperience", () => {
  it("survives Strict Mode replay and disposes page-scoped work on unmount", async () => {
    const signals: AbortSignal[] = [];
    const runtime = createSearchExperience({
      audience: {
        kind: "guest",
        search: async (_request, _callbacks, currentSignal) => {
          signals.push(currentSignal);
        },
      },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <StrictMode>{children}</StrictMode>
    );
    const { result, unmount } = renderHook(() => useSearchExperience(runtime), { wrapper });
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
    await act(() => Promise.resolve());
    expect(signals[0].aborted).toBe(true);
    const disposed = runtime.read();
    runtime.send({ type: "reset" });
    expect(runtime.read()).toBe(disposed);
  });
});
