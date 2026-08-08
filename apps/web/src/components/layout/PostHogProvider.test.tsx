// @vitest-environment jsdom

import { cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PostHogProvider, sanitizeAnalyticsProperties } from "./PostHogProvider";

const posthog = vi.hoisted(() => ({ init: vi.fn(), capture: vi.fn() }));
vi.mock("posthog-js", () => ({ default: posthog }));
vi.mock("posthog-js/react", () => ({ PostHogProvider: ({ children }: { children: React.ReactNode }) => children }));
vi.mock("next/navigation", () => ({ usePathname: () => "/search" }));

afterEach(() => {
  cleanup();
  delete process.env.NEXT_PUBLIC_POSTHOG_KEY;
  vi.clearAllMocks();
});

describe("PostHogProvider privacy defaults", () => {
  it("disables automatic capture and sends a pathname-only manual pageview", async () => {
    process.env.NEXT_PUBLIC_POSTHOG_KEY = "test-key";
    render(<PostHogProvider><div>App</div></PostHogProvider>);

    expect(posthog.init).toHaveBeenCalledWith("test-key", expect.objectContaining({
      capture_pageview: false,
      autocapture: false,
      disable_session_recording: true,
      sanitize_properties: sanitizeAnalyticsProperties,
    }));
    await waitFor(() => expect(posthog.capture).toHaveBeenCalledWith("$pageview", { $current_url: "/search" }));
  });

  it("removes query strings and referrers from automatically-added properties", () => {
    expect(sanitizeAnalyticsProperties({
      $current_url: "https://theocorpus.app/search?explore=private-text",
      $referrer: "https://example.com/?secret=value",
      category: "bug",
    })).toEqual({ $current_url: "/search", category: "bug" });
  });
});
