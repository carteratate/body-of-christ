// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

import { parseFeedbackContext, readFeedbackContextRaw, saveFeedbackContext } from "./feedbackContext";

beforeEach(() => {
  sessionStorage.clear();
  vi.useRealTimers();
});

describe("feedback context", () => {
  it("stores only a validated, short-lived contextual envelope", () => {
    saveFeedbackContext({
      category: "bug",
      origin: "search_error",
      route: "/search",
      search_id: "00000000-0000-0000-0000-000000000001",
      error_code: "network_error",
    });
    expect(parseFeedbackContext(readFeedbackContextRaw())).toEqual(expect.objectContaining({
      origin: "search_error",
      route: "/search",
      error_code: "network_error",
    }));
  });

  it("rejects expired, malformed, or unbounded context", () => {
    const now = Date.now();
    expect(parseFeedbackContext(JSON.stringify({ origin: "reader", route: "/reader", created_at: now - 31 * 60 * 1000 }))).toBeNull();
    expect(parseFeedbackContext(JSON.stringify({ origin: "reader", route: "https://evil.example", created_at: now }))).toBeNull();
    expect(parseFeedbackContext(JSON.stringify({ origin: "reader", route: "/reader", document_id: "not-a-uuid", created_at: now }))).toBeNull();
  });

  it("preserves the saved-search-not-found diagnostic code", () => {
    const parsed = parseFeedbackContext(JSON.stringify({
      origin: "search_error",
      route: "/search",
      error_code: "restore_not_found",
      created_at: Date.now(),
    }));
    expect(parsed?.error_code).toBe("restore_not_found");
  });
});
